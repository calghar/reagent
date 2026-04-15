import logging
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from reagent._tuning import score_to_grade as _grade_from_score

logger = logging.getLogger(__name__)

_SECURITY_GRADE_ORDER = ["A", "B", "C", "D", "F"]
_MIN_PASSING_GRADE = "C"


class CIMode(StrEnum):
    """Operating mode for the CI runner."""

    CHECK = "check"
    SUGGEST = "suggest"
    AUTO_FIX = "auto-fix"


class CIConfig(BaseModel):
    """Configuration for a CI run.

    Attributes:
        repo_path: Root of the repository to evaluate.
        mode: CI operating mode (check, suggest, or auto-fix).
        threshold: Minimum passing quality score (0-100).
        security: Whether to run the security scanner.
        output_format: Output format ("text" or "json").
    """

    repo_path: Path = Field(default_factory=Path.cwd)
    mode: CIMode = CIMode.CHECK
    threshold: float = 60.0
    security: bool = True
    output_format: str = "text"


class CIResult(BaseModel):
    """Result of a CI run.

    Attributes:
        overall_score: Average quality score across all assets.
        security_grade: Letter grade from the security scanner.
        passed: True when all assets meet the threshold and security passes.
        asset_results: Per-asset result dicts with name/type/score/grade/passed.
        drift_reports: Serialised DriftReport dicts.
        suggestions: Human-readable improvement suggestions.
        fixes_applied: Filenames written to disk in auto-fix mode.
        diff: Unified diff of all changes made in auto-fix mode.
        exit_code: 0 (pass), 1 (quality fail), or 2 (security fail).
    """

    overall_score: float = 0.0
    security_grade: str = "A"
    passed: bool = True
    asset_results: list[dict[str, object]] = Field(default_factory=list)
    drift_reports: list[dict[str, object]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    fixes_applied: list[str] = Field(default_factory=list)
    diff: str = ""
    exit_code: int = 0


def _security_grade_passes(grade: str) -> bool:
    """Return True if *grade* is C or better.

    Args:
        grade: Letter grade string.

    Returns:
        True when the grade is acceptable for CI.
    """
    try:
        return _SECURITY_GRADE_ORDER.index(grade) <= _SECURITY_GRADE_ORDER.index(
            _MIN_PASSING_GRADE
        )
    except ValueError:
        return False


def _build_asset_results(
    asset_metrics: Sequence[object],
    threshold: float,
) -> list[dict[str, object]]:
    """Serialise AssetMetrics into plain dicts for CIResult.

    Args:
        asset_metrics: List of AssetMetrics model instances.
        threshold: Minimum passing score.

    Returns:
        List of dicts with name, type, score, grade, and passed keys.
    """
    results: list[dict[str, object]] = []
    for m in asset_metrics:
        score: float = getattr(m, "quality_score", 0.0)
        name: str = getattr(m, "name", "")
        asset_type: str = getattr(m, "asset_type", "")
        grade = _grade_from_score(score)
        passed = score == 0 or score >= threshold
        results.append(
            {
                "name": name,
                "type": asset_type,
                "score": score,
                "grade": grade,
                "passed": passed,
            }
        )
    return results


def _build_suggestions(
    asset_results: list[dict[str, object]],
    drift_reports: list[dict[str, object]],
    threshold: float,
) -> list[str]:
    """Build the suggestions list from asset results and drift reports.

    Args:
        asset_results: Serialised per-asset result dicts.
        drift_reports: Serialised DriftReport dicts.
        threshold: Quality threshold used to identify failing assets.

    Returns:
        List of human-readable suggestion strings.
    """
    suggestions: list[str] = []
    for ar in asset_results:
        score = float(ar["score"])  # type: ignore[arg-type]
        if score > 0.0 and score < threshold:
            suggestions.append(
                f"Regenerate {ar['name']} ({ar['type']}): "
                f"score {score:.0f}/100 \u2014 below threshold"
            )
    for dr in drift_reports:
        severity = str(dr.get("severity", ""))
        if severity in ("warning", "error"):
            suggestions.append(
                f"Drift in {dr.get('asset_path', '')}: {dr.get('details', '')}"
            )
    return suggestions


def _apply_autofix(
    asset_results: list[dict[str, object]],
    repo_path: Path,
    threshold: float,
) -> tuple[list[str], str]:
    """Return empty results; auto-fix requires the removed creation module.

    Args:
        asset_results: Serialised per-asset result dicts.
        repo_path: Repository root path.
        threshold: Quality threshold.

    Returns:
        Tuple of (empty list, empty string).
    """
    logger.warning(
        "Auto-fix is unavailable: the creation module has been removed"
    )
    return [], ""


def _resolve_asset_path(repo_path: Path, name: str, asset_type: str) -> Path | None:
    """Attempt to find the on-disk path for a named asset.

    Args:
        repo_path: Repository root path.
        name: Asset name (stem).
        asset_type: Asset type string (agent, skill, command, etc.).

    Returns:
        Path if found, else None.
    """
    claude_dir = repo_path / ".claude"
    candidates: list[Path] = []

    if asset_type == "agent":
        candidates.append(claude_dir / "agents" / f"{name}.md")
    elif asset_type == "skill":
        candidates.append(claude_dir / "skills" / name / "SKILL.md")
    elif asset_type == "command":
        candidates.append(claude_dir / "commands" / f"{name}.md")
    else:
        candidates.extend(
            [
                claude_dir / "agents" / f"{name}.md",
                claude_dir / "skills" / name / "SKILL.md",
                claude_dir / "commands" / f"{name}.md",
                claude_dir / "rules" / f"{name}.md",
            ]
        )

    for path in candidates:
        if path.exists():
            return path
    return None


def _compute_overall_score(asset_results: list[dict[str, object]]) -> float:
    """Compute the mean quality score across all assets.

    Args:
        asset_results: Serialised per-asset result dicts.

    Returns:
        Mean score, or 0.0 if there are no assets.
    """
    scores = [float(ar["score"]) for ar in asset_results]  # type: ignore[arg-type]
    return sum(scores) / len(scores) if scores else 0.0


def _determine_exit_code(
    asset_results: list[dict[str, object]],
    security_grade: str,
    security_enabled: bool,
) -> int:
    """Compute the exit code for the CI run.

    Priority: security failures (2) > quality failures (1) > pass (0).

    Args:
        asset_results: Serialised per-asset result dicts.
        security_grade: Letter grade from the security scanner.
        security_enabled: Whether security scanning was performed.

    Returns:
        Exit code integer.
    """
    if security_enabled and not _security_grade_passes(security_grade):
        return 2
    quality_fail = any(not bool(ar["passed"]) for ar in asset_results)
    return 1 if quality_fail else 0


def _determine_passed(
    asset_results: list[dict[str, object]],
    security_grade: str,
    security_enabled: bool,
) -> bool:
    """Return True when all quality and security checks pass.

    Args:
        asset_results: Serialised per-asset result dicts.
        security_grade: Letter grade from the security scanner.
        security_enabled: Whether security scanning was performed.

    Returns:
        True if the CI run should be considered passing.
    """
    quality_ok = all(bool(ar["passed"]) for ar in asset_results)
    security_ok = (not security_enabled) or _security_grade_passes(security_grade)
    return quality_ok and security_ok


def _empty_result(note: str = "") -> CIResult:
    """Return a passing CIResult with no assets.

    Args:
        note: Optional note appended to suggestions.

    Returns:
        Empty CIResult that exits 0.
    """
    suggestions = [note] if note else []
    return CIResult(
        overall_score=0.0,
        security_grade="A",
        passed=True,
        suggestions=suggestions,
        exit_code=0,
    )


class CIRunner:
    """Orchestrates a full CI quality run for a repository.

    Wraps evaluate_repo, scan_directory, DriftDetector, and optionally
    regenerate_asset to provide a single entry point for CI pipelines.
    """

    def run(self, config: CIConfig) -> CIResult:
        """Execute the CI run and return a structured result.

        Args:
            config: Configuration for this run.

        Returns:
            CIResult with scores, grades, suggestions, and exit code.
        """
        repo_path = config.repo_path.resolve()
        asset_results = self._evaluate_assets(repo_path, config.threshold)
        security_grade, drift_reports = self._collect_secondary(config, repo_path)

        overall_score = _compute_overall_score(asset_results)
        passed = _determine_passed(asset_results, security_grade, config.security)
        suggestions = _build_suggestions(asset_results, drift_reports, config.threshold)
        exit_code = _determine_exit_code(asset_results, security_grade, config.security)

        fixes_applied: list[str] = []
        diff = ""
        if config.mode == CIMode.AUTO_FIX:
            fixes_applied, diff = _apply_autofix(
                asset_results, repo_path, config.threshold
            )

        return CIResult(
            overall_score=round(overall_score, 1),
            security_grade=security_grade,
            passed=passed,
            asset_results=asset_results,
            drift_reports=drift_reports,
            suggestions=suggestions,
            fixes_applied=fixes_applied,
            diff=diff,
            exit_code=exit_code,
        )

    def _evaluate_assets(
        self, repo_path: Path, threshold: float
    ) -> list[dict[str, object]]:
        """Run evaluate_repo and convert to serialised asset dicts.

        Args:
            repo_path: Repository root path.
            threshold: Minimum passing score.

        Returns:
            Serialised asset result dicts, or empty list on failure.
        """
        from reagent.evaluation.evaluator import evaluate_repo

        try:
            quality_report = evaluate_repo(repo_path)
            return _build_asset_results(quality_report.asset_metrics, threshold)
        except (OSError, ValueError) as exc:
            logger.warning("evaluate_repo failed: %s", exc)
            return []

    def _collect_secondary(
        self, config: CIConfig, repo_path: Path
    ) -> tuple[str, list[dict[str, object]]]:
        """Run security scan and drift detection.

        Args:
            config: CI configuration.
            repo_path: Repository root path.

        Returns:
            Tuple of (security_grade, serialised drift report dicts).
        """
        security_grade = self._run_security(config, repo_path)
        drift_reports = self._run_drift(repo_path)
        return security_grade, drift_reports

    def _run_security(self, config: CIConfig, repo_path: Path) -> str:
        """Run the security scanner if enabled.

        Args:
            config: CI configuration.
            repo_path: Repository root path.

        Returns:
            Letter grade from the scanner, or "A" if scanning is disabled.
        """
        if not config.security:
            return "A"
        from reagent.security.scanner import (
            scan_directory,
            score_report,
        )

        try:
            scan_report = scan_directory(repo_path)
            _, grade = score_report(scan_report)
            return grade
        except (OSError, ValueError) as exc:
            logger.warning("Security scan failed: %s", exc)
            return "A"

    def _run_drift(self, repo_path: Path) -> list[dict[str, object]]:
        """Run drift detection and serialise reports.

        Args:
            repo_path: Repository root path.

        Returns:
            List of serialised DriftReport dicts.
        """
        from reagent.ci.drift import DriftDetector

        try:
            reports = DriftDetector().detect(repo_path)
            return [r.model_dump() for r in reports]
        except (OSError, ValueError) as exc:
            logger.warning("Drift detection failed: %s", exc)
            return []
