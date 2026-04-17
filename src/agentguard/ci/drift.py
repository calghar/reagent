import logging
import re
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FILE_REF_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"`\./([^`]+)`"),
    re.compile(r"\b(\w[\w./]*\.(py|ts|js|go|rs|sh))\b"),
]


class DriftReport(BaseModel):
    """A single drift finding for one asset."""

    asset_path: str
    asset_type: str
    drift_type: str
    details: str
    severity: str


def _extract_file_refs(content: str) -> list[str]:
    """Extract file-path references from markdown content."""
    refs: set[str] = set()
    for pattern in _FILE_REF_PATTERNS:
        for match in pattern.finditer(content):
            refs.add(match.group(1))
    return list(refs)


def _infer_asset_type_from_path(asset_path: Path) -> str:
    """Infer a human-readable asset type from its filesystem location."""
    for part in asset_path.parts:
        if part in ("agents", "skills", "commands", "rules"):
            return part.rstrip("s")
    return "asset"


def _check_stale_asset(asset_path: Path, repo_path: Path) -> list[DriftReport]:
    """Check a single asset for stale file references."""
    try:
        content = asset_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read asset %s: %s", asset_path, exc)
        return []

    reports: list[DriftReport] = []
    asset_type = _infer_asset_type_from_path(asset_path)
    for ref in _extract_file_refs(content):
        candidate = repo_path / ref
        if not candidate.exists():
            reports.append(
                DriftReport(
                    asset_path=str(asset_path),
                    asset_type=asset_type,
                    drift_type="stale",
                    details=f"references removed file ./{ref}",
                    severity="warning",
                )
            )
    return reports


class DriftDetector:
    """Detect stale file references in agentguard-managed assets."""

    def detect(self, repo_path: Path) -> list[DriftReport]:
        """Run stale-reference checks and return combined findings."""
        claude_dir = repo_path / ".claude"
        if not claude_dir.exists():
            return []

        reports: list[DriftReport] = []
        for md_file in claude_dir.rglob("*.md"):
            reports.extend(_check_stale_asset(md_file, repo_path))
        return reports
