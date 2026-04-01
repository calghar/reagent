import logging
import re

import yaml
from pydantic import BaseModel

from reagent.core.parsers import AssetType

logger = logging.getLogger(__name__)

# Fields that are required per asset type in frontmatter
REQUIRED_FIELDS: dict[AssetType, set[str]] = {
    AssetType.AGENT: {"name", "description"},
    AssetType.SKILL: {"name", "description"},
    AssetType.HOOK: set(),
    AssetType.COMMAND: set(),
    AssetType.RULE: {"description"},
    AssetType.CLAUDE_MD: set(),
}


class GeneratedAsset(BaseModel):
    """A parsed LLM-generated asset."""

    asset_type: AssetType
    frontmatter: dict[str, object]
    body: str
    raw_response: str


class ParseError(Exception):
    """LLM response could not be parsed into a valid asset."""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences wrapping the content."""
    # Match ```markdown, ```yaml, ```json, or plain ```
    pattern = r"^```(?:markdown|yaml|json|md)?\s*\n(.*?)```\s*$"
    match = re.match(pattern, text.strip(), re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _strip_explanation_text(text: str) -> str:
    """Remove leading/trailing explanation text around the asset content.

    LLMs sometimes add "Here is the agent:" or similar before the actual
    frontmatter, or trailing explanations after the body.
    """
    # Find the first --- and work from there
    first_delim = text.find("---")
    if first_delim == -1:
        return text

    # Strip any leading text before the first ---
    cleaned = text[first_delim:]

    # Find if there's a trailing explanation after the content
    # (look for patterns like "\n\nThis agent..." or "\n\nNote:" after the body)
    # We keep everything up to a double-newline followed by common explanation starters
    trailing_patterns = (
        "\n\nThis ",
        "\n\nNote:",
        "\n\nThe above",
        "\n\nI've ",
        "\n\nHere's ",
    )
    trailing_pos = -1
    for pat in trailing_patterns:
        idx = cleaned.find(pat)
        if idx != -1 and (trailing_pos == -1 or idx < trailing_pos):
            trailing_pos = idx
    if trailing_pos != -1:
        # Only strip if it's clearly after the body (not inside frontmatter)
        parts = cleaned.split("---", 2)
        if len(parts) >= 3:
            # We have frontmatter + body; check if trailing pattern is in body
            body_start = len(parts[0]) + 3 + len(parts[1]) + 3
            if trailing_pos >= body_start:
                cleaned = cleaned[:trailing_pos]

    return cleaned.strip()


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split content into frontmatter dict and body string.

    Handles:
    - Standard ``---\\nYAML\\n---\\nbody`` format
    - Missing closing delimiter (treat everything as frontmatter attempt)
    - Empty frontmatter
    - Invalid YAML (raises ParseError)

    Returns:
        Tuple of (frontmatter_dict, body_string).
    """
    stripped = text.strip()
    if not stripped.startswith("---"):
        # No frontmatter — entire thing is body
        return {}, stripped

    # Find the closing ---
    rest = stripped[3:].lstrip("\n")
    close_idx = rest.find("\n---")
    if close_idx == -1:
        # No closing delimiter — try parsing as YAML anyway
        try:
            fm = yaml.safe_load(rest)
            if isinstance(fm, dict):
                return fm, ""
        except yaml.YAMLError:
            pass
        return {}, stripped

    fm_text = rest[:close_idx]
    body = rest[close_idx + 4 :].strip()

    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in frontmatter: {exc}"
        raise ParseError(msg) from exc

    if not isinstance(fm, dict):
        return {}, stripped

    return fm, body


def _validate_frontmatter(
    fm: dict[str, object],
    asset_type: AssetType,
) -> list[str]:
    """Validate frontmatter fields for the given asset type.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []
    required = REQUIRED_FIELDS.get(asset_type, set())
    for field in required:
        if field not in fm:
            errors.append(f"Missing required field: {field}")
        elif not fm[field]:
            errors.append(f"Empty required field: {field}")

    # Type-specific validation
    if asset_type == AssetType.AGENT:
        _validate_agent_fm(fm, errors)
    elif asset_type == AssetType.SKILL:
        _validate_skill_fm(fm, errors)

    return errors


def _validate_agent_fm(fm: dict[str, object], errors: list[str]) -> None:
    """Agent-specific frontmatter validation."""
    if "tools" in fm:
        tools = fm["tools"]
        if not isinstance(tools, list):
            errors.append("'tools' must be a list")
    if "model" in fm:
        valid_models = {
            "sonnet",
            "opus",
            "haiku",
            "inherit",
            "claude-sonnet-4-20250514",
            "claude-haiku-4-20250414",
        }
        model = str(fm["model"])
        if model not in valid_models and not model.startswith("claude-"):
            errors.append(f"Invalid model: {model}")
    if "permissionMode" in fm:
        valid_modes = {
            "default",
            "acceptEdits",
            "dontAsk",
            "bypassPermissions",
            "plan",
        }
        if fm["permissionMode"] not in valid_modes:
            errors.append(f"Invalid permissionMode: {fm['permissionMode']}")


def _validate_skill_fm(fm: dict[str, object], errors: list[str]) -> None:
    """Skill-specific frontmatter validation."""
    if "allowed-tools" in fm:
        tools = fm["allowed-tools"]
        if not isinstance(tools, list):
            errors.append("'allowed-tools' must be a list")
    if "name" in fm:
        name = str(fm["name"])
        if len(name) > 64:
            errors.append(f"name exceeds 64 chars: {len(name)}")
        if not re.match(r"^[a-z0-9-]+$", name):
            errors.append(f"name must be lowercase/hyphens: {name}")


def parse_llm_response(
    text: str,
    asset_type: AssetType,
) -> GeneratedAsset:
    """Parse raw LLM output into a GeneratedAsset.

    Handles common LLM artifacts: code fences, explanation text,
    missing frontmatter.

    Args:
        text: Raw LLM response text.
        asset_type: Expected asset type.

    Returns:
        Parsed GeneratedAsset.

    Raises:
        ParseError: If the response cannot be parsed.
    """
    if not text.strip():
        msg = "Empty LLM response"
        raise ParseError(msg)

    # Strip LLM artifacts
    cleaned = _strip_code_fences(text)
    cleaned = _strip_explanation_text(cleaned)

    # Special case: hooks are JSON, not frontmatter
    if asset_type == AssetType.HOOK:
        return GeneratedAsset(
            asset_type=asset_type,
            frontmatter={},
            body=cleaned,
            raw_response=text,
        )

    # CLAUDE.md may not have frontmatter
    if asset_type == AssetType.CLAUDE_MD and not cleaned.startswith("---"):
        return GeneratedAsset(
            asset_type=asset_type,
            frontmatter={},
            body=cleaned,
            raw_response=text,
        )

    fm, body = split_frontmatter(cleaned)

    errors = _validate_frontmatter(fm, asset_type)
    if errors:
        msg = f"Frontmatter validation failed: {'; '.join(errors)}"
        raise ParseError(msg)

    return GeneratedAsset(
        asset_type=asset_type,
        frontmatter=fm,
        body=body,
        raw_response=text,
    )
