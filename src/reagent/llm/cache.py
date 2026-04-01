import hashlib
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from reagent._tuning import get_tuning

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """A cached generation result."""

    cache_key: str
    asset_type: str
    name: str
    content: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str = ""
    model: str = ""
    cost_usd: float = 0.0
    profile_hash: str = ""
    instinct_hash: str = ""


def make_cache_key(
    asset_type: str,
    name: str,
    profile_hash: str,
    instinct_hash: str = "",
) -> str:
    """Compute a deterministic cache key.

    Args:
        asset_type: Asset type string.
        name: Asset name.
        profile_hash: Hash of the repo profile.
        instinct_hash: Hash of relevant instincts.

    Returns:
        SHA-256 hex digest.
    """
    raw = f"{asset_type}:{name}:{profile_hash}:{instinct_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


class GenerationCache:
    """SQLite-backed generation cache.

    Requires a ``sqlite3.Connection`` with the ``generations`` table
    already created (via ReagentDB migrations).
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        max_age_days: int | None = None,
    ) -> None:
        self._db = connection
        self._max_age_days = (
            max_age_days
            if max_age_days is not None
            else get_tuning().cache.default_max_age_days
        )

    def get(self, cache_key: str) -> CacheEntry | None:
        """Look up a cached generation by key.

        Returns ``None`` on cache miss or if the entry is expired.
        """
        cursor = self._db.execute(
            "SELECT cache_key, asset_type, name, content, generated_at, "
            "provider, model, cost_usd, profile_hash, instinct_hash "
            "FROM generations WHERE cache_key = ?",
            (cache_key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        generated_at = datetime.fromisoformat(row[4])
        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)
        if generated_at < cutoff:
            # Expired — treat as miss
            self._db.execute(
                "DELETE FROM generations WHERE cache_key = ?",
                (cache_key,),
            )
            self._db.commit()
            return None

        return CacheEntry(
            cache_key=row[0],
            asset_type=row[1],
            name=row[2],
            content=row[3],
            generated_at=generated_at,
            provider=row[5],
            model=row[6],
            cost_usd=row[7],
            profile_hash=row[8],
            instinct_hash=row[9],
        )

    def put(self, entry: CacheEntry) -> None:
        """Insert or replace a cache entry."""
        self._db.execute(
            "INSERT OR REPLACE INTO generations "
            "(cache_key, asset_type, name, content, generated_at, "
            "provider, model, cost_usd, profile_hash, instinct_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.cache_key,
                entry.asset_type,
                entry.name,
                entry.content,
                entry.generated_at.isoformat(),
                entry.provider,
                entry.model,
                entry.cost_usd,
                entry.profile_hash,
                entry.instinct_hash,
            ),
        )
        self._db.commit()

    def invalidate(self, cache_key: str) -> bool:
        """Remove a specific cache entry.

        Returns True if an entry was removed.
        """
        cursor = self._db.execute(
            "DELETE FROM generations WHERE cache_key = ?",
            (cache_key,),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def clear(self) -> int:
        """Remove all cached entries.

        Returns the number of entries removed.
        """
        cursor = self._db.execute("DELETE FROM generations")
        self._db.commit()
        return cursor.rowcount

    def evict_expired(self) -> int:
        """Remove entries older than ``max_age_days``.

        Returns the number of entries evicted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)
        cursor = self._db.execute(
            "DELETE FROM generations WHERE generated_at < ?",
            (cutoff.isoformat(),),
        )
        self._db.commit()
        return cursor.rowcount

    def stats(self) -> dict[str, int]:
        """Return basic cache statistics."""
        row = self._db.execute("SELECT COUNT(*) FROM generations").fetchone()
        total = int(row[0]) if row else 0

        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)
        row = self._db.execute(
            "SELECT COUNT(*) FROM generations WHERE generated_at >= ?",
            (cutoff.isoformat(),),
        ).fetchone()
        valid = int(row[0]) if row else 0

        return {"total": total, "valid": valid, "expired": total - valid}
