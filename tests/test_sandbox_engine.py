from pathlib import Path

import pytest

from reagent.attestation.store import AttestationStore
from reagent.sandbox.corpus import Probe, PromptCorpus
from reagent.sandbox.drivers import DriverEvent, DriverEventKind, MockDriver
from reagent.sandbox.engine import SandboxEngine
from reagent.storage import ReagentDB


def _tool_event(name: str, **args: object) -> DriverEvent:
    return DriverEvent(
        kind=DriverEventKind.TOOL_CALL,
        tool_name=name,
        tool_args=dict(args),
    )


def _tokens(inp: int, out: int) -> DriverEvent:
    return DriverEvent(
        kind=DriverEventKind.TOKEN_USAGE,
        input_tokens=inp,
        output_tokens=out,
    )


def _build_engine(tmp_path: Path) -> tuple[SandboxEngine, AttestationStore]:
    corpus = PromptCorpus(
        probes=[
            Probe(id="p1", prompt="probe-1"),
            Probe(id="p2", prompt="probe-2"),
        ]
    )
    scripted = {
        "probe-1": [
            _tool_event("Read", path="README.md"),
            _tool_event("WebFetch", url="https://api.anthropic.com/v1/messages"),
            _tokens(100, 40),
        ],
        "probe-2": [
            _tool_event("Bash", command="git status"),
            _tool_event("Write", file_path="src/a.py"),
            _tokens(200, 60),
        ],
    }
    driver = MockDriver(scripted=scripted)
    db = ReagentDB(tmp_path / "reagent.db")
    store = AttestationStore(db=db)
    engine = SandboxEngine(driver=driver, corpus=corpus, timeout_seconds=1)
    return engine, store


@pytest.fixture()
def asset_file(tmp_path: Path) -> Path:
    path = tmp_path / "skill.md"
    path.write_text("# demo skill\nA trivial asset for attestation tests.\n")
    return path


def test_mock_driver_produces_fingerprint(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_path = tmp_path / "key.pem"
    monkeypatch.setenv("REAGENT_DB_PATH", str(tmp_path / "reagent.db"))
    engine, store = _build_engine(tmp_path)
    record = engine.attest(
        asset_path=asset_file,
        signing_key_path=key_path,
        store=store,
    )
    fp = record.fingerprint
    assert "Read:path" in fp.tool_calls
    assert "Bash:command" in fp.tool_calls
    assert "Write:file_path" in fp.tool_calls
    assert "api.anthropic.com" in fp.egress_hosts
    assert any("src/" in w for w in fp.file_writes)
    assert fp.token_profile["input_count"] == 2


def test_fingerprint_deterministic_across_runs(
    asset_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REAGENT_DB_PATH", str(tmp_path / "reagent.db"))
    key_path = tmp_path / "key.pem"
    engine_a, store_a = _build_engine(tmp_path / "a")
    engine_b, store_b = _build_engine(tmp_path / "b")
    record_a = engine_a.attest(asset_file, key_path, store=store_a)
    record_b = engine_b.attest(asset_file, key_path, store=store_b)
    assert record_a.fingerprint_hash == record_b.fingerprint_hash
