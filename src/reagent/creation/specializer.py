import logging
from pathlib import Path

from reagent.creation.creator import AssetDraft, _target_path
from reagent.intelligence.analyzer import RepoProfile, analyze_repo

logger = logging.getLogger(__name__)


class SpecializationResult:
    """Result of specializing global assets for a repo."""

    def __init__(self) -> None:
        self.drafts: list[AssetDraft] = []
        self.skipped: list[str] = []

    @property
    def count(self) -> int:
        return len(self.drafts)


def _find_global_assets() -> list[Path]:
    """Find all asset files in ~/.claude/.

    Returns:
        List of paths to global asset files.
    """
    global_claude = Path.home() / ".claude"
    if not global_claude.exists():
        return []

    files: list[Path] = []

    # Agents
    agents_dir = global_claude / "agents"
    if agents_dir.is_dir():
        files.extend(sorted(agents_dir.glob("*.md")))

    # Skills
    skills_dir = global_claude / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    files.append(skill_file)

    # Rules
    rules_dir = global_claude / "rules"
    if rules_dir.is_dir():
        files.extend(sorted(rules_dir.glob("*.md")))

    # Commands
    commands_dir = global_claude / "commands"
    if commands_dir.is_dir():
        files.extend(sorted(commands_dir.glob("*.md")))

    return files


def _detect_asset_type(path: Path) -> str:
    """Detect asset type from file path."""
    parts = [p.lower() for p in path.parts]
    if "agents" in parts:
        return "agent"
    if "skills" in parts or path.name == "SKILL.md":
        return "skill"
    if "rules" in parts:
        return "rule"
    if "commands" in parts:
        return "command"
    return "unknown"


def _specialize_content(
    content: str,
    asset_type: str,
    profile: RepoProfile,
) -> str:
    """Inject repo-specific parameters into asset content.

    Replaces generic placeholders and adds repo-specific sections.

    Args:
        content: Original asset content.
        asset_type: The asset type.
        profile: Repository profile.

    Returns:
        Specialized content.
    """
    lang = profile.primary_language or "code"
    frameworks = ", ".join(profile.frameworks) if profile.frameworks else lang
    test_cmd = profile.test_config.command or "run tests"
    lint_cmd = profile.lint_configs[0].command if profile.lint_configs else ""

    # Replace common placeholders
    result = content
    result = result.replace("{{language}}", lang)
    result = result.replace("{{framework}}", frameworks)
    result = result.replace("{{test_command}}", test_cmd)
    result = result.replace("{{lint_command}}", lint_cmd)
    result = result.replace("{{repo_name}}", profile.repo_name)

    # Add repo-specific section if not already present
    if asset_type in ("agent", "skill") and "## Stack" not in result:
        repo_section = (
            f"\n\n## Repository: {profile.repo_name}\n"
            f"- Language: {lang}\n"
            f"- Frameworks: {frameworks}\n"
            f"- Test command: `{test_cmd}`\n"
        )
        if lint_cmd:
            repo_section += f"- Lint command: `{lint_cmd}`\n"
        result += repo_section

    return result


def specialize_repo(
    repo_path: Path,
    profile: RepoProfile | None = None,
    global_claude_dir: Path | None = None,
) -> SpecializationResult:
    """Specialize global assets for a specific repository.

    Takes global patterns/archetypes from ~/.claude/, injects repo-specific
    parameters from the repo profile, adds repo-specific sections, and
    produces drafts for the repo's .claude/ directory.

    Args:
        repo_path: Repository root path.
        profile: Optional pre-computed repo profile.
        global_claude_dir: Override global .claude directory.

    Returns:
        SpecializationResult with drafts ready for review.
    """
    if profile is None:
        profile = analyze_repo(repo_path)

    result = SpecializationResult()

    if global_claude_dir:
        global_files = _find_assets_in_dir(global_claude_dir)
    else:
        global_files = _find_global_assets()

    if not global_files:
        return result

    for global_file in global_files:
        asset_type = _detect_asset_type(global_file)
        if asset_type == "unknown":
            result.skipped.append(str(global_file))
            continue

        try:
            content = global_file.read_text(encoding="utf-8")
        except OSError:
            result.skipped.append(str(global_file))
            continue

        specialized = _specialize_content(content, asset_type, profile)

        # Determine name from the file
        if asset_type == "skill":
            name = global_file.parent.name
        else:
            name = global_file.stem

        target = _target_path(asset_type, name, repo_path)

        draft = AssetDraft(
            asset_type=asset_type,
            name=name,
            content=specialized,
            target_path=target,
            origin="reagent-specialize",
        )
        result.drafts.append(draft)

    return result


def _find_assets_in_dir(directory: Path) -> list[Path]:
    """Find asset files in a given .claude-like directory."""
    files: list[Path] = []

    agents_dir = directory / "agents"
    if agents_dir.is_dir():
        files.extend(sorted(agents_dir.glob("*.md")))

    skills_dir = directory / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    files.append(skill_file)

    rules_dir = directory / "rules"
    if rules_dir.is_dir():
        files.extend(sorted(rules_dir.glob("*.md")))

    commands_dir = directory / "commands"
    if commands_dir.is_dir():
        files.extend(sorted(commands_dir.glob("*.md")))

    return files
