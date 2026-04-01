import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChangeRecord(BaseModel):
    """Record of a single asset change within a loop iteration."""

    asset_type: str
    asset_name: str
    file_path: str
    previous_score: float | None = None
    new_score: float | None = None
    action: str  # "created" or "updated"


class LoopState(BaseModel):
    """Mutable state for a running or completed loop.

    Stored in the ``loops`` SQLite table and updated each iteration.
    """

    loop_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    loop_type: str  # "init", "improve", "watch"
    repo_path: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    iteration: int = 0
    total_cost: float = 0.0
    scores: list[float] = Field(default_factory=list)
    changes: list[ChangeRecord] = Field(default_factory=list)
    status: str = "running"  # running, stopped, completed, failed
    stop_reason: str | None = None


class PendingAsset(BaseModel):
    """An asset awaiting human approval before deployment.

    Stored in the ``pending_assets`` SQLite table.
    """

    pending_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_type: str
    asset_name: str
    file_path: str
    content: str
    previous_content: str | None = None
    previous_score: float | None = None
    new_score: float
    generation_method: str  # "llm", "enhanced_template"
    loop_id: str
    iteration: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "pending"  # pending, approved, rejected


class ApprovalQueue:
    """SQLite-backed approval queue for pending loop asset changes.

    All generated assets are held here for human review before any file
    on disk is modified.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise the queue backed by *db_path*.

        Args:
            db_path: Path to the SQLite database.  ``None`` uses the
                default ``~/.reagent/reagent.db``.
        """
        from reagent.storage import ReagentDB

        self._db = ReagentDB(db_path)

    def add(self, asset: PendingAsset) -> str:
        """Insert a pending asset into the queue.

        Args:
            asset: The asset to enqueue.

        Returns:
            The ``pending_id`` of the inserted record.
        """
        conn = self._db.connect()
        try:
            conn.execute(
                "INSERT INTO pending_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    asset.pending_id,
                    asset.asset_type,
                    asset.asset_name,
                    asset.file_path,
                    asset.content,
                    asset.previous_content,
                    asset.previous_score,
                    asset.new_score,
                    asset.generation_method,
                    asset.loop_id,
                    asset.iteration,
                    asset.created_at.isoformat(),
                    asset.status,
                ),
            )
            conn.commit()
            logger.debug(
                "Enqueued pending asset %s (%s)", asset.pending_id, asset.asset_name
            )
            return asset.pending_id
        finally:
            self._db.close()

    def list_pending(self) -> list[PendingAsset]:
        """Return all assets with ``status='pending'``.

        Returns:
            List of PendingAsset objects ordered by creation time.
        """
        conn = self._db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM pending_assets"
                " WHERE status='pending' ORDER BY created_at"
            ).fetchall()
            return [_row_to_pending_asset(dict(row)) for row in rows]
        finally:
            self._db.close()

    def approve(self, pending_id: str) -> None:
        """Mark a single asset as approved.

        Args:
            pending_id: ID of the asset to approve.
        """
        conn = self._db.connect()
        try:
            conn.execute(
                "UPDATE pending_assets SET status='approved' WHERE pending_id=?",
                (pending_id,),
            )
            conn.commit()
            logger.debug("Approved pending asset %s", pending_id)
        finally:
            self._db.close()

    def reject(self, pending_id: str) -> None:
        """Mark a single asset as rejected.

        Args:
            pending_id: ID of the asset to reject.
        """
        conn = self._db.connect()
        try:
            conn.execute(
                "UPDATE pending_assets SET status='rejected' WHERE pending_id=?",
                (pending_id,),
            )
            conn.commit()
            logger.debug("Rejected pending asset %s", pending_id)
        finally:
            self._db.close()

    def approve_all(self) -> int:
        """Approve every currently pending asset.

        Returns:
            Number of assets approved.
        """
        conn = self._db.connect()
        try:
            count = max(
                0,
                conn.execute(
                    "UPDATE pending_assets SET status='approved' WHERE status='pending'"
                ).rowcount,
            )
            conn.commit()
            logger.debug("Approved all %d pending assets", count)
            return count
        finally:
            self._db.close()

    def get(self, pending_id: str) -> PendingAsset | None:
        """Retrieve a single pending asset by ID.

        Args:
            pending_id: The pending asset ID to look up.

        Returns:
            The PendingAsset, or None if not found.
        """
        conn = self._db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM pending_assets WHERE pending_id=?", (pending_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_pending_asset(dict(row))
        finally:
            self._db.close()


def _row_to_pending_asset(row: dict[str, object]) -> PendingAsset:
    """Convert a DB row dict to a PendingAsset, parsing ISO datetime.

    Args:
        row: Raw dict from ``sqlite3.Row``.

    Returns:
        Hydrated PendingAsset instance.
    """
    created_at_raw = row.get("created_at")
    if isinstance(created_at_raw, str):
        row["created_at"] = datetime.fromisoformat(created_at_raw)
    return PendingAsset.model_validate(row)
