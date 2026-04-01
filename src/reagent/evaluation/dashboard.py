import logging
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reagent.config import ReagentConfig
from reagent.core.catalog import Catalog
from reagent.evaluation.evaluator import (
    ABTestStore,
    QualityLabel,
    QualityReport,
    evaluate_repo,
)

logger = logging.getLogger(__name__)


def _quality_color(label: QualityLabel) -> str:
    """Map quality label to a rich color.

    Args:
        label: Quality label.

    Returns:
        Rich color name.
    """
    return {
        QualityLabel.EXCELLENT: "green",
        QualityLabel.GOOD: "blue",
        QualityLabel.NEEDS_WORK: "yellow",
        QualityLabel.POOR: "red",
    }.get(label, "white")


def _score_bar(score: float, width: int = 20) -> Text:
    """Render a colored score bar.

    Args:
        score: Score on 0-100 scale.
        width: Bar width in characters.

    Returns:
        Rich Text with colored bar.
    """
    filled = int(score / 100 * width)
    if score > 85:
        color = "green"
    elif score > 70:
        color = "blue"
    elif score > 50:
        color = "yellow"
    else:
        color = "red"

    bar = "█" * filled + "░" * (width - filled)
    return Text(f"{bar} {score:.0f}", style=color)


def build_inventory_panel(catalog: Catalog) -> Panel:
    """Build the asset inventory summary panel.

    Args:
        catalog: Loaded catalog.

    Returns:
        Rich Panel with inventory table.
    """
    table = Table(show_header=True, expand=True)
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green", justify="right")

    counts = catalog.counts_by_type()
    for asset_type, count in sorted(counts.items(), key=lambda x: -x[1]):
        table.add_row(asset_type.value, str(count))

    table.add_row("[bold]Total[/bold]", f"[bold]{catalog.count}[/bold]")
    return Panel(table, title="Asset Inventory", border_style="blue")


def build_quality_panel(report: QualityReport) -> Panel:
    """Build the quality scores panel.

    Args:
        report: Quality evaluation report.

    Returns:
        Rich Panel with quality scores table.
    """
    table = Table(show_header=True, expand=True)
    table.add_column("Asset", style="cyan", max_width=30)
    table.add_column("Type", style="dim")
    table.add_column("Score")
    table.add_column("Label")

    for m in sorted(report.asset_metrics, key=lambda x: -x.quality_score):
        color = _quality_color(m.label)
        table.add_row(
            m.name,
            m.asset_type,
            _score_bar(m.quality_score),
            f"[{color}]{m.label.value}[/{color}]",
        )

    summary = (
        f"[green]{report.healthy} healthy[/green]  "
        f"[yellow]{report.underperforming} underperforming[/yellow]  "
        f"[red]{report.stale} stale[/red]"
    )
    return Panel(
        table,
        title=f"Quality Scores ({report.evaluated} assets)",
        subtitle=summary,
        border_style="green",
    )


def build_regressions_panel(regressions_path: Path) -> Panel:
    """Build the recent regressions panel.

    Args:
        regressions_path: Path to regressions.jsonl log file.

    Returns:
        Rich Panel with recent regressions.
    """
    import json

    table = Table(show_header=True, expand=True)
    table.add_column("Time", style="dim")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="red")
    table.add_column("Baseline", style="green")
    table.add_column("StdDev", style="yellow")

    if regressions_path.exists():
        lines = regressions_path.read_text(encoding="utf-8").splitlines()
        recent = lines[-10:] if len(lines) > 10 else lines
        for line in reversed(recent):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                for alert in data.get("alerts", []):
                    table.add_row(
                        data.get("timestamp", "")[:19],
                        alert.get("metric", ""),
                        f"{alert.get('current_value', 0):.2f}",
                        f"{alert.get('baseline_mean', 0):.2f}",
                        f"{alert.get('deviation', 0):.1f}sd",
                    )
            except (json.JSONDecodeError, KeyError):
                continue

    if table.row_count == 0:
        return Panel(
            "[green]No regressions detected[/green]",
            title="Recent Regressions",
        )

    return Panel(table, title="Recent Regressions", border_style="red")


def build_ab_tests_panel(ab_store: ABTestStore) -> Panel:
    """Build the A/B tests panel.

    Args:
        ab_store: Loaded A/B test store.

    Returns:
        Rich Panel with active tests.
    """
    table = Table(show_header=True, expand=True)
    table.add_column("Test", style="cyan")
    table.add_column("Original", style="green", justify="right")
    table.add_column("Variant", style="yellow", justify="right")
    table.add_column("Status")

    for test in ab_store.all_tests():
        status = "[green]active[/green]" if test.active else "[dim]ended[/dim]"
        table.add_row(
            test.test_id,
            str(test.sessions_original),
            str(test.sessions_variant),
            status,
        )

    if table.row_count == 0:
        return Panel("[dim]No active A/B tests[/dim]", title="A/B Tests")

    return Panel(table, title="A/B Tests", border_style="yellow")


def build_coverage_panel(report: QualityReport) -> Panel:
    """Build the coverage gaps panel.

    Args:
        report: Quality report with coverage metrics.

    Returns:
        Rich Panel with coverage gaps.
    """
    gaps: list[str] = []
    for m in report.asset_metrics:
        if m.coverage < 30:
            gaps.append(f"[yellow]{m.name}[/yellow]: {m.coverage:.0f}% coverage")

    if not gaps:
        return Panel(
            "[green]All assets have adequate coverage[/green]",
            title="Coverage Gaps",
        )

    content = "\n".join(gaps)
    return Panel(content, title="Coverage Gaps", border_style="yellow")


def render_dashboard(
    repo_path: Path,
    config: ReagentConfig | None = None,
    console: Console | None = None,
) -> None:
    """Render the full quality dashboard.

    Args:
        repo_path: Path to the repository.
        config: Reagent configuration.
        console: Rich console for output.
    """
    console = console or Console()
    config = config or ReagentConfig.load()

    catalog = Catalog(config.catalog.path)
    catalog.load()

    report = evaluate_repo(repo_path, config, catalog)

    regressions_path = config.catalog.path.parent / "telemetry" / "regressions.jsonl"

    ab_path = config.catalog.path.parent / "ab-tests.jsonl"
    ab_store = ABTestStore(ab_path)
    ab_store.load()

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    layout["left"].split_column(
        Layout(name="inventory"),
        Layout(name="coverage"),
    )
    layout["right"].split_column(
        Layout(name="quality"),
        Layout(name="regressions"),
        Layout(name="ab_tests"),
    )

    layout["header"].update(
        Panel(
            f"[bold]Reagent Dashboard[/bold] — \
                {report.repo_name} ({report.evaluated} assets)",
            style="blue",
        )
    )
    layout["inventory"].update(build_inventory_panel(catalog))
    layout["quality"].update(build_quality_panel(report))
    layout["regressions"].update(build_regressions_panel(regressions_path))
    layout["ab_tests"].update(build_ab_tests_panel(ab_store))
    layout["coverage"].update(build_coverage_panel(report))
    layout["footer"].update(Panel("[dim]Press Ctrl+C to exit[/dim]", style="dim"))

    console.print(layout)
