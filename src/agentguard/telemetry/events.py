import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    """A single tool invocation extracted from a session transcript."""

    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: str = ""
    timestamp: datetime | None = None
    success: bool = True


class Message(BaseModel):
    """A message in a session transcript."""

    role: str  # "user", "assistant", "system"
    content: str = ""
    timestamp: datetime | None = None


class TaskBlock(BaseModel):
    """A contiguous sequence of tool calls toward one goal."""

    tool_calls: list[ToolCall] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    intent: str = ""  # filled by profiler


class CorrectionEvent(BaseModel):
    """A user correction after an agent edit on the same file."""

    file_path: str
    agent_tool_call: ToolCall
    user_tool_call: ToolCall


class SessionMetrics(BaseModel):
    """Aggregate metrics for one parsed session."""

    session_id: str
    repo_path: str = ""
    tool_count: int = 0
    turn_count: int = 0
    correction_count: int = 0
    duration_seconds: float = 0.0
    tool_counts: dict[str, int] = Field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None


class ParsedSession(BaseModel):
    """A fully parsed Claude Code session transcript."""

    session_id: str
    repo_path: str = ""
    messages: list[Message] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    task_blocks: list[TaskBlock] = Field(default_factory=list)
    corrections: list[CorrectionEvent] = Field(default_factory=list)
    metrics: SessionMetrics = Field(
        default_factory=lambda: SessionMetrics(session_id="")
    )
    compact_events: list[dict[str, Any]] = Field(default_factory=list)


def _find_project_dir_name(repo_path: Path) -> str:
    """Compute the project directory name Claude Code uses.

    Claude Code mangles the absolute resolved path by replacing every
    non-alphanumeric character with ``-``.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        The mangled directory name used under ``~/.claude/projects/``.
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", str(repo_path.resolve()))


def _dir_has_sessions(project_dir: Path) -> bool:
    """Return True if the directory contains at least one ``.jsonl`` file."""
    return any(project_dir.glob("*.jsonl"))


def find_sessions_dir(
    repo_path: Path,
    claude_projects_path: Path | None = None,
) -> Path | None:
    """Find the Claude Code sessions directory for a given repo.

    Claude Code stores session ``.jsonl`` files and UUID sub-directories
    directly inside ``~/.claude/projects/<mangled-path>/``.

    Args:
        repo_path: Path to the repository.
        claude_projects_path: Override for ``~/.claude/projects/``.  When
            ``None``, falls back to ``$CLAUDE_PROJECTS_PATH`` env var, then
            the default ``~/.claude/projects/``.

    Returns:
        Path to the project directory containing session files, or None.
    """
    if claude_projects_path is None:
        env_val = os.environ.get("CLAUDE_PROJECTS_PATH", "").strip()
        if env_val:
            claude_projects_path = Path(env_val).expanduser()
        else:
            claude_projects_path = Path.home() / ".claude" / "projects"

    if not claude_projects_path.exists():
        return None

    # Try direct name match (path-mangled convention)
    mangled = _find_project_dir_name(repo_path)
    candidate = claude_projects_path / mangled
    if candidate.is_dir() and _dir_has_sessions(candidate):
        return candidate

    # Scan all project dirs for a session referencing this repo
    return _scan_project_dirs(claude_projects_path, repo_path)


def _scan_project_dirs(claude_dir: Path, repo_path: Path) -> Path | None:
    """Scan project directories for sessions matching a repo.

    Args:
        claude_dir: The ``~/.claude/projects/`` directory.
        repo_path: Target repository path to match against.

    Returns:
        Path to a matching project directory, or None.
    """
    resolved = repo_path.resolve()
    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        if not _dir_has_sessions(project_dir):
            continue
        match = _check_sessions_for_repo(project_dir, resolved)
        if match:
            return match
    return None


def _check_sessions_for_repo(project_dir: Path, resolved_repo: Path) -> Path | None:
    """Check if any session in a directory references the given repo.

    Reads the first few lines of each ``.jsonl`` file looking for a
    ``cwd`` value that matches ``resolved_repo``.  Claude Code may write
    ``queue-operation`` lines first (with ``cwd: null``), so a single-line
    check is not enough.

    Args:
        project_dir: Directory containing ``.jsonl`` session files.
        resolved_repo: Resolved absolute path of the target repo.

    Returns:
        The project_dir if a match is found, or None.
    """
    max_lines = 10
    for session_file in project_dir.glob("*.jsonl"):
        try:
            with session_file.open(encoding="utf-8") as fh:
                for _, line in zip(range(max_lines), fh, strict=False):
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    cwd = data.get("cwd")
                    if cwd and Path(cwd).resolve() == resolved_repo:
                        return project_dir
        except (json.JSONDecodeError, OSError):
            continue
    return None


def list_session_files(sessions_dir: Path) -> list[Path]:
    """List all JSONL session files in a sessions directory.

    Args:
        sessions_dir: Path to a directory containing session files.

    Returns:
        Sorted list of .jsonl file paths.
    """
    if not sessions_dir.exists():
        return []
    return sorted(sessions_dir.glob("*.jsonl"))


def _parse_timestamp(data: dict[str, Any]) -> datetime | None:
    """Extract timestamp from a transcript entry.

    Args:
        data: A parsed JSON entry from a session transcript.

    Returns:
        Parsed datetime in UTC, or None if no valid timestamp found.
    """
    ts = data.get("timestamp") or data.get("ts") or data.get("createdAt")
    if ts is None:
        return None
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(ts, int | float):
        try:
            return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=UTC)
        except (ValueError, OSError):
            return None
    return None


def _extract_file_path_from_tool(tool_input: dict[str, Any]) -> str:
    """Extract file path from tool input if present.

    Args:
        tool_input: The tool_input dict from a tool call.

    Returns:
        File path string, or empty string if not found.
    """
    for key in ("file_path", "filePath", "path", "file"):
        val = tool_input.get(key)
        if val and isinstance(val, str):
            return str(val)
    return ""


EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "edit_file", "write_file"})


class _SessionParseState:
    """Mutable state accumulated during session parsing."""

    def __init__(self) -> None:
        """Initialize empty parse state for a new session."""
        self.block_tools: list[ToolCall] = []
        self.block_messages: list[Message] = []
        self.agent_edits: dict[str, ToolCall] = {}


def parse_session(session_path: Path) -> ParsedSession:
    """Parse a single Claude Code session transcript.

    Args:
        session_path: Path to a .jsonl session file.

    Returns:
        ParsedSession with extracted data and computed metrics.
    """
    session_id = session_path.stem
    session = ParsedSession(
        session_id=session_id,
        metrics=SessionMetrics(session_id=session_id),
    )
    state = _SessionParseState()

    for data in _iter_jsonl(session_path):
        _process_entry(data, session, state)

    # Close final task block
    if state.block_tools:
        block = _close_task_block(state.block_tools, state.block_messages)
        session.task_blocks.append(block)

    _compute_metrics(session)
    return session


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read and parse all JSONL lines from a file.

    Args:
        path: Path to a .jsonl file.

    Returns:
        List of parsed JSON dicts, skipping malformed lines.
    """
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _process_entry(
    data: dict[str, Any],
    session: ParsedSession,
    state: _SessionParseState,
) -> None:
    """Process a single transcript entry.

    Args:
        data: Parsed JSON dict from one JSONL line.
        session: The session being built up.
        state: Mutable parse state for task block tracking.
    """
    entry_type = data.get("type", "")
    role = data.get("role", "")
    ts = _parse_timestamp(data)

    if not session.repo_path:
        cwd = data.get("cwd", "")
        if cwd:
            session.repo_path = cwd

    if _is_tool_use(entry_type, data):
        _process_tool_use(data, ts, session, state)
    elif entry_type == "tool_result":
        _handle_tool_result(data, session)
    elif role in ("user", "assistant", "system"):
        _process_message(data, role, ts, session, state)
    elif entry_type == "compact":
        session.compact_events.append(data)


def _process_tool_use(
    data: dict[str, Any],
    ts: datetime | None,
    session: ParsedSession,
    state: _SessionParseState,
) -> None:
    """Process a tool use entry.

    Args:
        data: Parsed JSON dict for the tool_use entry.
        ts: Timestamp of the entry, if available.
        session: The session being built up.
        state: Mutable parse state for task block tracking.
    """
    tc = _handle_tool_use(data, ts)
    session.tool_calls.append(tc)
    state.block_tools.append(tc)

    if tc.tool_name in EDIT_TOOLS:
        fp = _extract_file_path_from_tool(tc.tool_input)
        if fp:
            state.agent_edits[fp] = tc


def _process_message(
    data: dict[str, Any],
    role: str,
    ts: datetime | None,
    session: ParsedSession,
    state: _SessionParseState,
) -> None:
    """Process a message entry.

    Args:
        data: Parsed JSON dict for the message entry.
        role: Message role ("user", "assistant", or "system").
        ts: Timestamp of the entry, if available.
        session: The session being built up.
        state: Mutable parse state for task block tracking.
    """
    msg = _handle_message(data, role, ts)
    session.messages.append(msg)
    state.block_messages.append(msg)

    if role == "user" and state.block_tools:
        block = _close_task_block(state.block_tools, state.block_messages[:-1])
        session.task_blocks.append(block)
        state.block_tools = []
        state.block_messages = [msg]

    if role == "user":
        _detect_corrections(data, ts, state.agent_edits, session)


def _is_tool_use(entry_type: str, data: dict[str, Any]) -> bool:
    """Check if a transcript entry is a tool use.

    Args:
        entry_type: The "type" field from the transcript entry.
        data: The full parsed JSON dict.

    Returns:
        True if the entry represents a tool invocation.
    """
    if entry_type == "tool_use":
        return True
    return (
        entry_type == "content_block"
        and data.get("content_block", {}).get("type") == "tool_use"
    )


def _handle_tool_use(data: dict[str, Any], ts: datetime | None) -> ToolCall:
    """Extract a ToolCall from a tool_use entry.

    Args:
        data: Parsed JSON dict containing tool use data.
        ts: Timestamp of the entry, if available.

    Returns:
        Populated ToolCall model.
    """
    tool_data = data.get("content_block", data)
    tool_name = tool_data.get("name", tool_data.get("tool_name", "unknown"))
    tool_input = tool_data.get("input", tool_data.get("tool_input", {}))
    if not isinstance(tool_input, dict):
        tool_input = {}
    return ToolCall(tool_name=tool_name, tool_input=tool_input, timestamp=ts)


def _handle_tool_result(data: dict[str, Any], session: ParsedSession) -> None:
    """Update the last tool call with its result.

    Args:
        data: Parsed JSON dict containing tool result data.
        session: The session whose last tool call is updated.
    """
    output = data.get("content", data.get("output", ""))
    is_error = data.get("is_error", False)
    if isinstance(output, list):
        output = " ".join(
            str(block.get("text", "")) for block in output if isinstance(block, dict)
        )
    if session.tool_calls:
        session.tool_calls[-1].tool_output = str(output)[:500]
        session.tool_calls[-1].success = not is_error


def _handle_message(data: dict[str, Any], role: str, ts: datetime | None) -> Message:
    """Extract a Message from a transcript entry.

    Args:
        data: Parsed JSON dict containing message data.
        role: Message role ("user", "assistant", or "system").
        ts: Timestamp of the entry, if available.

    Returns:
        Populated Message model.
    """
    content = data.get("content", "")
    if isinstance(content, list):
        content = " ".join(
            str(block.get("text", "")) for block in content if isinstance(block, dict)
        )
    return Message(role=role, content=str(content)[:500], timestamp=ts)


def _close_task_block(tools: list[ToolCall], messages: list[Message]) -> TaskBlock:
    """Create a TaskBlock from accumulated tools and messages.

    Args:
        tools: Tool calls in this block.
        messages: Messages in this block.

    Returns:
        TaskBlock with start/end times derived from tool timestamps.
    """
    block = TaskBlock(tool_calls=tools, messages=messages)
    if tools and tools[0].timestamp:
        block.start_time = tools[0].timestamp
    if tools and tools[-1].timestamp:
        block.end_time = tools[-1].timestamp
    return block


def _detect_corrections(
    data: dict[str, Any],
    ts: datetime | None,
    last_agent_edits: dict[str, ToolCall],
    session: ParsedSession,
) -> None:
    """Detect user corrections after agent edits.

    Args:
        data: Parsed JSON dict for the user message.
        ts: Timestamp of the entry, if available.
        last_agent_edits: Map of file paths to the last agent edit ToolCall.
        session: The session to append corrections to.
    """
    user_tool_data = data.get("tool_use", {})
    if not isinstance(user_tool_data, dict):
        return
    user_tool_name = user_tool_data.get("name", "")
    user_input = user_tool_data.get("input", {})
    if not isinstance(user_input, dict):
        return
    if user_tool_name not in EDIT_TOOLS:
        return
    fp = _extract_file_path_from_tool(user_input)
    if fp and fp in last_agent_edits:
        user_tc = ToolCall(
            tool_name=user_tool_name,
            tool_input=user_input,
            timestamp=ts,
        )
        session.corrections.append(
            CorrectionEvent(
                file_path=fp,
                agent_tool_call=last_agent_edits[fp],
                user_tool_call=user_tc,
            )
        )


def _compute_metrics(session: ParsedSession) -> None:
    """Compute aggregate metrics for a parsed session.

    Args:
        session: The session whose metrics field is populated in-place.
    """
    session.metrics.repo_path = session.repo_path
    session.metrics.tool_count = len(session.tool_calls)
    session.metrics.turn_count = sum(1 for m in session.messages if m.role == "user")
    session.metrics.correction_count = len(session.corrections)

    tool_counts: dict[str, int] = {}
    for tc in session.tool_calls:
        tool_counts[tc.tool_name] = tool_counts.get(tc.tool_name, 0) + 1
    session.metrics.tool_counts = tool_counts

    timestamps = [tc.timestamp for tc in session.tool_calls if tc.timestamp] + [
        m.timestamp for m in session.messages if m.timestamp
    ]
    if timestamps:
        session.metrics.start_time = min(timestamps)
        session.metrics.end_time = max(timestamps)
        delta = session.metrics.end_time - session.metrics.start_time
        session.metrics.duration_seconds = delta.total_seconds()


def parse_all_sessions(sessions_dir: Path) -> list[ParsedSession]:
    """Parse all session transcripts in a directory.

    Args:
        sessions_dir: Path to a sessions/ directory.

    Returns:
        List of parsed sessions, sorted by start time.
    """
    sessions: list[ParsedSession] = []
    for path in list_session_files(sessions_dir):
        try:
            session = parse_session(path)
            sessions.append(session)
        except OSError:
            continue

    return sorted(
        sessions,
        key=lambda s: s.metrics.start_time or datetime.min.replace(tzinfo=UTC),
    )
