import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from reagent.core.parsers import AssetType
from reagent.llm.parser import GeneratedAsset

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
    """A file to be written when adapting to a target harness.

    Attributes:
        path: Relative path within the repo where the file should be written.
        content: File content as a string.
        mode: Write strategy — ``write`` overwrites, ``append_section`` appends
            a new markdown section, ``merge_json`` deep-merges JSON objects.
    """

    path: str
    content: str
    mode: str = field(default="write")


_ALL_TARGET_FORMATS: tuple[HarnessFormat, ...] = (
    HarnessFormat.CURSOR,
    HarnessFormat.CODEX,
    HarnessFormat.OPENCODE,
)

# Asset types that are meaningfully translated by adapters
_ADAPTABLE_TYPES: frozenset[AssetType] = frozenset(
    {
        AssetType.AGENT,
        AssetType.SKILL,
        AssetType.RULE,
        AssetType.HOOK,
        AssetType.CLAUDE_MD,
        AssetType.COMMAND,
    }
)


def adapt(asset: GeneratedAsset, target: HarnessFormat) -> list[HarnessFile]:
    """Translate a canonical Claude Code asset to a target harness format.

    Returns an empty list for ``CLAUDE_CODE`` and ``AGENTS_MD`` — those are
    handled separately (CLAUDE_CODE is the canonical source; AGENTS_MD is
    generated via :func:`~reagent.harness.agents_md.generate_agents_md`).

    Args:
        asset: The GeneratedAsset in canonical Claude Code format.
        target: The harness format to translate to.

    Returns:
        List of :class:`HarnessFile` instances to write.  May be empty if the
        asset type is not applicable for the target harness.
    """
    if target in (HarnessFormat.CLAUDE_CODE, HarnessFormat.AGENTS_MD):
        return []

    from reagent.harness.adapters import (
        adapt_to_codex,
        adapt_to_cursor,
        adapt_to_opencode,
    )

    match target:
        case HarnessFormat.CURSOR:
            return adapt_to_cursor(asset)
        case HarnessFormat.CODEX:
            return adapt_to_codex(asset)
        case HarnessFormat.OPENCODE:
            return adapt_to_opencode(asset)
        case _:
            logger.warning("Unknown harness target: %s — returning empty list", target)
            return []


def detect_harness(repo_path: Path) -> HarnessFormat:
    """Auto-detect which AI harness a repository uses.

    Delegates to :func:`~reagent.harness.detection.detect_harness`.

    Args:
        repo_path: Root path of the repository to inspect.

    Returns:
        Detected :class:`HarnessFormat`, defaulting to ``CLAUDE_CODE`` when
        no harness-specific artefacts are found.
    """
    from reagent.harness.detection import detect_harness as _detect

    return _detect(repo_path)
