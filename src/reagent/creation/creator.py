import asyncio
import logging
from pathlib import Path
from typing import Any

import click

from reagent.creation.generators import (
    generate_claude_md,
    generate_command,
    generate_hook,
    generate_rule,
    generate_settings,
)
from reagent.intelligence.analyzer import RepoProfile, analyze_repo
from reagent.intelligence.patterns import (
    PatternTemplate,
)
from reagent.intelligence.schema_validator import validate_frontmatter

logger = logging.getLogger(__name__)

VALID_ASSET_TYPES = ("agent", "skill", "hook", "command", "rule")


class AssetDraft:
    """A generated asset ready for review and installation."""

    def __init__(
        self,
        asset_type: str,
        name: str,
        content: str,
        target_path: Path,
        origin: str = "reagent-create",
    ) -> None:
        self.asset_type = asset_type
        self.name = name
        self.content = content
        self.target_path = target_path
        self.origin = origin

    def write(self) -> Path:
        """Write the asset to its target path.

        Returns:
            The path the asset was written to.
        """
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path.write_text(self.content, encoding="utf-8")
        return self.target_path


def _infer_name(asset_type: str, repo_profile: RepoProfile) -> str:
    """Infer a default name for a new asset based on repo profile.

    Args:
        asset_type: The asset type.
        repo_profile: Repository profile with language info.

    Returns:
        A name string like ``python-agent``.
    """
    lang = repo_profile.primary_language or "generic"
    return f"{lang}-{asset_type}"


def _target_path(
    asset_type: str,
    name: str,
    repo_path: Path,
) -> Path:
    """Compute the target file path for a new asset.

    Args:
        asset_type: The asset type.
        name: The asset name.
        repo_path: The repository root.

    Returns:
        Absolute path for the new asset file.
    """
    claude_dir = repo_path / ".claude"
    if asset_type == "agent":
        return claude_dir / "agents" / f"{name}.md"
    elif asset_type == "skill":
        return claude_dir / "skills" / name / "SKILL.md"
    elif asset_type == "hook":
        return claude_dir / "hooks.json"
    elif asset_type == "command":
        return claude_dir / "commands" / f"{name}.md"
    elif asset_type == "rule":
        return claude_dir / "rules" / f"{name}.md"
    else:
        return claude_dir / f"{name}.md"


_KNOWN_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Agent",
    "WebFetch",
    "WebSearch",
    "Task",
]


def _extract_key_value_pairs(text: str) -> dict[str, str]:
    """Extract explicit ``key: value`` pairs from outline text.

    Args:
        text: User-provided outline text.

    Returns:
        Dict of extracted field-value pairs.
    """
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower().replace(" ", "-")
        value = value.strip()
        if key and value and len(key) < 30:
            fields[key] = value
    return fields


def _extract_tool_mentions(text_lower: str) -> list[str]:
    """Find mentioned tool names in lowercased text.

    Args:
        text_lower: Lowercased user text.

    Returns:
        List of matched tool names (original casing).
    """
    return [t for t in _KNOWN_TOOLS if t.lower() in text_lower]


def _extract_hook_events(text_lower: str) -> list[str]:
    """Find mentioned hook event names in lowercased text.

    Args:
        text_lower: Lowercased user text.

    Returns:
        List of matching event names.
    """
    from reagent.intelligence.schema_validator import VALID_HOOK_EVENTS

    return [e for e in VALID_HOOK_EVENTS if e.lower() in text_lower]


def _parse_outline(text: str, asset_type: str) -> dict[str, Any]:
    """Parse a rough user description into structured fields.

    Extracts intent, explicit field values, and tool mentions from
    a plain-text description.

    Args:
        text: User-provided outline text.
        asset_type: Target asset type.

    Returns:
        Dict of extracted field-value pairs.
    """
    fields: dict[str, Any] = dict(_extract_key_value_pairs(text))
    text_lower = text.lower()

    mentioned_tools = _extract_tool_mentions(text_lower)
    if mentioned_tools:
        key = "tools" if asset_type == "agent" else "allowed-tools"
        fields[key] = mentioned_tools

    for model in ("sonnet", "opus", "haiku"):
        if model in text_lower:
            fields["model"] = model
            break

    if asset_type == "hook":
        events = _extract_hook_events(text_lower)
        if events:
            fields["events"] = events

    if "description" not in fields:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        if len(first_line) <= 200:
            fields["description"] = first_line

    return fields


def create_from_outline(
    outline_text: str,
    asset_type: str,
    repo_path: Path,
    name: str | None = None,
    profile: RepoProfile | None = None,
) -> AssetDraft:
    """Create an asset from a rough user description.

    Args:
        outline_text: Plain text description of the desired asset.
        asset_type: Target asset type.
        repo_path: Repository root path.
        name: Optional asset name (inferred if not provided).
        profile: Optional pre-computed repo profile.

    Returns:
        AssetDraft ready for review.
    """
    if profile is None:
        profile = analyze_repo(repo_path)

    fields = _parse_outline(outline_text, asset_type)

    # Infer name
    if not name:
        name = str(fields.get("name", _infer_name(asset_type, profile)))
    fields["name"] = name

    # Infer missing fields from profile
    if "description" not in fields or not fields["description"]:
        title = name.replace("-", " ").title()
        fields["description"] = f"{title} for {profile.repo_name}"

    # Generate content based on asset type
    content = _build_asset_from_fields(asset_type, fields, profile)

    target = _target_path(asset_type, name, repo_path)

    return AssetDraft(
        asset_type=asset_type,
        name=name,
        content=content,
        target_path=target,
        origin="reagent-create-outline",
    )


def _build_asset_from_fields(
    asset_type: str,
    fields: dict[str, Any],
    profile: RepoProfile,
) -> str:
    """Build asset content from extracted fields.

    Args:
        asset_type: The asset type.
        fields: Extracted field values from outline or interactive input.
        profile: Repository profile for context.

    Returns:
        Rendered asset content string.
    """
    name = fields.get("name", "unnamed")
    desc = fields.get("description", "")

    if asset_type == "agent":
        tools = fields.get("tools", ["Read", "Glob", "Grep"])
        model = fields.get("model", "")
        content = f"---\nname: {name}\ndescription: {desc}\n"
        if model:
            content += f"model: {model}\n"
        content += "tools:\n"
        for t in tools:
            content += f"  - {t}\n"
        content += f"---\n# {name.replace('-', ' ').title()}\n\n"
        content += f"{desc}\n"
        return content

    elif asset_type == "skill":
        tools = fields.get("allowed-tools", ["Read", "Glob", "Grep"])
        tools_str = ", ".join(tools)
        content = (
            f"---\n"
            f"name: {name}\n"
            f"description: {desc}\n"
            f"allowed-tools: [{tools_str}]\n"
            f"---\n"
            f"# {name.replace('-', ' ').title()}\n\n"
            f"{desc}\n"
        )
        return content

    elif asset_type == "rule":
        return generate_rule(name, profile)

    elif asset_type == "command":
        return generate_command(name, profile)

    elif asset_type == "hook":
        return generate_hook(name, profile)

    logger.warning("Unknown asset type %r in _build_asset_from_fields", asset_type)
    return ""


def _load_interactive_schema(
    asset_type: str,
    schema_dir: Path | None,
) -> dict[str, Any]:
    """Load the schema for interactive mode prompts.

    Args:
        asset_type: Target asset type.
        schema_dir: Override schema directory.

    Returns:
        Loaded JSON schema dict, or empty dict on failure.
    """
    from reagent.intelligence.schema_validator import (
        _ensure_schemas_installed,
        _load_schema,
        _schema_name_for_type,
    )

    schema_file = _schema_name_for_type(asset_type)
    if not schema_file:
        return {}
    try:
        _ensure_schemas_installed()
        return _load_schema(schema_file, schema_dir)
    except (FileNotFoundError, ValueError):
        return {}


def _prompt_for_field(
    field_name: str,
    field_schema: dict[str, Any],
    is_required: bool,
    default: str,
) -> Any:
    """Prompt the user for a single field value.

    Args:
        field_name: Schema field name.
        field_schema: JSON Schema definition for the field.
        is_required: Whether the field is required.
        default: Default value string.

    Returns:
        Parsed value (str, int, bool, or list), or None to skip.
    """
    field_type = field_schema.get("type", "string")
    desc = field_schema.get("description", "")
    enum_values = field_schema.get("enum")

    prompt_text = f"{field_name}"
    if desc:
        prompt_text += f" ({desc})"
    if default:
        prompt_text += f" [{default}]"
    if is_required:
        prompt_text += " *"
    if enum_values:
        prompt_text += f" ({'/'.join(enum_values)})"

    value = click.prompt(
        prompt_text,
        default=default or "",
        show_default=False,
    )

    if not value and not is_required:
        return None

    if field_type == "integer":
        try:
            return int(value)
        except ValueError:
            return None
    if field_type == "boolean":
        return value.lower() in ("true", "yes", "1")
    if field_type == "array":
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def create_interactive(
    asset_type: str,
    repo_path: Path,
    profile: RepoProfile | None = None,
    schema_dir: Path | None = None,
) -> AssetDraft:
    """Create an asset through interactive field-by-field prompts.

    Args:
        asset_type: Target asset type.
        repo_path: Repository root path.
        profile: Optional pre-computed repo profile.
        schema_dir: Override schema directory.

    Returns:
        AssetDraft ready for review.
    """
    if profile is None:
        profile = analyze_repo(repo_path)

    schema = _load_interactive_schema(asset_type, schema_dir)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    for field_name, field_schema in properties.items():
        default = _smart_default(field_name, asset_type, profile)
        result = _prompt_for_field(
            field_name,
            field_schema,
            field_name in required,
            default,
        )
        if result is not None:
            fields[field_name] = result

    name = fields.get("name", _infer_name(asset_type, profile))
    content = _build_asset_from_fields(asset_type, fields, profile)
    target = _target_path(asset_type, str(name), repo_path)

    return AssetDraft(
        asset_type=asset_type,
        name=str(name),
        content=content,
        target_path=target,
        origin="reagent-create-interactive",
    )


def _smart_default(
    field_name: str,
    asset_type: str,
    profile: RepoProfile,
) -> str:
    """Compute smart default values from repo profile.

    Args:
        field_name: Schema field name.
        asset_type: Target asset type.
        profile: Repository profile for context.

    Returns:
        Default value string, or empty string.
    """
    defaults: dict[str, str] = {
        "name": _infer_name(asset_type, profile),
        "description": f"{asset_type.title()} for {profile.repo_name}",
    }

    if field_name == "tools" and asset_type == "agent":
        return "Read, Glob, Grep"
    if field_name == "allowed-tools" and asset_type == "skill":
        return "Read, Glob, Grep"
    if field_name == "model":
        return ""

    return defaults.get(field_name, "")


def _find_matching_pattern(
    from_pattern: str | None,
    patterns_dir: Path | None,
) -> PatternTemplate | None:
    """Resolve a pattern template for asset generation.

    Args:
        asset_type: Target asset type.
        from_pattern: Explicit pattern name, or None.
        patterns_dir: Override patterns directory.

    Returns:
        Matched PatternTemplate, or None.

    Raises:
        FileNotFoundError: If *from_pattern* is specified but not found.
    """
    if not from_pattern:
        return None

    pattern = PatternTemplate.load_pattern(
        from_pattern,
        patterns_dir,
    )
    if pattern is None:
        msg = f"Pattern not found: {from_pattern}"
        raise FileNotFoundError(msg)
    return pattern


_GENERATORS: dict[str, str] = {
    "agent": "generate_agent",
    "skill": "generate_skill",
    "hook": "generate_hook",
    "command": "generate_command",
    "rule": "generate_rule",
}


def _generate_content(
    asset_type: str,
    name: str,
    profile: RepoProfile,
    pattern: PatternTemplate | None,
    repo_path: Path,
) -> str:
    """Dispatch to the correct generator for *asset_type*.

    Args:
        asset_type: Target asset type.
        name: Asset name.
        profile: Repository profile.
        pattern: Optional pattern template.
        repo_path: Repository root.

    Returns:
        Generated content string.

    Raises:
        ValueError: If *asset_type* has no generator.
    """
    import reagent.creation.generators as gen

    if asset_type in ("agent", "skill"):
        func = getattr(gen, _GENERATORS[asset_type])
        result: str = func(name, profile, pattern, repo_path)
        return result

    if asset_type in _GENERATORS:
        func = getattr(gen, _GENERATORS[asset_type])
        result = func(name, profile)
        return result

    msg = f"No generator for asset type: {asset_type}"
    raise ValueError(msg)


def _validate_generated(
    content: str,
    asset_type: str,
    name: str,
    schema_dir: Path | None,
) -> None:
    """Validate generated asset content and raise on errors.

    Args:
        content: Generated asset content.
        asset_type: Target asset type.
        name: Asset name.
        schema_dir: Override schema directory.

    Raises:
        ValueError: If validation finds errors.
    """
    if asset_type not in ("agent", "skill"):
        return

    from reagent.core.parsers import _split_frontmatter

    fm, _ = _split_frontmatter(content)
    result = validate_frontmatter(fm, asset_type, name, "", schema_dir)
    if not result.valid:
        error_msgs = "; ".join(e.message for e in result.errors)
        msg = f"Generated asset validation failed: {error_msgs}"
        raise ValueError(msg)


class GenerationMetadata:
    """Metadata from the generation process (LLM or template)."""

    def __init__(
        self,
        *,
        tier: str = "template",
        provider: str = "",
        model: str = "",
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        critic_score: int | None = None,
    ) -> None:
        self.tier = tier
        self.provider = provider
        self.model = model
        self.cost_usd = cost_usd
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.critic_score = critic_score


def _try_llm_generation(
    asset_type: str,
    name: str,
    profile: RepoProfile,
    *,
    telemetry_context: str | None = None,
    evaluation_context: str | None = None,
    instincts_context: str | None = None,
) -> tuple[str, GenerationMetadata] | None:
    """Attempt Tier 1 LLM generation.

    Returns:
        Tuple of (content, metadata) on success, None on failure.
    """
    try:
        from reagent.config import ReagentConfig
        from reagent.core.parsers import AssetType as CoreAssetType
        from reagent.llm.parser import ParseError
        from reagent.llm.providers import LLMProviderError, create_provider
        from reagent.llm.quality import generate_with_quality

        config = ReagentConfig.load()
        llm_config = config.llm
        llm_config.apply_env_overrides()

        if not llm_config.features.enabled:
            return None

        provider = create_provider(llm_config.provider, llm_config.model)
        if not provider.available:
            return None

        # Map string asset_type to AssetType enum
        type_map: dict[str, CoreAssetType] = {
            "agent": CoreAssetType.AGENT,
            "skill": CoreAssetType.SKILL,
            "hook": CoreAssetType.HOOK,
            "command": CoreAssetType.COMMAND,
            "rule": CoreAssetType.RULE,
        }
        at = type_map.get(asset_type)
        if at is None:
            return None

        # Build combined prompt context
        combined_telemetry = telemetry_context or ""
        if instincts_context:
            combined_telemetry = (
                f"{combined_telemetry}\n{instincts_context}"
                if combined_telemetry
                else instincts_context
            )

        # Run async pipeline in sync context
        result = asyncio.run(
            generate_with_quality(
                at,
                name,
                profile,
                provider,
                llm_config,
                evaluation_context=evaluation_context,
                telemetry_context=(combined_telemetry or None),
            )
        )

        if not result.quality.passed:
            logger.warning(
                "LLM quality gate failed: %s",
                "; ".join(result.quality.errors),
            )
            return None

        # Convert GeneratedAsset back to text
        from reagent.llm.quality import _asset_to_text

        content = _asset_to_text(result.asset)
        metadata = GenerationMetadata(
            tier="llm",
            provider=result.response.provider,
            model=result.response.model,
            cost_usd=result.total_cost_usd,
            input_tokens=result.total_input_tokens,
            output_tokens=result.total_output_tokens,
            latency_ms=result.response.latency_ms,
            critic_score=(result.critic.score if result.critic else None),
        )
        return content, metadata

    except (LLMProviderError, ParseError, ImportError) as exc:
        logger.info("LLM generation failed, falling back: %s", exc)
        return None
    except (OSError, ValueError, KeyError, RuntimeError):
        logger.exception("Unexpected LLM error, falling back to templates")
        return None


def _load_telemetry_context(
    asset_type: str,
    name: str,
    repo_path: Path,
) -> tuple[str | None, str | None]:
    """Load telemetry and instinct context for prompt injection.

    Args:
        asset_type: Target asset type string.
        name: Asset name.
        repo_path: Repository root path.

    Returns:
        Tuple of (telemetry_context, instincts_context) strings.
    """
    telemetry_ctx: str | None = None
    instincts_ctx: str | None = None
    try:
        from reagent.config import ReagentConfig
        from reagent.core.parsers import AssetType as CoreAssetType
        from reagent.llm.instincts import (
            InstinctStore,
            build_telemetry_context,
            ensure_bundled,
            format_instincts_for_prompt,
        )
        from reagent.telemetry.profiler import profile_repo

        wp = profile_repo(repo_path)
        tc = build_telemetry_context(wp)
        if tc:
            telemetry_ctx = tc.to_prompt_section()

        config = ReagentConfig.load()
        store_path = config.catalog.path.parent / "instincts.json"
        store = InstinctStore(store_path)
        store.load()
        ensure_bundled(store)

        type_map: dict[str, CoreAssetType] = {
            "agent": CoreAssetType.AGENT,
            "skill": CoreAssetType.SKILL,
            "hook": CoreAssetType.HOOK,
            "command": CoreAssetType.COMMAND,
            "rule": CoreAssetType.RULE,
        }
        at = type_map.get(asset_type)
        if at is not None:
            relevant = store.get_relevant(at, name)
            instincts_ctx = format_instincts_for_prompt(relevant)
    except (OSError, ValueError):
        logger.debug(
            "Telemetry/instinct context unavailable",
            exc_info=True,
        )
    return telemetry_ctx, instincts_ctx


def create_asset(
    asset_type: str,
    repo_path: Path,
    name: str | None = None,
    from_pattern: str | None = None,
    from_outline: str | None = None,
    interactive: bool = False,
    profile: RepoProfile | None = None,
    patterns_dir: Path | None = None,
    schema_dir: Path | None = None,
    no_llm: bool = False,
    use_telemetry: bool = False,
) -> AssetDraft:
    """Create a new asset with repo-aware generation.

    Tries LLM generation (Tier 1) first, falling back to enhanced
    templates (Tier 2) on failure or when ``no_llm=True``.

    Args:
        asset_type: One of "agent", "skill", "hook", "command", "rule".
        repo_path: Repository root path.
        name: Optional asset name.
        from_pattern: Optional pattern name to use as base.
        from_outline: Optional outline text or file path.
        interactive: Whether to use interactive mode.
        profile: Optional pre-computed repo profile.
        patterns_dir: Override patterns directory.
        schema_dir: Override schema directory.
        no_llm: If True, skip LLM and use templates directly.
        use_telemetry: If True, load telemetry and instincts.

    Returns:
        AssetDraft ready for review and installation.
    """
    if asset_type not in VALID_ASSET_TYPES:
        msg = f"Invalid asset type: {asset_type}. Must be one of {VALID_ASSET_TYPES}"
        raise ValueError(msg)

    logger.info(
        "create_asset: type=%s, repo=%s, name=%s, pattern=%s",
        asset_type,
        repo_path,
        name,
        from_pattern,
    )

    if profile is None:
        profile = analyze_repo(repo_path)

    if from_outline:
        return create_from_outline(
            from_outline,
            asset_type,
            repo_path,
            name,
            profile,
        )

    if interactive:
        return create_interactive(
            asset_type,
            repo_path,
            profile,
            schema_dir,
        )

    pattern = _find_matching_pattern(
        from_pattern,
        patterns_dir,
    )

    if not name:
        name = _infer_name(asset_type, profile)

    # Tier 1: Try LLM generation (unless explicitly disabled)
    metadata: GenerationMetadata | None = None
    content: str | None = None

    # Build telemetry/instinct context when requested
    telemetry_ctx: str | None = None
    instincts_ctx: str | None = None
    if use_telemetry and not no_llm:
        telemetry_ctx, instincts_ctx = _load_telemetry_context(
            asset_type, name, repo_path
        )

    if not no_llm and not from_pattern:
        llm_result = _try_llm_generation(
            asset_type,
            name,
            profile,
            telemetry_context=telemetry_ctx,
            instincts_context=instincts_ctx,
        )
        if llm_result is not None:
            content, metadata = llm_result
            logger.info(
                "LLM generated %s/%s via %s ($%.4f)",
                asset_type,
                name,
                metadata.provider,
                metadata.cost_usd,
            )

    # Tier 2: Enhanced templates
    if content is None:
        content = _generate_content(
            asset_type,
            name,
            profile,
            pattern,
            repo_path,
        )
        metadata = GenerationMetadata(tier="template")

    _validate_generated(content, asset_type, name, schema_dir)

    target = _target_path(asset_type, name, repo_path)

    draft = AssetDraft(
        asset_type=asset_type,
        name=name,
        content=content,
        target_path=target,
        origin=f"reagent-create-{metadata.tier}" if metadata else "reagent-create",
    )
    draft.generation_metadata = metadata  # type: ignore[attr-defined]
    return draft


def regenerate_asset(
    asset_path: Path,
    repo_path: Path,
) -> AssetDraft:
    """Regenerate an existing asset using evaluation feedback.

    Loads the existing asset, evaluates it, loads relevant instincts,
    and generates an improved version via LLM.

    Args:
        asset_path: Path to the existing asset file.
        repo_path: Repository root path.

    Returns:
        AssetDraft with the regenerated content.

    Raises:
        FileNotFoundError: If asset_path does not exist.
        ValueError: If asset cannot be parsed.
    """
    if not asset_path.exists():
        msg = f"Asset not found: {asset_path}"
        raise FileNotFoundError(msg)

    existing_content = asset_path.read_text(encoding="utf-8")

    # Parse to determine asset type and name
    from reagent.core.parsers import _split_frontmatter

    fm, _ = _split_frontmatter(existing_content)
    name = fm.get("name", asset_path.stem)
    asset_type = _infer_asset_type_from_path(asset_path)

    # Build evaluation context
    eval_ctx = _build_evaluation_context(asset_path, repo_path, name)

    # Load telemetry + instinct context
    telemetry_ctx, instincts_ctx = _load_telemetry_context(
        asset_type, str(name), repo_path
    )

    # Combine evaluation with existing content summary
    full_eval_ctx = f"Existing asset content:\n{existing_content[:500]}\n\n"
    if eval_ctx:
        full_eval_ctx += eval_ctx

    profile = analyze_repo(repo_path)

    # Try LLM with all context
    llm_result = _try_llm_generation(
        asset_type,
        str(name),
        profile,
        telemetry_context=telemetry_ctx,
        evaluation_context=full_eval_ctx,
        instincts_context=instincts_ctx,
    )

    if llm_result is not None:
        content, metadata = llm_result
    else:
        # Fallback: return original with a note
        content = existing_content
        metadata = GenerationMetadata(tier="template")

    target = asset_path
    draft = AssetDraft(
        asset_type=asset_type,
        name=str(name),
        content=content,
        target_path=target,
        origin="reagent-regenerate",
    )
    draft.generation_metadata = metadata  # type: ignore[attr-defined]
    return draft


def _infer_asset_type_from_path(path: Path) -> str:
    """Infer asset type from file path conventions.

    Args:
        path: Path to the asset file.

    Returns:
        Asset type string.
    """
    parts = path.parts
    if "agents" in parts:
        return "agent"
    if "skills" in parts or path.name == "SKILL.md":
        return "skill"
    if "commands" in parts:
        return "command"
    if "rules" in parts:
        return "rule"
    if path.name == "hooks.json":
        return "hook"
    return "rule"


def _build_evaluation_context(
    _asset_path: Path,
    repo_path: Path,
    name: str,
) -> str | None:
    """Build evaluation context string for regeneration.

    Args:
        _asset_path: Path to the asset (reserved for future use).
        repo_path: Repository root.
        name: Asset name.

    Returns:
        Evaluation summary string, or None.
    """
    try:
        from reagent.config import ReagentConfig
        from reagent.evaluation.evaluator import evaluate_repo

        config = ReagentConfig.load()
        from reagent.core.catalog import Catalog

        catalog = Catalog(config.catalog.path)
        catalog.load()
        report = evaluate_repo(repo_path, config, catalog)

        for m in report.asset_metrics:
            if m.name == name:
                return (
                    f"Quality score: {m.quality_score:.0f}/100\n"
                    f"Label: {m.label.value}\n"
                    f"Invocation rate: {m.invocation_rate:.1f}/week\n"
                    f"Correction rate: {m.correction_rate:.0%}\n"
                    f"Staleness: {m.staleness_days:.0f} days"
                )
    except (OSError, ValueError):
        logger.debug("Evaluation context unavailable", exc_info=True)
    return None


def generate_init_assets(
    repo_path: Path,
    profile: RepoProfile | None = None,
) -> list[AssetDraft]:
    """Generate smart default assets for a repository.

    Based on repo analysis, produces a starter asset set.

    Args:
        repo_path: Repository root path.
        profile: Optional pre-computed repo profile.

    Returns:
        List of AssetDraft objects for review.
    """
    if profile is None:
        profile = analyze_repo(repo_path)

    logger.info(
        "generate_init_assets: repo=%s, lang=%s, has_ci=%s, has_docker=%s",
        profile.repo_name,
        profile.primary_language,
        profile.has_ci,
        profile.has_docker,
    )

    drafts: list[AssetDraft] = []

    # Always generate a CLAUDE.md if missing
    if not profile.asset_audit.has_claude_md:
        drafts.append(
            AssetDraft(
                asset_type="claude_md",
                name="CLAUDE.md",
                content=generate_claude_md(profile),
                target_path=repo_path / "CLAUDE.md",
            )
        )

    # Settings with permissions
    if not profile.asset_audit.has_settings:
        drafts.append(
            AssetDraft(
                asset_type="settings",
                name="settings.json",
                content=generate_settings(profile),
                target_path=repo_path / ".claude" / "settings.json",
            )
        )

    # Test hook if test runner detected
    if profile.test_config.command:
        drafts.append(
            AssetDraft(
                asset_type="hook",
                name="test-on-edit",
                content=generate_hook("test-on-edit", profile),
                target_path=repo_path / ".claude" / "hooks.json",
            )
        )

    # CI check skill if CI detected
    if profile.has_ci:
        drafts.append(
            create_asset(
                "skill",
                repo_path,
                name="ci-check",
                profile=profile,
            )
        )

    # API conventions rule if API detected
    if profile.has_api_routes:
        drafts.append(
            create_asset(
                "rule",
                repo_path,
                name="api-conventions",
                profile=profile,
            )
        )

    # Docker agent if Docker detected
    if profile.has_docker:
        drafts.append(
            create_asset(
                "agent",
                repo_path,
                name="devops",
                profile=profile,
            )
        )

    return drafts
