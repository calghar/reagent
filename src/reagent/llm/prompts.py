import logging
from enum import StrEnum

from pydantic import BaseModel

from reagent.core.parsers import AssetType
from reagent.intelligence.analyzer import RepoProfile
from reagent.llm.prompt_loader import render_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS: dict[AssetType, str] = {
    AssetType.AGENT: render_prompt("agent_system.j2"),
    AssetType.SKILL: render_prompt("skill_system.j2"),
    AssetType.HOOK: render_prompt("hook_system.j2"),
    AssetType.COMMAND: render_prompt("command_system.j2"),
    AssetType.RULE: render_prompt("rule_system.j2"),
    AssetType.CLAUDE_MD: render_prompt("claude_md_system.j2"),
}

CRITIC_SYSTEM: str = render_prompt("critic_system.j2")


def _format_profile_core(profile: RepoProfile) -> list[str]:
    """Format core profile fields (language, framework, build)."""
    lines: list[str] = []
    if profile.languages:
        lines.append(f"- All languages: {', '.join(profile.languages)}")
    if profile.frameworks:
        lines.append(f"- Frameworks: {', '.join(profile.frameworks)}")
    if profile.package_manager:
        lines.append(f"- Package manager: {profile.package_manager}")
    if profile.build_system:
        lines.append(f"- Build system: {profile.build_system}")
    if profile.architecture:
        lines.append(f"- Architecture: {profile.architecture}")
    return lines


def _format_profile_tooling(profile: RepoProfile) -> list[str]:
    """Format tooling fields (test, lint, CI, entry points)."""
    lines: list[str] = []
    if profile.test_config.command:
        lines.append(f"- Test command: `{profile.test_config.command}`")
    if profile.test_config.test_dir:
        lines.append(f"- Test directory: {profile.test_config.test_dir}")
    for lc in profile.lint_configs:
        lines.append(f"- Lint: `{lc.command}` ({lc.tool})")
    if profile.ci_system:
        lines.append(f"- CI: {profile.ci_system}")
    if profile.entry_points:
        lines.append(f"- Entry points: {', '.join(profile.entry_points[:5])}")
    return lines


def _format_profile_metadata(profile: RepoProfile) -> list[str]:
    """Format metadata fields (conventions, docker, env, API, monorepo)."""
    lines: list[str] = []
    for key, value in profile.conventions.items():
        lines.append(f"- Convention ({key}): {value}")
    if profile.has_docker:
        lines.append("- Docker: yes")
    if profile.has_env_file:
        lines.append("- Environment files: yes")
    if profile.has_api_routes:
        lines.append("- API routes: yes")
    if profile.is_monorepo:
        lines.append(f"- Monorepo workspaces: {', '.join(profile.workspaces)}")
    return lines


def _format_profile_section(profile: RepoProfile) -> str:
    """Format the full repo profile as a prompt section."""
    lines = [
        "## Repository Profile",
        f"- Name: {profile.repo_name}",
        f"- Language: {profile.primary_language or 'unknown'}",
    ]
    lines.extend(_format_profile_core(profile))
    lines.extend(_format_profile_tooling(profile))
    lines.extend(_format_profile_metadata(profile))
    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


class PromptBudget(BaseModel):
    """Token budget allocation for prompt construction."""

    total: int = 2000
    core_profile: int = 200
    conventions: int = 300
    lint_configs: int = 150
    evaluation: int = 200
    instincts: int = 500
    examples: int = 600
    reserve: int = 50


class ProfileTier(StrEnum):
    """Profile compression tier."""

    CORE = "core"  # ~100 tokens
    STANDARD = "standard"  # ~200 tokens
    FULL = "full"  # ~400 tokens


def select_profile_tier(
    asset_type: AssetType,
    budget: PromptBudget,
    used_tokens: int = 0,
) -> ProfileTier:
    """Select the profile compression tier for the given asset type.

    CLAUDE.md always gets Tier 3 (full). For other types the tier is
    chosen based on the remaining budget.
    """
    if asset_type == AssetType.CLAUDE_MD:
        return ProfileTier.FULL

    remaining = budget.total - used_tokens - budget.reserve

    # Hooks and commands only need core profile
    if asset_type in (AssetType.HOOK, AssetType.COMMAND):
        return ProfileTier.CORE

    # Agents, skills, rules get standard or full based on budget
    if remaining >= budget.core_profile + budget.conventions:
        return ProfileTier.STANDARD

    return ProfileTier.CORE


def _format_profile_tiered(
    profile: RepoProfile,
    tier: ProfileTier,
) -> str:
    """Format the repo profile at the requested compression tier."""
    lines = [
        "## Repository Profile",
        f"- Name: {profile.repo_name}",
        f"- Language: {profile.primary_language or 'unknown'}",
    ]

    # Tier 1: core (~100 tokens)
    lines.extend(_format_profile_core(profile))
    lines.extend(_format_profile_tooling(profile))

    if tier == ProfileTier.CORE:
        return "\n".join(lines)

    # Tier 2: standard (~200 tokens) - add conventions and entry points
    conventions = profile.conventions
    if conventions:
        for key, value in list(conventions.items())[:5]:
            lines.append(f"- Convention ({key}): {value}")
    if profile.entry_points:
        lines.append(f"- Entry points: {', '.join(profile.entry_points[:3])}")

    if tier == ProfileTier.STANDARD:
        return "\n".join(lines)

    # Tier 3: full (~400 tokens) - add metadata, deps, all conventions
    lines.extend(_format_profile_metadata(profile))
    return "\n".join(lines)


def build_generation_prompt(
    asset_type: AssetType,
    name: str,
    profile: RepoProfile,
    *,
    evaluation_context: str | None = None,
    telemetry_context: str | None = None,
    max_prompt_tokens: int = 2000,
    budget: PromptBudget | None = None,
) -> str:
    """Build the user prompt for LLM asset generation.

    Uses budget-aware profile compression: selects the appropriate
    tier based on asset type and remaining token budget.

    Args:
        asset_type: Target asset type.
        name: Asset name.
        profile: Repository profile with full context.
        evaluation_context: Optional summary from previous evaluations.
        telemetry_context: Optional summary from telemetry data.
        max_prompt_tokens: Token budget for the prompt.
        budget: Optional explicit PromptBudget allocation.

    Returns:
        Assembled prompt string.
    """
    if budget is None:
        budget = PromptBudget(total=max_prompt_tokens)

    header = (
        f'Generate a Claude Code {asset_type.value} named "{name}" '
        f"for the following repository:"
    )

    # Select profile tier based on asset type and budget
    header_tokens = _estimate_tokens(header)
    tier = select_profile_tier(asset_type, budget, header_tokens)
    profile_section = _format_profile_tiered(profile, tier)

    # Determine which optional sections fit within budget
    base_tokens = _estimate_tokens(header) + _estimate_tokens(profile_section)
    eval_ctx: str | None = None
    if evaluation_context and (
        base_tokens + _estimate_tokens(evaluation_context) < budget.total
    ):
        eval_ctx = evaluation_context
        base_tokens += _estimate_tokens(evaluation_context)

    telemetry_ctx: str | None = None
    if telemetry_context and (
        base_tokens + _estimate_tokens(telemetry_context) < budget.total
    ):
        telemetry_ctx = telemetry_context

    return render_prompt(
        "generation_user.j2",
        asset_type_value=asset_type.value,
        name=name,
        profile_section=profile_section,
        evaluation_context=eval_ctx,
        telemetry_context=telemetry_ctx,
    )


def build_critic_prompt(asset_content: str, asset_type: AssetType) -> str:
    """Build the user prompt for the critic pass.

    Args:
        asset_content: The generated asset to critique.
        asset_type: The asset type being critiqued.

    Returns:
        Critic prompt string.
    """
    return render_prompt(
        "critic.j2",
        asset_type_value=asset_type.value,
        asset_content=asset_content,
    )


def build_revision_prompt(
    original_prompt: str,
    asset_content: str,
    critic_score: int,
    critic_issues: list[str],
    critic_suggestions: list[str],
) -> str:
    """Build the revision prompt incorporating critic feedback.

    Args:
        original_prompt: The original generation prompt.
        asset_content: The generated asset that was critiqued.
        critic_score: Score from the critic (1-10).
        critic_issues: List of issues found.
        critic_suggestions: List of improvement suggestions.

    Returns:
        Revision prompt string.
    """
    return render_prompt(
        "revision.j2",
        original_prompt=original_prompt,
        asset_content=asset_content,
        critic_score=critic_score,
        issues=critic_issues,
        suggestions=critic_suggestions,
    )
