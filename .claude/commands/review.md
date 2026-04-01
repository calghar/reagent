---
allowed-tools: Read, Glob, Grep, Bash(git diff:*), Bash(git log:*), Bash(git show:*)
description: Review recent changes for bugs and style issues
---

## Context

- Recent changes: !`git diff HEAD`
- Modified files: !`git diff --name-only HEAD`

## Your task

Review all modified files for:
1. **Bugs**: Logic errors, None safety, resource leaks, exception handling
2. **Types**: Correct annotations, mypy compliance
3. **Style**: No module docstrings, no separator comments, parametrized tests, named constants via TuningConfig
4. **Security**: No hardcoded secrets, parameterized SQL, no command injection
5. **Patterns**: Uses get_tuning() for configurable values, Jinja2 for prompts, context managers for DB

Only report issues with confidence ≥ 80%. Be concise.
