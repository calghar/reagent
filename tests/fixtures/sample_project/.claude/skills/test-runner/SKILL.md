---
name: test-runner
description: Run and analyze test results
user-invocable: true
disable-model-invocation: false
allowed-tools: [Bash, Read, Glob]
---

# /test-runner -- Run Tests

## Steps

1. Identify changed files: `git diff --name-only HEAD`
2. Run related tests: `pytest $ARGUMENTS`
3. Analyze failures and suggest fixes
