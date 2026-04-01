import logging
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


@click.group()
def hooks() -> None:
    """Manage Reagent telemetry hooks."""


@hooks.command("install")
def hooks_install() -> None:
    """Install Reagent telemetry hooks into ~/.claude/settings.json."""
    from reagent.telemetry.hook_installer import install_hooks

    report = install_hooks()
    console.print(f"Settings: {report.settings_path}")
    console.print(f"Installed {report.installed_count}/{report.total_count} hooks")
    for h in report.hooks:
        status_icon = "[green]✓[/green]" if h.installed else "[red]✗[/red]"
        console.print(f"  {status_icon} {h.event}")


@hooks.command("uninstall")
def hooks_uninstall() -> None:
    """Remove Reagent hooks from ~/.claude/settings.json."""
    from reagent.telemetry.hook_installer import uninstall_hooks

    report = uninstall_hooks()
    console.print(f"Removed Reagent hooks from {report.settings_path}")
    console.print(f"Active: {report.installed_count}/{report.total_count}")


@hooks.command("status")
def hooks_status() -> None:
    """Show status of Reagent telemetry hooks."""
    from reagent.telemetry.hook_installer import status

    report = status()
    if not report.settings_exists:
        console.print("[yellow]~/.claude/settings.json does not exist[/yellow]")
        return

    table = Table(title="Reagent Hooks")
    table.add_column("Event", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Script", style="dim")

    for h in report.hooks:
        status_text = (
            "[green]installed[/green]" if h.installed else "[red]not installed[/red]"
        )
        table.add_row(h.event, status_text, Path(h.script_path).name)

    console.print(table)


@hooks.command("install-prompt-hooks")
def hooks_install_prompt() -> None:
    """Install Reagent prompt hooks (opt-in quality gates)."""
    from reagent.telemetry.hook_installer import install_prompt_hooks

    report = install_prompt_hooks()
    console.print(f"Prompt hooks installed to {report.settings_path}")


@hooks.command("install-agent-hooks")
def hooks_install_agent() -> None:
    """Install Reagent agent hooks (opt-in session evaluator)."""
    from reagent.telemetry.hook_installer import install_agent_hooks

    report = install_agent_hooks()
    console.print(f"Agent hooks installed to {report.settings_path}")
    console.print("Session evaluator agent deployed to ~/.claude/agents/")
