import logging
import re
import shlex
import statistics
from collections.abc import Iterable
from urllib.parse import urlparse

from agentguard.attestation.fingerprint import BehavioralFingerprint
from agentguard.sandbox.drivers import DriverEvent, DriverEventKind

logger = logging.getLogger(__name__)


_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_FETCH_TOOLS = {"WebFetch", "WebSearch"}
_BASH_TOOLS = {"Bash"}
_URL_IN_BASH_RE = re.compile(
    r"https?://([A-Za-z0-9.\-_]+(?:\:\d+)?)[/\s\"']?", re.IGNORECASE
)


def events_to_fingerprint(events: Iterable[DriverEvent]) -> BehavioralFingerprint:
    """Reduce a stream of driver events into a ``BehavioralFingerprint``.

    Args:
        events: Iterable of driver events captured during sandbox replay.

    Returns:
        A normalized fingerprint with shape-level (not value-level) data.
    """
    tool_calls: list[str] = []
    egress_hosts: list[str] = []
    file_writes: list[str] = []
    hook_subprocess: list[str] = []
    input_tokens: list[int] = []
    output_tokens: list[int] = []

    for event in events:
        if event.kind == DriverEventKind.TOOL_CALL:
            name = event.tool_name or "unknown"
            tool_calls.append(f"{name}:{_arg_shape(event.tool_args)}")
            if name in _FETCH_TOOLS:
                host = _host_from_url(event.tool_args.get("url"))
                if host:
                    egress_hosts.append(host)
            if name in _WRITE_TOOLS:
                path = event.tool_args.get("file_path") or event.tool_args.get("path")
                if isinstance(path, str):
                    file_writes.append(_glob_of(path))
            if name in _BASH_TOOLS:
                cmd = event.tool_args.get("command")
                if isinstance(cmd, str):
                    hook_subprocess.append(_argv_signature(cmd))
                    egress_hosts.extend(_hosts_from_bash(cmd))
        elif event.kind == DriverEventKind.TOKEN_USAGE:
            if event.input_tokens:
                input_tokens.append(event.input_tokens)
            if event.output_tokens:
                output_tokens.append(event.output_tokens)

    return BehavioralFingerprint(
        tool_calls=tool_calls,
        egress_hosts=egress_hosts,
        file_writes=file_writes,
        hook_subprocess=hook_subprocess,
        token_profile=_profile(input_tokens, output_tokens),
    )


def _arg_shape(args: dict[str, object]) -> str:
    return ",".join(sorted(args.keys()))


def _host_from_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    return parsed.hostname


def _glob_of(path: str) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return path
    if "." in parts[-1]:
        ext = parts[-1].rsplit(".", 1)[1]
        return f"{'/'.join(parts[:-1])}/*.{ext}"
    return f"{'/'.join(parts[:-1])}/*"


def _argv_signature(cmd: str) -> str:
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return cmd.split()[0] if cmd else ""
    if not parts:
        return ""
    head = parts[0]
    flags = [p for p in parts[1:] if p.startswith("-")]
    return f"{head}:{':'.join(sorted(flags))}" if flags else head


def _hosts_from_bash(cmd: str) -> list[str]:
    return [m.group(1) for m in _URL_IN_BASH_RE.finditer(cmd)]


def _profile(inp: list[int], out: list[int]) -> dict[str, float]:
    if not inp and not out:
        return {}
    profile = {
        "input_count": float(len(inp)),
        "output_count": float(len(out)),
    }
    if inp:
        profile["input_mean"] = float(statistics.fmean(inp))
        profile["input_std"] = float(statistics.pstdev(inp)) if len(inp) > 1 else 0.0
    if out:
        profile["output_mean"] = float(statistics.fmean(out))
        profile["output_std"] = float(statistics.pstdev(out)) if len(out) > 1 else 0.0
    return profile
