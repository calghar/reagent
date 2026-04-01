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

### `reagent init REPO`

Generate smart default assets based on repo analysis.

```bash
reagent init ./my-project
```

Analyzes the repo and proposes starter agents, skills, and rules tailored to the detected stack. Prompts for confirmation before writing.

### `reagent baseline ROOT`

Generate baseline `.claude` assets for all repos under a root directory.

```bash
reagent baseline ~/Development
reagent baseline ~/Development --max-depth 3
reagent baseline ~/Development --dry-run
```

Discovers repositories by looking for project markers (`.git`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Gemfile`, `Package.swift`) and generates smart default assets for each.

**Options:**

| Flag | Description |
| --- | --- |
| `--max-depth INT` | Max directory depth to search for repos (default: 2) |
| `--dry-run` | Show what would be generated without writing files |

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

## Creation

### `reagent create TYPE`

Create a new Claude Code asset with repo-aware generation.

```bash
reagent create agent --repo . --name code-reviewer
reagent create skill --repo . --from ci-deploy
reagent create hook --repo . --from-outline outline.md
reagent create command --interactive
```

**Arguments:**

| Argument | Values |
| --- | --- |
| `TYPE` | `agent`, `skill`, `hook`, `command`, `rule` |

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Target repository (default: current directory) |
| `--name NAME` | Asset name |
| `--from PATTERN` | Pattern name to use as template |
| `--from-outline PATH` | Outline file (use `-` for stdin) |
| `--interactive` | Interactive field-by-field mode |

### `reagent regenerate PATH`

Regenerate an existing asset using evaluation feedback and instincts.

```bash
reagent regenerate .claude/agents/code-reviewer.md
reagent regenerate .claude/agents/code-reviewer.md --repo .
```

**Options:**

| Flag | Description |
| --- | --- |
| `--repo PATH` | Repository path (default: current directory) |

### `reagent specialize REPO`

Apply global assets with repo-specific adaptation.

```bash
reagent specialize ./my-project
```

Reads global patterns and adapts them to the repo's languages, frameworks, and conventions.

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

### `reagent dashboard`

Start the Reagent web dashboard.

```bash
reagent dashboard
reagent dashboard --port 8080
reagent dashboard --no-browser
```

Opens a browser at `http://localhost:8080` showing asset health, evaluation trends,
generation costs, provider status, and loop control.

**Options:**

| Flag | Description |
| --- | --- |
| `--port INT` | Port to listen on (default: 8080) |
| `--host TEXT` | Host to bind to (default: 0.0.0.0) |
| `--docker` | Run via Docker Compose |
| `--no-browser` | Don't open browser automatically |

## Autonomous Loops

### `reagent loop init`

Run the init loop: generate assets from scratch for the repo.

```bash
reagent loop init
reagent loop init --threshold 85 --max-iterations 3
reagent loop init --no-approval   # Auto-deploy without review
```

**Options:**

| Flag | Description |
| --- | --- |
| `--max-iterations N` | Maximum loop iterations (default: 5) |
| `--max-cost FLOAT` | Maximum spend in USD (default: 2.0) |
| `--target FLOAT` | Target quality score 0–100 (default: 80.0) |
| `--no-approval` | Skip human review step (auto-deploy) |
| `--repo PATH` | Repository path (default: current directory) |

### `reagent loop improve`

Run the improve loop: regenerate below-threshold existing assets.

```bash
reagent loop improve
reagent loop improve --threshold 70 --max-iterations 3
```

**Options:**

| Flag | Description |
| --- | --- |
| `--threshold FLOAT` | Score threshold below which assets are regenerated (default: 80.0) |
| `--max-iterations N` | Maximum loop iterations (default: 5) |
| `--repo PATH` | Repository path (default: current directory) |

### `reagent loop watch`

Run the watch loop: monitor repo for changes and regenerate assets.

```bash
reagent loop watch
reagent loop watch --interval 60
```

**Options:**

| Flag | Description |
| --- | --- |
| `--interval FLOAT` | Poll interval in seconds (default: 30.0) |
| `--repo PATH` | Repository path (default: current directory) |

### `reagent loop stop`

Activate the kill switch to stop any running loop.

```bash
reagent loop stop
```

### `reagent loop status`

Show the most recent loop's state.

```bash
reagent loop status
```

### `reagent loop review`

Show pending assets awaiting approval.

```bash
reagent loop review
```

### `reagent loop deploy`

Write approved asset content to disk.

```bash
reagent loop deploy
```

### `reagent loop discard`

Reject pending assets without writing to disk.

```bash
reagent loop discard
```

### `reagent loop diff`

Show unified diff for a pending asset vs its previous version.

```bash
reagent loop diff
```

### `reagent loop history`

Show the last 10 loop runs.

```bash
reagent loop history
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

## Telemetry Hooks

### `reagent hooks install`

Install Reagent telemetry hooks into `~/.claude/settings.json`.

```bash
reagent hooks install
```

### `reagent hooks uninstall`

Remove Reagent hooks from `~/.claude/settings.json`.

```bash
reagent hooks uninstall
```

### `reagent hooks status`

Show status of Reagent telemetry hooks.

```bash
reagent hooks status
```

### `reagent hooks install-prompt-hooks`

Install prompt hooks for quality gates (convention checking, review summaries).

```bash
reagent hooks install-prompt-hooks
```

### `reagent hooks install-agent-hooks`

Install agent hooks for automated session evaluation.

```bash
reagent hooks install-agent-hooks
```

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
