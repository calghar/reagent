import hashlib
import logging
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from agentguard.attestation.divergence import (
    DivergenceDetector,
    DivergenceFinding,
    DivergenceSeverity,
    IQRDivergenceDetector,
)
from agentguard.attestation.fingerprint import BehavioralFingerprint
from agentguard.attestation.models import AttestationRecord
from agentguard.sandbox.capture import events_to_fingerprint
from agentguard.sandbox.corpus import PromptCorpus, load_universal_corpus
from agentguard.sandbox.drivers import DriverEvent, HarnessDriver

logger = logging.getLogger(__name__)


class CounterfactualResult(BaseModel):
    """Outcome of comparing a proposed asset revision to an attested baseline."""

    new_asset_content_hash: str
    new_fingerprint: BehavioralFingerprint
    new_fingerprint_hash: str
    baseline_asset_content_hash: str
    baseline_fingerprint_hash: str
    divergence_findings: list[DivergenceFinding] = Field(default_factory=list)
    blocks_merge: bool = False


class CounterfactualGate:
    """Run a proposed asset revision through sandbox replay and compare to baseline.

    Blocks a merge if any CRITICAL or HIGH divergence is detected — these
    represent behavioral expansions (new egress host, new hook subprocess,
    new tool call) that a static scanner cannot catch.
    """

    def __init__(
        self,
        driver: HarnessDriver,
        corpus: PromptCorpus | None = None,
        detector: DivergenceDetector | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._driver = driver
        self._corpus = corpus or load_universal_corpus()
        self._detector = detector or IQRDivergenceDetector()
        self._timeout = timeout_seconds

    def evaluate(
        self,
        baseline: AttestationRecord,
        new_asset_path: Path,
    ) -> CounterfactualResult:
        """Return a ``CounterfactualResult`` for ``new_asset_path`` vs ``baseline``."""
        new_hash = hashlib.sha256(new_asset_path.read_bytes()).hexdigest()
        new_fingerprint = self._replay(new_asset_path)
        findings = self._detector.check(
            attested=baseline.fingerprint,
            live=new_fingerprint,
            asset_content_hash=new_hash,
        )
        blocks = any(
            f.severity in (DivergenceSeverity.CRITICAL, DivergenceSeverity.HIGH)
            for f in findings
        )
        return CounterfactualResult(
            new_asset_content_hash=new_hash,
            new_fingerprint=new_fingerprint,
            new_fingerprint_hash=new_fingerprint.content_hash(),
            baseline_asset_content_hash=baseline.asset_content_hash,
            baseline_fingerprint_hash=baseline.fingerprint_hash,
            divergence_findings=findings,
            blocks_merge=blocks,
        )

    def _replay(self, asset_path: Path) -> BehavioralFingerprint:
        events: list[DriverEvent] = []
        with tempfile.TemporaryDirectory(prefix="agentguard-crg-") as tmp:
            workdir = Path(tmp)
            for probe in self._corpus.probes:
                events.extend(
                    self._driver.run_probe(
                        asset_path=asset_path,
                        workdir=workdir,
                        probe=probe.prompt,
                        timeout=self._timeout,
                    )
                )
        return events_to_fingerprint(events)
