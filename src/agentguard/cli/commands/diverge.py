import hashlib
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group()
def diverge() -> None:
    """Runtime behavioral divergence detection."""


@diverge.command("check")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--live-fingerprint",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to a JSON file containing the live BehavioralFingerprint.",
)
@click.option(
    "--save/--no-save",
    default=True,
    show_default=True,
    help="Persist findings to the divergence store.",
)
def check_cmd(asset_path: Path, live_fingerprint: Path, save: bool) -> None:
    """Compare a live fingerprint to the attested baseline for ASSET_PATH."""
    from rich.console import Console
    from rich.table import Table

    from agentguard.attestation import (
        AttestationStore,
        BehavioralFingerprint,
        DivergenceStore,
        IQRDivergenceDetector,
    )

    console = Console()
    asset_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()

    attestation = AttestationStore().get_by_asset_hash(asset_hash)
    if attestation is None:
        console.print(f"[red]No attestation for {asset_path}[/red]")
        raise SystemExit(1)

    live = BehavioralFingerprint.model_validate_json(
        live_fingerprint.read_text(encoding="utf-8")
    )

    findings = IQRDivergenceDetector().check(
        attested=attestation.fingerprint,
        live=live,
        asset_content_hash=asset_hash,
    )

    if not findings:
        console.print("[green]No divergence detected[/green]")
        raise SystemExit(0)

    store = DivergenceStore() if save else None
    table = Table(title="RFDD findings")
    table.add_column("Severity")
    table.add_column("Dimension")
    table.add_column("Kind")
    table.add_column("ATLAS")
    table.add_column("Detail")
    for finding in findings:
        detail = (
            ", ".join(finding.observed)
            if finding.observed
            else f"value={finding.observed_value} range={finding.attested_range}"
        )
        table.add_row(
            finding.severity.value,
            finding.dimension,
            finding.kind,
            ", ".join(finding.mitre_atlas),
            detail,
        )
        if store is not None:
            store.save(finding)
    console.print(table)
    raise SystemExit(2)
