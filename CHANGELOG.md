# Changelog
<!-- markdownlint-disable MD024 -->
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## 0.1.0

Initial release of AgentGuard — an automated asset synthesis and optimization engine for AI agent harnesses.

### Asset Management

- **Inventory & Catalog** — Scan `.claude/` directories and index agents, skills, hooks, commands, rules, and settings into a searchable JSONL catalog with content hashing
- **Smart Initialization** — Analyze repo conventions (language, framework, CI) and generate tailored starter assets with `agentguard init`
- **Schema Validation** — Two-layer validation: portable Agent Skills standard plus vendor extensions (JSON Schema); auto-normalization of common field variants
- **Snapshot & Rollback** — Version-track asset content with hash-based snapshots and rollback to any prior version
- **Baseline Generation** — `agentguard baseline` generates assets for all repos under a root directory with `--dry-run` and `--max-depth` options

### AI-Powered Generation

- **Multi-Provider LLM** — Generate repo-aware assets using Anthropic, OpenAI, Gemini, or Ollama via `httpx` (no vendor SDKs required); critic/revise adversarial pipeline for high-quality output
- **Template Fallback** — Falls back to rule-based template generation when no provider is configured
- **Instinct System** — Learns patterns from session history to improve future generation; confidence scoring with trust tiers (workspace / team / global); TTL-based expiry; extract, prune, import, and export commands
- **Cost Tracking** — Per-session and monthly LLM spend tracking with configurable budget limits and `agentguard cost` reporting

### Security

- **Security Scanning** — 20+ static analysis rules across critical/high/medium severity covering prompt injection, unsafe permissions, shell injection, tool over-provisioning, and hardcoded secrets
- **Security Gate** — Post-generation security validation integrated into the quality pipeline; security grade (A–F) shown in `agentguard evaluate` output; `--fix` flag for auto-remediation
- **Trust Model** — 4-level trust model with import gates

### Multi-Harness Support

- **Cross-Harness Export** — Generate assets for Claude Code, Cursor, Codex, and OpenCode from a single canonical source via `--harness` flag
- **Auto-Detection** — Automatically detect active harness from repo layout
- **AGENTS.md Generation** — Produce a universal `AGENTS.md` overview for any repo

### Quality & Evaluation

- **Quality Scoring** — Per-asset quality metrics (invocation rate, correction rate, staleness) with configurable thresholds
- **Regression Detection** — Check sessions for quality regressions against baselines
- **A/B Testing** — Create variants, compare metrics, and promote winners
- **`agentguard evaluate`** — Per-asset evaluation with structured JSON output and security grade

### Autonomous Loops

- **Loop Engine** — Autonomous generate→evaluate→improve cycle with guardrails and human approval gates
- **Loop Types** — `init`, `improve`, and `watch` modes scoped per repository

### Web Dashboard

- **REST + SSE API** — Starlette ASGI backend with 11 REST endpoints and server-sent events
- **React Frontend** — React 19 + TypeScript + Vite + Tailwind CSS; 6 pages: Asset Overview, Eval Trends, Cost Monitor, Instinct Store, Provider Config, Loop Control
- **Eval Trends** — Project-aware filtering, interactive chart with asset selection grouped by repository, sortable trend table with grade badges
- **Loop Control** — Guided trigger workflow: select loop type and repository, preview CLI command, view run history with filters
- **Instinct Store** — Browse by category or trust tier, confidence filters, expandable content rows, CLI action cards with copy buttons
- **Cost Monitor** — Per-provider spend breakdown, demo data detection, sourcing clarity labels
- **Docker** — Multi-stage `dashboard/Dockerfile` and `docker-compose.yml` for one-command launch
- **Cyberpunk Theme** — Dark mode with electric cyan/magenta/green neon accents, glow effects, gradient titles, polished animations

### CLI

- **30+ commands** — Full coverage of inventory, analysis, creation, security, evaluation, schema management, cost, instincts, and dashboard launch
- **Global logging** — `-v`/`--verbose` and `--log-file` flags; rotating file handler at `~/.agentguard/agentguard.log`
- **SQLite storage** — WAL-mode database at `~/.agentguard/agentguard.db` with FTS5 full-text index over instincts
- **GitHub Action** — `action.yml` for CI integration: evaluate assets and fail on quality regression
