<!--markdownlint-disable MD033 -->
<h1 align="center">Reagent</h1>

<p align="center">
  <strong>Automated asset synthesis and optimization engine for AI agent harnesses.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.13+-blue.svg" alt="Python 3.13+"></a>
  <a href="docs/"><img src="https://img.shields.io/badge/docs-available-blue.svg" alt="Docs"></a>
</p>

---

Reagent manages the full lifecycle of AI agent assets — agents, skills, hooks, commands, and rules. It inventories your `.claude/` directories, profiles actual usage from session transcripts, evaluates quality over time, detects security issues, and exports to multiple harness formats.

## Features

### Asset Management

- **Inventory & Catalog** — Scan and index agents, skills, hooks, commands, rules, and settings into a searchable JSONL catalog with content hashing
- **Schema Validation** — Validate assets against JSON Schema with bundled defaults and update support

### AI-Powered Features

- **Multi-Provider LLM** — Leverage Anthropic, OpenAI, Gemini, or Ollama via `httpx` (no vendor SDKs) for intelligent suggestions and analysis
- **Template Fallback** — Falls back to rule-based template generation when no API key is configured
- **Instinct System** — Learns patterns from session history to improve future recommendations; extract, prune, import, and export instincts

### Multi-Harness Support

- **Cross-Harness Export** — Generate assets for **Claude Code**, **Cursor**, **Codex**, and **OpenCode** from a single canonical source
- **Auto-Detection** — Automatically detect which harness a repo uses based on directory structure
- **AGENTS.md Generation** — Produce a universal AGENTS.md overview for any repo

### Quality & Evaluation

- **Quality Scoring** — Per-asset quality metrics with configurable thresholds
- **Regression Detection** — Check sessions for quality regressions against baselines
- **A/B Testing** — Create variants, compare metrics, and promote winners
- **Pattern Extraction** — Cluster similar assets and generate reusable parameterized templates

### Security

- **Static Analysis** — 20+ security rules for prompt injection, exfiltration, and unsafe patterns
- **AgentShield Integration** — Optional `npx agentshield` scanning for deeper analysis
- **Trust Management** — 4-level trust model with promotion and integrity verification
- **Import Gates** — Security scanning on imported assets from URLs, gists, or local paths
- **Snapshot & Rollback** — Track asset history and rollback to any previous version

### CI/CD Integration

- **CI Pipeline** — Run `reagent ci` as a quality gate in any CI system with configurable thresholds
- **Drift Detection** — Find stale, outdated, or missing assets that have fallen behind repo changes
- **Exit Codes** — Structured exit codes: 0 = pass, 1 = quality fail, 2 = security fail

### Telemetry & Profiling

- **Session Profiling** — Parse transcripts to detect workflows, correction hotspots, and coverage gaps
- **Actionable Suggestions** — Get recommendations based on workflow profiles, optionally auto-apply them

## Installation

> **Requires Python 3.13+** and [uv](https://docs.astral.sh/uv/).

### From Source (recommended — package not yet on PyPI)

```bash
git clone https://github.com/calghar/reagent.git
cd reagent

# Core CLI only
uv sync

# With dev tools (tests, linters)
uv sync --extra dev
```

Then run:

```bash
uv run reagent --help
```

### From PyPI (coming soon)

```bash
pip install reagent
```

## Quick Start

```bash
# Scan a repo and build the asset catalog
reagent inventory --repo .

# Evaluate asset quality
reagent evaluate --repo .

# Get improvement suggestions
reagent suggest --repo .

# Run a security audit
reagent audit --repo .

# Check for stale or missing assets
reagent drift --repo .
```

## Configuration

### LLM Provider Setup

Set an API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=..   # Anthropic (default)
export OPENAI_API_KEY=s...    # OpenAI
export GOOGLE_API_KEY=...     # Gemini
```

Additional environment variables: `REAGENT_LLM_PROVIDER`, `REAGENT_LLM_MODEL`, `REAGENT_LLM_ENABLED`.

Without a key configured, Reagent falls back to rule-based template generation — no LLM required.

### Config File

Reagent reads `~/.reagent/config.yaml`:

```yaml
llm:
  provider: anthropic          # anthropic | openai | google | ollama
  model: claude-sonnet-4-20250514
```

See the [Configuration Guide](docs/getting-started.md) for all options.

## CLI Commands

<details>
<summary><strong>Asset Management</strong></summary>

| Command | Description |
| --- | --- |
| `suggest --repo <path>` | Actionable recommendations; add `--apply` to auto-create |
| `inventory` | Scan repos and update the asset catalog |
| `catalog` | List all cataloged assets (filter with `--type`) |
| `show <id>` | Show detailed view of an asset or suggestion |
| `export <repo>` | Export assets to another harness format |
| `harnesses` | List supported harness formats |

</details>

<details>
<summary><strong>Evaluation &amp; Quality</strong></summary>

| Command | Description |
| --- | --- |
| `evaluate --repo <path>` | Compute quality scores for all assets |
| `check-regression <session>` | Check a session for quality regressions |
| `compare <a> <b>` | Compare quality metrics between two assets |
| `variant <asset-id>` | Create an A/B test variant |
| `promote <variant-id>` | Promote a winning variant |
| `rollback-best <asset-id>` | Rollback to historically best-quality version |

</details>

<details>
<summary><strong>Security</strong></summary>

| Command | Description |
| --- | --- |
| `scan <path>` | Run security scanner on a file or directory |
| `audit --repo <path>` | Full security audit of a repo's `.claude/` |
| `import <source>` | Import an asset with security gates |
| `trust show <id>` | Show trust level and history |
| `trust promote <id>` | Promote an asset to a higher trust level |
| `integrity check` | Verify all tracked asset hashes |
| `integrity report` | Show tampered/modified assets since last scan |
| `history <id>` | Show snapshot timeline for an asset |
| `rollback <id> <snapshot>` | Restore an asset from a previous snapshot |

</details>

<details>
<summary><strong>Analysis &amp; Patterns</strong></summary>

| Command | Description |
| --- | --- |
| `analyze <repo>` | Detect languages, frameworks, and conventions |
| `extract-patterns` | Extract reusable patterns from the catalog |
| `apply-pattern <name>` | Apply a pattern template to a repo |
| `validate <file>` | Validate an asset file against the schema registry |
| `schema show <type>` | Print the current schema for an asset type |
| `schema check` | Compare local schemas against bundled defaults |
| `schema update` | Update schemas from bundled defaults |
| `schema reset` | Restore bundled default schemas |

</details>

<details>
<summary><strong>CI, Drift &amp; Telemetry</strong></summary>

| Command | Description |
| --- | --- |
| `ci` | Evaluate quality for CI pipelines (exit 1/2 for fail) |
| `drift` | Detect stale, outdated, or missing assets |
| `profile --repo <path>` | Analyze session workflows |

</details>

<details>
<summary><strong>Instincts</strong></summary>

| Command | Description |
| --- | --- |
| `instincts list` | List learned patterns from session history |
| `instincts extract` | Extract instincts from session transcripts |
| `instincts prune` | Remove stale or low-confidence instincts |
| `instincts import` | Import instincts from a JSON file |
| `instincts export` | Export high-confidence instincts to a file |

</details>

## CI Integration

Run Reagent as a quality gate in any CI system:

```bash
reagent ci --threshold 70 --mode check --security
```

**Exit codes:** `0` = pass, `1` = quality failure, `2` = security failure.

See the [CI Integration Guide](docs/ci-integration.md) for detailed setup instructions with GitLab CI, Jenkins, CircleCI, and other providers.

## How It Works

Reagent follows a pipeline architecture:

1. **Scan** — Parse `.claude/` directories to discover agents, skills, hooks, commands, rules, and settings
2. **Catalog** — Index assets in a JSONL catalog with content hashing and metadata
3. **Profile** — Parse session transcripts to understand how assets are actually used
4. **Analyze** — Detect repo languages, frameworks, and conventions for context-aware operations
5. **Extract** — Cluster similar assets and generate reusable pattern templates; distill instincts from session history
6. **Evaluate** — Score asset quality from telemetry, detect regressions, run A/B tests; surface actionable suggestions

## Documentation

Full documentation is available in the **[docs/](docs/)** directory.

| Guide | Description |
| --- | --- |
| [Getting Started](docs/getting-started.md) | Installation, setup, and first steps |
| [CLI Reference](docs/cli-reference.md) | Full command documentation with examples |
| [Configuration](docs/configuration.md) | Full configuration reference and environment variables |
| [Security Scanning](docs/security-scanning.md) | Security features, trust model, and scanning |
| [Evaluation](docs/evaluation.md) | Quality measurement and A/B testing |
| [CI Integration](docs/ci-integration.md) | Running Reagent in CI pipelines |
| [Comparison](docs/comparison.md) | How Reagent compares to related projects |

## Development

```bash
git clone https://github.com/calghar/reagent.git
cd reagent
uv sync --extra dev
```

Run the test suite and linters:

```bash
uv run pytest                    # tests
uv run ruff check src/ tests/    # linting
uv run ruff format --check src/  # formatting
uv run mypy src/                 # type checking
```

Pre-commit hooks are available:

```bash
uv run pre-commit install
```

## License

MIT — see [LICENSE](LICENSE).
