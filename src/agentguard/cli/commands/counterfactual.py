import hashlib
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.command("counterfactual")
@click.argument("new_asset_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--baseline-hash",
    type=str,
    default=None,
    help=(
        "Content hash of the prior-approved asset version to compare against. "
        "If omitted, the command looks up the latest attestation matching the "
        "new asset's path name."
    ),
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
def counterfactual_cmd(
    new_asset_path: Path,
    baseline_hash: str | None,
    claude_binary: str,
    timeout: int,
) -> None:
    """Replay NEW_ASSET_PATH in the sandbox and compare to the attested baseline."""
    from rich.console import Console
    from rich.table import Table

    from agentguard.attestation import (
        AttestationStore,
        CounterfactualGate,
    )
    from agentguard.sandbox import ClaudeCodeDriver

    console = Console()
    store = AttestationStore()

    baseline = None
    if baseline_hash:
        baseline = store.get_by_asset_hash(baseline_hash)
    else:
        new_hash = hashlib.sha256(new_asset_path.read_bytes()).hexdigest()
        baseline = store.get_by_asset_hash(new_hash)
    if baseline is None:
        console.print(
            "[red]No baseline attestation found — pass --baseline-hash "
            "or run `agentguard attest run` on the prior version first.[/red]"
        )
        raise SystemExit(1)

    gate = CounterfactualGate(
        driver=ClaudeCodeDriver(claude_binary=claude_binary),
        timeout_seconds=timeout,
    )
    result = gate.evaluate(baseline=baseline, new_asset_path=new_asset_path)

    if not result.divergence_findings:
        console.print("[green]No behavioral divergence from baseline[/green]")
        raise SystemExit(0)

    table = Table(title="CRG behavioral diff")
    table.add_column("Severity")
    table.add_column("Dimension")
    table.add_column("Kind")
    table.add_column("ATLAS")
    table.add_column("Detail")
    for finding in result.divergence_findings:
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
    console.print(table)

    if result.blocks_merge:
        console.print("[red]Merge blocked (exit 3): behavioral divergence[/red]")
        raise SystemExit(3)
    console.print("[yellow]Behavioral delta within tolerance[/yellow]")
    raise SystemExit(0)
