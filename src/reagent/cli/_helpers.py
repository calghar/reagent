import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from reagent.config import ReagentConfig
from reagent.core.catalog import Catalog

logger = logging.getLogger(__name__)


def _configure_logging(
    verbose: bool,
    log_file: Path | None,
    config: ReagentConfig | None = None,
) -> None:
    """Configure root logger for the CLI session.

    Args:
        verbose: Enable DEBUG-level output to stderr.
        log_file: Explicit log file path override.
        config: Loaded config for defaults.
    """
    root = logging.getLogger("reagent")
    fmt = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    level = logging.DEBUG if verbose else logging.WARNING
    root.setLevel(level)

    if verbose:
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(fmt)
        root.addHandler(stderr_handler)

    file_path = log_file
    if file_path is None and config is not None:
        file_path = config.log.file
    if file_path is not None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = config.log.max_bytes if config else 5_000_000
        backup_count = config.log.backup_count if config else 3
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)


def _load_config() -> ReagentConfig:
    """Load the Reagent configuration from the default path.

    Returns:
        Loaded configuration with defaults for missing values.
    """
    return ReagentConfig.load()


def _load_catalog(config: ReagentConfig) -> Catalog:
    """Load the asset catalog from disk.

    Args:
        config: Reagent configuration containing catalog path.

    Returns:
        Loaded catalog instance.
    """
    catalog = Catalog(config.catalog.path)
    catalog.load()
    return catalog
