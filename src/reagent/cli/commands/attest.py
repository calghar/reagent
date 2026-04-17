import hashlib
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group()
def attest() -> None:
    """Behavioral attestation for agent-configuration assets."""


@attest.command("verify")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
def verify_cmd(asset_path: Path) -> None:
    """Verify the latest stored attestation for ASSET_PATH."""
    from rich.console import Console

    from reagent.attestation import (
        AttestationStore,
        load_or_create_signing_key,
        verify_attestation,
    )
    from reagent.config import ReagentConfig

    console = Console()
    config = ReagentConfig.load()

    content = asset_path.read_bytes()
    asset_hash = hashlib.sha256(content).hexdigest()

    record = AttestationStore().get_by_asset_hash(asset_hash)
    if record is None:
        console.print(f"[yellow]No attestation found for {asset_path}[/yellow]")
        raise SystemExit(1)

    key = load_or_create_signing_key(config.attestation.signing_key_path)
    ok = verify_attestation(record, key.public_key())

    status = "[green]VALID[/green]" if ok else "[red]INVALID[/red]"
    console.print(f"Attestation for {asset_path}: {status}")
    console.print(f"  signer_key_id: {record.signer_key_id}")
    console.print(f"  signed_at:     {record.signed_at.isoformat()}")
    console.print(f"  harness:       {record.harness}")
    console.print(f"  trust_level:   {record.trust_level.name}")
    console.print(f"  fingerprint:   {record.fingerprint_hash[:16]}…")
    raise SystemExit(0 if ok else 2)


@attest.command("run")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--harness",
    default="claude-code",
    show_default=True,
    help="Harness identifier recorded on the attestation.",
)
@click.option(
    "--claude-binary",
    default="claude",
    show_default=True,
    help="Path to the claude CLI binary used by the sandbox driver.",
)
@click.option(
    "--timeout",
    type=int,
    default=120,
    show_default=True,
    help="Per-probe timeout in seconds.",
)
def run_cmd(asset_path: Path, harness: str, claude_binary: str, timeout: int) -> None:
    """Run sandbox replay against ASSET_PATH and emit a signed attestation."""
    from rich.console import Console

    from reagent.attestation.store import AttestationStore
    from reagent.config import ReagentConfig
    from reagent.sandbox import ClaudeCodeDriver, SandboxEngine

    console = Console()
    config = ReagentConfig.load()

    driver = ClaudeCodeDriver(claude_binary=claude_binary)
    engine = SandboxEngine(driver=driver, timeout_seconds=timeout)

    record = engine.attest(
        asset_path=asset_path,
        signing_key_path=config.attestation.signing_key_path,
        harness=harness,
        store=AttestationStore(),
    )

    console.print(f"[green]Attested[/green] {asset_path}")
    console.print(f"  asset_content_hash:  {record.asset_content_hash}")
    console.print(f"  fingerprint_hash:    {record.fingerprint_hash}")
    console.print(f"  signer_key_id:       {record.signer_key_id}")
    console.print(f"  harness:             {record.harness}")
    console.print(f"  trust_level:         {record.trust_level.name}")
    raise SystemExit(0)
