from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from reagent.ci.drift import DriftDetector, DriftReport
from reagent.ci.reporter import CIReporter
from reagent.ci.runner import (
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
    passed = score == 0.0 or score >= threshold
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


def _make_quality_report(metrics: list[MagicMock]) -> MagicMock:
    report = MagicMock()
    report.asset_metrics = metrics
    return report


def _make_scan_report() -> MagicMock:
    report = MagicMock()
    report.risk_score = 0.0
    return report


class TestCIResult:
    def test_ci_result_passed_when_all_above_threshold(self) -> None:
        assets = [_make_asset_result(score=80.0, threshold=60.0)]
        result = _make_ci_result(overall_score=80.0, passed=True, asset_results=assets)
        assert result.passed is True
        assert result.exit_code == 0

    def test_ci_result_fails_when_below_threshold(self) -> None:
        assets = [_make_asset_result(score=40.0, threshold=60.0)]
        assets[0]["passed"] = False
        result = _make_ci_result(
            overall_score=40.0, passed=False, asset_results=assets, exit_code=1
        )
        assert result.passed is False
        assert result.exit_code == 1

    def test_ci_result_exit_code_0_on_pass(self) -> None:
        result = _make_ci_result(passed=True, exit_code=0)
        assert result.exit_code == 0

    def test_ci_result_exit_code_1_on_quality_fail(self) -> None:
        result = _make_ci_result(passed=False, exit_code=1)
        assert result.exit_code == 1

    def test_ci_result_exit_code_2_on_security_fail(self) -> None:
        result = _make_ci_result(passed=False, security_grade="F", exit_code=2)
        assert result.exit_code == 2

    def test_exit_code_2_takes_priority_over_1(self) -> None:
        # Security grade F and quality failure → exit code 2
        assets = [_make_asset_result(score=40.0, threshold=60.0)]
        assets[0]["passed"] = False
        exit_code = _determine_exit_code(assets, "F", security_enabled=True)
        assert exit_code == 2

    def test_security_grade_passes_c_or_better(self) -> None:
        assert _security_grade_passes("A") is True
        assert _security_grade_passes("B") is True
        assert _security_grade_passes("C") is True
        assert _security_grade_passes("D") is False
        assert _security_grade_passes("F") is False

    def test_compute_overall_score_empty(self) -> None:
        assert _compute_overall_score([]) == 0.0

    def test_compute_overall_score_average(self) -> None:
        assets = [
            _make_asset_result(score=80.0),
            _make_asset_result(score=60.0),
        ]
        assert _compute_overall_score(assets) == pytest.approx(70.0)

    def test_determine_passed_all_ok(self) -> None:
        assets = [_make_asset_result(score=80.0)]
        assert _determine_passed(assets, "A", security_enabled=True) is True

    def test_determine_passed_security_disabled(self) -> None:
        # Even with a bad grade, security disabled → pass
        assets = [_make_asset_result(score=80.0)]
        assert _determine_passed(assets, "F", security_enabled=False) is True

    def test_build_asset_results_zero_score_treated_as_unknown(self) -> None:
        metrics = [_make_asset_metrics(quality_score=0.0)]
        results = _build_asset_results(metrics, threshold=60.0)
        # Score == 0 is treated as "unknown" — should pass (not fail)
        assert results[0]["passed"] is True

    def test_ci_result_exit_code_security_takes_priority(self) -> None:
        """Verify exit code 2 takes priority over exit code 1 on CIResult.

        A result with both quality failure (would be exit code 1) AND security
        grade F must carry exit code 2, demonstrating security takes priority.
        """
        assets = [_make_asset_result(score=40.0, threshold=60.0)]
        assets[0]["passed"] = False
        # _determine_exit_code should return 2 even though quality also fails
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


class TestDriftDetector:
    def test_detect_stale_references_missing_file(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude" / "agents"
        claude_dir.mkdir(parents=True)
        agent_file = claude_dir / "test-agent.md"
        agent_file.write_text(
            "---\nname: test-agent\n---\nRun `./scripts/missing.sh` to deploy.\n",
            encoding="utf-8",
        )
        # Do NOT create scripts/missing.sh

        detector = DriftDetector()
        reports = detector._check_stale(tmp_path)

        assert any(
            r.drift_type == "stale" and "missing.sh" in r.details for r in reports
        )

    def test_detect_no_drift_when_all_refs_exist(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude" / "agents"
        claude_dir.mkdir(parents=True)
        script = tmp_path / "scripts" / "deploy.sh"
        script.parent.mkdir(parents=True)
        script.write_text("#!/bin/bash\necho deploy\n", encoding="utf-8")

        agent_file = claude_dir / "deploy-agent.md"
        agent_file.write_text(
            "---\nname: deploy-agent\n---\nRun `./scripts/deploy.sh` to deploy.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()
        reports = detector._check_stale(tmp_path)
        assert len(reports) == 0

    def test_detect_missing_asset_for_ci_repo(self, tmp_path: Path) -> None:
        # Repo with has_ci=True but no CI agent
        profile = MagicMock()
        profile.has_ci = True
        profile.has_api_routes = False
        profile.test_config.runner = None

        detector = DriftDetector()
        agents_dir = tmp_path / ".claude" / "agents"
        reports = detector._check_missing_ci_asset(profile, agents_dir)

        assert len(reports) == 1
        assert reports[0].drift_type == "missing"
        assert "CI" in reports[0].details or "ci" in reports[0].details.lower()

    def test_detect_config_drift_missing_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ = tmp_path
        # Ensure env var is not set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        config_data = {"llm": {"provider": "anthropic"}}
        with patch("reagent.ci.drift._load_reagent_config", return_value=config_data):
            detector = DriftDetector()
            reports = detector._check_config_drift()

        assert len(reports) == 1
        assert reports[0].drift_type == "config_drift"
        assert "ANTHROPIC_API_KEY" in reports[0].details

    def test_detect_config_drift_no_drift_when_var_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _ = tmp_path
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        config_data = {"llm": {"provider": "anthropic"}}
        with patch("reagent.ci.drift._load_reagent_config", return_value=config_data):
            detector = DriftDetector()
            reports = detector._check_config_drift()

        assert len(reports) == 0

    def test_detect_empty_repo_no_drift(self, tmp_path: Path) -> None:
        detector = DriftDetector()
        # No .claude dir, no config file
        with patch("reagent.ci.drift._load_reagent_config", return_value=None):
            reports = detector.detect(tmp_path)
        # May have missing reports from analyze_repo, but not stale or config
        stale = [r for r in reports if r.drift_type == "stale"]
        config_drift = [r for r in reports if r.drift_type == "config_drift"]
        assert stale == []
        assert config_drift == []

    def test_detect_missing_api_agent(self, tmp_path: Path) -> None:
        profile = MagicMock()
        profile.has_ci = False
        profile.has_api_routes = True
        profile.test_config.runner = None

        agents_dir = tmp_path / ".claude" / "agents"
        detector = DriftDetector()
        reports = detector._check_missing_api_asset(profile, agents_dir)

        assert len(reports) == 1
        assert reports[0].drift_type == "missing"
        assert "API" in reports[0].details or "api" in reports[0].details.lower()

    def test_detect_missing_test_skill(self, tmp_path: Path) -> None:
        profile = MagicMock()
        profile.has_ci = False
        profile.has_api_routes = False
        test_cfg = MagicMock()
        test_cfg.runner = "pytest"
        profile.test_config = test_cfg

        skills_dir = tmp_path / ".claude" / "skills"
        detector = DriftDetector()
        reports = detector._check_missing_test_skill(profile, skills_dir)

        assert len(reports) == 1
        assert reports[0].drift_type == "missing"
        assert "pytest" in reports[0].details

    def test_detect_no_missing_when_ci_agent_exists(self, tmp_path: Path) -> None:
        profile = MagicMock()
        profile.has_ci = True
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "ci-agent.md").write_text("# CI Agent\n", encoding="utf-8")

        detector = DriftDetector()
        reports = detector._check_missing_ci_asset(profile, agents_dir)
        assert len(reports) == 0

    def test_drift_detector_reports_stale_asset(self, tmp_path: Path) -> None:
        """Verify drift is detected when an asset references a non-existent file."""
        claude_dir = tmp_path / ".claude" / "agents"
        claude_dir.mkdir(parents=True)
        agent_file = claude_dir / "broken-agent.md"
        agent_file.write_text(
            "---\nname: broken-agent\n---\nRun `./scripts/gone.sh` for setup.\n",
            encoding="utf-8",
        )
        # scripts/gone.sh does NOT exist → stale reference

        detector = DriftDetector()
        reports = detector._check_stale(tmp_path)

        stale = [r for r in reports if r.drift_type == "stale"]
        assert len(stale) >= 1, "Expected at least one stale-reference report"
        assert any("gone.sh" in r.details for r in stale)


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

    def test_format_check_output_passing(self) -> None:
        reporter = CIReporter()
        result = self._passing_result()
        output = reporter.format_check_output(result)

        assert "Reagent Asset Quality Check" in output
        assert "82" in output
        assert "test-runner" in output
        assert "\u2713" in output  # checkmark

    def test_format_check_output_failing(self) -> None:
        reporter = CIReporter()
        result = self._failing_result()
        output = reporter.format_check_output(result)

        assert "add-feature" in output
        assert "55" in output
        assert "\u2717" in output  # cross
        assert "below threshold" in output

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

    def test_format_pr_comment_contains_table(self) -> None:
        reporter = CIReporter()
        result = self._passing_result()
        comment = reporter.format_pr_comment(result)

        assert "## " in comment
        assert "| Asset |" in comment
        assert "| Type |" in comment
        assert "test-runner" in comment
        assert "agent" in comment

    def test_format_pr_comment_contains_suggestions(self) -> None:
        reporter = CIReporter()
        result = self._failing_result()
        comment = reporter.format_pr_comment(result)

        assert "Suggestions" in comment
        assert "add-feature" in comment

    def test_format_pr_comment_overall_score(self) -> None:
        reporter = CIReporter()
        result = self._passing_result()
        comment = reporter.format_pr_comment(result)

        assert "82" in comment
        assert "Security" in comment
        assert "B" in comment

    def test_format_github_annotations_failing(self) -> None:
        reporter = CIReporter()
        result = self._failing_result()
        annotations = reporter.format_github_annotations(result)

        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["level"] == "error"
        assert "add-feature" in ann["message"]
        assert "55" in ann["message"]
        assert "below threshold" in ann["message"]

    def test_format_github_annotations_empty_when_passing(self) -> None:
        reporter = CIReporter()
        result = self._passing_result()
        annotations = reporter.format_github_annotations(result)

        assert annotations == []

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
        """Runner returns a passing result when the repo contains no assets.

        Uses a real empty directory — no mocks needed because evaluate_repo
        returns an empty report for an uncatalogued repo, scan_directory finds
        nothing to flag, and DriftDetector finds no .claude directory.
        """
        config = CIConfig(repo_path=tmp_path, mode=CIMode.CHECK)
        result = CIRunner().run(config)

        assert result.overall_score == 0.0
        assert result.exit_code == 0
        assert result.asset_results == []

    def test_runner_check_mode_passing(self, tmp_path: Path) -> None:
        """Runner reports pass when evaluated assets are all above threshold.

        Only _evaluate_assets is mocked (the heavy catalog+LLM evaluation);
        security and drift run for real on the empty tmp_path and return clean
        results naturally.
        """
        assets = [_make_asset_result("good-agent", "agent", 80.0)]
        with patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets):
            config = CIConfig(repo_path=tmp_path, mode=CIMode.CHECK, threshold=60.0)
            result = CIRunner().run(config)

        assert result.passed is True
        assert result.exit_code == 0
        assert result.overall_score == pytest.approx(80.0)

    def test_runner_check_mode_failing(self, tmp_path: Path) -> None:
        """Runner reports failure when an asset is below threshold.

        Only _evaluate_assets is mocked; security and drift use real empty-dir
        implementations (both return clean results on tmp_path).
        """
        assets = [_make_asset_result("bad-skill", "skill", 40.0, threshold=60.0)]
        assets[0]["passed"] = False
        with patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets):
            config = CIConfig(repo_path=tmp_path, mode=CIMode.CHECK, threshold=60.0)
            result = CIRunner().run(config)

        assert result.passed is False
        assert result.exit_code == 1

    def test_runner_autofix_writes_files(self, tmp_path: Path) -> None:
        # Create a real asset file to auto-fix
        claude_dir = tmp_path / ".claude" / "agents"
        claude_dir.mkdir(parents=True)
        agent_file = claude_dir / "bad-agent.md"
        agent_file.write_text(
            "---\nname: bad-agent\n---\nOld content.\n", encoding="utf-8"
        )

        assets = [_make_asset_result("bad-agent", "agent", 40.0, threshold=60.0)]
        assets[0]["passed"] = False

        mock_draft = MagicMock()
        mock_draft.content = "---\nname: bad-agent\n---\nImproved content.\n"
        mock_draft.target_path = agent_file

        with (
            patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets),
            patch("reagent.ci.runner.CIRunner._run_security", return_value="A"),
            patch("reagent.ci.runner.CIRunner._run_drift", return_value=[]),
            patch("reagent.creation.creator.regenerate_asset", return_value=mock_draft),
        ):
            config = CIConfig(
                repo_path=tmp_path,
                mode=CIMode.AUTO_FIX,
                threshold=60.0,
                security=False,
            )
            result = CIRunner().run(config)

        assert len(result.fixes_applied) == 1
        assert "bad-agent.md" in result.fixes_applied[0]
        assert agent_file.read_text(encoding="utf-8") == mock_draft.content

    def test_runner_suggest_mode_returns_result(self, tmp_path: Path) -> None:
        assets = [_make_asset_result("suggest-agent", "agent", 70.0)]
        with (
            patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets),
            patch("reagent.ci.runner.CIRunner._run_security", return_value="B"),
            patch("reagent.ci.runner.CIRunner._run_drift", return_value=[]),
        ):
            config = CIConfig(repo_path=tmp_path, mode=CIMode.SUGGEST, threshold=60.0)
            result = CIRunner().run(config)

        assert result.overall_score == pytest.approx(70.0)
        assert result.security_grade == "B"
        assert result.exit_code == 0

    def test_runner_security_disabled(self, tmp_path: Path) -> None:
        assets = [_make_asset_result("agent", "agent", 80.0)]
        with (
            patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets),
            patch("reagent.ci.runner.CIRunner._run_drift", return_value=[]),
        ):
            config = CIConfig(
                repo_path=tmp_path,
                mode=CIMode.CHECK,
                security=False,
                threshold=60.0,
            )
            result = CIRunner().run(config)

        assert result.exit_code == 0
        # Security grade defaults to A when disabled
        assert result.security_grade == "A"

    def test_runner_security_grade_f_exits_2(self, tmp_path: Path) -> None:
        assets = [_make_asset_result("agent", "agent", 80.0)]
        with (
            patch("reagent.ci.runner.CIRunner._evaluate_assets", return_value=assets),
            patch("reagent.ci.runner.CIRunner._run_security", return_value="F"),
            patch("reagent.ci.runner.CIRunner._run_drift", return_value=[]),
        ):
            config = CIConfig(
                repo_path=tmp_path,
                mode=CIMode.CHECK,
                security=True,
                threshold=60.0,
            )
            result = CIRunner().run(config)

        assert result.exit_code == 2
        assert result.passed is False


class TestCLI:
    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture()
    def cli_app(self) -> Any:
        from reagent.cli import cli

        return cli

    def test_cli_ci_help(self, runner: CliRunner, cli_app: Any) -> None:
        result = runner.invoke(cli_app, ["ci", "--help"])
        assert result.exit_code == 0
        assert "mode" in result.output.lower()
        assert "threshold" in result.output.lower()

    def test_cli_drift_help(self, runner: CliRunner, cli_app: Any) -> None:
        result = runner.invoke(cli_app, ["drift", "--help"])
        assert result.exit_code == 0
        assert "repo" in result.output.lower()

    def test_cli_ci_exits_0_on_pass(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        mock_result = _make_ci_result(overall_score=80.0, passed=True, exit_code=0)
        with patch("reagent.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                ["ci", "--repo", str(tmp_path), "--no-security"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0

    def test_cli_ci_exits_1_on_fail(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        mock_result = _make_ci_result(overall_score=40.0, passed=False, exit_code=1)
        with patch("reagent.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                ["ci", "--repo", str(tmp_path), "--no-security"],
            )
        assert result.exit_code == 1

    def test_cli_ci_suggest_mode(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        mock_result = _make_ci_result(overall_score=75.0, exit_code=0)
        with patch("reagent.ci.runner.CIRunner.run", return_value=mock_result):
            result = runner.invoke(
                cli_app,
                ["ci", "--mode", "suggest", "--repo", str(tmp_path), "--no-security"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "Reagent" in result.output

    def test_cli_ci_json_output(
        self, runner: CliRunner, cli_app: Any, tmp_path: Path
    ) -> None:
        import json

        mock_result = _make_ci_result(overall_score=80.0, exit_code=0)
        with patch("reagent.ci.runner.CIRunner.run", return_value=mock_result):
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
        with patch("reagent.ci.drift.DriftDetector.detect", return_value=[]):
            result = runner.invoke(
                cli_app, ["drift", "--repo", str(tmp_path)], catch_exceptions=False
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
        with patch("reagent.ci.drift.DriftDetector.detect", return_value=reports):
            result = runner.invoke(
                cli_app, ["drift", "--repo", str(tmp_path)], catch_exceptions=False
            )
        assert result.exit_code == 0
        assert "stale" in result.output.lower()
        assert "gone.sh" in result.output
