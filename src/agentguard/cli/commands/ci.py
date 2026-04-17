import logging
from pathlib import Path

import click
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


@click.command("ci")
@click.option(
    "--mode",
    type=click.Choice(["check", "suggest", "auto-fix"]),
    default="check",
    show_default=True,
    help="CI operating mode.",
)
@click.option(
    "--threshold",
    type=float,
    default=60.0,
    show_default=True,
    help="Minimum quality score (0-100).",
)
@click.option(
    "--security/--no-security",
    default=True,
    help="Enable security scanning.",
)
@click.option(
    "--repo",
    type=click.Path(path_type=Path),
    default=None,
    help="Repository path to evaluate (default: current directory).",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output JSON instead of text.",
)
def ci_cmd(
    mode: str,
    threshold: float,
    security: bool,
    repo: Path | None,
    output_json: bool,
) -> None:
    """Evaluate asset quality for CI pipelines.

    Exits with code 1 if assets are below threshold, 2 if security issues
    are found.
    """
    import json
    import os
    import sys

    from agentguard.ci import CIConfig, CIMode, CIRunner
    from agentguard.ci.reporter import CIReporter

    repo_path = (repo or Path.cwd()).resolve()
    config = CIConfig(
        repo_path=repo_path,
        mode=CIMode(mode),
        threshold=threshold,
        security=security,
        output_format="json" if output_json else "text",
    )

    try:
        result = CIRunner().run(config)
    except (OSError, ValueError) as exc:
        console.print(f"[red]CI run failed: {exc}[/red]")
        raise SystemExit(1) from None

    reporter = CIReporter()
    if output_json:
        click.echo(json.dumps(result.model_dump(), indent=2))
    elif mode == "suggest":
        click.echo(reporter.format_pr_comment(result))
    else:
        click.echo(reporter.format_check_output(result))

    # Emit GitHub Actions annotations when running inside Actions
    if os.environ.get("GITHUB_ACTIONS") == "true":
        annotations = reporter.format_github_annotations(result)
        for ann in annotations:
            level = ann.get("level", "warning")
            file_ = ann.get("file", "")
            message = ann.get("message", "")
            print(f"::{level} file={file_}::{message}", file=sys.stderr)

    raise SystemExit(result.exit_code)


@click.command("drift")
@click.option(
    "--repo",
    type=click.Path(path_type=Path),
    default=None,
    help="Repository path to check (default: current directory).",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output JSON instead of text.",
)
def drift_cmd(repo: Path | None, output_json: bool) -> None:
    """Detect stale, outdated, or missing assets."""
    import json

    from agentguard.ci.drift import DriftDetector

    repo_path = (repo or Path.cwd()).resolve()

    try:
        reports = DriftDetector().detect(repo_path)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Drift detection failed: {exc}[/red]")
        raise SystemExit(1) from None

    if output_json:
        click.echo(json.dumps([r.model_dump() for r in reports], indent=2))
        return

    if not reports:
        console.print("[green]No drift detected.[/green]")
        return

    console.print(f"[bold]Drift Report[/bold] — {len(reports)} issue(s) found\n")
    for report in reports:
        severity_color = {
            "error": "red",
            "warning": "yellow",
            "info": "cyan",
        }.get(report.severity, "white")
        console.print(
            f"[{severity_color}][{report.severity.upper()}][/{severity_color}] "
            f"[bold]{report.drift_type}[/bold] — {report.asset_path}"
        )
        console.print(f"  {report.details}\n")
