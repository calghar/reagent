import json
import logging
import sqlite3
import statistics
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from reagent._tuning import get_tuning
from reagent.config import ReagentConfig
from reagent.core.catalog import Catalog, CatalogEntry
from reagent.security.scanner import scan_file
from reagent.security.snapshots import SnapshotStore
from reagent.telemetry.events import (
    ParsedSession,
    find_sessions_dir,
    parse_all_sessions,
)
from reagent.telemetry.profiler import WorkflowProfile, profile_repo

logger = logging.getLogger(__name__)


class QualityLabel(StrEnum):
    """Qualitative quality label for an asset."""

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    NEEDS_WORK = "NEEDS_WORK"
    POOR = "POOR"


class AssetMetrics(BaseModel):
    """Per-asset quality metrics computed from telemetry data."""

    asset_id: str
    asset_type: str = ""
    name: str = ""
    invocation_rate: float = 0.0
    completion_rate: float = 0.0
    correction_rate: float = 0.0
    turn_efficiency: float = 0.0
    staleness_days: float = 0.0
    coverage: float = 0.0
    security_score: float = 100.0
    freshness: float = 100.0
    quality_score: float = 0.0
    label: QualityLabel = QualityLabel.POOR


class QualityReport(BaseModel):
    """Full quality evaluation report for a set of assets."""

    repo_path: str = ""
    repo_name: str = ""
    evaluated: int = 0
    healthy: int = 0
    underperforming: int = 0
    stale: int = 0
    asset_metrics: list[AssetMetrics] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


METRIC_WEIGHTS = {
    "invocation_rate": 0.15,
    "completion_rate": 0.15,
    "correction_rate": 0.20,
    "turn_efficiency": 0.10,
    "staleness": 0.10,
    "coverage": 0.10,
    "security_score": 0.10,
    "freshness": 0.10,
}


def _normalize_invocation_rate(rate: float) -> float:
    """Normalize invocation rate to 0-100 scale.

    Args:
        rate: Raw invocations per week.

    Returns:
        Normalized score where >=5/week = 100.
    """
    return min(rate / get_tuning().evaluation.max_invocations_per_week, 1.0) * 100


def _normalize_completion_rate(rate: float) -> float:
    """Normalize completion rate (already 0-1) to 0-100 scale.

    Args:
        rate: Completion rate as fraction (0.0-1.0).

    Returns:
        Score on 0-100 scale.
    """
    return rate * 100


def _normalize_correction_rate(rate: float) -> float:
    """Normalize correction rate (inverted: lower = better).

    Args:
        rate: Correction rate as fraction (0.0-1.0).

    Returns:
        Score on 0-100 scale where 0% corrections = 100.
    """
    return max(0.0, (1.0 - rate) * 100)


def _normalize_turn_efficiency(avg_turns: float) -> float:
    """Normalize turn efficiency to 0-100 scale.

    Args:
        avg_turns: Average turns per task.

    Returns:
        Score on 0-100 scale where 1 turn = 100, 20+ turns = 0.
    """
    if avg_turns <= 0:
        return 50.0
    efficiency = get_tuning().evaluation.max_turn_efficiency
    return max(0.0, min(100.0, (1.0 - (avg_turns - 1) / efficiency) * 100))


def _normalize_staleness(days: float) -> float:
    """Normalize staleness to 0-100 scale.

    Args:
        days: Days since last invocation.

    Returns:
        Score on 0-100 scale where 0 days = 100, 90+ = 0.
    """
    if days <= 0:
        return 100.0
    return max(0.0, (1.0 - days / get_tuning().evaluation.staleness_window_days) * 100)


def _compute_quality_score(metrics: AssetMetrics) -> float:
    """Compute weighted composite quality score.

    Args:
        metrics: Per-asset metrics to combine.

    Returns:
        Quality score on 0-100 scale.
    """
    normalized = {
        "invocation_rate": _normalize_invocation_rate(metrics.invocation_rate),
        "completion_rate": _normalize_completion_rate(metrics.completion_rate),
        "correction_rate": _normalize_correction_rate(metrics.correction_rate),
        "turn_efficiency": _normalize_turn_efficiency(metrics.turn_efficiency),
        "staleness": _normalize_staleness(metrics.staleness_days),
        "coverage": metrics.coverage,
        "security_score": metrics.security_score,
        "freshness": metrics.freshness,
    }
    return sum(normalized[k] * METRIC_WEIGHTS[k] for k in METRIC_WEIGHTS)


def _label_from_score(score: float) -> QualityLabel:
    """Assign a qualitative label from a numeric score.

    Args:
        score: Quality score on 0-100 scale.

    Returns:
        Qualitative label.
    """
    if score > 85:
        return QualityLabel.EXCELLENT
    if score > 70:
        return QualityLabel.GOOD
    if score > 50:
        return QualityLabel.NEEDS_WORK
    return QualityLabel.POOR


def _count_asset_invocations(
    asset_name: str,
    _asset_type: str,
    sessions: list[ParsedSession],
) -> int:
    """Count how many sessions invoke an asset.

    Args:
        asset_name: Name of the asset.
        _asset_type: Type of the asset (reserved for future filtering).
        sessions: Parsed sessions to search.

    Returns:
        Number of sessions that mention/invoke the asset.
    """
    count = 0
    for session in sessions:
        for tc in session.tool_calls:
            tool_lower = tc.tool_name.lower()
            input_str = json.dumps(tc.tool_input).lower()
            if asset_name.lower() in tool_lower or asset_name.lower() in input_str:
                count += 1
                break
    return count


def _compute_completion_rate(sessions: list[ParsedSession]) -> float:
    """Compute the fraction of sessions reaching natural completion.

    Args:
        sessions: Parsed sessions to analyze.

    Returns:
        Fraction of sessions that appear to complete naturally (0.0-1.0).
    """
    if not sessions:
        return 0.0
    completed = 0
    for session in sessions:
        if session.metrics.tool_count > 0:
            last_tools = (
                session.tool_calls[-3:]
                if len(session.tool_calls) >= 3
                else session.tool_calls
            )
            if all(tc.success for tc in last_tools):
                completed += 1
    return completed / len(sessions)


def _compute_correction_rate_for_asset(
    asset_name: str,
    sessions: list[ParsedSession],
) -> float:
    """Compute correction rate for a specific asset.

    Args:
        asset_name: Name of the asset.
        sessions: Parsed sessions containing corrections.

    Returns:
        Correction rate as a fraction (0.0-1.0).
    """
    total_invocations = 0
    corrections = 0
    name_lower = asset_name.lower()
    for session in sessions:
        session_matched = False
        for tc in session.tool_calls:
            input_str = json.dumps(tc.tool_input).lower()
            if name_lower in tc.tool_name.lower() or name_lower in input_str:
                total_invocations += 1
                session_matched = True
        if session_matched:
            corrections += session.metrics.correction_count
    if total_invocations == 0:
        return 0.0
    return min(1.0, corrections / max(total_invocations, 1))


def _compute_avg_turns(sessions: list[ParsedSession]) -> float:
    """Compute average turns across sessions.

    Args:
        sessions: Parsed sessions.

    Returns:
        Average turn count.
    """
    if not sessions:
        return 0.0
    turns = [s.metrics.turn_count for s in sessions if s.metrics.turn_count > 0]
    return statistics.mean(turns) if turns else 0.0


def _compute_security_score(entry: CatalogEntry) -> float:
    """Compute security score for an asset by scanning its file.

    Args:
        entry: Catalog entry for the asset.

    Returns:
        Score on 0-100 scale (100 = no issues).
    """
    if not entry.file_path.exists():
        return 50.0
    try:
        report = scan_file(entry.file_path)
        if not report.findings:
            return 100.0
        return max(0.0, 100.0 - report.risk_score * 10)
    except (OSError, ValueError):
        return 50.0


def _compute_freshness(entry: CatalogEntry) -> float:
    """Compute freshness score based on age of last modification.

    Args:
        entry: Catalog entry for the asset.

    Returns:
        Score on 0-100 scale (100 = modified today).
    """
    now = datetime.now(UTC)
    age_days = (now - entry.last_modified).total_seconds() / 86400
    window = get_tuning().evaluation.staleness_window_days
    return max(0.0, (1.0 - age_days / window) * 100)


def evaluate_asset(
    entry: CatalogEntry,
    sessions: list[ParsedSession],
    workflow_profile: WorkflowProfile | None = None,
    weeks_span: float = 4.0,
) -> AssetMetrics:
    """Evaluate quality metrics for a single asset.

    Args:
        entry: Catalog entry for the asset.
        sessions: All parsed sessions for the repo.
        workflow_profile: Optional workflow profile for coverage.
        weeks_span: Time span of sessions in weeks.

    Returns:
        Computed AssetMetrics for the asset.
    """
    metrics = AssetMetrics(
        asset_id=entry.asset_id,
        asset_type=entry.asset_type.value,
        name=entry.name,
    )

    invocations = _count_asset_invocations(entry.name, entry.asset_type.value, sessions)
    metrics.invocation_rate = invocations / max(weeks_span, 1.0)
    metrics.completion_rate = _compute_completion_rate(sessions)
    metrics.correction_rate = _compute_correction_rate_for_asset(entry.name, sessions)
    metrics.turn_efficiency = _compute_avg_turns(sessions)

    now = datetime.now(UTC)
    metrics.staleness_days = (now - entry.last_seen).total_seconds() / 86400

    if workflow_profile and workflow_profile.workflows:
        total_workflows = len(workflow_profile.workflows)
        covered = sum(
            1
            for wf in workflow_profile.workflows
            if entry.name.lower()
            in [s.lower() for s in wf.skills_used + wf.agents_used]
            or entry.name.lower() in wf.intent.lower()
        )
        metrics.coverage = (covered / total_workflows) * 100 if total_workflows else 0.0
    else:
        metrics.coverage = 50.0

    metrics.security_score = _compute_security_score(entry)
    metrics.freshness = _compute_freshness(entry)

    metrics.quality_score = round(_compute_quality_score(metrics), 1)
    metrics.label = _label_from_score(metrics.quality_score)

    return metrics


_INSERT_EVALUATION_SQL = """
    INSERT OR REPLACE INTO evaluations
        (evaluation_id, asset_path, asset_type, asset_name,
         quality_score, invocation_rate, correction_rate,
         issues_json, evaluated_at, repo_path)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def persist_report(report: QualityReport, db_path: Path | None = None) -> None:
    """Persist evaluation results to the SQLite database for dashboard visibility.

    Args:
        report: Quality report containing per-asset metrics to store.
        db_path: Optional database path override (defaults to ~/.reagent/reagent.db).
    """
    from reagent.storage import ReagentDB

    evaluated_at = report.timestamp.isoformat()

    with ReagentDB(db_path) as db:
        conn = db.connect()
        rows = [
            (
                uuid.uuid4().hex,
                m.asset_id,
                m.asset_type,
                m.name,
                m.quality_score,
                m.invocation_rate,
                m.correction_rate,
                "[]",
                evaluated_at,
                report.repo_path,
            )
            for m in report.asset_metrics
        ]
        conn.executemany(_INSERT_EVALUATION_SQL, rows)
        conn.commit()

    logger.debug(
        "Persisted %d evaluation(s) for %s",
        len(report.asset_metrics),
        report.repo_path,
    )


def evaluate_repo(
    repo_path: Path,
    config: ReagentConfig | None = None,
    catalog: Catalog | None = None,
    db_path: Path | None = None,
) -> QualityReport:
    """Evaluate quality metrics for all assets in a repository.

    Args:
        repo_path: Path to the repository.
        config: Reagent configuration.
        catalog: Loaded asset catalog.
        db_path: Optional database path override for persistence.

    Returns:
        QualityReport with per-asset metrics.
    """
    repo_path = repo_path.resolve()
    config = config or ReagentConfig.load()

    if catalog is None:
        catalog = Catalog(config.catalog.path)
        catalog.load()

    report = QualityReport(
        repo_path=str(repo_path),
        repo_name=repo_path.name,
    )

    entries = catalog.query(repo_name=repo_path.name)
    if not entries:
        from reagent.core.inventory import scan_repo

        scanned = scan_repo(repo_path)
        if scanned:
            catalog.apply_diff(scanned, [], [])
            catalog.save()
            entries = catalog.query(repo_name=repo_path.name)
        if not entries:
            return report

    sessions_dir = find_sessions_dir(repo_path)
    sessions: list[ParsedSession] = []
    if sessions_dir:
        sessions = parse_all_sessions(sessions_dir)

    weeks_span = 4.0
    if sessions:
        timestamps = []
        for s in sessions:
            if s.metrics.start_time:
                timestamps.append(s.metrics.start_time)
        if len(timestamps) >= 2:
            span = (max(timestamps) - min(timestamps)).total_seconds()
            weeks_span = max(1.0, span / (7 * 86400))

    workflow_profile: WorkflowProfile | None = None
    try:
        workflow_profile = profile_repo(repo_path)
    except (OSError, ValueError):
        pass  # Profiling is best-effort; missing transcripts are fine

    for entry in entries:
        metrics = evaluate_asset(entry, sessions, workflow_profile, weeks_span)
        report.asset_metrics.append(metrics)
        report.evaluated += 1

        if metrics.label in (QualityLabel.EXCELLENT, QualityLabel.GOOD):
            report.healthy += 1
        elif metrics.staleness_days > get_tuning().evaluation.staleness_window_days:
            report.stale += 1
        else:
            report.underperforming += 1

    try:
        persist_report(report, db_path=db_path)
    except (OSError, sqlite3.Error):
        logger.debug("Failed to persist evaluation report", exc_info=True)

    return report


class RegressionAlert(BaseModel):
    """A detected quality regression for an asset."""

    asset_id: str
    metric: str
    current_value: float
    baseline_mean: float
    baseline_std: float
    deviation: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    related_changes: list[str] = Field(default_factory=list)


class RegressionReport(BaseModel):
    """Regression detection report for a session."""

    session_id: str
    repo_path: str = ""
    alerts: list[RegressionAlert] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_regressions(self) -> bool:
        return len(self.alerts) > 0


class BaselineMetrics(BaseModel):
    """Rolling baseline metrics for comparison."""

    correction_rates: list[float] = Field(default_factory=list)
    turn_counts: list[float] = Field(default_factory=list)
    tool_counts: list[float] = Field(default_factory=list)
    durations: list[float] = Field(default_factory=list)


def build_baseline(
    sessions: list[ParsedSession], window_days: int = 30
) -> BaselineMetrics:
    """Build baseline metrics from historical sessions.

    Args:
        sessions: Historical parsed sessions.
        window_days: Number of days to include in the baseline.

    Returns:
        BaselineMetrics aggregated from the sessions.
    """
    baseline = BaselineMetrics()
    cutoff = datetime.now(UTC).timestamp() - (window_days * 86400)

    for session in sessions:
        if (
            session.metrics.start_time
            and session.metrics.start_time.timestamp() < cutoff
        ):
            continue
        total = max(session.metrics.tool_count, 1)
        baseline.correction_rates.append(session.metrics.correction_count / total)
        baseline.turn_counts.append(float(session.metrics.turn_count))
        baseline.tool_counts.append(float(session.metrics.tool_count))
        if session.metrics.duration_seconds > 0:
            baseline.durations.append(session.metrics.duration_seconds)

    return baseline


def check_regression(
    session_id: str,
    repo_path: Path,
    config: ReagentConfig | None = None,
    snapshot_store: SnapshotStore | None = None,
) -> RegressionReport:
    """Check a single session for regressions against baseline.

    Args:
        session_id: Session identifier to check.
        repo_path: Path to the repository.
        config: Reagent configuration.
        snapshot_store: Optional snapshot store for change correlation.

    Returns:
        RegressionReport with any detected alerts.
    """
    config = config or ReagentConfig.load()
    report = RegressionReport(session_id=session_id, repo_path=str(repo_path))

    sessions_dir = find_sessions_dir(repo_path)
    if not sessions_dir:
        return report

    sessions = parse_all_sessions(sessions_dir)
    if not sessions:
        return report

    target = None
    others: list[ParsedSession] = []
    for s in sessions:
        if s.session_id == session_id:
            target = s
        else:
            others.append(s)

    if target is None:
        return report

    baseline = build_baseline(others)
    _check_correction_regression(target, baseline, report, snapshot_store)
    _check_turn_regression(target, baseline, report)

    return report


def _check_correction_regression(
    target: ParsedSession,
    baseline: BaselineMetrics,
    report: RegressionReport,
    snapshot_store: SnapshotStore | None = None,
) -> None:
    """Check if correction rate has regressed significantly.

    Args:
        target: The session to check.
        baseline: Rolling baseline metrics.
        report: Report to append alerts to.
        snapshot_store: Optional snapshot store for change correlation.
    """
    if len(baseline.correction_rates) < 3:
        return

    total = max(target.metrics.tool_count, 1)
    current_rate = target.metrics.correction_count / total
    mean = statistics.mean(baseline.correction_rates)
    std = (
        statistics.stdev(baseline.correction_rates)
        if len(baseline.correction_rates) > 1
        else 0.0
    )

    if std > 0 and current_rate > mean + 2 * std:
        related: list[str] = []
        if snapshot_store:
            for chain in snapshot_store.all_chains():
                if chain.latest:
                    age = (
                        datetime.now(UTC) - chain.latest.timestamp
                    ).total_seconds() / 86400
                    if age < 7:
                        related.append(f"{chain.asset_id} modified {age:.0f}d ago")

        report.alerts.append(
            RegressionAlert(
                asset_id="session",
                metric="correction_rate",
                current_value=current_rate,
                baseline_mean=mean,
                baseline_std=std,
                deviation=(current_rate - mean) / std,
                related_changes=related,
            )
        )


def _check_turn_regression(
    target: ParsedSession,
    baseline: BaselineMetrics,
    report: RegressionReport,
) -> None:
    """Check if turn count has regressed significantly.

    Args:
        target: The session to check.
        baseline: Rolling baseline metrics.
        report: Report to append alerts to.
    """
    if len(baseline.turn_counts) < 3:
        return

    current = float(target.metrics.turn_count)
    mean = statistics.mean(baseline.turn_counts)
    std = (
        statistics.stdev(baseline.turn_counts) if len(baseline.turn_counts) > 1 else 0.0
    )

    if std > 0 and current > mean + 2 * std:
        report.alerts.append(
            RegressionAlert(
                asset_id="session",
                metric="turn_count",
                current_value=current,
                baseline_mean=mean,
                baseline_std=std,
                deviation=(current - mean) / std,
            )
        )


def log_regression(log_path: Path, report: RegressionReport) -> None:
    """Append regression report to the regressions log.

    Args:
        log_path: Path to regressions.jsonl.
        report: Report to log.
    """
    if not report.has_regressions:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(report.model_dump_json() + "\n")


class ABTest(BaseModel):
    """An active A/B test comparing asset variants."""

    test_id: str
    original_asset_id: str
    variant_name: str
    variant_path: str = ""
    original_path: str = ""
    description: str = ""
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    active: bool = True
    sessions_original: int = 0
    sessions_variant: int = 0


class ABTestStore:
    """Store for managing A/B test assignments."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._tests: dict[str, ABTest] = {}

    def load(self) -> None:
        """Load A/B tests from JSONL file."""
        self._tests.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                test = ABTest.model_validate_json(line)
                self._tests[test.test_id] = test
            except ValueError:
                continue

    def save(self) -> None:
        """Write all tests to JSONL file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            t.model_dump_json()
            for t in sorted(self._tests.values(), key=lambda t: t.test_id)
        ]
        self.path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")

    def create_test(
        self,
        original_asset_id: str,
        variant_name: str,
        description: str = "",
        original_path: str = "",
        variant_path: str = "",
    ) -> ABTest:
        """Create a new A/B test.

        Args:
            original_asset_id: Asset ID of the original.
            variant_name: Name for the variant.
            description: Description of the change.
            original_path: Path to the original asset file.
            variant_path: Path to the variant asset file.

        Returns:
            The created ABTest.
        """
        test_id = f"{original_asset_id}::{variant_name}"
        test = ABTest(
            test_id=test_id,
            original_asset_id=original_asset_id,
            variant_name=variant_name,
            description=description,
            original_path=original_path,
            variant_path=variant_path,
        )
        self._tests[test_id] = test
        return test

    def get_test(self, test_id: str) -> ABTest | None:
        """Get a test by ID."""
        return self._tests.get(test_id)

    def get_tests_for_asset(self, asset_id: str) -> list[ABTest]:
        """Get all active tests for an asset."""
        return [
            t
            for t in self._tests.values()
            if t.original_asset_id == asset_id and t.active
        ]

    def all_tests(self) -> list[ABTest]:
        """Return all tests."""
        return sorted(self._tests.values(), key=lambda t: t.test_id)

    def deactivate(self, test_id: str) -> None:
        """Mark a test as inactive."""
        test = self._tests.get(test_id)
        if test:
            test.active = False

    def route_session(self, test_id: str, session_id: str) -> str:
        """Determine which variant to use for a session.

        Uses deterministic hashing for consistent assignment.

        Args:
            test_id: The A/B test identifier.
            session_id: The session identifier.

        Returns:
            "original" or "variant".
        """
        import hashlib

        test = self._tests.get(test_id)
        if not test or not test.active:
            return "original"

        hash_input = f"{test_id}:{session_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        if hash_val % 2 == 0:
            test.sessions_original += 1
            return "original"
        test.sessions_variant += 1
        return "variant"


def create_variant(
    asset_id: str,
    variant_name: str,
    description: str,
    catalog: Catalog,
    ab_store: ABTestStore,
) -> ABTest:
    """Create a variant copy of an asset for A/B testing.

    Args:
        asset_id: The original asset identifier.
        variant_name: Name for the variant.
        description: Description of the change.
        catalog: Loaded asset catalog.
        ab_store: A/B test store.

    Returns:
        The created ABTest.

    Raises:
        ValueError: If the asset is not found in the catalog.
    """
    entry = catalog.get(asset_id)
    if not entry:
        raise ValueError(f"Asset not found: {asset_id}")

    original_path = entry.file_path
    if not original_path.exists():
        raise ValueError(f"Asset file not found: {original_path}")

    variant_path = (
        original_path.parent
        / f"{original_path.stem}.variant-{variant_name}{original_path.suffix}"
    )
    content = original_path.read_text(encoding="utf-8")
    variant_path.parent.mkdir(parents=True, exist_ok=True)
    variant_path.write_text(content, encoding="utf-8")

    return ab_store.create_test(
        original_asset_id=asset_id,
        variant_name=variant_name,
        description=description,
        original_path=str(original_path),
        variant_path=str(variant_path),
    )


class VariantComparison(BaseModel):
    """Statistical comparison of two asset variants."""

    original_id: str
    variant_name: str
    original_metrics: AssetMetrics | None = None
    variant_metrics: AssetMetrics | None = None
    winner: str = ""
    confidence: float = 0.0
    metric_diffs: dict[str, float] = Field(default_factory=dict)


def compare_variants(
    original_id: str,
    variant_name: str,
    catalog: Catalog,
    repo_path: Path,
) -> VariantComparison:
    """Compare quality metrics between original and variant.

    Args:
        original_id: Asset ID of the original.
        variant_name: Name of the variant.
        catalog: Loaded catalog.
        repo_path: Path to the repository.

    Returns:
        VariantComparison with statistical results.
    """
    comparison = VariantComparison(
        original_id=original_id,
        variant_name=variant_name,
    )

    entry = catalog.get(original_id)
    if not entry:
        return comparison

    sessions_dir = find_sessions_dir(repo_path)
    sessions = parse_all_sessions(sessions_dir) if sessions_dir else []

    comparison.original_metrics = evaluate_asset(entry, sessions)

    if comparison.original_metrics and comparison.variant_metrics:
        diff = (
            comparison.variant_metrics.quality_score
            - comparison.original_metrics.quality_score
        )
        comparison.metric_diffs["quality_score"] = diff
        if diff > 5:
            comparison.winner = "variant"
            comparison.confidence = min(abs(diff) / 20, 1.0)
        elif diff < -5:
            comparison.winner = "original"
            comparison.confidence = min(abs(diff) / 20, 1.0)
        else:
            comparison.winner = "inconclusive"
    else:
        comparison.winner = "inconclusive"

    return comparison


def promote_variant(
    test_id: str,
    ab_store: ABTestStore,
) -> Path | None:
    """Promote a variant to replace the original.

    Args:
        test_id: The A/B test identifier.
        ab_store: A/B test store.

    Returns:
        Path where the promoted content was written, or None on failure.
    """
    test = ab_store.get_test(test_id)
    if not test:
        return None

    variant_path = Path(test.variant_path)
    original_path = Path(test.original_path)
    if not variant_path.exists():
        return None

    content = variant_path.read_text(encoding="utf-8")
    original_path.write_text(content, encoding="utf-8")
    ab_store.deactivate(test_id)

    return original_path
