import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from agentguard.cli._helpers import _load_catalog, _load_config
from agentguard.core.parsers import AssetType

logger = logging.getLogger(__name__)
console = Console()


def _show_repo_security_grade(repo: Path) -> None:
    """Scan the repo's .claude/ directory and display the aggregate security grade."""
    from agentguard.security.scanner import scan_directory, score_report

    claude_dir = repo / ".claude"
    if not claude_dir.exists():
        return

    sec_report = scan_directory(claude_dir)
    score, grade = score_report(sec_report)
    grade_color = (
        "green" if grade in ("A", "B") else "yellow" if grade == "C" else "red"
    )
    issue_count = len(sec_report.findings)
    console.print(
        f"\n[bold]Security Grade:[/bold] [{grade_color}]{grade}[/{grade_color}]"
        f" (score: {score:.0f}/100, {issue_count} issue(s))"
    )


def _show_asset(asset_id: str) -> None:
    """Show detailed view of a single asset."""
    config = _load_config()
    catalog = _load_catalog(config)

    entry = catalog.get(asset_id)
    if not entry:
        console.print(f"[red]Asset not found:[/red] {asset_id}")
        raise SystemExit(1)

    console.print(f"[bold cyan]{entry.asset_id}[/bold cyan]")
    console.print(f"  Type:       {entry.asset_type.value}")
    console.print(f"  Name:       {entry.name}")
    console.print(f"  Scope:      {entry.scope.value}")
    console.print(f"  Repo:       {entry.repo_path}")
    console.print(f"  File:       {entry.file_path}")
    console.print(f"  Hash:       {entry.content_hash}")
    console.print(f"  Trust:      {entry.trust_level}")
    console.print(f"  First seen: {entry.first_seen.isoformat()}")
    console.print(f"  Last seen:  {entry.last_seen.isoformat()}")

    if entry.metadata:
        console.print("\n  [bold]Metadata:[/bold]")
        for key, value in entry.metadata.items():
            console.print(f"    {key}: {value}")


@click.command()
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    help="Scan a single repo or parent directory",
)
def inventory(repo: Path | None) -> None:
    """Scan for Claude Code assets and update the catalog."""
    from agentguard.core.inventory import run_inventory, scan_path

    config = _load_config()
    catalog = _load_catalog(config)

    if repo:
        repo = repo.resolve()
        logger.info("Inventory scan of %s", repo)

        repo_entries = scan_path(
            repo,
            max_depth=config.scan.max_depth,
            exclude_patterns=config.scan.exclude_patterns,
        )

        if not repo_entries:
            console.print(f"[yellow]No Claude assets found under {repo}[/yellow]")
            console.print(
                "Tip: ensure repos have a .claude/ directory or CLAUDE.md file."
            )
            return

        total_added = 0
        total_modified = 0
        for repo_path, entries in repo_entries.items():
            added, modified, removed_ids = catalog.diff_repo(entries, repo_path)
            catalog.apply_diff(added, modified, removed_ids)
            total_added += len(added)
            total_modified += len(modified)
            if len(repo_entries) > 1:
                console.print(
                    f"  [cyan]{repo_path.name}[/cyan]: "
                    f"{len(entries)} assets ({len(added)} new,"
                    f" {len(modified)} modified)"
                )

        catalog.save()
        total_assets = sum(len(e) for e in repo_entries.values())
        repo_label = (
            f"{len(repo_entries)} repo(s)" if len(repo_entries) > 1 else str(repo)
        )
        console.print(
            f"Scanned {repo_label}: "
            f"{total_assets} assets ({total_added} new, {total_modified} modified)"
        )
    else:
        console.print("Scanning configured roots...")
        added_count, modified_count, removed_count = run_inventory(config, catalog)
        total = catalog.count

        console.print(f"\nAssets found: {total}")
        counts = catalog.counts_by_type()
        parts = []
        for asset_type in AssetType:
            count = counts.get(asset_type, 0)
            if count > 0:
                parts.append(f"{asset_type.value}: {count}")
        if parts:
            console.print(f"  {', '.join(parts)}")

        if added_count or modified_count or removed_count:
            console.print(
                f"\nChanges: {added_count} added, {modified_count} modified, "
                f"{removed_count} removed"
            )


@click.command("catalog")
@click.option(
    "--type",
    "asset_type",
    type=click.Choice([t.value for t in AssetType]),
    help="Filter by type",
)
@click.option("--repo", help="Filter by repo name")
def catalog_cmd(asset_type: str | None, repo: str | None) -> None:
    """List all cataloged assets."""
    config = _load_config()
    catalog = _load_catalog(config)

    type_filter = AssetType(asset_type) if asset_type else None
    entries = catalog.query(asset_type=type_filter, repo_name=repo)

    if not entries:
        console.print("No assets in catalog. Run `agentguard inventory` first.")
        return

    table = Table(title="Cataloged Assets")
    table.add_column("Asset ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Repo", style="yellow")
    table.add_column("Hash", style="dim", max_width=12)

    for entry in entries:
        table.add_row(
            entry.asset_id,
            entry.asset_type.value,
            entry.repo_path.name,
            entry.content_hash[:12],
        )

    console.print(table)
    console.print(f"\nTotal: {len(entries)} assets")


@click.command("show")
@click.argument("asset_id")
def show_item(asset_id: str) -> None:
    """Show detailed view of an asset."""
    _show_asset(asset_id)


@click.command("harnesses")
def harnesses_cmd() -> None:
    """List supported harness formats."""
    from agentguard.harness import HarnessFormat

    table = Table(title="Supported Harness Formats")
    table.add_column("Format", style="cyan")
    table.add_column("Description", style="white")

    descriptions = {
        HarnessFormat.CLAUDE_CODE: (
            "Default. Claude Code (.claude/ directory structure)"
        ),
        HarnessFormat.CURSOR: "Cursor AI (.cursor/ directory, YAML rule frontmatter)",
        HarnessFormat.CODEX: (
            "OpenAI Codex (.codex/ + AGENTS.md instruction-based rules)"
        ),
        HarnessFormat.OPENCODE: (
            "OpenCode (.opencode/ directory, opencode.json plugins)"
        ),
        HarnessFormat.AGENTS_MD: "Universal AGENTS.md (read by all harnesses)",
    }
    for fmt in HarnessFormat:
        table.add_row(fmt.value, descriptions.get(fmt, ""))

    console.print(table)


@click.command("evaluate")
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository to evaluate",
)
def evaluate_cmd(repo: Path) -> None:
    """Compute quality scores for all assets in a repository."""
    from agentguard.evaluation.evaluator import QualityLabel, evaluate_repo

    config = _load_config()
    catalog = _load_catalog(config)

    console.print(f"Evaluating {repo.resolve()}...")
    report = evaluate_repo(repo, config, catalog)

    if report.evaluated == 0:
        console.print("[yellow]No assets found to evaluate[/yellow]")
        return

    table = Table(title=f"Quality Report — {report.repo_name}")
    table.add_column("Asset", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Label")
    table.add_column("Invoc", justify="right", style="dim")
    table.add_column("Corr%", justify="right", style="dim")
    table.add_column("Stale", justify="right", style="dim")

    label_colors = {
        QualityLabel.EXCELLENT: "green",
        QualityLabel.GOOD: "blue",
        QualityLabel.NEEDS_WORK: "yellow",
        QualityLabel.POOR: "red",
    }

    for m in sorted(report.asset_metrics, key=lambda x: -x.quality_score):
        color = label_colors.get(m.label, "white")
        bar_len = int(m.quality_score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        table.add_row(
            m.name,
            m.asset_type,
            f"[{color}]{bar} {m.quality_score:.0f}[/{color}]",
            f"[{color}]{m.label.value}[/{color}]",
            f"{m.invocation_rate:.1f}/w",
            f"{m.correction_rate:.0%}",
            f"{m.staleness_days:.0f}d",
        )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {report.evaluated} evaluated, "
        f"[green]{report.healthy} healthy[/green], "
        f"[yellow]{report.underperforming} underperforming[/yellow], "
        f"[red]{report.stale} stale[/red]"
    )

    _show_repo_security_grade(repo)
