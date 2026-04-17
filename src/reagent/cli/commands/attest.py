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
def run_cmd(asset_path: Path) -> None:
    """Run sandbox replay and emit a signed attestation (wired in Chunk 3)."""
    from rich.console import Console

    Console().print(
        f"[yellow]reagent attest run[/yellow] not yet implemented for {asset_path} "
        "— sandbox engine lands in Chunk 3."
    )
    raise SystemExit(2)
