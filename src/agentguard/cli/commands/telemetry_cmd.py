import json
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group()
def telemetry() -> None:
    """Runtime telemetry helpers (HLOT attribute emission)."""


@telemetry.command("hlot")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--fallback-unattested/--strict",
    default=True,
    show_default=True,
    help=(
        "When true, emit attributes with trust_tier=untrusted and empty "
        "fingerprint hash if the asset has no attestation record. "
        "When false, exit with code 2 instead."
    ),
)
def hlot_cmd(asset_path: Path, fallback_unattested: bool) -> None:
    """Emit HLOT span attributes for ASSET_PATH as a one-line JSON object.

    Intended to be called from a Claude Code PreToolUse hook or any OTel
    exporter that needs to stamp spans with AgentGuard identity.
    """
    from agentguard.telemetry.hlot import (
        HLOTNotAttestedError,
        compute_hlot_attributes,
        unattested_attributes,
    )

    try:
        attrs = compute_hlot_attributes(asset_path)
    except HLOTNotAttestedError:
        if not fallback_unattested:
            click.echo(
                json.dumps({"error": "not_attested", "asset_path": str(asset_path)}),
                err=True,
            )
            raise SystemExit(2) from None
        attrs = unattested_attributes(asset_path)

    click.echo(json.dumps(attrs.as_span_attributes(), sort_keys=True))
