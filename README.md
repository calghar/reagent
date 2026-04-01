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

Reagent manages the full lifecycle of AI agent assets — agents, skills, hooks, commands, and rules. It inventories your `.claude/` directories, profiles actual usage from session transcripts, generates repo-specialized assets via LLM or templates, evaluates quality over time, and exports to multiple harness formats. Autonomous loops handle the generate→evaluate→improve cycle with guardrails and human approval gates.

## Features

### Asset Management

- **Inventory & Catalog** — Scan and index agents, skills, hooks, commands, rules, and settings into a searchable JSONL catalog with content hashing
- **Smart Initialization** — Analyze repo conventions (language, framework, CI) and generate tailored starter assets with `reagent init`
- **Schema Validation** — Validate assets against JSON Schema with bundled defaults and update support

### AI-Powered Generation

- **Multi-Provider LLM** — Generate repo-aware assets using Anthropic, OpenAI, Gemini, or Ollama via `httpx` (no vendor SDKs)
- **Template Fallback** — Falls back to rule-based template generation when no API key is configured
- **Instinct System** — Learns patterns from session history to improve future generation; extract, prune, import, and export instincts
- **Cost Tracking** — Per-session and monthly LLM spend tracking with configurable budget limits

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

### Autonomous Loops

- **`loop init`** — Generate all assets for a repo from scratch
- **`loop improve`** — Regenerate below-threshold assets with evaluation feedback
- **`loop watch`** — Monitor repo for changes and auto-regenerate assets
- **Guardrails** — Hard limits on iterations (max 5), cost ($2/loop), and a kill-switch file
- **Human Approval** — All changes queue for review before deployment via `loop review` / `loop deploy`

### CI/CD Integration

- **GitHub Action** — Drop-in quality gate for CI pipelines with configurable thresholds
- **Drift Detection** — Find stale, outdated, or missing assets that have fallen behind repo changes
- **Exit Codes** — Structured exit codes: 0 = pass, 1 = quality fail, 2 = security fail

### Telemetry & Profiling

- **Session Profiling** — Parse transcripts to detect workflows, correction hotspots, and coverage gaps
- **Hooks** — Install telemetry, prompt, and agent hooks for continuous feedback
- **Actionable Suggestions** — Get recommendations based on workflow profiles, optionally auto-apply them

### Web Dashboard

- **Starlette + React UI** — View assets, evaluation trends, cost history, instincts, and loop status
- **Docker Support** — Run via `docker compose up` for a pre-configured setup

## Installation

> **Requires Python 3.13+** and [uv](https://docs.astral.sh/uv/).

### From Source (recommended — package not yet on PyPI)

```bash
git clone https://github.com/calghar/reagent.git
cd reagent

# Core CLI only
uv sync

# With dashboard UI
uv sync --extra dashboard

# With dashboard + dev tools (tests, linters)
uv sync --extra dev --extra dashboard
```

If you want the web dashboard, also build the React frontend once:

```bash
cd dashboard
npm install
npm run build
cd ..
```

Then run:

```bash
uv run reagent --help
uv run reagent dashboard   # start the web UI
```

### From PyPI (coming soon)

```bash
pip install reagent
pip install "reagent[dashboard]"   # with web dashboard
```

## Quick Start

```bash
# Initialize a repo with AI-generated assets
reagent init .

# Evaluate asset quality
reagent evaluate --repo .

# Get improvement suggestions
reagent suggest --repo .

# Run a security audit
reagent audit --repo .

# Launch the web dashboard
reagent dashboard
```

### Autonomous workflow

```bash
# Generate all assets autonomously (with guardrails)
reagent loop init --repo .

# Review what was generated
reagent loop review

# Deploy approved assets to disk
reagent loop deploy

# Continuously improve below-threshold assets
reagent loop improve --repo .
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
  monthly_budget: 10.0         # USD — enforced per calendar month
```

See the [Configuration Guide](docs/getting-started.md) for all options.

## CLI Commands

<details>
<summary><strong>Asset Management</strong></summary>

| Command | Description |
| --- | --- |
| `init <repo>` | Generate smart default assets based on repo analysis |
| `create <type> --repo <path>` | Create a new asset with LLM-powered generation |
| `regenerate <asset>` | Regenerate an existing asset using feedback and instincts |
| `suggest --repo <path>` | Actionable recommendations; add `--apply` to auto-create |
| `inventory` | Scan repos and update the asset catalog |
| `catalog` | List all cataloged assets (filter with `--type`) |
| `show <id>` | Show detailed view of an asset or suggestion |
| `baseline <root>` | Generate assets for all repos under a directory |
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
<summary><strong>Autonomous Loops</strong></summary>

| Command | Description |
| --- | --- |
| `loop init` | Generate assets from scratch for the repo |
| `loop improve` | Regenerate below-threshold existing assets |
| `loop watch` | Monitor repo for changes and auto-regenerate |
| `loop stop` | Activate the kill switch to halt any running loop |
| `loop status` | Show the most recent loop's state |
| `loop review` | Show pending assets awaiting approval |
| `loop deploy` | Write approved assets to disk |
| `loop discard` | Reject pending assets without deploying |
| `loop diff` | Show unified diff for a pending asset |
| `loop history` | Show the last 10 loop runs |

</details>

<details>
<summary><strong>Analysis &amp; Patterns</strong></summary>

| Command | Description |
| --- | --- |
| `analyze <repo>` | Detect languages, frameworks, and conventions |
| `extract-patterns` | Extract reusable patterns from the catalog |
| `apply-pattern <name>` | Apply a pattern template to a repo |
| `specialize <repo>` | Adapt global assets to repo conventions |
| `validate <file>` | Validate an asset file against the schema registry |
| `schema show <type>` | Print the current schema for an asset type |
| `schema check` | Compare local schemas against bundled defaults |
| `schema update` | Update schemas from bundled defaults |
| `schema reset` | Restore bundled default schemas |

</details>

<details>
<summary><strong>CI, Drift, Telemetry &amp; Hooks</strong></summary>

| Command | Description |
| --- | --- |
| `ci` | Evaluate quality for CI pipelines (exit 1/2 for fail) |
| `drift` | Detect stale, outdated, or missing assets |
| `profile --repo <path>` | Analyze session workflows |
| `hooks install` | Install telemetry hooks |
| `hooks uninstall` | Remove hooks |
| `hooks status` | Show hook installation status |
| `hooks install-prompt-hooks` | Install prompt hooks (quality gates) |
| `hooks install-agent-hooks` | Install agent hooks (session evaluator) |

</details>

<details>
<summary><strong>Instincts &amp; Cost</strong></summary>

| Command | Description |
| --- | --- |
| `instincts list` | List learned patterns from session history |
| `instincts extract` | Extract instincts from session transcripts |
| `instincts prune` | Remove stale or low-confidence instincts |
| `instincts import` | Import instincts from a JSON file |
| `instincts export` | Export high-confidence instincts to a file |
| `cost` | Show LLM generation costs (session and monthly) |
| `dashboard` | Launch the web dashboard |

</details>

## Autonomous Loops

The loop system runs generate→evaluate→improve cycles autonomously with hard guardrails:

```txt
┌──────────-┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Generate  │────▶│ Evaluate │────▶│ Improve  │────▶│  Queue   │
│  (LLM)    │     │ (Score)  │     │ (Regen)  │     │ (Review) │
└──────────-┘     └──────────┘     └──────────┘     └──────────┘
                                       │                 │
                                       ▼                 ▼
                                  Max 5 iters      Human approval
                                  $2 cost cap      before deploy
```

- **Kill switch**: Create `~/.reagent/loop_stop_signal` to halt any running loop immediately
- **Approval queue**: `reagent loop review` lists pending changes; `loop deploy` or `loop discard` to act

## GitHub Action

Add Reagent to your CI pipeline with the bundled GitHub Action:

```yaml
- uses: calghar/reagent@v0.1.0
  with:
    mode: check          # check | suggest | auto-fix
    threshold: 60        # minimum quality score (0-100)
    security: true       # enable security scanning
    repo: '.'            # repository path
```

**Outputs:**

- `score` — Overall quality score (0-100)
- `passed` — Whether all assets passed the threshold

**Exit codes:** `0` = pass, `1` = quality failure, `2` = security failure.

## Web Dashboard

Install dashboard dependencies and launch:

```bash
# From source (see Installation above)
uv sync --extra dashboard
cd dashboard && npm install && npm run build && cd ..
uv run reagent dashboard
```

The dashboard runs at `http://127.0.0.1:8080` and provides:

- **Asset inventory** with quality scores, letter grades, and trend indicators
- **Asset detail view** — full markdown-rendered content, evaluation history, and an action toolbar to evaluate, regenerate, or security-scan assets directly from the UI
- **Approval queue** — approve, reject, or bulk-deploy pending loop-generated assets
- **Evaluation trends** — project-aware filtering (repo dropdown, asset type chips, text search), interactive chart with asset selection grouped by project, collapsible project-grouped table with sortable columns and grade badges
- **Cost monitoring** — per-provider breakdown with demo data detection and toggle filter, sourcing clarity labels, real vs demo cost breakdown
- **Loop control** — guided trigger workflow (select loop type → select repo → review guardrails → copy CLI command), type-specific guardrails display, loop runs with type/status filters, pending approval queue, and generation records
- **Provider status** — API key detection with env var setup hints for unconfigured providers
- **Cyberpunk visual theme** — dark mode with neon accents, glow effects, gradient titles, monospace data values, and enhanced animations
- **Instinct management** — three browsing tabs (All / By Category / By Trust Tier), confidence filter chips, expandable content rows, CLI action cards with copy buttons, pagination

### Running via container

**Docker:**

```bash
reagent dashboard --docker
# or directly:
docker compose up --build
```

**Podman:**

```bash
reagent dashboard --podman
# or directly:
podman compose up --build
```

> **Note:** Set `REAGENT_REPOS_PATH` in your environment (or `.env` file) to mount your local repos into the container. Defaults to `~/repos`.

See [Dashboard documentation](docs/dashboard.md) for full details including API endpoints and development setup.

## How It Works

Reagent follows a pipeline architecture:

1. **Scan** — Parse `.claude/` directories to discover agents, skills, hooks, commands, rules, and settings
2. **Catalog** — Index assets in a JSONL catalog with content hashing and metadata
3. **Profile** — Parse session transcripts to understand how assets are actually used
4. **Analyze** — Detect repo languages, frameworks, and conventions for context-aware operations
5. **Extract** — Cluster similar assets and generate reusable pattern templates; distill instincts from session history
6. **Create** — Generate new assets via LLM (primary) with pattern and template fallbacks; validate against schema
7. **Evaluate** — Score asset quality from telemetry, detect regressions, run A/B tests; feed insights back into generation

## Documentation

Full documentation is available in the **[docs/](docs/)** directory.

| Guide | Description |
| --- | --- |
| [Getting Started](docs/getting-started.md) | Installation, setup, and first steps |
| [CLI Reference](docs/cli-reference.md) | Full command documentation with examples |
| [Asset Creation](docs/asset-creation.md) | Creating and generating Claude Code assets |
| [Security Scanning](docs/security-scanning.md) | Security features, trust model, and scanning |
| [Evaluation](docs/evaluation.md) | Quality measurement and A/B testing |
| [Comparison](docs/comparison.md) | How Reagent compares to related projects |

## Development

```bash
git clone https://github.com/calghar/reagent.git
cd reagent
uv sync --extra dev --extra dashboard
```

Build the frontend (required for the dashboard):

```bash
cd dashboard
npm install
npm run build
cd ..
```

> **Note:** The frontend project lives in `dashboard/`. Always run `npm` commands from that directory — there is no `package.json` at the repo root.

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
