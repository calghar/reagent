import json
import logging
from pathlib import Path
from typing import Any

from reagent.intelligence.analyzer import RepoProfile
from reagent.intelligence.patterns import PatternTemplate

logger = logging.getLogger(__name__)

TOOL_CATEGORIES: dict[str, dict[str, Any]] = {
    "read_only": {
        "tools": ["Read", "Grep", "Glob"],
        "keywords": {
            "reviewer",
            "auditor",
            "analyzer",
            "scanner",
            "inspector",
            "checker",
            "monitor",
            "observer",
            "watcher",
            "validator",
        },
        "signals": {
            "review",
            "audit",
            "analyze",
            "scan",
            "inspect",
            "check",
            "verify",
            "assess",
            "report",
        },
    },
    "read_write": {
        "tools": ["Read", "Write", "Edit", "Grep", "Glob"],
        "keywords": {
            "developer",
            "writer",
            "creator",
            "builder",
            "generator",
            "fixer",
            "updater",
            "implementer",
            "coder",
            "author",
        },
        "signals": {
            "create",
            "write",
            "implement",
            "build",
            "fix",
            "update",
            "add",
            "modify",
            "generate",
        },
    },
    "execute": {
        "tools": ["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
        "keywords": {
            "runner",
            "tester",
            "deployer",
            "executor",
            "debugger",
            "profiler",
            "benchmarker",
            "installer",
        },
        "signals": {
            "run",
            "test",
            "deploy",
            "execute",
            "debug",
            "profile",
            "benchmark",
            "install",
        },
    },
    "refactor": {
        "tools": ["Read", "Write", "Edit", "Grep", "Glob"],
        "keywords": {
            "refactorer",
            "cleaner",
            "optimizer",
            "migrator",
            "formatter",
            "modernizer",
            "simplifier",
        },
        "signals": {
            "refactor",
            "clean",
            "optimize",
            "migrate",
            "format",
            "simplify",
            "restructure",
        },
    },
}


def classify_tools(name: str, description: str = "") -> list[str]:
    """Classify tools by semantic category analysis.

    Scores each category by keyword and description signal matches,
    then returns the tools for the highest-scoring category.
    Defaults to read-write if no match.

    Args:
        name: Asset name.
        description: Optional description text.

    Returns:
        List of tool names.
    """
    combined = f"{name} {description}".lower()
    words = set(combined.replace("-", " ").replace("_", " ").split())

    scores: dict[str, float] = {}
    for category, config in TOOL_CATEGORIES.items():
        keyword_hits = len(words & config["keywords"])
        signal_hits = sum(1 for s in config["signals"] if s in combined)
        scores[category] = keyword_hits * 2 + signal_hits

    best_score = max(scores.values()) if scores else 0
    if best_score > 0:
        best = max(scores, key=lambda k: scores[k])
        best_category = TOOL_CATEGORIES.get(best)
        if best_category is None:
            return []
        return list(best_category.get("tools", []))

    # Default: read-write (better to grant too much than be non-functional)
    return ["Read", "Write", "Edit", "Grep", "Glob"]


def compress_profile(profile: RepoProfile) -> dict[str, str]:
    """Convert a RepoProfile to a comprehensive parameter dict.

    Unlike profile_to_params, this includes ALL relevant fields.

    Args:
        profile: Repository profile to convert.

    Returns:
        Flat dict of string parameters.
    """
    lint_commands = [lc.command for lc in profile.lint_configs]
    conventions = profile.conventions or {}
    return {
        "language": profile.primary_language or "code",
        "languages": ", ".join(profile.languages) or "code",
        "framework": ", ".join(profile.frameworks) or "none",
        "test_command": profile.test_config.command or "",
        "test_dir": profile.test_config.test_dir or "",
        "lint_commands": ", ".join(lint_commands),
        "lint_command": lint_commands[0] if lint_commands else "",
        "repo_name": profile.repo_name,
        "package_manager": profile.package_manager or "",
        "build_system": profile.build_system or "",
        "architecture": profile.architecture or "",
        "ci_system": profile.ci_system or "",
        "line_length": conventions.get("line_length", ""),
        "naming": conventions.get("naming", ""),
        "entry_points": ", ".join(profile.entry_points[:5]),
    }


def _try_render_pattern(
    pattern: PatternTemplate | None,
    profile: RepoProfile,
) -> str | None:
    """Attempt to render content from a pattern template.

    Args:
        pattern: Optional pattern template.
        profile: Repository profile for parameter substitution.

    Returns:
        Rendered content string, or None if pattern is unavailable.
    """
    if not pattern or not pattern.assets:
        return None
    params = compress_profile(profile)
    rendered = pattern.render(params)
    if rendered:
        return rendered[0].get("content")
    return None


def _agent_description(name: str, lang: str, repo_name: str) -> str:
    """Generate a meaningful agent description based on the name.

    Args:
        name: Agent name.
        lang: Primary programming language.
        repo_name: Repository display name.

    Returns:
        Description string suitable for frontmatter.
    """
    name_lower = name.lower()
    descriptions: list[tuple[list[str], str]] = [
        (
            ["review"],
            f"Code review agent — reviews {lang} changes for quality, "
            f"correctness, and conventions in {repo_name}",
        ),
        (
            ["security", "audit"],
            f"Security audit agent — reviews {lang} code for "
            f"vulnerabilities and security best practices in {repo_name}",
        ),
        (
            ["test"],
            f"Test specialist — writes and maintains {lang} tests for {repo_name}",
        ),
        (
            ["devops", "deploy", "ops"],
            f"DevOps agent — manages deployment, CI/CD, and\
                 infrastructure for {repo_name}",
        ),
        (
            ["implement", "develop", "code"],
            f"Implementation agent — writes production {lang} code for {repo_name}",
        ),
    ]

    for keywords, desc in descriptions:
        if any(kw in name_lower for kw in keywords):
            return desc
    return f"{lang.title()} specialist for {repo_name}"


def _agent_responsibilities(
    name: str,
    lang: str,
    test_cmd: str,
) -> list[str]:
    """Generate responsibilities tailored to the agent type.

    Args:
        name: Agent name.
        lang: Primary programming language.
        test_cmd: Test command (may be empty).

    Returns:
        List of responsibility strings.
    """
    name_lower = name.lower()
    if "review" in name_lower:
        resps = [
            "Review staged/pending changes for correctness and quality",
            f"Check adherence to {lang} standards and conventions",
            "Identify bugs, logic errors, and edge cases",
            "Produce a structured review report with verdict",
        ]
        if test_cmd:
            resps.append("Verify test coverage for changed code")
        return resps

    if "security" in name_lower:
        return [
            "Audit code for common security vulnerabilities",
            "Check dependency versions for known CVEs",
            "Review permission handling and auth logic",
            "Flag hardcoded secrets and injection risks",
        ]

    if "test" in name_lower:
        resps = [
            f"Write comprehensive {lang} tests for changed code",
            "Cover edge cases, error paths, and boundaries",
        ]
        if test_cmd:
            resps.append(f"Run `{test_cmd}` after every change")
        return resps

    # Default (implementer)
    resps = [
        f"Write production {lang} code following conventions",
        "Ensure changes are well-tested",
        "Keep commits small and focused",
    ]
    if test_cmd:
        resps.append(f"Run `{test_cmd}` before marking work complete")
    return resps


def _agent_constraints(
    name: str,
    test_cmd: str,
) -> list[str]:
    """Generate constraints tailored to the agent type.

    Args:
        name: Agent name.
        test_cmd: Test command (may be empty).

    Returns:
        List of constraint strings.
    """
    constraints: list[str] = []
    if "review" in name.lower():
        constraints.append("Never modify files — read-only review only")
    constraints.append("Never commit secrets or API keys")
    constraints.append("Never push to main without explicit approval")
    if test_cmd:
        constraints.append(f"Always run `{test_cmd}` to verify changes")
    return constraints


def _build_agent_frontmatter(
    name: str,
    tools: list[str],
    lang: str,
    repo_name: str,
    model: str,
    permission: str,
) -> str:
    """Build YAML frontmatter for an agent.

    Args:
        name: Agent name.
        tools: List of tool names.
        lang: Primary programming language.
        repo_name: Repository display name.
        model: Model string (may be empty).
        permission: Permission mode string (may be empty).

    Returns:
        Frontmatter block including ``---`` delimiters.
    """
    desc = _agent_description(name, lang, repo_name)
    lines = ["---", f"name: {name}", f"description: {desc}"]
    if model:
        lines.append(f"model: {model}")
    if permission:
        lines.append(f"permissionMode: {permission}")
    lines.append("tools:")
    for t in tools:
        lines.append(f"  - {t}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _build_agent_body(
    name: str,
    profile: RepoProfile,
) -> str:
    """Build the markdown body for an agent.

    Args:
        name: Agent name.
        profile: Repository profile.

    Returns:
        Markdown body string.
    """
    lang = profile.primary_language or "code"
    frameworks = ", ".join(profile.frameworks) if profile.frameworks else ""
    test_cmd = profile.test_config.command
    lint_cmds = [lc.command for lc in profile.lint_configs]
    lint_cmd = lint_cmds[0] if lint_cmds else ""
    title = name.replace("-", " ").title()

    lines = [
        f"# {title}",
        "",
        f"You are a {lang} specialist working on {profile.repo_name}.",
        "",
        "## Stack",
        f"- Language: {lang}",
    ]

    if frameworks:
        lines.append(f"- Frameworks: {frameworks}")
    if profile.build_system:
        lines.append(f"- Build: {profile.build_system}")
    if profile.package_manager:
        lines.append(f"- Package manager: {profile.package_manager}")
    if test_cmd:
        lines.append(f"- Test command: `{test_cmd}`")
    for lc in lint_cmds:
        lines.append(f"- Lint: `{lc}`")
    lines.append("")

    lines.append("## Responsibilities")
    for resp in _agent_responsibilities(name, lang, test_cmd):
        lines.append(f"- {resp}")
    lines.append("")

    # Constraints section
    lines.append("## Constraints")
    for c in _agent_constraints(name, test_cmd):
        lines.append(f"- **{c}**")
    lines.append("")

    if "review" not in name.lower():
        lines.extend(_build_workflow_steps(lang, test_cmd, lint_cmd))

    return "\n".join(lines) + "\n"


def _build_workflow_steps(
    lang: str,
    test_cmd: str,
    lint_cmd: str,
) -> list[str]:
    """Build numbered workflow steps for an agent body.

    Args:
        lang: Primary programming language.
        test_cmd: Test command (may be empty).
        lint_cmd: Lint command (may be empty).

    Returns:
        List of markdown lines for the workflow section.
    """
    lines = [
        "## Workflow",
        f"1. Understand the task and relevant {lang} code",
        "2. Make changes incrementally with tests",
    ]
    step = 3
    if test_cmd:
        lines.append(f"{step}. Run `{test_cmd}` and fix any failures")
        step += 1
    if lint_cmd:
        lines.append(f"{step}. Run `{lint_cmd}` and fix any issues")
        step += 1
    lines.append(f"{step}. Present a summary of changes for review")
    lines.append("")
    return lines


def generate_agent(
    name: str,
    profile: RepoProfile,
    pattern: PatternTemplate | None = None,
    repo_path: Path | None = None,
) -> str:
    """Generate agent markdown content.

    Args:
        name: Agent name.
        profile: Repository profile for context.
        pattern: Optional pattern to base the agent on.
        repo_path: Repo path for exemplar discovery.

    Returns:
        Complete agent markdown with frontmatter.
    """
    _ = repo_path  # reserved for future exemplar use
    rendered = _try_render_pattern(pattern, profile)
    if rendered:
        return rendered

    lang = profile.primary_language or "code"
    tools = classify_tools(name)

    is_reviewer = "review" in name.lower()
    model = "sonnet" if is_reviewer else ""
    permission = "plan" if is_reviewer else ""

    fm = _build_agent_frontmatter(
        name,
        tools,
        lang,
        profile.repo_name,
        model,
        permission,
    )
    body = _build_agent_body(name, profile)

    return fm + body


def _skill_description(name: str, lang: str, repo_name: str) -> str:
    """Generate meaningful skill description.

    Args:
        name: Skill name.
        lang: Primary programming language.
        repo_name: Repository display name.

    Returns:
        Description string suitable for frontmatter.
    """
    name_lower = name.lower()
    checks = ("ci", "check", "build")
    deploys = ("deploy", "ship", "release")

    if any(k in name_lower for k in checks):
        return f"Run CI checks ({lang} tests, linting, type-checking) for {repo_name}"
    if any(k in name_lower for k in deploys):
        return f"Deploy or release {repo_name}"
    if "review" in name_lower:
        return f"Run code review on current changes in {repo_name}"
    if "test" in name_lower:
        return f"Run and verify tests for {repo_name}"
    if "lint" in name_lower:
        return f"Run linters and formatters for {repo_name}"
    return f"{name.replace('-', ' ').title()} for {repo_name}"


def _skill_steps(
    name: str,
    lang: str,
    test_cmd: str,
    lint_cmd: str,
) -> list[str]:
    """Generate procedural steps for a skill.

    Args:
        name: Skill name.
        lang: Primary programming language.
        test_cmd: Test command (may be empty).
        lint_cmd: Lint command (may be empty).

    Returns:
        List of step strings (without numbering).
    """
    name_lower = name.lower()

    if any(k in name_lower for k in ("ci", "check", "build")):
        return _ci_check_steps(test_cmd, lint_cmd)
    if "review" in name_lower:
        return _review_steps(lang)
    if "test" in name_lower:
        return _test_steps(test_cmd)
    if any(k in name_lower for k in ("deploy", "ship", "release")):
        return _deploy_steps(test_cmd, lint_cmd)
    return _default_skill_steps(lang, test_cmd, lint_cmd)


def _ci_check_steps(test_cmd: str, lint_cmd: str) -> list[str]:
    """Generate steps for CI/check/build skills.

    Args:
        test_cmd: Test runner command.
        lint_cmd: Linter command.

    Returns:
        List of step description strings.
    """
    steps: list[str] = []
    if test_cmd:
        steps.append(f"Run tests: `{test_cmd}`")
    if lint_cmd:
        steps.append(f"Run linter: `{lint_cmd}`")
    steps.append(
        "If any step fails, read the error output and\
         identify the failing file and line"
    )
    steps.append("Suggest a fix for each error")
    steps.append("If all checks pass, confirm success")
    return steps


def _review_steps(lang: str) -> list[str]:
    """Generate steps for review skills.

    Args:
        lang: Primary language name.

    Returns:
        List of step description strings.
    """
    return [
        "Gather changes: `git diff --stat HEAD` and `git diff HEAD`",
        f"Review all changes for correctness and {lang} idioms",
        "Check for bugs, logic errors, and edge cases",
        "Produce a structured review report with verdict",
    ]


def _test_steps(test_cmd: str) -> list[str]:
    """Generate steps for test skills.

    Args:
        test_cmd: Test runner command.

    Returns:
        List of step description strings.
    """
    steps = [
        "Identify changed files: `git diff --name-only HEAD`",
        "Write or update tests for changed code",
    ]
    if test_cmd:
        steps.append(f"Run tests: `{test_cmd}`")
    steps.append("Report test results and coverage")
    return steps


def _deploy_steps(test_cmd: str, lint_cmd: str) -> list[str]:
    """Generate steps for deploy/ship/release skills.

    Args:
        test_cmd: Test runner command.
        lint_cmd: Linter command.

    Returns:
        List of step description strings.
    """
    steps: list[str] = []
    if test_cmd:
        steps.append(f"Run tests: `{test_cmd}`")
    if lint_cmd:
        steps.append(f"Run linter: `{lint_cmd}`")
    steps.append("Verify all checks pass before proceeding")
    steps.append("Stage changes and prepare release commit")
    steps.append("**WAIT for human approval** before pushing")
    return steps


def _default_skill_steps(
    lang: str,
    test_cmd: str,
    lint_cmd: str,
) -> list[str]:
    """Generate default steps when no specific skill type matches.

    Args:
        lang: Primary language name.
        test_cmd: Test runner command.
        lint_cmd: Linter command.

    Returns:
        List of step description strings.
    """
    steps = [
        "Parse `$ARGUMENTS` to determine the task scope",
        f"Identify relevant {lang} source files for the task",
    ]
    if test_cmd:
        steps.append(f"Run tests after changes: `{test_cmd}`")
    if lint_cmd:
        steps.append(f"Run linter: `{lint_cmd}`")
    steps.append("Verify all changes are correct and complete")
    return steps


def generate_skill(
    name: str,
    profile: RepoProfile,
    pattern: PatternTemplate | None = None,
    repo_path: Path | None = None,
) -> str:
    """Generate skill SKILL.md content.

    Args:
        name: Skill name.
        profile: Repository profile for context.
        pattern: Optional pattern to base the skill on.
        repo_path: Repo path for exemplar discovery (reserved).

    Returns:
        Complete skill markdown with frontmatter.
    """
    _ = repo_path  # reserved for future exemplar use
    rendered = _try_render_pattern(pattern, profile)
    if rendered:
        return rendered

    lang = profile.primary_language or "code"
    test_cmd = profile.test_config.command
    lint_cmds = [lc.command for lc in profile.lint_configs]
    lint_cmd = lint_cmds[0] if lint_cmds else ""

    tools = classify_tools(name)
    tools_str = ", ".join(tools)
    desc = _skill_description(name, lang, profile.repo_name)

    body_lines = [
        f"# /{name} — {name.replace('-', ' ').title()}",
        "",
        desc,
        "",
        "## Steps",
        "",
    ]
    for i, step in enumerate(_skill_steps(name, lang, test_cmd, lint_cmd), 1):
        body_lines.append(f"{i}. {step}")
    body_lines.append("")

    fm = f"---\nname: {name}\ndescription: {desc}\nallowed-tools: [{tools_str}]\n---\n"
    return fm + "\n".join(body_lines) + "\n"


def generate_hook(name: str, profile: RepoProfile) -> str:
    """Generate hooks.json content.

    Args:
        name: Hook name (unused, reserved for multi-hook support).
        profile: Repository profile for context.

    Returns:
        JSON string for hooks.json.
    """
    _ = name  # reserved for future multi-hook support
    test_cmd = profile.test_config.command or "echo 'no tests configured'"
    return (
        "{\n"
        '  "hooks": {\n'
        '    "PostToolUse": [\n'
        "      {\n"
        '        "matcher": "Write|Edit",\n'
        '        "hooks": [\n'
        "          {\n"
        '            "type": "command",\n'
        f'            "command": "{test_cmd}",\n'
        '            "timeout": 30000\n'
        "          }\n"
        "        ]\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
    )


def generate_command(name: str, profile: RepoProfile) -> str:
    """Generate command markdown content.

    Args:
        name: Command name.
        profile: Repository profile for context.

    Returns:
        Complete command markdown.
    """
    title = name.replace("-", " ").title()
    return f"# {title}\n\nRun in {profile.repo_name}: $ARGUMENTS\n"


def generate_rule(name: str, profile: RepoProfile) -> str:
    """Generate rule markdown content.

    Args:
        name: Rule name.
        profile: Repository profile for context.

    Returns:
        Complete rule markdown with frontmatter.
    """
    lang = profile.primary_language or "code"
    ext_map = {
        "python": "py",
        "typescript": "ts",
        "javascript": "js",
        "go": "go",
        "rust": "rs",
        "swift": "swift",
        "ruby": "rb",
    }
    ext = ext_map.get(lang, "*")
    title = name.replace("-", " ").title()

    return (
        f"---\n"
        f"description: {title} rules\n"
        f"applyTo: '**/*.{ext}'\n"
        f"---\n"
        f"# {title}\n\n"
        f"Coding conventions for {lang} in {profile.repo_name}.\n"
    )


def generate_claude_md(profile: RepoProfile) -> str:
    """Generate a starter CLAUDE.md.

    Args:
        profile: Repository profile for context.

    Returns:
        Complete CLAUDE.md content.
    """
    lang = profile.primary_language or "code"
    frameworks = ", ".join(profile.frameworks) if profile.frameworks else ""
    test_cmd = profile.test_config.command
    lint_cmds = [lc.command for lc in profile.lint_configs]
    lint_cmd = lint_cmds[0] if lint_cmds else ""
    arch = profile.architecture or "application"

    lines = [
        f"# {profile.repo_name}",
        "",
        "## Project Overview",
        f"{lang.title()} {arch} project.",
        "",
        "## Stack",
        f"- **Language**: {lang}",
    ]

    if frameworks:
        lines.append(f"- **Frameworks**: {frameworks}")
    if profile.build_system:
        lines.append(f"- **Build**: {profile.build_system}")
    if profile.package_manager:
        lines.append(f"- **Package manager**: {profile.package_manager}")
    if test_cmd:
        lines.append(f"- **Test command**: `{test_cmd}`")
    for lc in lint_cmds:
        lines.append(f"- **Lint**: `{lc}`")
    if profile.ci_system:
        lines.append(f"- **CI**: {profile.ci_system}")
    lines.append("")

    cmds = _dev_commands(test_cmd, lint_cmd)
    if cmds:
        lines.append("## Development Commands")
        lines.extend(cmds)
        lines.append("")

    lines.extend(_conventions(test_cmd, lint_cmd))

    return "\n".join(lines)


def _dev_commands(test_cmd: str, lint_cmd: str) -> list[str]:
    """Build development command bullet points.

    Args:
        test_cmd: Test command (may be empty).
        lint_cmd: Lint command (may be empty).

    Returns:
        List of markdown bullet lines.
    """
    cmds: list[str] = []
    if test_cmd:
        cmds.append(f"- Run tests: `{test_cmd}`")
    if lint_cmd:
        cmds.append(f"- Lint: `{lint_cmd}`")
    return cmds


def _conventions(test_cmd: str, lint_cmd: str) -> list[str]:
    """Build conventions section lines.

    Args:
        test_cmd: Test command (may be empty).
        lint_cmd: Lint command (may be empty).

    Returns:
        List of markdown lines including the section heading.
    """
    lines = [
        "## Conventions",
        "- Follow existing code style and project patterns",
        "- Write tests for new functionality",
    ]
    if test_cmd:
        lines.append(f"- Run `{test_cmd}` before committing")
    if lint_cmd:
        lines.append(f"- Run `{lint_cmd}` to check for style issues")
    lines.append("- Keep commits small and focused")
    lines.append("- Never commit secrets or API keys")
    lines.append("")
    return lines


def generate_settings(profile: RepoProfile) -> str:
    """Generate a starter settings.json.

    Args:
        profile: Repository profile for context.

    Returns:
        JSON string for settings.json.
    """
    allow: list[str] = []
    deny: list[str] = []

    if profile.test_config.command:
        allow.append(f"Bash({profile.test_config.command})")
    for lc in profile.lint_configs:
        if lc.command:
            allow.append(f"Bash({lc.command})")

    if profile.has_env_file:
        deny.append("Read(.env)")
        deny.append("Read(.env.local)")

    settings: dict[str, Any] = {"permissions": {}}
    if allow:
        settings["permissions"]["allow"] = allow
    if deny:
        settings["permissions"]["deny"] = deny

    return json.dumps(settings, indent=2) + "\n"
