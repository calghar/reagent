import logging
import os
import sqlite3
from pathlib import Path

from reagent.storage.migrations import CURRENT_VERSION, apply_migrations

logger = logging.getLogger(__name__)


def _default_db_path() -> Path:
    env = os.environ.get("REAGENT_DB_PATH")
    if env:
        return Path(env)
    return Path.home() / ".reagent" / "reagent.db"


class ReagentDB:
    """Central database access for all reagent persistent data."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        """Open (or return existing) database connection.

        Enables WAL mode and foreign keys, then runs pending
        migrations.
        """
        if self._conn is not None:
            return self._conn

        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        self._conn = conn

        self.migrate()
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
            self._conn = None

    def migrate(self) -> None:
        """Apply all pending schema migrations."""
        if self._conn is None:
            msg = "Database not connected. Call connect() first."
            raise RuntimeError(msg)
        apply_migrations(self._conn)

    @property
    def version(self) -> int:
        """Current schema version of the database."""
        if self._conn is None:
            msg = "Database not connected."
            raise RuntimeError(msg)
        row = self._conn.execute("PRAGMA user_version").fetchone()
        if row is None:
            return 0
        return int(row[0])

    def __enter__(self) -> "ReagentDB":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["CURRENT_VERSION", "ReagentDB"]
