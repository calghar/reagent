---
allowed-tools: Bash(git checkout --branch:*), Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*)
description: Stage, commit, and optionally push changes
---

## Context

- Current git status: !`git status`
- Current branch: !`git branch --show-current`

## Your task

Based on the above changes:
1. Review what has changed
2. Group related changes into logical commits if needed
3. Stage the appropriate files with `git add`
4. Create commits with clear, conventional commit messages (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
5. NEVER include "Co-authored-by" trailers or mention AI/Copilot in commit messages
6. Ask the user before pushing or creating PRs
