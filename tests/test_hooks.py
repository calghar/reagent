import json
from pathlib import Path

import pytest

from reagent.telemetry.hook_installer import (
    REAGENT_MARKER,
    install_hooks,
    status,
    uninstall_hooks,
)


@pytest.fixture()
def settings_path(tmp_path: Path) -> Path:
    """Return a temporary settings.json path."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    return claude_dir / "settings.json"


class TestInstallHooks:
    def test_install_creates_settings_if_missing(self, settings_path: Path) -> None:
        assert not settings_path.exists()
        report = install_hooks(settings_path=settings_path)
        assert settings_path.exists()
        assert report.installed_count > 0

    def test_install_adds_hooks_section(self, settings_path: Path) -> None:
        install_hooks(settings_path=settings_path)
        data = json.loads(settings_path.read_text())
        assert "hooks" in data
        assert "SessionStart" in data["hooks"]
        assert "PostToolUse" in data["hooks"]
        assert "Stop" in data["hooks"]

    def test_install_preserves_existing_settings(self, settings_path: Path) -> None:
        # Write existing settings with permissions
        settings_path.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Read", "Write"]},
                    "hooks": {},
                }
            )
        )

        install_hooks(settings_path=settings_path)
        data = json.loads(settings_path.read_text())
        assert data["permissions"]["allow"] == ["Read", "Write"]

    def test_install_preserves_user_hooks(self, settings_path: Path) -> None:
        # Write existing settings with user hooks
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {"type": "command", "command": "echo safety check"}
                                ],
                            }
                        ]
                    }
                }
            )
        )

        install_hooks(settings_path=settings_path)
        data = json.loads(settings_path.read_text())

        # User hook on PreToolUse still exists
        pre_tool = data["hooks"]["PreToolUse"]
        assert len(pre_tool) == 1
        assert pre_tool[0]["hooks"][0]["command"] == "echo safety check"

        # Reagent hooks also installed
        assert "SessionStart" in data["hooks"]

    def test_install_is_idempotent(self, settings_path: Path) -> None:
        install_hooks(settings_path=settings_path)
        data1 = json.loads(settings_path.read_text())

        install_hooks(settings_path=settings_path)
        data2 = json.loads(settings_path.read_text())

        # Should not duplicate hooks
        for event in data1["hooks"]:
            reagent_hooks_1 = sum(
                1
                for cfg in data1["hooks"].get(event, [])
                for h in cfg.get("hooks", [])
                if h.get("statusMessage", "").startswith(REAGENT_MARKER)
            )
            reagent_hooks_2 = sum(
                1
                for cfg in data2["hooks"].get(event, [])
                for h in cfg.get("hooks", [])
                if h.get("statusMessage", "").startswith(REAGENT_MARKER)
            )
            assert reagent_hooks_1 == reagent_hooks_2

    def test_all_hooks_have_async_true(self, settings_path: Path) -> None:
        install_hooks(settings_path=settings_path)
        data = json.loads(settings_path.read_text())

        for event, configs in data["hooks"].items():
            for cfg in configs:
                for h in cfg.get("hooks", []):
                    if h.get("statusMessage", "").startswith(REAGENT_MARKER):
                        assert h.get("async") is True, f"Hook on {event} not async"


class TestUninstallHooks:
    def test_uninstall_removes_reagent_hooks(self, settings_path: Path) -> None:
        install_hooks(settings_path=settings_path)
        report = uninstall_hooks(settings_path=settings_path)
        assert report.installed_count == 0

        data = json.loads(settings_path.read_text())
        # No Reagent hooks remain
        for configs in data.get("hooks", {}).values():
            for cfg in configs:
                for h in cfg.get("hooks", []):
                    assert not h.get("statusMessage", "").startswith(REAGENT_MARKER)

    def test_uninstall_preserves_user_hooks(self, settings_path: Path) -> None:
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [{"type": "command", "command": "echo check"}],
                            }
                        ]
                    }
                }
            )
        )

        install_hooks(settings_path=settings_path)
        uninstall_hooks(settings_path=settings_path)

        data = json.loads(settings_path.read_text())
        assert "PreToolUse" in data["hooks"]
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo check"

    def test_uninstall_on_empty(self, settings_path: Path) -> None:
        settings_path.write_text("{}")
        report = uninstall_hooks(settings_path=settings_path)
        assert report.installed_count == 0


class TestStatus:
    def test_status_when_not_installed(self, settings_path: Path) -> None:
        settings_path.write_text("{}")
        report = status(settings_path=settings_path)
        assert report.settings_exists is True
        assert report.installed_count == 0
        assert report.total_count > 0

    def test_status_when_installed(self, settings_path: Path) -> None:
        install_hooks(settings_path=settings_path)
        report = status(settings_path=settings_path)
        assert report.installed_count == report.total_count

    def test_status_when_no_settings(self, settings_path: Path) -> None:
        report = status(settings_path=settings_path)
        assert report.settings_exists is False
        assert report.installed_count == 0
