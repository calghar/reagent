import logging
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from reagent.loops.state import PendingAsset

logger = logging.getLogger(__name__)
console = Console()


def _resolve_pending_by_id(
    queue: object,
    identifiers: tuple[str, ...],
) -> list[PendingAsset]:
    """Resolve a mix of row-number strings and UUID strings to PendingAsset objects.

    Accepts identifiers from ``reagent loop review`` output: either the
    1-based row number shown in the ``#`` column, or the full UUID.

    Args:
        queue: An :class:`ApprovalQueue` instance.
        identifiers: Tuple of strings (numbers or UUIDs).

    Returns:
        Ordered list of matching PendingAsset objects (duplicates excluded).
    """
    from reagent.loops.state import ApprovalQueue
    from reagent.loops.state import PendingAsset as _PendingAsset

    if not isinstance(queue, ApprovalQueue):
        return []

    pending = queue.list_pending()
    seen: set[str] = set()
    result: list[_PendingAsset] = []

    for ident in identifiers:
        asset: _PendingAsset | None = None
        if ident.isdigit():
            idx = int(ident) - 1  # 1-based → 0-based
            if 0 <= idx < len(pending):
                asset = pending[idx]
        else:
            asset = queue.get(ident)
        if asset is not None and asset.pending_id not in seen:
            seen.add(asset.pending_id)
            result.append(asset)

    return result


@click.group("loop")
def loop_group() -> None:
    """Manage autonomous generation-evaluation loops."""


@loop_group.command("init")
@click.option(
    "--max-iterations", default=5, show_default=True, help="Maximum loop iterations."
)
@click.option(
    "--max-cost", default=2.0, show_default=True, help="Maximum spend in USD."
)
@click.option(
    "--no-approval",
    is_flag=True,
    default=False,
    help="Skip approval queue (auto-deploy).",
)
@click.option(
    "--target",
    default=80.0,
    show_default=True,
    help="Target quality score (0-100).",
)
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Repository path.",
)
def loop_init(
    max_iterations: int,
    max_cost: float,
    no_approval: bool,
    target: float,
    repo: Path,
) -> None:
    """Run the init loop: generate assets from scratch for the repo."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from reagent.loops import LoopConfig, LoopController

    cfg = LoopConfig(
        max_iterations=max_iterations,
        max_cost_usd=max_cost,
        require_approval=not no_approval,
        target_score=target,
    )
    ctrl = LoopController()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running init loop\u2026", total=None)
        result = ctrl.run_init(repo, cfg)

    console.print(f"[bold green]Loop completed[/bold green] ({result.status})")
    console.print(f"  Iterations:       {result.iterations}")
    console.print(f"  Assets generated: {result.assets_generated}")
    console.print(f"  Average score:    {result.avg_score:.1f}")
    console.print(f"  Total cost:       ${result.total_cost:.4f}")
    console.print(f"  Pending approval: {result.pending_count}")
    if result.stop_reason:
        console.print(f"  Stopped because:  {result.stop_reason}")
    if result.pending_count:
        console.print("\nReview with: [cyan]reagent loop review[/cyan]")


@loop_group.command("improve")
@click.option(
    "--threshold",
    default=80.0,
    show_default=True,
    help="Score threshold below which assets are regenerated.",
)
@click.option(
    "--max-iterations", default=5, show_default=True, help="Maximum loop iterations."
)
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Repository path.",
)
def loop_improve(threshold: float, max_iterations: int, repo: Path) -> None:
    """Run the improve loop: regenerate below-threshold existing assets."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from reagent.loops import LoopConfig, LoopController

    cfg = LoopConfig(max_iterations=max_iterations, target_score=threshold)
    ctrl = LoopController()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running improve loop\u2026", total=None)
        result = ctrl.run_improve(repo, cfg)

    console.print(f"[bold green]Loop completed[/bold green] ({result.status})")
    console.print(f"  Iterations:       {result.iterations}")
    console.print(f"  Assets improved:  {result.assets_generated}")
    console.print(f"  Average score:    {result.avg_score:.1f}")
    console.print(f"  Pending approval: {result.pending_count}")
    if result.stop_reason:
        console.print(f"  Stopped because:  {result.stop_reason}")
    if result.pending_count:
        console.print("\nReview with: [cyan]reagent loop review[/cyan]")


@loop_group.command("watch")
@click.option(
    "--interval",
    default=30.0,
    show_default=True,
    help="Poll interval in seconds.",
)
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Repository path.",
)
def loop_watch(interval: float, repo: Path) -> None:
    """Run the watch loop: monitor repo for changes and regenerate assets."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from reagent.loops import LoopConfig, LoopController, LoopResult

    cfg = LoopConfig(cooldown_seconds=interval)
    ctrl = LoopController()
    console.print(f"Watching [cyan]{repo}[/cyan] (Ctrl-C to stop)\u2026")
    watch_result: LoopResult | None = None
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Watching for changes\u2026", total=None)
            watch_result = ctrl.run_watch(repo, cfg)
    except KeyboardInterrupt:
        ctrl.stop()

    if watch_result is not None:
        console.print(f"[bold]Watch loop ended[/bold]: {watch_result.status}")
        if watch_result.pending_count:
            console.print(f"  Pending approval: {watch_result.pending_count}")
            console.print("Review with: [cyan]reagent loop review[/cyan]")
    else:
        console.print("[yellow]Watch loop stopped by user.[/yellow]")


@loop_group.command("stop")
def loop_stop() -> None:
    """Activate the kill switch to stop any running loop."""
    from reagent.loops import LoopController

    LoopController().stop()
    console.print("[yellow]Kill switch activated \u2014 loop will stop.[/yellow]")


@loop_group.command("status")
def loop_status() -> None:
    """Show the most recent loop's state."""
    from reagent.storage import ReagentDB

    with ReagentDB() as db:
        conn = db.connect()
        row = conn.execute(
            "SELECT * FROM loops ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        console.print("[yellow]No loops found.[/yellow]")
        return
    d = dict(row)
    console.print(f"[bold cyan]Loop {d['loop_id']}[/bold cyan]")
    console.print(f"  Type:      {d['loop_type']}")
    console.print(f"  Status:    {d['status']}")
    console.print(f"  Repo:      {d['repo_path']}")
    console.print(f"  Iteration: {d['iteration']}")
    avg = d["avg_score"]
    avg_str = f"  Avg score: {avg:.1f}" if avg is not None else "  Avg score: \u2014"
    console.print(avg_str)
    console.print(f"  Started:   {d['started_at']}")
    if d["completed_at"]:
        console.print(f"  Completed: {d['completed_at']}")
    if d["stop_reason"]:
        console.print(f"  Reason:    {d['stop_reason']}")


@loop_group.command("review")
def loop_review() -> None:
    """Show pending assets awaiting approval."""
    from reagent.loops import ApprovalQueue

    queue = ApprovalQueue()
    pending = queue.list_pending()
    if not pending:
        console.print("[green]No pending assets.[/green]")
        return

    tbl = Table(title="Pending Assets", show_lines=False)
    tbl.add_column("#", style="bold", justify="right")
    tbl.add_column("Type", style="cyan")
    tbl.add_column("Name")
    tbl.add_column("Score", justify="right")
    tbl.add_column("Delta", justify="right")
    tbl.add_column("Path", style="dim")

    for idx, asset in enumerate(pending, start=1):
        prev = asset.previous_score
        new = asset.new_score
        if prev is not None:
            score_str = f"{prev:.0f} \u2192 {new:.0f}"
            delta = new - prev
            delta_str = (
                f"[green]+{delta:.0f}[/green]"
                if delta >= 0
                else f"[red]{delta:.0f}[/red]"
            )
        else:
            score_str = f"\u2192 {new:.0f}"
            delta_str = "new"
        tbl.add_row(
            str(idx),
            asset.asset_type,
            asset.asset_name,
            score_str,
            delta_str,
            asset.file_path,
        )

    console.print(tbl)
    console.print(
        "\nDeploy: [cyan]reagent loop deploy[/cyan]  "
        "Diff: [cyan]reagent loop diff <ID>[/cyan]"
    )


@loop_group.command("deploy")
@click.option("--all", "deploy_all", is_flag=True, help="Deploy all pending assets.")
@click.argument("identifiers", nargs=-1, metavar="[IDS...]")
def loop_deploy(deploy_all: bool, identifiers: tuple[str, ...]) -> None:
    """Write approved asset content to disk.

    IDS can be row numbers from 'reagent loop review' (e.g. 1 3) or
    full pending UUIDs.  Use --all to deploy every pending asset.
    """
    from reagent.loops import ApprovalQueue

    queue = ApprovalQueue()

    if deploy_all:
        assets = queue.list_pending()
    else:
        if not identifiers:
            console.print("[red]Specify IDs / row numbers or use --all.[/red]")
            raise SystemExit(1)
        assets = _resolve_pending_by_id(queue, identifiers)
        if not assets:
            console.print("[red]No matching pending assets found.[/red]")
            raise SystemExit(1)

    deployed = 0
    for asset in assets:
        try:
            dest = Path(asset.file_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(asset.content, encoding="utf-8")
            queue.approve(asset.pending_id)
            console.print(f"[green]Deployed[/green] {asset.asset_name} \u2192 {dest}")
            deployed += 1
        except OSError as exc:
            console.print(f"[red]Failed to deploy {asset.asset_name}: {exc}[/red]")

    console.print(f"\nDeployed {deployed}/{len(assets)} assets.")


@loop_group.command("discard")
@click.option("--all", "discard_all", is_flag=True, help="Discard all pending assets.")
@click.argument("identifiers", nargs=-1, metavar="[IDS...]")
def loop_discard(discard_all: bool, identifiers: tuple[str, ...]) -> None:
    """Reject pending assets without writing to disk.

    IDS can be row numbers from 'reagent loop review' or full pending UUIDs.
    Use --all to discard every pending asset.
    """
    from reagent.loops import ApprovalQueue

    queue = ApprovalQueue()

    if discard_all:
        count = 0
        for asset in queue.list_pending():
            queue.reject(asset.pending_id)
            count += 1
        console.print(f"[yellow]Discarded {count} pending assets.[/yellow]")
        return

    if not identifiers:
        console.print("[red]Specify IDs / row numbers or use --all.[/red]")
        raise SystemExit(1)

    assets = _resolve_pending_by_id(queue, identifiers)
    for asset in assets:
        queue.reject(asset.pending_id)
        console.print(f"[yellow]Discarded[/yellow] {asset.asset_name}")


@loop_group.command("diff")
@click.argument("identifier")
def loop_diff(identifier: str) -> None:
    """Show unified diff for a pending asset vs its previous version.

    IDENTIFIER can be a row number from 'reagent loop review' or a full UUID.
    """
    import difflib

    from reagent.loops import ApprovalQueue

    queue = ApprovalQueue()
    assets = _resolve_pending_by_id(queue, (identifier,))
    if not assets:
        console.print(f"[red]Pending asset not found: {identifier}[/red]")
        raise SystemExit(1)
    asset = assets[0]

    prev = asset.previous_content or ""
    new = asset.content
    diff = list(
        difflib.unified_diff(
            prev.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"previous/{asset.asset_name}",
            tofile=f"pending/{asset.asset_name}",
        )
    )
    if not diff:
        console.print("[green]No differences.[/green]")
        return

    for line in diff:
        line_stripped = line.rstrip("\n")
        if line_stripped.startswith("+"):
            console.print(f"[green]{line_stripped}[/green]")
        elif line_stripped.startswith("-"):
            console.print(f"[red]{line_stripped}[/red]")
        elif line_stripped.startswith("@@"):
            console.print(f"[cyan]{line_stripped}[/cyan]")
        else:
            console.print(line_stripped)


@loop_group.command("history")
def loop_history() -> None:
    """Show the last 10 loop runs."""
    from reagent.storage import ReagentDB

    with ReagentDB() as db:
        conn = db.connect()
        rows = conn.execute(
            "SELECT loop_id, loop_type, status, iteration, avg_score, started_at "
            "FROM loops ORDER BY started_at DESC LIMIT 10"
        ).fetchall()

    if not rows:
        console.print("[yellow]No loop history found.[/yellow]")
        return

    tbl = Table(title="Loop History", show_lines=False)
    tbl.add_column("ID", style="dim")
    tbl.add_column("Type", style="cyan")
    tbl.add_column("Status")
    tbl.add_column("Iterations", justify="right")
    tbl.add_column("Avg Score", justify="right")
    tbl.add_column("Started")

    for row in rows:
        d = dict(row)
        avg = d["avg_score"]
        avg_str = f"{avg:.1f}" if avg is not None else "\u2014"
        status_val = d["status"]
        status_style = "green" if status_val == "completed" else "yellow"
        tbl.add_row(
            str(d["loop_id"])[:8],
            d["loop_type"],
            f"[{status_style}]{status_val}[/{status_style}]",
            str(d["iteration"]),
            avg_str,
            str(d["started_at"])[:19],
        )

    console.print(tbl)
