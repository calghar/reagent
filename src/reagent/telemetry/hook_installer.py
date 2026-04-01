import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from reagent.hooks import get_hooks_dir

logger = logging.getLogger(__name__)

# Marker used to identify Reagent-managed hooks
REAGENT_MARKER = "reagent:"

# Map of Claude Code events to Reagent hook scripts
HOOK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "SessionStart": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",  # filled at runtime with absolute path
                "async": True,
                "statusMessage": "reagent: logging session start",
            }
        ],
        "script": "log-session-start.sh",
    },
    "PostToolUse": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",
                "async": True,
                "statusMessage": "reagent: logging tool use",
            }
        ],
        "script": "log-tool-use.sh",
    },
    "Stop": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",
                "async": True,
                "statusMessage": "reagent: logging session end",
            }
        ],
        "script": "log-session-end.sh",
    },
    "SubagentStart": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",
                "async": True,
                "statusMessage": "reagent: logging agent event",
            }
        ],
        "script": "log-agent-event.sh",
    },
    "SubagentStop": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",
                "async": True,
                "statusMessage": "reagent: logging agent event",
            }
        ],
        "script": "log-agent-event.sh",
    },
    "ConfigChange": {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": "",
                "async": True,
                "statusMessage": "reagent: verifying asset integrity",
            }
        ],
        "script": "verify-integrity.sh",
    },
}


class HookStatus(BaseModel):
    """Status of a single hook event."""

    event: str
    installed: bool = False
    script_path: str = ""


class HooksReport(BaseModel):
    """Report on installed hooks."""

    settings_path: Path
    settings_exists: bool = False
    hooks: list[HookStatus] = Field(default_factory=list)

    @property
    def installed_count(self) -> int:
        """Number of Reagent hooks currently installed."""
        return sum(1 for h in self.hooks if h.installed)

    @property
    def total_count(self) -> int:
        """Total number of Reagent hook events tracked."""
        return len(self.hooks)


def _get_settings_path() -> Path:
    """Return path to ~/.claude/settings.json."""
    return Path.home() / ".claude" / "settings.json"


def _read_settings(path: Path) -> dict[str, Any]:
    """Read settings.json, returning empty dict if missing.

    Args:
        path: Path to the settings.json file.

    Returns:
        Parsed JSON as a dictionary, or empty dict if file is missing.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    result: dict[str, Any] = json.loads(text)
    return result


def _write_settings(path: Path, data: dict[str, Any]) -> None:
    """Write settings.json with pretty formatting.

    Args:
        path: Path to write the settings file.
        data: Dictionary to serialize as JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _is_reagent_hook(hook_entry: dict[str, Any]) -> bool:
    """Check if a hook entry was installed by Reagent.

    Args:
        hook_entry: A single hook configuration dict.

    Returns:
        True if the hook has a Reagent status message marker.
    """
    status = hook_entry.get("statusMessage", "")
    return isinstance(status, str) and status.startswith(REAGENT_MARKER)


def _build_hook_config(event_name: str, hooks_dir: Path) -> dict[str, Any]:
    """Build hook config dict for a given event.

    Args:
        event_name: Claude Code event name (e.g. "SessionStart").
        hooks_dir: Directory containing hook shell scripts.

    Returns:
        Hook configuration dict ready for settings.json.
    """
    defn = HOOK_DEFINITIONS[event_name]
    script_path = hooks_dir / defn["script"]
    config: dict[str, Any] = {
        "matcher": defn["matcher"],
        "hooks": [],
    }
    for hook_template in defn["hooks"]:
        hook = dict(hook_template)
        hook["command"] = f"bash {script_path}"
        config["hooks"].append(hook)
    return config


def install_hooks(settings_path: Path | None = None) -> HooksReport:
    """Install Reagent telemetry hooks into ~/.claude/settings.json.

    Merges Reagent hook entries alongside existing user hooks without
    overwriting them. Idempotent — safe to run multiple times.

    Args:
        settings_path: Override path for testing. Defaults to ~/.claude/settings.json.

    Returns:
        HooksReport with status of all hooks.
    """
    path = settings_path or _get_settings_path()
    data = _read_settings(path)
    hooks_dir = get_hooks_dir()

    if "hooks" not in data:
        data["hooks"] = {}

    for event_name in HOOK_DEFINITIONS:
        event_configs: list[dict[str, Any]] = data["hooks"].get(event_name, [])

        # Remove any existing Reagent hooks for this event (to update cleanly)
        cleaned: list[dict[str, Any]] = []
        for cfg in event_configs:
            # Keep configs that have at least one non-Reagent hook
            kept_hooks = [h for h in cfg.get("hooks", []) if not _is_reagent_hook(h)]
            if kept_hooks:
                cfg["hooks"] = kept_hooks
                cleaned.append(cfg)
            elif not any(_is_reagent_hook(h) for h in cfg.get("hooks", [])):
                cleaned.append(cfg)

        # Add Reagent hook config
        reagent_config = _build_hook_config(event_name, hooks_dir)
        cleaned.append(reagent_config)
        data["hooks"][event_name] = cleaned

    _write_settings(path, data)

    return status(settings_path=path)


def uninstall_hooks(settings_path: Path | None = None) -> HooksReport:
    """Remove all Reagent hook entries from ~/.claude/settings.json.

    Preserves user-defined hooks on the same events.

    Args:
        settings_path: Override path for testing. Defaults to ~/.claude/settings.json.

    Returns:
        HooksReport showing all hooks removed.
    """
    path = settings_path or _get_settings_path()
    data = _read_settings(path)

    hooks_section = data.get("hooks", {})
    for event_name in hooks_section.copy():
        event_configs: list[dict[str, Any]] = hooks_section[event_name]
        cleaned: list[dict[str, Any]] = []
        for cfg in event_configs:
            non_reagent = [h for h in cfg.get("hooks", []) if not _is_reagent_hook(h)]
            if non_reagent:
                cfg["hooks"] = non_reagent
                cleaned.append(cfg)
            elif not any(_is_reagent_hook(h) for h in cfg.get("hooks", [])):
                cleaned.append(cfg)
        if cleaned:
            hooks_section[event_name] = cleaned
        else:
            del hooks_section[event_name]

    _write_settings(path, data)

    return status(settings_path=path)


def status(settings_path: Path | None = None) -> HooksReport:
    """Report which Reagent hooks are installed.

    Args:
        settings_path: Override path for testing. Defaults to ~/.claude/settings.json.

    Returns:
        HooksReport with per-event status.
    """
    path = settings_path or _get_settings_path()
    hooks_dir = get_hooks_dir()
    report = HooksReport(settings_path=path, settings_exists=path.exists())

    data = _read_settings(path)
    hooks_section = data.get("hooks", {})

    for event_name, defn in HOOK_DEFINITIONS.items():
        script_path = str(hooks_dir / defn["script"])
        installed = False

        event_configs = hooks_section.get(event_name, [])
        for cfg in event_configs:
            for hook in cfg.get("hooks", []):
                if _is_reagent_hook(hook):
                    installed = True
                    break
            if installed:
                break

        report.hooks.append(
            HookStatus(event=event_name, installed=installed, script_path=script_path)
        )

    return report


PROMPT_HOOK_MARKER = "reagent-prompt:"

PROMPT_HOOK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "PreToolUse": {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
            {
                "type": "prompt",
                "prompt": "",  # filled at runtime from data file
                "statusMessage": "reagent-prompt: convention check",
            }
        ],
        "data_file": "convention-check.prompt",
    },
    "Stop": {
        "matcher": "*",
        "hooks": [
            {
                "type": "prompt",
                "prompt": "",
                "statusMessage": "reagent-prompt: session review",
            }
        ],
        "data_file": "review-summary.prompt",
    },
}


def _is_reagent_prompt_hook(hook_entry: dict[str, Any]) -> bool:
    """Check if a hook entry is a Reagent prompt hook.

    Args:
        hook_entry: A single hook configuration dict.

    Returns:
        True if the hook has a Reagent prompt marker.
    """
    status = hook_entry.get("statusMessage", "")
    return isinstance(status, str) and status.startswith(PROMPT_HOOK_MARKER)


def _get_data_hooks_dir() -> Path:
    """Return the directory containing hook data templates.

    Returns:
        Path to the data/hooks directory.
    """
    from importlib import resources

    return Path(str(resources.files("reagent.data.hooks")))


def install_prompt_hooks(settings_path: Path | None = None) -> HooksReport:
    """Install Reagent prompt hooks into ~/.claude/settings.json.

    Args:
        settings_path: Override path for testing.

    Returns:
        HooksReport with status.
    """
    path = settings_path or _get_settings_path()
    data = _read_settings(path)
    data_dir = _get_data_hooks_dir()

    if "hooks" not in data:
        data["hooks"] = {}

    for event_name, defn in PROMPT_HOOK_DEFINITIONS.items():
        event_configs: list[dict[str, Any]] = data["hooks"].get(event_name, [])

        # Remove existing reagent prompt hooks
        cleaned = _remove_reagent_prompt_hooks(event_configs)

        # Load prompt content
        prompt_file = data_dir / defn["data_file"]
        prompt_text = ""
        if prompt_file.exists():
            prompt_text = prompt_file.read_text(encoding="utf-8").strip()

        # Build config
        config: dict[str, Any] = {
            "matcher": defn["matcher"],
            "hooks": [],
        }
        for hook_template in defn["hooks"]:
            hook = dict(hook_template)
            hook["prompt"] = prompt_text
            config["hooks"].append(hook)
        cleaned.append(config)
        data["hooks"][event_name] = cleaned

    _write_settings(path, data)
    return status(settings_path=path)


def _remove_reagent_prompt_hooks(
    event_configs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove Reagent prompt hooks from a list of event configs.

    Args:
        event_configs: List of hook configs for one event.

    Returns:
        Cleaned list without Reagent prompt hooks.
    """
    cleaned: list[dict[str, Any]] = []
    for cfg in event_configs:
        kept = [h for h in cfg.get("hooks", []) if not _is_reagent_prompt_hook(h)]
        if kept:
            cfg["hooks"] = kept
            cleaned.append(cfg)
        elif not any(_is_reagent_prompt_hook(h) for h in cfg.get("hooks", [])):
            cleaned.append(cfg)
    return cleaned


AGENT_HOOK_MARKER = "reagent-agent:"

AGENT_HOOK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "Stop": {
        "matcher": "*",
        "hooks": [
            {
                "type": "agent",
                "agent": "session-evaluator",
                "statusMessage": "reagent-agent: session evaluation",
            }
        ],
    },
}


def _is_reagent_agent_hook(hook_entry: dict[str, Any]) -> bool:
    """Check if a hook entry is a Reagent agent hook.

    Args:
        hook_entry: A single hook configuration dict.

    Returns:
        True if the hook has a Reagent agent marker.
    """
    status = hook_entry.get("statusMessage", "")
    return isinstance(status, str) and status.startswith(AGENT_HOOK_MARKER)


def install_agent_hooks(settings_path: Path | None = None) -> HooksReport:
    """Install Reagent agent hooks and the session-evaluator agent.

    Args:
        settings_path: Override path for testing.

    Returns:
        HooksReport with status.
    """
    path = settings_path or _get_settings_path()
    data = _read_settings(path)

    if "hooks" not in data:
        data["hooks"] = {}

    for event_name, defn in AGENT_HOOK_DEFINITIONS.items():
        event_configs: list[dict[str, Any]] = data["hooks"].get(event_name, [])

        # Remove existing reagent agent hooks
        cleaned: list[dict[str, Any]] = []
        for cfg in event_configs:
            kept = [h for h in cfg.get("hooks", []) if not _is_reagent_agent_hook(h)]
            if kept:
                cfg["hooks"] = kept
                cleaned.append(cfg)
            elif not any(_is_reagent_agent_hook(h) for h in cfg.get("hooks", [])):
                cleaned.append(cfg)

        config: dict[str, Any] = {
            "matcher": defn["matcher"],
            "hooks": list(defn["hooks"]),
        }
        cleaned.append(config)
        data["hooks"][event_name] = cleaned

    _write_settings(path, data)

    # Install the session-evaluator agent
    _install_session_evaluator_agent()

    return status(settings_path=path)


def _install_session_evaluator_agent() -> Path:
    """Copy session-evaluator.md to ~/.claude/agents/.

    Returns:
        Path where the agent was installed.
    """
    data_dir = _get_data_hooks_dir()
    source = data_dir / "session-evaluator.md"
    target_dir = Path.home() / ".claude" / "agents"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "session-evaluator.md"

    if source.exists():
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target
