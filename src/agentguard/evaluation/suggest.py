import logging
from pathlib import Path

from pydantic import BaseModel, Field

from agentguard.core.catalog import Catalog
from agentguard.telemetry.profiler import WorkflowProfile, profile_repo

logger = logging.getLogger(__name__)


class Suggestion(BaseModel):
    """A single actionable recommendation."""

    number: int
    category: str  # high-correction, uncovered-workflow, stale-asset, missing-hook
    title: str
    description: str
    severity: str = "info"  # info, warning, critical
    draft_content: str = ""
    target_path: str = ""
    asset_type: str = ""  # agent, skill, rule, hook, command
    estimated_quality: str = ""  # estimated quality label


class SuggestionReport(BaseModel):
    """Full suggestion report for a repository."""

    repo_path: str
    repo_name: str
    suggestions: list[Suggestion] = Field(default_factory=list)

    def get_suggestion(self, number: int) -> Suggestion | None:
        """Get a suggestion by its number.

        Args:
            number: The suggestion number to look up.

        Returns:
            Matching Suggestion, or None if not found.
        """
        for s in self.suggestions:
            if s.number == number:
                return s
        return None


def _suggest_high_corrections(
    profile: WorkflowProfile,
    suggestions: list[Suggestion],
) -> None:
    """Suggest improvements for files with high correction rates.

    Args:
        profile: Workflow profile containing correction hotspots.
        suggestions: List to append new suggestions to.
    """
    for hotspot in profile.correction_hotspots:
        if hotspot.correction_rate < 0.15:
            continue
        num = len(suggestions) + 1
        file_name = Path(hotspot.file_pattern).name

        draft = (
            f"---\n"
            f"description: Specific rules for {file_name}\n"
            f"applyTo: '**/{file_name}'\n"
            f"---\n"
            f"# Rules for {file_name}\n\n"
            f"This file has a {hotspot.correction_rate:.0%} "
            f"correction rate.\n"
            f"Add specific coding rules here to reduce corrections.\n"
        )

        suggestions.append(
            Suggestion(
                number=num,
                category="high-correction",
                title=f"High correction rate on {file_name}",
                description=(
                    f"{file_name} has a {hotspot.correction_rate:.0%} "
                    f"correction rate ({hotspot.correction_count} "
                    f"corrections). Consider adding targeted rules."
                ),
                severity="warning",
                draft_content=draft,
                target_path=f".claude/rules/{file_name}-rules.md",
                asset_type="rule",
                estimated_quality="GOOD",
            )
        )


def _suggest_uncovered_workflows(
    profile: WorkflowProfile,
    suggestions: list[Suggestion],
    existing_names: frozenset[str] | None = None,
) -> None:
    """Suggest new skills/agents for uncovered workflow types.

    Args:
        profile: Workflow profile containing coverage gaps.
        suggestions: List to append new suggestions to.
        existing_names: Optional set of existing catalog entry names for
            deduplication. Gaps matching an existing name are skipped.
    """
    for gap in profile.coverage_gaps:
        # Skip if a similar skill already exists in the catalog
        if existing_names and any(gap in name for name in existing_names):
            continue
        num = len(suggestions) + 1

        draft = (
            f"---\n"
            f"name: {gap}\n"
            f"description: Automate {gap} workflow\n"
            f"user-invocable: true\n"
            f"---\n"
            f"# {gap.title()} Workflow\n\n"
            f"Automate the {gap} workflow for this repository.\n"
        )

        suggestions.append(
            Suggestion(
                number=num,
                category="uncovered-workflow",
                title=f"No skill for '{gap}' workflow",
                description=(
                    f"The '{gap}' workflow pattern was not detected "
                    f"in session data. Consider creating a skill to "
                    f"support this common workflow."
                ),
                severity="info",
                draft_content=draft,
                target_path=f".claude/skills/{gap}/SKILL.md",
                asset_type="skill",
                estimated_quality="NEEDS_WORK",
            )
        )


def _suggest_missing_hooks(
    profile: WorkflowProfile,
    suggestions: list[Suggestion],
) -> None:
    """Suggest hooks for safety or telemetry.

    Args:
        profile: Workflow profile to check for missing hooks.
        suggestions: List to append new suggestions to.
    """
    if profile.session_count == 0:
        num = len(suggestions) + 1
        suggestions.append(
            Suggestion(
                number=num,
                category="missing-hook",
                title="No telemetry hooks installed",
                description=(
                    "No session data found. Install AgentGuard "
                    "telemetry hooks to start collecting "
                    "workflow data."
                ),
                severity="warning",
                draft_content="Run: agentguard hooks install",
            )
        )

    # Suggest test hook if implement workflow has no test step
    for wf in profile.workflows:
        if wf.intent == "implement" and "Bash" not in wf.tools_used:
            num = len(suggestions) + 1
            suggestions.append(
                Suggestion(
                    number=num,
                    category="missing-hook",
                    title="No test execution in implement workflow",
                    description=(
                        "Implementation workflow doesn't include "
                        "test execution. Consider adding a "
                        "PostToolUse hook to run tests after edits."
                    ),
                    severity="info",
                    draft_content=(
                        "Add to .claude/settings.json hooks:\n"
                        '"PostToolUse": [{"matcher": "Edit", '
                        '"hooks": [{"type": "command", '
                        '"command": "make test", "async": true}]}]'
                    ),
                )
            )
            break


def _suggest_workflow_improvements(
    profile: WorkflowProfile,
    suggestions: list[Suggestion],
) -> None:
    """Suggest improvements for detected workflows.

    Args:
        profile: Workflow profile with workflow correction rates.
        suggestions: List to append new suggestions to.
    """
    for wf in profile.workflows:
        if wf.correction_rate > 0.2:
            num = len(suggestions) + 1
            suggestions.append(
                Suggestion(
                    number=num,
                    category="high-correction",
                    title=f"High corrections in '{wf.intent}' workflow",
                    description=(
                        f"The '{wf.intent}' workflow has a "
                        f"{wf.correction_rate:.0%} correction rate. "
                        f"Review and improve associated skills."
                    ),
                    severity="warning",
                )
            )


def generate_suggestions(
    profile: WorkflowProfile,
    catalog: Catalog | None = None,
) -> SuggestionReport:
    """Generate suggestions from a workflow profile.

    Args:
        profile: Workflow profile to generate suggestions from.
        catalog: Optional catalog for deduplication checks.

    Returns:
        SuggestionReport with numbered suggestions.
    """
    report = SuggestionReport(
        repo_path=profile.repo_path,
        repo_name=profile.repo_name,
    )

    existing_names: frozenset[str] | None = None
    if catalog is not None:
        existing_names = frozenset(e.name for e in catalog.all_entries())

    _suggest_high_corrections(profile, report.suggestions)
    _suggest_uncovered_workflows(profile, report.suggestions, existing_names)
    _suggest_missing_hooks(profile, report.suggestions)
    _suggest_workflow_improvements(profile, report.suggestions)
    return report


def suggest_for_repo(repo_path: Path) -> SuggestionReport:
    """Run profiling and produce suggestions for a repository.

    Args:
        repo_path: Path to the repository root.

    Returns:
        SuggestionReport with actionable suggestions.
    """
    from agentguard.config import AgentGuardConfig

    profile = profile_repo(repo_path)
    config = AgentGuardConfig.load()
    catalog = Catalog(config.catalog.path)
    catalog.load()
    return generate_suggestions(profile, catalog)


class ApplyResult(BaseModel):
    """Result of applying suggestions."""

    applied: int = 0
    skipped: int = 0
    paths: list[str] = Field(default_factory=list)


def apply_suggestions(
    repo_path: Path,
    *,
    dry_run: bool = False,
) -> ApplyResult:
    """Apply all actionable suggestions by creating assets.

    Only suggestions with ``target_path`` and ``draft_content`` are
    applied.  In dry-run mode no files are written.

    Args:
        repo_path: Repository root path.
        dry_run: If True, report what would be created.

    Returns:
        ApplyResult with counts and paths.
    """
    report = suggest_for_repo(repo_path)
    result = ApplyResult()

    for suggestion in report.suggestions:
        if not suggestion.target_path or not suggestion.draft_content:
            result.skipped += 1
            continue

        target = repo_path / suggestion.target_path
        result.paths.append(str(target))

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(suggestion.draft_content, encoding="utf-8")
            logger.info("Applied suggestion #%d: %s", suggestion.number, target)

        result.applied += 1

    return result
