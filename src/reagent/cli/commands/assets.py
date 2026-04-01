import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from reagent.cli._helpers import _load_catalog, _load_config
from reagent.core.parsers import AssetType

logger = logging.getLogger(__name__)
console = Console()

_PROJECT_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "Package.swift",
)


def _discover_repos(
    root: Path,
    max_depth: int,
) -> list[Path]:
    """Walk root to find directories that look like project repos.

    Args:
        root: Starting directory.
        max_depth: Maximum depth to recurse.

    Returns:
        Sorted list of discovered repo root paths.
    """
    repos: list[Path] = []
    _walk_for_repos(root, max_depth, 0, repos)
    repos.sort()
    return repos


def _walk_for_repos(
    current: Path,
    max_depth: int,
    depth: int,
    result: list[Path],
) -> None:
    """Recursive helper to find repos without exceeding depth.

    Args:
        current: Current directory being inspected.
        max_depth: Maximum allowed depth.
        depth: Current recursion depth.
        result: Accumulator list of repo paths.
    """
    if depth > max_depth:
        return
    if any((current / m).exists() for m in _PROJECT_MARKERS):
        result.append(current)
        return  # Don't recurse into discovered repos
    try:
        children = sorted(current.iterdir())
    except PermissionError:
        return
    for child in children:
        if child.is_dir() and not child.name.startswith("."):
            _walk_for_repos(child, max_depth, depth + 1, result)


def _show_content_security_grade(content: str) -> None:
    """Run a quick built-in security scan on raw content and show the grade.

    Args:
        content: Text content to scan (e.g. a generated asset body).
    """
    from pathlib import Path as _Path

    from reagent.security.scanner import ScanReport as _ScanReport
    from reagent.security.scanner import scan_content, score_report

    virtual_path = _Path("<generated>")
    findings = scan_content(content, virtual_path)
    report = _ScanReport(files_scanned=1)
    for f in findings:
        report.add(f)
    score, grade = score_report(report)
    grade_color = (
        "green" if grade in ("A", "B") else "yellow" if grade == "C" else "red"
    )
    console.print(
        f"\n[dim]Security Grade:[/dim] [{grade_color}]{grade}[/{grade_color}]"
        f" (score: {score:.0f}/100) [builtin]"
    )
    if findings:
        console.print(
            f"[dim]  {len(findings)} issue(s) found."
            " Use [bold]reagent scan --fix[/bold] after writing.[/dim]"
        )


def _show_repo_security_grade(repo: Path) -> None:
    """Scan the repo's .claude/ directory and display the aggregate security grade.

    Args:
        repo: Repository root path.
    """
    from reagent.security.scanner import scan_directory, score_report

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


def _write_harness_files(
    content: str,
    asset_type_str: str,
    repo: Path,
    harness: str,
) -> None:
    """Adapt content to target harness(es) and write resulting files.

    Args:
        content: Raw markdown content of the asset.
        asset_type_str: Asset type string (e.g. ``"agent"``).
        repo: Absolute repository root path.
        harness: Target harness name, or ``"all"`` for all non-Claude formats.
    """
    from reagent.core.parsers import AssetType as _AssetType
    from reagent.harness import HarnessFormat, adapt
    from reagent.llm.parser import GeneratedAsset, parse_llm_response

    # Map string to AssetType; fall back gracefully for unknown types
    _type_map: dict[str, _AssetType] = {
        "agent": _AssetType.AGENT,
        "skill": _AssetType.SKILL,
        "hook": _AssetType.HOOK,
        "command": _AssetType.COMMAND,
        "rule": _AssetType.RULE,
        "claude_md": _AssetType.CLAUDE_MD,
        "settings": _AssetType.SETTINGS,
    }
    asset_type = _type_map.get(asset_type_str.lower())
    if asset_type is None:
        console.print(
            f"[yellow]Unknown asset type '{asset_type_str}'; "
            "skipping harness adaptation.[/yellow]"
        )
        return

    try:
        generated = parse_llm_response(content, asset_type)
    except (ValueError, KeyError):
        # Construct a minimal GeneratedAsset from raw content when parsing fails
        generated = GeneratedAsset(
            asset_type=asset_type,
            frontmatter={},
            body=content,
            raw_response=content,
        )

    _skip = {HarnessFormat.CLAUDE_CODE, HarnessFormat.AGENTS_MD}

    if harness == "all":
        targets: list[HarnessFormat] = [
            fmt for fmt in HarnessFormat if fmt not in _skip
        ]
    else:
        try:
            targets = [HarnessFormat(harness)]
        except ValueError:
            valid = ", ".join(HarnessFormat)
            console.print(
                f"[red]Unknown harness '{harness}'. Valid values: {valid}[/red]"
            )
            return

    for target in targets:
        if target in _skip:
            continue
        hfiles = adapt(generated, target)
        for hfile in hfiles:
            dest = repo / hfile.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(hfile.content, encoding="utf-8")
            console.print(f"  [dim]Harness [{target}]:[/dim] [green]{dest}[/green]")


def _show_suggestion(identifier: str) -> None:
    """Show draft content for a suggestion.

    Args:
        identifier: Suggestion number as a string.
    """
    from reagent.creation.suggest import suggest_for_repo

    try:
        num = int(identifier)
    except ValueError:
        console.print(f"[red]Invalid suggestion number:[/red] {identifier}")
        raise SystemExit(1) from None

    # Re-run suggestion for current directory
    report = suggest_for_repo(Path.cwd())
    suggestion = report.get_suggestion(num)

    if not suggestion:
        console.print(f"[red]Suggestion #{num} not found[/red]")
        raise SystemExit(1)

    console.print(f"[bold cyan]Suggestion #{num}:[/bold cyan] {suggestion.title}")
    console.print(f"  Category: {suggestion.category}")
    console.print(f"  Severity: {suggestion.severity}")
    if suggestion.target_path:
        console.print(f"  Target:   {suggestion.target_path}")
    if suggestion.draft_content:
        console.print("\n[bold]Draft content:[/bold]")
        console.print(suggestion.draft_content)


def _show_asset(asset_id: str) -> None:
    """Show detailed view of a single asset.

    Args:
        asset_id: The asset identifier in repo:type:name format.
    """
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
    from reagent.core.inventory import run_inventory, scan_path

    config = _load_config()
    catalog = _load_catalog(config)

    if repo:
        repo = repo.resolve()
        logger.info("Inventory scan of %s", repo)

        # Use scan_path for automatic recursive discovery
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
        console.print("No assets in catalog. Run `reagent inventory` first.")
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
@click.option("--suggestion", is_flag=True, help="Show a suggestion by number")
def show_item(asset_id: str, suggestion: bool) -> None:
    """Show detailed view of an asset or suggestion."""
    if suggestion:
        _show_suggestion(asset_id)
    else:
        _show_asset(asset_id)


@click.command()
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository to analyze",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Generate and create all suggested assets",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be created (with --apply)",
)
def suggest(repo: Path, apply: bool, dry_run: bool) -> None:
    """Show actionable recommendations based on workflow profiles."""
    from reagent.creation.suggest import (
        apply_suggestions,
        suggest_for_repo,
    )

    if apply:
        console.print(f"Analyzing {repo.resolve()}...")
        result = apply_suggestions(repo, dry_run=dry_run)

        if result.applied == 0:
            console.print("[green]No actionable suggestions to apply[/green]")
            return

        label = "Would create" if dry_run else "Created"
        console.print(f"\n[bold]{label} {result.applied} asset(s):[/bold]")
        for p in result.paths:
            icon = "[dim]→[/dim]" if dry_run else "[green]✓[/green]"
            console.print(f"  {icon} {p}")

        if result.skipped:
            console.print(
                f"\n[dim]{result.skipped} suggestion(s) skipped"
                f" (no draft content)[/dim]"
            )
        return

    console.print(f"Analyzing {repo.resolve()}...")
    report = suggest_for_repo(repo)

    if not report.suggestions:
        console.print("[green]No suggestions — everything looks good![/green]")
        return

    console.print(f"\n[bold]{len(report.suggestions)} suggestion(s):[/bold]\n")
    for s in report.suggestions:
        severity_color = {"critical": "red", "warning": "yellow", "info": "blue"}.get(
            s.severity, "white"
        )
        console.print(
            f"  [{severity_color}]{s.number}.[/{severity_color}] "
            f"[{severity_color}][{s.category}][/{severity_color}] {s.title}"
        )
        console.print(f"     {s.description}")

    console.print("\nUse `reagent show --suggestion <N>` for draft content.")


@click.command("regenerate")
@click.argument("asset", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository root",
)
def regenerate_cmd(asset: Path, repo: Path) -> None:
    """Regenerate an asset with evaluation feedback and instincts."""
    from reagent.creation.creator import regenerate_asset

    console.print(f"Regenerating {asset}...")
    try:
        draft = regenerate_asset(asset.resolve(), repo.resolve())
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None

    # Show diff
    original = asset.read_text(encoding="utf-8")
    if original.strip() == draft.content.strip():
        console.print("[green]No changes — asset is already optimal[/green]")
        return

    console.print(f"\n[bold]Regenerated {draft.name}[/bold]\n")
    console.print(draft.content)

    if not click.confirm("\nWrite this improved version?"):
        console.print("Cancelled.")
        return

    path = draft.write()
    console.print(f"[green]Wrote {path}[/green]")


@click.command()
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository to profile",
)
def profile(repo: Path) -> None:
    """Analyze Claude Code sessions and show workflow profile."""
    from reagent.telemetry.profiler import profile_repo, save_workflow_model

    console.print(f"Profiling {repo.resolve()}...")
    result = profile_repo(repo)

    if result.session_count == 0:
        console.print("[yellow]No sessions found for this repository.[/yellow]")
        console.print("Install hooks first: reagent hooks install")
        return

    console.print(f"\n[bold]Sessions:[/bold] {result.session_count}")
    console.print(f"[bold]Tool calls:[/bold] {result.total_tool_calls}")
    console.print(f"[bold]Corrections:[/bold] {result.total_corrections}")
    if result.avg_session_duration:
        console.print(f"[bold]Avg duration:[/bold] {result.avg_session_duration:.0f}s")

    if result.workflows:
        console.print("\n[bold]Detected Workflows:[/bold]")
        table = Table()
        table.add_column("Intent", style="cyan")
        table.add_column("Frequency", style="green")
        table.add_column("Avg Turns", style="yellow")
        table.add_column("Sequence", style="dim")

        for wf in result.workflows:
            table.add_row(
                wf.intent,
                f"{wf.frequency:.1f}/session",
                f"{wf.avg_turns:.0f}",
                " → ".join(wf.typical_sequence[:5]),
            )
        console.print(table)

    if result.correction_hotspots:
        console.print("\n[bold]Correction Hotspots:[/bold]")
        for hs in result.correction_hotspots[:5]:
            console.print(
                f"  {hs.file_pattern}: {hs.correction_rate:.0%}"
                f" ({hs.correction_count}x)"
            )

    if result.coverage_gaps:
        console.print(
            f"\n[bold]Coverage gaps:[/bold] {', '.join(result.coverage_gaps)}"
        )

    output = save_workflow_model(result)
    console.print(f"\nWorkflow model saved to {output}")


@click.command("analyze")
@click.argument("repo", type=click.Path(exists=True, path_type=Path))
def analyze_cmd(repo: Path) -> None:
    """Analyze a repository for language, framework, and conventions."""
    from reagent.intelligence.analyzer import analyze_repo

    console.print(f"Analyzing {repo.resolve()}...")
    profile_result = analyze_repo(repo)

    console.print(f"\n[bold]Repository:[/bold] {profile_result.repo_name}")
    console.print(
        f"[bold]Languages:[/bold] "
        f"{', '.join(profile_result.languages) or 'none detected'}"
    )
    console.print(
        f"[bold]Frameworks:[/bold] {', '.join(profile_result.frameworks) or 'none'}"
    )
    console.print(f"[bold]Architecture:[/bold] {profile_result.architecture}")
    if profile_result.test_config.command:
        console.print(
            f"[bold]Test command:[/bold] {profile_result.test_config.command}"
        )
    if profile_result.lint_configs:
        linters = ", ".join(lc.tool for lc in profile_result.lint_configs)
        console.print(f"[bold]Linters:[/bold] {linters}")
    if profile_result.has_ci:
        console.print(f"[bold]CI:[/bold] {profile_result.ci_system}")
    if profile_result.has_docker:
        console.print("[bold]Docker:[/bold] yes")
    if profile_result.has_env_file:
        console.print("[bold]Env files:[/bold] yes")

    # Asset audit
    audit = profile_result.asset_audit
    if audit.has_claude_dir:
        console.print(
            f"\n[bold]Assets:[/bold] "
            f"{audit.agent_count} agents, {audit.skill_count} skills, "
            f"{audit.rule_count} rules, {audit.command_count} commands"
        )
    else:
        console.print("\n[yellow]No .claude/ directory found[/yellow]")

    if audit.issues:
        for issue in audit.issues:
            console.print(f"  [yellow]- {issue}[/yellow]")

    output = profile_result.save()
    console.print(f"\nProfile saved to {output}")


@click.command("cost")
def cost_cmd() -> None:
    """Show LLM generation costs (session and monthly)."""
    from reagent.llm.costs import CostTracker

    config = _load_config()
    tracker = CostTracker(monthly_budget=config.llm.monthly_budget)

    monthly = tracker.monthly_total()
    budget = config.llm.monthly_budget
    status = tracker.budget_status()
    by_provider = tracker.cost_by_provider()

    status_colors = {"ok": "green", "warning": "yellow", "exceeded": "red"}
    color = status_colors.get(status.value, "white")

    console.print(f"[bold]Monthly spend:[/bold] ${monthly:.4f} / ${budget:.2f}")
    console.print(f"[bold]Status:[/bold] [{color}]{status.value.upper()}[/{color}]")

    if by_provider:
        console.print("\n[bold]By provider:[/bold]")
        for provider, cost in sorted(by_provider.items()):
            console.print(f"  {provider}: ${cost:.4f}")

    tracker.close()


@click.command("harnesses")
def harnesses_cmd() -> None:
    """List supported harness formats."""
    table = Table(title="Supported Harness Formats", show_header=True)
    table.add_column("Format", style="cyan", no_wrap=True)
    table.add_column("Description")

    rows = [
        ("claude-code", "Default. Claude Code (.claude/ directory structure)"),
        ("cursor", "Cursor AI (.cursor/ directory, YAML rule frontmatter)"),
        ("codex", "OpenAI Codex (.codex/ + AGENTS.md instruction-based rules)"),
        ("opencode", "OpenCode (.opencode/ directory, opencode.json plugins)"),
        ("agents-md", "Universal AGENTS.md (read by all harnesses)"),
    ]
    for fmt, desc in rows:
        table.add_row(fmt, desc)

    console.print(table)


@click.command("export")
@click.argument("repo", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--harness",
    default=None,
    help="Target harness format (cursor, codex, opencode, all)",
)
@click.option(
    "--agents-md",
    "agents_md",
    is_flag=True,
    help="Generate universal AGENTS.md from existing catalog assets",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: repo root)",
)
def export_cmd(
    repo: Path,
    harness: str | None,
    agents_md: bool,
    output: Path | None,
) -> None:
    """Export existing Claude Code assets to another harness format."""
    from reagent.core.catalog import CatalogEntry
    from reagent.core.parsers import AssetType as _AssetType
    from reagent.harness import HarnessFormat, adapt
    from reagent.harness.agents_md import generate_agents_md
    from reagent.intelligence.analyzer import RepoProfile, analyze_repo
    from reagent.llm.parser import GeneratedAsset, parse_llm_response

    out_dir = (output or repo).resolve()
    config = _load_config()
    catalog = _load_catalog(config)

    # Gather assets for the resolved repo path
    repo_abs = repo.resolve()
    all_entries: list[CatalogEntry] = catalog.all_entries()
    repo_entries = [e for e in all_entries if str(repo_abs) in str(e.file_path)]

    if not repo_entries and not agents_md:
        console.print(f"[yellow]No cataloged assets found for {repo_abs}[/yellow]")
        return

    _type_map: dict[str, _AssetType] = {
        "agent": _AssetType.AGENT,
        "skill": _AssetType.SKILL,
        "hook": _AssetType.HOOK,
        "command": _AssetType.COMMAND,
        "rule": _AssetType.RULE,
        "claude_md": _AssetType.CLAUDE_MD,
        "settings": _AssetType.SETTINGS,
        "agent_memory": _AssetType.AGENT_MEMORY,
    }

    _skip = {HarnessFormat.CLAUDE_CODE, HarnessFormat.AGENTS_MD}

    def _entry_to_generated(entry: CatalogEntry) -> GeneratedAsset | None:
        """Read a catalog entry's file and build a GeneratedAsset."""
        at = _type_map.get(entry.asset_type.value)
        if at is None:
            return None
        try:
            raw = entry.file_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read %s; skipping export", entry.file_path)
            return None
        try:
            return parse_llm_response(raw, at)
        except (ValueError, KeyError):
            return GeneratedAsset(
                asset_type=at,
                frontmatter={"name": entry.name},
                body=raw,
                raw_response=raw,
            )

    if harness:
        if harness == "all":
            targets: list[HarnessFormat] = [
                fmt for fmt in HarnessFormat if fmt not in _skip
            ]
        else:
            try:
                targets = [HarnessFormat(harness)]
            except ValueError:
                console.print(
                    f"[red]Unknown harness '{harness}'. "
                    f"Valid values: {', '.join(HarnessFormat)}[/red]"
                )
                raise SystemExit(1) from None

        written = 0
        for entry in repo_entries:
            generated = _entry_to_generated(entry)
            if generated is None:
                continue
            for target in targets:
                if target in _skip:
                    continue
                for hfile in adapt(generated, target):
                    dest = out_dir / hfile.path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(hfile.content, encoding="utf-8")
                    console.print(f"  [dim][{target}][/dim] [green]{dest}[/green]")
                    written += 1

        console.print(f"\n[bold]Exported {written} harness file(s).[/bold]")

    if agents_md:
        gen_assets: list[GeneratedAsset] = [
            g for e in repo_entries if (g := _entry_to_generated(e)) is not None
        ]
        agent_list = [g for g in gen_assets if g.asset_type == _AssetType.AGENT]
        skill_list = [g for g in gen_assets if g.asset_type == _AssetType.SKILL]
        rule_list = [g for g in gen_assets if g.asset_type == _AssetType.RULE]

        try:
            repo_profile: RepoProfile = analyze_repo(repo_abs)
        except (OSError, ValueError):
            repo_profile = RepoProfile(
                repo_path=str(repo_abs),
                repo_name=repo_abs.name,
            )

        md_content = generate_agents_md(agent_list, skill_list, rule_list, repo_profile)
        dest_md = out_dir / "AGENTS.md"
        dest_md.write_text(md_content, encoding="utf-8")
        console.print(f"[green]Wrote {dest_md}[/green]")


@click.command("create")
@click.argument(
    "asset_type", type=click.Choice(["agent", "skill", "hook", "command", "rule"])
)
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repo path",
)
@click.option("--name", default=None, help="Asset name")
@click.option("--from", "from_pattern", default=None, help="Pattern name to use")
@click.option("--from-outline", default=None, help="Outline file or - for stdin")
@click.option("--interactive", is_flag=True, help="Interactive field-by-field mode")
@click.option("--no-llm", is_flag=True, help="Skip LLM, use templates only")
@click.option(
    "--use-telemetry/--no-telemetry",
    default=False,
    help="Use telemetry and instincts for generation",
)
@click.option(
    "--harness",
    default=None,
    help="Target harness format (claude-code, cursor, codex, opencode, all)",
)
@click.option(
    "--skip-security",
    is_flag=True,
    default=False,
    help="Skip post-generation security scan",
)
def create_cmd(
    asset_type: str,
    repo: Path,
    name: str | None,
    from_pattern: str | None,
    from_outline: str | None,
    interactive: bool,
    no_llm: bool,
    use_telemetry: bool,
    harness: str | None,
    skip_security: bool,
) -> None:
    """Create a new Claude Code asset with repo-aware generation."""
    from reagent.creation.creator import create_asset

    if no_llm:
        console.print("[dim]Using enhanced templates (--no-llm).[/dim]")

    # Read outline from file or stdin
    outline_text: str | None = None
    if from_outline:
        if from_outline == "-":
            outline_text = sys.stdin.read()
        else:
            outline_path = Path(from_outline)
            if not outline_path.exists():
                console.print(f"[red]File not found:[/red] {from_outline}")
                raise SystemExit(1)
            outline_text = outline_path.read_text(encoding="utf-8")

    try:
        draft = create_asset(
            asset_type=asset_type,
            repo_path=repo.resolve(),
            name=name,
            from_pattern=from_pattern,
            from_outline=outline_text,
            interactive=interactive,
            no_llm=no_llm,
            use_telemetry=use_telemetry,
        )
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None

    console.print(f"\n[bold]Generated {asset_type}:[/bold] {draft.name}")
    console.print(f"[bold]Target:[/bold] {draft.target_path}\n")

    # Show generation metadata if available
    metadata = getattr(draft, "generation_metadata", None)
    if metadata and metadata.tier == "llm":
        console.print(
            f"[dim]Provider: {metadata.provider} | "
            f"Model: {metadata.model} | "
            f"Cost: ${metadata.cost_usd:.4f} | "
            f"Tokens: {metadata.input_tokens}in/{metadata.output_tokens}out | "
            f"Latency: {metadata.latency_ms}ms[/dim]\n"
        )

    console.print(draft.content)

    # Security scan (unless skipped)
    if not skip_security:
        _show_content_security_grade(draft.content)

    if not click.confirm("\nWrite this asset?"):
        console.print("Cancelled.")
        return

    path = draft.write()
    console.print(f"[green]Wrote {path}[/green]")

    # Optionally adapt to other harness formats
    if harness:
        _write_harness_files(draft.content, asset_type, repo.resolve(), harness)


@click.command("init")
@click.argument("repo", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--harness",
    default=None,
    help="Target harness format (claude-code, cursor, codex, opencode, all)",
)
def init_cmd(repo: Path, harness: str | None) -> None:
    """Generate smart default assets based on repo analysis."""
    from reagent.creation.creator import generate_init_assets

    console.print(f"Analyzing {repo.resolve()}...")
    drafts = generate_init_assets(repo)

    if not drafts:
        console.print("[green]No assets to generate -- repo is well-configured[/green]")
        return

    console.print(f"\n[bold]{len(drafts)} asset(s) to generate:[/bold]\n")
    for draft in drafts:
        console.print(f"  [cyan]{draft.asset_type}[/cyan]: {draft.target_path}")
        # Show content preview
        preview = draft.content[:200].replace("\n", "\\n")
        console.print(f"    {preview}...\n")

    if not click.confirm("Write these assets?"):
        console.print("Cancelled.")
        return

    for draft in drafts:
        path = draft.write()
        console.print(f"  [green]Wrote {path}[/green]")

    # Optionally adapt to other harness formats
    if harness:
        for draft in drafts:
            _write_harness_files(
                draft.content, draft.asset_type, repo.resolve(), harness
            )


@click.command("baseline")
@click.argument(
    "root",
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--max-depth",
    type=int,
    default=2,
    help="Max directory depth to search for repos",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be generated without writing",
)
def baseline_cmd(
    root: Path,
    max_depth: int,
    dry_run: bool,
) -> None:
    """Generate baseline .claude assets for all repos under ROOT.

    Discovers repositories by looking for common project markers
    (e.g. .git, pyproject.toml, package.json, Cargo.toml, go.mod)
    and generates smart default assets for each.
    """
    from reagent.creation.creator import generate_init_assets

    root = root.resolve()
    repos = _discover_repos(root, max_depth)

    if not repos:
        console.print(f"[yellow]No repos found under {root}[/yellow]")
        return

    console.print(f"Found [bold]{len(repos)}[/bold] repo(s) under {root}\n")

    total_written = 0
    for repo_path in repos:
        rel = repo_path.relative_to(root)
        logger.info("Generating baseline for %s", repo_path)

        try:
            drafts = generate_init_assets(repo_path)
        except Exception:
            logger.exception("Failed: %s", repo_path)
            console.print(f"  [red]{rel}[/red]: error (see log)")
            continue

        if not drafts:
            console.print(f"  [dim]{rel}[/dim]: up to date")
            continue

        types = ", ".join(d.asset_type for d in drafts)
        console.print(f"  [cyan]{rel}[/cyan]: {types}")

        if not dry_run:
            for draft in drafts:
                draft.write()
                total_written += 1

    if dry_run:
        console.print("\n[yellow]Dry run — no files written[/yellow]")
    else:
        console.print(
            f"\n[green]Done:[/green] {total_written} asset(s)"
            f" across {len(repos)} repo(s)"
        )


@click.command("extract-patterns")
def extract_patterns_cmd() -> None:
    """Scan all cataloged assets and extract reusable patterns."""
    from reagent.intelligence.patterns import extract_all_patterns

    config = _load_config()
    catalog = _load_catalog(config)
    count = catalog.count

    if count == 0:
        console.print("No assets in catalog. Run `reagent inventory` first.")
        return

    console.print(f"Extracting patterns from {count} assets...")
    patterns = extract_all_patterns(catalog)

    if not patterns:
        console.print("[yellow]No patterns detected[/yellow]")
        return

    console.print(f"\n[bold]{len(patterns)} pattern(s) found:[/bold]\n")
    for p in patterns:
        console.print(f"  [cyan]{p.name}[/cyan] ({p.pattern_type})")
        if p.description:
            console.print(f"    {p.description}")
        if p.parameters:
            params = ", ".join(p.parameters.keys())
            console.print(f"    Parameters: {params}")
        console.print()


@click.command("apply-pattern")
@click.argument("pattern_name")
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repo path",
)
def apply_pattern_cmd(pattern_name: str, repo: Path) -> None:
    """Apply a pattern template to a repository."""
    from reagent.intelligence.analyzer import analyze_repo
    from reagent.intelligence.patterns import PatternTemplate

    pattern = PatternTemplate.load_pattern(pattern_name)
    if not pattern:
        console.print(f"[red]Pattern not found:[/red] {pattern_name}")
        raise SystemExit(1)

    console.print(f"Applying pattern '{pattern_name}' to {repo.resolve()}...")
    repo_profile = analyze_repo(repo)

    params = {
        "language": repo_profile.primary_language or "code",
        "framework": ", ".join(repo_profile.frameworks) or "none",
        "test_command": repo_profile.test_config.command or "",
        "lint_command": (
            repo_profile.lint_configs[0].command if repo_profile.lint_configs else ""
        ),
        "repo_name": repo_profile.repo_name,
    }

    rendered = pattern.render(params)
    console.print(f"\n[bold]{len(rendered)} asset(s) to generate:[/bold]\n")
    for asset in rendered:
        console.print(f"  [cyan]{asset['type']}[/cyan]: {asset['name']}")
        preview = asset["content"][:200].replace("\n", "\\n")
        console.print(f"    {preview}...\n")

    if not click.confirm("Write these assets?"):
        console.print("Cancelled.")
        return

    console.print("[green]Pattern applied.[/green]")


@click.command("specialize")
@click.argument("repo", type=click.Path(exists=True, path_type=Path))
def specialize_cmd(repo: Path) -> None:
    """Apply global assets with repo-specific adaptation."""
    from reagent.creation.specializer import specialize_repo

    console.print(f"Specializing {repo.resolve()}...")
    result = specialize_repo(repo)

    if not result.drafts:
        console.print("[yellow]No global assets found to specialize[/yellow]")
        return

    console.print(f"\n[bold]{result.count} asset(s) to write:[/bold]\n")
    for draft in result.drafts:
        console.print(f"  [cyan]{draft.asset_type}[/cyan]: {draft.target_path}")

    if not click.confirm("\nWrite these assets?"):
        console.print("Cancelled.")
        return

    for draft in result.drafts:
        path = draft.write()
        console.print(f"  [green]Wrote {path}[/green]")


@click.command("validate")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate_cmd(path: Path) -> None:
    """Validate an asset file against the schema registry."""
    from reagent.intelligence.schema_validator import IssueSeverity, validate_asset_file

    result = validate_asset_file(path)

    if not result.issues:
        console.print(f"[green]Valid:[/green] {path}")
        return

    for issue in result.issues:
        if issue.severity == IssueSeverity.ERROR:
            color = "red"
            label = "ERROR"
        elif issue.severity == IssueSeverity.WARNING:
            color = "yellow"
            label = "WARN"
        else:
            color = "blue"
            label = "INFO"

        console.print(
            f"[{color}]{label}[/{color}] {issue.asset_type}"
            f' "{issue.name}" {issue.message}'
        )
        if issue.file_path:
            console.print(f"  File: {issue.file_path}")
        if issue.field:
            console.print(f"  Field: {issue.field}")
        if issue.expected:
            console.print(f"  Expected: {issue.expected}")
        if issue.fix:
            console.print(f"  Fix: {issue.fix}")

    if result.valid:
        console.print(
            f"\n[yellow]{len(result.warnings)} warning(s), no errors[/yellow]"
        )
    else:
        console.print(
            f"\n[red]{len(result.errors)} error(s),"
            f" {len(result.warnings)} warning(s)[/red]"
        )
        raise SystemExit(1)


@click.command("evaluate")
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository to evaluate",
)
def evaluate_cmd(repo: Path) -> None:
    """Compute quality scores for all assets in a repository."""
    from reagent.evaluation.evaluator import QualityLabel, evaluate_repo

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

    # Security aggregate grade for the repo's .claude/ directory
    _show_repo_security_grade(repo)


@click.command("check-regression")
@click.argument("session_id")
@click.option(
    "--repo",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Repository path",
)
def check_regression_cmd(session_id: str, repo: Path) -> None:
    """Check a session for quality regressions against baseline."""
    from reagent.evaluation.evaluator import check_regression, log_regression

    config = _load_config()
    report = check_regression(session_id, repo, config)

    if not report.has_regressions:
        console.print(f"[green]No regressions detected for {session_id}[/green]")
        return

    for alert in report.alerts:
        console.print(
            f"[red]REGRESSION:[/red] {alert.metric} = {alert.current_value:.2f} "
            f"(baseline: {alert.baseline_mean:.2f} ± {alert.baseline_std:.2f}, "
            f"{alert.deviation:.1f} std dev)"
        )
        if alert.related_changes:
            for change in alert.related_changes:
                console.print(f"  Related: {change}")

    # Log to regressions file
    log_path = config.catalog.path.parent / "telemetry" / "regressions.jsonl"
    log_regression(log_path, report)


@click.command("variant")
@click.argument("asset_id")
@click.option("--name", required=True, help="Variant name")
@click.option("--change", "description", default="", help="Description of change")
def variant_cmd(asset_id: str, name: str, description: str) -> None:
    """Create an A/B test variant of an asset."""
    from reagent.evaluation.evaluator import ABTestStore, create_variant

    config = _load_config()
    catalog = _load_catalog(config)

    ab_path = config.catalog.path.parent / "ab-tests.jsonl"
    ab_store = ABTestStore(ab_path)
    ab_store.load()

    try:
        test = create_variant(asset_id, name, description, catalog, ab_store)
        ab_store.save()
        console.print(f"[green]Created variant:[/green] {test.test_id}")
        console.print(f"  Variant file: {test.variant_path}")
        console.print(
            "  Edit the variant file, then sessions will alternate automatically."
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None


@click.command("compare")
@click.argument("asset_a")
@click.argument("asset_b")
def compare_cmd(asset_a: str, asset_b: str) -> None:
    """Compare quality metrics between two assets or variants."""
    from reagent.evaluation.evaluator import compare_variants

    config = _load_config()
    catalog = _load_catalog(config)

    comparison = compare_variants(asset_a, asset_b, catalog, Path.cwd())

    table = Table(title=f"Comparison: {asset_a} vs {asset_b}")
    table.add_column("Metric", style="cyan")
    table.add_column("Original", justify="right")
    table.add_column("Variant", justify="right")

    if comparison.original_metrics:
        om = comparison.original_metrics
        table.add_row("Quality Score", f"{om.quality_score:.1f}", "—")
        table.add_row("Invocation Rate", f"{om.invocation_rate:.2f}/w", "—")
        table.add_row("Correction Rate", f"{om.correction_rate:.0%}", "—")
        table.add_row("Turn Efficiency", f"{om.turn_efficiency:.1f}", "—")

    console.print(table)
    console.print(f"\n[bold]Winner:[/bold] {comparison.winner}")
    if comparison.confidence > 0:
        console.print(f"[bold]Confidence:[/bold] {comparison.confidence:.0%}")


@click.command("promote")
@click.argument("variant_id")
def promote_cmd(variant_id: str) -> None:
    """Promote a variant to replace its original asset."""
    from reagent.evaluation.evaluator import ABTestStore, promote_variant

    config = _load_config()
    ab_path = config.catalog.path.parent / "ab-tests.jsonl"
    ab_store = ABTestStore(ab_path)
    ab_store.load()

    test = ab_store.get_test(variant_id)
    if not test:
        console.print(f"[red]A/B test not found:[/red] {variant_id}")
        raise SystemExit(1)

    if not click.confirm(
        f"Promote variant '{test.variant_name}' to replace {test.original_asset_id}?"
    ):
        return

    result = promote_variant(variant_id, ab_store)
    if result:
        ab_store.save()
        console.print(f"[green]Promoted to {result}[/green]")
    else:
        console.print("[red]Promotion failed — variant file not found[/red]")
        raise SystemExit(1)


@click.command("rollback-best")
@click.argument("asset_id")
def rollback_best_cmd(asset_id: str) -> None:
    """Rollback an asset to its historically best-quality version."""
    from reagent.evaluation.evaluator import evaluate_asset
    from reagent.security.snapshots import SnapshotStore
    from reagent.telemetry.events import find_sessions_dir, parse_all_sessions

    config = _load_config()
    catalog = _load_catalog(config)
    snap_dir = config.catalog.path.parent / "snapshots"
    store = SnapshotStore(snap_dir, config)
    store.load()

    entry = catalog.get(asset_id)
    if not entry:
        console.print(f"[red]Asset not found:[/red] {asset_id}")
        raise SystemExit(1)

    snapshots = store.history(asset_id)
    if not snapshots:
        console.print(f"[yellow]No snapshots for {asset_id}[/yellow]")
        return

    # Get sessions for quality evaluation
    sessions_dir = find_sessions_dir(entry.repo_path)
    sessions = parse_all_sessions(sessions_dir) if sessions_dir else []

    current_metrics = evaluate_asset(entry, sessions)

    table = Table(title=f"Version History: {asset_id}")
    table.add_column("#", style="dim")
    table.add_column("Timestamp")
    table.add_column("Hash", style="cyan", max_width=16)
    table.add_column("Trigger", style="green")
    table.add_column("Note")

    for snap in snapshots:
        note = ""
        if snap == snapshots[-1]:
            note = "[bold]current[/bold]"
        table.add_row(
            str(snap.snapshot_id),
            snap.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            snap.content_hash[:16],
            snap.trigger,
            note,
        )

    console.print(table)
    console.print(
        f"\nCurrent quality: [{current_metrics.label.value}] "
        f"{current_metrics.quality_score:.0f}/100"
    )

    if len(snapshots) < 2:
        console.print("[yellow]Only one version available[/yellow]")
        return

    # Use the second-to-last as "best" candidate if current is poor
    best_candidate = snapshots[-2]
    if not click.confirm(
        f"Rollback to snapshot #{best_candidate.snapshot_id}"
        f" ({best_candidate.timestamp:%Y-%m-%d})?"
    ):
        return

    target = (
        Path(best_candidate.file_path) if best_candidate.file_path else entry.file_path
    )
    store.rollback(asset_id, best_candidate.snapshot_id, target)
    store.save()
    console.print(f"[green]Restored to snapshot #{best_candidate.snapshot_id}[/green]")


@click.group("schema")
def schema_group() -> None:
    """Manage asset validation schemas."""


@schema_group.command("show")
@click.argument(
    "asset_type",
    type=click.Choice(["agent", "skill", "hook"]),
    required=False,
)
def schema_show(asset_type: str | None) -> None:
    """Print the current schema for an asset type."""
    import json

    from reagent.intelligence.schema_validator import show_schema

    if not asset_type:
        for at in ("agent", "skill", "hook"):
            schema = show_schema(at)
            console.print(f"\n[bold cyan]{at}[/bold cyan]:")
            console.print(json.dumps(schema, indent=2), markup=False)
        return

    schema = show_schema(asset_type)
    console.print(json.dumps(schema, indent=2), markup=False)


@schema_group.command("check")
def schema_check() -> None:
    """Compare local schemas against bundled defaults."""
    from reagent.intelligence.schema_validator import check_schemas

    diff = check_schemas()

    if not diff.has_changes:
        console.print("[green]Schemas are up to date[/green]")
        return

    if diff.added_fields:
        console.print("\n[bold]Added fields:[/bold]")
        for schema, fields in diff.added_fields.items():
            console.print(f"  {schema}: {', '.join(fields)}")
    if diff.removed_fields:
        console.print("\n[bold]Removed fields:[/bold]")
        for schema, fields in diff.removed_fields.items():
            console.print(f"  {schema}: {', '.join(fields)}")
    if diff.changed_fields:
        console.print("\n[bold]Changed fields:[/bold]")
        for schema, fields in diff.changed_fields.items():
            console.print(f"  {schema}: {', '.join(fields)}")


@schema_group.command("update")
def schema_update() -> None:
    """Update schemas from bundled defaults."""
    from reagent.intelligence.schema_validator import check_schemas, update_schemas

    diff = check_schemas()
    if not diff.has_changes:
        console.print("[green]Schemas are already up to date[/green]")
        return

    console.print("[bold]Schema changes detected:[/bold]")
    if diff.added_fields:
        for schema, fields in diff.added_fields.items():
            console.print(f"  + {schema}: {', '.join(fields)}")
    if diff.removed_fields:
        for schema, fields in diff.removed_fields.items():
            console.print(f"  - {schema}: {', '.join(fields)}")

    if not click.confirm("Apply these changes?"):
        console.print("Cancelled.")
        return

    update_schemas()
    console.print("[green]Schemas updated[/green]")


@schema_group.command("reset")
def schema_reset() -> None:
    """Restore bundled default schemas."""
    from reagent.intelligence.schema_validator import reset_schemas

    path = reset_schemas()
    console.print(f"[green]Schemas restored to {path}[/green]")
