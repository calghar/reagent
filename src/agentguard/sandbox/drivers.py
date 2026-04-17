import enum
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DriverEventKind(enum.StrEnum):
    TOOL_CALL = "tool_call"
    TOKEN_USAGE = "token_usage"  # noqa: S105


class DriverEvent(BaseModel):
    kind: DriverEventKind
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


class HarnessDriver(Protocol):
    """Driver that runs a single probe against an installed asset.

    Implementations must be side-effect free with respect to the user's
    real `.claude/` directory; all state should be confined to ``workdir``.
    """

    def run_probe(
        self,
        asset_path: Path,
        workdir: Path,
        probe: str,
        timeout: int,
    ) -> list[DriverEvent]: ...


class MockDriver:
    """Driver that returns scripted events per probe prompt.

    Used in unit tests to exercise the engine and capture pipeline without
    spawning a real agent runtime.
    """

    def __init__(self, scripted: dict[str, list[DriverEvent]]) -> None:
        self._scripted = scripted

    def run_probe(
        self,
        asset_path: Path,
        workdir: Path,
        probe: str,
        timeout: int,
    ) -> list[DriverEvent]:
        return list(self._scripted.get(probe, []))


class ClaudeCodeDriver:
    """Driver that invokes the real ``claude`` CLI in a mediated subprocess.

    Spawns ``claude --print --output-format stream-json`` with an isolated
    HOME and cwd, installs the asset under ``workdir/.claude/``, and parses
    the stream-json output into ``DriverEvent`` instances.

    Requires ``ANTHROPIC_API_KEY`` in the environment and the ``claude``
    binary on ``PATH``. Construction validates neither — failures surface
    at ``run_probe`` time.
    """

    def __init__(
        self,
        claude_binary: str = "claude",
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._binary = claude_binary
        self._extra_env = extra_env or {}

    def run_probe(
        self,
        asset_path: Path,
        workdir: Path,
        probe: str,
        timeout: int,
    ) -> list[DriverEvent]:
        claude_dir = workdir / ".claude"
        self._install_asset(asset_path, claude_dir)

        env = self._build_env(workdir)
        args = [
            self._binary,
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            probe,
        ]
        logger.debug("Spawning claude probe: %s", args)
        try:
            completed = subprocess.run(  # noqa: S603
                args,
                cwd=str(workdir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("claude probe timed out after %ss: %s", timeout, exc)
            return []
        except FileNotFoundError:
            logger.error("claude binary not found on PATH; set --binary or install it")
            raise

        if completed.returncode != 0:
            logger.info(
                "claude exited %d; stderr=%s", completed.returncode, completed.stderr
            )
        return list(_parse_stream_json(completed.stdout))

    @staticmethod
    def _install_asset(asset_path: Path, claude_dir: Path) -> None:
        subdir = _subdir_for_asset(asset_path)
        target_dir = claude_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_path, target_dir / asset_path.name)

    def _build_env(self, workdir: Path) -> dict[str, str]:
        env = {
            "HOME": str(workdir),
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        if api_key := os.environ.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = api_key
        env.update(self._extra_env)
        return env


def _subdir_for_asset(asset_path: Path) -> str:
    parents = {p.name for p in asset_path.parents}
    if "skills" in parents or asset_path.stem.lower() in {"skill"}:
        return "skills"
    if "agents" in parents:
        return "agents"
    if "commands" in parents:
        return "commands"
    return "skills"


def _parse_stream_json(stdout: str) -> Iterable[DriverEvent]:
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield from _record_to_events(record)


def _record_to_events(record: dict[str, Any]) -> Iterable[DriverEvent]:
    rtype = record.get("type")
    if rtype == "assistant":
        message = record.get("message", {})
        for block in message.get("content", []) or []:
            if block.get("type") == "tool_use":
                yield DriverEvent(
                    kind=DriverEventKind.TOOL_CALL,
                    tool_name=str(block.get("name", "")),
                    tool_args=dict(block.get("input") or {}),
                )
        usage = message.get("usage") or {}
        if usage:
            yield DriverEvent(
                kind=DriverEventKind.TOKEN_USAGE,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
    elif rtype == "result":
        usage = record.get("usage") or {}
        if usage:
            yield DriverEvent(
                kind=DriverEventKind.TOKEN_USAGE,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            )
