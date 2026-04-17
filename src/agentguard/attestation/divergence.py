import enum
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from agentguard.attestation.fingerprint import BehavioralFingerprint

logger = logging.getLogger(__name__)


_SET_DIMENSIONS = ("tool_calls", "egress_hosts", "file_writes", "hook_subprocess")

# MITRE ATLAS tags for each divergence dimension.
_DIMENSION_ATLAS: dict[str, list[str]] = {
    "tool_calls": ["AML.T0011"],
    "egress_hosts": ["AML.T0024", "AML.T0025"],
    "file_writes": ["AML.T0025"],
    "hook_subprocess": ["AML.T0010", "AML.T0050"],
    "token_profile_output": ["AML.T0043", "AML.T0054"],
    "token_profile_input": ["AML.T0051"],
}


class DivergenceSeverity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


class DivergenceFinding(BaseModel):
    """A single runtime divergence against an attested fingerprint."""

    asset_content_hash: str
    fingerprint_hash: str
    dimension: str
    kind: str
    observed: list[str] = Field(default_factory=list)
    observed_value: float | None = None
    attested_range: tuple[float, float] | None = None
    severity: DivergenceSeverity = DivergenceSeverity.HIGH
    mitre_atlas: list[str] = Field(default_factory=list)


class DivergenceDetector(Protocol):
    """Detector comparing live observations against an attested fingerprint."""

    def check(
        self,
        attested: BehavioralFingerprint,
        live: BehavioralFingerprint,
        asset_content_hash: str,
    ) -> list[DivergenceFinding]: ...


class IQRDivergenceDetector:
    """Divergence detector using set membership and IQR outlier thresholds.

    For the four set-valued dimensions (tool calls, egress hosts, file
    writes, hook subprocess), any element present in ``live`` but absent
    from ``attested`` is reported. For ``token_profile``, the detector
    flags any observed mean/std that falls outside ``[Q1 - k*IQR,
    Q3 + k*IQR]`` where ``k`` defaults to 1.5.
    """

    def __init__(self, k: float = 1.5) -> None:
        self._k = k

    def check(
        self,
        attested: BehavioralFingerprint,
        live: BehavioralFingerprint,
        asset_content_hash: str,
    ) -> list[DivergenceFinding]:
        findings: list[DivergenceFinding] = []
        fp_hash = attested.content_hash()

        for dim in _SET_DIMENSIONS:
            new = sorted(set(getattr(live, dim)) - set(getattr(attested, dim)))
            if new:
                findings.append(
                    DivergenceFinding(
                        asset_content_hash=asset_content_hash,
                        fingerprint_hash=fp_hash,
                        dimension=dim,
                        kind="new_element",
                        observed=new,
                        severity=_severity_for(dim),
                        mitre_atlas=list(_DIMENSION_ATLAS.get(dim, [])),
                    )
                )

        findings.extend(
            self._check_token_profile(attested, live, asset_content_hash, fp_hash)
        )
        return findings

    def _check_token_profile(
        self,
        attested: BehavioralFingerprint,
        live: BehavioralFingerprint,
        asset_content_hash: str,
        fp_hash: str,
    ) -> list[DivergenceFinding]:
        findings: list[DivergenceFinding] = []
        pairs = (
            ("output_mean", "token_profile_output"),
            ("input_mean", "token_profile_input"),
        )
        for stat_key, dim_key in pairs:
            attested_mean = attested.token_profile.get(stat_key)
            attested_std = attested.token_profile.get(
                stat_key.replace("mean", "std"), 0.0
            )
            observed = live.token_profile.get(stat_key)
            if attested_mean is None or observed is None:
                continue
            lo, hi = _iqr_bounds(attested_mean, attested_std, self._k)
            if observed < lo or observed > hi:
                findings.append(
                    DivergenceFinding(
                        asset_content_hash=asset_content_hash,
                        fingerprint_hash=fp_hash,
                        dimension=dim_key,
                        kind="outlier",
                        observed_value=observed,
                        attested_range=(lo, hi),
                        severity=DivergenceSeverity.MEDIUM,
                        mitre_atlas=list(_DIMENSION_ATLAS.get(dim_key, [])),
                    )
                )
        return findings


def _severity_for(dimension: str) -> DivergenceSeverity:
    if dimension in ("egress_hosts", "hook_subprocess"):
        return DivergenceSeverity.CRITICAL
    if dimension == "tool_calls":
        return DivergenceSeverity.HIGH
    return DivergenceSeverity.MEDIUM


def _iqr_bounds(mean: float, std: float, k: float) -> tuple[float, float]:
    # With only mean/std at hand we approximate Q1/Q3 as mean ∓ 0.6745*std
    # (the normal-distribution quartile offset). IQR = 2 * 0.6745 * std.
    q_offset = 0.6745 * std
    q1 = mean - q_offset
    q3 = mean + q_offset
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr
