"""MkDocs hook: copy root-level docs into docs/ and patch links for MkDocs."""

import shutil
from pathlib import Path
from typing import Any

# Root markdown files to include in the site
_ROOT_DOCS = {
    "README.md": "index.md",
    "ARCHITECTURE.md": "architecture.md",
    "CONTRIBUTING.md": "contributing.md",
    "SECURITY.md": "security.md",
    "CHANGELOG.md": "changelog.md",
}

# Link rewrites for index.md (README.md used as landing page)
_INDEX_LINK_REWRITES = {
    "ARCHITECTURE.md": "architecture.md",
    "CONTRIBUTING.md": "contributing.md",
    "SECURITY.md": "security.md",
    "CHANGELOG.md": "changelog.md",
    "docs/getting-started.md": "getting-started.md",
    "docs/cli-reference.md": "cli-reference.md",
    "docs/configuration.md": "configuration.md",
    "docs/security-scanning.md": "security-scanning.md",
    "docs/asset-creation.md": "asset-creation.md",
    "docs/evaluation.md": "evaluation.md",
    "docs/ci-integration.md": "ci-integration.md",
    "docs/dashboard.md": "dashboard.md",
    "docs/comparison.md": "comparison.md",
}


def on_pre_build(config: dict[str, Any]) -> None:
    """Copy root markdown files into docs/ before build."""
    root = Path(config["config_file_path"]).parent
    docs_dir = Path(config["docs_dir"])

    copied: set[str] = set()
    for src_name, dest_name in _ROOT_DOCS.items():
        src = root / src_name
        dest = docs_dir / dest_name
        if src.exists() and src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
            copied.add(src_name)

    # Patch links in the copied index.md so they resolve within MkDocs
    index = docs_dir / "index.md"
    if index.exists() and "README.md" in copied:
        content = index.read_text(encoding="utf-8")
        for old, new in _INDEX_LINK_REWRITES.items():
            content = content.replace(f"]({old})", f"]({new})")
        index.write_text(content, encoding="utf-8")


def on_post_build(config: dict[str, Any]) -> None:
    """Clean up copied files after build."""
    docs_dir = Path(config["docs_dir"])
    for dest_name in _ROOT_DOCS.values():
        copied = docs_dir / dest_name
        if copied.exists():
            copied.unlink()
