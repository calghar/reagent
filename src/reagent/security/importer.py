import hashlib
import logging
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from reagent.security.scanner import ScanReport, scan_directory
from reagent.security.trust import TrustLevel, TrustStore

logger = logging.getLogger(__name__)


class ImportSource(BaseModel):
    """Describes the source for an import operation."""

    raw: str
    source_type: str = "local"  # local, git, gist
    resolved_path: Path | None = None
    git_url: str = ""


class ImportResult(BaseModel):
    """Result of an import operation."""

    import_id: str
    source: str
    staging_path: Path
    scan_report: ScanReport = Field(default_factory=ScanReport)
    approved: bool = False
    installed: bool = False
    installed_path: Path | None = None
    error: str = ""


_GIT_URL_RE = re.compile(r"^(https?://|git@|ssh://)[^\s]+\.git$")
_GIST_URL_RE = re.compile(r"^https://gist\.github\.com/[^/]+/[a-f0-9]+$")


def resolve_source(source: str) -> ImportSource:
    """Determine the type and location of an import source.

    Args:
        source: A local path, git URL, or GitHub gist URL.

    Returns:
        ImportSource with type and resolved information.

    Raises:
        ValueError: If the source type cannot be determined.
    """
    # Check gist first (before generic git URL)
    if _GIST_URL_RE.match(source):
        return ImportSource(raw=source, source_type="gist", git_url=source)

    if _GIT_URL_RE.match(source):
        return ImportSource(raw=source, source_type="git", git_url=source)

    # Try as local path
    path = Path(source).expanduser().resolve()
    if path.exists():
        return ImportSource(raw=source, source_type="local", resolved_path=path)

    raise ValueError(f"Cannot resolve import source: {source}")


def fetch_to_staging(
    source: ImportSource,
    staging_root: Path | None = None,
) -> tuple[str, Path]:
    """Fetch source content into an isolated staging directory.

    Args:
        source: Resolved import source.
        staging_root: Root directory for staging. Defaults to ~/.reagent/staging/.

    Returns:
        Tuple of (import_id, staging_path).

    Raises:
        RuntimeError: If fetching fails.
    """
    if staging_root is None:
        staging_root = Path.home() / ".reagent" / "staging"

    import_id = uuid.uuid4().hex[:12]
    staging_path = staging_root / import_id
    staging_path.mkdir(parents=True, exist_ok=True)

    if source.source_type == "local":
        _copy_local(source, staging_path)
    elif source.source_type in ("git", "gist"):
        _clone_git(source, staging_path)
    else:
        raise RuntimeError(f"Unknown source type: {source.source_type}")

    return import_id, staging_path


def _copy_local(source: ImportSource, staging_path: Path) -> None:
    """Copy local files to staging."""
    src = source.resolved_path
    if src is None:
        raise RuntimeError("Local source has no resolved path")

    if src.is_file():
        shutil.copy2(src, staging_path / src.name)
    elif src.is_dir():
        # Copy directory contents
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                dest = staging_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
    else:
        raise RuntimeError(f"Source path does not exist: {src}")


def _clone_git(source: ImportSource, staging_path: Path) -> None:
    """Clone a git repository to staging."""
    url = source.git_url
    if not url:
        raise RuntimeError("Git source has no URL")

    # For gists, convert to .git URL if needed
    git_url = url
    if source.source_type == "gist" and not url.endswith(".git"):
        git_url = url + ".git"

    # Resolve absolute path to git executable (fixes S607)
    git_executable = shutil.which("git")
    if not git_executable:
        raise RuntimeError("git executable not found in PATH")

    result = subprocess.run(  # noqa: S603
        [git_executable, "clone", "--depth=1", git_url, str(staging_path / "repo")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")


def run_import(
    source_str: str,
    staging_root: Path | None = None,
) -> ImportResult:
    """Execute the full import pipeline (sans interactive approval).

    Steps:
        1. Resolve and fetch source to staging
        2. Run static security analysis
        3. Return result for user review

    The caller is responsible for presenting findings and getting approval
    before calling install_from_staging().

    Args:
        source_str: Import source (path, git URL, or gist URL).
        staging_root: Override staging directory root.

    Returns:
        ImportResult with staging path and scan report.
    """
    try:
        source = resolve_source(source_str)
    except ValueError as e:
        return ImportResult(
            import_id="",
            source=source_str,
            staging_path=Path(),
            error=str(e),
        )

    try:
        import_id, staging_path = fetch_to_staging(source, staging_root)
    except RuntimeError as e:
        return ImportResult(
            import_id="",
            source=source_str,
            staging_path=Path(),
            error=str(e),
        )

    # Static analysis
    scan_report = scan_directory(staging_path)

    result = ImportResult(
        import_id=import_id,
        source=source_str,
        staging_path=staging_path,
        scan_report=scan_report,
    )

    return result


def install_from_staging(
    result: ImportResult,
    target_repo: Path,
    trust_store: TrustStore | None = None,
) -> ImportResult:
    """Install approved content from staging to the target .claude/ directory.

    Args:
        result: Import result from run_import (must be approved).
        target_repo: Repository where assets should be installed.
        trust_store: Optional trust store to record trust metadata.

    Returns:
        Updated ImportResult with installation details.

    Raises:
        ValueError: If the import has not been approved.
    """
    if not result.approved:
        raise ValueError(
            "Cannot install unapproved import.\
            Set result.approved = True first."
        )

    staging = result.staging_path
    if not staging.exists():
        result.error = "Staging directory no longer exists"
        return result

    target_claude = target_repo / ".claude"

    # Copy all files from staging to .claude/
    installed_files: list[Path] = []
    for item in staging.rglob("*"):
        if item.is_file():
            rel = item.relative_to(staging)
            dest = target_claude / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            installed_files.append(dest)

    result.installed = True
    result.installed_path = target_claude

    # Record trust level for imported assets
    if trust_store and installed_files:
        for file_path in installed_files:
            content = file_path.read_text(encoding="utf-8")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            asset_id = f"imported:{result.import_id}:{file_path.name}"
            trust_store.set_level(asset_id, TrustLevel.REVIEWED, content_hash)

    return result


def cleanup_staging(staging_path: Path) -> None:
    """Remove a staging directory after import is complete or rejected.

    Args:
        staging_path: Path to the staging directory to remove.
    """
    if staging_path.exists() and staging_path.is_dir():
        shutil.rmtree(staging_path)
