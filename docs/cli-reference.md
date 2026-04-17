# CLI Reference

## Global Options

All commands accept these flags:

| Flag | Description |
| --- | --- |
| `-v`, `--verbose` | Enable verbose (DEBUG-level) logging to stderr |
| `--log-file PATH` | Log file path (default: `~/.agentguard/agentguard.log`) |

## Inventory

### `agentguard inventory`

Scan for Claude Code assets and update the catalog.

```bash
agentguard inventory                    # Scan all configured roots
agentguard inventory --repo ./my-repo   # Scan a single repository
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Scan a single repository instead of all configured roots |

### `agentguard catalog`

List all cataloged assets.

```bash
agentguard catalog
agentguard catalog --type agent
agentguard catalog --repo my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--type TYPE` | Filter by asset type (agent, skill, hook, command, rule, settings, claude-md, memory) |
| `--repo NAME` | Filter by repository name |

### `agentguard show ASSET_ID`

Show detailed view of an asset or suggestion.

```bash
agentguard show my-project:agent:reviewer
agentguard show --suggestion 3
```

**Options:**

| Flag | Description |
| --- | --- |
| `--suggestion` | Interpret the argument as a suggestion number |

## Analysis

### `agentguard analyze REPO`

Analyze a repository for language, framework, and conventions.

```bash
agentguard analyze ./my-project
```

Outputs detected languages, frameworks, architecture style, test/lint configuration, CI setup, and an asset audit.

### `agentguard extract-patterns`

Scan all cataloged assets and extract reusable patterns.

```bash
agentguard extract-patterns
```

Clusters similar assets and generates parameterized templates for reuse across repositories.

### `agentguard apply-pattern PATTERN_NAME`

Apply a pattern template to a repository.

```bash
agentguard apply-pattern ci-deploy --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Target repository (default: current directory) |

### `agentguard validate PATH`

Validate an asset file against the schema registry.

```bash
agentguard validate ./my-project/.claude/agents/reviewer.md
```

Checks both portable Agent Skills fields and Claude Code vendor extension fields.

## Security

### `agentguard scan PATH`

Run the security scanner on a file or directory.

```bash
agentguard scan ./agent.md
agentguard scan ./my-project/.claude
```

Reports findings by severity (critical, high, medium) with rule IDs, line numbers, and descriptions.

### `agentguard audit`

Run a full security audit on a repository's `.claude/` directory.

```bash
agentguard audit --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to audit (default: current directory) |

### `agentguard import SOURCE`

Import a Claude Code asset from a local path, git URL, or gist.

```bash
agentguard import ./shared-agent.md
agentguard import https://gist.github.com/user/abc123
agentguard import --target-repo ./my-project https://github.com/user/repo
```

Runs security scan, displays findings, and requires explicit approval before installation.

**Options:**

| Flag | Description |
| --- | --- |
| `--target-repo PATH` | Target repository for installation (default: current directory) |

### `agentguard trust show ASSET_ID`

Show trust level and history for an asset.

```bash
agentguard trust show my-project:agent:reviewer
```

### `agentguard trust promote ASSET_ID`

Promote an asset to a higher trust level.

```bash
agentguard trust promote my-project:agent:reviewer --level 2 --reason "Reviewed and approved"
```

**Options:**

| Flag | Description |
| --- | --- |
| `--level INT` | Target trust level (2 = REVIEWED, 3 = VERIFIED) |
| `--reason TEXT` | Justification for promotion |

### `agentguard integrity check`

Verify all tracked asset hashes against the catalog.

```bash
agentguard integrity check
```

### `agentguard integrity report`

Show tampered or modified assets since last scan.

```bash
agentguard integrity report
```

### `agentguard history ASSET_ID`

Show snapshot timeline for an asset.

```bash
agentguard history my-project:agent:reviewer
```

### `agentguard rollback ASSET_ID`

Restore an asset from a previous snapshot.

```bash
agentguard rollback my-project:agent:reviewer --snapshot 3
```

**Options:**

| Flag | Description |
| --- | --- |
| `--snapshot INT` | Snapshot ID to restore |

## Evaluation

### `agentguard evaluate`

Compute quality scores for all assets in a repository.

```bash
agentguard evaluate --repo ./my-project
```

Reports per-asset quality scores with metrics: invocation rate, correction rate, turn efficiency, staleness, coverage, and security score.

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to evaluate (default: current directory) |

### `agentguard check-regression SESSION_ID`

Check a session for quality regressions against the baseline.

```bash
agentguard check-regression abc123 --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository path (default: current directory) |

### `agentguard variant ASSET_ID`

Create an A/B test variant of an asset.

```bash
agentguard variant my-project:agent:reviewer --name v2 --change "Reduced verbosity"
```

**Options:**

| Flag | Description |
| --- | --- |
| `--name TEXT` | Variant name |
| `--change TEXT` | Description of the change |

### `agentguard compare ASSET_A ASSET_B`

Compare quality metrics between two assets or variants.

```bash
agentguard compare my-project:agent:reviewer my-project:agent:reviewer-v2
```

### `agentguard promote VARIANT_ID`

Promote a variant to replace its original asset.

```bash
agentguard promote my-project:agent:reviewer-v2
```

### `agentguard rollback-best ASSET_ID`

Rollback an asset to its historically best-quality version.

```bash
agentguard rollback-best my-project:agent:reviewer
```

## CI Integration

### `agentguard ci`

Evaluate asset quality for CI pipelines.

Exits with code 0 if all checks pass, 1 if assets are below the quality threshold,
or 2 if security issues are found.

```bash
agentguard ci
agentguard ci --threshold 70
agentguard ci --mode suggest
agentguard ci --json
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

### `agentguard drift`

Detect stale, outdated, or missing assets.

```bash
agentguard drift
agentguard drift --repo ./my-project
agentguard drift --json
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository path to check (default: current directory) |
| `--json` | Output JSON instead of text |

## Schema Management

### `agentguard schema show [TYPE]`

Print the current schema for an asset type.

```bash
agentguard schema show agent    # Show agent schema
agentguard schema show skill    # Show skill schema
agentguard schema show hook     # Show hook schema
agentguard schema show          # Show all schemas
```

### `agentguard schema check`

Compare local schemas against bundled defaults.

```bash
agentguard schema check
```

### `agentguard schema update`

Update schemas from bundled defaults.

```bash
agentguard schema update
```

### `agentguard schema reset`

Restore bundled default schemas.

```bash
agentguard schema reset
```

## Telemetry

### `agentguard profile`

Analyze Claude Code sessions and show workflow profile.

```bash
agentguard profile --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to profile (default: current directory) |

### `agentguard suggest`

Show actionable recommendations based on workflow profiles.

```bash
agentguard suggest --repo ./my-project
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository to analyze (default: current directory) |

## Instincts

### `agentguard instincts list`

Show all instincts with confidence scores.

```bash
agentguard instincts list
```

### `agentguard instincts extract`

Extract instincts from local telemetry sessions.

```bash
agentguard instincts extract
agentguard instincts extract --repo ./my-project
```

### `agentguard instincts prune`

Remove stale or low-confidence instincts.

```bash
agentguard instincts prune
```

### `agentguard instincts import`

Import instincts from a JSON file.

```bash
agentguard instincts import instincts.json
```

### `agentguard instincts export`

Export high-confidence instincts to a JSON file.

```bash
agentguard instincts export --output instincts.json
```

## Cross-Harness Export

### `agentguard export REPO`

Export existing Claude Code assets to another harness format.

```bash
agentguard export . --harness cursor
agentguard export . --harness all
agentguard export . --agents-md
```

**Options:**

| Flag | Description |
| --- | --- |
| `--harness TEXT` | Target harness format: `cursor`, `codex`, `opencode`, or `all` |
| `--agents-md` | Generate universal AGENTS.md from existing catalog assets |
| `--output PATH` | Output directory (default: repo root) |

### `agentguard harnesses`

List supported harness formats.

```bash
agentguard harnesses
```
