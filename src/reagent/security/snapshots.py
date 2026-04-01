import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from reagent.config import ReagentConfig

logger = logging.getLogger(__name__)


class SnapshotEntry(BaseModel):
    """A single snapshot in an asset's version history."""

    snapshot_id: int
    asset_id: str
    content_hash: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trigger: str = "manual"  # manual, scan, config_change
    file_path: str = ""


class SnapshotChain(BaseModel):
    """The full snapshot history for one asset."""

    asset_id: str
    snapshots: list[SnapshotEntry] = Field(default_factory=list)

    @property
    def latest(self) -> SnapshotEntry | None:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def next_id(self) -> int:
        return (self.snapshots[-1].snapshot_id + 1) if self.snapshots else 1


class SnapshotStore:
    """Content-addressed snapshot store for asset versioning.

    Layout:
        base_dir/index.jsonl     -- maps asset_id to snapshot chain
        base_dir/blobs/<sha256>.md -- immutable content copies
    """

    def __init__(self, base_dir: Path, config: ReagentConfig | None = None) -> None:
        self.base_dir = base_dir
        self.index_path = base_dir / "index.jsonl"
        self.blobs_dir = base_dir / "blobs"
        self._chains: dict[str, SnapshotChain] = {}

        if config:
            self.max_per_asset = config.versioning.max_snapshots_per_asset
            self.retention_days = config.versioning.snapshot_retention
        else:
            self.max_per_asset = 50
            self.retention_days = 90

    def load(self) -> None:
        """Load the snapshot index from disk."""
        self._chains.clear()
        if not self.index_path.exists():
            return
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                chain = SnapshotChain.model_validate_json(line)
                self._chains[chain.asset_id] = chain
            except ValueError:
                continue

    def save(self) -> None:
        """Write the snapshot index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            chain.model_dump_json()
            for chain in sorted(self._chains.values(), key=lambda c: c.asset_id)
        ]
        self.index_path.write_text(
            "\n".join(lines) + "\n" if lines else "", encoding="utf-8"
        )

    def take_snapshot(
        self,
        asset_id: str,
        content: str,
        file_path: Path | str = "",
        trigger: str = "manual",
    ) -> SnapshotEntry:
        """Take a snapshot of asset content.

        Stores the content as an immutable blob and records it in the index.
        Skips if the content hash matches the latest snapshot.

        Args:
            asset_id: Asset identifier.
            content: The full text content to snapshot.
            file_path: Original file path for reference.
            trigger: What triggered this snapshot.

        Returns:
            The SnapshotEntry for this snapshot (new or existing if unchanged).
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        chain = self._chains.get(asset_id)
        if chain is None:
            chain = SnapshotChain(asset_id=asset_id)
            self._chains[asset_id] = chain

        # Skip if content unchanged
        if chain.latest and chain.latest.content_hash == content_hash:
            return chain.latest

        # Store blob
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        blob_path = self.blobs_dir / f"{content_hash}.md"
        if not blob_path.exists():
            blob_path.write_text(content, encoding="utf-8")

        entry = SnapshotEntry(
            snapshot_id=chain.next_id,
            asset_id=asset_id,
            content_hash=content_hash,
            trigger=trigger,
            file_path=str(file_path),
        )
        chain.snapshots.append(entry)

        # Enforce retention
        self._enforce_retention(chain)

        return entry

    def get_chain(self, asset_id: str) -> SnapshotChain | None:
        """Get the snapshot chain for an asset."""
        return self._chains.get(asset_id)

    def get_snapshot(self, asset_id: str, snapshot_id: int) -> SnapshotEntry | None:
        """Get a specific snapshot by asset and snapshot ID."""
        chain = self._chains.get(asset_id)
        if not chain:
            return None
        for snap in chain.snapshots:
            if snap.snapshot_id == snapshot_id:
                return snap
        return None

    def read_blob(self, content_hash: str) -> str | None:
        """Read the content of a blob by its hash.

        Args:
            content_hash: SHA-256 hash of the content.

        Returns:
            The content string, or None if the blob doesn't exist.
        """
        blob_path = self.blobs_dir / f"{content_hash}.md"
        if not blob_path.exists():
            return None
        return blob_path.read_text(encoding="utf-8")

    def rollback(
        self, asset_id: str, snapshot_id: int, target_path: Path
    ) -> SnapshotEntry:
        """Restore an asset from a specific snapshot.

        Writes the blob content to the target path and records a new snapshot.

        Args:
            asset_id: Asset identifier.
            snapshot_id: ID of the snapshot to restore from.
            target_path: Path where the content should be written.

        Returns:
            The new SnapshotEntry created after the rollback.

        Raises:
            ValueError: If snapshot or blob not found.
        """
        snap = self.get_snapshot(asset_id, snapshot_id)
        if not snap:
            raise ValueError(f"Snapshot {snapshot_id} not found for asset {asset_id}")

        content = self.read_blob(snap.content_hash)
        if content is None:
            raise ValueError(
                f"Blob {snap.content_hash} not found for snapshot {snapshot_id}"
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")

        return self.take_snapshot(
            asset_id, content, file_path=target_path, trigger="rollback"
        )

    def history(self, asset_id: str) -> list[SnapshotEntry]:
        """Get the snapshot timeline for an asset.

        Args:
            asset_id: Asset identifier.

        Returns:
            List of snapshots in chronological order.
        """
        chain = self._chains.get(asset_id)
        if not chain:
            return []
        return list(chain.snapshots)

    def _enforce_retention(self, chain: SnapshotChain) -> None:
        """Remove old snapshots exceeding retention limits."""
        # Max count
        if len(chain.snapshots) > self.max_per_asset:
            excess = len(chain.snapshots) - self.max_per_asset
            removed = chain.snapshots[:excess]
            chain.snapshots = chain.snapshots[excess:]
            self._cleanup_blobs(removed)

        # Age-based retention
        if self.retention_days > 0:
            cutoff = datetime.now(UTC).timestamp() - (self.retention_days * 86400)
            to_keep: list[SnapshotEntry] = []
            to_remove: list[SnapshotEntry] = []
            for snap in chain.snapshots:
                if snap.timestamp.timestamp() < cutoff:
                    to_remove.append(snap)
                else:
                    to_keep.append(snap)
            # Always keep at least one snapshot
            if to_keep:
                chain.snapshots = to_keep
                self._cleanup_blobs(to_remove)

    def _cleanup_blobs(self, removed: list[SnapshotEntry]) -> None:
        """Remove blob files that are no longer referenced by any chain."""
        # Collect all referenced hashes
        referenced = set()
        for chain in self._chains.values():
            for snap in chain.snapshots:
                referenced.add(snap.content_hash)

        for snap in removed:
            if snap.content_hash not in referenced:
                blob_path = self.blobs_dir / f"{snap.content_hash}.md"
                blob_path.unlink(missing_ok=True)

    def all_chains(self) -> list[SnapshotChain]:
        """Return all snapshot chains sorted by asset_id."""
        return sorted(self._chains.values(), key=lambda c: c.asset_id)
