import logging
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel

from reagent.llm.config import PROVIDER_ENV_KEYS

logger = logging.getLogger(__name__)

_FILE_REF_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"`\./([^`]+)`"),
    re.compile(r"\b(\w[\w./]*\.(py|ts|js|go|rs|sh))\b"),
]

_CI_GLOBS = ("*ci*", "*test*")
_API_GLOBS = ("*api*",)
_TEST_GLOBS = ("*test*",)


class DriftReport(BaseModel):
    """A single drift finding for one asset.

    Attributes:
        asset_path: Relative or absolute path to the asset file.
        asset_type: Type of asset (agent, skill, command, etc.).
        drift_type: Category of drift (stale, outdated, missing, config_drift).
        details: Human-readable description of the drift.
        severity: info, warning, or error.
    """

    asset_path: str
    asset_type: str
    drift_type: str
    details: str
    severity: str


def _extract_file_refs(content: str) -> list[str]:
    """Extract file-path references from markdown content.

    Args:
        content: Markdown text to scan.

    Returns:
        Deduplicated list of file reference strings found.
    """
    refs: set[str] = set()
    for pattern in _FILE_REF_PATTERNS:
        for match in pattern.finditer(content):
            refs.add(match.group(1))
    return list(refs)


def _infer_asset_type_from_path(asset_path: Path) -> str:
    """Infer a human-readable asset type from its filesystem location.

    Args:
        asset_path: Path to the asset file.

    Returns:
        Asset type string.
    """
    parts = asset_path.parts
    for part in parts:
        if part in ("agents", "skills", "commands", "rules"):
            return part.rstrip("s")  # e.g. "agents" → "agent"
    return "asset"


def _check_stale_asset(asset_path: Path, repo_path: Path) -> list[DriftReport]:
    """Check a single asset for stale file references.

    Args:
        asset_path: Path to the markdown asset file.
        repo_path: Repository root for resolving relative paths.

    Returns:
        List of DriftReport instances for stale references found.
    """
    try:
        content = asset_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read asset %s: %s", asset_path, exc)
        return []

    reports: list[DriftReport] = []
    asset_type = _infer_asset_type_from_path(asset_path)
    refs = _extract_file_refs(content)

    for ref in refs:
        candidate = repo_path / ref
        if not candidate.exists():
            reports.append(
                DriftReport(
                    asset_path=str(asset_path),
                    asset_type=asset_type,
                    drift_type="stale",
                    details=f"references removed file ./{ref}",
                    severity="warning",
                )
            )
    return reports


def _glob_exists(directory: Path, *patterns: str) -> bool:
    """Return True if any of the glob patterns match a file under *directory*.

    Args:
        directory: Directory to search in.
        *patterns: Glob patterns to try.

    Returns:
        True if at least one file matches.
    """
    for pattern in patterns:
        if any(directory.glob(pattern)):
            return True
    return False


def _load_reagent_config() -> dict[str, object] | None:
    """Load the reagent config YAML from the default path.

    Returns:
        Parsed YAML dict, or None if the file does not exist or is invalid.
    """
    config_path = Path.home() / ".reagent" / "config.yaml"
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to parse reagent config: %s", exc)
    return None


def _get_configured_provider(config: dict[str, object]) -> str | None:
    """Extract the LLM provider name from a reagent config dict.

    Args:
        config: Parsed reagent config dictionary.

    Returns:
        Provider string or None if not set.
    """
    llm = config.get("llm")
    if isinstance(llm, dict):
        provider = llm.get("provider")
        if isinstance(provider, str):
            return provider
    return None


class DriftDetector:
    """Detect drift in reagent-managed assets within a repository."""

    def detect(self, repo_path: Path) -> list[DriftReport]:
        """Run all drift checks and return combined findings.

        Args:
            repo_path: Root of the repository to inspect.

        Returns:
            List of DriftReport instances describing all drift found.
        """
        reports: list[DriftReport] = []
        reports.extend(self._check_stale(repo_path))
        reports.extend(self._check_missing(repo_path))
        reports.extend(self._check_config_drift())
        return reports

    def _check_stale(self, repo_path: Path) -> list[DriftReport]:
        """Check if asset content references files that no longer exist.

        Args:
            repo_path: Repository root path.

        Returns:
            List of stale-reference DriftReports.
        """
        claude_dir = repo_path / ".claude"
        if not claude_dir.exists():
            return []

        reports: list[DriftReport] = []
        for md_file in claude_dir.rglob("*.md"):
            reports.extend(_check_stale_asset(md_file, repo_path))
        return reports

    def _check_missing(self, repo_path: Path) -> list[DriftReport]:
        """Check if the repo profile implies assets that are absent.

        Uses analyze_repo to detect repo capabilities and compares them
        against the files present under .claude/.

        Args:
            repo_path: Repository root path.

        Returns:
            List of missing-asset DriftReports.
        """
        from reagent.intelligence.analyzer import analyze_repo

        try:
            profile = analyze_repo(repo_path)
        except (OSError, ValueError) as exc:
            logger.warning("analyze_repo failed during drift check: %s", exc)
            return []

        reports: list[DriftReport] = []
        agents_dir = repo_path / ".claude" / "agents"
        skills_dir = repo_path / ".claude" / "skills"

        reports.extend(self._check_missing_ci_asset(profile, agents_dir))
        reports.extend(self._check_missing_api_asset(profile, agents_dir))
        reports.extend(self._check_missing_test_skill(profile, skills_dir))
        return reports

    def _check_missing_ci_asset(
        self, profile: object, agents_dir: Path
    ) -> list[DriftReport]:
        """Report a missing CI agent when repo has CI configuration.

        Args:
            profile: RepoProfile instance.
            agents_dir: Path to .claude/agents/.

        Returns:
            DriftReport list (empty if no issue found).
        """
        if not getattr(profile, "has_ci", False):
            return []
        if agents_dir.exists() and _glob_exists(agents_dir, *_CI_GLOBS):
            return []
        return [
            DriftReport(
                asset_path=str(agents_dir),
                asset_type="agent",
                drift_type="missing",
                details=(
                    "Repo has CI configuration but no CI/test agent"
                    " found in .claude/agents/"
                ),
                severity="warning",
            )
        ]

    def _check_missing_api_asset(
        self, profile: object, agents_dir: Path
    ) -> list[DriftReport]:
        """Report a missing API agent when repo has API routes.

        Args:
            profile: RepoProfile instance.
            agents_dir: Path to .claude/agents/.

        Returns:
            DriftReport list (empty if no issue found).
        """
        if not getattr(profile, "has_api_routes", False):
            return []
        if agents_dir.exists() and _glob_exists(agents_dir, *_API_GLOBS):
            return []
        return [
            DriftReport(
                asset_path=str(agents_dir),
                asset_type="agent",
                drift_type="missing",
                details="Repo has API routes but no API agent found in .claude/agents/",
                severity="warning",
            )
        ]

    def _check_missing_test_skill(
        self, profile: object, skills_dir: Path
    ) -> list[DriftReport]:
        """Report a missing test skill when repo has a test runner configured.

        Args:
            profile: RepoProfile instance.
            skills_dir: Path to .claude/skills/.

        Returns:
            DriftReport list (empty if no issue found).
        """
        test_config = getattr(profile, "test_config", None)
        runner = getattr(test_config, "runner", None) if test_config else None
        if not runner:
            return []
        if skills_dir.exists() and _glob_exists(skills_dir, *_TEST_GLOBS):
            return []
        return [
            DriftReport(
                asset_path=str(skills_dir),
                asset_type="skill",
                drift_type="missing",
                details=(
                    f"Repo uses {runner} but no test skill found in .claude/skills/"
                ),
                severity="info",
            )
        ]

    def _check_config_drift(self) -> list[DriftReport]:
        """Check if the reagent config references providers without env vars set.

        Args:
            repo_path: Repository root path (unused, kept for API consistency).

        Returns:
            List of config-drift DriftReports.
        """
        config = _load_reagent_config()
        if config is None:
            return []

        provider = _get_configured_provider(config)
        if provider is None:
            return []

        env_var = PROVIDER_ENV_KEYS.get(provider)
        if env_var is None or os.environ.get(env_var):
            return []

        return [
            DriftReport(
                asset_path=str(Path.home() / ".reagent" / "config.yaml"),
                asset_type="config",
                drift_type="config_drift",
                details=(f"Provider '{provider}' configured but {env_var} is not set"),
                severity="warning",
            )
        ]
