# Asset Creation

Reagent generates Claude Code assets (agents, skills, hooks, commands, rules) that are tailored to your repository's languages, frameworks, and conventions.

## Analyzing Your Repository

Before creating assets, analyze the target repository:

```bash
reagent analyze ./my-project
```

This detects:

- **Languages** — primary and secondary languages by file count
- **Frameworks** — detected from package files (e.g., React, FastAPI, Django)
- **Architecture** — monorepo, microservice, library, etc.
- **Test configuration** — test runner and command
- **Lint configuration** — active linters and their config files
- **CI system** — GitHub Actions, GitLab CI, etc.
- **Asset audit** — existing agents, skills, hooks, commands in `.claude/`

The profile is saved to `~/.reagent/workflows/` for use by other commands.

## Creating Assets

### LLM-Powered Generation (Default)

By default, `reagent create` uses an LLM to generate assets tailored to your repository. It analyzes your stack (languages, frameworks, test config, conventions) and produces context-aware content:

```bash
reagent create agent --repo . --name code-reviewer
reagent create skill --repo . --name deploy
reagent create rule --repo . --name python-conventions
```

The generator uses a three-tier fallback:

1. **LLM** — Full generation via configured provider (Anthropic, OpenAI, etc.)
2. **Pattern** — Render from a matching stored pattern template
3. **Enhanced template** — Rule-based generation from repo profile

To skip LLM and use templates only:

```bash
reagent create agent --repo . --name reviewer --no-llm
```

To see estimated generation cost:

```bash
reagent cost
```

### From Smart Defaults

Generate a starter set of assets based on repo analysis:

```bash
reagent init ./my-project
```

This proposes agents, skills, and rules appropriate for the detected stack. You'll be shown previews and asked to confirm before anything is written.

### From a Pattern

Apply a reusable pattern template:

```bash
reagent create agent --repo . --from code-reviewer
reagent create skill --repo . --from ci-deploy
```

Patterns are extracted from your catalog using `reagent extract-patterns` and stored as parameterized templates.

### From an Outline

Provide a text outline and Reagent generates the asset:

```bash
reagent create agent --repo . --name reviewer --from-outline outline.md
echo "Review PRs, check tests, suggest improvements" | reagent create agent --repo . --name reviewer --from-outline -
```

### Interactive Mode

Build an asset field by field:

```bash
reagent create agent --repo . --interactive
```

### Regenerating Existing Assets

Regenerate an asset using evaluation feedback and accumulated instincts:

```bash
reagent regenerate .claude/agents/code-reviewer.md --repo .
```

This evaluates the current asset quality, loads relevant instincts from session history, and produces an improved version via LLM. You'll see a diff and can confirm before writing.

### Supported Asset Types

| Type | Output Location | Description |
| --- | --- | --- |
| `agent` | `.claude/agents/<name>.md` | Specialized AI agent with tools, skills, and instructions |
| `skill` | `.claude/skills/<name>/SKILL.md` | Reusable capability following the Agent Skills standard |
| `hook` | `.claude/settings.json` (hooks section) | Event-triggered scripts (PreToolUse, PostToolUse, etc.) |
| `command` | `.claude/commands/<name>.md` | Slash commands invokable during Claude Code sessions |
| `rule` | `.claude/rules/<name>.md` | Project rules and conventions applied to all sessions |

### CLAUDE.md

In addition to the structured asset types above, Reagent manages `CLAUDE.md` files — the project-level context file that Claude Code reads automatically. This file describes your project's conventions, architecture, and development practices.

```bash
reagent create claude-md --repo .       # Generate CLAUDE.md from repo analysis
```

`CLAUDE.md` is detected and cataloged as `claude_md` type. It lives at the repository root and can include:

- Project description and architecture overview
- Coding conventions and style guidelines
- Build, test, and lint commands
- File structure and naming conventions
- Important dependencies and integrations

When exporting to other harness formats, `CLAUDE.md` is translated:

- **Cursor** → `.cursor/rules/project-context.md` (with `alwaysApply: true` frontmatter)
- **Codex** → `AGENTS.md` (appended as a "Project Context" section)
- **OpenCode** → `.opencode/instructions/project-context.md`

## Generation Pipeline

When `reagent create` runs with LLM enabled, it follows this pipeline:

1. **Analyze** — Repo profile is loaded (languages, frameworks, conventions, CI system)
2. **Instinct injection** — Relevant instincts from session history are loaded and appended to the prompt
3. **Prompt build** — Structured prompt is assembled with repo context, asset type, and instincts
4. **LLM call** — Request sent to configured provider; response streamed and collected
5. **Critic review** — If `use_critic: true`, a second (cheaper) model reviews the output for quality
6. **Validate** — Output is parsed and validated against the asset schema
7. **Write** — Asset written to disk after optional human confirmation

### Fallback Chain

If any step in the LLM pipeline fails:

```txt
LLM generation → Enhanced template (full repo profile) → Basic template
```

Enhanced templates use the full `RepoProfile` (20+ fields) to produce repo-specific content
without an API call. Basic templates produce minimal but valid assets.

### Instinct System

Instincts are learned patterns extracted from session telemetry:

```bash
reagent instincts extract --repo .    # Extract from recent sessions
reagent instincts list                # View all instincts with confidence scores
reagent instincts prune               # Remove stale or low-confidence instincts
reagent instincts export --output instincts.json   # Share across repos
reagent instincts import instincts.json            # Import from file
```

Instincts are injected into generation prompts when `use_instincts: true` (default).
Higher-confidence instincts receive more weight in the prompt.

## LLM Provider Configuration

Reagent uses an LLM to generate high-quality, repo-aware assets. Configure the provider in `~/.reagent/config.yaml`:

```yaml
llm:
  provider: anthropic          # anthropic | openai | google | ollama
  model: claude-sonnet-4-20250514
  monthly_budget: 10.0         # USD hard cap
  temperature: 0.3
  features:
    enabled: true
    use_instincts: true        # Apply learned patterns from session history
    use_critic: false          # Enable critic pass for quality review
  fallback:
    - provider: openai
      model: gpt-4o-mini
```

### Environment Variables

Override config values at runtime:

| Variable | Description |
| --- | --- |
| `REAGENT_LLM_PROVIDER` | Provider name (`anthropic`, `openai`, `google`, `ollama`) |
| `REAGENT_LLM_MODEL` | Model name override |
| `REAGENT_LLM_ENABLED` | Disable LLM (`0` or `false`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google Gemini API key |

### Cost Tracking

Monitor spending:

```bash
reagent cost
```

Shows monthly spend, budget status, and cost by provider. The budget cap prevents unexpected charges.

Adapt globally-extracted patterns to a specific repository:

```bash
reagent specialize ./my-project
```

This reads global patterns from `~/.reagent/patterns/`, analyzes the target repo, and generates adapted versions. For example, a generic "test runner" skill becomes a pytest-specific skill for a Python repo or a vitest-specific skill for a TypeScript repo.

## Schema Validation

Reagent validates assets against two schema layers:

### Layer 1: Portable (Agent Skills Standard)

Fields defined by the [Agent Skills open standard](https://agentskills.io/specification): `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. Validated by the `skills-ref` reference implementation.

> **Note:** Skills use `allowed-tools` (from the Agent Skills standard), while agents use `tools` (Claude Code vendor extension). Reagent auto-normalises common variants (`allowedTools`, `allowed_tools`) during validation.

### Layer 2: Vendor (Claude Code Extensions)

Fields specific to Claude Code: `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `mcpServers`, `hooks`, `memory`, `background`, `effort`, `isolation`, `initialPrompt`. Validated against JSON Schema data files bundled with Reagent.

### Validating Assets

```bash
reagent validate ./my-agent.md       # Validate a single file
```

### Managing Schemas

```bash
reagent schema show agent            # View current schema
reagent schema check                 # Check for schema updates
reagent schema update                # Apply schema updates
reagent schema reset                 # Restore bundled defaults
```

Schemas ship as data files and can be updated independently of Reagent releases. A staleness reminder appears after 90 days without an update.

## Pattern Extraction

Extract reusable patterns from your entire asset catalog:

```bash
reagent extract-patterns
```

This clusters similar assets, identifies parameterized fields, and generates templates. Patterns are stored at `~/.reagent/patterns/` and can be applied with:

```bash
reagent apply-pattern <pattern-name> --repo ./my-project
```

The pattern engine fills in repo-specific values (language, framework, test command, lint command, repo name) based on the analysis profile.

## Cross-Harness Export

Reagent can export assets from Claude Code format to other agent harnesses:

```bash
reagent export . --harness cursor     # Export to Cursor rules format
reagent export . --harness codex      # Export to Codex format
reagent export . --harness opencode   # Export to OpenCode format
reagent export . --harness all        # Export to all supported harnesses
reagent export . --agents-md          # Generate universal AGENTS.md
```

List all supported harness formats:

```bash
reagent harnesses
```

AGENTS.md is a universal format recognized by Claude Code, Codex, Cursor, and OpenCode.
Using `--agents-md` generates a single file that works across all harnesses.

### Harness Format Comparison

Each harness stores configuration in a different directory structure. Reagent translates between them automatically:

| Asset Type | Claude Code | Cursor | Codex | OpenCode |
| --- | --- | --- | --- | --- |
| Agent | `.claude/agents/<name>.md` | `.cursor/agents/<name>.md` | `.codex/agents/<name>.toml` | `.opencode/agents/<name>.md` |
| Skill | `.claude/skills/<name>/SKILL.md` | `.cursor/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.opencode/skills/<name>/SKILL.md` |
| Rule | `.claude/rules/<name>.md` | `.cursor/rules/<name>.md` ¹ | `AGENTS.md` section | `.opencode/instructions/<name>.md` |
| Hook | `.claude/settings.json` | `.cursor/hooks/hooks.json` | *(not supported)* | `opencode.json` |
| CLAUDE.md | `CLAUDE.md` (repo root) | `.cursor/rules/project-context.md` | `AGENTS.md` section | `.opencode/instructions/project-context.md` |
| Command | `.claude/commands/<name>.md` | `.cursor/commands/<name>.md` | *(not supported)* | *(not supported)* |

¹ Cursor rules include additional frontmatter keys: `alwaysApply` (bool) and `globs` (list of file patterns).

### Auto-Detection

Reagent auto-detects the harness a repo uses by checking for directory markers:

1. `.claude/` directory → Claude Code
2. `.cursor/` directory or `.cursorrules` file → Cursor
3. `codex.md` at repo root → Codex
4. `opencode.md` at repo root → OpenCode
5. Default → Claude Code

Configure your preferred harness in `~/.reagent/config.yaml`:

```yaml
harness:
  default: claude-code
  generate:
    - claude-code
    - cursor        # Also generate Cursor format
```
