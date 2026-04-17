# CLAUDE.md

## Commands

```bash
uv run pytest tests/                    # Run all tests
uv run pytest tests/ -x -q --tb=short  # Quick test run, stop on first failure
uv run pytest tests/ -k "not test_catalog_empty"  # Skip env-dependent test
uvx ruff check src/ tests/             # Lint
uvx ruff check src/ tests/ --fix       # Auto-fix lint
uvx ruff format src/ tests/            # Format
uv run python -m mypy src/reagent/     # Type check (requires venv for pydantic plugin)
uv run pre-commit run --all-files      # Full pre-commit suite
uv run reagent --help                  # CLI help
```

## What This Is

Reagent is an automated asset synthesis and optimization engine for AI agent harnesses (Claude Code, Cursor, Codex, OpenCode). It analyzes repositories, generates configuration assets (agents, skills, hooks, commands, rules, CLAUDE.md files), evaluates their quality, and iteratively improves them through autonomous loops.

## Architecture

Python 3.13 CLI (`src/reagent/cli/`) backed by these packages:

- **core/** — parsers, inventory, catalog (leaf module, no upward imports)
- **creation/** — asset generation (creator, generators, suggest, exemplars)
- **evaluation/** — quality scoring with weighted metrics
- **intelligence/** — repo analysis, code intel, patterns, schema validation
- **security/** — scanner (20+ rules with MITRE ATLAS + OWASP AST10 metadata), trust model, integrity, governance, AgentShield gate
- **attestation/** — signed behavioral fingerprint (BehavioralFingerprint, ed25519 signing, AttestationStore), RFDD divergence detector, counterfactual replay gate
- **sandbox/** — BSR engine with HarnessDriver protocol, MockDriver, real-Claude-Code subprocess ClaudeCodeDriver, prompt corpus
- **shield/** — BATT runtime shield: TrustPolicy per TrustLevel, ShieldEnforcer with pluggable PolicySource, Claude Code PreToolUse hook script
- **llm/** — provider abstraction (Anthropic/OpenAI/Google/Ollama), router with circuit breaker, costs, cache, instincts, quality pipeline, Jinja2 prompts
- **loops/** — autonomous generate→evaluate→improve cycles with guardrails and approval queue
- **ci/** — CI runner (exit codes 0/1/2/3 for pass/quality/security/behavioral), drift detection, reporting
- **api/** — Starlette ASGI dashboard backend (REST + SSE endpoints)
- **storage/** — SQLite with WAL mode, forward-only migrations (through v6: attestations, divergence_findings)
- **harness/** — cross-harness adapters (Cursor, Codex, OpenCode, AGENTS.md)
- **telemetry/** — workflow profiling, hook installation, event parsing, HLOT attribute emission (`agentguard.asset.*`)
- **data/** — bundled schemas, prompt templates (.j2), hook scripts, sandbox probe corpus, red-team seed corpus
- **config.py** — Pydantic config hierarchy (CLI → env → config.yaml → defaults)
- **_tuning.py** — cached `get_tuning()` accessor for `TuningConfig` scoring/threshold constants

## Key Patterns

- **Lazy imports** in Click commands to keep CLI startup fast
- **TuningConfig** in config.py — all scoring/threshold constants are user-configurable via `~/.reagent/config.yaml` `tuning:` section, accessed via `get_tuning()` from `_tuning.py`
- **Jinja2 prompt templates** in `src/reagent/data/prompts/*.j2`, loaded by `llm/prompt_loader.py`, wired to asset types in `llm/prompts.py`
- **Three-tier LLM fallback**: LLM generation → enhanced templates → basic templates
- **Adversarial quality pipeline**: generator → critic → revision (up to 3 rounds)
- **Human-gated autonomy**: loops queue changes for approval before deploying
- **SQLite context managers**: Always `with sqlite3.connect(...)` or `with ReagentDB(...)`, never manual close
- **Circular import guard**: `config.py` uses `llm: Any` with `@model_validator` lazy import for LLMConfig; `_tuning.py` uses `from __future__ import annotations` + `TYPE_CHECKING`

## Things That Will Bite You

- `test_catalog_empty` fails on dev machines with existing `~/.reagent/catalog.jsonl` — skip with `-k "not test_catalog_empty"`
- `config.py` has a circular import workaround — `llm` field is `Any` with a model_validator that lazy-imports `LLMConfig`. Don't change this pattern.
- `_tuning.py` uses `from __future__ import annotations` + `TYPE_CHECKING` to avoid circular imports with `config.py`. This is intentional.
- The old monolithic `src/reagent/cli.py` was deleted; CLI is now `src/reagent/cli/` package with `commands/` submodules. Entry point is `cli:main` in `cli/__init__.py`.
- Provider API keys: env var always wins over config file. Precedence: env → `config.yaml` `llm.api_keys` → empty
- `uvx mypy` fails because pydantic plugin isn't available outside venv. Always use `uv run python -m mypy`.
- Dashboard static files are served from `dashboard/dist/` — must be built before Docker deployment
- ruff is not in the venv; use `uvx ruff` or configure pre-commit
- `llm/prompts.py` still exists but now renders Jinja2 templates via `prompt_loader.py` — it's not plain string constants anymore

## Code Conventions

- Python 3.13+, `X | None` unions, `list[str]` lowercase builtins
- `from __future__ import annotations` is allowed when needed for `TYPE_CHECKING` imports (see `_tuning.py`, `config.py`)
- Pydantic BaseModel for all data models, Field(default_factory=...) for mutable defaults
- Full type annotations on every function
- No module-level docstrings, no em-dash separator comments
- Google-style docstrings on public classes/functions only
- `logging.getLogger(__name__)` in every module
- `pytest.mark.parametrize` for repetitive test cases, `pytest.param(..., id="name")` for readable IDs
- Click for CLI with Rich console output; lazy imports inside command functions
- httpx for HTTP (no vendor SDKs)
- ruff line-length 88, mypy strict with pydantic plugin
- Configurable constants via `TuningConfig` in config.py, accessed through `get_tuning()` from `_tuning.py`
- CLI must work independenlty from the backend and it must be possible to just use the CLI.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **reagent** (3811 symbols, 11156 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/reagent/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/reagent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/reagent/clusters` | All functional areas |
| `gitnexus://repo/reagent/processes` | All execution flows |
| `gitnexus://repo/reagent/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
