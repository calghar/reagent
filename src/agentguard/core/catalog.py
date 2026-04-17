import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentguard.core.parsers import AssetScope, AssetType, ParsedAsset

logger = logging.getLogger(__name__)


class CatalogEntry(BaseModel):
    """A single entry in the asset catalog."""

    asset_id: str  # repo:type:name
    asset_type: AssetType
    name: str
    scope: AssetScope = AssetScope.PROJECT
    repo_path: Path
    file_path: Path
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    trust_level: str = "untrusted"
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))


def make_asset_id(repo_path: Path, asset_type: AssetType, name: str) -> str:
    """Build asset_id as repo_name:type:name.

    Args:
        repo_path: Path to the repository.
        asset_type: The type of the asset.
        name: The asset name.

    Returns:
        Formatted asset identifier string.
    """
    repo_name = repo_path.name
    return f"{repo_name}:{asset_type.value}:{name}"


def entry_from_parsed(
    asset: ParsedAsset,
    repo_path: Path,
    scope: AssetScope = AssetScope.PROJECT,
) -> CatalogEntry:
    """Create a CatalogEntry from a ParsedAsset.

    Args:
        asset: Parsed asset to convert.
        repo_path: Path to the repository containing the asset.
        scope: Asset scope (global, project, or local).

    Returns:
        CatalogEntry populated with asset data and timestamps.
    """
    asset_id = make_asset_id(repo_path, asset.asset_type, asset.name)

    # Extract key metadata fields depending on asset type
    metadata: dict[str, Any] = {}
    for field_name in ("description", "model", "tools", "allowed_tools", "permissions"):
        value = getattr(asset, field_name, None)
        if value:
            metadata[field_name] = value

    now = datetime.now(UTC)
    return CatalogEntry(
        asset_id=asset_id,
        asset_type=asset.asset_type,
        name=asset.name,
        scope=scope,
        repo_path=repo_path,
        file_path=asset.file_path,
        content_hash=asset.content_hash,
        metadata=metadata,
        first_seen=now,
        last_seen=now,
        last_modified=now,
    )


class Catalog:
    """JSONL-backed asset catalog."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, CatalogEntry] = {}

    def load(self) -> None:
        """Load all entries from the JSONL file.

        Clears existing in-memory entries and repopulates from disk.
        Silently skips malformed lines.
        """
        self._entries.clear()
        if not self.path.exists():
            logger.debug("Catalog file does not exist: %s", self.path)
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = CatalogEntry.model_validate_json(line)
                self._entries[entry.asset_id] = entry
            except ValueError:
                logger.warning("Skipping malformed catalog line: %.80s", line)
                continue
        logger.debug("Loaded %d entries from catalog", len(self._entries))

    def save(self) -> None:
        """Write all entries to the JSONL file (full rewrite).

        Creates parent directories if needed. Entries are sorted by
        asset_id for deterministic output.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            entry.model_dump_json()
            for entry in sorted(self._entries.values(), key=lambda e: e.asset_id)
        ]
        self.path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
        logger.debug("Saved %d entries to %s", len(lines), self.path)

    def add(self, entry: CatalogEntry) -> None:
        """Add or update an entry in the catalog.

        Args:
            entry: The catalog entry to add. If an entry with the same
                asset_id exists, first_seen is preserved.
        """
        existing = self._entries.get(entry.asset_id)
        if existing:
            # Preserve first_seen, update last_seen
            entry.first_seen = existing.first_seen
        entry.last_seen = datetime.now(UTC)
        self._entries[entry.asset_id] = entry

    def remove(self, asset_id: str) -> bool:
        """Remove an entry by asset_id.

        Args:
            asset_id: The identifier of the entry to remove.

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        return self._entries.pop(asset_id, None) is not None

    def get(self, asset_id: str) -> CatalogEntry | None:
        """Get an entry by asset_id.

        Args:
            asset_id: The identifier to look up.

        Returns:
            The matching CatalogEntry, or None if not found.
        """
        return self._entries.get(asset_id)

    def query(
        self,
        asset_type: AssetType | None = None,
        repo_name: str | None = None,
        name: str | None = None,
    ) -> list[CatalogEntry]:
        """Query entries with optional filters.

        Args:
            asset_type: Filter by asset type.
            repo_name: Filter by repository name.
            name: Filter by asset name.

        Returns:
            List of matching entries sorted by asset_id.
        """
        results = list(self._entries.values())
        if asset_type is not None:
            results = [e for e in results if e.asset_type == asset_type]
        if repo_name is not None:
            results = [e for e in results if e.repo_path.name == repo_name]
        if name is not None:
            results = [e for e in results if e.name == name]
        return sorted(results, key=lambda e: e.asset_id)

    def all_entries(self) -> list[CatalogEntry]:
        """Return all catalog entries sorted by asset_id.

        Returns:
            Sorted list of all entries.
        """
        return sorted(self._entries.values(), key=lambda e: e.asset_id)

    def diff(
        self, new_entries: list[CatalogEntry]
    ) -> tuple[list[CatalogEntry], list[CatalogEntry], list[str]]:
        """Compare new entries against existing catalog.

        Args:
            new_entries: Freshly scanned entries to compare.

        Returns:
            Tuple of (added, modified, removed_ids).
        """
        new_by_id = {e.asset_id: e for e in new_entries}
        old_ids = set(self._entries.keys())
        new_ids = set(new_by_id.keys())

        added = [new_by_id[aid] for aid in sorted(new_ids - old_ids)]
        removed_ids = sorted(old_ids - new_ids)

        modified: list[CatalogEntry] = []
        for aid in sorted(new_ids & old_ids):
            if new_by_id[aid].content_hash != self._entries[aid].content_hash:
                modified.append(new_by_id[aid])

        return added, modified, removed_ids

    def diff_repo(
        self, new_entries: list[CatalogEntry], repo_path: Path
    ) -> tuple[list[CatalogEntry], list[CatalogEntry], list[str]]:
        """Compare new entries against existing catalog scoped to one repo.

        Only considers existing entries that belong to *repo_path* when
        computing removals, so entries from other repos are unaffected.

        Args:
            new_entries: Freshly scanned entries for the repo.
            repo_path: Repo path to scope the diff to.

        Returns:
            Tuple of (added, modified, removed_ids).
        """
        new_by_id = {e.asset_id: e for e in new_entries}
        new_ids = set(new_by_id.keys())

        # Only consider existing entries from this repo
        old_repo_ids = {
            eid for eid, entry in self._entries.items() if entry.repo_path == repo_path
        }

        added = [new_by_id[aid] for aid in sorted(new_ids - old_repo_ids)]
        removed_ids = sorted(old_repo_ids - new_ids)

        modified: list[CatalogEntry] = []
        for aid in sorted(new_ids & old_repo_ids):
            if new_by_id[aid].content_hash != self._entries[aid].content_hash:
                modified.append(new_by_id[aid])

        return added, modified, removed_ids

    def apply_diff(
        self,
        added: list[CatalogEntry],
        modified: list[CatalogEntry],
        removed_ids: list[str],
    ) -> None:
        """Apply a diff result to the catalog.

        Args:
            added: New entries to add.
            modified: Changed entries to update.
            removed_ids: Asset IDs to remove.
        """
        for entry in added:
            self.add(entry)
        for entry in modified:
            self.add(entry)
        for asset_id in removed_ids:
            self.remove(asset_id)

    @property
    def count(self) -> int:
        """Total number of entries in the catalog."""
        return len(self._entries)

    def counts_by_type(self) -> dict[AssetType, int]:
        """Return count of entries grouped by asset type.

        Returns:
            Dictionary mapping each AssetType to its entry count.
        """
        counts: dict[AssetType, int] = {}
        for entry in self._entries.values():
            counts[entry.asset_type] = counts.get(entry.asset_type, 0) + 1
        return counts
