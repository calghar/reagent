import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from agentguard.cli._helpers import _configure_logging, _load_config
from agentguard.cli._helpers import _load_catalog as _load_catalog

logger = logging.getLogger(__name__)
console = Console()


@click.group()
@click.version_option(package_name="agentguard")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.option(
    "--log-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Log file path (default: ~/.agentguard/agentguard.log)",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, log_file: Path | None) -> None:
    """AgentGuard - behavioral attestation and runtime shield for AI agent assets."""
    ctx.ensure_object(dict)
    config = _load_config()
    _configure_logging(verbose, log_file, config)
    ctx.obj["config"] = config


def main() -> int:
    """Main entry point for the agentguard CLI."""
    try:
        cli(standalone_mode=False)
    except click.UsageError as exc:
        args = sys.argv[1:]
        if args and Path(args[0]).exists():
            path = Path(args[0])
            console.print(f"[red]Error:[/red] {exc}")
            console.print(
                f"\n[yellow]Did you mean one of these?[/yellow]\n"
                f"  agentguard inventory --repo {path}\n"
                f"  agentguard scan {path}\n"
                f"  agentguard evaluate --repo {path}\n"
            )
            return 1
        console.print(f"[red]Error:[/red] {exc}")
        console.print("Run [bold]agentguard --help[/bold] for available commands.")
        return 1
    except click.exceptions.Exit:
        pass
    return 0


# inventory / catalog / show / harnesses / evaluate
from agentguard.cli.commands.assets import (  # noqa: E402
    catalog_cmd,
    evaluate_cmd,
    harnesses_cmd,
    inventory,
    show_item,
)

cli.add_command(inventory)
cli.add_command(catalog_cmd)
cli.add_command(show_item)
cli.add_command(harnesses_cmd)
cli.add_command(evaluate_cmd)

# security (scan, audit, import, trust, integrity, history, rollback)
from agentguard.cli.commands.security import (  # noqa: E402
    audit_cmd,
    history_cmd,
    import_cmd,
    integrity,
    rollback_cmd,
    scan_cmd,
    trust,
)

cli.add_command(scan_cmd)
cli.add_command(audit_cmd)
cli.add_command(import_cmd)
cli.add_command(history_cmd)
cli.add_command(rollback_cmd)
cli.add_command(trust)
cli.add_command(integrity)

# CI commands
from agentguard.cli.commands.ci import ci_cmd, drift_cmd  # noqa: E402

cli.add_command(ci_cmd)
cli.add_command(drift_cmd)

# attestation
from agentguard.cli.commands.attest import attest  # noqa: E402

cli.add_command(attest)

# runtime divergence
from agentguard.cli.commands.diverge import diverge  # noqa: E402

cli.add_command(diverge)

# counterfactual replay gate
from agentguard.cli.commands.counterfactual import counterfactual_cmd  # noqa: E402

cli.add_command(counterfactual_cmd)

# telemetry (HLOT attribute emission)
from agentguard.cli.commands.telemetry_cmd import telemetry  # noqa: E402

cli.add_command(telemetry)

# BATT runtime shield
from agentguard.cli.commands.shield import shield  # noqa: E402

cli.add_command(shield)


if __name__ == "__main__":
    sys.exit(main())
