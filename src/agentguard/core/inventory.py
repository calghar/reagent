import json
import logging
from collections.abc import Callable
from pathlib import Path

from agentguard.config import AgentGuardConfig
from agentguard.core.catalog import Catalog, CatalogEntry, entry_from_parsed
from agentguard.core.parsers import (
    AssetScope,
    ParsedAsset,
    parse_agent,
    parse_agent_memory,
    parse_claude_md,
    parse_command,
    parse_hooks,
    parse_rule,
    parse_settings,
    parse_skill,
)

logger = logging.getLogger(__name__)

# Default exclude patterns used when no config is available
_DEFAULT_EXCLUDES = ["node_modules", ".git", "__pycache__", "venv", ".venv"]

type AssetParser[T: ParsedAsset] = Callable[[Path], T]


def _safe_parse[T: ParsedAsset](
    parser: AssetParser[T], path: Path, label: str
) -> T | None:
    """Call a parser function, returning None on error.

    Args:
        parser: The parser callable to invoke.
        path: Path to the file to parse.
        label: Human-readable label for log messages.

    Returns:
        Parsed asset, or None if parsing failed.
    """
    try:
        return parser(path)
    except (OSError, ValueError) as exc:
        logger.warning("Failed to parse %s: %s (%s)", label, path, exc)
        return None


def _collect_md_assets(
    directory: Path,
    parser: AssetParser[ParsedAsset],
    label: str,
    repo_path: Path,
    scope: AssetScope,
) -> list[CatalogEntry]:
    """Collect parsed assets from .md files in a directory.

    Args:
        directory: Directory to scan for .md files.
        parser: Parser function to apply to each file.
        label: Human-readable label for log messages.
        repo_path: Path to the parent repository.
        scope: Asset scope (global, project, or local).

    Returns:
        List of catalog entries for successfully parsed files.
    """
    entries: list[CatalogEntry] = []
    if not directory.is_dir():
        return entries
    for f in sorted(directory.iterdir()):
        if f.suffix == ".md" and f.is_file():
            asset = _safe_parse(parser, f, label)
            if asset:
                entries.append(entry_from_parsed(asset, repo_path, scope))
    return entries


def _find_skill_files(skills_dir: Path) -> list[Path]:
    """Find all SKILL.md files under a skills directory.

    Args:
        skills_dir: The .claude/skills/ directory to search.

    Returns:
        Sorted list of paths to SKILL.md files.
    """
    paths: list[Path] = []
    if not skills_dir.is_dir():
        return paths
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir():
            skill_file = item / "SKILL.md"
            if skill_file.is_file():
                paths.append(skill_file)
        elif item.suffix == ".md" and item.is_file():
            paths.append(item)
    return paths


def _collect_skills(
    skills_dir: Path, repo_path: Path, scope: AssetScope
) -> list[CatalogEntry]:
    """Collect skill assets from .claude/skills/.

    Args:
        skills_dir: Path to the skills directory.
        repo_path: Path to the parent repository.
        scope: Asset scope.

    Returns:
        List of catalog entries for parsed skills.
    """
    entries: list[CatalogEntry] = []
    for skill_file in _find_skill_files(skills_dir):
        asset = _safe_parse(parse_skill, skill_file, "skill")
        if asset:
            entries.append(entry_from_parsed(asset, repo_path, scope))
    return entries


def _collect_hooks_from_settings(
    claude_dir: Path, repo_path: Path, scope: AssetScope
) -> list[CatalogEntry]:
    """Check settings.json for embedded hooks.

    Args:
        claude_dir: Path to the .claude/ directory.
        repo_path: Path to the parent repository.
        scope: Asset scope.

    Returns:
        List with one entry if hooks found, empty otherwise.
    """
    settings_path = claude_dir / "settings.json"
    if not settings_path.is_file():
        return []
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if "hooks" not in data:
        return []
    asset = _safe_parse(parse_hooks, settings_path, "hooks-in-settings")
    if not asset:
        return []
    return [entry_from_parsed(asset, repo_path, scope)]


def _collect_settings(
    claude_dir: Path, repo_path: Path, scope: AssetScope
) -> list[CatalogEntry]:
    """Collect settings assets.

    Args:
        claude_dir: Path to the .claude/ directory.
        repo_path: Path to the parent repository.
        scope: Asset scope.

    Returns:
        List of catalog entries for settings files found.
    """
    entries: list[CatalogEntry] = []
    for settings_file in ("settings.json", "settings.local.json"):
        settings_path = claude_dir / settings_file
        if settings_path.is_file():
            asset = _safe_parse(parse_settings, settings_path, "settings")
            if asset:
                entries.append(entry_from_parsed(asset, repo_path, scope))
    return entries


def scan_claude_dir(
    claude_dir: Path, repo_path: Path, scope: AssetScope
) -> list[CatalogEntry]:
    """Scan a single .claude/ directory and return catalog entries.

    Args:
        claude_dir: Path to the .claude/ directory.
        repo_path: Path to the parent repository.
        scope: Asset scope (global, project, or local).

    Returns:
        List of catalog entries for all assets found.
    """
    if not claude_dir.is_dir():
        return []

    entries: list[CatalogEntry] = []

    # Agents
    entries.extend(
        _collect_md_assets(
            claude_dir / "agents", parse_agent, "agent", repo_path, scope
        )
    )

    # Skills
    entries.extend(_collect_skills(claude_dir / "skills", repo_path, scope))

    # Commands
    entries.extend(
        _collect_md_assets(
            claude_dir / "commands", parse_command, "command", repo_path, scope
        )
    )

    # Rules
    entries.extend(
        _collect_md_assets(claude_dir / "rules", parse_rule, "rule", repo_path, scope)
    )

    # Hooks from hooks.json
    hooks_path = claude_dir / "hooks.json"
    if hooks_path.is_file():
        asset = _safe_parse(parse_hooks, hooks_path, "hooks")
        if asset:
            entries.append(entry_from_parsed(asset, repo_path, scope))

    # Hooks embedded in settings.json
    entries.extend(_collect_hooks_from_settings(claude_dir, repo_path, scope))

    # Settings
    entries.extend(_collect_settings(claude_dir, repo_path, scope))

    # Agent Memory
    memory_dir = claude_dir / "agent-memory"
    if memory_dir.is_dir():
        mem_asset = _safe_parse(parse_agent_memory, memory_dir, "agent-memory")
        if mem_asset:
            entries.append(entry_from_parsed(mem_asset, repo_path, scope))

    # CLAUDE.md inside .claude/
    claude_md = claude_dir / "CLAUDE.md"
    if claude_md.is_file():
        md_asset = _safe_parse(parse_claude_md, claude_md, "claude-md")
        if md_asset:
            entries.append(entry_from_parsed(md_asset, repo_path, scope))

    return entries


def scan_repo(path: Path) -> list[CatalogEntry]:
    """Scan a single repo's .claude/ directory and project-root CLAUDE.md.

    Args:
        path: Path to the repository root.

    Returns:
        List of catalog entries for all assets found.
    """
    path = path.resolve()
    entries: list[CatalogEntry] = []

    # Scan .claude/ directory
    claude_dir = path / ".claude"
    entries.extend(scan_claude_dir(claude_dir, path, AssetScope.PROJECT))

    # Scan project-root CLAUDE.md
    root_claude_md = path / "CLAUDE.md"
    if root_claude_md.is_file():
        asset = _safe_parse(parse_claude_md, root_claude_md, "root-claude-md")
        if asset:
            entries.append(entry_from_parsed(asset, path, AssetScope.PROJECT))

    logger.debug("scan_repo %s: found %d assets", path, len(entries))
    return entries


def scan_path(
    path: Path,
    max_depth: int = 5,
    exclude_patterns: list[str] | None = None,
) -> dict[Path, list[CatalogEntry]]:
    """Scan a path for Claude assets, discovering repos recursively if needed.

    If *path* itself is a repo (has ``.claude/`` or ``CLAUDE.md``), scan it
    directly. Otherwise treat it as a parent directory and discover repos
    underneath up to *max_depth* levels.

    Args:
        path: Filesystem path to scan.
        max_depth: Maximum depth for recursive repo discovery.
        exclude_patterns: Directory names to skip during discovery.

    Returns:
        Mapping of repo path -> list of catalog entries found there.
    """
    path = path.resolve()
    excludes = exclude_patterns or _DEFAULT_EXCLUDES

    # Direct repo?
    if _is_repo_with_assets(path):
        logger.info("Path %s is a repo with assets - scanning directly", path)
        return {path: scan_repo(path)}

    # Otherwise, discover repos underneath
    repos = _find_repos_with_claude(path, max_depth, excludes)
    # Also include repos with only a root CLAUDE.md (no .claude/ dir)
    repos_with_md = _find_repos_with_claude_md(path, max_depth, excludes)
    all_repos = sorted(set(repos) | set(repos_with_md))

    if not all_repos:
        logger.warning("No repos with Claude assets found under %s", path)
        return {}

    logger.info(
        "Discovered %d repo(s) with Claude assets under %s", len(all_repos), path
    )
    result: dict[Path, list[CatalogEntry]] = {}
    for repo_path in all_repos:
        entries = scan_repo(repo_path)
        if entries:
            result[repo_path] = entries
            logger.info("  %s: %d assets", repo_path.name, len(entries))
    return result


def _is_repo_with_assets(path: Path) -> bool:
    """Check if a path is itself a repo containing Claude assets."""
    return (path / ".claude").is_dir() or (path / "CLAUDE.md").is_file()


def _find_repos_with_claude_md(
    root: Path, max_depth: int, exclude_patterns: list[str]
) -> list[Path]:
    """Find directories containing a root CLAUDE.md (but no .claude/ dir).

    These are repos that have a CLAUDE.md but not a .claude/ directory,
    which ``_find_repos_with_claude`` would miss.
    """
    repos: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack:
        current, depth = stack.pop()
        if depth > max_depth or not current.is_dir():
            continue

        if (current / "CLAUDE.md").is_file() and not (current / ".claude").is_dir():
            repos.append(current)

        for child in reversed(_list_child_dirs(current, exclude_patterns)):
            stack.append((child, depth + 1))

    return sorted(repos)


def _should_skip(name: str, exclude_patterns: list[str]) -> bool:
    """Check if a directory name should be skipped during scanning.

    Args:
        name: Directory name to check.
        exclude_patterns: List of names to exclude.

    Returns:
        True if the directory should be skipped.
    """
    return name in exclude_patterns or name == ".claude"


def _list_child_dirs(directory: Path, exclude_patterns: list[str]) -> list[Path]:
    """List non-excluded child directories.

    Args:
        directory: Parent directory to list.
        exclude_patterns: Directory names to exclude.

    Returns:
        Sorted list of child directory paths.
    """
    try:
        return [
            child
            for child in sorted(directory.iterdir())
            if child.is_dir() and not _should_skip(child.name, exclude_patterns)
        ]
    except PermissionError:
        return []


def _find_repos_with_claude(
    root: Path, max_depth: int, exclude_patterns: list[str]
) -> list[Path]:
    """Find directories containing .claude/ under a root directory.

    Args:
        root: Root directory to search from.
        max_depth: Maximum directory depth to traverse.
        exclude_patterns: Directory names to skip.

    Returns:
        Sorted list of repository paths containing .claude/ dirs.
    """
    repos: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack:
        current, depth = stack.pop()
        if depth > max_depth or not current.is_dir():
            continue

        if (current / ".claude").is_dir():
            repos.append(current)

        for child in reversed(_list_child_dirs(current, exclude_patterns)):
            stack.append((child, depth + 1))

    return sorted(repos)


def scan_all(config: AgentGuardConfig) -> list[CatalogEntry]:
    """Scan all configured root directories for repos with .claude/ dirs.

    Args:
        config: AgentGuard configuration with scan roots and options.

    Returns:
        List of catalog entries from all discovered repositories.
    """
    entries: list[CatalogEntry] = []
    seen_repos: set[Path] = set()

    for root in config.scan.roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            logger.warning("Scan root does not exist: %s", root)
            continue

        repos = _find_repos_with_claude(
            root, config.scan.max_depth, config.scan.exclude_patterns
        )
        for repo_path in repos:
            resolved = repo_path.resolve()
            if resolved in seen_repos:
                continue
            seen_repos.add(resolved)
            entries.extend(scan_repo(repo_path))

    return entries


def scan_global() -> list[CatalogEntry]:
    """Scan ~/.claude/ for global assets.

    Returns:
        List of catalog entries for global Claude Code assets.
    """
    global_claude = Path.home() / ".claude"
    if not global_claude.is_dir():
        return []
    return scan_claude_dir(global_claude, Path.home(), AssetScope.GLOBAL)


def run_inventory(config: AgentGuardConfig, catalog: Catalog) -> tuple[int, int, int]:
    """Run a full inventory scan and update the catalog.

    Args:
        config: AgentGuard configuration with scan roots.
        catalog: Catalog instance to update.

    Returns:
        Tuple of (added_count, modified_count, removed_count).
    """
    # Scan all configured roots
    new_entries = scan_all(config)

    # Also scan global
    new_entries.extend(scan_global())

    # Diff and apply
    added, modified, removed_ids = catalog.diff(new_entries)
    catalog.apply_diff(added, modified, removed_ids)
    catalog.save()

    return len(added), len(modified), len(removed_ids)
