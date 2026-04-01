from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from reagent.loops.guardrails import GuardrailChecker, LoopConfig
from reagent.loops.state import ApprovalQueue, LoopState, PendingAsset


def _make_pending(
    loop_id: str = "loop-1",
    asset_type: str = "agent",
    asset_name: str = "test-agent",
    file_path: str = "/fake/test-agent.md",
    new_score: float = 75.0,
    _db_path: Path | None = None,
) -> PendingAsset:
    return PendingAsset(
        asset_type=asset_type,
        asset_name=asset_name,
        file_path=file_path,
        content="---\nname: test-agent\n---\nDo things.\n",
        previous_content=None,
        previous_score=None,
        new_score=new_score,
        generation_method="enhanced_template",
        loop_id=loop_id,
        iteration=1,
    )


class TestGuardrailIterationLimit:
    @pytest.mark.parametrize(
        "current,limit,expected,reason_pattern",
        [
            (3, 5, True, None),  # within limit
            (5, 5, True, None),  # at limit — 5th iteration allowed
            (6, 5, False, "5"),  # over limit
        ],
    )
    def test_iteration_limit(
        self,
        current: int,
        limit: int,
        expected: bool,
        reason_pattern: str | None,
    ) -> None:
        checker = GuardrailChecker()
        result = checker.check_iteration_limit(current, limit)
        assert result.passed is expected
        if reason_pattern is not None:
            assert result.reason is not None
            assert reason_pattern in result.reason
        else:
            assert result.reason is None


class TestGuardrailCostLimit:
    @pytest.mark.parametrize(
        "cost,limit,expected,reason_pattern",
        [
            (1.99, 2.0, True, None),  # under limit
            (2.0, 2.0, False, None),  # at limit
            (3.50, 2.0, False, "$3.50"),  # over limit
        ],
    )
    def test_cost_limit(
        self,
        cost: float,
        limit: float,
        expected: bool,
        reason_pattern: str | None,
    ) -> None:
        checker = GuardrailChecker()
        result = checker.check_cost_limit(cost, limit)
        assert result.passed is expected
        if reason_pattern is not None:
            assert reason_pattern in (result.reason or "")


class TestGuardrailKillSwitch:
    @pytest.mark.parametrize(
        "active,expected,reason_pattern",
        [
            (False, True, None),  # not set
            (True, False, "Kill switch"),  # set
        ],
    )
    def test_kill_switch(
        self,
        active: bool,
        expected: bool,
        reason_pattern: str | None,
    ) -> None:
        checker = GuardrailChecker()
        result = checker.check_kill_switch(active)
        assert result.passed is expected
        if reason_pattern is not None:
            assert reason_pattern in (result.reason or "")


class TestGuardrailImprovement:
    @pytest.mark.parametrize(
        "prev,curr,min_delta,expected,reason_pattern",
        [
            (0.0, 50.0, 5.0, True, None),  # no prior score
            (60.0, 70.0, 5.0, True, None),  # sufficient improvement
            (60.0, 63.0, 5.0, False, None),  # insufficient improvement
            (60.0, 60.0, 5.0, False, None),  # no improvement
            (70.0, 70.0, 5.0, False, "70.0"),  # identical scores — loop stops
        ],
    )
    def test_check_improvement(
        self,
        prev: float,
        curr: float,
        min_delta: float,
        expected: bool,
        reason_pattern: str | None,
    ) -> None:
        checker = GuardrailChecker()
        result = checker.check_improvement(prev, curr, min_delta)
        assert result.passed is expected
        if reason_pattern is not None:
            assert result.reason is not None
            assert reason_pattern in result.reason


class TestGuardrailCheckAll:
    def test_all_pass(self) -> None:
        checker = GuardrailChecker()
        cfg = LoopConfig(max_iterations=5, max_cost_usd=2.0, min_improvement=5.0)
        result = checker.check_all(1, cfg, 0.0, 75.0, 0.10)
        assert result.passed is True

    def test_fails_on_cost(self) -> None:
        checker = GuardrailChecker()
        cfg = LoopConfig(max_iterations=5, max_cost_usd=1.0)
        result = checker.check_all(1, cfg, 0.0, 75.0, 1.50)
        assert result.passed is False
        assert "Cost" in (result.reason or "")

    def test_fails_on_iteration(self) -> None:
        checker = GuardrailChecker()
        cfg = LoopConfig(max_iterations=3)
        result = checker.check_all(4, cfg, 0.0, 75.0, 0.01)
        assert result.passed is False
        assert "Iteration" in (result.reason or "")

    def test_kill_switch_takes_priority(self) -> None:
        checker = GuardrailChecker()
        cfg = LoopConfig(kill_switch=True, max_iterations=100, max_cost_usd=100.0)
        result = checker.check_all(1, cfg, 0.0, 75.0, 0.01)
        assert result.passed is False
        assert "Kill switch" in (result.reason or "")


class TestLoopState:
    def test_defaults(self) -> None:
        state = LoopState(loop_type="init", repo_path="/repo")
        assert state.iteration == 0
        assert state.total_cost == 0.0
        assert state.status == "running"
        assert state.stop_reason is None
        assert isinstance(state.loop_id, str)
        assert len(state.loop_id) == 36  # UUID format

    def test_serialization(self) -> None:
        state = LoopState(loop_type="improve", repo_path="/project")
        data = state.model_dump()
        restored = LoopState.model_validate(data)
        assert restored.loop_id == state.loop_id
        assert restored.loop_type == state.loop_type

    def test_started_at_is_utc(self) -> None:
        state = LoopState(loop_type="watch", repo_path="/x")
        assert state.started_at.tzinfo is not None

    def test_loop_state_persists_across_iterations(self) -> None:
        """Verify LoopState scores list grows with each iteration."""
        state = LoopState(loop_type="improve", repo_path="/repo")
        assert state.scores == []

        state.scores.append(60.0)
        state.scores.append(70.0)
        state.scores.append(80.0)

        assert len(state.scores) == 3
        assert state.scores[0] == pytest.approx(60.0)
        assert state.scores[1] == pytest.approx(70.0)
        assert state.scores[2] == pytest.approx(80.0)


class TestPendingAssetModel:
    def test_defaults(self) -> None:
        asset = _make_pending()
        assert asset.status == "pending"
        assert isinstance(asset.pending_id, str)
        assert asset.previous_content is None

    def test_score_stored(self) -> None:
        asset = _make_pending(new_score=82.5)
        assert asset.new_score == 82.5

    def test_created_at_is_utc(self) -> None:
        asset = _make_pending()
        assert asset.created_at.tzinfo is not None


class TestApprovalQueue:
    def test_add_returns_pending_id(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        asset = _make_pending()
        returned_id = queue.add(asset)
        assert returned_id == asset.pending_id

    def test_list_pending_empty(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        assert queue.list_pending() == []

    def test_list_pending_after_add(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        asset = _make_pending(asset_name="my-agent")
        queue.add(asset)
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].asset_name == "my-agent"

    def test_approved_not_in_pending(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        asset = _make_pending()
        queue.add(asset)
        queue.approve(asset.pending_id)
        assert queue.list_pending() == []

    def test_rejected_not_in_pending(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        asset = _make_pending()
        queue.add(asset)
        queue.reject(asset.pending_id)
        assert queue.list_pending() == []

    def test_approve_all(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        for i in range(3):
            queue.add(_make_pending(asset_name=f"agent-{i}"))
        count = queue.approve_all()
        assert count == 3
        assert queue.list_pending() == []

    def test_get_returns_asset(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        asset = _make_pending(asset_name="specific")
        queue.add(asset)
        fetched = queue.get(asset.pending_id)
        assert fetched is not None
        assert fetched.asset_name == "specific"

    def test_get_unknown_returns_none(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        assert queue.get("nonexistent-id") is None

    def test_reject_individual(self, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "test.db")
        a1 = _make_pending(asset_name="keep")
        a2 = _make_pending(asset_name="discard")
        queue.add(a1)
        queue.add(a2)
        queue.reject(a2.pending_id)
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].asset_name == "keep"

    def test_approval_queue_number_addressing(self, tmp_path: Path) -> None:
        """Verify pending assets can be addressed by row number (1-based)."""
        from reagent.cli import _resolve_pending_by_id

        queue = ApprovalQueue(tmp_path / "num.db")
        queue.add(_make_pending(asset_name="first"))
        queue.add(_make_pending(asset_name="second"))
        queue.add(_make_pending(asset_name="third"))

        # Row number 2 should resolve to the second-added asset
        result = _resolve_pending_by_id(queue, ("2",))
        assert len(result) == 1
        assert result[0].asset_name == "second"  # type: ignore[union-attr]


class TestMigrationV2:
    def test_creates_loops_table(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "m.db")
        conn = db.connect()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "loops" in tables

    def test_creates_pending_assets_table(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "m.db")
        conn = db.connect()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "pending_assets" in tables

    def test_schema_version_is_current(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB
        from reagent.storage.migrations import CURRENT_VERSION

        db = ReagentDB(tmp_path / "v.db")
        conn = db.connect()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_VERSION

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB
        from reagent.storage.migrations import CURRENT_VERSION, apply_migrations

        db = ReagentDB(tmp_path / "idem.db")
        conn = db.connect()
        # Run again — should not raise
        apply_migrations(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == CURRENT_VERSION

    def test_loops_table_columns(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "cols.db")
        conn = db.connect()
        info = conn.execute("PRAGMA table_info(loops)").fetchall()
        col_names = {row[1] for row in info}
        assert {"loop_id", "loop_type", "repo_path", "status", "iteration"}.issubset(
            col_names
        )

    def test_pending_assets_table_columns(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "cols2.db")
        conn = db.connect()
        info = conn.execute("PRAGMA table_info(pending_assets)").fetchall()
        col_names = {row[1] for row in info}
        assert {
            "pending_id",
            "asset_type",
            "asset_name",
            "content",
            "new_score",
            "status",
        }.issubset(col_names)

    def test_security_scans_table_columns(self, tmp_path: Path) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "scans.db")
        conn = db.connect()
        info = conn.execute("PRAGMA table_info(security_scans)").fetchall()
        col_names = {row[1] for row in info}
        assert {
            "scan_id",
            "asset_path",
            "repo_path",
            "findings_json",
            "finding_count",
            "scanned_at",
        }.issubset(col_names)


class TestLoopControllerStop:
    def test_stop_sets_kill_switch(self, tmp_path: Path) -> None:
        from reagent.loops import LoopController

        ctrl = LoopController(db_path=tmp_path / "s.db")
        assert ctrl._kill_switch is False
        ctrl.stop()
        assert ctrl._kill_switch is True

    def test_stop_writes_signal_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import reagent.loops.controller as ctrl_mod
        from reagent.loops import LoopController

        monkeypatch.setattr(ctrl_mod, "_STOP_DIR", tmp_path)
        ctrl = LoopController(db_path=tmp_path / "s.db")
        ctrl.stop()
        signal_file = tmp_path / f"{ctrl_mod._STOP_FILE_PREFIX}signal"
        assert signal_file.exists()


class TestLoopControllerInitEmptyRepo:
    def test_init_no_plan_returns_result(self, tmp_path: Path, mocker: Any) -> None:
        # Patch analyze_repo to return minimal profile
        from reagent.intelligence.analyzer import RepoProfile
        from reagent.loops import LoopConfig, LoopController

        mock_profile = RepoProfile(repo_path=str(tmp_path), repo_name="test")
        mocker.patch(
            "reagent.loops.controller.analyze_repo",
            return_value=mock_profile,
        )
        # With no detected plan items (no language detected), loop ends quickly
        mocker.patch(
            "reagent.loops.controller._detect_asset_plan",
            return_value=[],
        )

        ctrl = LoopController(db_path=tmp_path / "db.db")
        cfg = LoopConfig(max_iterations=2, cooldown_seconds=0.0)
        result = ctrl.run_init(tmp_path, cfg)

        assert result.loop_type == "init"
        assert result.iterations == 0 or result.assets_generated == 0


class TestLoopControllerImproveNoAssets:
    def test_improve_no_assets_returns_immediately(
        self, tmp_path: Path, mocker: Any
    ) -> None:
        from reagent.loops import LoopConfig, LoopController

        mocker.patch(
            "reagent.loops.controller._find_existing_assets",
            return_value=[],
        )

        ctrl = LoopController(db_path=tmp_path / "db.db")
        cfg = LoopConfig(max_iterations=3, cooldown_seconds=0.0)
        result = ctrl.run_improve(tmp_path, cfg)

        assert result.loop_type == "improve"
        assert result.assets_generated == 0


_VALID_AGENT_CONTENT = (
    "---\n"
    "name: test-agent\n"
    "description: A test agent for unit testing.\n"
    "---\n\n"
    "## Role\n\nHandles testing tasks.\n\n"
    "## Usage\n\nInvoke to run tests.\n"
)


class TestLoopControllerCostGuardrail:
    def test_cost_guardrail_stops_loop(self, tmp_path: Path, mocker: Any) -> None:
        from reagent.creation.creator import AssetDraft
        from reagent.intelligence.analyzer import RepoProfile
        from reagent.loops import LoopConfig, LoopController

        mock_profile = RepoProfile(repo_path=str(tmp_path), repo_name="test")
        mocker.patch(
            "reagent.loops.controller.analyze_repo",
            return_value=mock_profile,
        )
        # Plan one asset per iteration
        mocker.patch(
            "reagent.loops.controller._detect_asset_plan",
            return_value=[("agent", "test-agent")],
        )

        real_draft = AssetDraft(
            asset_type="agent",
            name="test-agent",
            content=_VALID_AGENT_CONTENT,
            target_path=tmp_path / "test-agent.md",
            origin="reagent-create-template",
        )
        mocker.patch("reagent.creation.creator.create_asset", return_value=real_draft)

        # Set max_cost to 0 so it trips on first iteration
        ctrl = LoopController(db_path=tmp_path / "db.db")
        cfg = LoopConfig(
            max_iterations=10,
            max_cost_usd=0.0,
            cooldown_seconds=0.0,
            min_improvement=0.0,
        )
        result = ctrl.run_init(tmp_path, cfg)
        assert result.stop_reason is not None
        assert "Cost" in result.stop_reason


class TestLoopControllerIterationGuardrail:
    def test_iteration_guardrail_stops_loop(self, tmp_path: Path, mocker: Any) -> None:
        from reagent.creation.creator import AssetDraft
        from reagent.intelligence.analyzer import RepoProfile
        from reagent.loops import LoopConfig, LoopController

        mock_profile = RepoProfile(repo_path=str(tmp_path), repo_name="test")
        mocker.patch(
            "reagent.loops.controller.analyze_repo",
            return_value=mock_profile,
        )
        mocker.patch(
            "reagent.loops.controller._detect_asset_plan",
            return_value=[("agent", "test-agent")],
        )

        real_draft = AssetDraft(
            asset_type="agent",
            name="test-agent",
            content=_VALID_AGENT_CONTENT,
            target_path=tmp_path / "test-agent.md",
            origin="reagent-create-template",
        )
        mocker.patch("reagent.creation.creator.create_asset", return_value=real_draft)

        ctrl = LoopController(db_path=tmp_path / "db.db")
        cfg = LoopConfig(
            max_iterations=1,
            max_cost_usd=100.0,
            cooldown_seconds=0.0,
            min_improvement=0.0,
            target_score=100.0,  # Never reached
        )
        result = ctrl.run_init(tmp_path, cfg)
        # After 1 iteration, next check would trip iteration limit
        assert result.iterations >= 1


class TestQualityGates:
    def test_schema_gate_fails_missing_description(self) -> None:
        from reagent.loops.controller import _run_quality_gates
        from reagent.loops.state import PendingAsset

        asset = PendingAsset(
            asset_type="agent",
            asset_name="bad-agent",
            file_path="/fake/bad-agent.md",
            content="---\nname: bad-agent\n---\nNo description.\n",
            new_score=50.0,
            generation_method="template",
            loop_id="loop-1",
            iteration=1,
        )
        result = _run_quality_gates([asset])
        assert not result.passed
        assert "Schema validation failed" in (result.reason or "")

    def test_schema_gate_passes_valid_agent(self) -> None:
        from reagent.loops.controller import _run_quality_gates
        from reagent.loops.state import PendingAsset

        asset = PendingAsset(
            asset_type="agent",
            asset_name="good-agent",
            file_path="/fake/good-agent.md",
            content=_VALID_AGENT_CONTENT,
            new_score=70.0,
            generation_method="template",
            loop_id="loop-1",
            iteration=1,
        )
        result = _run_quality_gates([asset])
        assert result.passed

    def test_regression_gate_blocks_score_drop(self) -> None:
        from reagent.loops.controller import _run_quality_gates
        from reagent.loops.state import PendingAsset

        asset = PendingAsset(
            asset_type="agent",
            asset_name="regressed-agent",
            file_path="/fake/regressed-agent.md",
            content=_VALID_AGENT_CONTENT,
            previous_score=80.0,
            new_score=60.0,  # dropped
            generation_method="template",
            loop_id="loop-1",
            iteration=2,
        )
        result = _run_quality_gates([asset])
        assert not result.passed
        assert "Regression" in (result.reason or "")

    def test_regression_gate_passes_when_improved(self) -> None:
        from reagent.loops.controller import _run_quality_gates
        from reagent.loops.state import PendingAsset

        asset = PendingAsset(
            asset_type="agent",
            asset_name="improved-agent",
            file_path="/fake/improved-agent.md",
            content=_VALID_AGENT_CONTENT,
            previous_score=60.0,
            new_score=80.0,
            generation_method="template",
            loop_id="loop-1",
            iteration=2,
        )
        result = _run_quality_gates([asset])
        assert result.passed

    def test_security_gate_blocks_critical_finding(self) -> None:
        from reagent.loops.controller import _run_quality_gates
        from reagent.loops.state import PendingAsset

        # Content that triggers SEC-010 / PERMISSION_ESCALATION (CRITICAL severity)
        dangerous_content = (
            "---\nname: sec-agent\ndescription: Dangerous agent.\n---\n\n"
            "permissionMode: bypassPermissions\n"
        )
        asset = PendingAsset(
            asset_type="agent",
            asset_name="sec-agent",
            file_path="/fake/sec-agent.md",
            content=dangerous_content,
            new_score=50.0,
            generation_method="template",
            loop_id="loop-1",
            iteration=1,
        )
        result = _run_quality_gates([asset])
        # bypassPermissions is CRITICAL → security gate must block
        assert result.passed is False

    def test_empty_asset_list_passes(self) -> None:
        from reagent.loops.controller import _run_quality_gates

        result = _run_quality_gates([])
        assert result.passed


class TestSelectLowestScorers:
    def test_selects_bottom_third(self) -> None:
        from reagent.loops.controller import _select_lowest_scorers
        from reagent.loops.guardrails import LoopConfig

        scores = {
            ("agent", "a"): 30.0,
            ("agent", "b"): 50.0,
            ("agent", "c"): 70.0,
            ("agent", "d"): 90.0,
        }
        cfg = LoopConfig(target_score=80.0)
        result = _select_lowest_scorers(scores, cfg)
        # Bottom third of below-target assets: a(30) and b(50) are below;
        # cutoff = max(1, 2//3) = 1, so only the worst one
        assert len(result) >= 1
        assert ("agent", "a") in result

    def test_returns_at_least_one(self) -> None:
        from reagent.loops.controller import _select_lowest_scorers
        from reagent.loops.guardrails import LoopConfig

        scores = {("agent", "only"): 10.0}
        cfg = LoopConfig(target_score=80.0)
        result = _select_lowest_scorers(scores, cfg)
        assert len(result) == 1

    def test_returns_empty_when_all_above_target(self) -> None:
        from reagent.loops.controller import _select_lowest_scorers
        from reagent.loops.guardrails import LoopConfig

        scores = {("agent", "good"): 90.0}
        cfg = LoopConfig(target_score=80.0)
        result = _select_lowest_scorers(scores, cfg)
        assert result == []


class TestResolveByNumber:
    def test_resolve_by_row_number(self, tmp_path: Path) -> None:
        from reagent.cli import _resolve_pending_by_id
        from reagent.loops.state import ApprovalQueue

        queue = ApprovalQueue(tmp_path / "q.db")
        queue.add(_make_pending(asset_name="first"))
        queue.add(_make_pending(asset_name="second"))

        result = _resolve_pending_by_id(queue, ("2",))
        assert len(result) == 1
        assert result[0].asset_name == "second"  # type: ignore[union-attr]

    def test_resolve_by_uuid(self, tmp_path: Path) -> None:
        from reagent.cli import _resolve_pending_by_id
        from reagent.loops.state import ApprovalQueue

        queue = ApprovalQueue(tmp_path / "q2.db")
        asset = _make_pending(asset_name="by-uuid")
        queue.add(asset)

        result = _resolve_pending_by_id(queue, (asset.pending_id,))
        assert len(result) == 1
        assert result[0].asset_name == "by-uuid"  # type: ignore[union-attr]

    def test_deploy_by_number(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        from reagent.loops.state import ApprovalQueue

        queue = ApprovalQueue(tmp_path / "q3.db")
        queue.add(_make_pending(asset_name="asset-one"))
        queue.add(_make_pending(asset_name="asset-two"))

        with patch("reagent.loops.ApprovalQueue", return_value=queue):
            result = runner.invoke(cli, ["loop", "deploy", "1"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "Deployed" in result.output

    def test_discard_by_number(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        from reagent.loops.state import ApprovalQueue

        queue = ApprovalQueue(tmp_path / "q4.db")
        queue.add(_make_pending(asset_name="to-discard"))

        with patch("reagent.loops.ApprovalQueue", return_value=queue):
            result = runner.invoke(cli, ["loop", "discard", "1"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "Discarded" in result.output


@pytest.fixture()
def runner() -> CliRunner:
    """Return a Click test runner."""
    return CliRunner()


@pytest.fixture()
def cli():  # type: ignore[no-untyped-def]
    """Lazy import of CLI to avoid circular imports when run in isolation."""
    from reagent.cli import cli as _cli

    return _cli


class TestCliLoopStatus:
    def test_no_loops(self, runner: CliRunner, cli: object, tmp_path: Path) -> None:
        _ = tmp_path
        with (
            patch("reagent.storage.ReagentDB.__init__", return_value=None),
            patch("reagent.storage.ReagentDB.connect") as mock_connect,
        ):
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_connect.return_value = mock_conn
            result = runner.invoke(cli, ["loop", "status"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "No loops" in result.output

    def test_shows_loop_info(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "test.db"
        from reagent.storage import ReagentDB

        # Create real DB and insert a loop row
        db = ReagentDB(db_path)
        conn = db.connect()
        conn.execute(
            "INSERT INTO loops VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "test-loop-id",
                "init",
                str(tmp_path),
                "completed",
                None,
                3,
                0.05,
                72.5,
                datetime.now(UTC).isoformat(),
                None,
            ),
        )
        conn.commit()

        with patch("reagent.storage.ReagentDB", return_value=db):
            result = runner.invoke(cli, ["loop", "status"])  # type: ignore[arg-type]

        assert result.exit_code == 0


class TestCliLoopReviewEmpty:
    def test_no_pending(self, runner: CliRunner, cli: object, tmp_path: Path) -> None:
        queue = ApprovalQueue(tmp_path / "q.db")
        with patch("reagent.loops.ApprovalQueue", return_value=queue):
            result = runner.invoke(cli, ["loop", "review"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "No pending" in result.output

    def test_with_pending_items(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        queue = ApprovalQueue(tmp_path / "q2.db")
        queue.add(_make_pending(asset_name="my-agent", new_score=75.0))
        with patch("reagent.loops.ApprovalQueue", return_value=queue):
            result = runner.invoke(cli, ["loop", "review"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "my-agent" in result.output


class TestCliLoopHistory:
    def test_empty_history(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "h.db")
        db.connect()  # ensure tables exist

        with patch("reagent.storage.ReagentDB", return_value=db):
            result = runner.invoke(cli, ["loop", "history"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "No loop history" in result.output

    def test_shows_history_rows(
        self, runner: CliRunner, cli: object, tmp_path: Path
    ) -> None:
        from reagent.storage import ReagentDB

        db = ReagentDB(tmp_path / "h2.db")
        conn = db.connect()
        conn.execute(
            "INSERT INTO loops VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "abcdef12-1234-1234-1234-123456789012",
                "improve",
                "/repo",
                "completed",
                None,
                2,
                0.02,
                81.0,
                datetime.now(UTC).isoformat(),
                None,
            ),
        )
        conn.commit()

        with patch("reagent.storage.ReagentDB", return_value=db):
            result = runner.invoke(cli, ["loop", "history"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "improve" in result.output


class TestCliLoopHelp:
    def test_loop_group_help(self, runner: CliRunner, cli: object) -> None:
        result = runner.invoke(cli, ["loop", "--help"])  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert "init" in result.output
        assert "improve" in result.output
        assert "watch" in result.output
        assert "stop" in result.output
        assert "review" in result.output
        assert "deploy" in result.output
        assert "discard" in result.output
        assert "diff" in result.output
        assert "history" in result.output
