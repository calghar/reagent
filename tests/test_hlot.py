from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentguard.attestation import (
    AttestationStore,
    BehavioralFingerprint,
    sign_fingerprint,
)
from agentguard.security.trust import TrustLevel
from agentguard.storage import AgentGuardDB
from agentguard.telemetry.hlot import (
    HLOT_CONTENT_HASH_KEY,
    HLOT_FINGERPRINT_HASH_KEY,
    HLOT_TRUST_TIER_KEY,
    HLOTNotAttestedError,
    compute_hlot_attributes,
    unattested_attributes,
)


@pytest.fixture()
def asset_file(tmp_path: Path) -> Path:
    path = tmp_path / "skill.md"
    path.write_text("# demo skill\nAttested behavior only.\n")
    return path


def test_hlot_attributes_populated(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    db_path = tmp_path / "agentguard.db"
    monkeypatch.setenv("AGENTGUARD_DB_PATH", str(db_path))
    store = AttestationStore(db=AgentGuardDB(db_path))

    fp = BehavioralFingerprint(
        tool_calls=["Read:path"],
        egress_hosts=["api.anthropic.com"],
        token_profile={"input_mean": 100.0, "input_count": 1.0, "input_std": 0.0},
    )
    asset_hash = hashlib.sha256(asset_file.read_bytes()).hexdigest()
    record = sign_fingerprint(
        fingerprint=fp,
        asset_content_hash=asset_hash,
        harness="claude-code",
        corpus_hash="b" * 64,
        signing_key=Ed25519PrivateKey.generate(),
        trust_level=TrustLevel.VERIFIED,
    )
    store.save(record)

    attrs = compute_hlot_attributes(asset_file, store=store)
    span_attrs = attrs.as_span_attributes()
    assert span_attrs[HLOT_CONTENT_HASH_KEY] == asset_hash
    assert span_attrs[HLOT_FINGERPRINT_HASH_KEY] == record.fingerprint_hash
    assert span_attrs[HLOT_TRUST_TIER_KEY] == "verified"


def test_unattested_asset_raises_and_fallback_works(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "agentguard.db"
    monkeypatch.setenv("AGENTGUARD_DB_PATH", str(db_path))
    store = AttestationStore(db=AgentGuardDB(db_path))

    with pytest.raises(HLOTNotAttestedError):
        compute_hlot_attributes(asset_file, store=store)

    fallback = unattested_attributes(asset_file)
    assert fallback.trust_tier == "untrusted"
    assert fallback.fingerprint_hash == ""
    assert len(fallback.content_hash) == 64
