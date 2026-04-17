from datetime import UTC, datetime
from pathlib import Path

from agentguard.evaluation.evaluator import (
    BaselineMetrics,
    RegressionAlert,
    RegressionReport,
    _check_correction_regression,
    _check_turn_regression,
    build_baseline,
    log_regression,
)
from agentguard.telemetry.events import ParsedSession, SessionMetrics

TELEMETRY_DIR = Path(__file__).parent / "fixtures" / "telemetry"


class TestBuildBaseline:
    def test_builds_from_sessions(self) -> None:
        sessions = [
            ParsedSession(
                session_id=f"s{i}",
                metrics=SessionMetrics(
                    session_id=f"s{i}",
                    tool_count=10,
                    turn_count=3,
                    correction_count=1,
                    duration_seconds=120.0,
                    start_time=datetime.now(UTC),
                ),
            )
            for i in range(5)
        ]
        baseline = build_baseline(sessions, window_days=30)
        assert len(baseline.correction_rates) == 5
        assert len(baseline.turn_counts) == 5
        assert len(baseline.durations) == 5


class TestCorrectionRegression:
    def test_detects_spike(self) -> None:
        baseline = BaselineMetrics(
            correction_rates=[0.05, 0.06, 0.04, 0.05, 0.07, 0.05, 0.06],
            turn_counts=[3.0, 4.0, 3.0, 3.0, 4.0, 3.0, 4.0],
        )
        # Session with very high correction rate
        target = ParsedSession(
            session_id="spike",
            metrics=SessionMetrics(
                session_id="spike",
                tool_count=10,
                turn_count=5,
                correction_count=5,  # 50% correction rate vs ~5% baseline
            ),
        )
        report = RegressionReport(session_id="spike")
        _check_correction_regression(target, baseline, report)
        assert report.has_regressions
        assert report.alerts[0].metric == "correction_rate"
        assert report.alerts[0].deviation > 2.0

    def test_no_regression_normal_rate(self) -> None:
        baseline = BaselineMetrics(
            correction_rates=[0.05, 0.06, 0.04, 0.05, 0.07, 0.05, 0.06],
        )
        target = ParsedSession(
            session_id="normal",
            metrics=SessionMetrics(
                session_id="normal",
                tool_count=20,
                turn_count=3,
                correction_count=1,  # 5% — well within normal range
            ),
        )
        report = RegressionReport(session_id="normal")
        _check_correction_regression(target, baseline, report)
        assert not report.has_regressions

    def test_skips_with_insufficient_data(self) -> None:
        baseline = BaselineMetrics(correction_rates=[0.05, 0.06])
        target = ParsedSession(
            session_id="test",
            metrics=SessionMetrics(
                session_id="test", tool_count=10, correction_count=5
            ),
        )
        report = RegressionReport(session_id="test")
        _check_correction_regression(target, baseline, report)
        assert not report.has_regressions


class TestTurnRegression:
    def test_detects_turn_spike(self) -> None:
        baseline = BaselineMetrics(
            turn_counts=[3.0, 4.0, 3.0, 3.0, 4.0, 3.0, 3.0],
        )
        target = ParsedSession(
            session_id="spike",
            metrics=SessionMetrics(
                session_id="spike",
                tool_count=20,
                turn_count=15,  # way above 3.3 avg
            ),
        )
        report = RegressionReport(session_id="spike")
        _check_turn_regression(target, baseline, report)
        assert report.has_regressions
        assert report.alerts[0].metric == "turn_count"

    def test_no_regression_normal_turns(self) -> None:
        baseline = BaselineMetrics(
            turn_counts=[3.0, 4.0, 3.0, 3.0, 4.0, 3.0, 4.0],
        )
        target = ParsedSession(
            session_id="normal",
            metrics=SessionMetrics(session_id="normal", tool_count=10, turn_count=4),
        )
        report = RegressionReport(session_id="normal")
        _check_turn_regression(target, baseline, report)
        assert not report.has_regressions


class TestLogRegression:
    def test_logs_to_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "regressions.jsonl"
        report = RegressionReport(
            session_id="test",
            alerts=[
                RegressionAlert(
                    asset_id="session",
                    metric="correction_rate",
                    current_value=0.5,
                    baseline_mean=0.05,
                    baseline_std=0.01,
                    deviation=45.0,
                )
            ],
        )
        log_regression(log_path, report)
        assert log_path.exists()
        content = log_path.read_text()
        assert "correction_rate" in content

    def test_skips_empty_report(self, tmp_path: Path) -> None:
        log_path = tmp_path / "regressions.jsonl"
        report = RegressionReport(session_id="test")
        log_regression(log_path, report)
        assert not log_path.exists()
