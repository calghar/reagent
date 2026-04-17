from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from agentguard.ci.drift import DriftDetector, DriftReport
from agentguard.ci.reporter import CIReporter
from agentguard.ci.runner import (
    CIConfig,
    CIMode,
    CIResult,
    CIRunner,
    _build_asset_results,
    _compute_overall_score,
    _determine_exit_code,
    _determine_passed,
    _grade_from_score,
    _security_grade_passes,
)


def _make_asset_result(
    name: str = "test-agent",
    asset_type: str = "agent",
    score: float = 75.0,
    threshold: float = 60.0,
) -> dict[str, Any]:
    passed = score == abs(0.0) or score >= threshold
    return {
        "name": name,
        "type": asset_type,
        "score": score,
        "grade": _grade_from_score(score),
        "passed": passed,
    }


def _make_ci_result(
    overall_score: float = 75.0,
    security_grade: str = "A",
    passed: bool = True,
    asset_results: list[dict[str, Any]] | None = None,
    drift_reports: list[dict[str, Any]] | None = None,
    suggestions: list[str] | None = None,
    exit_code: int = 0,
) -> CIResult:
    return CIResult(
        overall_score=overall_score,
        security_grade=security_grade,
        passed=passed,
        asset_results=asset_results or [],
        drift_reports=drift_reports or [],
        suggestions=suggestions or [],
        exit_code=exit_code,
    )


def _make_asset_metrics(
    name: str = "test-agent",
    asset_type: str = "agent",
    quality_score: float = 75.0,
) -> MagicMock:
    m = MagicMock()
    m.name = name
    m.asset_type = asset_type
    m.quality_score = quality_score
    return m


class TestCIResult:
    @pytest.mark.parametrize(
        ("score", "threshold", "passed", "exit_code"),
        [
            pytest.param(80.0, 60.0, True, 0, id="above_threshold"),
            pytest.param(40.0, 60.0, False, 1, id="below_threshold"),
        ],
    )
    def test_ci_result_pass_and_fail(
        self,
        score: float,
        threshold: float,
        passed: bool,
        exit_code: int,
    ) -> None:
        assets = [_make_asset_result(score=score, threshold=threshold)]
        if not passed:
            assets[0]["passed"] = False
        result = _make_ci_result(
            overall_score=score,
            passed=passed,
            asset_results=assets,
            exit_code=exit_code,
        )
        assert result.passed is passed
        assert result.exit_code == exit_code

    @pytest.mark.parametrize(
        ("passed", "security_grade", "exit_code"),
        [
            pytest.param(True, "A", 0, id="pass"),
            pytest.param(False, "A", 1, id="quality_fail"),
            pytest.param(False, "F", 2, id="security_fail"),
        ],
    )
    def test_exit_code_stored(
        self, passed: bool, security_grade: str, exit_code: int
    ) -> None:
        result = _make_ci_result(
            passed=passed, security_grade=security_grade, exit_code=exit_code
        )
        assert result.exit_code == exit_code

    def test_exit_code_security_takes_priority(self) -> None:
        """Exit code 2 (security) takes priority over 1 (quality)."""
        assets = [_make_asset_result(score=40.0, threshold=60.0)]
        assets[0]["passed"] = False
        exit_code = _determine_exit_code(assets, "F", security_enabled=True)
        result = _make_ci_result(
            overall_score=40.0,
            security_grade="F",
            passed=False,
            asset_results=assets,
            exit_code=exit_code,
        )
        assert result.exit_code == 2
        assert not _security_grade_passes(result.security_grade)

    @pytest.mark.parametrize(
        ("grade", "expected"),
        [
            pytest.param("A", True, id="A"),
            pytest.param("B", True, id="B"),
            pytest.param("C", True, id="C"),
            pytest.param("D", False, id="D"),
            pytest.param("F", False, id="F"),
        ],
    )
    def test_security_grade_passes(self, grade: str, expected: bool) -> None:
        assert _security_grade_passes(grade) is expected

    @pytest.mark.parametrize(
        ("assets_scores", "expected"),
        [
            pytest.param([], 0.0, id="empty"),
            pytest.param([80.0, 60.0], 70.0, id="average"),
        ],
    )
    def test_compute_overall_score(
        self, assets_scores: list[float], expected: float
    ) -> None:
        assets = [_make_asset_result(score=s) for s in assets_scores]
        assert _compute_overall_score(assets) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("security_grade", "security_enabled", "expected"),
        [
            pytest.param("A", True, True, id="all_ok"),
            pytest.param("F", False, True, id="security_disabled"),
        ],
    )
    def test_determine_passed(
        self, security_grade: str, security_enabled: bool, expected: bool
    ) -> None:
        assets = [_make_asset_result(score=80.0)]
        assert (
            _determine_passed(assets, security_grade, security_enabled=security_enabled)
            is expected
        )

    def test_build_asset_results_zero_score_treated_as_unknown(self) -> None:
        metrics = [_make_asset_metrics(quality_score=0.0)]
        results = _build_asset_results(metrics, threshold=60.0)
        assert results[0]["passed"] is True


class TestDriftDetector:
    @pytest.mark.parametrize(
        ("script_name", "create_script", "expect_stale"),
        [
            pytest.param("missing.sh", False, True, id="stale_reference"),
            pytest.param("deploy.sh", True, False, id="valid_reference"),
        ],
    )
    def test_stale_reference_detection(
        self,
        tmp_path: Path,
        script_name: str,
        create_script: bool,
        expect_stale: bool,
    ) -> None:
        claude_dir = tmp_path / ".claude" / "agents"
        claude_dir.mkdir(parents=True)
        agent_file = claude_dir / "test-agent.md"
        agent_file.write_text(
            f"---\nname: test-agent\n---\nRun `./scripts/{script_name}` to deploy.\n",
            encoding="utf-8",
        )
        if create_script:
            script = tmp_path / "scripts" / script_name
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/bash\necho deploy\n", encoding="utf-8")

        detector = DriftDetector()
        reports = detector.detect(tmp_path)

        if expect_stale:
            assert any(
                r.drift_type == "stale" and script_name in r.details for r in reports
            )
        else:
            assert len(reports) == 0

    def test_detect_empty_repo_no_drift(self, tmp_path: Path) -> None:
        detector = DriftDetector()
        reports = detector.detect(tmp_path)
        assert reports == []


class TestCIReporter:
    def _passing_result(self) -> CIResult:
        return _make_ci_result(
            overall_score=82.0,
            security_grade="B",
            passed=True,
            asset_results=[
                _make_asset_result("test-runner", "agent", 82.0),
            ],
        )

    def _failing_result(self) -> CIResult:
        assets = [_make_asset_result("add-feature", "skill", 55.0)]
        assets[0]["passed"] = False
        return _make_ci_result(
            overall_score=55.0,
            security_grade="C",
            passed=False,
            asset_results=assets,
            suggestions=[
                "Regenerate add-feature (skill): score 55/100 \u2014 below threshold"
            ],
            exit_code=1,
        )

    @pytest.mark.parametrize(
        ("use_passing", "expected_strings"),
        [
            pytest.param(
                True,
                ["AgentGuard Asset Quality Check", "82", "test-runner", "\u2713"],
                id="passing",
            ),
            pytest.param(
                False,
                ["add-feature", "55", "\u2717", "below threshold"],
                id="failing",
            ),
        ],
    )
    def test_format_check_output(
        self, use_passing: bool, expected_strings: list[str]
    ) -> None:
        reporter = CIReporter()
        result = self._passing_result() if use_passing else self._failing_result()
        output = reporter.format_check_output(result)
        for s in expected_strings:
            assert s in output

    def test_format_check_output_with_drift(self) -> None:
        reporter = CIReporter()
        result = _make_ci_result(
            drift_reports=[
                {
                    "asset_path": ".claude/agents/test.md",
                    "asset_type": "agent",
                    "drift_type": "stale",
                    "details": "references removed file ./scripts/old.sh",
                    "severity": "warning",
                }
            ]
        )
        output = reporter.format_check_output(result)
        assert "Drift" in output
        assert "old.sh" in output

    def test_format_pr_comment_passing(self) -> None:
        reporter = CIReporter()
        result = self._passing_result()
        comment = reporter.format_pr_comment(result)

        assert "## " in comment
        assert "| Asset |" in comment
        assert "| Type |" in comment
        assert "test-runner" in comment
        assert "agent" in comment
        assert "82" in comment
        assert "Security" in comment
        assert "B" in comment

    def test_format_pr_comment_contains_suggestions(self) -> None:
        reporter = CIReporter()
        result = self._failing_result()
        comment = reporter.format_pr_comment(result)

        assert "Suggestions" in comment
        assert "add-feature" in comment

    @pytest.mark.parametrize(
        ("use_passing", "expected_count"),
        [
            pytest.param(True, 0, id="passing_empty"),
            pytest.param(False, 1, id="failing_has_annotations"),
        ],
    )
    def test_format_github_annotations(
        self, use_passing: bool, expected_count: int
    ) -> None:
        reporter = CIReporter()
        result = self._passing_result() if use_passing else self._failing_result()
        annotations = reporter.format_github_annotations(result)

        assert len(annotations) == expected_count
        if expected_count == 1:
            ann = annotations[0]
            assert ann["level"] == "error"
            assert "add-feature" in ann["message"]
            assert "55" in ann["message"]
            assert "below threshold" in ann["message"]

    def test_format_pr_comment_drift_section(self) -> None:
        reporter = CIReporter()
        result = _make_ci_result(
            drift_reports=[
                {
                    "asset_path": ".claude/agents/test.md",
                    "asset_type": "agent",
                    "drift_type": "stale",
                    "details": "references removed file ./gone.sh",
                    "severity": "warning",
                }
            ]
        )
        comment = reporter.format_pr_comment(result)
        assert "Drift Detected" in comment
        assert "gone.sh" in comment


class TestCIRunner:
    def test_runner_check_mode_empty_repo(self, tmp_path: Path) -> None:
        config = CIConfig(repo_path=tmp_path, mode=CIMode.CHECK)
        result = CIRunner().run(config)

        assert result.overall_score == abs(0.0)
        assert result.exit_code == 0
        assert result.asset_results == []

    @pytest.mark.parametrize(
        ("name", "asset_type", "score", "expect_passed", "expect_exit"),
        [
            pytest.param("good-agent", "agent", 80.0, True, 0, id="passing"),
            pytest.param("bad-skill", "skill", 40.0, False, 1, id="failing"),
        ],
    )
    def test_runner_check_mode(
        self,
        tmp_path: Path,
        name: str,
        asset_type: str,
        score: float,
        expect_passed: bool,
        expect_exit: int,
    ) -> None:
        assets = [_make_asset_result(name, asset_type, score, threshold=60.0)]
        if not expect_passed:
            assets[0]["passed"] = False
        with patch(
            "agentguard.ci.runner.CIRunner._evaluate_assets", return_value=assets
        ):
            config = CIConfig(repo_path=tmp_path, mode=CIMode.CHECK, threshold=60.0)
            result = CIRunner().run(config)

        assert result.passed is expect_passed
        assert result.exit_code == expect_exit
        if expect_passed:
            assert result.overall_score == pytest.approx(score)

    def test_runner_autofix_returns_empty_without_creation(
        self, tmp_path: Path
    ) -> None:
        assets = [_make_asset_result("bad-agent", "agent", 40.0, threshold=60.0)]
        assets[0]["passed"] = False

        with (
            patch(
                "agentguard.ci.runner.CIRunner._evaluate_assets",
                return_value=assets,
            ),
            patch("agentguard.ci.runner.CIRunner._run_security", return_value="A"),
            patch("agentguard.ci.runner.CIRunner._run_drift", return_value=[]),
        ):
            config = CIConfig(
                repo_path=tmp_path,
                mode=CIMode.AUTO_FIX,
                threshold=60.0,
                security=False,
            )
            result = CIRunner().run(config)

        assert len(result.fixes_applied) == 0

    def test_runner_suggest_mode_returns_result(self, tmp_path: Path) -> None:
        assets = [_make_asset_result("suggest-agent", "agent", 70.0)]
        with (
            patch(
                "agentguard.ci.runner.CIRunner._evaluate_assets",
                return_value=assets,
            ),
            patch("agentguard.ci.runner.CIRunner._run_security", return_value="B"),
            patch("agentguard.ci.runner.CIRunner._run_drift", return_value=[]),
        ):
            config = CIConfig(repo_path=tmp_path, mode=CIMode.SUGGEST, threshold=60.0)
            result = CIRunner().run(config)

        assert result.overall_score == pytest.approx(70.0)
        assert result.security_grade == "B"
        assert result.exit_code == 0

    @pytest.mark.parametrize(
        ("security", "mock_grade", "expect_exit", "expect_grade"),
        [
            pytest.param(False, None, 0, "A", id="disabled"),
            pytest.param(True, "F", 2, "F", id="grade_f"),
        ],
    )
    def test_runner_security_handling(
        self,
        tmp_path: Path,
        security: bool,
        mock_grade: str | None,
        expect_exit: int,
        expect_grade: str,
    ) -> None:
        assets = [_make_asset_result("agent", "agent", 80.0)]
        mocks: dict[str, Any] = {
            "agentguard.ci.runner.CIRunner._evaluate_assets": assets,
            "agentguard.ci.runner.CIRunner._run_drift": [],
        }
        if mock_grade is not None:
            mocks["agentguard.ci.runner.CIRunner._run_security"] = mock_grade

        with ExitStack() as stack:
            for target, rv in mocks.items():
                stack.enter_context(patch(target, return_value=rv))
            config = CIConfig(
                repo_path=tmp_path,
                mode=CIMode.CHECK,
                security=security,
                threshold=60.0,
            )
            result = CIRunner().run(config)

        assert result.exit_code == expect_exit
        assert result.security_grade == expect_grade
        if expect_exit == 2:
            assert result.passed is False


class TestCLI:
    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture()
    def cli_app(self) -> Any:
        from agentguard.cli import cli

        return cli

    @pytest.mark.parametrize(
        ("command", "expected_words"),
        [
            pytest.param(["ci", "--help"], ["mode", "threshold"], id="ci"),
            pytest.param(["drift", "--help"], ["repo"], id="drift"),
        ],
    )
    def test_help_output(
        self,
        runner: CliRunner,
        cli_app: Any,
        command: list[str],
        expected_words: list[str],
    ) -> None:
        result = runner.invoke(cli_app, command)
        assert result.exit_code == 0
        for word in expected_words:
            assert word in result.output.lower()

    @pytest.mark.parametrize(
        ("overall_score", "passed", "exit_code"),
        [
            pytest.param(80.0, True, 0, id="pass"),
            pytest.param(40.0, False, 1, id="fail"),
        ],
    )
    def test_cli_ci_exit_code(
        self,
        runner: CliRunner,
        cli_app: Any,
        tmp_path: Path,
        overall_score: float,
        passed: bool,
        exit_code: int,
    ) -> None:
        mock_result = _make_ci_result(
            overall_score=overall_score, passed=passed, exit_code=exit_code
        )
        with patch("agentguard.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                ["ci", "--repo", str(tmp_path), "--no-security"],
            )
        assert result.exit_code == exit_code

    def test_cli_ci_suggest_mode(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        mock_result = _make_ci_result(overall_score=75.0, exit_code=0)
        with patch("agentguard.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                [
                    "ci",
                    "--mode",
                    "suggest",
                    "--repo",
                    str(tmp_path),
                    "--no-security",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "AgentGuard" in result.output

    def test_cli_ci_json_output(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        import json

        mock_result = _make_ci_result(overall_score=80.0, exit_code=0)
        with patch("agentguard.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                ["ci", "--repo", str(tmp_path), "--no-security", "--json"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall_score" in data

    def test_cli_drift_no_drift(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        with patch("agentguard.ci.drift.DriftDetector.detect", return_value=[]):
            result = runner.invoke(
                cli_app,
                ["drift", "--repo", str(tmp_path)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "No drift" in result.output

    def test_cli_drift_reports_found(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        reports = [
            DriftReport(
                asset_path=".claude/agents/old.md",
                asset_type="agent",
                drift_type="stale",
                details="references removed file ./gone.sh",
                severity="warning",
            )
        ]
        with patch("agentguard.ci.drift.DriftDetector.detect", return_value=reports):
            result = runner.invoke(
                cli_app,
                ["drift", "--repo", str(tmp_path)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "stale" in result.output.lower()
        assert "gone.sh" in result.output
