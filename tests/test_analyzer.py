import json
from pathlib import Path

import pytest

from reagent.intelligence.analyzer import RepoProfile, analyze_repo


@pytest.fixture()
def python_repo(tmp_path: Path) -> Path:
    """Create a minimal Python project."""
    repo = tmp_path / "my-app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        '[project]\nname = "my-app"\n'
        'dependencies = [\n  "fastapi>=0.100",\n  "click>=8.0",\n]\n'
        "[tool.ruff]\nline-length = 100\n"
        "[tool.mypy]\nstrict = true\n"
    )
    (repo / "uv.lock").write_text("")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "conftest.py").write_text("")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    (repo / "Dockerfile").write_text("FROM python:3.13\n")
    (repo / ".env.example").write_text("SECRET=xxx\n")
    return repo


@pytest.fixture()
def go_repo(tmp_path: Path) -> Path:
    """Create a minimal Go project."""
    repo = tmp_path / "my-go-app"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/my-go-app\n\ngo 1.21\n\n"
        "require github.com/gin-gonic/gin v1.9.1\n"
    )
    (repo / "cmd" / "server").mkdir(parents=True)
    (repo / "cmd" / "server" / "main.go").write_text("package main\n")
    (repo / "pkg").mkdir()
    (repo / ".golangci.yml").write_text("linters:\n")
    return repo


@pytest.fixture()
def js_repo(tmp_path: Path) -> Path:
    """Create a minimal JS/TS project."""
    repo = tmp_path / "my-js-app"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "my-js-app",
                "scripts": {"test": "jest"},
                "dependencies": {"next": "^14.0", "react": "^18.0"},
                "devDependencies": {"jest": "^29.0", "eslint": "^8.0"},
            }
        )
    )
    (repo / "tsconfig.json").write_text("{}")
    (repo / "yarn.lock").write_text("")
    return repo


@pytest.fixture()
def swift_repo(tmp_path: Path) -> Path:
    """Create a minimal Swift project."""
    repo = tmp_path / "my-ios-app"
    repo.mkdir()
    (repo / "MyApp.xcodeproj").mkdir()
    (repo / ".swiftlint.yml").write_text("disabled_rules:\n")
    return repo


class TestPythonDetection:
    def test_language(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert "python" in profile.languages
        assert profile.primary_language == "python"

    def test_framework(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert "fastapi" in profile.frameworks

    def test_build_system(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.build_system == "hatch"
        assert profile.package_manager == "uv"

    def test_test_config(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.test_config.runner == "pytest"
        assert profile.test_config.command == "uv run pytest"
        assert profile.test_config.test_dir == "tests"

    def test_lint_config(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        tools = [lc.tool for lc in profile.lint_configs]
        assert "ruff" in tools
        assert "mypy" in tools

    def test_ci(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.has_ci
        assert profile.ci_system == "github-actions"

    def test_docker(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.has_docker

    def test_env_file(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.has_env_file

    def test_api_routes(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.has_api_routes

    def test_architecture(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.architecture == "cli"


class TestGoDetection:
    def test_language(self, go_repo: Path) -> None:
        profile = analyze_repo(go_repo)
        assert "go" in profile.languages

    def test_framework(self, go_repo: Path) -> None:
        profile = analyze_repo(go_repo)
        assert "gin" in profile.frameworks

    def test_test_command(self, go_repo: Path) -> None:
        profile = analyze_repo(go_repo)
        assert profile.test_config.command == "go test ./..."

    def test_linter(self, go_repo: Path) -> None:
        profile = analyze_repo(go_repo)
        tools = [lc.tool for lc in profile.lint_configs]
        assert "golangci-lint" in tools


class TestJSDetection:
    def test_language(self, js_repo: Path) -> None:
        profile = analyze_repo(js_repo)
        assert "typescript" in profile.languages

    def test_frameworks(self, js_repo: Path) -> None:
        profile = analyze_repo(js_repo)
        assert "next.js" in profile.frameworks
        assert "react" in profile.frameworks

    def test_package_manager(self, js_repo: Path) -> None:
        profile = analyze_repo(js_repo)
        assert profile.package_manager == "yarn"

    def test_test_runner(self, js_repo: Path) -> None:
        profile = analyze_repo(js_repo)
        assert profile.test_config.runner == "jest"


class TestSwiftDetection:
    def test_language(self, swift_repo: Path) -> None:
        profile = analyze_repo(swift_repo)
        assert "swift" in profile.languages

    def test_build_system(self, swift_repo: Path) -> None:
        profile = analyze_repo(swift_repo)
        assert profile.build_system == "xcode"

    def test_linter(self, swift_repo: Path) -> None:
        profile = analyze_repo(swift_repo)
        tools = [lc.tool for lc in profile.lint_configs]
        assert "swiftlint" in tools


class TestConventions:
    def test_naming_python(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.conventions.get("naming") == "snake_case"

    def test_line_length(self, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        assert profile.conventions.get("line_length") == "100"


class TestAssetAudit:
    def test_no_claude_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "bare"
        repo.mkdir()
        profile = analyze_repo(repo)
        assert not profile.asset_audit.has_claude_dir

    def test_with_claude_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "configured"
        repo.mkdir()
        claude = repo / ".claude"
        claude.mkdir()
        (claude / "settings.json").write_text("{}")
        agents = claude / "agents"
        agents.mkdir()
        (agents / "review.md").write_text("---\nname: review\ndescription: test\n---\n")
        (repo / "CLAUDE.md").write_text("# Project\n")

        profile = analyze_repo(repo)
        assert profile.asset_audit.has_claude_dir
        assert profile.asset_audit.has_settings
        assert profile.asset_audit.has_claude_md
        assert profile.asset_audit.agent_count == 1


class TestProfileSaveLoad:
    def test_round_trip(self, tmp_path: Path, python_repo: Path) -> None:
        profile = analyze_repo(python_repo)
        output_dir = tmp_path / "profiles"
        profile.save(output_dir)

        loaded = RepoProfile.load_profile(
            profile.repo_name,
            output_dir,
        )
        assert loaded is not None
        assert loaded.primary_language == "python"
        assert loaded.repo_name == profile.repo_name

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        loaded = RepoProfile.load_profile("nonexistent", tmp_path)
        assert loaded is None
