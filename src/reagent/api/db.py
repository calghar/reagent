import logging
import os
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    """Return the SQLite database path.

    Reads ``REAGENT_DB_PATH`` environment variable first, falling back to
    ``~/.reagent/reagent.db``.
    """
    env_path = os.environ.get("REAGENT_DB_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".reagent" / "reagent.db"


def ensure_schema(db_path: Path | None = None) -> None:
    """Create the database and apply all pending migrations.

    Safe to call repeatedly — migrations are idempotent.  Uses a
    synchronous connection so it can run at import / startup time
    before the async event loop is available.

    Args:
        db_path: Optional path override.  Defaults to :func:`get_db_path`.
    """
    from reagent.storage.migrations import apply_migrations

    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(conn)
    logger.debug("Database schema ensured at %s", path)


@asynccontextmanager
async def get_connection(
    db_path: Path | None = None,
) -> AsyncGenerator[aiosqlite.Connection]:
    """Async context manager for a SQLite connection.

    Args:
        db_path: Optional path override.  Defaults to :func:`get_db_path`.

    Yields:
        An open :class:`aiosqlite.Connection` with ``row_factory`` set.
    """
    path = db_path or get_db_path()
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
