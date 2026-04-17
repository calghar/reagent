import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from agentguard.storage import AgentGuardDB
from agentguard.storage.migrations import CURRENT_VERSION, apply_migrations


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def db(db_path: Path) -> Generator[AgentGuardDB]:
    rdb = AgentGuardDB(path=db_path)
    rdb.connect()
    yield rdb
    rdb.close()


class TestAgentGuardDB:
    def test_connect_creates_file(self, db_path: Path) -> None:
        rdb = AgentGuardDB(path=db_path)
        rdb.connect()
        assert db_path.exists()
        rdb.close()

    def test_wal_mode_enabled(self, db: AgentGuardDB) -> None:
        conn = db.connect()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal"

    def test_migration_sets_version(self, db: AgentGuardDB) -> None:
        assert db.version == CURRENT_VERSION

    def test_context_manager(self, db_path: Path) -> None:
        with AgentGuardDB(path=db_path) as rdb:
            assert rdb.version == CURRENT_VERSION
        assert rdb._conn is None

    def test_double_connect_returns_same(self, db: AgentGuardDB) -> None:
        c1 = db.connect()
        c2 = db.connect()
        assert c1 is c2


class TestMigrations:
    def test_migration_idempotent(self, db_path: Path) -> None:
        rdb = AgentGuardDB(path=db_path)
        rdb.connect()
        assert rdb.version == CURRENT_VERSION
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
