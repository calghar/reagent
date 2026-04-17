import logging
from collections.abc import Sequence

from agentguard.intelligence.analyzer import RepoProfile
from agentguard.llm.parser import GeneratedAsset

logger = logging.getLogger(__name__)


def _section_project_context(profile: RepoProfile) -> str:
    """Render the Project Context section.

    Args:
        profile: Repository profile.

    Returns:
        Markdown section string.
    """
    name = getattr(profile, "repo_name", "") or "this project"
    language = getattr(profile, "primary_language", "") or ""
    description_parts: list[str] = [f"**Project:** {name}"]
    if language:
        description_parts.append(f"**Primary language:** {language}")

    extra_langs = getattr(profile, "languages", [])
    if extra_langs and len(extra_langs) > 1:
        description_parts.append(f"**Languages:** {', '.join(extra_langs)}")

    return "\n".join(description_parts)


def _section_architecture(profile: RepoProfile) -> str:
    """Render the Architecture Overview section.

    Args:
        profile: Repository profile.

    Returns:
        Markdown section string.
    """
    lines: list[str] = []
    language = getattr(profile, "primary_language", "")
    if language:
        lines.append(f"**Language:** {language}")

    frameworks = getattr(profile, "frameworks", [])
    if frameworks:
        lines.append(f"**Frameworks:** {', '.join(frameworks)}")

    architecture = getattr(profile, "architecture", "")
    if architecture:
        lines.append(f"**Architecture:** {architecture}")

    build_system = getattr(profile, "build_system", "")
    if build_system:
        lines.append(f"**Build system:** {build_system}")

    package_manager = getattr(profile, "package_manager", "")
    if package_manager:
        lines.append(f"**Package manager:** {package_manager}")

    return "\n".join(lines) if lines else "_No architecture details detected._"


def _section_conventions(profile: RepoProfile) -> str:
    """Render the Conventions section.

    Args:
        profile: Repository profile.

    Returns:
        Markdown section string.
    """
    lines: list[str] = []

    conventions = getattr(profile, "conventions", {})
    if conventions:
        for key, value in conventions.items():
            lines.append(f"- **{key}:** {value}")

    test_config = getattr(profile, "test_config", None)
    if test_config:
        command = getattr(test_config, "command", "")
        if command:
            lines.append(f"- **Test command:** `{command}`")

    lint_configs = getattr(profile, "lint_configs", [])
    for lc in lint_configs:
        tool = getattr(lc, "tool", "")
        command = getattr(lc, "command", "")
        if tool and command:
            lines.append(f"- **Lint ({tool}):** `{command}`")
        elif tool:
            lines.append(f"- **Linter:** {tool}")

    return "\n".join(lines) if lines else "_No conventions detected._"


def _render_agent_entry(asset: GeneratedAsset) -> str:
    """Render a single agent as a markdown subsection.

    Args:
        asset: An AGENT-type GeneratedAsset.

    Returns:
        Markdown string for one agent.
    """
    name = str(asset.frontmatter.get("name", "unnamed"))
    description = str(asset.frontmatter.get("description", "")).strip()
    raw_tools = asset.frontmatter.get("tools", [])
    tools: list[str] = (
        [str(t) for t in raw_tools] if isinstance(raw_tools, list) else []
    )

    lines = [f"### {name}"]
    if description:
        lines.append(f"\n{description}")
    if tools:
        lines.append(f"\n**Tools:** {', '.join(f'`{t}`' for t in tools)}")
    if asset.body.strip():
        lines.append(f"\n{asset.body.strip()}")
    return "\n".join(lines)


def _render_skill_entry(asset: GeneratedAsset) -> str:
    """Render a single skill as a bullet list entry.

    Args:
        asset: A SKILL-type GeneratedAsset.

    Returns:
        Markdown bullet string for one skill.
    """
    name = str(asset.frontmatter.get("name", "unnamed"))
    description = str(asset.frontmatter.get("description", "")).strip()
    if description:
        return f"- **{name}**: {description}"
    return f"- **{name}**"


def _render_rule_entry(asset: GeneratedAsset) -> str:
    """Render a single rule inline.

    Args:
        asset: A RULE-type GeneratedAsset.

    Returns:
        Markdown string for one rule (body only).
    """
    name = str(asset.frontmatter.get("name", "")) or str(
        asset.frontmatter.get("description", "rule")
    )
    body = asset.body.strip()
    if not body:
        return f"_Rule `{name}` has no body._"
    return f"### {name}\n\n{body}"


def generate_agents_md(
    agents: Sequence[GeneratedAsset],
    skills: Sequence[GeneratedAsset],
    rules: Sequence[GeneratedAsset],
    profile: RepoProfile,
) -> str:
    """Generate a universal AGENTS.md from profiled repo data and assets.

    The output is a comprehensive, human-readable markdown file understood by
    all four supported harnesses (Claude Code, Cursor, Codex, OpenCode).

    Args:
        agents: List of generated AGENT assets.
        skills: List of generated SKILL assets.
        rules: List of generated RULE assets.
        profile: Repository profile from the intelligence analyser.

    Returns:
        Markdown string ready to write to ``AGENTS.md`` at the repo root.
    """
    sections: list[str] = ["# Agent Instructions"]

    # Project Context
    project_ctx = _section_project_context(profile)
    sections.append(f"## Project Context\n\n{project_ctx}")

    # Architecture Overview
    arch = _section_architecture(profile)
    sections.append(f"## Architecture Overview\n\n{arch}")

    # Conventions
    conv = _section_conventions(profile)
    sections.append(f"## Conventions\n\n{conv}")

    # Agents
    if agents:
        agent_entries = "\n\n".join(_render_agent_entry(a) for a in agents)
        sections.append(f"## Agents\n\n{agent_entries}")
    else:
        sections.append("## Agents\n\n_No agents defined._")

    # Skills
    if skills:
        skill_entries = "\n".join(_render_skill_entry(s) for s in skills)
        sections.append(f"## Skills\n\n{skill_entries}")
    else:
        sections.append("## Skills\n\n_No skills defined._")

    # Workflows (placeholder — populated from telemetry in future phases)
    sections.append(
        "## Workflows\n\n_Workflow chains will be populated automatically as "
        "agentguard observes development patterns._"
    )

    # Rules
    if rules:
        rule_entries = "\n\n".join(_render_rule_entry(r) for r in rules)
        sections.append(f"## Rules\n\n{rule_entries}")
    else:
        sections.append("## Rules\n\n_No rules defined._")

    return "\n\n".join(sections) + "\n"


__all__ = ["generate_agents_md"]
