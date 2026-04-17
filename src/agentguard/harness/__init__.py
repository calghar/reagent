import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class HarnessFormat(StrEnum):
    """Supported AI-harness target formats."""

    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    CURSOR = "cursor"
    OPENCODE = "opencode"
    AGENTS_MD = "agents-md"


@dataclass
class HarnessFile:
    """A file to be written when adapting to a target harness."""

    path: str
    content: str
    mode: str = field(default="write")


def detect_harness(repo_path: Path) -> HarnessFormat:
    """Auto-detect which AI harness a repository uses."""
    from agentguard.harness.detection import detect_harness as _detect

    return _detect(repo_path)
