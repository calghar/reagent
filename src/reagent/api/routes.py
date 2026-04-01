import asyncio
import json
import logging
import os
import shlex
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from reagent._tuning import get_tuning
from reagent.api.db import get_connection
from reagent.api.models import (
    AssetContent,
    AssetSummary,
    CostEntriesPage,
    CostEntry,
    CostSummary,
    EvaluateResult,
    EvaluationPoint,
    GenerationRow,
    HealthResponse,
    InstinctRow,
    LoopRun,
    LoopTriggerResult,
    PendingAssetRow,
    ProviderStatus,
    RegenerateResult,
    ScanResult,
)
from reagent.llm.config import PROVIDER_ENV_KEYS

logger = logging.getLogger(__name__)

# Providers that need no API key are always considered available.
# PROVIDER_ENV_KEYS only contains providers that require a key, so a
# provider absent from it (e.g. ollama) maps to None → always available.
_PROVIDER_ENV_KEYS_WITH_NONE: dict[str, str | None] = dict(PROVIDER_ENV_KEYS) | {
    "ollama": None,
}

_ALLOWED_GROUP_COLS: frozenset[str] = frozenset({"provider", "model", "session_id"})

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "ollama": "llama3",
}

_UNEVALUATED_SCORE: float = 0.0

_LIST_ASSETS_SQL = """
WITH ranked AS (
    SELECT
        asset_path,
        asset_type,
        asset_name,
        repo_path,
        quality_score,
        evaluated_at,
        'evaluated' AS status,
        COUNT(*) OVER (PARTITION BY asset_path) AS evaluation_count,
        ROW_NUMBER() OVER (
            PARTITION BY asset_path ORDER BY evaluated_at DESC
        ) AS rn
    FROM evaluations
    {where_clause}
),
pending_not_evaluated AS (
    SELECT
        pa.file_path        AS asset_path,
        pa.asset_type,
        pa.asset_name,
        COALESCE(l.repo_path, '.') AS repo_path,
        pa.new_score        AS quality_score,
        pa.created_at       AS evaluated_at,
        pa.status,
        1                   AS evaluation_count,
        1                   AS rn
    FROM pending_assets pa
    LEFT JOIN loops l ON pa.loop_id = l.loop_id
    WHERE pa.status = 'pending'
      AND pa.file_path NOT IN (SELECT asset_path FROM evaluations)
      {pending_type_clause}
)
SELECT
    asset_path,
    asset_type,
    asset_name,
    repo_path,
    quality_score  AS latest_score,
    evaluation_count,
    evaluated_at   AS last_evaluated,
    status
FROM ranked
WHERE rn = 1
UNION ALL
SELECT
    asset_path,
    asset_type,
    asset_name,
    repo_path,
    quality_score  AS latest_score,
    evaluation_count,
    evaluated_at   AS last_evaluated,
    status
FROM pending_not_evaluated
ORDER BY latest_score DESC
"""


_CATALOG_ID_FILE_MAP: dict[str, list[str]] = {
    "agent": [".claude/agents/{name}.md"],
    "skill": [
        ".claude/skills/{name}/SKILL.md",
        ".claude/skills/{name}.md",
        ".claude/skills/{slug}/SKILL.md",
        ".claude/skills/{slug}.md",
    ],
    "hook": [".claude/settings.json"],
    "settings": [".claude/settings.json", ".claude/settings.local.json"],
    "claude_md": ["CLAUDE.md", ".claude/CLAUDE.md"],
    "command": [".claude/commands/{name}.md"],
    "rule": [".cursorrules", ".claude/rules/{name}.md"],
}


def _slugify(name: str) -> str:
    """Convert a display name to a file-system-friendly slug."""
    return name.lower().replace(" ", "_").replace("-", "_")


def _resolve_asset_path(asset_path: str, repo_path: str) -> Path | None:
    """Try multiple strategies to resolve an asset file path.

    Handles catalog IDs (``repo:type:name``), absolute paths, and relative
    paths.  Inside a container the host ``repo_path`` won't exist, so we
    remap through ``/home/app/repos/<repo_name>``.
    """
    repo = Path(repo_path)

    # Strategy 0: parse catalog ID format "repo:type:name"
    parts_split = asset_path.split(":")
    catalog_type = ""
    catalog_name = ""
    catalog_templates: list[str] = []
    if len(parts_split) >= 3:
        catalog_type = parts_split[1]
        catalog_name = ":".join(parts_split[2:])
        catalog_templates = _CATALOG_ID_FILE_MAP.get(catalog_type, [])
        slug = _slugify(catalog_name)
        for tmpl in catalog_templates:
            candidate = repo / tmpl.replace("{name}", catalog_name).replace(
                "{slug}", slug
            )
            if candidate.exists():
                return candidate

    # Strategy 1: absolute path as-is
    candidate = Path(asset_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    # Strategy 2: relative to repo_path
    candidate = repo / asset_path
    if candidate.exists():
        return candidate

    # Strategy 3: strip common prefixes to find relative portion
    asset_markers = (".claude", ".cursorrules", "agents", "skills", "hooks")
    path_parts = Path(asset_path).parts
    relative_from_marker: Path | None = None
    for i, part in enumerate(path_parts):
        if part in asset_markers:
            relative_from_marker = Path(*path_parts[i:])
            candidate = repo / relative_from_marker
            if candidate.exists():
                return candidate
            break

    # Strategy 4: try under ~/.reagent base
    reagent_home = Path.home() / ".reagent"
    candidate = reagent_home / asset_path
    if candidate.exists():
        return candidate

    # Strategy 5: Docker/container path remapping
    # When the DB was populated on the host, repo_path is an absolute host
    # path (e.g. /Users/alice/dev/my-repo) that doesn't exist inside the
    # container.  Repos are mounted at /home/app/repos/<dir_name>.
    docker_repos = Path("/home/app/repos")
    if docker_repos.is_dir() and repo.parts:
        remapped = docker_repos / repo.name
        if remapped.is_dir():
            # 5a: catalog templates
            if catalog_templates:
                slug = _slugify(catalog_name)
                for tmpl in catalog_templates:
                    candidate = remapped / tmpl.replace("{name}", catalog_name).replace(
                        "{slug}", slug
                    )
                    if candidate.exists():
                        return candidate
            # 5b: relative portion extracted from the absolute asset_path
            if relative_from_marker is not None:
                candidate = remapped / relative_from_marker
                if candidate.exists():
                    return candidate
            # 5c: strip the host repo_path prefix from the absolute asset_path
            asset_p = Path(asset_path)
            if asset_p.is_absolute():
                try:
                    rel = asset_p.relative_to(repo)
                    candidate = remapped / rel
                    if candidate.exists():
                        return candidate
                except ValueError:
                    pass

    return None


class _Routes:
    """Route handler class that carries the DB path through all endpoints."""

    def __init__(self, db_path: Path | None) -> None:
        self._db_path = db_path

    async def health(self, _request: Request) -> JSONResponse:
        """GET /api/health — liveness probe."""
        try:
            async with get_connection(self._db_path) as conn:
                await conn.execute("SELECT 1")
            return JSONResponse(
                HealthResponse(status="ok", db="connected").model_dump()
            )
        except (aiosqlite.Error, OSError):
            return JSONResponse(
                HealthResponse(status="degraded", db="error").model_dump(),
                status_code=503,
            )

    async def list_assets(self, request: Request) -> JSONResponse:
        """GET /api/assets — list unique assets with latest evaluation scores."""
        type_filter = request.query_params.get("type")
        where_clause = "WHERE asset_type = :type_val" if type_filter else ""
        pending_type_clause = "AND pa.asset_type = :type_val" if type_filter else ""
        sql = _LIST_ASSETS_SQL.format(
            where_clause=where_clause,
            pending_type_clause=pending_type_clause,
        )

        try:
            async with get_connection(self._db_path) as conn:
                params: dict[str, str] = {}
                if type_filter:
                    params["type_val"] = type_filter
                cursor = await conn.execute(sql, params)
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch assets: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [
            AssetSummary(
                asset_path=str(row["asset_path"]),
                asset_type=str(row["asset_type"]),
                asset_name=str(row["asset_name"]),
                repo_path=str(row["repo_path"]),
                latest_score=float(row["latest_score"]),
                evaluation_count=int(row["evaluation_count"]),
                last_evaluated=str(row["last_evaluated"]),
                status=str(row["status"]),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def get_asset_detail(self, request: Request) -> Response:
        """GET /api/assets/{id} — evaluation history for a specific asset."""
        asset_path: str = request.path_params["id"]

        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT evaluation_id, asset_name, asset_type,
                           quality_score, evaluated_at, repo_path
                    FROM evaluations
                    WHERE asset_path = ?
                    ORDER BY evaluated_at DESC
                    """,
                    (asset_path,),
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError):
            return JSONResponse({"detail": "Database error"}, status_code=500)

        if not rows:
            return JSONResponse({"detail": "Asset not found"}, status_code=404)

        items = [
            EvaluationPoint(
                evaluation_id=str(row["evaluation_id"]),
                asset_name=str(row["asset_name"]),
                asset_type=str(row["asset_type"]),
                quality_score=float(row["quality_score"]),
                evaluated_at=str(row["evaluated_at"]),
                repo_path=str(row["repo_path"] or ""),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def get_asset_content(self, request: Request) -> Response:
        """GET /api/assets/{id}/content — raw file content for an asset."""
        asset_path: str = request.path_params["id"]

        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """SELECT asset_name, asset_type, quality_score,
                              evaluated_at, repo_path
                       FROM evaluations WHERE asset_path = ?
                       ORDER BY evaluated_at DESC LIMIT 1""",
                    (asset_path,),
                )
                row = await cursor.fetchone()
        except (aiosqlite.Error, OSError):
            return JSONResponse({"detail": "Database error"}, status_code=500)

        if not row:
            return JSONResponse({"detail": "Asset not found"}, status_code=404)

        repo_path = str(row["repo_path"])
        resolved = _resolve_asset_path(asset_path, repo_path)
        if resolved is None:
            content = "File not found on disk"
        else:
            try:
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                content = "Unable to read file"

        return JSONResponse(
            AssetContent(
                asset_path=asset_path,
                asset_name=str(row["asset_name"]),
                asset_type=str(row["asset_type"]),
                content=content,
                repo_path=repo_path,
                quality_score=(
                    float(row["quality_score"])
                    if row["quality_score"] is not None
                    else None
                ),
                last_evaluated=(
                    str(row["evaluated_at"])
                    if row["evaluated_at"] is not None
                    else None
                ),
            ).model_dump()
        )

    async def list_evaluations(self, request: Request) -> JSONResponse:
        """GET /api/evaluations — evaluation time-series data."""
        api = get_tuning().api
        try:
            limit = int(request.query_params.get("limit", str(api.default_eval_limit)))
        except ValueError:
            limit = api.default_eval_limit

        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT evaluation_id, asset_name, asset_type,
                           quality_score, evaluated_at, repo_path
                    FROM evaluations
                    ORDER BY evaluated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch evaluations: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [
            EvaluationPoint(
                evaluation_id=str(row["evaluation_id"]),
                asset_name=str(row["asset_name"]),
                asset_type=str(row["asset_type"]),
                quality_score=float(row["quality_score"]),
                evaluated_at=str(row["evaluated_at"]),
                repo_path=str(row["repo_path"] or ""),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def get_costs(self, _request: Request) -> JSONResponse:
        """GET /api/costs — aggregate cost summary."""
        try:
            async with get_connection(self._db_path) as conn:
                summary_row = await _fetch_cost_summary(conn)
                by_provider = await _fetch_cost_by_group(conn, "provider")
                by_model = await _fetch_cost_by_group(conn, "model")
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch cost summary: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        total: float = float(summary_row["total_usd"] or 0)
        count: int = int(summary_row["entry_count"] or 0)
        cache_count: int = int(summary_row["cache_count"] or 0)
        rate = cache_count / count if count > 0 else 0.0

        return JSONResponse(
            CostSummary(
                total_usd=total,
                by_provider=by_provider,
                by_model=by_model,
                entry_count=count,
                cache_hit_rate=rate,
            ).model_dump()
        )

    async def get_cost_entries(self, request: Request) -> JSONResponse:
        """GET /api/costs/entries — paginated cost entries."""
        api = get_tuning().api
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            per_page = max(
                1,
                min(
                    api.max_page_size,
                    int(
                        request.query_params.get("per_page", str(api.default_page_size))
                    ),
                ),
            )
        except ValueError:
            page, per_page = 1, api.default_page_size

        offset = (page - 1) * per_page

        try:
            async with get_connection(self._db_path) as conn:
                count_row = await conn.execute("SELECT COUNT(*) FROM cost_entries")
                total_row = await count_row.fetchone()
                total = int(total_row[0]) if total_row else 0

                cursor = await conn.execute(
                    """
                    SELECT cost_id, timestamp, provider, model, asset_type, asset_name,
                           input_tokens, output_tokens, cost_usd,
                           latency_ms, tier, was_fallback
                    FROM cost_entries
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (per_page, offset),
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch cost entries: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [_row_to_cost_entry(row) for row in rows]
        return JSONResponse(
            CostEntriesPage(
                items=items, total=total, page=page, per_page=per_page
            ).model_dump()
        )

    async def list_instincts(self, _request: Request) -> JSONResponse:
        """GET /api/instincts — all instincts with confidence and trust tier."""
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT instinct_id, content, category, trust_tier,
                           confidence, use_count, success_rate, created_at
                    FROM instincts
                    ORDER BY confidence DESC
                    """
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch instincts: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [
            InstinctRow(
                instinct_id=str(row["instinct_id"]),
                content=str(row["content"]),
                category=str(row["category"]),
                trust_tier=str(row["trust_tier"]),
                confidence=float(row["confidence"]),
                use_count=int(row["use_count"]),
                success_rate=float(row["success_rate"]),
                created_at=str(row["created_at"]),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def get_providers(self, _request: Request) -> JSONResponse:
        """GET /api/providers — provider availability from env vars."""
        try:
            items = _build_provider_list_from_env()
            return JSONResponse([p.model_dump() for p in items])
        except (KeyError, ValueError) as exc:
            logger.warning("Failed to list providers: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

    async def list_repos(self, _request: Request) -> JSONResponse:
        """GET /api/repos — unique repository paths from evaluations and loops."""
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT DISTINCT repo_path FROM (
                        SELECT repo_path FROM evaluations
                        UNION
                        SELECT repo_path FROM loops
                    )
                    WHERE repo_path IS NOT NULL AND repo_path != ''
                    ORDER BY repo_path
                    """
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch repos: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        repos = [str(row["repo_path"]) for row in rows]
        return JSONResponse(repos)

    async def list_loops(self, _request: Request) -> JSONResponse:
        """GET /api/loops — recent generation cache entries."""
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    """
                    SELECT cache_key, asset_type, name, generated_at,
                           provider, model, cost_usd
                    FROM generations
                    ORDER BY generated_at DESC
                    LIMIT ?
                    """,
                    (get_tuning().api.max_loop_results,),
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch loops: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [
            GenerationRow(
                cache_key=str(row["cache_key"]),
                asset_type=str(row["asset_type"]),
                name=str(row["name"]),
                generated_at=str(row["generated_at"]),
                provider=str(row["provider"]),
                model=str(row["model"]),
                cost_usd=float(row["cost_usd"]),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def trigger_loop(self, request: Request) -> JSONResponse:
        """POST /api/loops/trigger — generate CLI command for loop execution."""
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except (ValueError, KeyError):
            pass

        loop_type = body.get("loop_type", "improve")
        repo_path = body.get("repo_path", ".")

        safe_repo = shlex.quote(repo_path)
        commands = {
            "init": f"reagent loop init --repo {safe_repo}",
            "improve": f"reagent loop improve --repo {safe_repo}",
            "watch": f"reagent loop watch --repo {safe_repo}",
        }
        command = commands.get(loop_type, commands["improve"])

        descriptions = {
            "init": (
                "Generate all missing assets from scratch"
                " (max 5 iterations, $2 budget cap)."
                " Assets are queued for approval"
                " before deployment."
            ),
            "improve": (
                "Regenerate below-threshold assets to raise"
                " quality scores (max 5 iterations,"
                " $2 budget cap). Only assets scoring"
                " below 80 are targeted."
            ),
            "watch": (
                "Monitor the repository for file changes"
                " and auto-regenerate affected assets."
                " Runs until stopped or 30-minute timeout."
            ),
        }
        description = descriptions.get(loop_type, descriptions["improve"])

        result = LoopTriggerResult(
            job_id=str(uuid.uuid4()),
            status="ready",
            message=description,
            command=command,
            loop_type=loop_type,
            repo_path=repo_path,
        )
        return JSONResponse(result.model_dump(), status_code=200)

    async def list_loop_runs(self, _request: Request) -> JSONResponse:
        """GET /api/loops/state — actual loop runs."""
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM loops ORDER BY started_at DESC LIMIT 50"
                )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch loop runs: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [
            LoopRun(
                loop_id=str(row["loop_id"]),
                loop_type=str(row["loop_type"]),
                repo_path=str(row["repo_path"]),
                status=str(row["status"]),
                stop_reason=(
                    str(row["stop_reason"]) if row["stop_reason"] is not None else None
                ),
                iteration=int(row["iteration"]),
                total_cost=float(row["total_cost"]),
                avg_score=(
                    float(row["avg_score"]) if row["avg_score"] is not None else None
                ),
                started_at=str(row["started_at"]),
                completed_at=(
                    str(row["completed_at"])
                    if row["completed_at"] is not None
                    else None
                ),
            ).model_dump()
            for row in rows
        ]
        return JSONResponse(items)

    async def list_pending_assets(self, request: Request) -> JSONResponse:
        """GET /api/loops/pending — pending assets awaiting approval."""
        loop_id = request.query_params.get("loop_id")
        try:
            async with get_connection(self._db_path) as conn:
                if loop_id:
                    cursor = await conn.execute(
                        "SELECT * FROM pending_assets"
                        " WHERE loop_id = ?"
                        " ORDER BY created_at DESC",
                        (loop_id,),
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT * FROM pending_assets"
                        " WHERE status = 'pending'"
                        " ORDER BY created_at DESC"
                    )
                rows = await cursor.fetchall()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to fetch pending assets: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        items = [_row_to_pending_asset(row).model_dump() for row in rows]
        return JSONResponse(items)

    # ------------------------------------------------------------------
    # Approval / rejection
    # ------------------------------------------------------------------

    async def approve_pending_asset(self, request: Request) -> JSONResponse:
        """POST /api/loops/pending/{id}/approve — approve and deploy a pending asset."""
        pending_id: str = request.path_params["id"]
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM pending_assets"
                    " WHERE pending_id = ? AND status = 'pending'",
                    (pending_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    return JSONResponse(
                        {"detail": "Pending asset not found or already processed"},
                        status_code=404,
                    )
                await conn.execute(
                    "UPDATE pending_assets SET status = 'approved'"
                    " WHERE pending_id = ?",
                    (pending_id,),
                )
                await _deploy_asset_to_disk(conn, row)
                await conn.commit()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to approve pending asset %s: %s", pending_id, exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        return JSONResponse({"pending_id": pending_id, "status": "approved"})

    async def reject_pending_asset(self, request: Request) -> JSONResponse:
        """POST /api/loops/pending/{id}/reject — reject a pending asset."""
        pending_id: str = request.path_params["id"]
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "UPDATE pending_assets SET status = 'rejected'"
                    " WHERE pending_id = ? AND status = 'pending'",
                    (pending_id,),
                )
                await conn.commit()
                if cursor.rowcount == 0:
                    return JSONResponse(
                        {"detail": "Pending asset not found or already processed"},
                        status_code=404,
                    )
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to reject pending asset %s: %s", pending_id, exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        return JSONResponse({"pending_id": pending_id, "status": "rejected"})

    async def deploy_pending_assets(self, _request: Request) -> JSONResponse:
        """POST /api/loops/pending/deploy — deploy all pending assets to disk."""
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT * FROM pending_assets WHERE status = 'pending'"
                )
                rows = list(await cursor.fetchall())
                for row in rows:
                    await _deploy_asset_to_disk(conn, row)
                await conn.execute(
                    "UPDATE pending_assets SET status = 'approved'"
                    " WHERE status = 'pending'"
                )
                await conn.commit()
                deployed_count = len(rows)
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to deploy pending assets: %s", exc)
            return JSONResponse({"error": "internal error"}, status_code=500)

        return JSONResponse({"deployed_count": deployed_count})

    # ------------------------------------------------------------------
    # Asset actions (evaluate / regenerate / scan)
    # ------------------------------------------------------------------

    async def evaluate_asset(self, request: Request) -> JSONResponse:
        """POST /api/assets/{id}/evaluate — trigger evaluation for a single asset."""
        asset_path: str = request.path_params["id"]

        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT repo_path FROM evaluations"
                    " WHERE asset_path = ?"
                    " ORDER BY evaluated_at DESC LIMIT 1",
                    (asset_path,),
                )
                row = await cursor.fetchone()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to look up asset for evaluation: %s", exc)
            return JSONResponse(
                EvaluateResult(
                    asset_path=asset_path,
                    quality_score=None,
                    status="error",
                    message="Database error",
                ).model_dump(),
                status_code=500,
            )

        if not row:
            return JSONResponse(
                EvaluateResult(
                    asset_path=asset_path,
                    quality_score=None,
                    status="error",
                    message="Asset not found in evaluations",
                ).model_dump(),
                status_code=404,
            )

        repo_path = Path(str(row["repo_path"]))
        try:
            from reagent.evaluation.evaluator import evaluate_repo

            report = await asyncio.to_thread(
                evaluate_repo, repo_path, None, None, self._db_path
            )
            # Find the matching asset's new score
            score: float | None = None
            for metric in report.asset_metrics:
                name_match = metric.name == Path(asset_path).stem
                if metric.asset_id == asset_path or name_match:
                    score = metric.quality_score
                    break
            return JSONResponse(
                EvaluateResult(
                    asset_path=asset_path,
                    quality_score=score,
                    status="evaluated",
                    message="Evaluation complete",
                ).model_dump()
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Evaluation failed for %s: %s", asset_path, exc)
            return JSONResponse(
                EvaluateResult(
                    asset_path=asset_path,
                    quality_score=None,
                    status="error",
                    message=f"Evaluation failed: {exc}",
                ).model_dump(),
                status_code=500,
            )

    async def regenerate_asset(self, request: Request) -> JSONResponse:
        """POST /api/assets/{id}/regenerate — regenerate an asset using LLM."""
        asset_path: str = request.path_params["id"]

        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT repo_path FROM evaluations"
                    " WHERE asset_path = ?"
                    " ORDER BY evaluated_at DESC LIMIT 1",
                    (asset_path,),
                )
                row = await cursor.fetchone()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to look up asset for regeneration: %s", exc)
            return JSONResponse(
                RegenerateResult(
                    asset_path=asset_path,
                    status="error",
                    message="Database error",
                ).model_dump(),
                status_code=500,
            )

        if not row:
            return JSONResponse(
                RegenerateResult(
                    asset_path=asset_path,
                    status="error",
                    message="Asset not found in evaluations",
                ).model_dump(),
                status_code=404,
            )

        repo_path = Path(str(row["repo_path"]))
        resolved = _resolve_asset_path(asset_path, str(repo_path))
        if resolved is None:
            return JSONResponse(
                RegenerateResult(
                    asset_path=asset_path,
                    status="error",
                    message="Asset file not found on disk",
                ).model_dump(),
                status_code=404,
            )

        try:
            from reagent.creation.creator import regenerate_asset as _regenerate

            draft = await asyncio.to_thread(_regenerate, resolved, repo_path)

            # Check if LLM generation was used or fell back to template
            gen_meta = getattr(draft, "generation_metadata", None)
            used_llm = gen_meta is not None and getattr(gen_meta, "tier", "") == "llm"

            if not used_llm:
                # Template fallback means no LLM provider was available
                return JSONResponse(
                    RegenerateResult(
                        asset_path=asset_path,
                        status="no_llm",
                        message=(
                            "No LLM provider available — configure an API key"
                            " (ANTHROPIC_API_KEY, OPENAI_API_KEY, or"
                            " GOOGLE_API_KEY) to enable regeneration"
                        ),
                    ).model_dump()
                )

            # Persist the regenerated draft as a pending asset for approval
            pending_id = uuid.uuid4().hex
            now = datetime.now(UTC).isoformat()
            try:
                async with get_connection(self._db_path) as conn:
                    # Read existing content for diff comparison
                    prev_content: str | None = None
                    try:
                        prev_content = resolved.read_text(encoding="utf-8")
                    except OSError:
                        pass

                    await conn.execute(
                        """
                        INSERT INTO pending_assets
                            (pending_id, asset_type, asset_name, file_path,
                             content, previous_content, previous_score,
                             new_score, generation_method, loop_id, iteration,
                             created_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            pending_id,
                            draft.asset_type,
                            draft.name,
                            str(resolved),
                            draft.content,
                            prev_content,
                            None,
                            _UNEVALUATED_SCORE,
                            "regenerate",
                            "manual",
                            0,
                            now,
                            "pending",
                        ),
                    )
                    await conn.commit()
            except (aiosqlite.Error, OSError) as db_exc:
                logger.warning("Failed to persist regenerated draft: %s", db_exc)

            return JSONResponse(
                RegenerateResult(
                    asset_path=asset_path,
                    status="regenerated",
                    message=(
                        f"Regenerated {draft.name} ({draft.asset_type})"
                        " — pending approval"
                    ),
                ).model_dump()
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Regeneration failed for %s: %s", asset_path, exc)
            return JSONResponse(
                RegenerateResult(
                    asset_path=asset_path,
                    status="error",
                    message=f"Regeneration failed: {exc}",
                ).model_dump(),
                status_code=500,
            )

    async def scan_asset(self, request: Request) -> JSONResponse:
        """POST /api/assets/{id}/scan — security scan a single asset."""
        asset_path: str = request.path_params["id"]

        # Look up repo_path for resolution
        try:
            async with get_connection(self._db_path) as conn:
                cursor = await conn.execute(
                    "SELECT repo_path FROM evaluations"
                    " WHERE asset_path = ?"
                    " ORDER BY evaluated_at DESC LIMIT 1",
                    (asset_path,),
                )
                row = await cursor.fetchone()
        except (aiosqlite.Error, OSError) as exc:
            logger.warning("Failed to look up asset for scan: %s", exc)
            return JSONResponse(
                ScanResult(
                    asset_path=asset_path,
                    findings=[],
                    status="error",
                ).model_dump(),
                status_code=500,
            )

        repo_path = str(row["repo_path"]) if row else ""
        resolved = _resolve_asset_path(asset_path, repo_path)
        if resolved is None:
            return JSONResponse(
                ScanResult(
                    asset_path=asset_path,
                    findings=[],
                    status="file_not_found",
                ).model_dump(),
                status_code=404,
            )

        try:
            from reagent.security.scanner import scan_file

            report = await asyncio.to_thread(scan_file, resolved)
            findings = [
                {
                    "severity": f.severity.value,
                    "message": f.description,
                    "line": str(f.line_number),
                    "rule_id": f.rule_id,
                    "matched_text": f.matched_text,
                }
                for f in report.findings
            ]

            # Persist scan results for audit trail
            try:
                scan_id = uuid.uuid4().hex
                now = datetime.now(UTC).isoformat()

                async with get_connection(self._db_path) as conn:
                    await conn.execute(
                        """
                        INSERT INTO security_scans
                            (scan_id, asset_path, repo_path, findings_json,
                             finding_count, scanned_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scan_id,
                            asset_path,
                            repo_path,
                            json.dumps(findings),
                            len(findings),
                            now,
                        ),
                    )
                    await conn.commit()
            except (aiosqlite.Error, OSError) as db_exc:
                logger.warning("Failed to persist scan results: %s", db_exc)

            return JSONResponse(
                ScanResult(
                    asset_path=asset_path,
                    findings=findings,
                    status="scanned",
                ).model_dump()
            )
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("Security scan failed for %s: %s", asset_path, exc)
            return JSONResponse(
                ScanResult(
                    asset_path=asset_path,
                    findings=[],
                    status="error",
                ).model_dump(),
                status_code=500,
            )


async def _fetch_cost_summary(conn: Any) -> Any:  # aiosqlite.Row
    """Fetch aggregate cost summary from cost_entries."""
    row = await conn.execute(
        """
        SELECT
            COALESCE(SUM(cost_usd), 0.0)                           AS total_usd,
            COUNT(*)                                                AS entry_count,
            SUM(CASE WHEN was_fallback = 0 THEN 1 ELSE 0 END)      AS cache_count
        FROM cost_entries
        """
    )
    return await row.fetchone()


async def _fetch_cost_by_group(conn: Any, group_col: str) -> dict[str, float]:
    """Fetch SUM(cost_usd) grouped by a column name."""
    if group_col not in _ALLOWED_GROUP_COLS:
        raise ValueError(f"Invalid group column: {group_col!r}")
    cursor = await conn.execute(
        f"SELECT {group_col}, COALESCE(SUM(cost_usd), 0.0) AS total"  # noqa: S608
        " FROM cost_entries GROUP BY 1"
    )
    rows = await cursor.fetchall()
    return {str(r[0]): float(r[1]) for r in rows}


def _row_to_cost_entry(row: Any) -> CostEntry:
    """Convert an aiosqlite Row to a CostEntry model."""
    return CostEntry(
        cost_id=str(row["cost_id"]),
        timestamp=str(row["timestamp"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        asset_type=str(row["asset_type"]),
        asset_name=str(row["asset_name"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        cost_usd=float(row["cost_usd"]),
        latency_ms=int(row["latency_ms"]),
        tier=str(row["tier"]),
        was_fallback=bool(int(row["was_fallback"])),
    )


def _row_to_pending_asset(row: Any) -> PendingAssetRow:
    """Convert an aiosqlite Row to a PendingAssetRow model."""
    return PendingAssetRow(
        pending_id=str(row["pending_id"]),
        asset_type=str(row["asset_type"]),
        asset_name=str(row["asset_name"]),
        file_path=str(row["file_path"]),
        content=str(row["content"]),
        previous_content=(
            str(row["previous_content"])
            if row["previous_content"] is not None
            else None
        ),
        previous_score=(
            float(row["previous_score"]) if row["previous_score"] is not None else None
        ),
        new_score=float(row["new_score"]),
        generation_method=str(row["generation_method"]),
        loop_id=str(row["loop_id"]),
        iteration=int(row["iteration"]),
        created_at=str(row["created_at"]),
        status=str(row["status"]),
    )


async def _deploy_asset_to_disk(
    conn: Any,
    row: Any,
) -> None:
    """Write an approved asset to disk and record an evaluation.

    Args:
        conn: Open aiosqlite connection (caller manages the transaction).
        row: A pending_assets DB row.
    """
    raw_path = Path(str(row["file_path"]))
    content = str(row["content"])
    asset_type = str(row["asset_type"])
    asset_name = str(row["asset_name"])
    new_score = float(row["new_score"])
    loop_id = str(row["loop_id"])

    # Determine repo_path from the loop record
    repo_cursor = await conn.execute(
        "SELECT repo_path FROM loops WHERE loop_id = ?", (loop_id,)
    )
    repo_row = await repo_cursor.fetchone()
    repo_path = str(repo_row["repo_path"]) if repo_row else ""

    # Resolve file_path: if relative, anchor under repo_path/.claude/
    if raw_path.is_absolute():
        file_path = raw_path
    elif repo_path:
        file_path = Path(repo_path) / ".claude" / raw_path
    else:
        logger.warning(
            "Cannot deploy %s: no repo_path and file_path is relative",
            raw_path,
        )
        return

    # Guard against path traversal (e.g. ../../etc/passwd)
    if repo_path and not file_path.resolve().is_relative_to(Path(repo_path).resolve()):
        logger.warning(
            "Blocked path traversal: %s escapes repo %s", file_path, repo_path
        )
        return

    # Write asset content to disk (run blocking I/O in thread)

    def _write_file() -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_write_file)
    logger.info("Deployed asset to %s", file_path)

    # Insert an evaluation record so the asset appears on the Assets page
    eval_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        """
        INSERT INTO evaluations
            (evaluation_id, asset_path, asset_type, asset_name,
             quality_score, issues_json, evaluated_at, repo_path)
        VALUES (?, ?, ?, ?, ?, '[]', ?, ?)
        """,
        (eval_id, str(file_path), asset_type, asset_name, new_score, now, repo_path),
    )


def _build_provider_list_from_env() -> list[ProviderStatus]:
    """Build provider status from env vars only (no config import needed)."""
    providers: list[ProviderStatus] = []
    for name, default_model in _DEFAULT_MODELS.items():
        providers.append(_make_provider_status(name, default_model))
    return providers


def _make_provider_status(provider: str, model: str) -> ProviderStatus:
    """Create a ProviderStatus for one provider."""
    env_key = _PROVIDER_ENV_KEYS_WITH_NONE.get(provider)
    if env_key is None:
        # e.g. ollama — no key needed
        key_configured = True
    else:
        raw = os.environ.get(env_key, "")
        key_configured = bool(raw)
        if not key_configured:
            logger.debug("Provider %s: env var %s not set", provider, env_key)
    return ProviderStatus(
        provider=provider,
        model=model,
        available=key_configured,
        key_configured=key_configured,
    )
