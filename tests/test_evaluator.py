from datetime import UTC, datetime
from pathlib import Path

import pytest

from reagent.core.catalog import Catalog, CatalogEntry
from reagent.core.parsers import AssetType
from reagent.evaluation.evaluator import (
    ABTestStore,
    AssetMetrics,
    QualityLabel,
    QualityReport,
    _compute_quality_score,
    _label_from_score,
    _normalize_correction_rate,
    _normalize_invocation_rate,
    _normalize_staleness,
    _normalize_turn_efficiency,
    build_baseline,
    create_variant,
    evaluate_asset,
    persist_report,
    promote_variant,
)
from reagent.telemetry.events import ParsedSession, SessionMetrics, ToolCall


class TestNormalization:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 0.0),
            (5.0, 100.0),
            (10.0, 100.0),
        ],
    )
    def test_normalize_invocation_rate(self, value: float, expected: float) -> None:
        assert _normalize_invocation_rate(value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 100.0),
            (1.0, 0.0),
        ],
    )
    def test_normalize_correction_rate(self, value: float, expected: float) -> None:
        assert _normalize_correction_rate(value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "value,expected",
        [
            (1.0, 100.0),
            (20.0, 0.0),
            (0.0, 50.0),
        ],
    )
    def test_normalize_turn_efficiency(self, value: float, expected: float) -> None:
        assert _normalize_turn_efficiency(value) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 100.0),
            (90.0, 0.0),
        ],
    )
    def test_normalize_staleness(self, value: float, expected: float) -> None:
        assert _normalize_staleness(value) == pytest.approx(expected)


class TestQualityLabel:
    @pytest.mark.parametrize(
        "score,expected",
        [
            (90.0, QualityLabel.EXCELLENT),
            (85.1, QualityLabel.EXCELLENT),
            (75.0, QualityLabel.GOOD),
            (85.0, QualityLabel.GOOD),
            (60.0, QualityLabel.NEEDS_WORK),
            (30.0, QualityLabel.POOR),
        ],
    )
    def test_label_from_score(self, score: float, expected: QualityLabel) -> None:
        assert _label_from_score(score) == expected


class TestQualityScore:
    def test_perfect_scores(self) -> None:
        metrics = AssetMetrics(
            asset_id="test:skill:deploy",
            invocation_rate=5.0,
            completion_rate=1.0,
            correction_rate=0.0,
            turn_efficiency=1.0,
            staleness_days=0.0,
            coverage=100.0,
            security_score=100.0,
            freshness=100.0,
        )
        score = _compute_quality_score(metrics)
        assert score == pytest.approx(100.0)

    def test_zero_scores(self) -> None:
        metrics = AssetMetrics(
            asset_id="test:skill:deploy",
            invocation_rate=0.0,
            completion_rate=0.0,
            correction_rate=1.0,
            turn_efficiency=20.0,
            staleness_days=90.0,
            coverage=0.0,
            security_score=0.0,
            freshness=0.0,
        )
        score = _compute_quality_score(metrics)
        assert score == pytest.approx(0.0)

    def test_moderate_scores(self) -> None:
        metrics = AssetMetrics(
            asset_id="test:skill:deploy",
            invocation_rate=2.5,
            completion_rate=0.5,
            correction_rate=0.5,
            turn_efficiency=10.0,
            staleness_days=45.0,
            coverage=50.0,
            security_score=50.0,
            freshness=50.0,
        )
        score = _compute_quality_score(metrics)
        assert 40 < score < 60


class TestEvaluateAsset:
    def test_evaluate_with_no_sessions(self, tmp_path: Path) -> None:
        asset_file = tmp_path / "review.md"
        asset_file.write_text("---\nname: review\n---\nReview code.\n")
        entry = CatalogEntry(
            asset_id="test:agent:review",
            asset_type=AssetType.AGENT,
            name="review",
            repo_path=tmp_path,
            file_path=asset_file,
            content_hash="abc123",
        )
        metrics = evaluate_asset(entry, [])
        assert metrics.asset_id == "test:agent:review"
        assert metrics.invocation_rate == pytest.approx(0.0)
        assert metrics.quality_score > 0

    def test_evaluate_with_sessions(self, tmp_path: Path) -> None:
        asset_file = tmp_path / "review.md"
        asset_file.write_text("---\nname: review\n---\nReview code.\n")
        entry = CatalogEntry(
            asset_id="test:agent:review",
            asset_type=AssetType.AGENT,
            name="review",
            repo_path=tmp_path,
            file_path=asset_file,
            content_hash="abc123",
        )
        sessions = [
            ParsedSession(
                session_id="s1",
                tool_calls=[
                    ToolCall(tool_name="review", tool_input={}),
                ],
                metrics=SessionMetrics(
                    session_id="s1",
                    tool_count=5,
                    turn_count=3,
                    correction_count=0,
                ),
            ),
        ]
        metrics = evaluate_asset(entry, sessions, weeks_span=1.0)
        assert metrics.invocation_rate == pytest.approx(1.0)


class TestBuildBaseline:
    def test_empty_sessions(self) -> None:
        baseline = build_baseline([])
        assert baseline.correction_rates == []
        assert baseline.turn_counts == []

    def test_aggregates_metrics(self) -> None:
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
        baseline = build_baseline(sessions)
        assert len(baseline.correction_rates) == 5
        assert len(baseline.turn_counts) == 5
        assert all(r == pytest.approx(0.1) for r in baseline.correction_rates)


class TestABTestStore:
    def test_create_and_load(self, tmp_path: Path) -> None:
        store_path = tmp_path / "ab-tests.jsonl"
        store = ABTestStore(store_path)
        store.create_test("test:skill:deploy", "v2", "faster deploys")
        store.save()

        store2 = ABTestStore(store_path)
        store2.load()
        assert len(store2.all_tests()) == 1
        test = store2.all_tests()[0]
        assert test.variant_name == "v2"

    def test_route_session_deterministic(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("test:skill:deploy", "v2")

        test_id = "test:skill:deploy::v2"
        result1 = store.route_session(test_id, "session-abc")
        result2 = store.route_session(test_id, "session-abc")
        # Same session always gets same route (minus counter increment)
        assert result1 == result2

    def test_route_alternates(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("test:skill:deploy", "v2")

        test_id = "test:skill:deploy::v2"
        results = set()
        for i in range(20):
            results.add(store.route_session(test_id, f"session-{i}"))
        # With 20 sessions, we should see both routes
        assert "original" in results
        assert "variant" in results

    def test_deactivate(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test("test:skill:deploy", "v2")
        test_id = "test:skill:deploy::v2"
        store.deactivate(test_id)
        assert store.route_session(test_id, "any") == "original"


class TestCreateVariant:
    def test_creates_variant_file(self, tmp_path: Path) -> None:
        asset_file = tmp_path / "review.md"
        asset_file.write_text("---\nname: review\n---\nOriginal content\n")

        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="test:agent:review",
                asset_type=AssetType.AGENT,
                name="review",
                repo_path=tmp_path,
                file_path=asset_file,
                content_hash="abc",
            )
        )

        ab_store = ABTestStore(tmp_path / "ab.jsonl")
        test = create_variant(
            "test:agent:review", "v2", "test change", catalog, ab_store
        )
        assert test.test_id == "test:agent:review::v2"
        assert Path(test.variant_path).exists()
        assert Path(test.variant_path).read_text() == asset_file.read_text()

    def test_raises_for_missing_asset(self, tmp_path: Path) -> None:
        catalog = Catalog(tmp_path / "catalog.jsonl")
        ab_store = ABTestStore(tmp_path / "ab.jsonl")
        with pytest.raises(ValueError, match="Asset not found"):
            create_variant("nope:agent:missing", "v2", "", catalog, ab_store)


class TestPromoteVariant:
    def test_promote_replaces_original(self, tmp_path: Path) -> None:
        original = tmp_path / "review.md"
        variant = tmp_path / "review.variant-v2.md"
        original.write_text("original content")
        variant.write_text("improved content")

        store = ABTestStore(tmp_path / "ab.jsonl")
        store.create_test(
            "test:agent:review",
            "v2",
            original_path=str(original),
            variant_path=str(variant),
        )

        test_id = "test:agent:review::v2"
        result = promote_variant(test_id, store)
        assert result == original
        assert original.read_text() == "improved content"
        test = store.get_test(test_id)
        assert test is not None
        assert not test.active

    def test_promote_missing_test(self, tmp_path: Path) -> None:
        store = ABTestStore(tmp_path / "ab.jsonl")
        assert promote_variant("nonexistent", store) is None


class TestPersistReport:
    def test_persist_writes_to_database(self, tmp_path: Path) -> None:
        import sqlite3

        from reagent.storage import ReagentDB

        db_path = tmp_path / "reagent.db"
        with ReagentDB(db_path) as db:
            db.connect()

        repo = tmp_path / "test-repo"
        report = QualityReport(
            repo_path=str(repo),
            repo_name="test-repo",
            evaluated=2,
            healthy=1,
            underperforming=1,
            asset_metrics=[
                AssetMetrics(
                    asset_id="test:agent:review",
                    asset_type="agent",
                    name="review",
                    quality_score=85.0,
                    invocation_rate=3.0,
                    correction_rate=0.1,
                ),
                AssetMetrics(
                    asset_id="test:skill:deploy",
                    asset_type="skill",
                    name="deploy",
                    quality_score=42.0,
                    invocation_rate=1.0,
                    correction_rate=0.5,
                ),
            ],
        )

        persist_report(report, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM evaluations ORDER BY asset_name").fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0]["asset_name"] == "deploy"
        assert rows[0]["asset_type"] == "skill"
        assert float(rows[0]["quality_score"]) == pytest.approx(42.0)
        assert rows[0]["repo_path"] == str(repo)
        assert rows[1]["asset_name"] == "review"
        assert rows[1]["asset_type"] == "agent"
        assert float(rows[1]["quality_score"]) == pytest.approx(85.0)

    def test_persist_creates_unique_rows(self, tmp_path: Path) -> None:
        import sqlite3

        from reagent.storage import ReagentDB

        db_path = tmp_path / "reagent.db"
        with ReagentDB(db_path) as db:
            db.connect()

        repo = tmp_path / "test-repo"
        report = QualityReport(
            repo_path=str(repo),
            repo_name="test-repo",
            evaluated=1,
            asset_metrics=[
                AssetMetrics(
                    asset_id="test:agent:review",
                    asset_type="agent",
                    name="review",
                    quality_score=60.0,
                ),
            ],
        )

        persist_report(report, db_path=db_path)
        persist_report(report, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        conn.close()

        # Each call creates new uuid4 IDs so both rows are inserted
        assert count == 2

    def test_persist_empty_report(self, tmp_path: Path) -> None:
        import sqlite3

        from reagent.storage import ReagentDB

        db_path = tmp_path / "reagent.db"
        with ReagentDB(db_path) as db:
            db.connect()

        repo = tmp_path / "empty-repo"
        report = QualityReport(repo_path=str(repo), repo_name="empty")
        persist_report(report, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        conn.close()

        assert count == 0
