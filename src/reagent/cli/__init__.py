import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from reagent.cli._helpers import _configure_logging, _load_config

# Re-export helpers so existing callers of ``from reagent.cli import X`` work.
from reagent.cli._helpers import _load_catalog as _load_catalog

logger = logging.getLogger(__name__)
console = Console()


@click.group()
@click.version_option(package_name="reagent")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.option(
    "--log-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Log file path (default: ~/.reagent/reagent.log)",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, log_file: Path | None) -> None:
    """Reagent - manage Claude Code assets across repositories."""
    ctx.ensure_object(dict)
    config = _load_config()
    _configure_logging(verbose, log_file, config)
    ctx.obj["config"] = config


def main() -> int:
    """Main entry point for the reagent CLI.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    try:
        cli(standalone_mode=False)
    except click.UsageError as exc:
        # Check if user passed a bare path like `reagent /some/path`
        args = sys.argv[1:]
        if args and Path(args[0]).exists():
            path = Path(args[0])
            console.print(f"[red]Error:[/red] {exc}")
            console.print(
                f"\n[yellow]Did you mean one of these?[/yellow]\n"
                f"  reagent inventory --repo {path}\n"
                f"  reagent analyze {path}\n"
                f"  reagent scan {path}\n"
                f"  reagent evaluate --repo {path}\n"
            )
            return 1
        console.print(f"[red]Error:[/red] {exc}")
        console.print("Run [bold]reagent --help[/bold] for available commands.")
        return 1
    except click.exceptions.Exit:
        pass
    return 0


# assets (inventory, catalog, show, suggest, profile, analyze,
#         harnesses, export, schema,
#         extract-patterns, apply-pattern, validate, evaluate,
#         check-regression, variant, compare, promote, rollback-best)
from reagent.cli.commands.assets import (  # noqa: E402
    analyze_cmd,
    apply_pattern_cmd,
    catalog_cmd,
    check_regression_cmd,
    compare_cmd,
    evaluate_cmd,
    export_cmd,
    extract_patterns_cmd,
    harnesses_cmd,
    inventory,
    profile,
    promote_cmd,
    rollback_best_cmd,
    schema_group,
    show_item,
    suggest,
    validate_cmd,
    variant_cmd,
)

cli.add_command(inventory)
cli.add_command(catalog_cmd)
cli.add_command(show_item)
cli.add_command(suggest)
cli.add_command(profile)
cli.add_command(analyze_cmd)
cli.add_command(harnesses_cmd)
cli.add_command(export_cmd)
cli.add_command(extract_patterns_cmd)
cli.add_command(apply_pattern_cmd)
cli.add_command(validate_cmd)
cli.add_command(evaluate_cmd)
cli.add_command(check_regression_cmd)
cli.add_command(variant_cmd)
cli.add_command(compare_cmd)
cli.add_command(promote_cmd)
cli.add_command(rollback_best_cmd)
cli.add_command(schema_group)

# security (scan, audit, import, trust, integrity, history, rollback)
from reagent.cli.commands.security import (  # noqa: E402
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

# instincts group
from reagent.cli.commands.instincts import instincts_group  # noqa: E402

cli.add_command(instincts_group)

# CI commands
from reagent.cli.commands.ci import ci_cmd, drift_cmd  # noqa: E402

cli.add_command(ci_cmd)
cli.add_command(drift_cmd)

# attestation commands
from reagent.cli.commands.attest import attest  # noqa: E402

cli.add_command(attest)


if __name__ == "__main__":
    sys.exit(main())
