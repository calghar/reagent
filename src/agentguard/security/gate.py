import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from agentguard._tuning import score_to_grade as _score_to_grade
from agentguard.llm.parser import GeneratedAsset

logger = logging.getLogger(__name__)

# Per-severity score deductions applied in the built-in scanner
_SEVERITY_DEDUCTIONS: dict[str, float] = {
    "critical": 15.0,
    "high": 8.0,
    "medium": 3.0,
}


class SecurityIssue(BaseModel):
    """A single security issue surfaced by the gate."""

    rule_id: str
    severity: str  # "critical", "high", "medium", "low"
    message: str
    line: int = 0
    auto_fixable: bool = False


class SecurityResult(BaseModel):
    """Overall security assessment from the gate."""

    grade: str  # "A", "B", "C", "D", "F"
    score: float  # 0.0-100.0
    issues: list[SecurityIssue] = Field(default_factory=list)
    scanner: str = "builtin"  # "agentshield" or "builtin"

    @property
    def passed(self) -> bool:
        """Returns True if grade is A, B, or C."""
        return self.grade in ("A", "B", "C")


def _asset_to_text(asset: GeneratedAsset) -> str:
    """Convert a GeneratedAsset to a text representation for scanning.

    Args:
        asset: The asset to serialise.

    Returns:
        YAML-frontmatter + body string.
    """
    if not asset.frontmatter:
        return asset.body

    fm_text = yaml.dump(
        asset.frontmatter,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{fm_text}\n---\n{asset.body}"


def _builtin_scan(asset: GeneratedAsset) -> SecurityResult:
    """Run the built-in scanner on a GeneratedAsset.

    Deductions: CRITICAL=15, HIGH=8, MEDIUM=3.  Score is clamped at 0.

    Args:
        asset: The generated asset to scan.

    Returns:
        SecurityResult produced by the built-in scanner.
    """
    from agentguard.security.scanner import scan_content

    content = _asset_to_text(asset)
    virtual_path = Path(f"<generated>/{asset.asset_type.value}.md")
    findings = scan_content(content, virtual_path)

    score = 100.0
    issues: list[SecurityIssue] = []

    for finding in findings:
        severity_str = finding.severity.value
        score -= _SEVERITY_DEDUCTIONS.get(severity_str, 0.0)
        issues.append(
            SecurityIssue(
                rule_id=finding.rule_id,
                severity=severity_str,
                message=finding.description,
                line=finding.line_number,
                auto_fixable=False,
            )
        )

    score = max(0.0, score)
    return SecurityResult(
        grade=_score_to_grade(score),
        score=score,
        issues=issues,
        scanner="builtin",
    )


class SecurityGate:
    """Post-generation security validation gate.

    Tries AgentShield first; falls back to the built-in scanner when
    AgentShield is not installed or fails.
    """

    async def check(self, asset: GeneratedAsset, repo_path: Path) -> SecurityResult:
        """Run security validation on a generated asset.

        Workflow:
        1. Write asset to a temp file under ``repo_path/.agentguard_tmp_scan/``.
        2. Try AgentShield scan on that file.
        3. If AgentShield is unavailable or fails, run the built-in scanner.
        4. Clean up the temp file.

        Args:
            asset: The generated asset to validate.
            repo_path: Repository root used to create the temp scan directory.

        Returns:
            SecurityResult with grade, score, and individual issues.
        """
        scan_dir = repo_path / ".agentguard_tmp_scan"
        scan_dir.mkdir(parents=True, exist_ok=True)

        asset_name = str(asset.frontmatter.get("name", "asset")).replace("/", "_")
        tmp_file = scan_dir / f"{asset_name}_{asset.asset_type.value}.md"

        try:
            content = _asset_to_text(asset)
            tmp_file.write_text(content, encoding="utf-8")
            return await self._run_scan(asset, tmp_file)
        finally:
            _cleanup_tmp(tmp_file, scan_dir)

    async def _run_scan(self, asset: GeneratedAsset, tmp_file: Path) -> SecurityResult:
        """Attempt AgentShield, fall back to built-in.

        Args:
            asset: Asset for built-in fallback.
            tmp_file: Path to the written temp file for AgentShield.

        Returns:
            SecurityResult from whichever scanner ran.
        """
        try:
            from agentguard.security.agentshield import run_agentshield_scan

            result = await run_agentshield_scan(tmp_file)
            if result is not None:
                return result
        except ImportError:
            logger.debug("AgentShield module not available, using built-in scanner")

        return _builtin_scan(asset)


def _cleanup_tmp(tmp_file: Path, scan_dir: Path) -> None:
    """Remove a temp scan file and its directory if empty.

    Args:
        tmp_file: Temp file to remove.
        scan_dir: Directory to remove if empty.
    """
    if tmp_file.exists():
        tmp_file.unlink()
    try:
        scan_dir.rmdir()
    except OSError:
        pass  # Directory not empty — leave it
