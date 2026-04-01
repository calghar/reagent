import logging
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

from reagent.cli._helpers import _load_catalog, _load_config

if TYPE_CHECKING:
    from reagent.security.scanner import ScanReport

logger = logging.getLogger(__name__)
console = Console()


def _print_scan_report(report: ScanReport) -> None:
    """Pretty-print a security scan report.

    Args:
        report: The scan report to display.
    """
    from reagent.security.scanner import Severity

    if not report.findings:
        console.print(
            f"[green]No security issues found[/green] ({report.files_scanned} files)"
        )
        return

    table = Table(title="Security Findings")
    table.add_column("#", style="dim")
    table.add_column("Severity")
    table.add_column("Rule", style="cyan")
    table.add_column("File", style="dim", max_width=40)
    table.add_column("Line", style="yellow")
    table.add_column("Description")

    severity_colors = {
        Severity.CRITICAL: "red bold",
        Severity.HIGH: "red",
        Severity.MEDIUM: "yellow",
    }

    for i, finding in enumerate(report.findings, 1):
        color = severity_colors.get(finding.severity, "white")
        table.add_row(
            str(i),
            f"[{color}]{finding.severity.value}[/{color}]",
            finding.rule_id,
            str(finding.file_path.name),
            str(finding.line_number),
            finding.description,
        )

    console.print(table)
    verdict_color = "red" if report.verdict == "fail" else "green"
    console.print(
        f"\nRisk score: {report.risk_score:.1f} | "
        f"Verdict: [{verdict_color}]{report.verdict.upper()}[/{verdict_color}] | "
        f"Files: {report.files_scanned}"
    )


def _apply_fixes_to_path(
    path: Path,
    apply_fn: object,
) -> None:
    """Apply auto-fixes to a file or all files in a directory.

    Args:
        path: File or directory to fix.
        apply_fn: Callable ``(content: str) -> tuple[str, list[str]]``.
    """
    from collections.abc import Callable

    if not callable(apply_fn):
        return

    fn: Callable[[str], tuple[str, list[str]]] = apply_fn
    targets = [path] if path.is_file() else list(path.rglob("*.md"))
    for target in targets:
        try:
            content = target.read_text(encoding="utf-8")
            fixed, applied = fn(content)
            if applied:
                target.write_text(fixed, encoding="utf-8")
                for fix in applied:
                    console.print(f"  [green]Fixed[/green] {target.name}: {fix}")
        except OSError as exc:
            console.print(f"  [red]Could not fix {target.name}:[/red] {exc}")


@click.command("scan")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--fix", is_flag=True, help="Auto-fix common security issues in place")
def scan_cmd(path: Path, fix: bool) -> None:
    """Run the security scanner on a file or directory."""
    from reagent.security.scanner import (
        apply_auto_fixes,
        scan_directory,
        scan_file,
        score_report,
    )

    console.print(f"Scanning {path}...")
    if path.is_file():
        report = scan_file(path)
    else:
        report = scan_directory(path)

    _print_scan_report(report)

    # Show grade and score
    score, grade = score_report(report)
    grade_color = (
        "green" if grade in ("A", "B") else "yellow" if grade == "C" else "red"
    )
    console.print(
        f"Security Grade: [{grade_color}]{grade}[/{grade_color}]"
        f" (score: {score:.0f}/100) [builtin]"
    )

    if fix:
        _apply_fixes_to_path(path, apply_auto_fixes)


@click.command("audit")
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository to audit",
)
def audit_cmd(repo: Path) -> None:
    """Run a full security audit on a repository's .claude/ directory."""
    from reagent.security.scanner import scan_directory

    claude_dir = repo / ".claude"
    if not claude_dir.exists():
        console.print(f"[yellow]No .claude/ directory found in {repo}[/yellow]")
        return

    console.print(f"Auditing {claude_dir}...")
    report = scan_directory(claude_dir)
    _print_scan_report(report)


@click.command("import")
@click.argument("source")
@click.option(
    "--target-repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Target repository for installation",
)
def import_cmd(source: str, target_repo: Path) -> None:
    """Import a Claude Code asset from a local path, git URL, or gist."""
    from reagent.security.importer import (
        cleanup_staging,
        install_from_staging,
        run_import,
    )
    from reagent.security.trust import TrustStore

    console.print(f"Importing from {source}...")
    result = run_import(source)

    if result.error:
        console.print(f"[red]Import failed:[/red] {result.error}")
        raise SystemExit(1)

    console.print(f"Staged to {result.staging_path}")
    _print_scan_report(result.scan_report)

    if result.scan_report.verdict == "fail":
        console.print("\n[red bold]Security scan FAILED.[/red bold]")

    # Human review gate
    if not click.confirm("\nApprove and install?"):
        cleanup_staging(result.staging_path)
        console.print("Import rejected. Staging cleaned up.")
        return

    result.approved = True
    config = _load_config()
    trust_path = config.catalog.path.parent / "trust.jsonl"
    trust_store = TrustStore(trust_path)
    trust_store.load()

    result = install_from_staging(result, target_repo.resolve(), trust_store)
    trust_store.save()

    cleanup_staging(result.staging_path)
    console.print(f"[green]Installed to {result.installed_path}[/green]")


@click.command("history")
@click.argument("asset_id")
def history_cmd(asset_id: str) -> None:
    """Show snapshot timeline for an asset."""
    from reagent.security.snapshots import SnapshotStore

    config = _load_config()
    snap_dir = config.catalog.path.parent / "snapshots"
    store = SnapshotStore(snap_dir, config)
    store.load()

    snapshots = store.history(asset_id)
    if not snapshots:
        console.print(f"[yellow]No snapshots for {asset_id}[/yellow]")
        return

    table = Table(title=f"Snapshots: {asset_id}")
    table.add_column("#", style="dim")
    table.add_column("Timestamp")
    table.add_column("Hash", style="cyan", max_width=16)
    table.add_column("Trigger", style="green")

    for snap in snapshots:
        table.add_row(
            str(snap.snapshot_id),
            snap.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            snap.content_hash[:16],
            snap.trigger,
        )

    console.print(table)


@click.command("rollback")
@click.argument("asset_id")
@click.option(
    "--snapshot", "snapshot_id", type=int, required=True, help="Snapshot ID to restore"
)
def rollback_cmd(asset_id: str, snapshot_id: int) -> None:
    """Restore an asset from a previous snapshot."""
    from reagent.security.snapshots import SnapshotStore

    config = _load_config()
    snap_dir = config.catalog.path.parent / "snapshots"
    store = SnapshotStore(snap_dir, config)
    store.load()

    snap = store.get_snapshot(asset_id, snapshot_id)
    if not snap:
        console.print(f"[red]Snapshot {snapshot_id} not found for {asset_id}[/red]")
        raise SystemExit(1)

    target = Path(snap.file_path)
    if not target.name:
        console.print("[red]No file path recorded in snapshot[/red]")
        raise SystemExit(1)

    if not click.confirm(
        f"Restore {asset_id} from snapshot #{snapshot_id} to {target}?"
    ):
        return

    new_snap = store.rollback(asset_id, snapshot_id, target)
    store.save()
    console.print(
        f"[green]Restored {asset_id} to snapshot #{snapshot_id} "
        f"(new snapshot #{new_snap.snapshot_id})[/green]"
    )


@click.group()
def trust() -> None:
    """Manage asset trust levels."""


@trust.command("show")
@click.argument("asset_id")
def trust_show(asset_id: str) -> None:
    """Show trust level and history for an asset."""
    from reagent.security.trust import TrustStore

    config = _load_config()
    trust_path = config.catalog.path.parent / "trust.jsonl"
    store = TrustStore(trust_path)
    store.load()

    record = store.get(asset_id)
    if not record:
        console.print(f"[yellow]No trust record for {asset_id}[/yellow]")
        return

    console.print(f"[bold cyan]{record.asset_id}[/bold cyan]")
    console.print(
        f"  Trust level: {record.trust_level.name} ({record.trust_level.value})"
    )
    console.print(f"  State:       {record.state.value}")
    if record.last_review:
        console.print(f"  Last review: {record.last_review.isoformat()}")

    if record.history:
        console.print("\n  [bold]History:[/bold]")
        for event in record.history:
            from_str = event.from_level.name if event.from_level is not None else "?"
            to_str = event.to_level.name if event.to_level is not None else "?"
            console.print(
                f"    {event.timestamp:%Y-%m-%d %H:%M} {event.action}:"
                f" {from_str} -> {to_str}"
            )
            if event.reason:
                console.print(f"      Reason: {event.reason}")


@trust.command("promote")
@click.argument("asset_id")
@click.option("--level", type=int, required=True, help="Target trust level (2 or 3)")
@click.option("--reason", required=True, help="Justification for promotion")
def trust_promote(asset_id: str, level: int, reason: str) -> None:
    """Promote an asset to a higher trust level."""
    from reagent.security.trust import TrustLevel, TrustStore

    config = _load_config()
    trust_path = config.catalog.path.parent / "trust.jsonl"
    store = TrustStore(trust_path)
    store.load()

    try:
        target = TrustLevel(level)
    except ValueError:
        console.print(f"[red]Invalid trust level: {level}[/red]")
        console.print("Valid levels: 2 (REVIEWED), 3 (VERIFIED)")
        raise SystemExit(1) from None

    try:
        record = store.promote(asset_id, target, reason)
        store.save()
        console.print(
            f"[green]Promoted {asset_id} to {record.trust_level.name}[/green]"
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@click.group()
def integrity() -> None:
    """Verify asset integrity."""


@integrity.command("check")
def integrity_check() -> None:
    """Verify all tracked asset hashes against catalog."""
    from reagent.security.governance import run_integrity_check_with_logging

    config = _load_config()
    catalog = _load_catalog(config)
    log_path = config.catalog.path.parent / "security" / "integrity-log.jsonl"

    report = run_integrity_check_with_logging(catalog, log_path)

    console.print(f"Checked {report.checked} assets: {report.ok} ok")
    if report.modified:
        console.print(f"\n[red]{len(report.modified)} modified:[/red]")
        for r in report.modified:
            console.print(f"  {r.asset_id} ({r.file_path})")
    if report.missing:
        console.print(f"\n[yellow]{len(report.missing)} missing:[/yellow]")
        for r in report.missing:
            console.print(f"  {r.asset_id} ({r.file_path})")

    if report.clean:
        console.print("[green]All assets verified[/green]")


@integrity.command("report")
def integrity_report() -> None:
    """Show tampered/modified assets since last scan."""
    from reagent.security.governance import check_integrity

    config = _load_config()
    catalog = _load_catalog(config)
    report = check_integrity(catalog)

    if report.clean:
        console.print("[green]No integrity issues[/green]")
        return

    table = Table(title="Integrity Report")
    table.add_column("Asset", style="cyan")
    table.add_column("Status")
    table.add_column("File", style="dim")

    for r in report.modified:
        table.add_row(r.asset_id, "[red]modified[/red]", str(r.file_path))
    for r in report.missing:
        table.add_row(r.asset_id, "[yellow]missing[/yellow]", str(r.file_path))

    console.print(table)
