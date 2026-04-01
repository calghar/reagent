import json
import logging

import yaml

from reagent.core.parsers import AssetType
from reagent.harness import HarnessFile
from reagent.llm.parser import GeneratedAsset

logger = logging.getLogger(__name__)


def _asset_name(asset: GeneratedAsset) -> str:
    """Extract the asset name from frontmatter, falling back to 'unnamed'.

    Args:
        asset: The generated asset.

    Returns:
        Name string suitable for use in file paths.
    """
    name = asset.frontmatter.get("name", "")
    return str(name).strip() or "unnamed"


def _render_asset(asset: GeneratedAsset) -> str:
    """Re-serialise a :class:`GeneratedAsset` as ``---\\nYAML\\n---\\nbody``.

    Assets with no frontmatter keys are rendered body-only.

    Args:
        asset: The asset to render.

    Returns:
        Markdown string with YAML frontmatter block (if any) plus body.
    """
    if not asset.frontmatter:
        return asset.body

    fm_text = yaml.dump(
        asset.frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()
    return f"---\n{fm_text}\n---\n{asset.body}"


def _to_toml_agent(asset: GeneratedAsset) -> str:
    """Render a GeneratedAsset as a minimal Codex TOML agent definition.

    Args:
        asset: An AGENT-type GeneratedAsset.

    Returns:
        TOML-formatted string for ``.codex/agents/<name>.toml``.
    """
    name = _asset_name(asset)
    description = str(asset.frontmatter.get("description", "")).strip()
    raw_tools = asset.frontmatter.get("tools", [])
    tools: list[str] = (
        [str(t) for t in raw_tools] if isinstance(raw_tools, list) else []
    )
    tools_inline = ", ".join(f'"{t}"' for t in tools)
    lines = [
        "[agent]",
        f'name = "{name}"',
        f'description = "{description}"',
        f"tools = [{tools_inline}]",
    ]

    # Carry forward optional fields that Codex understands
    if "model" in asset.frontmatter:
        lines.append(f'model = "{asset.frontmatter["model"]}"')

    if asset.body.strip():
        # Embed the instructions as a multi-line TOML string
        body_escaped = asset.body.strip().replace('"""', "'''")
        lines.append(f'\ninstructions = """\n{body_escaped}\n"""')

    return "\n".join(lines) + "\n"


def _cursor_rule_frontmatter(fm: dict[str, object]) -> dict[str, object]:
    """Add Cursor-specific rule frontmatter keys if not already present.

    Cursor expects ``alwaysApply`` (bool) and ``globs`` (list) in rule
    frontmatter.  Existing values are preserved.

    Args:
        fm: Original frontmatter dict.

    Returns:
        New dict with Cursor keys merged in.
    """
    updated = dict(fm)
    if "alwaysApply" not in updated:
        updated["alwaysApply"] = False
    if "globs" not in updated:
        updated["globs"] = []
    return updated


def _hook_to_cursor_json(asset: GeneratedAsset) -> str:
    """Convert a hook asset body to Cursor hook JSON format.

    Cursor hooks use the same event names as Claude Code but wrap them in a
    slightly different structure.  We do a best-effort conversion: if the body
    is already valid JSON we merge it; otherwise we emit an empty hooks object.

    Args:
        asset: A HOOK-type GeneratedAsset whose body contains JSON.

    Returns:
        JSON string suitable for ``.cursor/hooks/hooks.json``.
    """
    try:
        data: dict[str, object] = json.loads(asset.body)
    except ValueError:
        logger.warning("Hook body is not valid JSON; emitting empty cursor hooks")
        data = {}

    # Normalise: Claude Code may use a top-level "hooks" key
    hooks_payload = data.get("hooks", data)
    return json.dumps({"hooks": hooks_payload}, indent=2)


def _hook_to_opencode_json(asset: GeneratedAsset) -> str:
    """Convert a hook asset body to OpenCode plugin format JSON.

    OpenCode stores plugins under ``opencode.json`` at the repo root.

    Args:
        asset: A HOOK-type GeneratedAsset whose body contains JSON.

    Returns:
        JSON string suitable for ``opencode.json``.
    """
    try:
        data: dict[str, object] = json.loads(asset.body)
    except ValueError:
        logger.warning("Hook body is not valid JSON; emitting empty opencode plugins")
        data = {}

    hooks_payload = data.get("hooks", data)
    return json.dumps({"plugins": hooks_payload}, indent=2)


def _cursor_project_rule(body: str) -> str:
    """Wrap CLAUDE.md body as a Cursor rule markdown file.

    Args:
        body: The raw body text from the CLAUDE.md asset.

    Returns:
        Cursor rule markdown with required frontmatter.
    """
    fm = {
        "description": "Project context",
        "alwaysApply": True,
        "globs": [],
    }
    fm_text = yaml.dump(fm, default_flow_style=False, sort_keys=False).rstrip()
    return f"---\n{fm_text}\n---\n{body}"


def _agents_md_section(name: str, body: str) -> str:
    """Format a body as a named markdown section for AGENTS.md.

    Args:
        name: Section heading name.
        body: Section content.

    Returns:
        Markdown section string (starts with ``## {name}``).
    """
    return f"\n## {name}\n\n{body.strip()}\n"


def adapt_to_cursor(asset: GeneratedAsset) -> list[HarnessFile]:
    """Translate a Claude Code asset to Cursor harness format.

    Mapping:
    - AGENT   → ``.cursor/agents/<name>.md`` (same frontmatter/body)
    - SKILL   → ``.cursor/skills/<name>/SKILL.md`` (shared SKILL.md format)
    - RULE    → ``.cursor/rules/<name>.md`` (adds Cursor frontmatter keys)
    - HOOK    → ``.cursor/hooks/hooks.json`` (mode=merge_json)
    - CLAUDE_MD → ``.cursor/rules/project-context.md``
    - COMMAND → ``.cursor/commands/<name>.md``

    Args:
        asset: The GeneratedAsset in canonical Claude Code format.

    Returns:
        List of :class:`~reagent.harness.HarnessFile` instances.
    """
    name = _asset_name(asset)

    match asset.asset_type:
        case AssetType.AGENT:
            return [
                HarnessFile(
                    path=f".cursor/agents/{name}.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.SKILL:
            return [
                HarnessFile(
                    path=f".cursor/skills/{name}/SKILL.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.RULE:
            updated_fm = _cursor_rule_frontmatter(asset.frontmatter)
            updated_asset = asset.model_copy(update={"frontmatter": updated_fm})
            return [
                HarnessFile(
                    path=f".cursor/rules/{name}.md",
                    content=_render_asset(updated_asset),
                )
            ]

        case AssetType.HOOK:
            return [
                HarnessFile(
                    path=".cursor/hooks/hooks.json",
                    content=_hook_to_cursor_json(asset),
                    mode="merge_json",
                )
            ]

        case AssetType.CLAUDE_MD:
            return [
                HarnessFile(
                    path=".cursor/rules/project-context.md",
                    content=_cursor_project_rule(asset.body),
                )
            ]

        case AssetType.COMMAND:
            return [
                HarnessFile(
                    path=f".cursor/commands/{name}.md",
                    content=_render_asset(asset),
                )
            ]

        case _:
            logger.debug("No Cursor mapping for asset type %s", asset.asset_type)
            return []


def adapt_to_codex(asset: GeneratedAsset) -> list[HarnessFile]:
    """Translate a Claude Code asset to Codex harness format.

    Mapping:
    - AGENT   → ``.codex/agents/<name>.toml``
    - SKILL   → ``.agents/skills/<name>/SKILL.md``
    - RULE    → ``AGENTS.md`` (mode=append_section)
    - HOOK    → skipped (Codex is sandbox-based; no hook support)
    - CLAUDE_MD → ``AGENTS.md`` (mode=append_section)

    Args:
        asset: The GeneratedAsset in canonical Claude Code format.

    Returns:
        List of :class:`~reagent.harness.HarnessFile` instances.
    """
    name = _asset_name(asset)

    match asset.asset_type:
        case AssetType.AGENT:
            return [
                HarnessFile(
                    path=f".codex/agents/{name}.toml",
                    content=_to_toml_agent(asset),
                )
            ]

        case AssetType.SKILL:
            return [
                HarnessFile(
                    path=f".agents/skills/{name}/SKILL.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.RULE:
            return [
                HarnessFile(
                    path="AGENTS.md",
                    content=_agents_md_section(name, asset.body),
                    mode="append_section",
                )
            ]

        case AssetType.HOOK:
            logger.debug("Codex has no hook support; skipping hook asset %s", name)
            return []

        case AssetType.CLAUDE_MD:
            return [
                HarnessFile(
                    path="AGENTS.md",
                    content=_agents_md_section("Project Context", asset.body),
                    mode="append_section",
                )
            ]

        case _:
            logger.debug("No Codex mapping for asset type %s", asset.asset_type)
            return []


def adapt_to_opencode(asset: GeneratedAsset) -> list[HarnessFile]:
    """Translate a Claude Code asset to OpenCode harness format.

    Mapping:
    - AGENT   → ``.opencode/agents/<name>.md``
    - SKILL   → ``.opencode/skills/<name>/SKILL.md``
    - RULE    → ``.opencode/instructions/<name>.md``
    - HOOK    → ``opencode.json`` (mode=merge_json)
    - CLAUDE_MD → ``.opencode/instructions/project-context.md``

    Args:
        asset: The GeneratedAsset in canonical Claude Code format.

    Returns:
        List of :class:`~reagent.harness.HarnessFile` instances.
    """
    name = _asset_name(asset)

    match asset.asset_type:
        case AssetType.AGENT:
            return [
                HarnessFile(
                    path=f".opencode/agents/{name}.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.SKILL:
            return [
                HarnessFile(
                    path=f".opencode/skills/{name}/SKILL.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.RULE:
            return [
                HarnessFile(
                    path=f".opencode/instructions/{name}.md",
                    content=_render_asset(asset),
                )
            ]

        case AssetType.HOOK:
            return [
                HarnessFile(
                    path="opencode.json",
                    content=_hook_to_opencode_json(asset),
                    mode="merge_json",
                )
            ]

        case AssetType.CLAUDE_MD:
            return [
                HarnessFile(
                    path=".opencode/instructions/project-context.md",
                    content=_render_asset(asset),
                )
            ]

        case _:
            logger.debug("No OpenCode mapping for asset type %s", asset.asset_type)
            return []
