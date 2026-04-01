import logging
from pathlib import Path
from typing import Any

import yaml as _yaml

logger = logging.getLogger(__name__)

# Asset types recognized by the exemplar scanner
_ASSET_SEARCH_DIRS: dict[str, str] = {
    "agent": "agents",
    "skill": "skills",
    "rule": "rules",
    "command": "commands",
}


def _find_skill_files(skills_dir: Path) -> list[Path]:
    """Locate SKILL.md files inside a skills directory.

    Args:
        skills_dir: Path to the ``.claude/skills/`` directory.

    Returns:
        Sorted list of skill file paths.
    """
    found: list[Path] = []
    for d in sorted(skills_dir.iterdir()):
        if d.is_dir() and (d / "SKILL.md").is_file():
            found.append(d / "SKILL.md")
        elif d.suffix == ".md" and d.is_file():
            found.append(d)
    return found


def _find_asset_files(
    claude_dir: Path,
    asset_type: str,
    sibling: Path,
) -> list[Path]:
    """Locate asset files of the given type inside a .claude/ directory.

    Args:
        claude_dir: Path to a ``<repo>/.claude/`` directory.
        asset_type: One of agent, skill, rule, command, hook, claude_md.
        sibling: The parent repo path (used for CLAUDE.md fallback).

    Returns:
        Sorted list of discovered file paths.
    """
    if asset_type == "hook":
        hooks_path = claude_dir / "hooks.json"
        return [hooks_path] if hooks_path.is_file() else []

    if asset_type == "claude_md":
        for loc in [sibling / "CLAUDE.md", claude_dir / "CLAUDE.md"]:
            if loc.is_file():
                return [loc]
        return []

    if asset_type == "skill":
        skills_dir = claude_dir / "skills"
        if skills_dir.is_dir():
            return _find_skill_files(skills_dir)
        return []

    subdir_name = _ASSET_SEARCH_DIRS.get(asset_type)
    if not subdir_name:
        return []
    subdir = claude_dir / subdir_name
    return sorted(subdir.glob("*.md")) if subdir.is_dir() else []


def _read_exemplar(fp: Path) -> dict[str, str] | None:
    """Read a single exemplar file and return its metadata.

    Args:
        fp: Path to the exemplar file.

    Returns:
        Dict with ``repo``, ``name``, ``content`` keys, or None on error.
    """
    try:
        content = fp.read_text(encoding="utf-8")
    except OSError:
        logger.debug("Could not read exemplar %s", fp)
        return None

    # Walk up to find the repo root (parent of .claude/)
    repo_name = fp.parent.name
    for parent in fp.parents:
        if parent.name == ".claude":
            repo_name = parent.parent.name
            break

    return {
        "repo": repo_name,
        "name": fp.stem if fp.stem != "SKILL" else fp.parent.name,
        "content": content,
    }


def _collect_from_sibling(
    sibling: Path,
    asset_type: str,
    max_exemplars: int,
    exemplars: list[dict[str, str]],
) -> None:
    """Collect exemplar assets from a single sibling repo.

    Args:
        sibling: Path to the sibling repository.
        asset_type: Asset type to search for.
        max_exemplars: Stop collecting once this count is reached.
        exemplars: Mutable list to append results into.
    """
    claude_dir = sibling / ".claude"
    if not claude_dir.is_dir():
        return

    for fp in _find_asset_files(claude_dir, asset_type, sibling):
        if len(exemplars) >= max_exemplars:
            return
        entry = _read_exemplar(fp)
        if entry:
            exemplars.append(entry)


def discover_exemplar_assets(
    repo_path: Path,
    asset_type: str,
    max_exemplars: int = 3,
) -> list[dict[str, str]]:
    """Find existing assets of the given type from sibling repos.

    Walks the parent directory of *repo_path* looking for repos that already
    have Claude Code assets of the requested type.  Returns the file content
    alongside basic metadata so generators can learn from real examples.

    Args:
        repo_path: The current repository path.
        asset_type: Asset type to search for (e.g. ``"agent"``).
        max_exemplars: Maximum exemplars to return.

    Returns:
        List of dicts with keys ``repo``, ``name``, ``content``.
    """
    parent = repo_path.resolve().parent
    if not parent.is_dir():
        return []

    exemplars: list[dict[str, str]] = []
    resolved = repo_path.resolve()

    siblings = [
        s for s in sorted(parent.iterdir()) if s.is_dir() and s.resolve() != resolved
    ]

    for sibling in siblings:
        if len(exemplars) >= max_exemplars:
            break
        _collect_from_sibling(
            sibling,
            asset_type,
            max_exemplars,
            exemplars,
        )

    if exemplars:
        logger.info(
            "Found %d exemplar(s) for %s from sibling repos: %s",
            len(exemplars),
            asset_type,
            [e["repo"] + "/" + e["name"] for e in exemplars],
        )
    return exemplars


def _parse_exemplar_frontmatter(lines: list[str]) -> list[str]:
    """Extract frontmatter keys from lines starting with ``---``.

    Args:
        lines: All lines of the exemplar content.

    Returns:
        List of frontmatter field names, or empty list if none found.
    """
    if not lines or lines[0].strip() != "---":
        return []

    end_idx = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx <= 0:
        return []

    try:
        fm = _yaml.safe_load("\n".join(lines[1:end_idx]))
        if isinstance(fm, dict):
            return list(fm.keys())
    except _yaml.YAMLError:
        pass
    return []


def _classify_section(section: str) -> dict[str, bool]:
    """Classify a section heading into boolean feature flags.

    Args:
        section: The section heading text (without ``##`` prefix).

    Returns:
        Dict of boolean flags that are True for this section.
    """
    lower = section.lower()
    return {
        "has_constraints": "constraint" in lower or "rule" in lower,
        "has_checklist": "check" in lower,
        "has_architecture": "architect" in lower or "stack" in lower,
        "has_steps": "step" in lower or "workflow" in lower,
    }


def _is_constraint_line(stripped: str) -> bool:
    """Check if a line indicates a constraint.

    Args:
        stripped: A whitespace-stripped line of text.

    Returns:
        True if the line starts with a constraint marker.
    """
    return stripped.startswith("- **Never**") or stripped.startswith("- **Do not**")


def extract_structure_from_exemplar(
    exemplar_content: str,
) -> dict[str, Any]:
    """Extract structural elements from an exemplar asset.

    Parses frontmatter fields, section headings, and general structure
    to guide generation of new assets.

    Args:
        exemplar_content: Raw markdown content of the exemplar file.

    Returns:
        Dict describing the structure: sections, frontmatter keys, and
        boolean flags for common sections (constraints, checklist, etc.).
    """
    structure: dict[str, Any] = {
        "sections": [],
        "frontmatter_keys": [],
        "has_constraints": False,
        "has_checklist": False,
        "has_architecture": False,
        "has_steps": False,
    }

    lines = exemplar_content.splitlines()
    structure["frontmatter_keys"] = _parse_exemplar_frontmatter(lines)

    for line in lines:
        stripped = line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            structure["sections"].append(section)
            for key, val in _classify_section(section).items():
                if val:
                    structure[key] = True

        if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
            structure["has_checklist"] = True
        if _is_constraint_line(stripped):
            structure["has_constraints"] = True

    return structure
