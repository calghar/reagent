from importlib import resources
from pathlib import Path


def get_hooks_dir() -> Path:
    """Return the directory containing hook shell scripts.

    Returns:
        Path to the installed hooks package directory.
    """
    return Path(str(resources.files("reagent.hooks")))
