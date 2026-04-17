from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from reagent.attestation import (
    BehavioralFingerprint,
    sign_fingerprint,
    verify_attestation,
)
from reagent.security.trust import TrustLevel


def _fp(**overrides: object) -> BehavioralFingerprint:
    base: dict[str, object] = {
        "tool_calls": ["Read:path", "Write:path"],
        "egress_hosts": ["api.anthropic.com"],
        "file_writes": ["src/**/*.py"],
        "token_profile": {
            "input_mean": 120.0,
            "input_std": 4.0,
            "output_mean": 80.0,
            "output_std": 3.0,
            "output_count": 10.0,
        },
        "hook_subprocess": ["bash:-c:echo"],
    }
    base.update(overrides)
    return BehavioralFingerprint(**base)  # type: ignore[arg-type]


def test_canonical_hash_stable() -> None:
    a = _fp()
    b = _fp()
    assert a.content_hash() == b.content_hash()


def test_canonical_hash_is_order_insensitive() -> None:
    a = _fp(tool_calls=["Read:path", "Write:path"], egress_hosts=["api.anthropic.com"])
    b = _fp(tool_calls=["Write:path", "Read:path"], egress_hosts=["api.anthropic.com"])
    assert a.content_hash() == b.content_hash()


def test_sign_verify_roundtrip() -> None:
    key = Ed25519PrivateKey.generate()
    fp = _fp()
    record = sign_fingerprint(
        fingerprint=fp,
        asset_content_hash="a" * 64,
        harness="claude-code",
        corpus_hash="b" * 64,
        signing_key=key,
        trust_level=TrustLevel.REVIEWED,
    )
    assert verify_attestation(record, key.public_key())

    tampered = record.model_copy(update={"asset_content_hash": "c" * 64})
    assert not verify_attestation(tampered, key.public_key())
