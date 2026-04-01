---
allowed-tools: Bash(uv run:*), Bash(uvx:*)
description: Run tests, lint, and type checking
---

## Context

- Modified files: !`git diff --name-only HEAD`
- Untracked files: !`git ls-files --others --exclude-standard`

## Your task

Run the full verification suite:
1. `uv run pytest tests/ -x -q --tb=short -k "not test_catalog_empty"` — tests
2. `uvx ruff check src/ tests/` — lint
3. `uv run python -m mypy src/reagent/` — type check

Report results concisely. If anything fails, show the relevant error output.
