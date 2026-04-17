# Getting Started

## Installation

> **AgentGuard is not yet published to PyPI.** Install from source using the instructions below.

### From Source (recommended)

```bash
git clone https://github.com/calghar/agentguard.git
cd agentguard

# Core CLI only
uv sync

# With dev tools
uv sync --extra dev
```

Then run agentguard via:

```bash
uv run agentguard --help
```

### Optional Extras

```bash
uv sync --extra code-intel      # MCP integration
uv sync --extra dev             # Dev tools (pytest, ruff, mypy)
```

### From PyPI (coming soon)

```bash
pip install agentguard
```

## LLM Configuration

AgentGuard's AI-powered features require an LLM provider API key. Without one, AgentGuard
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

AgentGuard auto-detects which provider to use based on available API keys.

### Config File

For persistent configuration, create `~/.agentguard/config.yaml`:

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
```

See the [Configuration Reference](configuration.md) for all available settings and environment variables.

## First Scan

Run `agentguard inventory` to scan your repositories and build the asset catalog:

```bash
agentguard inventory
```

This scans all configured roots (default: `~/Development`) for `.claude/` directories and indexes every agent, skill, hook, command, rule, and settings file it finds.

To scan a single repo:

```bash
agentguard inventory --repo ./my-project
```

## Understanding the Catalog

After scanning, view your assets:

```bash
agentguard catalog
```

Filter by type:

```bash
agentguard catalog --type agent
agentguard catalog --type skill
agentguard catalog --repo my-project
```

View details for a specific asset:

```bash
agentguard show <asset-id>
```

Asset IDs follow the format `repo-name:type:name` (e.g., `my-project:agent:code-reviewer`).

## Next Steps

### Analyze a Repository

Detect languages, frameworks, and conventions:

```bash
agentguard analyze ./my-project
```

### Get Suggestions

Get actionable recommendations for improving your assets:

```bash
agentguard suggest --repo ./my-project
```

### Security Scan

Audit a `.claude/` directory for security issues:

```bash
agentguard scan ./my-project/.claude
agentguard audit --repo ./my-project
```

### Detect Drift

Check for stale, outdated, or missing assets:

```bash
agentguard drift --repo ./my-project
```

### CI Integration

Run AgentGuard in CI pipelines with automatic quality gates:

```bash
agentguard ci --threshold 70   # Exit 1 if below 70, exit 2 if security issues
```

See the [CI Integration Guide](ci-integration.md) for setup instructions with GitLab CI, Jenkins, and other providers.

### Evaluate Quality

Score your assets based on actual session telemetry:

```bash
agentguard evaluate --repo ./my-project
```

See the [CLI Reference](cli-reference.md) for full command documentation.
