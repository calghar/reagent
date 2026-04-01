import logging
import os
import sqlite3
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from reagent.api.db import ensure_schema
from reagent.api.routes import _Routes
from reagent.api.sse import sse_endpoint

logger = logging.getLogger(__name__)

# Default static dir: <repo-root>/dashboard/dist  (dev layout)
# In Docker the static dir is passed explicitly via create_app(static_dir=...).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATIC_DEFAULT = _REPO_ROOT / "dashboard" / "dist"

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

_NOT_BUILT_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Reagent Dashboard</title></head>
<body style="font-family:sans-serif;padding:2rem;background:#0f0f0f;color:#e0e0e0">
  <h1>🧪 Reagent Dashboard</h1>
  <p>The frontend has not been built yet.</p>
  <pre style="background:#1a1a1a;padding:1rem;border-radius:4px">
cd dashboard
npm install
npm run build
  </pre>
  <p>The API is available at <a href="/api/health">/api/health</a>.</p>
</body>
</html>
"""


async def _fallback_html(_request: Request) -> Response:
    return HTMLResponse(_NOT_BUILT_HTML)


def _resolve_cors_origins(cors_origins: list[str] | None) -> list[str]:
    """Resolve CORS allowed origins from explicit arg or env var.

    Resolution order:
    1. Explicit ``cors_origins`` argument (if provided).
    2. ``REAGENT_CORS_ORIGINS`` environment variable (comma-separated list).
    3. Built-in defaults (localhost:5173, localhost:3000).

    Args:
        cors_origins: Explicit origin list passed to :func:`create_app`.

    Returns:
        Resolved list of allowed origin strings.
    """
    if cors_origins is not None:
        return cors_origins
    env_val = os.environ.get("REAGENT_CORS_ORIGINS", "").strip()
    if env_val:
        return [origin.strip() for origin in env_val.split(",") if origin.strip()]
    return _DEFAULT_CORS_ORIGINS


def create_app(
    db_path: Path | None = None,
    static_dir: Path | None = None,
    cors_origins: list[str] | None = None,
) -> Starlette:
    """Create and return the Reagent dashboard Starlette application.

    Args:
        db_path: Path to the SQLite database.  Defaults to
            ``~/.reagent/reagent.db`` (via env or default).
        static_dir: Path to the built frontend ``dist/`` directory.
            Defaults to ``<repo-root>/dashboard/dist``.
        cors_origins: Allowed CORS origins.  Falls back to the
            ``REAGENT_CORS_ORIGINS`` env var (comma-separated) and then
            to ``["http://localhost:5173", "http://localhost:3000"]``.

    Returns:
        A configured :class:`starlette.applications.Starlette` instance.
    """
    # Ensure the database exists and schema is up-to-date before serving.
    try:
        ensure_schema(db_path)
    except (OSError, sqlite3.Error):
        logger.warning("Failed to initialise database schema", exc_info=True)

    routes_obj = _Routes(db_path)

    api_routes: list[Route] = [
        Route("/api/health", routes_obj.health, methods=["GET"]),
        Route("/api/assets", routes_obj.list_assets, methods=["GET"]),
        Route(
            "/api/assets/{id:path}/evaluate",
            routes_obj.evaluate_asset,
            methods=["POST"],
        ),
        Route(
            "/api/assets/{id:path}/regenerate",
            routes_obj.regenerate_asset,
            methods=["POST"],
        ),
        Route(
            "/api/assets/{id:path}/scan",
            routes_obj.scan_asset,
            methods=["POST"],
        ),
        Route(
            "/api/assets/{id:path}/content",
            routes_obj.get_asset_content,
            methods=["GET"],
        ),
        Route("/api/assets/{id:path}", routes_obj.get_asset_detail, methods=["GET"]),
        Route("/api/evaluations", routes_obj.list_evaluations, methods=["GET"]),
        Route("/api/costs", routes_obj.get_costs, methods=["GET"]),
        Route("/api/costs/entries", routes_obj.get_cost_entries, methods=["GET"]),
        Route("/api/instincts", routes_obj.list_instincts, methods=["GET"]),
        Route("/api/providers", routes_obj.get_providers, methods=["GET"]),
        Route("/api/repos", routes_obj.list_repos, methods=["GET"]),
        Route("/api/loops", routes_obj.list_loops, methods=["GET"]),
        Route("/api/loops/state", routes_obj.list_loop_runs, methods=["GET"]),
        Route(
            "/api/loops/pending/deploy",
            routes_obj.deploy_pending_assets,
            methods=["POST"],
        ),
        Route(
            "/api/loops/pending/{id}/approve",
            routes_obj.approve_pending_asset,
            methods=["POST"],
        ),
        Route(
            "/api/loops/pending/{id}/reject",
            routes_obj.reject_pending_asset,
            methods=["POST"],
        ),
        Route("/api/loops/pending", routes_obj.list_pending_assets, methods=["GET"]),
        Route("/api/loops/trigger", routes_obj.trigger_loop, methods=["POST"]),
        Route("/api/events", sse_endpoint, methods=["GET"]),
    ]

    resolved_static = static_dir or _STATIC_DEFAULT
    index_path = resolved_static / "index.html"
    assets_dir = resolved_static / "_static"

    if resolved_static.exists() and index_path.is_file():
        _index_html = index_path.read_text()

        async def _spa_fallback(_request: Request) -> Response:
            return HTMLResponse(_index_html)

        spa_routes: list[Route | Mount] = [
            *api_routes,
        ]
        if assets_dir.is_dir():
            spa_routes.append(
                Mount("/_static", StaticFiles(directory=assets_dir)),
            )
        spa_routes.append(
            Route("/{path:path}", _spa_fallback, methods=["GET"]),
        )
        routes: list[Route | Mount] = spa_routes
    else:
        routes = [
            *api_routes,
            Route("/{path:path}", _fallback_html, methods=["GET"]),
        ]

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=_resolve_cors_origins(cors_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        ),
    ]

    return Starlette(routes=routes, middleware=middleware)
