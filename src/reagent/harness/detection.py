import logging
from pathlib import Path

from reagent.harness import HarnessFormat

logger = logging.getLogger(__name__)


def detect_harness(repo_path: Path) -> HarnessFormat:
    """Auto-detect which AI harness a repository uses.

    Checks for harness-specific artefacts in priority order:

    1. ``.claude/`` directory  → Claude Code
    2. ``.cursor/`` directory or ``.cursorrules`` file → Cursor
    3. ``codex.md`` at repo root → Codex
    4. ``opencode.md`` at repo root → OpenCode
    5. Default → Claude Code

    Args:
        repo_path: Root path of the repository to inspect.

    Returns:
        Detected :class:`HarnessFormat`.  Defaults to ``CLAUDE_CODE`` when
        no harness-specific artefacts are found.
    """
    if (repo_path / ".claude").is_dir():
        logger.debug("Detected harness: claude-code (found .claude/)")
        return HarnessFormat.CLAUDE_CODE

    if (repo_path / ".cursor").is_dir() or (repo_path / ".cursorrules").exists():
        logger.debug("Detected harness: cursor (found .cursor/ or .cursorrules)")
        return HarnessFormat.CURSOR

    if (repo_path / "codex.md").exists():
        logger.debug("Detected harness: codex (found codex.md)")
        return HarnessFormat.CODEX

    if (repo_path / "opencode.md").exists():
        logger.debug("Detected harness: opencode (found opencode.md)")
        return HarnessFormat.OPENCODE

    logger.debug("No harness artefacts found; defaulting to claude-code")
    return HarnessFormat.CLAUDE_CODE
