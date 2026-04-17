import logging
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field, model_validator

from reagent.attestation.fingerprint import BehavioralFingerprint
from reagent.attestation.signing import (
    public_key_fingerprint,
    sign_bytes,
    verify_bytes,
)
from reagent.security.trust import TrustLevel

logger = logging.getLogger(__name__)


def _signing_payload(
    fingerprint: BehavioralFingerprint,
    asset_content_hash: str,
    corpus_hash: str,
) -> bytes:
    return (
        fingerprint.canonical_json()
        + asset_content_hash.encode("utf-8")
        + corpus_hash.encode("utf-8")
    )


class AttestationRecord(BaseModel):
    """Signed attestation binding a behavioural fingerprint to an asset."""

    asset_content_hash: str
    fingerprint: BehavioralFingerprint
    fingerprint_hash: str = ""
    signature: str
    signer_key_id: str
    signed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    harness: str
    corpus_hash: str
    trust_level: TrustLevel = TrustLevel.UNTRUSTED

    @model_validator(mode="after")
    def _ensure_fingerprint_hash(self) -> "AttestationRecord":
        computed = self.fingerprint.content_hash()
        if not self.fingerprint_hash:
            self.fingerprint_hash = computed
        return self


def sign_fingerprint(
    fingerprint: BehavioralFingerprint,
    asset_content_hash: str,
    harness: str,
    corpus_hash: str,
    signing_key: Ed25519PrivateKey,
    trust_level: TrustLevel = TrustLevel.UNTRUSTED,
) -> AttestationRecord:
    """Build a signed ``AttestationRecord`` for the given fingerprint.

    Args:
        fingerprint: Behavioural fingerprint to attest.
        asset_content_hash: Hex sha256 of the asset's content.
        harness: Harness identifier (e.g. ``claude-code``).
        corpus_hash: Hex sha256 of the attestation prompt corpus.
        signing_key: Ed25519 private key used to sign.
        trust_level: Trust level to record with the attestation.

    Returns:
        A signed ``AttestationRecord``.
    """
    payload = _signing_payload(fingerprint, asset_content_hash, corpus_hash)
    signature = sign_bytes(signing_key, payload)
    key_id = public_key_fingerprint(signing_key)
    return AttestationRecord(
        asset_content_hash=asset_content_hash,
        fingerprint=fingerprint,
        fingerprint_hash=fingerprint.content_hash(),
        signature=signature,
        signer_key_id=key_id,
        harness=harness,
        corpus_hash=corpus_hash,
        trust_level=trust_level,
    )


def verify_attestation(record: AttestationRecord, public_key: Ed25519PublicKey) -> bool:
    """Verify an ``AttestationRecord`` against ``public_key``.

    Args:
        record: The attestation record to verify.
        public_key: Ed25519 public key expected to have signed the record.

    Returns:
        True if the signature and fingerprint hash are consistent.
    """
    if record.fingerprint_hash != record.fingerprint.content_hash():
        return False
    payload = _signing_payload(
        record.fingerprint, record.asset_content_hash, record.corpus_hash
    )
    return verify_bytes(public_key, payload, record.signature)
