import logging
import sqlite3
from typing import Any

from reagent.attestation.fingerprint import BehavioralFingerprint
from reagent.attestation.models import AttestationRecord
from reagent.security.trust import TrustLevel
from reagent.storage import ReagentDB

logger = logging.getLogger(__name__)


_INSERT_SQL = """
INSERT OR REPLACE INTO attestations (
    asset_content_hash, fingerprint_hash, fingerprint_json,
    signature, signer_key_id, signed_at, harness, corpus_hash, trust_level
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class AttestationStore:
    """SQLite-backed store for signed ``AttestationRecord`` instances."""

    def __init__(self, db: ReagentDB | None = None) -> None:
        self._db = db or ReagentDB()

    def _conn(self) -> sqlite3.Connection:
        return self._db.connect()

    def save(self, record: AttestationRecord) -> None:
        """Persist an attestation record.

        Args:
            record: The record to insert or replace.
        """
        conn = self._conn()
        conn.execute(
            _INSERT_SQL,
            (
                record.asset_content_hash,
                record.fingerprint_hash,
                record.fingerprint.canonical_json().decode("utf-8"),
                record.signature,
                record.signer_key_id,
                record.signed_at.isoformat(),
                record.harness,
                record.corpus_hash,
                int(record.trust_level),
            ),
        )
        conn.commit()

    def get_by_asset_hash(self, h: str) -> AttestationRecord | None:
        """Return the most recent record with ``asset_content_hash == h``."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM attestations WHERE asset_content_hash = ? "
            "ORDER BY signed_at DESC LIMIT 1",
            (h,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def get_by_fingerprint_hash(self, h: str) -> AttestationRecord | None:
        """Return the most recent record with ``fingerprint_hash == h``."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM attestations WHERE fingerprint_hash = ? "
            "ORDER BY signed_at DESC LIMIT 1",
            (h,),
        ).fetchone()
        return _row_to_record(row) if row else None

    def list_all(self) -> list[AttestationRecord]:
        """Return all attestation records ordered by ``signed_at`` descending."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM attestations ORDER BY signed_at DESC"
        ).fetchall()
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> AttestationRecord:
    from datetime import datetime

    fingerprint = BehavioralFingerprint.model_validate_json(row["fingerprint_json"])
    return AttestationRecord(
        asset_content_hash=row["asset_content_hash"],
        fingerprint=fingerprint,
        fingerprint_hash=row["fingerprint_hash"],
        signature=row["signature"],
        signer_key_id=row["signer_key_id"],
        signed_at=datetime.fromisoformat(row["signed_at"]),
        harness=row["harness"],
        corpus_hash=row["corpus_hash"],
        trust_level=TrustLevel(int(row["trust_level"])),
    )
