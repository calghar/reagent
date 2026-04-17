import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from agentguard.attestation.divergence import DivergenceFinding, DivergenceSeverity
from agentguard.storage import AgentGuardDB

logger = logging.getLogger(__name__)


_INSERT_SQL = """
INSERT INTO divergence_findings (
    finding_id, asset_content_hash, fingerprint_hash, dimension, kind,
    observed_json, observed_value, attested_low, attested_high,
    severity, mitre_atlas_json, detected_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class DivergenceStore:
    """SQLite-backed store for ``DivergenceFinding`` records."""

    def __init__(self, db: AgentGuardDB | None = None) -> None:
        self._db = db or AgentGuardDB()

    def _conn(self) -> sqlite3.Connection:
        return self._db.connect()

    def save(self, finding: DivergenceFinding) -> str:
        """Persist a divergence finding and return the generated finding_id."""
        conn = self._conn()
        finding_id = str(uuid.uuid4())
        lo, hi = finding.attested_range if finding.attested_range else (None, None)
        conn.execute(
            _INSERT_SQL,
            (
                finding_id,
                finding.asset_content_hash,
                finding.fingerprint_hash,
                finding.dimension,
                finding.kind,
                json.dumps(finding.observed),
                finding.observed_value,
                lo,
                hi,
                finding.severity.value,
                json.dumps(finding.mitre_atlas),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        return finding_id

    def list_for_asset(self, asset_content_hash: str) -> list[DivergenceFinding]:
        """Return divergence findings for ``asset_content_hash``, newest first."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM divergence_findings WHERE asset_content_hash = ? "
            "ORDER BY detected_at DESC",
            (asset_content_hash,),
        ).fetchall()
        return [_row_to_finding(row) for row in rows]


def _row_to_finding(row: Any) -> DivergenceFinding:
    attested_range: tuple[float, float] | None = None
    if row["attested_low"] is not None and row["attested_high"] is not None:
        attested_range = (float(row["attested_low"]), float(row["attested_high"]))
    return DivergenceFinding(
        asset_content_hash=row["asset_content_hash"],
        fingerprint_hash=row["fingerprint_hash"],
        dimension=row["dimension"],
        kind=row["kind"],
        observed=json.loads(row["observed_json"]),
        observed_value=row["observed_value"],
        attested_range=attested_range,
        severity=DivergenceSeverity(row["severity"]),
        mitre_atlas=json.loads(row["mitre_atlas_json"]),
    )
