# CI Integration

Reagent integrates into CI/CD pipelines to enforce asset quality gates, detect drift, and surface improvement suggestions. Run `reagent ci` directly in any CI system.

## Running `reagent ci`

Install Reagent and run the CI command:

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

```bash
reagent drift --repo . --json
```

## Example CI Configurations

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

When security scanning is enabled (the default), the CI runner scans all `.claude/` assets for:

- Unrestricted tool access (`tools: ["*"]`)
- Dangerous permission modes (`bypassPermissions`, `dontAsk`)
- Shell injection patterns in hooks
- Secrets or credentials in asset content
- External URL references in prompts

Security failures produce exit code 2, which takes priority over quality failures (exit code 1). See [Security Scanning](security-scanning.md) for details on rules and severity levels.
