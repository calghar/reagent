from pathlib import Path

from agentguard.core.parsers import (
    AssetType,
    compute_content_hash,
    parse_agent,
    parse_claude_md,
    parse_command,
    parse_hooks,
    parse_rule,
    parse_settings,
    parse_skill,
)


class TestComputeContentHash:
    def test_deterministic(self) -> None:
        assert compute_content_hash("hello") == compute_content_hash("hello")

    def test_different_content(self) -> None:
        assert compute_content_hash("hello") != compute_content_hash("world")

    def test_sha256_length(self) -> None:
        assert len(compute_content_hash("test")) == 64


class TestParseAgent:
    def test_parse_agent_with_frontmatter(self, sample_claude_dir: Path) -> None:
        agent_path = sample_claude_dir / ".claude" / "agents" / "review.md"
        agent = parse_agent(agent_path)

        assert agent.asset_type == AssetType.AGENT
        assert agent.name == "review"
        assert agent.description == "Code review agent"
        assert agent.model == "sonnet"
        assert agent.permission_mode == "plan"
        assert agent.tools == ["Read", "Glob", "Grep", "Bash"]
        assert agent.body == "Review code changes for correctness and style.\n"
        assert agent.content_hash

    def test_parse_agent_from_fixture(self, fixtures_dir: Path) -> None:
        agent_path = fixtures_dir / ".claude" / "agents" / "review.md"
        agent = parse_agent(agent_path)

        assert agent.name == "review"
        assert "correctness" in agent.description
        assert agent.model == "sonnet"
        assert agent.tools == ["Read", "Glob", "Grep", "Bash"]

    def test_parse_agent_with_max_turns(self, fixtures_dir: Path) -> None:
        agent_path = fixtures_dir / ".claude" / "agents" / "implementer.md"
        agent = parse_agent(agent_path)

        assert agent.name == "implementer"
        assert agent.model == "opus"
        assert agent.max_turns == 20
        assert "Task" in agent.tools

    def test_parse_agent_no_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "plain.md"
        path.write_text("Just a plain markdown agent.\n")
        agent = parse_agent(path)

        assert agent.name == "plain"
        assert agent.description == ""
        assert agent.tools == []

    def test_parse_agent_name_fallback_to_stem(self, tmp_path: Path) -> None:
        path = tmp_path / "my-agent.md"
        path.write_text("---\ndescription: test agent\n---\nBody text.\n")
        agent = parse_agent(path)

        assert agent.name == "my-agent"


class TestParseSkill:
    def test_parse_skill_with_frontmatter(self, sample_claude_dir: Path) -> None:
        skill_path = sample_claude_dir / ".claude" / "skills" / "deploy" / "SKILL.md"
        skill = parse_skill(skill_path)

        assert skill.asset_type == AssetType.SKILL
        assert skill.name == "deploy"
        assert skill.description == "Deploy to staging and production"
        assert skill.user_invocable is True
        assert skill.body.startswith("Build and deploy")

    def test_parse_skill_from_fixture(self, fixtures_dir: Path) -> None:
        skill_path = fixtures_dir / ".claude" / "skills" / "deploy" / "SKILL.md"
        skill = parse_skill(skill_path)

        assert skill.name == "deploy"
        assert "Deploy" in skill.description

    def test_parse_skill_with_allowed_tools(self, fixtures_dir: Path) -> None:
        skill_path = fixtures_dir / ".claude" / "skills" / "test-runner" / "SKILL.md"
        skill = parse_skill(skill_path)

        assert skill.name == "test-runner"
        assert skill.allowed_tools == ["Bash", "Read", "Glob"]
        assert skill.disable_model_invocation is False

    def test_parse_skill_name_fallback_to_parent(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\ndescription: A skill\n---\nBody.\n")
        skill = parse_skill(skill_file)

        assert skill.name == "my-skill"


class TestParseHooks:
    def test_parse_hooks_json(self, sample_claude_dir: Path) -> None:
        hooks_path = sample_claude_dir / ".claude" / "hooks.json"
        hooks = parse_hooks(hooks_path)

        assert hooks.asset_type == AssetType.HOOK
        assert "PreToolUse" in hooks.events
        assert len(hooks.events["PreToolUse"]) == 1
        config = hooks.events["PreToolUse"][0]
        assert config.matcher == "*"
        assert len(config.hooks) == 1
        assert config.hooks[0].hook_type == "command"
        assert config.hooks[0].command == "echo ok"

    def test_parse_hooks_from_fixture(self, fixtures_dir: Path) -> None:
        hooks_path = fixtures_dir / ".claude" / "hooks.json"
        hooks = parse_hooks(hooks_path)

        assert "PreToolUse" in hooks.events

    def test_parse_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        hooks = parse_hooks(path)

        assert hooks.events == {}


class TestParseCommand:
    def test_parse_command_plain(self, sample_claude_dir: Path) -> None:
        cmd_path = sample_claude_dir / ".claude" / "commands" / "test.md"
        cmd = parse_command(cmd_path)

        assert cmd.asset_type == AssetType.COMMAND
        assert cmd.name == "test"
        assert "$ARGUMENTS" in cmd.body

    def test_parse_command_from_fixture(self, fixtures_dir: Path) -> None:
        cmd_path = fixtures_dir / ".claude" / "commands" / "lint.md"
        cmd = parse_command(cmd_path)

        assert cmd.name == "lint"
        assert "ruff" in cmd.body


class TestParseRule:
    def test_parse_rule_with_frontmatter(self, sample_claude_dir: Path) -> None:
        rule_path = sample_claude_dir / ".claude" / "rules" / "style.md"
        rule = parse_rule(rule_path)

        assert rule.asset_type == AssetType.RULE
        assert rule.name == "style"
        assert rule.description == "Python coding style"
        assert rule.apply_to == "**/*.py"

    def test_parse_rule_from_fixture(self, fixtures_dir: Path) -> None:
        rule_path = fixtures_dir / ".claude" / "rules" / "python-style.md"
        rule = parse_rule(rule_path)

        assert rule.name == "python-style"
        assert "**/*.py" in rule.apply_to


class TestParseSettings:
    def test_parse_settings_with_permissions(self, sample_claude_dir: Path) -> None:
        settings_path = sample_claude_dir / ".claude" / "settings.json"
        settings = parse_settings(settings_path)

        assert settings.asset_type == AssetType.SETTINGS
        assert "Read" in settings.permissions.allow
        assert "Write" in settings.permissions.allow
        assert "Bash(rm -rf:*)" in settings.permissions.deny

    def test_parse_settings_local(self, fixtures_dir: Path) -> None:
        settings_path = fixtures_dir / ".claude" / "settings.local.json"
        settings = parse_settings(settings_path)

        assert "WebSearch" in settings.permissions.allow
        assert any("docs.python.org" in p for p in settings.permissions.allow)

    def test_parse_settings_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{bad json")
        settings = parse_settings(path)

        assert settings.permissions.allow == []

    def test_parse_settings_with_hooks(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.json"
        path.write_text('{"permissions": {}, "hooks": {"PreToolUse": []}}')
        settings = parse_settings(path)

        assert settings.has_hooks is True


class TestParseClaudeMd:
    def test_parse_claude_md(self, sample_claude_dir: Path) -> None:
        md_path = sample_claude_dir / "CLAUDE.md"
        md = parse_claude_md(md_path)

        assert md.asset_type == AssetType.CLAUDE_MD
        assert md.name == "CLAUDE.md"
        assert md.line_count > 0
        assert md.has_imports is False

    def test_parse_claude_md_from_fixture(self, fixtures_dir: Path) -> None:
        md_path = fixtures_dir / "CLAUDE.md"
        md = parse_claude_md(md_path)

        assert "Python" in md.body
        assert md.line_count > 5

    def test_detect_imports(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        path.write_text("# Project\n\n@import other.md\n")
        md = parse_claude_md(path)

        assert md.has_imports is True


class TestFrontmatterEdgeCases:
    def test_no_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "agent.md"
        path.write_text("Just markdown, no frontmatter.\n")
        agent = parse_agent(path)

        assert agent.frontmatter == {}
        assert "Just markdown" in agent.body

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "agent.md"
        path.write_text("---\n: invalid: yaml: [[\n---\nBody.\n")
        agent = parse_agent(path)

        assert agent.frontmatter == {}

    def test_empty_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "agent.md"
        path.write_text("---\n\n---\nBody text here.\n")
        agent = parse_agent(path)

        # Empty YAML returns None, which we treat as no frontmatter
        assert agent.frontmatter == {}

    def test_frontmatter_not_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "agent.md"
        path.write_text("---\n- item1\n- item2\n---\nBody.\n")
        agent = parse_agent(path)

        assert agent.frontmatter == {}
