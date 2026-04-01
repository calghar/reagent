from pathlib import Path

import pytest

from reagent.creation.creator import (
    create_asset,
    create_from_outline,
    generate_init_assets,
)
from reagent.intelligence.analyzer import (
    AssetAudit,
    DetectedTestConfig,
    LintConfig,
    RepoProfile,
)


@pytest.fixture()
def python_profile() -> RepoProfile:
    """Create a Python FastAPI repo profile."""
    return RepoProfile(
        repo_path="/tmp/test-repo",  # noqa: S108
        repo_name="test-repo",
        languages=["python"],
        primary_language="python",
        frameworks=["fastapi"],
        build_system="hatch",
        package_manager="uv",
        architecture="single-app",
        test_config=DetectedTestConfig(
            runner="pytest",
            command="uv run pytest",
            test_dir="tests",
        ),
        lint_configs=[LintConfig(tool="ruff", command="ruff check")],
        has_ci=True,
        ci_system="github-actions",
        has_docker=True,
        has_env_file=True,
        has_api_routes=True,
    )


@pytest.fixture()
def go_profile() -> RepoProfile:
    """Create a Go repo profile."""
    return RepoProfile(
        repo_path="/tmp/go-repo",  # noqa: S108
        repo_name="go-repo",
        languages=["go"],
        primary_language="go",
        frameworks=["gin"],
        package_manager="go modules",
        architecture="cli",
        test_config=DetectedTestConfig(
            runner="go test",
            command="go test ./...",
        ),
    )


class TestCreateAsset:
    @pytest.mark.parametrize(
        ("asset_type", "name", "expected_in", "not_expected_in"),
        [
            pytest.param(
                "agent",
                "reviewer",
                ["---", "python", "fastapi", "uv run pytest"],
                ["- Frameworks: python", "run tests"],
                id="agent",
            ),
            pytest.param(
                "skill",
                "deploy",
                ["allowed-tools:", "uv run pytest"],
                ["run tests"],
                id="skill",
            ),
            pytest.param(
                "hook",
                "test-on-edit",
                ["PostToolUse", "uv run pytest"],
                [],
                id="hook",
            ),
            pytest.param(
                "rule",
                "style",
                ["applyTo:", "*.py"],
                [],
                id="rule",
            ),
            pytest.param(
                "command",
                "test",
                ["$ARGUMENTS"],
                [],
                id="command",
            ),
        ],
    )
    def test_create_asset_type(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
        asset_type: str,
        name: str,
        expected_in: list[str],
        not_expected_in: list[str],
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        draft = create_asset(
            asset_type,
            repo,
            name=name,
            profile=python_profile,
        )
        assert draft.asset_type == asset_type
        for substring in expected_in:
            assert substring in draft.content or substring in draft.content.lower(), (
                f"Expected {substring!r} in content"
            )
        for substring in not_expected_in:
            assert substring not in draft.content, (
                f"Did not expect {substring!r} in content"
            )

    def test_invalid_asset_type(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        with pytest.raises(ValueError, match="Invalid asset type"):
            create_asset("invalid", repo, profile=python_profile)

    def test_go_agent(
        self,
        tmp_path: Path,
        go_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "go-repo"
        repo.mkdir()
        draft = create_asset(
            "agent",
            repo,
            name="reviewer",
            profile=go_profile,
        )
        assert "go" in draft.content.lower() or "Go" in draft.content
        # Must show actual framework
        assert "gin" in draft.content.lower()
        # Must show actual test command
        assert "go test" in draft.content

    def test_agent_no_frameworks_shows_none(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent with no frameworks should omit frameworks line.

        Should not repeat the language.
        """
        repo = tmp_path / "bare-repo"
        repo.mkdir()
        profile = RepoProfile(
            repo_path=str(repo),
            repo_name="bare-repo",
            languages=["python"],
            primary_language="python",
        )
        draft = create_asset("agent", repo, name="helper", profile=profile)
        # Must not show language as framework
        assert "- Frameworks: python" not in draft.content
        # Frameworks line omitted entirely when none
        assert "Frameworks:" not in draft.content

    def test_agent_no_test_command_omits_line(
        self,
        tmp_path: Path,
    ) -> None:
        """Agent with no test command should omit the test line entirely."""
        repo = tmp_path / "bare-repo"
        repo.mkdir()
        profile = RepoProfile(
            repo_path=str(repo),
            repo_name="bare-repo",
            languages=["python"],
            primary_language="python",
        )
        draft = create_asset("agent", repo, name="helper", profile=profile)
        assert "Test command" not in draft.content
        assert "run tests" not in draft.content

    def test_skill_no_test_command_omits_line(
        self,
        tmp_path: Path,
    ) -> None:
        """Skill with no test command should omit the test line entirely."""
        repo = tmp_path / "bare-repo"
        repo.mkdir()
        profile = RepoProfile(
            repo_path=str(repo),
            repo_name="bare-repo",
            languages=["python"],
            primary_language="python",
        )
        draft = create_asset("skill", repo, name="helper", profile=profile)
        assert "Test command" not in draft.content
        assert "run tests" not in draft.content

    def test_default_name_inferred(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        draft = create_asset(
            "agent",
            repo,
            profile=python_profile,
        )
        assert draft.name == "python-agent"

    def test_write_asset(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        draft = create_asset(
            "agent",
            repo,
            name="reviewer",
            profile=python_profile,
        )
        path = draft.write()
        assert path.exists()
        assert path.read_text() == draft.content


class TestCreateFromOutline:
    def test_simple_outline(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        outline = (
            "A skill that runs database migrations before deploy,"
            " needs Bash and Write tools"
        )
        draft = create_from_outline(
            outline,
            "skill",
            repo,
            profile=python_profile,
        )
        assert draft.asset_type == "skill"
        assert "Bash" in draft.content
        assert "Write" in draft.content

    def test_outline_with_model(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        outline = "An agent for security review using sonnet model"
        draft = create_from_outline(
            outline,
            "agent",
            repo,
            name="security",
            profile=python_profile,
        )
        assert "sonnet" in draft.content

    def test_outline_infers_name(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        outline = "A code review skill"
        draft = create_from_outline(
            outline,
            "skill",
            repo,
            profile=python_profile,
        )
        assert draft.name  # name should be inferred

    def test_from_outline_via_create_asset(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        draft = create_asset(
            "skill",
            repo,
            from_outline="A skill for running tests after changes",
            profile=python_profile,
        )
        assert draft.asset_type == "skill"


class TestGenerateInitAssets:
    def test_basic_init(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        drafts = generate_init_assets(repo, profile=python_profile)
        assert len(drafts) > 0

        types = [d.asset_type for d in drafts]
        # Should have CLAUDE.md, settings, hook at minimum
        assert "claude_md" in types
        assert "settings" in types

    def test_init_claude_md_has_real_values(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        """CLAUDE.md must contain actual profile data, not bogus defaults."""
        repo = tmp_path / "test-repo"
        repo.mkdir()
        drafts = generate_init_assets(repo, profile=python_profile)
        claude_md = next(d for d in drafts if d.asset_type == "claude_md")
        # Must contain real framework
        assert "fastapi" in claude_md.content.lower()
        assert "**Frameworks**: python" not in claude_md.content
        # Must contain real commands
        assert "uv run pytest" in claude_md.content
        assert "ruff check" in claude_md.content
        # Must NOT contain placeholder defaults
        assert "run tests" not in claude_md.content
        assert "none configured" not in claude_md.content

    def test_init_claude_md_no_test_omits_line(
        self,
        tmp_path: Path,
    ) -> None:
        """CLAUDE.md should omit test/lint lines when not detected."""
        repo = tmp_path / "bare-repo"
        repo.mkdir()
        profile = RepoProfile(
            repo_path=str(repo),
            repo_name="bare-repo",
            languages=["python"],
            primary_language="python",
        )
        drafts = generate_init_assets(repo, profile=profile)
        claude_md = next(d for d in drafts if d.asset_type == "claude_md")
        assert "Test command" not in claude_md.content
        assert "Lint command" not in claude_md.content
        assert "run tests" not in claude_md.content
        assert "none configured" not in claude_md.content

    def test_init_no_test_command_skips_hook(
        self,
        tmp_path: Path,
    ) -> None:
        """init should NOT generate a test hook when no test runner detected."""
        repo = tmp_path / "bare-repo"
        repo.mkdir()
        profile = RepoProfile(
            repo_path=str(repo),
            repo_name="bare-repo",
            languages=["python"],
            primary_language="python",
        )
        drafts = generate_init_assets(repo, profile=profile)
        hook_drafts = [d for d in drafts if d.asset_type == "hook"]
        assert len(hook_drafts) == 0

    def test_init_generates_hook_for_tests(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        drafts = generate_init_assets(repo, profile=python_profile)
        hook_drafts = [d for d in drafts if d.asset_type == "hook"]
        assert len(hook_drafts) >= 1
        # Hook must contain the actual test command
        assert "uv run pytest" in hook_drafts[0].content

    def test_init_generates_env_deny(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        drafts = generate_init_assets(repo, profile=python_profile)
        settings_drafts = [d for d in drafts if d.asset_type == "settings"]
        assert len(settings_drafts) == 1
        assert "Read(.env)" in settings_drafts[0].content

    def test_init_skips_existing_claude_md(
        self,
        tmp_path: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "test-repo"
        repo.mkdir()
        # Simulate existing CLAUDE.md
        python_profile.asset_audit = AssetAudit(
            has_claude_dir=True,
            has_claude_md=True,
            has_settings=True,
        )
        drafts = generate_init_assets(repo, profile=python_profile)
        types = [d.asset_type for d in drafts]
        assert "claude_md" not in types
        assert "settings" not in types
