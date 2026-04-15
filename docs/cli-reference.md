# CLI Reference

## Global Options

All commands accept these flags:

| Flag | Description |
| --- | --- |
| `-v`, `--verbose` | Enable verbose (DEBUG-level) logging to stderr |
| `--log-file PATH` | Log file path (default: `~/.reagent/reagent.log`) |

## Inventory

### `reagent inventory`

Scan for Claude Code assets and update the catalog.

```bash
reagent inventory                    # Scan all configured roots
reagent inventory --repo ./my-repo   # Scan a single repository
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Scan a single repository instead of all configured roots |

### `reagent catalog`

List all cataloged assets.

```bash
reagent catalog
reagent catalog --type agent
reagent catalog --repo my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--type TYPE` | Filter by asset type (agent, skill, hook, command, rule, settings, claude-md, memory) |
| `--repo NAME` | Filter by repository name |

### `reagent show ASSET_ID`

Show detailed view of an asset or suggestion.

```bash
reagent show my-project:agent:reviewer
reagent show --suggestion 3
```

**Options:**

| Flag | Description |
| --- | --- |
| `--suggestion` | Interpret the argument as a suggestion number |

## Analysis

### `reagent analyze REPO`

Analyze a repository for language, framework, and conventions.

```bash
reagent analyze ./my-project
```

Outputs detected languages, frameworks, architecture style, test/lint configuration, CI setup, and an asset audit.

### `reagent extract-patterns`

Scan all cataloged assets and extract reusable patterns.

```bash
reagent extract-patterns
```

Clusters similar assets and generates parameterized templates for reuse across repositories.

### `reagent apply-pattern PATTERN_NAME`

Apply a pattern template to a repository.

```bash
reagent apply-pattern ci-deploy --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Target repository (default: current directory) |

### `reagent validate PATH`

Validate an asset file against the schema registry.

```bash
reagent validate ./my-project/.claude/agents/reviewer.md
```

Checks both portable Agent Skills fields and Claude Code vendor extension fields.

## Security

### `reagent scan PATH`

Run the security scanner on a file or directory.

```bash
reagent scan ./agent.md
reagent scan ./my-project/.claude
```

Reports findings by severity (critical, high, medium) with rule IDs, line numbers, and descriptions.

### `reagent audit`

Run a full security audit on a repository's `.claude/` directory.

```bash
reagent audit --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to audit (default: current directory) |

### `reagent import SOURCE`

Import a Claude Code asset from a local path, git URL, or gist.

```bash
reagent import ./shared-agent.md
reagent import https://gist.github.com/user/abc123
reagent import --target-repo ./my-project https://github.com/user/repo
```

Runs security scan, displays findings, and requires explicit approval before installation.

**Options:**

| Flag | Description |
| --- | --- |
| `--target-repo PATH` | Target repository for installation (default: current directory) |

### `reagent trust show ASSET_ID`

Show trust level and history for an asset.

```bash
reagent trust show my-project:agent:reviewer
```

### `reagent trust promote ASSET_ID`

Promote an asset to a higher trust level.

```bash
reagent trust promote my-project:agent:reviewer --level 2 --reason "Reviewed and approved"
```

**Options:**

| Flag | Description |
| --- | --- |
| `--level INT` | Target trust level (2 = REVIEWED, 3 = VERIFIED) |
| `--reason TEXT` | Justification for promotion |

### `reagent integrity check`

Verify all tracked asset hashes against the catalog.

```bash
reagent integrity check
```

### `reagent integrity report`

Show tampered or modified assets since last scan.

```bash
reagent integrity report
```

### `reagent history ASSET_ID`

Show snapshot timeline for an asset.

```bash
reagent history my-project:agent:reviewer
```

### `reagent rollback ASSET_ID`

Restore an asset from a previous snapshot.

```bash
reagent rollback my-project:agent:reviewer --snapshot 3
```

**Options:**

| Flag | Description |
| --- | --- |
| `--snapshot INT` | Snapshot ID to restore |

## Evaluation

### `reagent evaluate`

Compute quality scores for all assets in a repository.

```bash
reagent evaluate --repo ./my-project
```

Reports per-asset quality scores with metrics: invocation rate, correction rate, turn efficiency, staleness, coverage, and security score.

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to evaluate (default: current directory) |

### `reagent check-regression SESSION_ID`

Check a session for quality regressions against the baseline.

```bash
reagent check-regression abc123 --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository path (default: current directory) |

### `reagent variant ASSET_ID`

Create an A/B test variant of an asset.

```bash
reagent variant my-project:agent:reviewer --name v2 --change "Reduced verbosity"
```

**Options:**

| Flag | Description |
| --- | --- |
| `--name TEXT` | Variant name |
| `--change TEXT` | Description of the change |

### `reagent compare ASSET_A ASSET_B`

Compare quality metrics between two assets or variants.

```bash
reagent compare my-project:agent:reviewer my-project:agent:reviewer-v2
```

### `reagent promote VARIANT_ID`

Promote a variant to replace its original asset.

```bash
reagent promote my-project:agent:reviewer-v2
```

### `reagent rollback-best ASSET_ID`

Rollback an asset to its historically best-quality version.

```bash
reagent rollback-best my-project:agent:reviewer
```

## CI Integration

### `reagent ci`

Evaluate asset quality for CI pipelines.

Exits with code 0 if all checks pass, 1 if assets are below the quality threshold,
or 2 if security issues are found.

```bash
reagent ci
reagent ci --threshold 70
reagent ci --mode suggest
reagent ci --json
```

**Options:**

| Flag | Description |
| --- | --- |
| `--mode MODE` | Operating mode: `check`, `suggest`, or `auto-fix` (default: check) |
| `--threshold FLOAT` | Minimum quality score 0–100 (default: 60.0) |
| `--security / --no-security` | Enable or disable security scanning |
| `--repo PATH` | Repository path to evaluate (default: current directory) |
| `--json` | Output JSON instead of text |

**Exit Codes:**

| Code | Meaning |
| --- | --- |
| 0 | All checks passed |
| 1 | Assets below quality threshold |
| 2 | Security issues found |

### `reagent drift`

Detect stale, outdated, or missing assets.

```bash
reagent drift
reagent drift --repo ./my-project
reagent drift --json
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository path to check (default: current directory) |
| `--json` | Output JSON instead of text |

## Schema Management

### `reagent schema show [TYPE]`

Print the current schema for an asset type.

```bash
reagent schema show agent    # Show agent schema
reagent schema show skill    # Show skill schema
reagent schema show hook     # Show hook schema
reagent schema show          # Show all schemas
```

### `reagent schema check`

Compare local schemas against bundled defaults.

```bash
reagent schema check
```

### `reagent schema update`

Update schemas from bundled defaults.

```bash
reagent schema update
```

### `reagent schema reset`

Restore bundled default schemas.

```bash
reagent schema reset
```

## Telemetry

### `reagent profile`

Analyze Claude Code sessions and show workflow profile.

```bash
reagent profile --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to profile (default: current directory) |

### `reagent suggest`

Show actionable recommendations based on workflow profiles.

```bash
reagent suggest --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to analyze (default: current directory) |

## Instincts

### `reagent instincts list`

Show all instincts with confidence scores.

```bash
reagent instincts list
```

### `reagent instincts extract`

Extract instincts from local telemetry sessions.

```bash
reagent instincts extract
reagent instincts extract --repo ./my-project
```

### `reagent instincts prune`

Remove stale or low-confidence instincts.

```bash
reagent instincts prune
```

### `reagent instincts import`

Import instincts from a JSON file.

```bash
reagent instincts import instincts.json
```

### `reagent instincts export`

Export high-confidence instincts to a JSON file.

```bash
reagent instincts export --output instincts.json
```

## Cross-Harness Export

### `reagent export REPO`

Export existing Claude Code assets to another harness format.

```bash
reagent export . --harness cursor
reagent export . --harness all
reagent export . --agents-md
```

**Options:**

| Flag | Description |
| --- | --- |
| `--harness TEXT` | Target harness format: `cursor`, `codex`, `opencode`, or `all` |
| `--agents-md` | Generate universal AGENTS.md from existing catalog assets |
| `--output PATH` | Output directory (default: repo root) |

### `reagent harnesses`

List supported harness formats.

```bash
reagent harnesses
```
