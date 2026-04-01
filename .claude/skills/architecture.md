---
name: architecture
description: Reagent v2 architecture reference. Load this skill when making design decisions, implementing new modules, or reviewing architecture alignment. Contains the system's design philosophy, module boundaries, and key patterns.
---

# Reagent v2 Architecture Reference

Quick reference for the reagent architecture. Full docs in `tmp/arch-v2/`.

## System Overview

Reagent is an automated asset synthesis and optimization engine for AI agent harnesses. It analyzes repositories, generates tailored agent configurations, evaluates quality, and continuously improves through a learning loop.

```txt
Repo Analysis → LLM Generation → Quality Gate → Asset Output
      ↑              ↑                ↑              |
      |         Instincts        Security         Evaluate
      |              ↑                               |
      └──────────────┴───── Learning Loop ───────────┘
```

## Package Boundaries

| Package | Responsibility | Key Files |
| --- | --- | --- |
| `reagent.core` | Asset parsing, catalog, inventory | `catalog.py`, `inventory.py`, `parsers.py` |
| `reagent.creation` | Asset generation + templates | `creator.py`, `generators.py`, `specializer.py`, `suggest.py`, `exemplars.py` |
| `reagent.evaluation` | Quality scoring, dashboards | `evaluator.py`, `dashboard.py` |
| `reagent.intelligence` | Repo analysis, patterns | `analyzer.py`, `code_intel.py`, `patterns.py`, `schema_validator.py` |
| `reagent.security` | Scanning, snapshots, trust | `agentshield.py`, `gate.py`, `governance.py`, `importer.py`, `scanner.py`, `snapshots.py`, `trust.py` |
| `reagent.telemetry` | Session profiling, hook events | `events.py`, `hook_installer.py`, `profiler.py` |
| `reagent.hooks` | Hook registration | `__init__.py` |
| `reagent.data` | Bundled instincts, schemas, prompt templates | `__init__.py`, `hooks/__init__.py`, `instincts/`, `schemas/`, `prompts/*.j2` |
| `reagent.llm` | LLM providers, prompts, quality | `cache.py`, `config.py`, `costs.py`, `instincts.py`, `parser.py`, `prompt_loader.py`, `prompts.py`, `providers.py`, `quality.py`, `router.py` |
| `reagent.storage` | SQLite database layer | `__init__.py`, `schema.sql`, `migrations.py` |
| `reagent.harness` | Cross-harness adapters | `adapters.py`, `agents_md.py`, `detection.py` |
| `reagent.loops` | Autonomous generation loops | `controller.py`, `guardrails.py`, `state.py` |
| `reagent.api` | ASGI dashboard backend | `routes.py`, `sse.py`, `app.py`, `db.py`, `models.py` |
| `reagent.ci` | GitHub Action, drift detection | `runner.py`, `drift.py`, `reporter.py` |

**Root-level modules**: `config.py` (Pydantic config hierarchy), `_tuning.py` (cached `get_tuning()` accessor for `TuningConfig`)

**CLI layer**: `cli/` package — `__init__.py` (entry point `main`), `_helpers.py`, `commands/` submodules (`assets.py`, `ci.py`, `dashboard.py`, `hooks.py`, `instincts.py`, `loop.py`, `security.py`)

## Key Design Decisions

1. **httpx over vendor SDKs**: No `anthropic` or `openai` packages. httpx + manual API calls = 500KB vs 10MB+ SDKs.

2. **SQLite over JSONL**: FTS5 for text search, WAL mode for concurrent CLI + dashboard reads, proper transactions, single file backup.

3. **Adversarial quality pipeline**: Generate → Critique → Revise → Validate. Cheap critic model (Haiku) spots defects; expensive model (Sonnet) fixes them. One revision cycle max.

4. **Instinct-based learning**: Not just patterns — instincts have confidence scores, TTL decay, trust tiers (bundled/managed/workspace). They evolve based on evaluation outcomes.

5. **Human-gated autonomy**: Autonomous loops always produce diffs for review. Never deploy without approval. Hard guardrails: max 5 iterations, max $2/loop, kill switch.

6. **Claude Code canonical format**: Generate for Claude Code first, then adapt to Codex/Cursor/OpenCode. AGENTS.md as universal cross-harness file.

7. **Three-tier fallback**: LLM (best) → Enhanced templates (good, no API key) → Minimal templates (last resort). Reagent always works without an API key.

8. **Jinja2 prompt templates**: LLM prompts are `.j2` files in `src/reagent/data/prompts/`, loaded by `llm/prompt_loader.py` via `render_prompt()`. `llm/prompts.py` wires system prompts to `AssetType` using the `SYSTEM_PROMPTS` dict.

9. **Lazy CLI imports**: All heavy imports inside Click command functions to keep `reagent --help` fast (< 100 ms).

10. **TuningConfig for constants**: All scoring weights, thresholds, and configurable constants live in `TuningConfig` (in `config.py`), user-overridable via `~/.reagent/config.yaml` `tuning:` section. Accessed via `get_tuning()` from `_tuning.py` (uses `lru_cache` + lazy import to avoid circular deps).

## Data Flow

```txt
CLI Command
    ↓
RepoProfile (analyzer.py)
    ↓
build_generation_prompt() ←── Instincts (instincts.py)
    ↓                    ←── Telemetry (profiler.py)
    ↓                    ←── Evaluation (evaluator.py)
ProviderRouter.generate()
    ↓
LLMResponse
    ↓
parse_response() → GeneratedAsset
    ↓
quality_gate() ←── SecurityGate
    ↓
[if critic enabled: critique → revise → re-validate]
    ↓
adapt_harness() ←── target format
    ↓
AssetDraft.write()
    ↓
SQLite: log generation, update evaluation
```

## Module Dependencies (What Can Import What)

```txt
cli/ → everything (lazy imports)
creation/ → core/, intelligence/, llm/, evaluation/
llm/ → core/ (types only), storage/
evaluation/ → core/, security/
harness/ → core/, creation/ (output types)
loops/ → creation/, evaluation/, llm/, storage/
api/ → storage/, evaluation/, loops/
ci/ → evaluation/, security/, creation/
_tuning.py → config.py (lazy import)
storage/ → nothing (leaf module)
core/ → nothing (leaf module)
```

Rules:

- `storage/` and `core/` are leaf modules — they import nothing from reagent.
- `llm/` depends only on `core/` types and `storage/`.
- No circular imports. If tempted, extract shared types into `core/`.
- `_tuning.py` breaks the config↔module cycle via `from __future__ import annotations` + `TYPE_CHECKING` + lazy import.

## Configuration Hierarchy

```txt
CLI flags (highest priority)
    ↓
Environment variables (REAGENT_LLM_PROVIDER, etc.)
    ↓
~/.reagent/config.yaml (user config)
    ↓
Built-in defaults (lowest priority)
```

Key config classes: `ReagentConfig`, `LLMConfig`, `TuningConfig`, `HarnessConfig`, `ScanConfig` (all in `config.py`).

## Database Schema (SQLite)

6 tables in `~/.reagent/reagent.db`:

- `profiles` — cached repo analysis
- `instincts` — learned patterns with confidence
- `cost_entries` — LLM cost tracking
- `evaluations` — asset quality history
- `generations` — LLM call log and cache
- `instincts_fts` — FTS5 virtual table

See `tmp/arch-v2/06-smart-memory.md` for full DDL.

## API Surface (`src/reagent/api/routes.py`)

All routes on the `_Routes` class:

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/assets` | All assets |
| `GET` | `/api/assets/{id}` | Single asset |
| `GET` | `/api/evaluations` | Evaluation history |
| `GET` | `/api/costs` | Cost summary |
| `GET` | `/api/costs/entries` | Itemised entries |
| `GET` | `/api/instincts` | Instinct store |
| `GET` | `/api/providers` | Provider health |
| `GET` | `/api/loops` | Loop run history |
| `POST` | `/api/loops/trigger` | Start a loop run |

## Implementation Phases

| Phase | Focus | Architecture Doc |
| --- | --- | --- |
| 1 | Provider abstraction | `04-multi-provider.md` |
| 2 | Generation engine | `03-llm-generation-engine.md`, `07-fallback-strategy.md` |
| 3 | Learning loop | `05-learning-loop.md` |
| 4 | SQLite storage | `06-smart-memory.md` |
| 5 | Cleanup | `01-current-state-audit.md` |
| 6 | Cross-harness | `11-cross-harness.md` |
| 7 | Security gate | `02-reference-analysis.md` (AgentShield) |
| 8 | Dashboard | `09-web-dashboard.md` |
| 9 | Autonomous loops | `10-autonomous-loops.md` |
| 10 | CI integration | `08-migration-plan.md` |

Full migration plan: `tmp/arch-v2/08-migration-plan.md`.
Phase prompts: `tmp/reagent-prompts-v2/`.

## Current Working Notes

- **NEVER** run `git add`, `git commit`, or `git push` — all architecture analysis belongs in response text only.
- All packages listed in the "Package Boundaries" table above are **real and shipped** in `src/reagent/` — none are planned/future.
- `loops/state.py` holds persistent loop state across process restarts (not just in-memory); `loops/controller.py` is the orchestrator; `loops/guardrails.py` enforces hard limits (max iterations, max cost, kill-switch file).
- `api/` routes are all methods on `_Routes` class in `routes.py`. The pattern avoids module-level route registration for testability.
- Dashboard type file is `dashboard/src/api/types.ts` (not `schemas.ts`).
- When the dependency graph changes, update this file.
