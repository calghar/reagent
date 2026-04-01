import logging
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

from reagent.telemetry.events import (
    ParsedSession,
    TaskBlock,
    find_sessions_dir,
    parse_all_sessions,
)

if TYPE_CHECKING:
    from reagent.config import ReagentConfig

logger = logging.getLogger(__name__)


def _strip_session_content(sessions: list[ParsedSession]) -> None:
    """Remove content payloads from sessions when exclude_content is enabled.

    Clears tool_input values and message content to prevent storing
    sensitive content while preserving structural metadata.

    Args:
        sessions: Parsed sessions to strip in-place.
    """
    for session in sessions:
        for tc in session.tool_calls:
            tc.tool_input = {}
        for msg in session.messages:
            msg.content = ""
        for block in session.task_blocks:
            for tc in block.tool_calls:
                tc.tool_input = {}
            for msg in block.messages:
                msg.content = ""


class WorkflowStep(BaseModel):
    """A single step in a detected workflow."""

    action: str  # e.g. "Read", "Edit", "Bash(test)"
    frequency: float = 0.0  # how often this step appears


class Workflow(BaseModel):
    """A detected workflow pattern."""

    name: str
    intent: str  # implement, review, debug, etc.
    frequency: float = 0.0  # occurrences per session
    avg_turns: float = 0.0
    typical_sequence: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)
    correction_rate: float = 0.0


class CorrectionHotspot(BaseModel):
    """A file pattern with high correction rate."""

    file_pattern: str
    correction_rate: float
    correction_count: int
    suggestion: str = ""


class WorkflowProfile(BaseModel):
    """Complete workflow profile for a repository."""

    repo_path: str
    repo_name: str
    session_count: int = 0
    total_tool_calls: int = 0
    total_corrections: int = 0
    avg_session_duration: float = 0.0
    workflows: list[Workflow] = Field(default_factory=list)
    tool_frequency: dict[str, int] = Field(default_factory=dict)
    correction_hotspots: list[CorrectionHotspot] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)


# Intent classification rules: tool sequence patterns -> intent
INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("debug", ["Read", "Grep", "Edit", "Bash"]),
    ("implement", ["Read", "Edit", "Bash"]),
    ("implement", ["Write", "Edit", "Bash"]),
    ("review", ["Read", "Read", "Grep"]),
    ("research", ["Read", "Grep", "Read"]),
    ("refactor", ["Read", "Edit", "Edit"]),
    ("docs", ["Read", "Write"]),
    ("release", ["Bash", "Bash"]),
    ("test", ["Bash", "Read", "Edit"]),
]


def _normalize_tool_name(name: str) -> str:
    """Normalize a tool name to its base form.

    Maps variant tool names to canonical categories:
    Read, Edit, Write, or Bash.

    Args:
        name: Raw tool name from a session transcript.

    Returns:
        Canonical tool category, or the original name if unrecognized.
    """
    read_tools = {"Read", "Glob", "Grep", "read_file", "list_dir"}
    edit_tools = {"Edit", "MultiEdit", "edit_file", "replace_file"}
    write_tools = {"Write", "write_file", "create_file"}
    bash_tools = {"Bash", "bash", "run_command"}

    if name in read_tools:
        return "Read"
    if name in edit_tools:
        return "Edit"
    if name in write_tools:
        return "Write"
    if name in bash_tools:
        return "Bash"
    return name


def _classify_bash_intent(tool_input: dict[str, Any]) -> str | None:
    """Classify a Bash tool call by its command content.

    Args:
        tool_input: The tool_input dict from a Bash tool call.

    Returns:
        Intent string ("test", "release", "ops"), or None if unrecognized.
    """
    cmd = str(tool_input.get("command", tool_input.get("cmd", "")))
    if not cmd:
        return None
    if re.search(r"\b(test|pytest|jest|mocha|vitest)\b", cmd):
        return "test"
    if re.search(r"\b(git\s+(push|merge|tag)|gh\s+pr)\b", cmd):
        return "release"
    if re.search(r"\b(deploy|kubectl|docker|terraform)\b", cmd):
        return "ops"
    return None


def classify_intent(block: TaskBlock) -> str:
    """Classify the intent of a task block based on tool sequence.

    Args:
        block: A task block with tool calls.

    Returns:
        Intent string (implement, review, debug, etc.)
    """
    if not block.tool_calls:
        return "unknown"

    tools = [_normalize_tool_name(tc.tool_name) for tc in block.tool_calls]

    # Check for Bash-specific intents first
    for tc in block.tool_calls:
        if _normalize_tool_name(tc.tool_name) == "Bash":
            bash_intent = _classify_bash_intent(tc.tool_input)
            if bash_intent:
                return bash_intent

    # Match against intent patterns (subsequence matching)
    for intent, pattern in INTENT_PATTERNS:
        if _is_subsequence(pattern, tools):
            return intent

    # Fallback: majority tool type
    if tools.count("Read") > len(tools) // 2:
        return "review"
    if tools.count("Edit") > len(tools) // 3:
        return "implement"
    return "unknown"


def _is_subsequence(pattern: list[str], sequence: list[str]) -> bool:
    """Check if pattern is a subsequence of sequence.

    Args:
        pattern: Ordered list of elements to find.
        sequence: List to search within.

    Returns:
        True if all pattern elements appear in order within sequence.
    """
    it = iter(sequence)
    return all(p in it for p in pattern)


def _extract_workflows(
    sessions: list[ParsedSession],
) -> list[Workflow]:
    """Extract workflow patterns from session data.

    Args:
        sessions: List of parsed sessions to analyze.

    Returns:
        List of detected workflows sorted by frequency (descending).
    """
    intent_blocks: dict[str, list[TaskBlock]] = {}

    for session in sessions:
        for block in session.task_blocks:
            intent = classify_intent(block)
            block.intent = intent
            if intent not in intent_blocks:
                intent_blocks[intent] = []
            intent_blocks[intent].append(block)

    workflows: list[Workflow] = []
    total_sessions = max(len(sessions), 1)

    for intent, blocks in sorted(intent_blocks.items()):
        if intent == "unknown":
            continue

        all_tools: list[str] = []
        total_turns = 0
        for block in blocks:
            tools = [_normalize_tool_name(tc.tool_name) for tc in block.tool_calls]
            all_tools.extend(tools)
            total_turns += len(block.tool_calls)

        # Find most common tool sequence
        tool_counter = Counter(all_tools)
        top_tools = [t for t, _ in tool_counter.most_common(6)]

        wf = Workflow(
            name=intent,
            intent=intent,
            frequency=len(blocks) / total_sessions,
            avg_turns=total_turns / max(len(blocks), 1),
            typical_sequence=top_tools,
            tools_used=list(tool_counter.keys()),
        )
        workflows.append(wf)

    return sorted(workflows, key=lambda w: -w.frequency)


def _find_correction_hotspots(
    sessions: list[ParsedSession],
) -> list[CorrectionHotspot]:
    """Find file patterns with high correction rates.

    Args:
        sessions: List of parsed sessions to analyze.

    Returns:
        List of hotspots sorted by correction rate (descending).
    """
    file_corrections: dict[str, int] = {}
    file_edits: dict[str, int] = {}

    for session in sessions:
        for correction in session.corrections:
            fp = correction.file_path
            file_corrections[fp] = file_corrections.get(fp, 0) + 1

        for tc in session.tool_calls:
            if tc.tool_name in (
                "Edit",
                "Write",
                "MultiEdit",
                "edit_file",
                "write_file",
            ):
                from reagent.telemetry.events import (
                    _extract_file_path_from_tool,
                )

                fp = _extract_file_path_from_tool(tc.tool_input)
                if fp:
                    file_edits[fp] = file_edits.get(fp, 0) + 1

    hotspots: list[CorrectionHotspot] = []
    for fp, corrections in file_corrections.items():
        edits = file_edits.get(fp, 1)
        rate = corrections / max(edits, 1)
        if rate > 0.1:  # >10% correction rate
            hotspots.append(
                CorrectionHotspot(
                    file_pattern=fp,
                    correction_rate=rate,
                    correction_count=corrections,
                    suggestion=(
                        f"High correction rate ({rate:.0%})"
                        " — consider adding specific rules"
                    ),
                )
            )

    return sorted(hotspots, key=lambda h: -h.correction_rate)


def profile_repo(
    repo_path: Path,
    config: "ReagentConfig | None" = None,
) -> WorkflowProfile:
    """Analyze all sessions for a repo and produce a workflow profile.

    Args:
        repo_path: Path to the repository.
        config: Optional ReagentConfig to control profiling behaviour.
            When ``config.telemetry.exclude_content`` is ``True``,
            tool inputs and message content are stripped before analysis.

    Returns:
        WorkflowProfile with detected workflows and metrics.
    """
    repo_path = repo_path.resolve()
    profile = WorkflowProfile(
        repo_path=str(repo_path),
        repo_name=repo_path.name,
    )

    sessions_dir = find_sessions_dir(repo_path)
    if sessions_dir is None:
        return profile

    sessions = parse_all_sessions(sessions_dir)
    if not sessions:
        return profile

    if config and config.telemetry.exclude_content:
        _strip_session_content(sessions)

    return _build_profile(profile, sessions)


def _build_profile(
    profile: WorkflowProfile, sessions: list[ParsedSession]
) -> WorkflowProfile:
    """Build workflow profile from parsed sessions.

    Args:
        profile: Profile object to populate with metrics.
        sessions: Parsed sessions to aggregate.

    Returns:
        The populated WorkflowProfile.
    """
    profile.session_count = len(sessions)
    profile.total_tool_calls = sum(s.metrics.tool_count for s in sessions)
    profile.total_corrections = sum(s.metrics.correction_count for s in sessions)

    durations = [
        s.metrics.duration_seconds for s in sessions if s.metrics.duration_seconds > 0
    ]
    if durations:
        profile.avg_session_duration = sum(durations) / len(durations)

    # Aggregate tool frequencies
    tool_freq: dict[str, int] = {}
    for session in sessions:
        for tool, count in session.metrics.tool_counts.items():
            tool_freq[tool] = tool_freq.get(tool, 0) + count
    profile.tool_frequency = dict(sorted(tool_freq.items(), key=lambda x: -x[1]))

    profile.workflows = _extract_workflows(sessions)
    profile.correction_hotspots = _find_correction_hotspots(sessions)

    # Identify coverage gaps
    detected_intents = {w.intent for w in profile.workflows}
    common_intents = {
        "implement",
        "review",
        "debug",
        "test",
        "docs",
    }
    gaps = common_intents - detected_intents
    profile.coverage_gaps = sorted(gaps)

    return profile


def save_workflow_model(
    profile: WorkflowProfile, output_dir: Path | None = None
) -> Path:
    """Save a workflow profile as a YAML file.

    Args:
        profile: The workflow profile to save.
        output_dir: Directory for output. Defaults to ~/.reagent/workflows/.

    Returns:
        Path to the saved YAML file.
    """
    if output_dir is None:
        output_dir = Path.home() / ".reagent" / "workflows"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize repo name for filename
    safe_name = re.sub(r"[^\w\-]", "_", profile.repo_name)
    output_path = output_dir / f"{safe_name}.yaml"

    data = profile.model_dump(mode="json")
    output_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    return output_path
