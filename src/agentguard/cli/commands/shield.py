import hashlib
import json
import logging
import shutil
from pathlib import Path

import click

logger = logging.getLogger(__name__)

_BUNDLED_HOOK = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "hook-scripts"
    / "agentguard_shield_pretool.py"
)


@click.group()
def shield() -> None:
    """BATT runtime shield — trust-tier-gated tool-call enforcement."""


@shield.command("check")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
@click.option("--tool", required=True, help="Tool name being invoked.")
@click.option(
    "--args-json",
    default="{}",
    show_default=True,
    help="JSON-encoded tool arguments.",
)
def check_cmd(asset_path: Path, tool: str, args_json: str) -> None:
    """Return an allow/deny decision for a proposed tool call."""
    from rich.console import Console

    from agentguard.shield.enforcer import ShieldEnforcer

    console = Console()
    args = json.loads(args_json)
    content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()

    decision = ShieldEnforcer().check(
        asset_content_hash=content_hash,
        tool_name=tool,
        tool_args=args,
    )

    tag = "[green]ALLOW[/green]" if decision.allowed else "[red]DENY[/red]"
    console.print(f"{tag} tool={tool} tier={decision.tier.name.lower()}")
    if decision.reason:
        console.print(f"  reason: {decision.reason}")
    raise SystemExit(0 if decision.allowed else 3)


@shield.command("install")
@click.option(
    "--repo",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path.cwd(),
    show_default=True,
    help="Repository root (the .claude/hooks/ directory is created if missing).",
)
def install_cmd(repo: Path) -> None:
    """Install the BATT PreToolUse hook script into ``<repo>/.claude/hooks/``."""
    from rich.console import Console

    console = Console()
    hooks_dir = repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "agentguard_shield_pretool.py"
    shutil.copy2(_BUNDLED_HOOK, target)
    target.chmod(0o755)
    console.print(f"[green]Installed[/green] {target}")
    console.print(
        "Configure Claude Code to invoke this hook on PreToolUse. "
        "See docs/shield.md for the settings snippet."
    )


@shield.command("status")
@click.argument("asset_path", type=click.Path(exists=True, path_type=Path))
def status_cmd(asset_path: Path) -> None:
    """Print the current trust tier and tool-grant authority for ASSET_PATH."""
    from rich.console import Console
    from rich.table import Table

    from agentguard.shield.enforcer import CompositePolicySource
    from agentguard.shield.policy import policy_for

    console = Console()
    content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    tier = CompositePolicySource().tier_for(content_hash)
    policy = policy_for(tier)

    console.print(f"Asset:        {asset_path}")
    console.print(f"Content hash: {content_hash}")
    console.print(f"Trust tier:   [bold]{tier.name}[/bold]")

    table = Table(title="Runtime authority")
    table.add_column("Capability")
    table.add_column("Value")
    table.add_row("Allowed tools", ", ".join(sorted(policy.allowed_tools)) or "—")
    table.add_row("Bash allowed", str(policy.allow_bash))
    table.add_row(
        "Bash allowlist prefixes",
        ", ".join(policy.bash_allowlist_prefixes) or "—",
    )
    table.add_row("External egress", str(policy.allow_external_egress))
    table.add_row("File writes", str(policy.allow_file_writes))
    console.print(table)
