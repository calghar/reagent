import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from reagent._tuning import get_tuning

logger = logging.getLogger(__name__)


class BudgetStatus(StrEnum):
    """Budget enforcement status."""

    OK = "ok"
    WARNING = "warning"  # >=80% spent
    EXCEEDED = "exceeded"  # >=100% spent


class CostEntry(BaseModel):
    """A single LLM cost record."""

    cost_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    asset_type: str = ""
    asset_name: str = ""
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    tier: str = "standard"
    was_fallback: bool = False


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cost_entries (
    cost_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT '',
    asset_name TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    tier TEXT NOT NULL DEFAULT 'standard',
    was_fallback INTEGER NOT NULL DEFAULT 0
)
"""


class CostTracker:
    """Track LLM costs with SQLite persistence and budget enforcement."""

    def __init__(
        self,
        db_path: Path | None = None,
        monthly_budget: float = 10.0,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._db_path = db_path or Path.home() / ".reagent" / "reagent.db"
        self._monthly_budget = monthly_budget
        self._session_entries: list[CostEntry] = []
        self._db: sqlite3.Connection | None = None
        self._owns_connection = connection is None
        if connection is not None:
            self._db = connection
            self._ensure_table()
        else:
            self._init_db()

    def _ensure_table(self) -> None:
        """Create cost_entries table if it doesn't exist."""
        if self._db is None:
            return
        self._db.execute(_CREATE_TABLE_SQL)
        self._db.commit()

    def _init_db(self) -> None:
        """Initialize SQLite table. Falls back to JSONL on failure."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self._db_path))
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(_CREATE_TABLE_SQL)
            self._db.commit()
        except (OSError, sqlite3.Error) as exc:
            logger.warning(
                "SQLite init failed (%s); cost entries will use JSONL fallback", exc
            )
            self._db = None

    def record(self, entry: CostEntry) -> None:
        """Record a cost entry to SQLite (or JSONL fallback)."""
        self._session_entries.append(entry)
        if self._db is not None:
            self._write_sqlite(entry)
        else:
            self._write_jsonl(entry)

    def _write_sqlite(self, entry: CostEntry) -> None:
        if self._db is None:  # pragma: no cover
            return
        self._db.execute(
            """INSERT OR REPLACE INTO cost_entries
               (cost_id, timestamp, provider, model, asset_type, asset_name,
                input_tokens, output_tokens, cost_usd, latency_ms, tier, was_fallback)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.cost_id,
                entry.timestamp.isoformat(),
                entry.provider,
                entry.model,
                entry.asset_type,
                entry.asset_name,
                entry.input_tokens,
                entry.output_tokens,
                entry.cost_usd,
                entry.latency_ms,
                entry.tier,
                int(entry.was_fallback),
            ),
        )
        self._db.commit()

    def _write_jsonl(self, entry: CostEntry) -> None:
        fallback_path = self._db_path.parent / "cost_log.jsonl"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        with fallback_path.open("a") as f:
            f.write(json.dumps(entry.model_dump(mode="json"), default=str) + "\n")

    def session_total(self) -> float:
        """Total cost in the current session."""
        return sum(e.cost_usd for e in self._session_entries)

    def monthly_total(self) -> float:
        """Total cost for the current calendar month from SQLite."""
        if self._db is None:
            return self.session_total()
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cursor = self._db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_entries WHERE timestamp >= ?",
            (month_start.isoformat(),),
        )
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0

    def budget_status(self) -> BudgetStatus:
        """Check budget against monthly total."""
        if self._monthly_budget <= 0:
            return BudgetStatus.OK
        total = self.monthly_total()
        ratio = total / self._monthly_budget
        if ratio >= get_tuning().budget.exceeded_ratio:
            return BudgetStatus.EXCEEDED
        if ratio >= get_tuning().budget.warning_ratio:
            return BudgetStatus.WARNING
        return BudgetStatus.OK

    def cost_by_provider(self) -> dict[str, float]:
        """Aggregate costs by provider for the current month."""
        if self._db is None:
            result: dict[str, float] = {}
            for e in self._session_entries:
                result[e.provider] = result.get(e.provider, 0.0) + e.cost_usd
            return result
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cursor = self._db.execute(
            "SELECT provider, SUM(cost_usd) FROM cost_entries "
            "WHERE timestamp >= ? GROUP BY provider",
            (month_start.isoformat(),),
        )
        return {row[0]: float(row[1]) for row in cursor.fetchall()}

    def close(self) -> None:
        """Close the database connection if we own it."""
        if self._db is not None and self._owns_connection:
            self._db.close()
            self._db = None

    def __enter__(self) -> "CostTracker":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
