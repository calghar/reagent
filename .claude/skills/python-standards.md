---
name: python-standards
description: Python 3.13+ coding standards for the reagent project. Load this skill when writing or reviewing Python code to ensure consistency with project conventions, modern Python idioms, and community best practices.
---

# Python 3.13+ Standards for Reagent

This skill codifies the Python coding standards for the reagent project. All Python code in `src/reagent/` and `tests/` must follow these rules.

## Language Level

Python 3.13+. Use modern syntax unconditionally:

```python
# Correct
def process(data: str | None = None) -> list[str]: ...
items: dict[str, list[int]] = {}

# Wrong — never do these
from typing import Optional, List, Dict  # use builtins
Optional[str]  # use str | None
```

`from __future__ import annotations` is allowed when paired with `TYPE_CHECKING` to break circular imports. See `_tuning.py` and `config.py` for the canonical pattern. Do NOT use it gratuitously.

## Module Structure

Every module follows this order:

```python
# stdlib imports
import logging
from pathlib import Path

# third-party imports
from pydantic import BaseModel, Field

# local imports
from reagent.core.catalog import CatalogEntry

logger = logging.getLogger(__name__)

# Constants (or use TuningConfig for user-configurable values)
MAX_RETRIES = 3

# Pydantic models
class MyModel(BaseModel): ...

# Plain classes
class MyService: ...

# Private helpers
def _helper() -> str: ...

# Public API
def public_function() -> None: ...
```

No module-level docstrings. No em-dash separator comments like:
```python
# ---------------------------------------------------------------------------
# Section heading   ← NEVER do this
# ---------------------------------------------------------------------------
```

## Configurable Constants (TuningConfig)

Scoring weights, thresholds, and other user-configurable constants belong in `TuningConfig` (defined in `config.py`), not as module-level constants. Access them via `get_tuning()`:

```python
from reagent._tuning import get_tuning

def evaluate(score: float) -> str:
    tuning = get_tuning()
    if score >= tuning.quality_threshold:
        return "pass"
    return "fail"
```

Use plain module-level constants only for truly fixed values (regex patterns, enum mappings, URL paths).

## Type Annotations

Every function is fully annotated. No exceptions.

```python
# All params and return type annotated
def create_asset(
    asset_type: AssetType,
    name: str,
    profile: RepoProfile,
    config: ReagentConfig | None = None,
) -> AssetDraft:
    """Create an asset draft from repo profile.

    Args:
        asset_type: The type of asset to create.
        name: Asset name (kebab-case).
        profile: Repository analysis profile.
        config: Optional config override.

    Returns:
        Draft ready to write to disk.
    """
```

Key rules:

- `X | None` for optional types, never `Optional[X]`
- `list[str]`, `dict[str, int]`, `tuple[int, ...]` — lowercase builtins
- `typing.Self` for classmethods returning the class
- `typing.Protocol` for structural subtyping (interfaces)
- `StrEnum` for string enumerations
- `**kwargs: Any` only at true boundaries — prefer explicit params

## Pydantic Models

```python
class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = "stop"

class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.3
    fallback: list[ProviderFallback] = Field(default_factory=list)
    monthly_budget: float = 10.0

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Load config from YAML file."""
```

Rules:

- `BaseModel` for all data classes. Never `@dataclass` for new code.
- `Field(default_factory=...)` for mutable defaults (lists, dicts, Paths).
- Model methods for domain logic. Keep models focused.
- `model_validate()` / `model_dump()` for serialization.
- `@computed_field` or `@property` for derived values.

## Error Handling

```python
# Good: specific exception, meaningful message
def get_provider(name: str) -> LLMProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider: {name!r}. Available: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]

# Good: non-critical failure with logging
try:
    profile = load_telemetry(repo_path)
except FileNotFoundError:
    logger.info("No telemetry data found, skipping")
    profile = None

# Wrong: bare except, swallowing errors
try:
    do_something()
except Exception:  # never
    pass
```

Rules:

- Raise specific exceptions: `ValueError`, `FileNotFoundError`, `RuntimeError`, or custom.
- Never bare `except Exception`. Always specify the exception type.
- CLI commands catch errors and produce Rich-formatted user messages.
- Use `logger.warning()` for recoverable issues, `logger.error()` for non-recoverable.
- OWASP: never log secrets, API keys, or user credentials.

## Functions and Complexity

```python
# Good: simple, focused function
def classify_tools(name: str, description: str = "") -> list[str]:
    """Classify tools by semantic category analysis."""
    combined = f"{name} {description}".lower()
    scores = _compute_category_scores(combined)
    if max(scores.values()) > 0:
        best = max(scores, key=scores.get)
        return TOOL_CATEGORIES[best]["tools"]
    return DEFAULT_TOOLS

# Good: break complex logic into helpers
def _compute_category_scores(text: str) -> dict[str, float]:
    """Score each tool category against input text."""
    words = set(text.replace("-", " ").replace("_", " ").split())
    return {
        category: _score_category(words, text, config)
        for category, config in TOOL_CATEGORIES.items()
    }
```

Rules:

- SonarQube cognitive complexity **max 15** per function. Break up complex logic.
- Early returns for guard clauses. Reduce nesting.
- Private helpers (`_prefixed`) for extracting sub-logic.
- Max ~40 lines per function. If longer, split.
- Prefer pure functions where possible. Side effects in clearly named methods.

## Async Code

```python
# httpx for all HTTP calls
async def generate(self, prompt: str, system: str, config: GenerationConfig) -> LLMResponse:
    """Generate an LLM completion."""
    response = await self._client.post(
        self.BASE_URL,
        headers=self._headers(),
        json=self._build_request(prompt, system, config),
    )
    response.raise_for_status()
    return self._parse_response(response.json())
```

Rules:

- `httpx.AsyncClient` for HTTP. No `requests`, no vendor SDKs (`anthropic`, `openai` packages are banned).
- `sqlite3` from stdlib for storage. No SQLAlchemy.
- Use `asyncio.TaskGroup` for concurrent operations (Python 3.13).
- Clean shutdown: close clients in `finally` blocks or context managers.

## SQLite Patterns

Always use context managers for connections — never leave connections open:

```python
import sqlite3
from pathlib import Path

# Good: context manager ensures connection is closed
def read_data(db_path: Path) -> list[dict[str, object]]:
    """Read all evaluations ordered by creation time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM evaluations ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

# Enable WAL mode and foreign keys on first connect
def _init_db(db_path: Path) -> None:
    """Initialize database pragmas for WAL mode and referential integrity."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
```

Rules:

- Always `with sqlite3.connect(db_path) as conn:` — never manual `conn.close()`.
- Always set `conn.row_factory = sqlite3.Row` for dict-like row access.
- **Always use parameterised queries** — never concatenate user input into SQL strings:
  ```python
  # Good
  conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
  # NEVER
  conn.execute(f"SELECT * FROM assets WHERE id = '{asset_id}'")
  ```
- WAL mode is set once at DB init by `ReagentDB.__init__` — do not re-set it in every query.
- `storage/` is a leaf module — it imports nothing from other reagent packages.

## LLM Prompts

Prompts are Jinja2 `.j2` templates in `src/reagent/data/prompts/`, loaded by `llm/prompt_loader.py` via `render_prompt()`. `llm/prompts.py` wires system prompts to `AssetType` using the `SYSTEM_PROMPTS` dict:

```python
# llm/prompt_loader.py — renders Jinja2 templates
from reagent.llm.prompt_loader import render_prompt

system = render_prompt("agent_system.j2")
user = render_prompt("generation_user.j2", profile=profile, instincts=instincts)

# llm/prompts.py — wires templates to asset types
SYSTEM_PROMPTS: dict[AssetType, str] = {
    AssetType.AGENT: render_prompt("agent_system.j2"),
    AssetType.SKILL: render_prompt("skill_system.j2"),
    ...
}
```

Template files: `agent_system.j2`, `skill_system.j2`, `hook_system.j2`, `command_system.j2`, `rule_system.j2`, `claude_md_system.j2`, `generation_user.j2`, `critic.j2`, `critic_system.j2`, `revision.j2`.

## CLI Patterns (Click)

```python
@cli.command()
@click.argument("repo", type=click.Path(exists=True, path_type=Path))
@click.option("--no-llm", is_flag=True, help="Use enhanced templates instead of LLM")
@click.option("--harness", type=click.Choice(["claude-code", "codex", "cursor", "opencode"]))
def create(repo: Path, no_llm: bool, harness: str | None) -> None:
    """Create agent assets for a repository."""
    # Lazy imports for startup speed
    from reagent.creation.creator import create_asset

    config = _load_config(ctx)
    # ...
```

Rules:

- Lazy imports of heavy modules inside command functions.
- `click.Path(exists=True, path_type=Path)` for path arguments.
- `click.Choice` for enum-like options.
- Rich console for all user-facing output. Tables for structured data.
- `click.UsageError` for user errors. `SystemExit(1)` for fatal errors.

## References

- Python 3.13 What's New: <https://docs.python.org/3.13/whatsnew/3.13.html>
- Pydantic v2 Docs: <https://docs.pydantic.dev/latest/>
- httpx Docs: <https://www.python-httpx.org/>
- Click Docs: <https://click.palletsprojects.com/>
- Rich Docs: <https://rich.readthedocs.io/>
- Google Python Style Guide: <https://google.github.io/styleguide/pyguide.html>
- ruff Rules: <https://docs.astral.sh/ruff/rules/>
- Effective Python (Brett Slatkin): Items on modern idioms, type hints, generators
- Architecture Patterns with Python (Percival & Gregory): domain models, service layer patterns
