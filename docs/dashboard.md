# Dashboard

Reagent includes a web dashboard for monitoring asset health, evaluation trends, generation costs, and controlling autonomous loops.

## Quick Start

```bash
reagent dashboard
```

This starts the dashboard API server and opens your browser at `http://localhost:8080`.

## Starting the Dashboard

### CLI

```bash
reagent dashboard                     # Start and open browser
reagent dashboard --port 9090         # Custom port
reagent dashboard --host 0.0.0.0     # Bind to all interfaces
reagent dashboard --no-browser        # Don't auto-open browser
```

**Options:**

| Flag | Description | Default |
|---|---|---|
| `--port INT` | Port to listen on | `8080` |
| `--host TEXT` | Host to bind to | `0.0.0.0` |
| `--docker` | Run via Docker Compose | off |
| `--podman` | Run via Podman Compose | off |
| `--no-browser` | Don't open browser automatically | off |

### Docker Compose

For persistent deployment or team access, use Docker Compose:

```bash
reagent dashboard --docker
```

Or run directly:

```bash
docker compose up -d
```

### Podman Compose

If you use Podman instead of Docker:

```bash
reagent dashboard --podman
```

Or run directly:

```bash
podman compose up -d
```

> **Note:** Podman 4.x+ ships with a built-in `podman compose` subcommand. For older versions, install [`podman-compose`](https://github.com/containers/podman-compose) separately.

The container setup:

- Builds the React frontend and Python API into a single image
- Mounts `~/.reagent` for database access
- Mounts your repos path (configurable via `REAGENT_REPOS_PATH`, defaults to `~/repos`) at `/home/app/repos` as read-only
- Exposes port `8080`
- Auto-restarts unless stopped

Set `REAGENT_REPOS_PATH` in your `.env` file to point to your local repos:

```bash
# .env
REAGENT_REPOS_PATH=~/my-projects
```

### Python Module

You can also start the API server directly:

```bash
python -m reagent.api --host 127.0.0.1 --port 8080
```

## Features

### Asset Overview

The main view shows all cataloged assets with:

- Asset name, type, and repository
- Quality score with letter grade (A–F)
- Last evaluation date
- Trend indicator (improving, stable, declining)

### Asset Detail View

Click any asset card to view its detail page, which includes:

- Full asset content rendered as markdown (via `react-markdown` with GFM support)
- Evaluation history chart showing score changes over time
- Score trend table with timestamps and letter grades
- Asset metadata: type, repository, quality score, and last evaluation date
- **Action toolbar** — trigger Evaluate, Regenerate, or Security Scan directly from the UI
  - **Regenerate** requires an LLM provider to be configured (returns a clear message if no API key is set)
  - **Security Scan** results persist to the database for audit trails
- **Security tab** — displays scan findings (severity, message, location) after running a scan
- Toast notifications for action results (success, error, info)

### Cyberpunk Visual Theme

The dashboard features a cyberpunk-inspired dark mode with electric cyan, magenta, and green neon accents. Cards, buttons, and badges have glow effects; page titles use gradient styling; data values use monospace fonts. Enhanced animations, custom scrollbars, and polished hover/loading/empty states complete the look. A light mode toggle remains available in the sidebar footer; your preference is saved to `localStorage` and persists across sessions.

### Page Descriptions

Each dashboard page includes a contextual banner explaining what data is displayed and which CLI commands populate it. For example, the Asset Overview banner explains that data comes from `reagent inventory` and `reagent evaluate`.

### Quality Trends

Time-series charts of evaluation scores per asset, showing how quality changes over time. Useful for tracking the impact of regeneration or manual edits.

The Eval Trends page includes project-aware filtering and visualization:

- **Repository dropdown** to filter evaluations by project
- **Asset type filter** chips for narrowing by type
- **Text search** for finding specific assets by name
- **Interactive chart** with user-controlled asset selection, grouped by project with a project-aware color strategy
- **Collapsible project-grouped table** with sortable columns, trend indicators, and grade badges
- **Summary cards** showing total evaluations, average score, and grade distribution

### Cost Tracking

Monitor LLM generation spending:

- Total cost by provider and model
- Cost per session and per asset
- Monthly budget utilization
- Cost breakdown by generation type (create, regenerate, critic)
- **Demo data detection** — seeded entries are tagged with `tier: "demo"` and can be toggled on or off via a filter
- **Sourcing clarity labels** distinguish real usage costs from demo/seed data
- **Enhanced summary cards** with real vs demo cost breakdown
- Cyberpunk-styled charts with neon colors

### Provider Status

Shows which LLM providers are configured and available:

- API key status (configured / missing)
- Default model per provider
- Provider health status
- **Environment variable hints** — each unconfigured provider shows which env var to set (e.g., `Set ANTHROPIC_API_KEY to activate`)

> **Tip:** When running via container, API keys must be set in the environment where you run `docker compose up` (or in a `.env` file). The `docker-compose.yml` passes them through automatically.

### Loop Control

View and manage autonomous generation loops through a three-tab interface:

- **Loop Runs** — Shows actual autonomous loop executions from the `loops` table, including status (running, completed, failed), iteration count, average score, and total cost. Supports type and status filters.
- **Pending Approval** — Lists assets generated by loops that are awaiting human review before deployment. Per-asset **Approve** and **Reject** buttons, plus bulk **Deploy All** and **Reject All** actions. Confirmation dialogs guard destructive operations. A content preview modal lets you inspect the asset before deciding.
- **Generations** — Browse LLM generation records with model, provider, token counts, and cost per generation.

The trigger workflow is a guided multi-step process:

1. Select a loop type: **init**, **improve**, or **watch** — each shows type-specific guardrails (init/improve: max 5 iterations, $2 cost cap; watch: 30-minute timeout, file change monitoring)
2. Select the target repository from the dropdown (populated from previous evaluations/loops) or type an absolute path
3. Review the pre-trigger summary with guardrails info and kill-switch reference
4. Copy the generated CLI command to run in your terminal

The dashboard generates the correct `reagent loop` command rather than executing it directly, giving you full control over when and where loops run.

**Stop reasons** — When a loop is stopped (e.g., security gate failures), the reason is displayed as a formatted list if it contains multiple items.

### Instincts

Browse extracted instincts (learned patterns from session telemetry):

- **Explanatory header banner** describing the instinct system
- **Three browsing tabs** — All, By Category, and By Trust Tier
- **Confidence filter chips** for narrowing by confidence level
- **Expandable content rows** to inspect instinct details inline
- **CLI action cards** — extract, prune, export, and import with copy-to-clipboard buttons
- **Pagination** at 25 instincts per page

## API Endpoints

The dashboard is built on a REST API that you can also use directly:

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/repos` | GET | Unique repository paths from evaluations and loops |
| `/api/assets` | GET | List all cataloged assets |
| `/api/assets/{id}` | GET | Asset detail with evaluation history |
| `/api/evaluations` | GET | Evaluation results over time |
| `/api/costs` | GET | Cost summary by provider |
| `/api/costs/entries` | GET | Individual cost entries |
| `/api/instincts` | GET | Extracted instincts list |
| `/api/providers` | GET | LLM provider status |
| `/api/loops` | GET | Loop history and status |
| `/api/loops/trigger` | POST | Generate a CLI command for a loop (`{ loop_type, repo_path }`) |
| `/api/loops/state` | GET | Actual loop run records from the `loops` table |
| `/api/loops/pending` | GET | Assets awaiting approval (filterable by `loop_id`) |
| `/api/assets/{id}/content` | GET | Raw file content for markdown rendering |
| `/api/assets/{id}/evaluate` | POST | Trigger evaluation for a single asset |
| `/api/assets/{id}/regenerate` | POST | Regenerate an asset using LLM |
| `/api/assets/{id}/scan` | POST | Security scan a single asset |
| `/api/loops/pending/{id}/approve` | POST | Approve a pending asset |
| `/api/loops/pending/{id}/reject` | POST | Reject a pending asset |
| `/api/loops/pending/deploy` | POST | Batch deploy all pending assets |
| `/api/events` | GET | SSE stream for real-time updates |

### Server-Sent Events

The `/api/events` endpoint streams real-time updates using SSE. The frontend uses this for live loop progress and evaluation updates without polling.

## Data Source

The dashboard reads from the SQLite database at `~/.reagent/reagent.db`. This database is populated by:

- **`reagent evaluate`** — writes evaluation scores
- **`reagent loop`** commands — writes loop state and pending assets
- **`reagent create` / `reagent regenerate`** — writes cost entries
- **`reagent inventory`** — writes asset catalog data
- **Security scans** — writes findings to the `security_scans` table (persisted for audit trail)

The database schema is auto-migrated on startup (currently version 3). Override the path via `REAGENT_DB_PATH` environment variable.

If the database doesn't exist yet, run some commands first to populate it:

```bash
reagent inventory                   # Build asset catalog
reagent evaluate --repo .           # Generate initial evaluations
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `REAGENT_DB_PATH` | SQLite database path | `~/.reagent/reagent.db` |
| `REAGENT_CORS_ORIGINS` | Comma-separated CORS origins | `http://localhost:5173,http://localhost:3000` |
| `ANTHROPIC_API_KEY` | Anthropic API key for LLM features | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `GOOGLE_API_KEY` | Google Gemini API key | — |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |

### CORS

The API server allows CORS requests from development origins by default. For production deployment, set `REAGENT_CORS_ORIGINS`:

```bash
export REAGENT_CORS_ORIGINS="https://dashboard.example.com"
```

## Development

The dashboard frontend is a React + TypeScript app built with Vite:

```bash
cd dashboard
npm install
npm run dev       # Start dev server at http://localhost:5173
```

The dev server proxies API requests to the backend at `http://localhost:8080`. Run the API server separately:

```bash
python -m reagent.api --host 127.0.0.1 --port 8080
```

### Build

```bash
cd dashboard
npm run build     # Outputs to dashboard/dist/
```

The production `reagent dashboard` command serves the built `dist/` directory as static files alongside the API.

### Shared Components

The dashboard includes reusable UI components in `dashboard/src/components/`:

| Component | Description |
|---|---|
| `Toast` | Notification system — success, error, info, warning variants |
| `Modal` | Dialog overlay — Escape to close, backdrop click dismissal |
| `ConfirmDialog` | Wraps Modal with confirm/cancel buttons for destructive actions |
| `ActionButton` | Button with automatic loading state and spinner for async operations |
| `StatusBadge` | Maps status strings to colored badges automatically |
| `EmptyState` | Placeholder with icon, title, and description |

### Asset Path Resolution

The backend resolves asset file paths using a multi-strategy approach in `_resolve_asset_path()`:

1. **Catalog ID** — parses `repo:type:name` format IDs
2. **Absolute path** — uses the path directly if it exists
3. **Relative path** — resolves against the working directory
4. **Prefix strip** — removes common prefixes to match
5. **Home directory** — expands `~` paths
6. **Docker remap** — maps repo paths to `/home/app/repos/` for container access

Names are slugified (spaces → underscores) for skill file matching.

### Tech Stack

- **Frontend:** React 19, TypeScript, Tailwind CSS, Recharts, TanStack Query
- **Backend:** Starlette (ASGI), uvicorn, aiosqlite
- **Database:** SQLite with WAL mode
- **Markdown:** `react-markdown` with `remark-gfm` for asset content rendering
- **Theming:** CSS custom properties with `[data-theme]` attribute; `useTheme()` hook for dark/light mode toggle
