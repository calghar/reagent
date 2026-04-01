import json
from pathlib import Path

import pytest

from reagent.core.parsers import AssetType
from reagent.harness import HarnessFile, HarnessFormat, adapt, detect_harness
from reagent.harness.adapters import adapt_to_codex, adapt_to_cursor, adapt_to_opencode
from reagent.harness.agents_md import generate_agents_md
from reagent.intelligence.analyzer import RepoProfile
from reagent.llm.parser import GeneratedAsset


def _make_agent(name: str = "test-agent") -> GeneratedAsset:
    """Create a minimal AGENT GeneratedAsset for testing."""
    return GeneratedAsset(
        asset_type=AssetType.AGENT,
        frontmatter={
            "name": name,
            "description": "A test agent",
            "tools": ["Read", "Write", "Bash"],
        },
        body="Do helpful things.",
        raw_response="",
    )


def _make_skill(name: str = "deploy") -> GeneratedAsset:
    """Create a minimal SKILL GeneratedAsset for testing."""
    return GeneratedAsset(
        asset_type=AssetType.SKILL,
        frontmatter={
            "name": name,
            "description": "Deploy the application",
            "user-invocable": True,
        },
        body="Run the deployment pipeline.",
        raw_response="",
    )


def _make_rule(name: str = "style") -> GeneratedAsset:
    """Create a minimal RULE GeneratedAsset for testing."""
    return GeneratedAsset(
        asset_type=AssetType.RULE,
        frontmatter={
            "name": name,
            "description": "Code style guide",
        },
        body="Use type hints on all functions.",
        raw_response="",
    )


def _make_rule_no_cursor_keys(_name: str = "no-keys") -> GeneratedAsset:
    """Create a RULE asset that has no alwaysApply or globs keys."""
    return GeneratedAsset(
        asset_type=AssetType.RULE,
        frontmatter={"description": "A rule without Cursor keys"},
        body="Follow all rules.",
        raw_response="",
    )


def _make_hook() -> GeneratedAsset:
    """Create a minimal HOOK GeneratedAsset for testing."""
    hook_config = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "echo ok"}],
                }
            ]
        }
    }
    payload = json.dumps(hook_config)
    return GeneratedAsset(
        asset_type=AssetType.HOOK,
        frontmatter={},
        body=payload,
        raw_response=payload,
    )


def _make_claude_md() -> GeneratedAsset:
    """Create a minimal CLAUDE_MD GeneratedAsset for testing."""
    return GeneratedAsset(
        asset_type=AssetType.CLAUDE_MD,
        frontmatter={},
        body="# Project\n\nThis is a sample project.",
        raw_response="",
    )


def _make_profile() -> RepoProfile:
    """Create a minimal RepoProfile for testing."""
    import tempfile

    repo_path = str(Path(tempfile.gettempdir()) / "test-repo")
    return RepoProfile(
        repo_path=repo_path,
        repo_name="test-repo",
        primary_language="Python",
        frameworks=["pytest"],
    )


class TestHarnessFormatEnum:
    """Tests for HarnessFormat enum values."""

    def test_harness_format_enum(self) -> None:
        """HarnessFormat should have the correct string values."""
        assert HarnessFormat.CLAUDE_CODE == "claude-code"
        assert HarnessFormat.CURSOR == "cursor"
        assert HarnessFormat.CODEX == "codex"
        assert HarnessFormat.OPENCODE == "opencode"
        assert HarnessFormat.AGENTS_MD == "agents-md"

    def test_harness_format_is_str(self) -> None:
        """HarnessFormat values should behave as plain strings."""
        assert isinstance(HarnessFormat.CURSOR, str)
        assert HarnessFormat.CURSOR == "cursor"


class TestCursorAdapter:
    """Tests for adapt_to_cursor()."""

    @pytest.mark.parametrize(
        ("asset_factory", "asset_name", "expected_path"),
        [
            pytest.param(
                _make_agent, "my-agent", ".cursor/agents/my-agent.md", id="agent_path"
            ),
            pytest.param(
                _make_rule, "my-rule", ".cursor/rules/my-rule.md", id="rule_path"
            ),
            pytest.param(
                _make_skill,
                "my-skill",
                ".cursor/skills/my-skill/SKILL.md",
                id="skill_path",
            ),
        ],
    )
    def test_cursor_asset_path(
        self,
        asset_factory: object,
        asset_name: str,
        expected_path: str,
    ) -> None:
        """Asset type → correct Cursor path."""
        asset = asset_factory(asset_name)  # type: ignore[operator]
        files = adapt_to_cursor(asset)
        assert files[0].path == expected_path

    def test_cursor_agent_content_has_frontmatter(self) -> None:
        """Cursor agent file should contain YAML frontmatter and body."""
        asset = _make_agent("my-agent")
        files = adapt_to_cursor(asset)

        content = files[0].content
        assert "---" in content
        assert "my-agent" in content
        assert "Do helpful things." in content

    def test_cursor_rule_adds_frontmatter(self) -> None:
        """RULE with no alwaysApply/globs → those keys are injected."""
        asset = _make_rule_no_cursor_keys("no-keys")
        files = adapt_to_cursor(asset)

        assert len(files) == 1
        content = files[0].content
        assert "alwaysApply" in content
        assert "globs" in content

    def test_cursor_rule_preserves_existing_frontmatter(self) -> None:
        """Cursor adapter should preserve existing frontmatter keys."""
        asset = GeneratedAsset(
            asset_type=AssetType.RULE,
            frontmatter={
                "description": "keep me",
                "alwaysApply": True,
                "globs": ["**/*.py"],
            },
            body="Only Python files.",
            raw_response="",
        )
        files = adapt_to_cursor(asset)
        content = files[0].content
        assert "keep me" in content
        assert "alwaysApply: true" in content

    def test_cursor_hook_path_and_mode(self) -> None:
        """HOOK → .cursor/hooks/hooks.json with mode=merge_json."""
        asset = _make_hook()
        files = adapt_to_cursor(asset)
        assert len(files) == 1
        assert files[0].path == ".cursor/hooks/hooks.json"
        assert files[0].mode == "merge_json"

    def test_cursor_claude_md_becomes_rule(self) -> None:
        """CLAUDE_MD → .cursor/rules/project-context.md"""
        asset = _make_claude_md()
        files = adapt_to_cursor(asset)
        assert files[0].path == ".cursor/rules/project-context.md"
        assert "Project context" in files[0].content

    def test_cursor_command_path(self) -> None:
        """COMMAND → .cursor/commands/<name>.md"""
        asset = GeneratedAsset(
            asset_type=AssetType.COMMAND,
            frontmatter={"name": "run-tests"},
            body="Run the test suite.",
            raw_response="",
        )
        files = adapt_to_cursor(asset)
        assert files[0].path == ".cursor/commands/run-tests.md"


class TestCodexAdapter:
    """Tests for adapt_to_codex()."""

    def test_codex_agent_toml(self) -> None:
        """AGENT → .codex/agents/<name>.toml with valid TOML-like content."""
        asset = _make_agent("build-agent")
        files = adapt_to_codex(asset)

        assert len(files) == 1
        hfile = files[0]
        assert hfile.path == ".codex/agents/build-agent.toml"
        assert "[agent]" in hfile.content
        assert 'name = "build-agent"' in hfile.content
        assert 'description = "A test agent"' in hfile.content
        assert '"Read"' in hfile.content

    def test_codex_rule_appends_to_agents_md(self) -> None:
        """RULE → AGENTS.md with mode=append_section."""
        asset = _make_rule("my-rule")
        files = adapt_to_codex(asset)

        assert len(files) == 1
        hfile = files[0]
        assert hfile.path == "AGENTS.md"
        assert hfile.mode == "append_section"

    def test_codex_rule_section_contains_body(self) -> None:
        """Codex rule AGENTS.md section should include the rule body."""
        asset = _make_rule("type-hints")
        files = adapt_to_codex(asset)
        assert "Use type hints on all functions." in files[0].content

    def test_codex_skill_path(self) -> None:
        """SKILL → .agents/skills/<name>/SKILL.md"""
        asset = _make_skill("ci-deploy")
        files = adapt_to_codex(asset)
        assert files[0].path == ".agents/skills/ci-deploy/SKILL.md"

    def test_codex_hook_skipped(self) -> None:
        """HOOK → empty list (Codex has no hook support)."""
        asset = _make_hook()
        files = adapt_to_codex(asset)
        assert files == []

    def test_codex_claude_md_appends_agents_md(self) -> None:
        """CLAUDE_MD → AGENTS.md section with mode=append_section."""
        asset = _make_claude_md()
        files = adapt_to_codex(asset)
        assert len(files) == 1
        assert files[0].path == "AGENTS.md"
        assert files[0].mode == "append_section"


class TestOpenCodeAdapter:
    """Tests for adapt_to_opencode()."""

    @pytest.mark.parametrize(
        ("asset_factory", "asset_name", "expected_path"),
        [
            pytest.param(
                _make_agent,
                "oc-agent",
                ".opencode/agents/oc-agent.md",
                id="agent_path",
            ),
            pytest.param(
                _make_rule,
                "lint-rule",
                ".opencode/instructions/lint-rule.md",
                id="rule_path",
            ),
            pytest.param(
                _make_skill,
                "oc-skill",
                ".opencode/skills/oc-skill/SKILL.md",
                id="skill_path",
            ),
        ],
    )
    def test_opencode_asset_path(
        self,
        asset_factory: object,
        asset_name: str,
        expected_path: str,
    ) -> None:
        """Asset type → correct OpenCode path."""
        asset = asset_factory(asset_name)  # type: ignore[operator]
        files = adapt_to_opencode(asset)
        assert files[0].path == expected_path

    def test_opencode_hook_path_and_mode(self) -> None:
        """HOOK → opencode.json with mode=merge_json."""
        asset = _make_hook()
        files = adapt_to_opencode(asset)
        assert len(files) == 1
        assert files[0].path == "opencode.json"
        assert files[0].mode == "merge_json"

    def test_opencode_hook_json_has_plugins_key(self) -> None:
        """OpenCode hook JSON should use 'plugins' key."""
        asset = _make_hook()
        files = adapt_to_opencode(asset)
        data = json.loads(files[0].content)
        assert "plugins" in data

    def test_opencode_claude_md_path(self) -> None:
        """CLAUDE_MD → .opencode/instructions/project-context.md"""
        asset = _make_claude_md()
        files = adapt_to_opencode(asset)
        assert files[0].path == ".opencode/instructions/project-context.md"


class TestDetectHarness:
    """Tests for detect_harness()."""

    def test_detect_harness_claude_code(self, tmp_path: Path) -> None:
        """Repo with .claude/ → CLAUDE_CODE."""
        (tmp_path / ".claude").mkdir()
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CLAUDE_CODE

    def test_detect_harness_cursor_dir(self, tmp_path: Path) -> None:
        """Repo with .cursor/ → CURSOR."""
        (tmp_path / ".cursor").mkdir()
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CURSOR

    def test_detect_harness_cursor_rules_file(self, tmp_path: Path) -> None:
        """Repo with .cursorrules file → CURSOR."""
        (tmp_path / ".cursorrules").write_text("# rules")
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CURSOR

    def test_detect_harness_codex(self, tmp_path: Path) -> None:
        """Repo with codex.md → CODEX."""
        (tmp_path / "codex.md").write_text("# Codex")
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CODEX

    def test_detect_harness_opencode(self, tmp_path: Path) -> None:
        """Repo with opencode.md → OPENCODE."""
        (tmp_path / "opencode.md").write_text("# OpenCode")
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.OPENCODE

    def test_detect_harness_default(self, tmp_path: Path) -> None:
        """Empty repo → CLAUDE_CODE default."""
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CLAUDE_CODE

    def test_detect_harness_priority_claude_over_cursor(self, tmp_path: Path) -> None:
        """When both .claude/ and .cursor/ exist, Claude Code wins (priority order)."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".cursor").mkdir()
        result = detect_harness(tmp_path)
        assert result == HarnessFormat.CLAUDE_CODE


class TestGenerateAgentsMd:
    """Tests for generate_agents_md()."""

    def test_agents_md_structure(self) -> None:
        """Output should contain all required top-level sections."""
        profile = _make_profile()
        agents = [_make_agent("worker")]
        skills = [_make_skill("ci")]
        rules: list[GeneratedAsset] = []

        output = generate_agents_md(agents, skills, rules, profile)

        assert "# Agent Instructions" in output
        assert "## Project Context" in output
        assert "## Architecture Overview" in output
        assert "## Conventions" in output
        assert "## Agents" in output
        assert "## Skills" in output
        assert "## Workflows" in output
        assert "## Rules" in output

    def test_agents_md_contains_agent_name(self) -> None:
        """Agent name should appear in the output."""
        profile = _make_profile()
        output = generate_agents_md([_make_agent("my-worker")], [], [], profile)
        assert "my-worker" in output

    def test_agents_md_contains_skill_name(self) -> None:
        """Skill name should appear in the output."""
        profile = _make_profile()
        output = generate_agents_md([], [_make_skill("my-skill")], [], profile)
        assert "my-skill" in output

    def test_agents_md_contains_rule_body(self) -> None:
        """Rule body should be embedded in the Rules section."""
        profile = _make_profile()
        output = generate_agents_md([], [], [_make_rule("type-rule")], profile)
        assert "Use type hints on all functions." in output

    def test_agents_md_empty_lists(self) -> None:
        """generate_agents_md should not raise with empty asset lists."""
        profile = _make_profile()
        output = generate_agents_md([], [], [], profile)
        assert "# Agent Instructions" in output
        assert "_No agents defined._" in output
        assert "_No skills defined._" in output

    def test_agents_md_profile_name_appears(self) -> None:
        """Repo name from profile should appear in the output."""
        profile = _make_profile()
        output = generate_agents_md([], [], [], profile)
        assert "test-repo" in output

    def test_agents_md_profile_language_appears(self) -> None:
        """Primary language from profile should appear in the output."""
        profile = _make_profile()
        output = generate_agents_md([], [], [], profile)
        assert "Python" in output


class TestAdaptDispatch:
    """Tests for the top-level adapt() dispatcher."""

    @pytest.mark.parametrize(
        ("harness_format", "expected_path_fragment"),
        [
            pytest.param(
                HarnessFormat.CURSOR,
                ".cursor/agents/",
                id="cursor",
            ),
            pytest.param(
                HarnessFormat.CODEX,
                ".codex/agents/",
                id="codex",
            ),
            pytest.param(
                HarnessFormat.OPENCODE,
                ".opencode/agents/",
                id="opencode",
            ),
        ],
    )
    def test_adapt_dispatch(
        self,
        harness_format: HarnessFormat,
        expected_path_fragment: str,
    ) -> None:
        """adapt() with a target format should return correctly-formatted files."""
        asset = _make_agent("dispatch-test")
        files = adapt(asset, harness_format)
        assert len(files) == 1
        assert expected_path_fragment in files[0].path

    @pytest.mark.parametrize(
        "harness_format",
        [
            pytest.param(HarnessFormat.CLAUDE_CODE, id="claude_code"),
            pytest.param(HarnessFormat.AGENTS_MD, id="agents_md"),
        ],
    )
    def test_adapt_dispatch_returns_empty(
        self,
        harness_format: HarnessFormat,
    ) -> None:
        """adapt() with passthrough targets should return empty list."""
        asset = _make_agent("dispatch-test")
        files = adapt(asset, harness_format)
        assert files == []


class TestHarnessFile:
    """Tests for the HarnessFile dataclass."""

    def test_harness_file_defaults(self) -> None:
        """HarnessFile should default mode to 'write'."""
        hf = HarnessFile(path="some/file.md", content="hello")
        assert hf.mode == "write"
        assert hf.path == "some/file.md"
        assert hf.content == "hello"

    def test_harness_file_custom_mode(self) -> None:
        """HarnessFile should accept custom mode values."""
        hf = HarnessFile(path="AGENTS.md", content="section", mode="append_section")
        assert hf.mode == "append_section"
