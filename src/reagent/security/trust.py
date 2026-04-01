import enum
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TrustLevel(enum.IntEnum):
    """Trust levels for Claude Code assets."""

    UNTRUSTED = 0
    REVIEWED = 2
    VERIFIED = 3
    NATIVE = 4


class AssetState(enum.StrEnum):
    """Lifecycle state for tracked assets."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class TrustEvent(BaseModel):
    """A single trust-level change event."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    asset_id: str
    action: str  # promote, demote, suspend, restore
    from_level: TrustLevel | None = None
    to_level: TrustLevel | None = None
    reason: str = ""


class TrustRecord(BaseModel):
    """Trust metadata for a single asset."""

    asset_id: str
    trust_level: TrustLevel = TrustLevel.UNTRUSTED
    state: AssetState = AssetState.ACTIVE
    history: list[TrustEvent] = Field(default_factory=list)
    last_review: datetime | None = None
    content_hash_at_review: str = ""


# Allowed trust transitions (from -> set of valid destinations)
_VALID_PROMOTIONS: dict[TrustLevel, set[TrustLevel]] = {
    TrustLevel.UNTRUSTED: {TrustLevel.REVIEWED},
    TrustLevel.REVIEWED: {TrustLevel.VERIFIED},
    # Cannot promote above verified (native is built-in only)
    TrustLevel.VERIFIED: set(),
    TrustLevel.NATIVE: set(),
}


def _can_promote(current: TrustLevel, target: TrustLevel) -> bool:
    return target in _VALID_PROMOTIONS.get(current, set())


class TrustStore:
    """Manage trust records for assets."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: dict[str, TrustRecord] = {}

    def load(self) -> None:
        """Load trust records from JSONL file."""
        self._records.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = TrustRecord.model_validate_json(line)
                self._records[record.asset_id] = record
            except ValueError:
                continue

    def save(self) -> None:
        """Write all records to JSONL file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            record.model_dump_json()
            for record in sorted(self._records.values(), key=lambda r: r.asset_id)
        ]
        self.path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")

    def get(self, asset_id: str) -> TrustRecord | None:
        """Get the trust record for an asset."""
        return self._records.get(asset_id)

    def get_or_create(self, asset_id: str) -> TrustRecord:
        """Get or create a trust record for an asset."""
        if asset_id not in self._records:
            self._records[asset_id] = TrustRecord(asset_id=asset_id)
        return self._records[asset_id]

    def set_level(
        self, asset_id: str, level: TrustLevel, content_hash: str = ""
    ) -> TrustRecord:
        """Set the trust level directly (for initial assignment).

        Args:
            asset_id: Asset identifier.
            level: Trust level to assign.
            content_hash: Content hash at the time of assignment.

        Returns:
            Updated trust record.
        """
        record = self.get_or_create(asset_id)
        old_level = record.trust_level
        record.trust_level = level
        record.last_review = datetime.now(UTC)
        if content_hash:
            record.content_hash_at_review = content_hash
        record.history.append(
            TrustEvent(
                asset_id=asset_id,
                action="set",
                from_level=old_level,
                to_level=level,
                reason="Initial trust assignment",
            )
        )
        return record

    def promote(self, asset_id: str, target: TrustLevel, reason: str) -> TrustRecord:
        """Promote an asset to a higher trust level.

        Args:
            asset_id: Asset identifier.
            target: Target trust level.
            reason: Justification for the promotion.

        Returns:
            Updated trust record.

        Raises:
            ValueError: If the promotion is not valid.
        """
        record = self.get_or_create(asset_id)

        if record.state == AssetState.SUSPENDED:
            raise ValueError(f"Cannot promote suspended asset {asset_id}")

        if target == TrustLevel.NATIVE:
            raise ValueError("Cannot promote to NATIVE -- reserved for built-in assets")

        if not _can_promote(record.trust_level, target):
            valid = [t.name for t in _VALID_PROMOTIONS.get(record.trust_level, set())]
            raise ValueError(
                f"Cannot promote {asset_id} from {record.trust_level.name}"
                f" to {target.name}. Valid targets: {valid}"
            )

        old_level = record.trust_level
        record.trust_level = target
        record.last_review = datetime.now(UTC)
        record.history.append(
            TrustEvent(
                asset_id=asset_id,
                action="promote",
                from_level=old_level,
                to_level=target,
                reason=reason,
            )
        )
        return record

    def demote(self, asset_id: str, target: TrustLevel, reason: str) -> TrustRecord:
        """Demote an asset to a lower trust level.

        Args:
            asset_id: Asset identifier.
            target: Target trust level (must be lower than current).
            reason: Justification for the demotion.

        Returns:
            Updated trust record.

        Raises:
            ValueError: If the target is not lower than the current level.
        """
        record = self.get_or_create(asset_id)

        if target >= record.trust_level:
            raise ValueError(
                f"Demotion target {target.name} must be lower than "
                f"current level {record.trust_level.name}"
            )

        old_level = record.trust_level
        record.trust_level = target
        record.history.append(
            TrustEvent(
                asset_id=asset_id,
                action="demote",
                from_level=old_level,
                to_level=target,
                reason=reason,
            )
        )
        return record

    def suspend(self, asset_id: str, reason: str) -> TrustRecord:
        """Suspend an asset due to a security concern.

        Args:
            asset_id: Asset identifier.
            reason: Reason for suspension.

        Returns:
            Updated trust record.

        Raises:
            ValueError: If asset is already suspended.
        """
        record = self.get_or_create(asset_id)

        if record.state == AssetState.SUSPENDED:
            raise ValueError(f"Asset {asset_id} is already suspended")

        record.state = AssetState.SUSPENDED
        record.history.append(
            TrustEvent(
                asset_id=asset_id,
                action="suspend",
                from_level=record.trust_level,
                to_level=record.trust_level,
                reason=reason,
            )
        )
        return record

    def restore(self, asset_id: str, reason: str) -> TrustRecord:
        """Restore a suspended asset back to active state.

        Args:
            asset_id: Asset identifier.
            reason: Reason for restoration.

        Returns:
            Updated trust record.

        Raises:
            ValueError: If asset is not suspended.
        """
        record = self.get_or_create(asset_id)

        if record.state != AssetState.SUSPENDED:
            raise ValueError(f"Asset {asset_id} is not suspended")

        record.state = AssetState.ACTIVE
        record.history.append(
            TrustEvent(
                asset_id=asset_id,
                action="restore",
                from_level=record.trust_level,
                to_level=record.trust_level,
                reason=reason,
            )
        )
        return record

    def all_records(self) -> list[TrustRecord]:
        """Return all trust records sorted by asset_id."""
        return sorted(self._records.values(), key=lambda r: r.asset_id)

    def records_at_level(self, level: TrustLevel) -> list[TrustRecord]:
        """Return all records at a specific trust level."""
        return [r for r in self.all_records() if r.trust_level == level]


def log_trust_event(log_path: Path, event: TrustEvent) -> None:
    """Append a trust event to the audit log.

    Args:
        log_path: Path to the JSONL audit log file.
        event: Trust event to log.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")
