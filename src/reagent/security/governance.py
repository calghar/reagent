import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from reagent.core.catalog import Catalog, CatalogEntry

logger = logging.getLogger(__name__)


class IntegrityResult(BaseModel):
    """Result of checking a single asset's integrity."""

    asset_id: str
    file_path: Path
    expected_hash: str
    actual_hash: str
    status: str = "ok"  # ok, modified, missing


class IntegrityReport(BaseModel):
    """Full integrity check report."""

    checked: int = 0
    ok: int = 0
    modified: list[IntegrityResult] = Field(default_factory=list)
    missing: list[IntegrityResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def clean(self) -> bool:
        return not self.modified and not self.missing


class IntegrityEvent(BaseModel):
    """A logged integrity event."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    asset_id: str
    file_path: str
    event_type: str  # check_ok, modified, missing
    expected_hash: str = ""
    actual_hash: str = ""


def check_integrity(catalog: Catalog) -> IntegrityReport:
    """Check all catalog assets against their recorded content hashes.

    Args:
        catalog: Loaded catalog with entries to verify.

    Returns:
        IntegrityReport with check results.
    """
    report = IntegrityReport()

    for entry in catalog.all_entries():
        report.checked += 1
        result = check_single_asset(entry)
        if result.status == "ok":
            report.ok += 1
        elif result.status == "modified":
            report.modified.append(result)
        elif result.status == "missing":
            report.missing.append(result)

    return report


def check_single_asset(entry: CatalogEntry) -> IntegrityResult:
    """Check a single asset's integrity.

    Args:
        entry: Catalog entry to verify.

    Returns:
        IntegrityResult with the check outcome.
    """
    file_path = entry.file_path
    if not file_path.exists():
        return IntegrityResult(
            asset_id=entry.asset_id,
            file_path=file_path,
            expected_hash=entry.content_hash,
            actual_hash="",
            status="missing",
        )

    content = file_path.read_text(encoding="utf-8")
    actual_hash = hashlib.sha256(content.encode()).hexdigest()

    status = "ok" if actual_hash == entry.content_hash else "modified"
    return IntegrityResult(
        asset_id=entry.asset_id,
        file_path=file_path,
        expected_hash=entry.content_hash,
        actual_hash=actual_hash,
        status=status,
    )


def log_integrity_event(log_path: Path, event: IntegrityEvent) -> None:
    """Append an integrity event to the audit log.

    Args:
        log_path: Path to the integrity log file.
        event: Event to log.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")


def run_integrity_check_with_logging(
    catalog: Catalog, log_path: Path
) -> IntegrityReport:
    """Check integrity and log all events.

    Args:
        catalog: Loaded catalog.
        log_path: Path to the integrity log file.

    Returns:
        IntegrityReport with check results.
    """
    report = check_integrity(catalog)

    for result in report.modified:
        log_integrity_event(
            log_path,
            IntegrityEvent(
                asset_id=result.asset_id,
                file_path=str(result.file_path),
                event_type="modified",
                expected_hash=result.expected_hash,
                actual_hash=result.actual_hash,
            ),
        )

    for result in report.missing:
        log_integrity_event(
            log_path,
            IntegrityEvent(
                asset_id=result.asset_id,
                file_path=str(result.file_path),
                event_type="missing",
                expected_hash=result.expected_hash,
            ),
        )

    return report
