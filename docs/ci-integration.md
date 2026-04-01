# CI Integration

Reagent integrates into CI/CD pipelines to enforce asset quality gates, detect drift, and optionally auto-fix below-threshold assets. Use it as a GitHub Action or run `reagent ci` directly.

## GitHub Action

The fastest way to add Reagent to your CI pipeline is with the official GitHub Action.

### Basic Usage

```yaml
# .github/workflows/reagent.yml
name: Asset Quality Check
on: [push, pull_request]

jobs:
  reagent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check asset quality
        uses: calghar/reagent@v0.3.0
        with:
          mode: check
          threshold: 70
          security: true
```

### Action Inputs

| Input | Description | Required | Default |
| --- | --- | --- | --- |
| `mode` | CI mode: `check`, `suggest`, or `auto-fix` | No | `check` |
| `threshold` | Minimum quality score (0–100) | No | `60` |
| `security` | Enable security scanning | No | `true` |
| `repo` | Repository path to evaluate | No | `.` |

### Action Outputs

| Output | Description |
| --- | --- |
| `score` | Overall quality score (0–100) |
| `passed` | Whether all assets passed the threshold (`true`/`false`) |

### Using Outputs in Workflows

```yaml
jobs:
  reagent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check asset quality
        id: quality
        uses: calghar/reagent@v0.3.0
        with:
          mode: check
          threshold: 70

      - name: Comment on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `Asset quality score: **${{ steps.quality.outputs.score }}**/100\nPassed: ${{ steps.quality.outputs.passed }}`
            })
```

## CI Modes

### `check` (default)

Evaluates all assets and fails if any are below the threshold or have security issues.

```yaml
- uses: calghar/reagent@v0.3.0
  with:
    mode: check
    threshold: 70
```

### `suggest`

Outputs improvement suggestions without failing the build. Useful for advisory checks.

```yaml
- uses: calghar/reagent@v0.3.0
  with:
    mode: suggest
```

### `auto-fix`

Regenerates below-threshold assets and commits the improvements. Best for non-main branches.

```yaml
- uses: calghar/reagent@v0.3.0
  with:
    mode: auto-fix
    threshold: 70
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

!!! warning
    `auto-fix` mode requires an LLM API key to regenerate assets. Without one, it falls back to template-based generation.

## Running `reagent ci` Directly

If you prefer not to use the GitHub Action, run the CLI command directly:

```bash
pip install reagent
reagent ci --threshold 70 --mode check --security
```

### CLI Options

```bash
reagent ci [OPTIONS]
```

| Flag | Description | Default |
| --- | --- | --- |
| `--mode MODE` | Operating mode: `check`, `suggest`, `auto-fix` | `check` |
| `--threshold FLOAT` | Minimum quality score (0–100) | `60.0` |
| `--security / --no-security` | Enable/disable security scanning | enabled |
| `--repo PATH` | Repository path to evaluate | current directory |
| `--json` | Output JSON instead of text | off |

### Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | All checks passed |
| 1 | One or more assets below quality threshold |
| 2 | Security issues found (takes priority over quality failures) |

## Drift Detection

Detect stale, outdated, or missing assets with `reagent drift`:

```bash
reagent drift --repo ./my-project
reagent drift --json   # Machine-readable output
```

Drift detection reports:

- **Stale assets** — not updated since significant repo changes
- **Missing assets** — expected assets that don't exist
- **Outdated assets** — configuration that references removed files or tools

### CI Drift Check

```yaml
- name: Check for drift
  run: |
    pip install reagent
    reagent drift --repo . --json
```

## Example Workflows

### Quality Gate on Pull Requests

```yaml
# .github/workflows/asset-quality.yml
name: Asset Quality Gate
on:
  pull_request:
    paths:
      - '.claude/**'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: calghar/reagent@v0.3.0
        with:
          mode: check
          threshold: 70
          security: true
```

### Nightly Quality Report

```yaml
# .github/workflows/asset-report.yml
name: Nightly Asset Report
on:
  schedule:
    - cron: '0 6 * * *'    # Daily at 6 AM UTC

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install reagent
        run: pip install reagent

      - name: Generate report
        run: |
          reagent ci --mode suggest --json > report.json
          reagent drift --json > drift.json

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: asset-report
          path: |
            report.json
            drift.json
```

### Auto-Fix on Feature Branches

```yaml
# .github/workflows/asset-autofix.yml
name: Auto-fix Assets
on:
  push:
    branches-ignore:
      - main
      - release/*
    paths:
      - '.claude/**'

jobs:
  autofix:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Auto-fix assets
        uses: calghar/reagent@v0.3.0
        with:
          mode: auto-fix
          threshold: 70
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Commit fixes
        run: |
          git config user.name "reagent[bot]"
          git config user.email "reagent@users.noreply.github.com"
          git add .claude/
          git diff --staged --quiet || git commit -m "fix: auto-improve below-threshold assets"
          git push
```

### GitLab CI

```yaml
# .gitlab-ci.yml
asset-quality:
  image: python:3.13-slim
  stage: test
  script:
    - pip install reagent
    - reagent ci --threshold 70 --security
  rules:
    - changes:
        - .claude/**/*
```

### Generic CI (Jenkins, CircleCI, etc.)

```bash
#!/bin/bash
set -e
pip install reagent
reagent ci --threshold 70 --mode check --security

# Exit code handling:
# 0 = all passed
# 1 = quality below threshold
# 2 = security issues found
```

## JSON Output Format

Use `--json` for machine-readable output:

```bash
reagent ci --json
```

```json
{
  "overall_score": 78.5,
  "security_grade": "B",
  "passed": true,
  "asset_results": [
    {
      "name": "code-reviewer",
      "type": "agent",
      "score": 85.0,
      "grade": "B",
      "passed": true
    }
  ],
  "drift_reports": [],
  "suggestions": [],
  "fixes_applied": [],
  "exit_code": 0
}
```

## Security Scanning in CI

When `security: true` (the default), the CI runner scans all `.claude/` assets for:

- Unrestricted tool access (`tools: ["*"]`)
- Dangerous permission modes (`bypassPermissions`, `dontAsk`)
- Shell injection patterns in hooks
- Secrets or credentials in asset content
- External URL references in prompts

Security failures produce exit code 2, which takes priority over quality failures (exit code 1). See [Security Scanning](security-scanning.md) for details on rules and severity levels.
