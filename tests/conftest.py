from collections.abc import Generator
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture(autouse=True, scope="session")
def _isolate_db(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None]:
    """Ensure tests never write to the real ~/.agentguard/agentguard.db."""
    db_dir = tmp_path_factory.mktemp("agentguard_test_db")
    db_path = str(db_dir / "agentguard.db")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AGENTGUARD_DB_PATH", db_path)
        yield


@pytest.fixture()
def fixtures_dir() -> Path:
    """Return the static fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture()
def sample_claude_dir(tmp_path: Path) -> Path:
    """Create a minimal .claude directory structure for testing."""
    claude_dir = tmp_path / "project" / ".claude"
    claude_dir.mkdir(parents=True)

    # Settings
    (claude_dir / "settings.json").write_text(
        '{"permissions": {"allow": ["Read", "Write"], "deny": ["Bash(rm -rf:*)"]}}'
    )

    # Settings local
    (claude_dir / "settings.local.json").write_text(
        '{"permissions": {"allow": ["WebSearch", "WebFetch(domain:docs.python.org)"]}}'
    )

    # Agent
    agents_dir = claude_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "review.md").write_text(
        "---\n"
        "name: review\n"
        "description: Code review agent\n"
        "model: sonnet\n"
        "permissionMode: plan\n"
        "tools:\n"
        "  - Read\n"
        "  - Glob\n"
        "  - Grep\n"
        "  - Bash\n"
        "---\n"
        "Review code changes for correctness and style.\n"
    )

    # Skill
    skill_dir = claude_dir / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: deploy\n"
        "description: Deploy to staging and production\n"
        "user-invocable: true\n"
        "---\n"
        "Build and deploy the application.\n"
    )

    # Command
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir()
    (commands_dir / "test.md").write_text("Run the test suite: pytest $ARGUMENTS\n")

    # Hooks
    (claude_dir / "hooks.json").write_text(
        '{"hooks": {"PreToolUse": [{"matcher": "*",'
        ' "hooks": [{"type": "command", "command": "echo ok"}]}]}}'
    )

    # Rules
    rules_dir = claude_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "style.md").write_text(
        "---\n"
        "description: Python coding style\n"
        "applyTo: '**/*.py'\n"
        "---\n"
        "Use type hints on all functions.\n"
    )

    # CLAUDE.md at project root
    project_dir = tmp_path / "project"
    (project_dir / "CLAUDE.md").write_text(
        "# Project\n\nA sample project for testing.\n"
    )

    return project_dir


@pytest.fixture()
def agentguard_home(tmp_path: Path) -> Path:
    """Create a temporary ~/.agentguard directory."""
    home = tmp_path / ".agentguard"
    home.mkdir()
    (home / "catalog.jsonl").write_text("")
    (home / "events.jsonl").write_text("")
    return home
