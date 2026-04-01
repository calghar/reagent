from pathlib import Path

import pytest

from reagent.creation.specializer import specialize_repo
from reagent.intelligence.analyzer import DetectedTestConfig, LintConfig, RepoProfile


@pytest.fixture()
def global_claude_dir(tmp_path: Path) -> Path:
    """Create a mock global .claude/ directory with assets."""
    d = tmp_path / "global_claude"
    d.mkdir()

    # Global agent
    agents = d / "agents"
    agents.mkdir()
    (agents / "code-reviewer.md").write_text(
        "---\n"
        "name: code-reviewer\n"
        "description: Generic code review agent\n"
        "tools:\n  - Read\n  - Glob\n  - Grep\n"
        "---\n"
        "# Code Reviewer\n\n"
        "Review code for {{language}} best practices.\n"
        "Test with: `{{test_command}}`\n"
    )

    # Global skill
    skill_dir = d / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: review\n"
        "description: Review skill for {{framework}}\n"
        "---\n"
        "# Review\n\n"
        "Review {{language}} code in {{repo_name}}.\n"
    )

    # Global rule
    rules = d / "rules"
    rules.mkdir()
    (rules / "code-quality.md").write_text(
        "---\ndescription: Code quality rules\n---\nFollow {{language}} idioms.\n"
    )

    return d


@pytest.fixture()
def python_profile() -> RepoProfile:
    return RepoProfile(
        repo_path="/tmp/my-app",  # noqa: S108
        repo_name="my-app",
        languages=["python"],
        primary_language="python",
        frameworks=["fastapi"],
        test_config=DetectedTestConfig(
            runner="pytest",
            command="uv run pytest",
        ),
        lint_configs=[LintConfig(tool="ruff", command="ruff check")],
    )


class TestSpecializeRepo:
    def test_basic_specialization(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        assert result.count == 3  # agent + skill + rule
        assert len(result.skipped) == 0

    def test_parameter_injection(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        agent_draft = next(d for d in result.drafts if d.asset_type == "agent")
        assert "python" in agent_draft.content
        assert "uv run pytest" in agent_draft.content

    def test_skill_specialization(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        skill_draft = next(d for d in result.drafts if d.asset_type == "skill")
        assert "fastapi" in skill_draft.content
        assert "my-app" in skill_draft.content

    def test_rule_specialization(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        rule_draft = next(d for d in result.drafts if d.asset_type == "rule")
        assert "python" in rule_draft.content

    def test_target_paths(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        for draft in result.drafts:
            assert str(repo) in str(draft.target_path)
            assert ".claude" in str(draft.target_path)

    def test_write_assets(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        for draft in result.drafts:
            path = draft.write()
            assert path.exists()
            assert path.read_text() == draft.content

    def test_empty_global_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()
        empty_global = tmp_path / "empty"
        empty_global.mkdir()

        result = specialize_repo(
            repo,
            global_claude_dir=empty_global,
        )
        assert result.count == 0

    def test_repo_section_added(
        self,
        tmp_path: Path,
        global_claude_dir: Path,
        python_profile: RepoProfile,
    ) -> None:
        repo = tmp_path / "my-app"
        repo.mkdir()

        result = specialize_repo(
            repo,
            profile=python_profile,
            global_claude_dir=global_claude_dir,
        )

        agent_draft = next(d for d in result.drafts if d.asset_type == "agent")
        # Should have repo-specific section appended
        assert "Repository: my-app" in agent_draft.content
