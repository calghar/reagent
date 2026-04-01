import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"

MigrationFn = Callable[[sqlite3.Connection], None]


def _v0_to_v1(conn: sqlite3.Connection) -> None:
    """Initial migration: create all core tables + FTS5."""
    sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(sql)


def _v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add loops and pending_assets tables for autonomous loop support."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS loops (
            loop_id      TEXT PRIMARY KEY,
            loop_type    TEXT NOT NULL,
            repo_path    TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'running',
            stop_reason  TEXT,
            iteration    INTEGER NOT NULL DEFAULT 0,
            total_cost   REAL NOT NULL DEFAULT 0.0,
            avg_score    REAL,
            started_at   TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pending_assets (
            pending_id        TEXT PRIMARY KEY,
            asset_type        TEXT NOT NULL,
            asset_name        TEXT NOT NULL,
            file_path         TEXT NOT NULL,
            content           TEXT NOT NULL,
            previous_content  TEXT,
            previous_score    REAL,
            new_score         REAL NOT NULL,
            generation_method TEXT NOT NULL,
            loop_id           TEXT NOT NULL,
            iteration         INTEGER NOT NULL,
            created_at        TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending'
        );
        """
    )


def _v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add security_scans table for persisting scan audit trails."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS security_scans (
            scan_id       TEXT PRIMARY KEY,
            asset_path    TEXT NOT NULL,
            repo_path     TEXT,
            findings_json TEXT,
            finding_count INTEGER,
            scanned_at    TEXT NOT NULL
        );
        """
    )


# Ordered list of migrations.  Index = version that migration produces.
# e.g. _MIGRATIONS[0] migrates from v0 → v1.
_MIGRATIONS: list[tuple[int, MigrationFn]] = [
    (1, _v0_to_v1),
    (2, _v1_to_v2),
    (3, _v2_to_v3),
]

CURRENT_VERSION: int = _MIGRATIONS[-1][0] if _MIGRATIONS else 0


def _get_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version}")


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations to *conn*.

    Reads the current ``user_version`` and runs each migration whose
    target version is higher.
    """
    current = _get_version(conn)
    for target, migration_fn in _MIGRATIONS:
        if current < target:
            logger.info("Applying migration v%d → v%d", current, target)
            migration_fn(conn)
            _set_version(conn, target)
            conn.commit()
            current = target
    logger.debug("Database at schema version %d", current)
