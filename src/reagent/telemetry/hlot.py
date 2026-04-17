import hashlib
import logging
from pathlib import Path

from pydantic import BaseModel

from reagent.attestation.store import AttestationStore
from reagent.security.trust import TrustLevel

logger = logging.getLogger(__name__)


HLOT_NAMESPACE = "agentguard.asset"
HLOT_CONTENT_HASH_KEY = f"{HLOT_NAMESPACE}.content_hash"
HLOT_FINGERPRINT_HASH_KEY = f"{HLOT_NAMESPACE}.fingerprint_hash"
HLOT_TRUST_TIER_KEY = f"{HLOT_NAMESPACE}.trust_tier"


class HLOTAttributes(BaseModel):
    """Hash-Linked OpenTelemetry attributes for an agent-session span.

    The three attributes carried on every HLOT-enriched span bind the
    runtime event to a specific attested asset version.
    """

    content_hash: str
    fingerprint_hash: str
    trust_tier: str

    def as_span_attributes(self) -> dict[str, str]:
        """Return attributes keyed for direct use as OTel span attributes."""
        return {
            HLOT_CONTENT_HASH_KEY: self.content_hash,
            HLOT_FINGERPRINT_HASH_KEY: self.fingerprint_hash,
            HLOT_TRUST_TIER_KEY: self.trust_tier,
        }


class HLOTNotAttestedError(Exception):
    """Raised when no attestation record exists for the requested asset."""


def compute_hlot_attributes(
    asset_path: Path,
    store: AttestationStore | None = None,
) -> HLOTAttributes:
    """Compute HLOT attributes for ``asset_path`` from the attestation store.

    Args:
        asset_path: Path to the agent-configuration asset in use.
        store: Optional ``AttestationStore``; if None, one is created.

    Returns:
        Populated ``HLOTAttributes`` for the asset's latest attestation.

    Raises:
        HLOTNotAttestedError: If no attestation record exists for the asset's
            current content hash. Callers are expected to fall back to a
            trust tier of "untrusted" explicitly rather than proceed
            with empty attribution.
    """
    content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    record = (store or AttestationStore()).get_by_asset_hash(content_hash)
    if record is None:
        raise HLOTNotAttestedError(f"No attestation for {asset_path} ({content_hash})")
    return HLOTAttributes(
        content_hash=content_hash,
        fingerprint_hash=record.fingerprint_hash,
        trust_tier=record.trust_level.name.lower(),
    )


def unattested_attributes(asset_path: Path) -> HLOTAttributes:
    """Return HLOT attributes for an asset that has no attestation record.

    Unattested assets still carry a content hash so downstream systems
    can identify the version; trust_tier is pinned to UNTRUSTED.

    Args:
        asset_path: Path to the agent-configuration asset in use.

    Returns:
        ``HLOTAttributes`` with an empty fingerprint hash and trust_tier
        set to ``untrusted``.
    """
    content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    return HLOTAttributes(
        content_hash=content_hash,
        fingerprint_hash="",
        trust_tier=TrustLevel.UNTRUSTED.name.lower(),
    )
