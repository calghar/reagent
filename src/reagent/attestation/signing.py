import base64
import hashlib
import logging
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)


def load_or_create_signing_key(path: Path) -> Ed25519PrivateKey:
    """Load a PEM-encoded ed25519 private key, generating one if missing.

    Args:
        path: Filesystem path to the signing key file.

    Returns:
        Loaded or newly generated ed25519 private key.
    """
    if path.exists():
        pem_bytes = path.read_bytes()
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path} is not an ed25519 private key")
        return key

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    try:
        os.chmod(path, 0o600)  # noqa: PTH101
    except OSError as exc:
        logger.warning("Could not chmod 0600 on %s: %s", path, exc)
    return key


def public_key_fingerprint(
    key: Ed25519PrivateKey | Ed25519PublicKey,
) -> str:
    """Return a short fingerprint for the public half of ``key``.

    Args:
        key: Private or public ed25519 key.

    Returns:
        First 16 hex characters of the sha256 of the raw public key bytes.
    """
    if isinstance(key, Ed25519PrivateKey):
        public = key.public_key()
    else:
        public = key
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()[:16]


def sign_bytes(key: Ed25519PrivateKey, data: bytes) -> str:
    """Sign ``data`` with ``key`` and return a base64-encoded signature."""
    signature = key.sign(data)
    return base64.b64encode(signature).decode("ascii")


def verify_bytes(public_key: Ed25519PublicKey, data: bytes, signature_b64: str) -> bool:
    """Verify a base64-encoded signature against ``data``.

    Args:
        public_key: Ed25519 public key used for verification.
        data: Original bytes that were signed.
        signature_b64: Base64-encoded signature to check.

    Returns:
        True if the signature is valid, False otherwise.
    """
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, data)
    except (InvalidSignature, ValueError, TypeError) as exc:
        logger.debug("Signature verification failed: %s", exc)
        return False
    return True
