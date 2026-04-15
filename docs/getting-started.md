# Getting Started

## Installation

> **Reagent is not yet published to PyPI.** Install from source using the instructions below.

### From Source (recommended)

```bash
git clone https://github.com/calghar/reagent.git
cd reagent

# Core CLI only
uv sync

# With dev tools
uv sync --extra dev
```

Then run reagent via:

```bash
uv run reagent --help
```

### Optional Extras

```bash
uv sync --extra code-intel      # MCP integration
uv sync --extra dev             # Dev tools (pytest, ruff, mypy)
```

### From PyPI (coming soon)

```bash
pip install reagent
```

## LLM Configuration

Reagent's AI-powered features require an LLM provider API key. Without one, Reagent
falls back to rule-based template generation which works but produces less tailored assets.

### Supported Providers

| Provider | Env Variable | Default Model |
|----------|-------------|---------------|
| Anthropic (recommended) | `ANTHROPIC_API_KEY` | claude-sonnet-4-20250514 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.5-pro |
| Ollama (local) | — | llama3 |

Set the env variable for your preferred provider:

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Reagent auto-detects which provider to use based on available API keys.

### Config File

For persistent configuration, create `~/.reagent/config.yaml`:

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
```

See the [Configuration Reference](configuration.md) for all available settings and environment variables.

## First Scan

Run `reagent inventory` to scan your repositories and build the asset catalog:

```bash
reagent inventory
```

This scans all configured roots (default: `~/Development`) for `.claude/` directories and indexes every agent, skill, hook, command, rule, and settings file it finds.

To scan a single repo:

```bash
reagent inventory --repo ./my-project
```

## Understanding the Catalog

After scanning, view your assets:

```bash
reagent catalog
```

Filter by type:

```bash
reagent catalog --type agent
reagent catalog --type skill
reagent catalog --repo my-project
```

View details for a specific asset:

```bash
reagent show <asset-id>
```

Asset IDs follow the format `repo-name:type:name` (e.g., `my-project:agent:code-reviewer`).

## Next Steps

### Analyze a Repository

Detect languages, frameworks, and conventions:

```bash
reagent analyze ./my-project
```

### Get Suggestions

Get actionable recommendations for improving your assets:

```bash
reagent suggest --repo ./my-project
```

### Security Scan

Audit a `.claude/` directory for security issues:

```bash
reagent scan ./my-project/.claude
reagent audit --repo ./my-project
```

### Detect Drift

Check for stale, outdated, or missing assets:

```bash
reagent drift --repo ./my-project
```

### CI Integration

Run Reagent in CI pipelines with automatic quality gates:

```bash
reagent ci --threshold 70   # Exit 1 if below 70, exit 2 if security issues
```

See the [CI Integration Guide](ci-integration.md) for setup instructions with GitLab CI, Jenkins, and other providers.

### Evaluate Quality

Score your assets based on actual session telemetry:

```bash
reagent evaluate --repo ./my-project
```

See the [CLI Reference](cli-reference.md) for full command documentation.
