import logging

from reagent._tuning import score_to_grade as _score_to_grade

logger = logging.getLogger(__name__)

_PASS_MARK = "\u2713"  # noqa: S105  # nosec B105
_FAIL_MARK = "\u2717"
_WARN_MARK = "\u26a0"
_RULER = "\u2501" * 30


def _asset_row_text(ar: dict[str, object], threshold: float) -> str:
    """Format one asset result as a plain-text line.

    Args:
        ar: Asset result dict (name, type, score, grade, passed).
        threshold: Quality threshold for the pass/fail label.

    Returns:
        Formatted text line.
    """
    name = str(ar.get("name", ""))
    atype = str(ar.get("type", ""))
    score = float(ar.get("score", 0.0))  # type: ignore[arg-type]
    passed = bool(ar.get("passed", True))
    mark = _PASS_MARK if passed else _FAIL_MARK
    label = f"  {_FAIL_MARK} below threshold ({threshold:.0f})" if not passed else ""
    suffix = f"{score:.0f}/100{label}"
    padding = " " * max(1, 30 - len(name) - len(atype))
    return f"  {mark} {name} ({atype}){padding}{suffix}"


def _drift_lines_text(drift_reports: list[dict[str, object]]) -> list[str]:
    """Format drift reports as plain-text lines.

    Args:
        drift_reports: Serialised DriftReport dicts.

    Returns:
        List of formatted text lines (empty if no reports).
    """
    if not drift_reports:
        return []
    lines = ["\nDrift:"]
    for dr in drift_reports:
        path = str(dr.get("asset_path", ""))
        details = str(dr.get("details", ""))
        lines.append(f"  {_WARN_MARK} {path}: {details}")
    return lines


def _suggestions_lines_text(suggestions: list[str]) -> list[str]:
    """Format suggestions as plain-text lines.

    Args:
        suggestions: List of suggestion strings.

    Returns:
        List of formatted text lines (empty if no suggestions).
    """
    if not suggestions:
        return []
    lines = ["\nSuggestions:"]
    for s in suggestions:
        lines.append(f"  - {s}")
    return lines


def _asset_row_md(ar: dict[str, object]) -> str:
    """Format one asset result as a Markdown table row.

    Args:
        ar: Asset result dict.

    Returns:
        Markdown table row string.
    """
    name = str(ar.get("name", ""))
    atype = str(ar.get("type", ""))
    score = float(ar.get("score", 0.0))  # type: ignore[arg-type]
    grade = str(ar.get("grade", _score_to_grade(score)))
    passed = bool(ar.get("passed", True))
    status = "\u2705" if passed else "\u26a0\ufe0f"
    return f"| {name} | {atype} | {score:.0f} | {grade} | {status} |"


def _drift_section_md(drift_reports: list[dict[str, object]]) -> str:
    """Format drift reports as a Markdown section.

    Args:
        drift_reports: Serialised DriftReport dicts.

    Returns:
        Markdown section string, or empty string if no reports.
    """
    if not drift_reports:
        return ""
    lines = ["\n### Drift Detected"]
    for dr in drift_reports:
        path = str(dr.get("asset_path", ""))
        details = str(dr.get("details", ""))
        lines.append(f"- `{path}`: {details}")
    return "\n".join(lines)


def _suggestions_section_md(suggestions: list[str]) -> str:
    """Format suggestions as a Markdown section.

    Args:
        suggestions: List of suggestion strings.

    Returns:
        Markdown section string, or empty string if no suggestions.
    """
    if not suggestions:
        return ""
    lines = ["\n### Suggestions"]
    for s in suggestions:
        lines.append(f"- {s}")
    return "\n".join(lines)


class CIReporter:
    """Format CIResult objects for different output targets."""

    def format_check_output(self, result: object) -> str:
        """Produce a terminal-friendly plain-text report.

        Args:
            result: CIResult instance.

        Returns:
            Multi-line string suitable for stdout.
        """
        overall_score: float = getattr(result, "overall_score", 0.0)
        security_grade: str = getattr(result, "security_grade", "A")
        asset_results: list[dict[str, object]] = getattr(result, "asset_results", [])
        drift_reports: list[dict[str, object]] = getattr(result, "drift_reports", [])
        suggestions: list[str] = getattr(result, "suggestions", [])
        threshold: float = 60.0  # displayed threshold label

        grade = _score_to_grade(overall_score)
        lines: list[str] = [
            "Reagent Asset Quality Check",
            _RULER,
            f"Overall Score: {overall_score:.0f}/100 ({grade})",
            f"Security Grade: {security_grade}",
        ]

        if asset_results:
            lines.append("\nAssets:")
            for ar in asset_results:
                lines.append(_asset_row_text(ar, threshold))

        lines.extend(_drift_lines_text(drift_reports))
        lines.extend(_suggestions_lines_text(suggestions))

        fixes_applied: list[str] = getattr(result, "fixes_applied", [])
        if fixes_applied:
            lines.append("\nAuto-fix applied to:")
            for f in fixes_applied:
                lines.append(f"  - {f}")

        diff: str = getattr(result, "diff", "")
        if diff:
            lines.append("\nDiff:")
            lines.append(diff)

        return "\n".join(lines)

    def format_pr_comment(self, result: object) -> str:
        """Produce a GitHub-flavoured Markdown PR comment.

        Args:
            result: CIResult instance.

        Returns:
            Markdown string suitable for a GitHub PR comment.
        """
        overall_score: float = getattr(result, "overall_score", 0.0)
        security_grade: str = getattr(result, "security_grade", "A")
        asset_results: list[dict[str, object]] = getattr(result, "asset_results", [])
        drift_reports: list[dict[str, object]] = getattr(result, "drift_reports", [])
        suggestions: list[str] = getattr(result, "suggestions", [])

        grade = _score_to_grade(overall_score)
        lines: list[str] = [
            "## \U0001f50d Reagent Asset Quality Report",
            "",
            f"**Overall Score:** {overall_score:.0f}/100 ({grade})"
            f" | **Security:** {security_grade}",
        ]

        if asset_results:
            lines.extend(
                [
                    "",
                    "| Asset | Type | Score | Grade | Status |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for ar in asset_results:
                lines.append(_asset_row_md(ar))

        drift_md = _drift_section_md(drift_reports)
        if drift_md:
            lines.append(drift_md)

        suggestions_md = _suggestions_section_md(suggestions)
        if suggestions_md:
            lines.append(suggestions_md)

        return "\n".join(lines)

    def format_github_annotations(self, result: object) -> list[dict[str, str]]:
        """Produce GitHub Actions annotation objects for failing assets.

        Args:
            result: CIResult instance.

        Returns:
            List of annotation dicts with level, message, and file keys.
        """
        asset_results: list[dict[str, object]] = getattr(result, "asset_results", [])
        annotations: list[dict[str, str]] = []

        for ar in asset_results:
            if bool(ar.get("passed", True)):
                continue
            name = str(ar.get("name", ""))
            atype = str(ar.get("type", ""))
            score = float(ar.get("score", 0.0))  # type: ignore[arg-type]
            asset_file = _resolve_annotation_file(ar)
            msg = f"{name} ({atype}) score {score:.0f}/100 below threshold"
            annotations.append(
                {
                    "level": "error",
                    "message": msg,
                    "file": asset_file,
                }
            )

        return annotations


def _resolve_annotation_file(ar: dict[str, object]) -> str:
    """Resolve the file path for a GitHub annotation.

    Falls back to a generic path when no explicit path is stored.

    Args:
        ar: Asset result dict.

    Returns:
        File path string for the annotation.
    """
    explicit = ar.get("file") or ar.get("asset_path")
    if isinstance(explicit, str) and explicit:
        return explicit
    name = str(ar.get("name", "unknown"))
    atype = str(ar.get("type", "asset"))
    return f".claude/{atype}s/{name}.md"
