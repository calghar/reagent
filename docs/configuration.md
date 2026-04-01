# Configuration Reference

Reagent stores its configuration at `~/.reagent/config.yaml`. If this file does not exist, all settings fall back to sensible defaults — no configuration is required to get started.

## Config File Location

```
~/.reagent/
├── config.yaml          # Main configuration
├── catalog.jsonl         # Asset catalog
├── events.jsonl          # Telemetry event log
├── reagent.db            # SQLite database (evaluations, loops, costs)
├── reagent.log           # Application log
├── patterns/             # Extracted reusable patterns
├── workflows/            # Repo analysis profiles
└── schemas/              # Asset validation schemas
```

Create the config file manually or let Reagent generate defaults on first run:

```bash
mkdir -p ~/.reagent
touch ~/.reagent/config.yaml
```

## Full Configuration Reference

### `scan` — Repository Discovery

Controls how `reagent inventory` discovers repositories and `.claude/` directories.

```yaml
scan:
  roots:
    - ~/Development            # Directories to scan for repos
  exclude_patterns:
    - node_modules
    - .git
    - __pycache__
    - venv
    - .venv
  max_depth: 5                 # Max directory depth to traverse
```

| Field | Type | Default | Description |
|---|---|---|---|
| `roots` | list of paths | `[~/Development]` | Top-level directories to scan for repositories |
| `exclude_patterns` | list of strings | `[node_modules, .git, __pycache__, venv, .venv]` | Directory names to skip during scan |
| `max_depth` | int | `5` | Maximum directory depth to traverse |

### `catalog` — Asset Catalog

Controls where the asset catalog is stored and how it refreshes.

```yaml
catalog:
  path: ~/.reagent/catalog.jsonl
  auto_refresh: true
  refresh_interval: 3600       # Seconds between auto-refreshes
```

| Field | Type | Default | Description |
|---|---|---|---|
| `path` | path | `~/.reagent/catalog.jsonl` | Catalog file location |
| `auto_refresh` | bool | `true` | Automatically refresh catalog on access |
| `refresh_interval` | int | `3600` | Minimum seconds between refreshes |

### `telemetry` — Session Tracking

Controls Claude Code session event collection used for evaluation and instinct extraction.

```yaml
telemetry:
  enabled: true
  event_store: ~/.reagent/events.jsonl
  hash_file_paths: false
  exclude_content: false
  retention_days: 90
```

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable telemetry event collection |
| `event_store` | path | `~/.reagent/events.jsonl` | Event log file location |
| `hash_file_paths` | bool | `false` | Hash file paths in events for privacy |
| `exclude_content` | bool | `false` | Exclude file content from events |
| `retention_days` | int | `90` | Days to retain events before pruning |

### `versioning` — Asset Snapshots

Controls the content-addressed snapshot store for asset version history.

```yaml
versioning:
  strategy: auto
  snapshot_retention: 90       # Days to keep old snapshots
  max_snapshots_per_asset: 50
```

| Field | Type | Default | Description |
|---|---|---|---|
| `strategy` | string | `"auto"` | Snapshot trigger strategy |
| `snapshot_retention` | int | `90` | Days to retain snapshots |
| `max_snapshots_per_asset` | int | `50` | Maximum snapshots per asset |

### `security` — Security Scanning

Controls the static analysis scanner and import gate behavior.

```yaml
security:
  rules_path: null             # Custom rules file (null = bundled rules)
  auto_scan: true              # Scan on import/create
  block_on_critical: true      # Block operations on critical findings
```

| Field | Type | Default | Description |
|---|---|---|---|
| `rules_path` | path or null | `null` | Path to custom security rules file; `null` uses bundled rules |
| `auto_scan` | bool | `true` | Automatically scan assets on import and creation |
| `block_on_critical` | bool | `true` | Block operations when critical findings are detected |

### `code_intel` — Code Intelligence

Controls integration with the GitNexus MCP server for enhanced code analysis.

```yaml
code_intel:
  enabled: false
  gitnexus_command: "npx -y gitnexus@latest mcp"
  timeout: 30
  fallback_on_error: true
```

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable GitNexus code intelligence integration |
| `gitnexus_command` | string | `"npx -y gitnexus@latest mcp"` | Command to start the GitNexus MCP server |
| `timeout` | int | `30` | Timeout in seconds for code intelligence queries |
| `fallback_on_error` | bool | `true` | Fall back to basic analysis when GitNexus fails |

!!! note
    Requires the `code-intel` extra: `pip install reagent[code-intel]`

### `harness` — Cross-Harness Generation

Controls which AI harness formats Reagent targets when generating assets.

```yaml
harness:
  default: claude-code         # Primary harness format
  generate:
    - claude-code              # Generate assets for these harnesses
```

| Field | Type | Default | Description |
|---|---|---|---|
| `default` | string | `"claude-code"` | Default harness format for new assets |
| `generate` | list of strings | `["claude-code"]` | Harness formats to generate simultaneously |

Supported values: `claude-code`, `cursor`, `codex`, `opencode`, `agents-md`

### `log` — Logging

Controls application logging output.

```yaml
log:
  level: WARNING
  file: ~/.reagent/reagent.log
  max_bytes: 5000000           # 5 MB
  backup_count: 3
```

| Field | Type | Default | Description |
|---|---|---|---|
| `level` | string | `"WARNING"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `file` | path | `~/.reagent/reagent.log` | Log file location |
| `max_bytes` | int | `5000000` | Maximum log file size before rotation (bytes) |
| `backup_count` | int | `3` | Number of rotated log backups to keep |

### `llm` — LLM Provider

Controls AI-powered generation via LLM providers.

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  temperature: 0.3
  max_output_tokens: 4096
  max_prompt_tokens: 2000
  monthly_budget: 10.0
  routing: cost
  critic_model: claude-haiku-4-20250414
  features:
    enabled: true
    use_critic: false
    use_instincts: false
    use_cache: true
  fallback:
    - provider: openai
      model: gpt-4o-mini
  api_keys:
    anthropic: sk-ant-...      # Optional: keys can also be set via env vars
    openai: sk-...
```

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `"anthropic"` | Primary LLM provider |
| `model` | string | `"claude-sonnet-4-20250514"` | Primary model name |
| `temperature` | float | `0.3` | Generation temperature (0.0–1.0) |
| `max_output_tokens` | int | `4096` | Maximum tokens in LLM response |
| `max_prompt_tokens` | int | `2000` | Maximum tokens in the prompt |
| `monthly_budget` | float | `10.0` | Monthly spending cap in USD |
| `routing` | string | `"cost"` | Routing strategy: `cost`, `latency`, or `fixed` |
| `critic_model` | string | `"claude-haiku-4-20250414"` | Model used for critic review pass |
| `fallback` | list | `[]` | Ordered fallback providers (each with `provider` and `model`) |
| `api_keys` | dict | `{}` | API keys by provider name (env vars take precedence) |

#### `llm.features` — Feature Flags

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Enable LLM-powered generation (false = templates only) |
| `use_critic` | bool | `false` | Run a second model pass to review output quality |
| `use_instincts` | bool | `false` | Inject learned patterns from session history into prompts |
| `use_cache` | bool | `true` | Cache LLM responses to avoid duplicate calls |

#### Supported Providers and Models

| Provider | Models | Pricing (input/output per 1M tokens) |
|---|---|---|
| `anthropic` | `claude-sonnet-4-20250514`, `claude-haiku-4-20250414` | $3.00/$15.00, $0.25/$1.25 |
| `openai` | `gpt-4o`, `gpt-4o-mini` | $2.50/$10.00, $0.15/$0.60 |
| `google` | `gemini-2.5-pro`, `gemini-2.0-flash` | $1.25/$10.00, $0.10/$0.40 |
| `ollama` | `llama3`, `llama3:70b` | Free (local) |

## Environment Variables

Environment variables override config file values. Set them in your shell profile, `.env` file, or CI secrets.

### LLM Configuration

| Variable | Description | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-api03-...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `GOOGLE_API_KEY` | Google Gemini API key | `AIza...` |
| `REAGENT_LLM_PROVIDER` | Override LLM provider | `anthropic`, `openai`, `google`, `ollama` |
| `REAGENT_LLM_MODEL` | Override LLM model | `claude-sonnet-4-20250514` |
| `REAGENT_LLM_ENABLED` | Disable LLM generation | `0` or `false` to disable |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` (default) |

### Dashboard & API

| Variable | Description | Example |
|---|---|---|
| `REAGENT_DB_PATH` | SQLite database path override | `/path/to/reagent.db` |
| `REAGENT_CORS_ORIGINS` | Comma-separated CORS allowed origins | `http://localhost:5173,http://localhost:3000` |

### CI

| Variable | Description | Example |
|---|---|---|
| `GITHUB_ACTIONS` | Auto-detected in GitHub Actions (enables CI formatting) | `true` |

### Provider Auto-Detection

Reagent auto-detects the LLM provider based on which API key environment variables are set. If multiple keys are present, the config file `llm.provider` setting (or `REAGENT_LLM_PROVIDER`) determines which is used. The priority:

1. `REAGENT_LLM_PROVIDER` environment variable
2. `llm.provider` in config.yaml
3. First available key: Anthropic → OpenAI → Google → Ollama

## Example Configurations

### Minimal (Anthropic, defaults for everything)

```yaml
llm:
  provider: anthropic
```

Then set the API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

### Budget-Conscious with Fallback

```yaml
llm:
  provider: google
  model: gemini-2.0-flash
  monthly_budget: 5.0
  features:
    use_cache: true
  fallback:
    - provider: ollama
      model: llama3
```

### Local-Only (No API Keys Needed)

```yaml
llm:
  provider: ollama
  model: llama3
```

Requires [Ollama](https://ollama.ai) running locally.

### Multi-Harness Team Setup

```yaml
harness:
  default: claude-code
  generate:
    - claude-code
    - cursor
    - codex

scan:
  roots:
    - ~/work/team-repos

security:
  block_on_critical: true
  auto_scan: true
```

### CI Pipeline Configuration

```yaml
llm:
  provider: anthropic
  monthly_budget: 20.0
  features:
    enabled: true
    use_critic: true

security:
  block_on_critical: true
```

### `tuning` — Scoring and Threshold Constants

Fine-tune scoring algorithms, budget thresholds, router timers, API pagination, and cache settings. All values have sensible defaults — you only need to override the ones you want to change.

```yaml
tuning:
  instinct:
    category_match_boost: 1.5
    recency_half_life_days: 180.0
    name_overlap_factor: 0.1
    confidence_increment: 0.1
    confidence_divisor: 8
    confidence_cap: 0.8
    correction_rate_threshold: 0.15
    quality_score_threshold: 70
    confidence_reward: 0.05
    confidence_penalty: 0.1
    min_use_count_for_promotion: 5
    default_top_k: 5
    trust_tier_weights:
      managed: 0.8
      workspace: 0.6
  budget:
    warning_ratio: 0.8
    exceeded_ratio: 1.0
  evaluation:
    max_invocations_per_week: 5.0
    max_turn_efficiency: 19.0
    staleness_window_days: 90.0
  router:
    health_check_interval_seconds: 60
    circuit_breaker_threshold: 3
    circuit_breaker_recovery_seconds: 300
  api:
    default_page_size: 20
    max_page_size: 200
    default_eval_limit: 500
    max_loop_results: 100
  cache:
    default_max_age_days: 7
```

#### `tuning.instinct` — Instinct Scoring

| Field | Type | Default | Description |
|---|---|---|---|
| `category_match_boost` | float | `1.5` | Score multiplier when instinct category matches asset type |
| `recency_half_life_days` | float | `180.0` | Days until recency weight halves |
| `name_overlap_factor` | float | `0.1` | Per-word overlap boost for name matching |
| `confidence_increment` | float | `0.1` | Confidence increase on duplicate instinct |
| `confidence_divisor` | int | `8` | Divisor for confidence from correction counts |
| `confidence_cap` | float | `0.8` | Maximum auto-assigned confidence |
| `correction_rate_threshold` | float | `0.15` | Minimum correction rate to generate a rule instinct |
| `quality_score_threshold` | int | `70` | Score above which instincts receive a confidence reward |
| `confidence_reward` | float | `0.05` | Confidence boost from positive evaluation |
| `confidence_penalty` | float | `0.1` | Confidence reduction from poor evaluation |
| `min_use_count_for_promotion` | int | `5` | Minimum uses before workspace→managed promotion |
| `default_top_k` | int | `5` | Default number of instincts returned by relevance query |
| `trust_tier_weights` | dict | `{managed: 0.8, workspace: 0.6}` | Score multipliers by trust tier |

#### `tuning.budget` — Budget Enforcement

| Field | Type | Default | Description |
|---|---|---|---|
| `warning_ratio` | float | `0.8` | Budget usage ratio that triggers a warning |
| `exceeded_ratio` | float | `1.0` | Budget usage ratio that triggers exceeded status |

#### `tuning.evaluation` — Quality Evaluation

| Field | Type | Default | Description |
|---|---|---|---|
| `max_invocations_per_week` | float | `5.0` | Invocation rate that normalizes to 100% |
| `max_turn_efficiency` | float | `19.0` | Turns value that normalizes to 0% efficiency |
| `staleness_window_days` | float | `90.0` | Days of inactivity that normalizes to 0% freshness |

#### `tuning.router` — Provider Router

| Field | Type | Default | Description |
|---|---|---|---|
| `health_check_interval_seconds` | int | `60` | Seconds between provider health checks |
| `circuit_breaker_threshold` | int | `3` | Consecutive failures before opening circuit |
| `circuit_breaker_recovery_seconds` | int | `300` | Seconds to wait before retrying an open circuit |

#### `tuning.api` — API Pagination

| Field | Type | Default | Description |
|---|---|---|---|
| `default_page_size` | int | `20` | Default items per page for paginated endpoints |
| `max_page_size` | int | `200` | Maximum allowed page size |
| `default_eval_limit` | int | `500` | Default limit for evaluation queries |
| `max_loop_results` | int | `100` | Maximum loop/generation results returned |

#### `tuning.cache` — Generation Cache

| Field | Type | Default | Description |
|---|---|---|---|
| `default_max_age_days` | int | `7` | Days before cached generations expire |
