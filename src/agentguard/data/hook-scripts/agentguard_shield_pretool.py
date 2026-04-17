#!/usr/bin/env python3
"""AgentGuard BATT shield — Claude Code PreToolUse hook.

Reads a PreToolUse hook event from stdin (JSON as emitted by Claude Code),
resolves the asset-in-scope's content hash from the session context, asks
``agentguard shield check`` whether the tool call is permitted under the
current trust tier, and either returns allow/deny on stdout.

Install by copying this script into ``.claude/hooks/pre-tool-use.py`` and
pointing Claude Code's settings at it, or use ``agentguard shield install``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def _asset_path_for_session(event: dict[str, object]) -> Path | None:
    candidate = event.get("agent_asset_path") or event.get("skill_path")
    if isinstance(candidate, str) and candidate:
        return Path(candidate)
    cwd = os.environ.get("CLAUDE_CWD") or str(Path.cwd())
    skill_id = event.get("skill_id")
    if isinstance(skill_id, str) and skill_id:
        guess = Path(cwd) / ".claude" / "skills" / skill_id / "SKILL.md"
        if guess.exists():
            return guess
    return None


def _emit(decision: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(decision))
    sys.stdout.flush()


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        _emit({"allow": True, "reason": "invalid-event"})
        return 0

    asset_path = _asset_path_for_session(event)
    tool_name = str(event.get("tool_name") or event.get("name") or "")
    tool_args = event.get("tool_input") or event.get("input") or {}
    if not isinstance(tool_args, dict):
        tool_args = {}

    if asset_path is None or not asset_path.exists():
        _emit({"allow": True, "reason": "no-asset-in-scope"})
        return 0

    from agentguard.shield.enforcer import ShieldEnforcer

    content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    decision = ShieldEnforcer().check(
        asset_content_hash=content_hash,
        tool_name=tool_name,
        tool_args=tool_args,
    )
    _emit(
        {
            "allow": decision.allowed,
            "reason": decision.reason,
            "tier": decision.tier.name.lower(),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
