import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DependencyInfo(BaseModel):
    """A detected project dependency."""

    name: str
    version: str = ""
    dev: bool = False


class DetectedTestConfig(BaseModel):
    """Detected test configuration."""

    runner: str = ""  # pytest, jest, go test, xcodebuild test, etc.
    command: str = ""  # Full test command
    test_dir: str = ""  # Primary test directory


class LintConfig(BaseModel):
    """Detected linter/formatter configuration."""

    tool: str = ""
    config_file: str = ""
    command: str = ""


class AssetAudit(BaseModel):
    """Audit of existing .claude/ assets."""

    has_claude_dir: bool = False
    has_claude_md: bool = False
    has_settings: bool = False
    has_hooks: bool = False
    agent_count: int = 0
    skill_count: int = 0
    rule_count: int = 0
    command_count: int = 0
    issues: list[str] = Field(default_factory=list)


class RepoProfile(BaseModel):
    """Complete profile of a repository."""

    repo_path: str
    repo_name: str
    languages: list[str] = Field(default_factory=list)
    primary_language: str = ""
    frameworks: list[str] = Field(default_factory=list)
    build_system: str = ""
    package_manager: str = ""
    architecture: str = ""  # monorepo, single-app, library, cli, etc.
    entry_points: list[str] = Field(default_factory=list)
    test_config: DetectedTestConfig = Field(default_factory=DetectedTestConfig)
    lint_configs: list[LintConfig] = Field(default_factory=list)
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    dev_dependencies: list[DependencyInfo] = Field(default_factory=list)
    has_ci: bool = False
    ci_system: str = ""
    has_docker: bool = False
    has_env_file: bool = False
    has_api_routes: bool = False
    is_monorepo: bool = False
    workspaces: list[str] = Field(default_factory=list)
    conventions: dict[str, str] = Field(default_factory=dict)
    asset_audit: AssetAudit = Field(default_factory=AssetAudit)

    def save(self, output_dir: Path | None = None) -> Path:
        """Save the repo profile to YAML.

        Args:
            output_dir: Override output directory. Defaults to ~/.reagent/repos/.

        Returns:
            Path to the saved profile file.
        """
        dest = output_dir or (Path.home() / ".reagent" / "repos")
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{self.repo_name}.yaml"
        path.write_text(
            yaml.dump(
                self.model_dump(exclude_defaults=True),
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load_profile(
        cls,
        repo_name: str,
        profiles_dir: Path | None = None,
    ) -> "RepoProfile | None":
        """Load a saved repo profile.

        Args:
            repo_name: Name of the repository.
            profiles_dir: Override profiles directory.

        Returns:
            Loaded RepoProfile, or None if not found.
        """
        directory = profiles_dir or (Path.home() / ".reagent" / "repos")
        path = directory / f"{repo_name}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return cls.model_validate(data)


def _detect_python_tests(repo: Path, profile: RepoProfile) -> None:
    """Detect Python test runner and test directory.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    has_pytest_cfg = (repo / "pytest.ini").exists() or (repo / "conftest.py").exists()
    has_test_dir = (repo / "tests").is_dir() or (repo / "test").is_dir()

    if has_pytest_cfg or has_test_dir:
        profile.test_config.runner = "pytest"

    if profile.test_config.runner == "pytest":
        cmd_map = {"uv": "uv run pytest", "poetry": "poetry run pytest"}
        profile.test_config.command = cmd_map.get(
            profile.package_manager,
            "pytest",
        )

    if (repo / "tests").is_dir():
        profile.test_config.test_dir = "tests"
    elif (repo / "test").is_dir():
        profile.test_config.test_dir = "test"


def _detect_python_linters(
    repo: Path,
    profile: RepoProfile,
) -> None:
    """Detect Python linters and formatters.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    pyproject = repo / "pyproject.toml"

    if (repo / "ruff.toml").exists():
        profile.lint_configs.append(
            LintConfig(
                tool="ruff",
                config_file="ruff.toml",
                command="ruff check",
            )
        )
    elif pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        if "[tool.ruff]" in content:
            profile.lint_configs.append(
                LintConfig(
                    tool="ruff",
                    config_file="pyproject.toml",
                    command="ruff check",
                )
            )
    if (repo / ".flake8").exists():
        profile.lint_configs.append(
            LintConfig(
                tool="flake8",
                config_file=".flake8",
                command="flake8",
            )
        )

    has_mypy_ini = (repo / "mypy.ini").exists()
    has_mypy_toml = pyproject.exists() and "[tool.mypy]" in pyproject.read_text(
        encoding="utf-8"
    )
    if has_mypy_ini or has_mypy_toml:
        profile.lint_configs.append(
            LintConfig(tool="mypy", command="mypy"),
        )


def _detect_python(repo: Path, profile: RepoProfile) -> None:
    """Detect Python language and framework details.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    pyproject = repo / "pyproject.toml"
    setup_py = repo / "setup.py"
    setup_cfg = repo / "setup.cfg"
    requirements = repo / "requirements.txt"

    markers = [pyproject, setup_py, setup_cfg, requirements]
    if not any(p.exists() for p in markers):
        if not list(repo.glob("**/*.py"))[:1]:
            return

    profile.languages.append("python")

    if pyproject.exists():
        _parse_pyproject(pyproject, profile)
    elif requirements.exists():
        _parse_requirements(requirements, profile)

    _detect_python_tests(repo, profile)
    _detect_python_linters(repo, profile)


def _parse_pyproject(path: Path, profile: RepoProfile) -> None:
    """Extract info from pyproject.toml.

    Args:
        path: Path to pyproject.toml.
        profile: Profile to populate.
    """
    content = path.read_text(encoding="utf-8")

    # Detect build backend / package manager
    if "hatchling" in content:
        profile.build_system = "hatch"
    elif "poetry" in content.lower():
        profile.build_system = "poetry"
        profile.package_manager = "poetry"
    elif "setuptools" in content:
        profile.build_system = "setuptools"
    elif "flit" in content:
        profile.build_system = "flit"

    # uv detection
    if (path.parent / "uv.lock").exists():
        profile.package_manager = "uv"
    elif not profile.package_manager:
        profile.package_manager = "pip"

    # Framework detection from dependencies
    deps_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies"):
            deps_section = True
            continue
        if deps_section:
            if stripped.startswith("]"):
                deps_section = False
                continue
            _check_python_framework(stripped, profile)

    # Detect pytest in test deps
    if "pytest" in content:
        profile.test_config.runner = "pytest"


def _check_python_framework(dep_line: str, profile: RepoProfile) -> None:
    """Check a dependency line for known Python frameworks.

    Args:
        dep_line: A single dependency line from pyproject.toml.
        profile: Profile to populate.
    """
    dep_lower = dep_line.lower()
    if "fastapi" in dep_lower:
        profile.frameworks.append("fastapi")
        profile.has_api_routes = True
    elif "flask" in dep_lower:
        profile.frameworks.append("flask")
        profile.has_api_routes = True
    elif "django" in dep_lower:
        profile.frameworks.append("django")
        profile.has_api_routes = True
    elif "click" in dep_lower and "cli" not in profile.architecture:
        profile.architecture = "cli"
    elif "typer" in dep_lower and "cli" not in profile.architecture:
        profile.architecture = "cli"


def _parse_requirements(path: Path, profile: RepoProfile) -> None:
    """Extract framework info from requirements.txt.

    Args:
        path: Path to requirements.txt.
        profile: Profile to populate.
    """
    content = path.read_text(encoding="utf-8").lower()
    profile.package_manager = "pip"

    if "fastapi" in content:
        profile.frameworks.append("fastapi")
        profile.has_api_routes = True
    if "flask" in content:
        profile.frameworks.append("flask")
        profile.has_api_routes = True
    if "django" in content:
        profile.frameworks.append("django")
        profile.has_api_routes = True


def _detect_js_package_manager(repo: Path) -> str:
    """Detect the JavaScript package manager from lock files.

    Args:
        repo: Repository root path.

    Returns:
        Package manager name string.
    """
    lock_files = {
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "bun.lockb": "bun",
    }
    for filename, pm in lock_files.items():
        if (repo / filename).exists():
            return pm
    return "npm"


def _detect_js_tests(
    all_deps: dict[str, Any],
    scripts: dict[str, str],
    profile: RepoProfile,
) -> None:
    """Detect JavaScript test runner from dependencies and scripts.

    Args:
        all_deps: Combined dependencies dict.
        scripts: Package.json scripts dict.
        profile: Profile to populate.
    """
    test_script = scripts.get("test", "")
    pm = profile.package_manager

    if "jest" in test_script or "jest" in all_deps:
        profile.test_config.runner = "jest"
        profile.test_config.command = f"{pm} test"
    elif "vitest" in test_script or "vitest" in all_deps:
        profile.test_config.runner = "vitest"
        profile.test_config.command = f"{pm} test"
    elif test_script:
        profile.test_config.command = f"{pm} test"


def _detect_js_workspaces(
    data: dict[str, Any],
    profile: RepoProfile,
) -> None:
    """Detect monorepo workspace configuration.

    Args:
        data: Parsed package.json dict.
        profile: Profile to populate.
    """
    workspaces = data.get("workspaces", [])
    if not workspaces:
        return
    profile.is_monorepo = True
    if isinstance(workspaces, list):
        profile.workspaces = workspaces
    elif isinstance(workspaces, dict) and "packages" in workspaces:
        profile.workspaces = workspaces["packages"]


def _detect_javascript(repo: Path, profile: RepoProfile) -> None:
    """Detect JavaScript/TypeScript and frameworks.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    pkg_json = repo / "package.json"
    if not pkg_json.exists():
        has_ts = bool(list(repo.glob("*.ts"))[:1])
        has_js = bool(list(repo.glob("*.js"))[:1])
        if has_ts or has_js:
            profile.languages.append("javascript")
        return

    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    lang = "typescript" if (repo / "tsconfig.json").exists() else "javascript"
    profile.languages.append(lang)
    profile.package_manager = _detect_js_package_manager(repo)

    all_deps = {
        **data.get("dependencies", {}),
        **data.get("devDependencies", {}),
    }
    _check_js_frameworks(all_deps, profile)
    _detect_js_tests(all_deps, data.get("scripts", {}), profile)
    _check_js_lint(all_deps, profile)
    _detect_js_workspaces(data, profile)


def _check_js_frameworks(
    all_deps: dict[str, Any],
    profile: RepoProfile,
) -> None:
    """Check JS dependencies for known frameworks.

    Args:
        all_deps: Combined dependencies dict.
        profile: Profile to populate.
    """
    if "next" in all_deps:
        profile.frameworks.append("next.js")
    if "react" in all_deps:
        profile.frameworks.append("react")
    if "vue" in all_deps:
        profile.frameworks.append("vue")
    if "express" in all_deps:
        profile.frameworks.append("express")
        profile.has_api_routes = True
    if "@nestjs/core" in all_deps:
        profile.frameworks.append("nestjs")
        profile.has_api_routes = True


def _check_js_lint(
    all_deps: dict[str, Any],
    profile: RepoProfile,
) -> None:
    """Detect JS linters from dependencies.

    Args:
        all_deps: Combined dependencies dict.
        profile: Profile to populate.
    """
    if "eslint" in all_deps:
        profile.lint_configs.append(LintConfig(tool="eslint", command="eslint ."))
    if "prettier" in all_deps:
        profile.lint_configs.append(LintConfig(tool="prettier"))
    if "biome" in all_deps or "@biomejs/biome" in all_deps:
        profile.lint_configs.append(LintConfig(tool="biome"))


def _detect_go(repo: Path, profile: RepoProfile) -> None:
    """Detect Go language and framework details.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    go_mod = repo / "go.mod"
    if not go_mod.exists():
        return

    profile.languages.append("go")
    profile.package_manager = "go modules"
    profile.test_config.runner = "go test"
    profile.test_config.command = "go test ./..."

    content = go_mod.read_text(encoding="utf-8")

    # Framework detection
    if "github.com/gin-gonic/gin" in content:
        profile.frameworks.append("gin")
        profile.has_api_routes = True
    if "github.com/gorilla/mux" in content:
        profile.frameworks.append("gorilla/mux")
        profile.has_api_routes = True
    if "github.com/labstack/echo" in content:
        profile.frameworks.append("echo")
        profile.has_api_routes = True

    # Architecture detection for Go
    if (repo / "cmd").is_dir():
        profile.architecture = "cli"
        profile.entry_points = [
            str(p.relative_to(repo)) for p in (repo / "cmd").iterdir() if p.is_dir()
        ]
    if (repo / "pkg").is_dir():
        profile.architecture = "library"

    # Linter
    if (repo / ".golangci.yml").exists() or (repo / ".golangci.yaml").exists():
        profile.lint_configs.append(
            LintConfig(tool="golangci-lint", command="golangci-lint run")
        )


def _detect_rust(repo: Path, profile: RepoProfile) -> None:
    """Detect Rust language and framework details.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    cargo = repo / "Cargo.toml"
    if not cargo.exists():
        return

    profile.languages.append("rust")
    profile.package_manager = "cargo"
    profile.build_system = "cargo"
    profile.test_config.runner = "cargo test"
    profile.test_config.command = "cargo test"

    content = cargo.read_text(encoding="utf-8")
    if "actix-web" in content:
        profile.frameworks.append("actix-web")
        profile.has_api_routes = True
    if "axum" in content:
        profile.frameworks.append("axum")
        profile.has_api_routes = True
    if "rocket" in content:
        profile.frameworks.append("rocket")
        profile.has_api_routes = True

    # Workspace detection
    if "[workspace]" in content:
        profile.is_monorepo = True

    profile.lint_configs.append(LintConfig(tool="clippy", command="cargo clippy"))


def _detect_swift(repo: Path, profile: RepoProfile) -> None:
    """Detect Swift/iOS project details.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    xcodeproj_dirs = list(repo.glob("*.xcodeproj"))
    package_swift = repo / "Package.swift"

    if not xcodeproj_dirs and not package_swift.exists():
        return

    profile.languages.append("swift")

    if xcodeproj_dirs:
        profile.build_system = "xcode"
        profile.test_config.runner = "xcodebuild test"
        profile.test_config.command = "xcodebuild test"
        profile.frameworks.append("swiftui")

    if package_swift.exists():
        profile.build_system = "swift package manager"
        profile.package_manager = "spm"
        profile.test_config.runner = "swift test"
        profile.test_config.command = "swift test"

    if any(repo.rglob("*SwiftUI*")) and "swiftui" not in profile.frameworks:
        profile.frameworks.append("swiftui")

    if (repo / ".swiftlint.yml").exists():
        profile.lint_configs.append(LintConfig(tool="swiftlint", command="swiftlint"))


def _detect_ruby(repo: Path, profile: RepoProfile) -> None:
    """Detect Ruby language and framework details.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    gemfile = repo / "Gemfile"
    if not gemfile.exists():
        return

    profile.languages.append("ruby")
    profile.package_manager = "bundler"

    content = gemfile.read_text(encoding="utf-8").lower()
    if "rails" in content:
        profile.frameworks.append("rails")
        profile.has_api_routes = True
    if "sinatra" in content:
        profile.frameworks.append("sinatra")
        profile.has_api_routes = True

    if "rspec" in content:
        profile.test_config.runner = "rspec"
        profile.test_config.command = "bundle exec rspec"
    elif "minitest" in content:
        profile.test_config.runner = "minitest"
        profile.test_config.command = "bundle exec rake test"

    if (repo / ".rubocop.yml").exists():
        profile.lint_configs.append(
            LintConfig(tool="rubocop", command="bundle exec rubocop")
        )


def _detect_architecture(repo: Path, profile: RepoProfile) -> None:
    """Detect project architecture from directory structure.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    if profile.architecture:
        return  # Already set by language detector

    dirs = {d.name for d in repo.iterdir() if d.is_dir() and not d.name.startswith(".")}

    if "packages" in dirs or "apps" in dirs:
        profile.is_monorepo = True
        profile.architecture = "monorepo"
        return

    if "cmd" in dirs or "bin" in dirs:
        profile.architecture = "cli"
        return

    if "lib" in dirs and "src" not in dirs:
        profile.architecture = "library"
        return

    if "app" in dirs or "pages" in dirs or "views" in dirs:
        profile.architecture = "web-app"
        return

    if "src" in dirs:
        profile.architecture = "single-app"
        return

    profile.architecture = "unknown"


def _detect_conventions(repo: Path, profile: RepoProfile) -> None:
    """Extract coding conventions from the repository.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    if (repo / ".editorconfig").exists():
        profile.conventions["editor_config"] = "present"

    # Naming conventions by language
    lang_naming = {
        "python": "snake_case",
        "go": "camelCase",
        "swift": "camelCase",
        "ruby": "snake_case",
        "typescript": "camelCase",
        "javascript": "camelCase",
    }
    for lang in profile.languages:
        if lang in lang_naming:
            profile.conventions["naming"] = lang_naming[lang]
            break

    # Line length from configs
    for lc in profile.lint_configs:
        if lc.config_file:
            cfg_path = repo / lc.config_file
            if cfg_path.exists():
                content = cfg_path.read_text(encoding="utf-8")
                match = re.search(r"line[_-]?length\s*=\s*(\d+)", content)
                if match:
                    profile.conventions["line_length"] = match.group(1)
                    break


# --- CI / Docker / Env Detection ---


def _detect_ci(repo: Path, profile: RepoProfile) -> None:
    """Detect CI/CD configuration.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    ci_indicators = [
        (".github/workflows", "github-actions"),
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        (".circleci", "circleci"),
        (".travis.yml", "travis"),
    ]
    for indicator, system in ci_indicators:
        if (repo / indicator).exists():
            profile.has_ci = True
            profile.ci_system = system
            return


def _detect_docker(repo: Path, profile: RepoProfile) -> None:
    """Detect Docker configuration.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    docker_files = [
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]
    profile.has_docker = any((repo / f).exists() for f in docker_files)


def _detect_env(repo: Path, profile: RepoProfile) -> None:
    """Detect .env files.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    env_files = [".env", ".env.example", ".env.local"]
    profile.has_env_file = any((repo / f).exists() for f in env_files)


def _audit_assets(repo: Path, profile: RepoProfile) -> None:
    """Audit existing .claude/ configuration quality.

    Args:
        repo: Repository root path.
        profile: Profile to populate.
    """
    audit = AssetAudit()
    claude_dir = repo / ".claude"

    if not claude_dir.exists():
        profile.asset_audit = audit
        return

    audit.has_claude_dir = True
    audit.has_settings = (claude_dir / "settings.json").exists()
    audit.has_hooks = (claude_dir / "hooks.json").exists() or (
        audit.has_settings
        and "hooks"
        in (claude_dir / "settings.json").read_text(
            encoding="utf-8",
        )
    )

    # Count assets
    agents_dir = claude_dir / "agents"
    if agents_dir.is_dir():
        audit.agent_count = sum(1 for _ in agents_dir.glob("*.md"))

    skills_dir = claude_dir / "skills"
    if skills_dir.is_dir():
        audit.skill_count = sum(
            1 for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
        )

    rules_dir = claude_dir / "rules"
    if rules_dir.is_dir():
        audit.rule_count = sum(1 for _ in rules_dir.glob("*.md"))

    commands_dir = claude_dir / "commands"
    if commands_dir.is_dir():
        audit.command_count = sum(1 for _ in commands_dir.glob("*.md"))

    # Check for CLAUDE.md
    audit.has_claude_md = (repo / "CLAUDE.md").exists() or (
        repo / ".claude" / "CLAUDE.md"
    ).exists()

    # Issues
    if not audit.has_settings:
        audit.issues.append("No settings.json -- no permission rules configured")
    if not audit.has_claude_md:
        audit.issues.append("No CLAUDE.md -- missing project context for Claude")

    profile.asset_audit = audit


def analyze_repo(repo_path: Path) -> RepoProfile:
    """Analyze a repository and produce a RepoProfile.

    Runs all detection heuristics: language, framework, architecture,
    conventions, CI, Docker, env files, and existing asset audit.

    Args:
        repo_path: Path to the repository root.

    Returns:
        Complete RepoProfile for the repository.
    """
    repo = repo_path.resolve()
    logger.info("Analyzing repo: %s", repo)
    profile = RepoProfile(
        repo_path=str(repo),
        repo_name=repo.name,
    )

    # Language & framework detection
    _detect_python(repo, profile)
    _detect_javascript(repo, profile)
    _detect_go(repo, profile)
    _detect_rust(repo, profile)
    _detect_swift(repo, profile)
    _detect_ruby(repo, profile)

    # Set primary language
    if profile.languages:
        profile.primary_language = profile.languages[0]

    # Architecture
    _detect_architecture(repo, profile)

    # Conventions
    _detect_conventions(repo, profile)

    # CI / Docker / Env
    _detect_ci(repo, profile)
    _detect_docker(repo, profile)
    _detect_env(repo, profile)

    # Asset audit
    _audit_assets(repo, profile)

    logger.info(
        "Repo %s: lang=%s, frameworks=%s, test=%s, assets=%d",
        profile.repo_name,
        profile.primary_language,
        profile.frameworks,
        profile.test_config.command,
        profile.asset_audit.agent_count
        + profile.asset_audit.skill_count
        + profile.asset_audit.rule_count
        + profile.asset_audit.command_count,
    )
    return profile
