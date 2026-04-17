import json
from pathlib import Path

import pytest

from agentguard.intelligence.schema_validator import (
    check_schemas,
    reset_schemas,
    schema_is_stale,
    show_schema,
    update_schemas,
    validate_asset_file,
    validate_frontmatter,
)


@pytest.fixture()
def schema_dir(tmp_path: Path) -> Path:
    """Create a temporary schema directory with bundled defaults."""
    d = tmp_path / "schemas" / "claude-code"
    reset_schemas(d)
    return d


# --- validate_frontmatter ---


class TestValidateFrontmatter:
    @pytest.mark.parametrize(
        ("fm", "asset_type", "name"),
        [
            pytest.param(
                {"name": "code-reviewer", "description": "Reviews code"},
                "agent",
                "code-reviewer",
                id="valid_agent",
            ),
            pytest.param(
                {
                    "name": "deploy",
                    "description": "Deploy the app",
                    "allowed-tools": ["Read", "Bash"],
                    "user-invocable": True,
                },
                "skill",
                "deploy",
                id="valid_skill",
            ),
        ],
    )
    def test_valid_frontmatter(
        self,
        schema_dir: Path,
        fm: dict[str, object],
        asset_type: str,
        name: str,
    ) -> None:
        result = validate_frontmatter(fm, asset_type, name, "", schema_dir)
        assert result.valid
        assert result.errors == []

    def test_missing_required_field(self, schema_dir: Path) -> None:
        fm = {"name": "test"}  # missing description
        result = validate_frontmatter(fm, "agent", "test", "", schema_dir)
        assert not result.valid
        assert any("description" in e.message for e in result.errors)

    def test_invalid_enum_value(self, schema_dir: Path) -> None:
        fm = {
            "name": "test-agent",
            "description": "Test",
            "permissionMode": "yolo",
        }
        result = validate_frontmatter(fm, "agent", "test-agent", "", schema_dir)
        assert not result.valid
        assert any("yolo" in e.message for e in result.errors)

    def test_unknown_field_is_warning(self, schema_dir: Path) -> None:
        fm = {
            "name": "test-agent",
            "description": "Test",
            "newFeature": True,
        }
        result = validate_frontmatter(fm, "agent", "test-agent", "", schema_dir)
        assert result.valid  # warnings don't block
        assert len(result.warnings) == 1
        assert "newFeature" in result.warnings[0].message

    def test_typo_suggestion_allowed_tools(self, schema_dir: Path) -> None:
        fm = {
            "name": "test-agent",
            "description": "Test",
            "allowedTools": ["Read"],
        }
        result = validate_frontmatter(fm, "agent", "test-agent", "", schema_dir)
        assert result.valid  # unknown field = warning
        assert any("tools" in w.fix for w in result.warnings)

    def test_type_mismatch(self, schema_dir: Path) -> None:
        fm = {
            "name": "test-agent",
            "description": "Test",
            "maxTurns": "ten",
        }
        result = validate_frontmatter(fm, "agent", "test-agent", "", schema_dir)
        assert not result.valid
        assert any("integer" in e.message.lower() for e in result.errors)

    def test_skill_typo_suggestion(self, schema_dir: Path) -> None:
        fm = {
            "name": "deploy",
            "description": "Deploy",
            "allowedTools": ["Read"],
        }
        result = validate_frontmatter(fm, "skill", "deploy", "", schema_dir)
        assert any("allowed-tools" in w.fix for w in result.warnings)

    def test_unknown_asset_type(self, schema_dir: Path) -> None:
        result = validate_frontmatter({}, "command", "test", "", schema_dir)
        assert result.valid  # no schema for commands, so no errors

    def test_missing_schema_file(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        fm = {"name": "test", "description": "Test"}
        result = validate_frontmatter(fm, "agent", "test", "", empty_dir)
        assert not result.valid
        assert any("missing" in e.message.lower() for e in result.errors)


# --- validate_asset_file ---


class TestValidateAssetFile:
    def test_agent_file(self, tmp_path: Path, schema_dir: Path) -> None:
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        agent_file = agents_dir / "review.md"
        agent_file.write_text(
            "---\nname: review\ndescription: Code review agent\n---\nReview code.\n"
        )
        result = validate_asset_file(agent_file, schema_dir)
        assert result.valid

    def test_skill_file(self, tmp_path: Path, schema_dir: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "deploy"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\nname: deploy\ndescription: Deploy\n---\nDeploy steps.\n"
        )
        result = validate_asset_file(skill_file, schema_dir)
        assert result.valid

    def test_hooks_file_valid(self, tmp_path: Path, schema_dir: Path) -> None:
        hooks_file = tmp_path / "hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {"PreToolUse": []}}))
        result = validate_asset_file(hooks_file, schema_dir)
        assert result.valid

    def test_hooks_file_unknown_event(
        self,
        tmp_path: Path,
        schema_dir: Path,
    ) -> None:
        hooks_file = tmp_path / "hooks.json"
        hooks_file.write_text(json.dumps({"hooks": {"InvalidEvent": []}}))
        result = validate_asset_file(hooks_file, schema_dir)
        assert len(result.warnings) == 1
        assert "InvalidEvent" in result.warnings[0].message

    def test_nonexistent_file(self, tmp_path: Path, schema_dir: Path) -> None:
        result = validate_asset_file(tmp_path / "no-such-file.md", schema_dir)
        assert not result.valid


# --- Schema lifecycle ---


class TestSchemaLifecycle:
    def test_reset_creates_schemas(self, tmp_path: Path) -> None:
        d = tmp_path / "schemas" / "claude-code"
        reset_schemas(d)
        assert (d / "agent.json").exists()
        assert (d / "skill-extensions.json").exists()
        assert (d / "hook-handler.json").exists()
        assert (d / "hook-events.json").exists()
        assert (d / "meta.json").exists()

    def test_show_schema_agent(self, schema_dir: Path) -> None:
        schema = show_schema("agent", schema_dir)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "description" in schema["properties"]

    def test_check_schemas_no_diff(self, schema_dir: Path) -> None:
        diff = check_schemas(schema_dir)
        assert not diff.has_changes

    def test_check_schemas_detects_removal(self, schema_dir: Path) -> None:
        # Add a custom field to local schema
        agent_path = schema_dir / "agent.json"
        schema = json.loads(agent_path.read_text())
        schema["properties"]["customField"] = {"type": "string"}
        agent_path.write_text(json.dumps(schema, indent=2))

        diff = check_schemas(schema_dir)
        assert diff.has_changes
        assert "customField" in diff.removed_fields.get("agent.json", [])

    def test_update_schemas(self, schema_dir: Path) -> None:
        # Modify a schema
        agent_path = schema_dir / "agent.json"
        schema = json.loads(agent_path.read_text())
        schema["properties"]["customField"] = {"type": "string"}
        agent_path.write_text(json.dumps(schema, indent=2))

        diff = update_schemas(schema_dir)
        assert diff.has_changes

        # After update, check should show no diff
        diff2 = check_schemas(schema_dir)
        assert not diff2.has_changes

    def test_schema_is_stale_fresh(self, schema_dir: Path) -> None:
        assert not schema_is_stale(schema_dir)

    def test_schema_is_stale_old(self, schema_dir: Path) -> None:
        meta_path = schema_dir / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["last_fetched"] = "2020-01-01T00:00:00Z"
        meta_path.write_text(json.dumps(meta))
        assert schema_is_stale(schema_dir)

    def test_schema_reset_recovers_corrupt(self, schema_dir: Path) -> None:
        # Corrupt a schema file
        (schema_dir / "agent.json").write_text("not json")

        # Validate should fail
        fm = {"name": "test", "description": "Test"}
        result = validate_frontmatter(fm, "agent", "test", "", schema_dir)
        assert not result.valid

        # Reset should recover
        reset_schemas(schema_dir)
        result = validate_frontmatter(fm, "agent", "test", "", schema_dir)
        assert result.valid
