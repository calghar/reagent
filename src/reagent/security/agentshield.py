import asyncio
import json
import logging
import shutil
from pathlib import Path

from reagent.security.gate import SecurityIssue, SecurityResult

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30


def is_available() -> bool:
    """Check whether ``npx`` is present on the system PATH.

    Does NOT actually invoke agentshield (too slow for import time).

    Returns:
        True if ``npx`` is found on PATH.
    """
    return shutil.which("npx") is not None


async def run_agentshield_scan(file_path: Path) -> SecurityResult | None:
    """Run an agentshield scan on a single file.

    Args:
        file_path: Absolute path to the file to scan.

    Returns:
        Parsed SecurityResult on success, ``None`` if unavailable or failed.
    """
    if not is_available():
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "agentshield",
            "scan",
            "--format",
            "json",
            str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_TIMEOUT_SECONDS
        )
        if proc.returncode != 0:
            logger.debug("agentshield scan failed: %s", stderr.decode())
            return None
        return _parse_agentshield_output(stdout.decode())
    except (TimeoutError, FileNotFoundError, OSError):
        logger.debug("agentshield not available or timed out")
        return None


def _parse_agentshield_output(output: str) -> SecurityResult | None:
    """Parse the JSON emitted by ``agentshield scan --format json``.

    Expected shape::

        {
            "grade": "A",
            "score": 95,
            "issues": [
                {"ruleId": "AS-001", "severity": "high",
                 "message": "...", "line": 5}
            ]
        }

    Args:
        output: Raw JSON string from the agentshield subprocess.

    Returns:
        SecurityResult on success, ``None`` on any parse error.
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        logger.debug("Failed to parse agentshield output: %r", output[:200])
        return None

    if not isinstance(data, dict):
        return None

    grade = str(data.get("grade", "F"))
    score = float(data.get("score", 0.0))
    raw_issues = data.get("issues", [])

    issues: list[SecurityIssue] = []
    if isinstance(raw_issues, list):
        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
            issues.append(
                SecurityIssue(
                    rule_id=str(issue.get("ruleId", "AS-UNKNOWN")),
                    severity=str(issue.get("severity", "medium")),
                    message=str(issue.get("message", "")),
                    line=int(issue.get("line", 0)),
                    auto_fixable=bool(issue.get("autoFixable", False)),
                )
            )

    return SecurityResult(
        grade=grade,
        score=score,
        issues=issues,
        scanner="agentshield",
    )
