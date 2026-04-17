import hashlib
import logging
import tempfile
from pathlib import Path

from agentguard.attestation.models import AttestationRecord, sign_fingerprint
from agentguard.attestation.signing import load_or_create_signing_key
from agentguard.attestation.store import AttestationStore
from agentguard.sandbox.capture import events_to_fingerprint
from agentguard.sandbox.corpus import PromptCorpus, load_universal_corpus
from agentguard.sandbox.drivers import DriverEvent, HarnessDriver
from agentguard.security.trust import TrustLevel

logger = logging.getLogger(__name__)


class SandboxEngine:
    """Orchestrates behavioral sandbox replay (BSR) for a single asset."""

    def __init__(
        self,
        driver: HarnessDriver,
        corpus: PromptCorpus | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._driver = driver
        self._corpus = corpus or load_universal_corpus()
        self._timeout = timeout_seconds

    def attest(
        self,
        asset_path: Path,
        signing_key_path: Path,
        harness: str = "claude-code",
        trust_level: TrustLevel = TrustLevel.UNTRUSTED,
        store: AttestationStore | None = None,
    ) -> AttestationRecord:
        """Run the corpus against ``asset_path`` and return a signed attestation.

        Args:
            asset_path: Path to the agent asset to attest.
            signing_key_path: Path to the ed25519 private signing key.
            harness: Harness identifier recorded on the attestation.
            trust_level: Trust level to record. New attestations start
                UNTRUSTED by default; promotion is a separate workflow.
            store: Optional ``AttestationStore``; if None, one is created.

        Returns:
            The signed ``AttestationRecord``.
        """
        asset_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        corpus_hash = self._corpus.hash()

        all_events: list[DriverEvent] = []
        with tempfile.TemporaryDirectory(prefix="agentguard-bsr-") as tmp:
            workdir = Path(tmp)
            for probe in self._corpus.probes:
                events = self._driver.run_probe(
                    asset_path=asset_path,
                    workdir=workdir,
                    probe=probe.prompt,
                    timeout=self._timeout,
                )
                all_events.extend(events)

        fingerprint = events_to_fingerprint(all_events)

        key = load_or_create_signing_key(signing_key_path)
        record = sign_fingerprint(
            fingerprint=fingerprint,
            asset_content_hash=asset_hash,
            harness=harness,
            corpus_hash=corpus_hash,
            signing_key=key,
            trust_level=trust_level,
        )

        (store or AttestationStore()).save(record)
        logger.info(
            "attested %s → fingerprint=%s",
            asset_path,
            record.fingerprint_hash[:16],
        )
        return record
