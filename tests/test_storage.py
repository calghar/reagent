import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reagent.core.parsers import AssetType
from reagent.llm.cache import CacheEntry, GenerationCache, make_cache_key
from reagent.llm.config import CostTier, LLMConfig, select_model
from reagent.llm.costs import CostEntry, CostTracker
from reagent.llm.instincts import Instinct, InstinctStore, TrustTier
from reagent.llm.prompts import (
    ProfileTier,
    PromptBudget,
    select_profile_tier,
)
from reagent.storage import ReagentDB
from reagent.storage.migrations import CURRENT_VERSION, apply_migrations


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def db(db_path: Path) -> Generator[ReagentDB]:
    rdb = ReagentDB(path=db_path)
    rdb.connect()
    yield rdb
    rdb.close()


@pytest.fixture()
def conn(db: ReagentDB) -> sqlite3.Connection:
    return db.connect()


class TestReagentDB:
    def test_connect_creates_file(self, db_path: Path) -> None:
        rdb = ReagentDB(path=db_path)
        rdb.connect()
        assert db_path.exists()
        rdb.close()

    def test_wal_mode_enabled(self, db: ReagentDB) -> None:
        conn = db.connect()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_migration_sets_version(self, db: ReagentDB) -> None:
        assert db.version == CURRENT_VERSION

    def test_context_manager(self, db_path: Path) -> None:
        with ReagentDB(path=db_path) as rdb:
            assert rdb.version == CURRENT_VERSION
        # connection closed after exit
        assert rdb._conn is None

    def test_double_connect_returns_same(self, db: ReagentDB) -> None:
        c1 = db.connect()
        c2 = db.connect()
        assert c1 is c2


class TestCostCRUD:
    def test_insert_and_query(self, conn: sqlite3.Connection) -> None:
        tracker = CostTracker(connection=conn)
        entry = CostEntry(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.0035,
            latency_ms=450,
        )
        tracker.record(entry)

        row = conn.execute(
            "SELECT provider, model, cost_usd FROM cost_entries WHERE cost_id = ?",
            (entry.cost_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "anthropic"
        assert row[2] == pytest.approx(0.0035)

    def test_session_total(self, conn: sqlite3.Connection) -> None:
        tracker = CostTracker(connection=conn)
        for _ in range(3):
            tracker.record(
                CostEntry(
                    provider="anthropic",
                    model="test",
                    input_tokens=10,
                    output_tokens=10,
                    cost_usd=1.0,
                    latency_ms=100,
                )
            )
        assert tracker.session_total() == pytest.approx(3.0)

    def test_monthly_total(self, conn: sqlite3.Connection) -> None:
        tracker = CostTracker(connection=conn)
        tracker.record(
            CostEntry(
                provider="openai",
                model="gpt-4o",
                input_tokens=50,
                output_tokens=50,
                cost_usd=2.5,
                latency_ms=300,
            )
        )
        assert tracker.monthly_total() >= 2.5


class TestInstinctsCRUD:
    def test_sqlite_save_and_load(
        self,
        conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        store = InstinctStore(
            tmp_path / "unused.json",
            connection=conn,
        )
        inst = Instinct(
            instinct_id="test-001",
            content="Always use Read before Write",
            category="generation",
            trust_tier=TrustTier.BUNDLED,
            confidence=0.9,
            source="reagent-core",
        )
        store.add(inst)
        store.save()

        # Load from SQLite in a fresh store
        store2 = InstinctStore(
            tmp_path / "unused.json",
            connection=conn,
        )
        store2.load()
        assert len(store2.instincts) == 1
        assert store2.instincts[0].instinct_id == "test-001"
        assert store2.instincts[0].content == "Always use Read before Write"

    def test_fts5_search(
        self,
        conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        store = InstinctStore(
            tmp_path / "unused.json",
            connection=conn,
        )
        store.add(
            Instinct(
                instinct_id="fts-001",
                content="Use structured error handling in Python",
                category="generation",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.8,
                source="telemetry",
            )
        )
        store.add(
            Instinct(
                instinct_id="fts-002",
                content="Always add lint commands to hooks",
                category="hook",
                trust_tier=TrustTier.BUNDLED,
                confidence=0.85,
                source="reagent-core",
            )
        )
        store.save()

        results = store.search_fts("error handling", limit=5)
        assert len(results) >= 1
        assert any("error handling" in r.content.lower() for r in results)

    def test_fts5_no_match(
        self,
        conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        store = InstinctStore(
            tmp_path / "unused.json",
            connection=conn,
        )
        store.add(
            Instinct(
                instinct_id="fts-010",
                content="Simple test instinct",
                category="generation",
                trust_tier=TrustTier.WORKSPACE,
                confidence=0.5,
                source="test",
            )
        )
        store.save()

        results = store.search_fts("nonexistentxyz123", limit=5)
        assert len(results) == 0


class TestPromptBudget:
    def test_claude_md_always_full_tier(self) -> None:
        budget = PromptBudget(total=2000)
        tier = select_profile_tier(AssetType.CLAUDE_MD, budget)
        assert tier == ProfileTier.FULL

    def test_hook_gets_core_tier(self) -> None:
        budget = PromptBudget(total=2000)
        tier = select_profile_tier(AssetType.HOOK, budget)
        assert tier == ProfileTier.CORE

    def test_command_gets_core_tier(self) -> None:
        budget = PromptBudget(total=2000)
        tier = select_profile_tier(AssetType.COMMAND, budget)
        assert tier == ProfileTier.CORE

    def test_agent_gets_standard_with_budget(self) -> None:
        budget = PromptBudget(total=2000)
        tier = select_profile_tier(AssetType.AGENT, budget, used_tokens=0)
        assert tier == ProfileTier.STANDARD

    def test_agent_degrades_to_core_on_tight_budget(self) -> None:
        budget = PromptBudget(total=300, core_profile=200, conventions=300)
        # used_tokens = 250 → remaining = 300 - 250 - 50 = 0
        tier = select_profile_tier(AssetType.AGENT, budget, used_tokens=250)
        assert tier == ProfileTier.CORE


class TestModelRouting:
    def test_hook_routes_to_cheap(self) -> None:
        config = LLMConfig(provider="anthropic")
        model, tier = select_model(AssetType.HOOK, config)
        assert tier == CostTier.CHEAP
        assert "haiku" in model

    def test_agent_routes_to_standard(self) -> None:
        config = LLMConfig(provider="anthropic")
        model, tier = select_model(AssetType.AGENT, config)
        assert tier == CostTier.STANDARD
        assert "sonnet" in model

    def test_critic_always_cheap(self) -> None:
        config = LLMConfig(provider="anthropic")
        _model, tier = select_model(
            AssetType.CLAUDE_MD,
            config,
            is_critic=True,
        )
        assert tier == CostTier.CHEAP

    def test_regeneration_uses_standard(self) -> None:
        config = LLMConfig(provider="anthropic")
        _model, tier = select_model(
            AssetType.HOOK,
            config,
            is_regeneration=True,
        )
        assert tier == CostTier.STANDARD

    def test_user_override_takes_precedence(self) -> None:
        config = LLMConfig(provider="anthropic")
        model, _tier = select_model(
            AssetType.HOOK,
            config,
            model_override="my-custom-model",
        )
        assert model == "my-custom-model"


class TestGenerationCache:
    def test_cache_miss(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn)
        assert cache.get("nonexistent-key") is None

    def test_cache_put_and_get(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn)
        key = make_cache_key("agent", "test-agent", "abc123", "def456")
        entry = CacheEntry(
            cache_key=key,
            asset_type="agent",
            name="test-agent",
            content="---\nname: test-agent\n---\n# Test",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            cost_usd=0.005,
            profile_hash="abc123",
            instinct_hash="def456",
        )
        cache.put(entry)

        result = cache.get(key)
        assert result is not None
        assert result.content == entry.content
        assert result.provider == "anthropic"

    def test_cache_invalidation(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn)
        key = make_cache_key("skill", "test", "hash1")
        cache.put(
            CacheEntry(
                cache_key=key,
                asset_type="skill",
                name="test",
                content="content",
                profile_hash="hash1",
            )
        )
        assert cache.get(key) is not None
        assert cache.invalidate(key) is True
        assert cache.get(key) is None

    def test_cache_expired_entry(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn, max_age_days=7)
        key = make_cache_key("hook", "old", "hash")
        old_date = datetime.now(UTC) - timedelta(days=10)
        cache.put(
            CacheEntry(
                cache_key=key,
                asset_type="hook",
                name="old",
                content="old-content",
                generated_at=old_date,
                profile_hash="hash",
            )
        )
        # Should return None (expired)
        assert cache.get(key) is None

    def test_cache_clear(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn)
        for i in range(3):
            cache.put(
                CacheEntry(
                    cache_key=f"key-{i}",
                    asset_type="agent",
                    name=f"agent-{i}",
                    content=f"content-{i}",
                    profile_hash="h",
                )
            )
        removed = cache.clear()
        assert removed == 3

    def test_cache_stats(self, conn: sqlite3.Connection) -> None:
        cache = GenerationCache(conn, max_age_days=7)
        # Add one fresh and one expired entry
        cache.put(
            CacheEntry(
                cache_key="fresh",
                asset_type="agent",
                name="fresh",
                content="content",
                profile_hash="h",
            )
        )
        old_date = datetime.now(UTC) - timedelta(days=10)
        cache.put(
            CacheEntry(
                cache_key="old",
                asset_type="agent",
                name="old",
                content="content",
                generated_at=old_date,
                profile_hash="h",
            )
        )
        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["valid"] == 1
        assert stats["expired"] == 1


class TestJSONLMigration:
    def test_instincts_json_to_sqlite(
        self,
        conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        """Instincts loaded from JSON can be saved to SQLite."""
        import json

        json_path = tmp_path / "instincts.json"
        data = [
            {
                "instinct_id": "migrate-001",
                "content": "Legacy instinct from JSON",
                "category": "generation",
                "trust_tier": "workspace",
                "confidence": 0.7,
                "source": "old-system",
                "created_at": datetime.now(UTC).isoformat(),
                "last_used": None,
                "use_count": 3,
                "success_rate": 0.5,
                "ttl_days": 90,
            }
        ]
        json_path.write_text(json.dumps(data), encoding="utf-8")

        # Load from JSON (no SQLite connection)
        json_store = InstinctStore(json_path)
        json_store.load()
        assert len(json_store.instincts) == 1

        # Save to SQLite
        sqlite_store = InstinctStore(json_path, connection=conn)
        for inst in json_store.instincts:
            sqlite_store.add(inst)
        sqlite_store.save()

        # Verify in SQLite
        sqlite_store2 = InstinctStore(json_path, connection=conn)
        sqlite_store2.load()
        assert len(sqlite_store2.instincts) == 1
        assert sqlite_store2.instincts[0].instinct_id == "migrate-001"

    def test_cost_tracker_jsonl_fallback(self, tmp_path: Path) -> None:
        """CostTracker falls back to JSONL when SQLite fails."""
        # Force a connection failure by passing a directory as db_path
        dir_path = tmp_path / "is_a_dir.db"
        dir_path.mkdir()

        tracker = CostTracker(db_path=dir_path)
        # Should fall back to JSONL — record shouldn't crash
        tracker.record(
            CostEntry(
                provider="test",
                model="test",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.001,
                latency_ms=50,
            )
        )
        assert tracker.session_total() == pytest.approx(0.001)


class TestMigrations:
    def test_migration_idempotent(self, db_path: Path) -> None:
        """Running migrations twice doesn't fail."""
        rdb = ReagentDB(path=db_path)
        rdb.connect()
        # First migration already ran
        assert rdb.version == CURRENT_VERSION
        # Running again should be a no-op
        rdb.migrate()
        assert rdb.version == CURRENT_VERSION
        rdb.close()

    def test_apply_migrations_fresh_db(self, tmp_path: Path) -> None:
        path = tmp_path / "fresh.db"
        conn = sqlite3.connect(str(path))
        apply_migrations(conn)
        row = conn.execute("PRAGMA user_version").fetchone()
        assert int(row[0]) == CURRENT_VERSION
        conn.close()
