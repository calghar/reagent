import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


def _dedupe_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _recursive_sort(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _recursive_sort(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_recursive_sort(item) for item in obj]
    return obj


class BehavioralFingerprint(BaseModel):
    """Deterministic summary of an asset's observed runtime behaviour.

    Captures the five dimensions used by AgentGuard attestation:
    tool-call signatures, egress hostnames, file-write globs, token
    usage statistics, and hook subprocess argv signatures.
    """

    tool_calls: list[str] = Field(default_factory=list)
    egress_hosts: list[str] = Field(default_factory=list)
    file_writes: list[str] = Field(default_factory=list)
    token_profile: dict[str, float] = Field(default_factory=dict)
    hook_subprocess: list[str] = Field(default_factory=list)

    @field_validator(
        "tool_calls",
        "egress_hosts",
        "file_writes",
        "hook_subprocess",
        mode="before",
    )
    @classmethod
    def _normalize_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError(f"expected list, got {type(value).__name__}")
        return _dedupe_sorted([str(v) for v in value])

    def canonical_json(self) -> bytes:
        """Return deterministic UTF-8 JSON with sorted keys and no whitespace.

        Returns:
            Canonical byte representation of the fingerprint.
        """
        data = self.model_dump(mode="json")
        normalized = _recursive_sort(data)
        return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def content_hash(self) -> str:
        """Return sha256 hex digest of the canonical JSON.

        Returns:
            Hex-encoded sha256 of ``canonical_json()``.
        """
        return hashlib.sha256(self.canonical_json()).hexdigest()
