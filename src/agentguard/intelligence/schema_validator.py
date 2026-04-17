import difflib
import importlib.resources
import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

BUNDLED_SCHEMAS = importlib.resources.files("agentguard.data.schemas.claude-code")
SCHEMAS_DIR = Path.home() / ".agentguard" / "schemas" / "claude-code"

VALID_HOOK_EVENTS: list[str] = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "Stop",
    "StopFailure",
    "TeammateIdle",
    "InstructionsLoaded",
    "ConfigChange",
    "CwdChanged",
    "FileChanged",
    "WorktreeCreate",
    "WorktreeRemove",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Elicitation",
    "ElicitationResult",
]

# Known field name corrections for typo suggestions
_FIELD_CORRECTIONS: dict[str, dict[str, str]] = {
    "agent": {
        "allowedTools": "tools",
        "disallowed_tools": "disallowedTools",
        "allowed_tools": "tools",
        "permission_mode": "permissionMode",
        "max_turns": "maxTurns",
        "mcp_servers": "mcpServers",
        "initial_prompt": "initialPrompt",
    },
    "skill": {
        "argumentHint": "argument-hint",
        "disableModelInvocation": "disable-model-invocation",
        "userInvocable": "user-invocable",
        "allowedTools": "allowed-tools",
        "allowed_tools": "allowed-tools",
        "tools": "allowed-tools",
    },
}


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single validation issue found in an asset."""

    severity: IssueSeverity
    asset_type: str
    name: str
    message: str
    file_path: str = ""
    field: str = ""
    value: str = ""
    expected: str = ""
    fix: str = ""


class ValidationResult(BaseModel):
    """Result of validating one or more assets."""

    issues: list[ValidationIssue] = Field(default_factory=list)
    files_checked: int = 0

    @property
    def valid(self) -> bool:
        """True if no errors were found (warnings are acceptable)."""
        return not any(i.severity == IssueSeverity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]


class SchemaDiff(BaseModel):
    """Diff between local and upstream schemas."""

    added_fields: dict[str, list[str]] = Field(default_factory=dict)
    removed_fields: dict[str, list[str]] = Field(default_factory=dict)
    changed_fields: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.added_fields or self.removed_fields or self.changed_fields)


def _ensure_schemas_installed() -> None:
    """Copy bundled schemas to ~/.agentguard/schemas/ if not present."""
    if SCHEMAS_DIR.exists() and (SCHEMAS_DIR / "meta.json").exists():
        return
    reset_schemas()


def reset_schemas(target_dir: Path | None = None) -> Path:
    """Restore bundled default schemas to the target directory.

    Args:
        target_dir: Override directory. Defaults to ~/.agentguard/schemas/claude-code/.

    Returns:
        Path to the schema directory.
    """
    dest = target_dir or SCHEMAS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    for filename in (
        "agent.json",
        "skill-extensions.json",
        "hook-handler.json",
        "hook-events.json",
        "meta.json",
    ):
        resource = BUNDLED_SCHEMAS.joinpath(filename)
        content = resource.read_text(encoding="utf-8")
        (dest / filename).write_text(content, encoding="utf-8")

    return dest


def _load_schema(schema_name: str, schema_dir: Path | None = None) -> dict[str, Any]:
    """Load a JSON Schema file from the schema directory.

    Args:
        schema_name: Filename of the schema (e.g., "agent.json").
        schema_dir: Override schema directory.

    Returns:
        Parsed JSON Schema dictionary.

    Raises:
        FileNotFoundError: If the schema file doesn't exist.
        json.JSONDecodeError: If the schema file is invalid JSON.
    """
    directory = schema_dir or SCHEMAS_DIR
    path = directory / schema_name

    if not path.exists():
        raise FileNotFoundError(
            f'Schema file "{schema_name}" is missing. Run "agentguard schema reset" '
            "to restore bundled defaults."
        )

    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f'Schema file "{schema_name}" is corrupt. Run "agentguard schema reset" '
            f"to restore bundled defaults. Original error: {e.msg}",
            e.doc,
            e.pos,
        ) from e


def _schema_name_for_type(asset_type: str) -> str:
    """Map an asset type string to its schema filename."""
    mapping = {
        "agent": "agent.json",
        "skill": "skill-extensions.json",
        "hook": "hook-handler.json",
    }
    return mapping.get(asset_type, "")


def _suggest_field_fix(asset_type: str, field_name: str) -> str:
    """Suggest a correction for a misnamed field.

    Args:
        asset_type: The asset type (agent, skill, etc.).
        field_name: The unknown field name.

    Returns:
        Suggestion string, or empty if no suggestion.
    """
    corrections = _FIELD_CORRECTIONS.get(asset_type, {})
    if field_name in corrections:
        return f'Did you mean "{corrections[field_name]}"?'

    # Try close matches against schema properties
    try:
        schema = _load_schema(_schema_name_for_type(asset_type))
        known_fields = list(schema.get("properties", {}).keys())
        matches = difflib.get_close_matches(field_name, known_fields, n=1, cutoff=0.6)
        if matches:
            return f'Did you mean "{matches[0]}"?'
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return ""


def _jsonschema_error_to_issue(
    error: jsonschema.ValidationError,
    asset_type: str,
    name: str,
    file_path: str,
) -> ValidationIssue:
    """Convert a single jsonschema error into a ValidationIssue."""
    field = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else ""
    value = str(error.instance) if error.instance is not None else ""

    if error.validator == "required":
        missing = error.message.split("'")[1] if "'" in error.message else ""
        return ValidationIssue(
            severity=IssueSeverity.ERROR,
            asset_type=asset_type,
            name=name,
            message=f'Missing required field "{missing}".',
            file_path=file_path,
            field=missing,
            fix=f'Add the "{missing}" field.',
        )

    if error.validator == "enum":
        expected_values = error.schema.get("enum", [])
        return ValidationIssue(
            severity=IssueSeverity.ERROR,
            asset_type=asset_type,
            name=name,
            message=(f'Field "{field}" value "{value}" not in {expected_values}.'),
            file_path=file_path,
            field=field,
            value=value,
            expected=f"one of {expected_values}",
            fix=f"Change {field} to a valid value.",
        )

    if error.validator == "type":
        expected_type = error.schema.get("type", "")
        return ValidationIssue(
            severity=IssueSeverity.ERROR,
            asset_type=asset_type,
            name=name,
            message=(
                f'Field "{field}" expects {expected_type},'
                f" got {type(error.instance).__name__}."
            ),
            file_path=file_path,
            field=field,
            value=value,
            expected=expected_type,
            fix=f"Change {field} to {expected_type} type.",
        )

    return ValidationIssue(
        severity=IssueSeverity.ERROR,
        asset_type=asset_type,
        name=name,
        message=error.message,
        file_path=file_path,
        field=field,
        value=value,
    )


def validate_frontmatter(
    frontmatter: dict[str, Any],
    asset_type: str,
    name: str,
    file_path: str = "",
    schema_dir: Path | None = None,
) -> ValidationResult:
    """Validate asset frontmatter against vendor extension schemas.

    Unknown fields produce warnings (forward-compatible). Missing required fields,
    type mismatches, and invalid enums produce errors.

    Args:
        frontmatter: The parsed YAML frontmatter dictionary.
        asset_type: Asset type string ("agent", "skill", "hook").
        name: Asset name for error messages.
        file_path: Optional file path for error messages.
        schema_dir: Override schema directory.

    Returns:
        ValidationResult with any issues found.
    """
    result = ValidationResult(files_checked=1)
    schema_file = _schema_name_for_type(asset_type)

    if not schema_file:
        return result

    directory = schema_dir or SCHEMAS_DIR
    _ensure_schemas_installed()

    try:
        schema = _load_schema(schema_file, directory)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        result.issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                asset_type=asset_type,
                name=name,
                message=str(e),
                file_path=file_path,
            )
        )
        return result

    # Separate unknown fields (warn) from schema-known validation (error)
    known_props = set(schema.get("properties", {}).keys())
    unknown_fields = set(frontmatter.keys()) - known_props

    for field in sorted(unknown_fields):
        suggestion = _suggest_field_fix(asset_type, field)
        fix_msg = f" {suggestion}" if suggestion else ""
        result.issues.append(
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                asset_type=asset_type,
                name=name,
                message=f'Unknown field "{field}".{fix_msg}',
                file_path=file_path,
                field=field,
                fix=suggestion,
            )
        )

    # Validate known fields using jsonschema (skip additionalProperties check)
    # We create a relaxed copy that allows unknown fields
    relaxed_schema = {**schema, "additionalProperties": True}

    validator = jsonschema.Draft202012Validator(relaxed_schema)
    for error in validator.iter_errors(frontmatter):
        result.issues.append(
            _jsonschema_error_to_issue(error, asset_type, name, file_path)
        )

    return result


def _detect_asset_info(path: Path) -> tuple[str, str] | None:
    """Detect asset type and name fallback from file path.

    Returns:
        Tuple of (asset_type, name_fallback) or None if unrecognized.
    """
    parts = [p.lower() for p in path.parts]
    if "agents" in parts and path.suffix == ".md":
        return ("agent", path.stem)
    if path.name == "SKILL.md" or "skills" in parts:
        return ("skill", path.parent.name)
    return None


def _validate_hook_events(content: str, path: Path) -> ValidationResult:
    """Validate hook event names in a JSON settings/hooks file."""
    result = ValidationResult(files_checked=1)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        result.issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                asset_type="hook",
                name=path.name,
                message="Invalid JSON",
                file_path=str(path),
            )
        )
        return result

    for event_name in data.get("hooks", {}):
        if event_name in VALID_HOOK_EVENTS:
            continue
        matches = difflib.get_close_matches(
            event_name, VALID_HOOK_EVENTS, n=1, cutoff=0.6
        )
        fix = f'Did you mean "{matches[0]}"?' if matches else ""
        result.issues.append(
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                asset_type="hook",
                name=path.name,
                message=f'Unknown hook event "{event_name}".{f" {fix}" if fix else ""}',
                file_path=str(path),
                field=event_name,
                fix=fix,
            )
        )

    return result


def validate_asset_file(
    path: Path,
    schema_dir: Path | None = None,
) -> ValidationResult:
    """Validate a single asset file against the schema registry.

    Determines asset type from the file location and validates accordingly.

    Args:
        path: Path to the asset file.
        schema_dir: Override schema directory.

    Returns:
        ValidationResult with any issues found.
    """
    from agentguard.core.parsers import _split_frontmatter

    if not path.exists():
        return ValidationResult(
            files_checked=1,
            issues=[
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    asset_type="unknown",
                    name=path.name,
                    message=f"File not found: {path}",
                    file_path=str(path),
                )
            ],
        )

    content = path.read_text(encoding="utf-8")

    # Agent or skill: validate frontmatter against schema
    asset_info = _detect_asset_info(path)
    if asset_info:
        asset_type, name_fallback = asset_info
        frontmatter, _ = _split_frontmatter(content)
        name = frontmatter.get("name", name_fallback)
        return validate_frontmatter(
            frontmatter, asset_type, name, str(path), schema_dir
        )

    # Hook/settings files: validate event names
    if path.name in ("hooks.json", "settings.json", "settings.local.json"):
        return _validate_hook_events(content, path)

    # Unknown file type
    return ValidationResult(files_checked=1)


def show_schema(asset_type: str, schema_dir: Path | None = None) -> dict[str, Any]:
    """Return the current schema for an asset type.

    Args:
        asset_type: Asset type ("agent", "skill", "hook").
        schema_dir: Override schema directory.

    Returns:
        The JSON Schema dictionary.
    """
    _ensure_schemas_installed()
    schema_file = _schema_name_for_type(asset_type)
    if not schema_file:
        return {}
    return _load_schema(schema_file, schema_dir)


def check_schemas(schema_dir: Path | None = None) -> SchemaDiff:
    """Compare installed schemas against bundled defaults.

    This is the offline version that compares against bundled schemas.
    A future version can fetch from upstream URLs.

    Args:
        schema_dir: Override schema directory.

    Returns:
        SchemaDiff showing added, removed, and changed fields.
    """
    _ensure_schemas_installed()
    directory = schema_dir or SCHEMAS_DIR
    diff = SchemaDiff()

    for schema_name in ("agent.json", "skill-extensions.json", "hook-handler.json"):
        try:
            local_schema = _load_schema(schema_name, directory)
            resource = BUNDLED_SCHEMAS.joinpath(schema_name)
            bundled_schema = json.loads(resource.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        local_props = set(local_schema.get("properties", {}).keys())
        bundled_props = set(bundled_schema.get("properties", {}).keys())

        added = bundled_props - local_props
        removed = local_props - bundled_props

        if added:
            diff.added_fields[schema_name] = sorted(added)
        if removed:
            diff.removed_fields[schema_name] = sorted(removed)

        # Check for changed field definitions
        common = local_props & bundled_props
        changed: list[str] = []
        local_prop_defs = local_schema.get("properties", {})
        bundled_prop_defs = bundled_schema.get("properties", {})
        for field in sorted(common):
            local_def = local_prop_defs.get(field)
            bundled_def = bundled_prop_defs.get(field)
            if local_def is None or bundled_def is None:
                continue
            if local_def != bundled_def:
                changed.append(field)
        if changed:
            diff.changed_fields[schema_name] = changed

    return diff


def update_schemas(schema_dir: Path | None = None) -> SchemaDiff:
    """Update schemas from bundled defaults (offline update).

    Args:
        schema_dir: Override schema directory.

    Returns:
        SchemaDiff that was applied.
    """
    diff = check_schemas(schema_dir)
    if diff.has_changes:
        reset_schemas(schema_dir)

        # Update meta.json timestamp
        directory = schema_dir or SCHEMAS_DIR
        meta_path = directory / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["last_fetched"] = datetime.now(UTC).isoformat()
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return diff


def schema_is_stale(schema_dir: Path | None = None, max_days: int = 90) -> bool:
    """Check if schemas haven't been updated in max_days.

    Args:
        schema_dir: Override schema directory.
        max_days: Number of days before schemas are considered stale.

    Returns:
        True if schemas are stale.
    """
    directory = schema_dir or SCHEMAS_DIR
    meta_path = directory / "meta.json"

    if not meta_path.exists():
        return True

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        last_fetched = datetime.fromisoformat(meta.get("last_fetched", "2000-01-01"))
        age = datetime.now(UTC) - last_fetched.replace(tzinfo=UTC)
        return age.days > max_days
    except (ValueError, TypeError):
        return True
