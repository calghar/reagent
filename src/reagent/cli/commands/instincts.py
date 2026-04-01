import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from reagent.cli._helpers import _load_config

logger = logging.getLogger(__name__)
console = Console()


@click.group("instincts")
def instincts_group() -> None:
    """Manage the instinct-based learning loop."""


@instincts_group.command("list")
def instincts_list() -> None:
    """Show all instincts with confidence scores."""
    from reagent.llm.instincts import InstinctStore, ensure_bundled

    config = _load_config()
    store_path = config.catalog.path.parent / "instincts.json"
    store = InstinctStore(store_path)
    store.load()
    ensure_bundled(store)

    if not store.instincts:
        console.print("[yellow]No instincts found[/yellow]")
        return

    table = Table(title="Instincts")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Tier", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Confidence", justify="right")
    table.add_column("Uses", justify="right", style="dim")
    table.add_column("Content", max_width=50)

    for inst in sorted(store.instincts, key=lambda i: -i.confidence):
        tier_color = {
            "bundled": "cyan",
            "managed": "green",
            "workspace": "yellow",
        }.get(inst.trust_tier, "white")
        table.add_row(
            inst.instinct_id,
            f"[{tier_color}]{inst.trust_tier}[/{tier_color}]",
            inst.category,
            f"{inst.confidence:.2f}",
            str(inst.use_count),
            inst.content[:50],
        )

    console.print(table)
    console.print(f"\nTotal: {len(store.instincts)} instincts")


@instincts_group.command("extract")
@click.argument(
    "repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    required=False,
)
def instincts_extract(repo: Path) -> None:
    """Extract instincts from local telemetry sessions.

    REPO is the path to the repository (defaults to current directory).
    """
    from reagent.llm.instincts import (
        InstinctStore,
        extract_from_profile,
    )
    from reagent.telemetry.profiler import profile_repo

    config = _load_config()
    store_path = config.catalog.path.parent / "instincts.json"
    store = InstinctStore(store_path)
    store.load()

    profile = profile_repo(repo)
    if profile.session_count == 0:
        console.print(
            "[yellow]No session transcripts found. "
            "Use Claude Code in your repo to generate session "
            "data, then re-run this command.[/yellow]"
        )
        return

    instincts = extract_from_profile(profile)
    for inst in instincts:
        store.add(inst)
    store.save()

    console.print(
        f"[green]Extracted {len(instincts)} instinct(s) "
        f"from {profile.session_count} sessions[/green]"
    )


@instincts_group.command("prune")
@click.option(
    "--max-age",
    type=int,
    default=90,
    help="Maximum age in days",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.3,
    help="Minimum confidence to keep",
)
def instincts_prune(max_age: int, min_confidence: float) -> None:
    """Remove stale or low-confidence instincts."""
    from reagent.llm.instincts import InstinctStore, prune_stale

    config = _load_config()
    store_path = config.catalog.path.parent / "instincts.json"
    store = InstinctStore(store_path)
    store.load()

    removed = prune_stale(
        store,
        max_age_days=max_age,
        min_confidence=min_confidence,
    )
    store.save()

    console.print(f"Pruned {removed} instinct(s)")
    console.print(f"Remaining: {len(store.instincts)}")


@instincts_group.command("import")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def instincts_import(path: Path) -> None:
    """Import instincts from a JSON file."""
    from reagent.llm.instincts import InstinctStore, import_instincts

    config = _load_config()
    store_path = config.catalog.path.parent / "instincts.json"
    store = InstinctStore(store_path)
    store.load()

    count = import_instincts(store, path)
    store.save()
    console.print(f"[green]Imported {count} instinct(s) from {path}[/green]")


@instincts_group.command("export")
@click.argument("path", type=click.Path(path_type=Path))
@click.option(
    "--min-confidence",
    type=float,
    default=0.7,
    help="Minimum confidence for export",
)
def instincts_export(path: Path, min_confidence: float) -> None:
    """Export high-confidence instincts to a JSON file."""
    from reagent.llm.instincts import InstinctStore, export_instincts

    config = _load_config()
    store_path = config.catalog.path.parent / "instincts.json"
    store = InstinctStore(store_path)
    store.load()

    count = export_instincts(store, path, min_confidence)
    console.print(f"[green]Exported {count} instinct(s) to {path}[/green]")
