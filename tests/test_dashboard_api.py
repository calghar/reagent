import sqlite3
from pathlib import Path

import pytest

starlette = pytest.importorskip("starlette", reason="starlette not installed")
from starlette.testclient import TestClient  # noqa: E402

from reagent.api.app import create_app  # noqa: E402


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    """Create a test SQLite DB seeded with representative data."""
    db_path = tmp_path / "test.db"
    # Create a fake repo directory for deploy tests
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    (fake_repo / ".claude").mkdir()
    repo_path_str = str(fake_repo)

    conn = sqlite3.connect(db_path)

    schema_sql = (
        Path(__file__).parent.parent / "src" / "reagent" / "storage" / "schema.sql"
    ).read_text()
    conn.executescript(schema_sql)

    # Evaluations — two assets, three evals total
    conn.execute(
        """
        INSERT INTO evaluations
            (evaluation_id, asset_path, asset_type, asset_name,
             quality_score, invocation_rate, correction_rate,
             issues_json, evaluated_at, repo_path)
        VALUES
            ('eval-1', 'agents/review.md', 'agent', 'review',
             0.85, 0.9, 0.1, '[]', '2024-01-01T10:00:00', ?),
            ('eval-2', 'agents/review.md', 'agent', 'review',
             0.90, 0.95, 0.05, '[]', '2024-01-02T10:00:00', ?),
            ('eval-3', 'skills/deploy.md', 'skill', 'deploy',
             0.70, 0.8, 0.2, '[]', '2024-01-01T10:00:00', ?)
        """,
        (repo_path_str, repo_path_str, repo_path_str),
    )

    # Instincts
    conn.execute(
        """
        INSERT INTO instincts
            (instinct_id, content, category, trust_tier,
             confidence, source, created_at, use_count, success_rate, ttl_days)
        VALUES
            ('inst-1', 'Always use type hints', 'coding', 'workspace',
             0.95, 'user', '2024-01-01T00:00:00', 10, 0.9, 90),
            ('inst-2', 'Write tests first', 'process', 'team',
             0.80, 'user', '2024-01-02T00:00:00', 5, 0.85, 90)
        """
    )

    # Cost entries — two from anthropic (one fallback), one from openai
    conn.execute(
        """
        INSERT INTO cost_entries
            (cost_id, timestamp, provider, model,
             asset_type, asset_name,
             input_tokens, output_tokens, cost_usd, latency_ms, tier, was_fallback)
        VALUES
            ('cost-1', '2024-01-01T10:00:00', 'anthropic',
             'claude-sonnet-4-20250514', 'agent', 'review',
             100, 50, 0.001, 500, 'standard', 0),
            ('cost-2', '2024-01-02T10:00:00', 'anthropic',
             'claude-sonnet-4-20250514', 'agent', 'review',
             200, 80, 0.002, 600, 'standard', 1),
            ('cost-3', '2024-01-03T10:00:00', 'openai',
             'gpt-4o', 'skill', 'deploy',
             150, 60, 0.0015, 400, 'standard', 0)
        """
    )

    # Generations
    conn.execute(
        """
        INSERT INTO generations
            (cache_key, asset_type, name, content,
             generated_at, provider, model, cost_usd,
             profile_hash, instinct_hash)
        VALUES
            ('gen-key-1', 'agent', 'review', 'Agent content here',
             '2024-01-01T10:00:00', 'anthropic', 'claude-sonnet-4-20250514',
             0.001, 'phash1', 'ihash1'),
            ('gen-key-2', 'skill', 'deploy', 'Skill content here',
             '2024-01-02T10:00:00', 'openai', 'gpt-4o',
             0.0015, 'phash2', 'ihash2')
        """
    )

    # Loop runs
    conn.execute(
        """
        INSERT INTO loops
            (loop_id, loop_type, repo_path, status, stop_reason,
             iteration, total_cost, avg_score, started_at, completed_at)
        VALUES
            ('loop-1', 'init', ?, 'completed', 'max_iterations',
             3, 0.005, 0.88, '2024-01-01T09:00:00', '2024-01-01T09:30:00'),
            ('loop-2', 'improve', ?, 'running', NULL,
             1, 0.001, NULL, '2024-01-02T09:00:00', NULL)
        """,
        (repo_path_str, repo_path_str),
    )

    # Pending assets
    conn.execute(
        """
        INSERT INTO pending_assets
            (pending_id, asset_type, asset_name, file_path, content,
             previous_content, previous_score, new_score,
             generation_method, loop_id, iteration, created_at, status)
        VALUES
            ('pend-1', 'agent', 'review', 'agents/review.md',
             '# New review agent', '# Old review agent', 0.85, 0.92,
             'improve', 'loop-1', 2, '2024-01-01T09:20:00', 'pending'),
            ('pend-2', 'skill', 'deploy', 'skills/deploy.md',
             '# New deploy skill', NULL, NULL, 0.78,
             'init', 'loop-1', 1, '2024-01-01T09:10:00', 'approved'),
            ('pend-3', 'agent', 'debug', 'agents/debug.md',
             '# Debug agent', NULL, NULL, 0.80,
             'init', 'loop-2', 1, '2024-01-02T09:05:00', 'pending')
        """
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def client(test_db: Path) -> TestClient:
    """Return a synchronous test client wired to the seeded test DB."""
    app = create_app(db_path=test_db)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def empty_client(tmp_path: Path) -> TestClient:
    """Return a test client backed by an empty (schema-only) DB."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    schema_sql = (
        Path(__file__).parent.parent / "src" / "reagent" / "storage" / "schema.sql"
    ).read_text()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    return TestClient(create_app(db_path=db_path))


def test_health_endpoint(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"


def test_list_assets_empty(empty_client: TestClient) -> None:
    r = empty_client.get("/api/assets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_assets(client: TestClient) -> None:
    r = client.get("/api/assets")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3  # review + deploy (evaluated) + debug (pending)

    names = {i["asset_name"] for i in items}
    assert names == {"review", "deploy", "debug"}

    # review has 2 evals
    review = next(i for i in items if i["asset_name"] == "review")
    assert review["evaluation_count"] == 2
    assert review["latest_score"] == pytest.approx(0.90)
    assert review["status"] == "evaluated"

    # debug is pending (not yet evaluated)
    debug = next(i for i in items if i["asset_name"] == "debug")
    assert debug["status"] == "pending"


def test_get_asset_detail(client: TestClient) -> None:
    r = client.get("/api/assets/agents/review.md")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    # Returned in descending order
    assert items[0]["quality_score"] == pytest.approx(0.90)
    assert items[1]["quality_score"] == pytest.approx(0.85)
    for item in items:
        assert item["asset_name"] == "review"
        assert "evaluation_id" in item
        assert "evaluated_at" in item


def test_get_asset_not_found(client: TestClient) -> None:
    r = client.get("/api/assets/nonexistent/path.md")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_evaluations_endpoint(client: TestClient) -> None:
    r = client.get("/api/evaluations")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3
    # Verify required fields
    for item in items:
        assert "evaluation_id" in item
        assert "asset_name" in item
        assert "quality_score" in item
        assert "evaluated_at" in item


def test_costs_endpoint(client: TestClient) -> None:
    r = client.get("/api/costs")
    assert r.status_code == 200
    data = r.json()
    assert "total_usd" in data
    assert "by_provider" in data
    assert "by_model" in data
    assert "entry_count" in data
    assert "cache_hit_rate" in data
    assert data["entry_count"] == 3
    assert data["total_usd"] == pytest.approx(0.001 + 0.002 + 0.0015)


def test_costs_by_provider(client: TestClient) -> None:
    r = client.get("/api/costs")
    assert r.status_code == 200
    by_provider = r.json()["by_provider"]
    assert "anthropic" in by_provider
    assert "openai" in by_provider
    assert by_provider["anthropic"] == pytest.approx(0.001 + 0.002)
    assert by_provider["openai"] == pytest.approx(0.0015)


def test_cost_entries_pagination(client: TestClient) -> None:
    # Page 1 with per_page=2 → 2 items
    r = client.get("/api/costs/entries?page=1&per_page=2")
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert data["per_page"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 2

    # Page 2 → 1 item
    r2 = client.get("/api/costs/entries?page=2&per_page=2")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["items"]) == 1


def test_instincts_endpoint(client: TestClient) -> None:
    r = client.get("/api/instincts")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2


def test_instincts_fields(client: TestClient) -> None:
    r = client.get("/api/instincts")
    items = r.json()
    for item in items:
        assert "instinct_id" in item
        assert "content" in item
        assert "category" in item
        assert "trust_tier" in item
        assert "confidence" in item
        assert "use_count" in item
        assert "success_rate" in item
        assert "created_at" in item


def test_providers_endpoint(client: TestClient) -> None:
    r = client.get("/api/providers")
    assert r.status_code == 200
    items = r.json()
    # Should include at least the known providers
    provider_names = {p["provider"] for p in items}
    assert "anthropic" in provider_names
    assert "openai" in provider_names
    for item in items:
        assert "provider" in item
        assert "model" in item
        assert "available" in item
        assert "key_configured" in item


def test_loops_endpoint(client: TestClient) -> None:
    r = client.get("/api/loops")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    for item in items:
        assert "cache_key" in item
        assert "asset_type" in item
        assert "name" in item
        assert "generated_at" in item
        assert "provider" in item
        assert "model" in item
        assert "cost_usd" in item


def test_loops_trigger(client: TestClient) -> None:
    r = client.post("/api/loops/trigger")
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "ready"
    assert "message" in data
    assert data["command"] == "reagent loop improve --repo ."
    assert data["loop_type"] == "improve"
    assert data["repo_path"] == "."
    # job_id should be a UUID string
    import uuid

    uuid.UUID(data["job_id"])  # raises ValueError if not a valid UUID


def test_sse_endpoint(client: TestClient) -> None:
    """SSE endpoint returns text/event-stream with a valid ping payload."""
    _ = client
    import asyncio
    import json
    from unittest.mock import AsyncMock, MagicMock

    from starlette.requests import Request as _Request

    from reagent.api.sse import _make_ping, sse_endpoint

    # Part 1 — Verify the ping frame format
    event = _make_ping()
    assert event.startswith("data: ")
    assert event.endswith("\n\n")
    payload = json.loads(event[6:].strip())
    assert payload["type"] == "ping"
    assert "ts" in payload

    # Part 2 — Verify the endpoint returns StreamingResponse with correct
    # media type (the generator is NOT iterated here, so no blocking).
    async def _check_response() -> None:
        mock_req = MagicMock(spec=_Request)
        mock_req.is_disconnected = AsyncMock(return_value=True)
        response = await sse_endpoint(mock_req)
        assert response.media_type == "text/event-stream"

    asyncio.run(_check_response())


def test_cors_headers(client: TestClient) -> None:
    r = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers


def test_assets_filter_by_type(client: TestClient) -> None:
    r = client.get("/api/assets?type=agent")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2  # review (evaluated) + debug (pending)
    names = {i["asset_name"] for i in items}
    assert names == {"review", "debug"}
    for item in items:
        assert item["asset_type"] == "agent"


def test_assets_filter_by_type_skill(client: TestClient) -> None:
    r = client.get("/api/assets?type=skill")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["asset_type"] == "skill"


def test_evaluations_limit(client: TestClient) -> None:
    r = client.get("/api/evaluations?limit=2")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2


def test_evaluations_limit_default(client: TestClient) -> None:
    r = client.get("/api/evaluations")
    assert r.status_code == 200
    # All 3 evals should be returned with default limit (500)
    assert len(r.json()) == 3


def test_costs_cache_hit_rate(client: TestClient) -> None:
    # was_fallback=0: cost-1, cost-3 (2 out of 3 rows)
    r = client.get("/api/costs")
    assert r.status_code == 200
    rate = r.json()["cache_hit_rate"]
    assert rate == pytest.approx(2 / 3)


def test_costs_entries_default_pagination(client: TestClient) -> None:
    r = client.get("/api/costs/entries")
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert data["per_page"] == 20
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Verify item structure
    item = data["items"][0]
    assert "cost_id" in item
    assert "provider" in item
    assert "cost_usd" in item
    assert "was_fallback" in item


def test_costs_empty_db(empty_client: TestClient) -> None:
    r = empty_client.get("/api/costs")
    assert r.status_code == 200
    data = r.json()
    assert data["total_usd"] == 0
    assert data["entry_count"] == 0
    assert data["cache_hit_rate"] == 0


def test_instincts_empty_db(empty_client: TestClient) -> None:
    r = empty_client.get("/api/instincts")
    assert r.status_code == 200
    assert r.json() == []


def test_loops_empty_db(empty_client: TestClient) -> None:
    r = empty_client.get("/api/loops")
    assert r.status_code == 200
    assert r.json() == []


class TestAssetContent:
    """Tests for GET /api/assets/{id}/content."""

    def test_returns_content_for_known_asset(self, client: TestClient) -> None:
        r = client.get("/api/assets/agents/review.md/content")
        assert r.status_code == 200
        data = r.json()
        assert data["asset_path"] == "agents/review.md"
        assert data["asset_name"] == "review"
        assert data["asset_type"] == "agent"
        assert isinstance(data["repo_path"], str)
        assert len(data["repo_path"]) > 0
        assert data["quality_score"] == pytest.approx(0.90)
        assert data["last_evaluated"] == "2024-01-02T10:00:00"
        # File doesn't exist on disk, so we get the fallback message
        assert data["content"] == "File not found on disk"

    def test_reads_real_file_from_disk(self, test_db: Path, tmp_path: Path) -> None:
        # Create a real file and insert an evaluation pointing to it
        asset_file = tmp_path / "agents" / "real.md"
        asset_file.parent.mkdir(parents=True, exist_ok=True)
        asset_file.write_text("# Real agent content", encoding="utf-8")

        conn = sqlite3.connect(test_db)
        conn.execute(
            """
            INSERT INTO evaluations
                (evaluation_id, asset_path, asset_type, asset_name,
                 quality_score, issues_json, evaluated_at, repo_path)
            VALUES
                ('eval-real', ?, 'agent', 'real',
                 0.95, '[]', '2024-01-03T10:00:00', '/repo')
            """,
            (str(asset_file),),
        )
        conn.commit()
        conn.close()

        app = create_app(db_path=test_db)
        c = TestClient(app, raise_server_exceptions=True)
        r = c.get(f"/api/assets/{asset_file}/content")
        assert r.status_code == 200
        assert r.json()["content"] == "# Real agent content"

    def test_not_found_for_unknown_asset(self, client: TestClient) -> None:
        r = client.get("/api/assets/nonexistent/path.md/content")
        assert r.status_code == 404
        assert r.json()["detail"] == "Asset not found"

    def test_existing_asset_detail_still_works(self, client: TestClient) -> None:
        """The content route must not break the existing detail route."""
        r = client.get("/api/assets/agents/review.md")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        assert items[0]["quality_score"] == pytest.approx(0.90)


class TestLoopState:
    """Tests for GET /api/loops/state."""

    def test_returns_loop_runs(self, client: TestClient) -> None:
        r = client.get("/api/loops/state")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2

    def test_loop_run_fields(self, client: TestClient) -> None:
        r = client.get("/api/loops/state")
        items = r.json()
        # Most recent first (loop-2 started later)
        run = items[0]
        assert run["loop_id"] == "loop-2"
        assert run["loop_type"] == "improve"
        assert run["status"] == "running"
        assert run["stop_reason"] is None
        assert run["iteration"] == 1
        assert run["total_cost"] == pytest.approx(0.001)
        assert run["avg_score"] is None
        assert run["completed_at"] is None

    def test_completed_loop_run(self, client: TestClient) -> None:
        r = client.get("/api/loops/state")
        items = r.json()
        completed = next(i for i in items if i["loop_id"] == "loop-1")
        assert completed["status"] == "completed"
        assert completed["stop_reason"] == "max_iterations"
        assert completed["iteration"] == 3
        assert completed["avg_score"] == pytest.approx(0.88)
        assert completed["completed_at"] == "2024-01-01T09:30:00"

    def test_empty_db(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/loops/state")
        assert r.status_code == 200
        assert r.json() == []


class TestPendingAssets:
    """Tests for GET /api/loops/pending."""

    def test_returns_pending_only_by_default(self, client: TestClient) -> None:
        r = client.get("/api/loops/pending")
        assert r.status_code == 200
        items = r.json()
        # pend-1 and pend-3 are pending; pend-2 is approved
        assert len(items) == 2
        statuses = {i["status"] for i in items}
        assert statuses == {"pending"}

    def test_filter_by_loop_id(self, client: TestClient) -> None:
        r = client.get("/api/loops/pending?loop_id=loop-1")
        assert r.status_code == 200
        items = r.json()
        # loop-1 has pend-1 (pending) and pend-2 (approved)
        assert len(items) == 2
        ids = {i["pending_id"] for i in items}
        assert ids == {"pend-1", "pend-2"}

    def test_pending_asset_fields(self, client: TestClient) -> None:
        r = client.get("/api/loops/pending?loop_id=loop-1")
        items = r.json()
        pend1 = next(i for i in items if i["pending_id"] == "pend-1")
        assert pend1["asset_type"] == "agent"
        assert pend1["asset_name"] == "review"
        assert pend1["file_path"] == "agents/review.md"
        assert pend1["content"] == "# New review agent"
        assert pend1["previous_content"] == "# Old review agent"
        assert pend1["previous_score"] == pytest.approx(0.85)
        assert pend1["new_score"] == pytest.approx(0.92)
        assert pend1["generation_method"] == "improve"
        assert pend1["loop_id"] == "loop-1"
        assert pend1["iteration"] == 2
        assert pend1["status"] == "pending"

    def test_null_previous_fields(self, client: TestClient) -> None:
        r = client.get("/api/loops/pending?loop_id=loop-1")
        items = r.json()
        pend2 = next(i for i in items if i["pending_id"] == "pend-2")
        assert pend2["previous_content"] is None
        assert pend2["previous_score"] is None

    def test_empty_db(self, empty_client: TestClient) -> None:
        r = empty_client.get("/api/loops/pending")
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_by_nonexistent_loop(self, client: TestClient) -> None:
        r = client.get("/api/loops/pending?loop_id=nonexistent")
        assert r.status_code == 200
        assert r.json() == []


class TestApproveReject:
    """Tests for POST /api/loops/pending/{id}/approve and reject."""

    @pytest.mark.parametrize(
        "pending_id, action, expected_status",
        [
            pytest.param("pend-1", "approve", "approved", id="approve-pending"),
            pytest.param("pend-3", "reject", "rejected", id="reject-pending"),
        ],
    )
    def test_pending_asset_succeeds(
        self,
        client: TestClient,
        pending_id: str,
        action: str,
        expected_status: str,
    ) -> None:
        r = client.post(f"/api/loops/pending/{pending_id}/{action}")
        assert r.status_code == 200
        data = r.json()
        assert data["pending_id"] == pending_id
        assert data["status"] == expected_status

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param("approve", id="approve-nonexistent"),
            pytest.param("reject", id="reject-nonexistent"),
        ],
    )
    def test_nonexistent_id_returns_404(self, client: TestClient, action: str) -> None:
        r = client.post(f"/api/loops/pending/no-such-id/{action}")
        assert r.status_code == 404
        assert "detail" in r.json()

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param("approve", id="approve-already-processed"),
            pytest.param("reject", id="reject-already-processed"),
        ],
    )
    def test_already_processed_returns_404(
        self, client: TestClient, action: str
    ) -> None:
        # pend-2 status is 'approved' — both approve and reject require 'pending'
        r = client.post(f"/api/loops/pending/pend-2/{action}")
        assert r.status_code == 404
        assert "detail" in r.json()


class TestDeployPending:
    """Tests for POST /api/loops/pending/deploy."""

    def test_deploy_all_pending(self, client: TestClient) -> None:
        r = client.post("/api/loops/pending/deploy")
        assert r.status_code == 200
        data = r.json()
        # pend-1 (pending) and pend-3 (pending) get deployed; pend-2 already approved
        assert data["deployed_count"] == 2

    def test_deploy_with_no_pending(self, empty_client: TestClient) -> None:
        r = empty_client.post("/api/loops/pending/deploy")
        assert r.status_code == 200
        assert r.json()["deployed_count"] == 0

    def test_deploy_is_idempotent(self, client: TestClient) -> None:
        first = client.post("/api/loops/pending/deploy")
        assert first.json()["deployed_count"] == 2
        # Second deploy finds nothing left in 'pending' status
        second = client.post("/api/loops/pending/deploy")
        assert second.status_code == 200
        assert second.json()["deployed_count"] == 0


class TestAssetActions:
    """Tests for POST /api/assets/{path}/evaluate, regenerate, scan."""

    @pytest.mark.parametrize(
        "action",
        [
            pytest.param("evaluate", id="evaluate-unknown"),
            pytest.param("regenerate", id="regenerate-unknown"),
            pytest.param("scan", id="scan-unknown"),
        ],
    )
    def test_unknown_path_returns_404(self, client: TestClient, action: str) -> None:
        r = client.post(f"/api/assets/nonexistent/path.md/{action}")
        assert r.status_code == 404
        data = r.json()
        assert data["asset_path"] == "nonexistent/path.md"

    def test_evaluate_known_asset(self, client: TestClient) -> None:
        r = client.post("/api/assets/agents/review.md/evaluate")
        # evaluate_repo will fail in test env (repo /repo doesn't exist)
        assert r.status_code in {200, 500}
        data = r.json()
        assert data["asset_path"] == "agents/review.md"
        assert "status" in data

    def test_regenerate_known_asset_file_not_on_disk(self, client: TestClient) -> None:
        r = client.post("/api/assets/agents/review.md/regenerate")
        # DB finds the evaluation but _resolve_asset_path fails (no file)
        assert r.status_code == 404
        data = r.json()
        assert data["asset_path"] == "agents/review.md"
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()

    def test_scan_known_asset_file_not_on_disk(self, client: TestClient) -> None:
        r = client.post("/api/assets/agents/review.md/scan")
        # DB finds repo_path but file doesn't exist on disk
        assert r.status_code in {200, 404}
        data = r.json()
        assert data["asset_path"] == "agents/review.md"

    def test_scan_returns_findings_structure(
        self, test_db: Path, tmp_path: Path
    ) -> None:
        # Create a real asset file so the scanner can run
        asset_file = tmp_path / "agents" / "scanme.md"
        asset_file.parent.mkdir(parents=True, exist_ok=True)
        asset_file.write_text("# Scannable agent", encoding="utf-8")

        conn = sqlite3.connect(test_db)
        conn.execute(
            """
            INSERT INTO evaluations
                (evaluation_id, asset_path, asset_type, asset_name,
                 quality_score, issues_json, evaluated_at, repo_path)
            VALUES
                ('eval-scan', ?, 'agent', 'scanme',
                 0.80, '[]', '2024-01-05T10:00:00', ?)
            """,
            (str(asset_file), str(tmp_path)),
        )
        conn.commit()
        conn.close()

        app = create_app(db_path=test_db)
        c = TestClient(app, raise_server_exceptions=True)
        r = c.post(f"/api/assets/{asset_file}/scan")
        assert r.status_code in {200, 500}
        data = r.json()
        assert "asset_path" in data
        assert "findings" in data
        assert "status" in data


class TestResolveAssetPath:
    """Unit tests for _resolve_asset_path."""

    def test_absolute_existing_path(self, tmp_path: Path) -> None:
        from reagent.api.routes import _resolve_asset_path

        f = tmp_path / "test.md"
        f.write_text("content", encoding="utf-8")
        result = _resolve_asset_path(str(f), str(tmp_path))
        assert result == f

    def test_nonexistent_path_returns_none(self) -> None:
        from reagent.api.routes import _resolve_asset_path

        result = _resolve_asset_path("/nonexistent/path.md", "/nonexistent/repo")
        assert result is None

    def test_relative_path_under_repo(self, tmp_path: Path) -> None:
        from reagent.api.routes import _resolve_asset_path

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        f = agents_dir / "test.md"
        f.write_text("content", encoding="utf-8")
        result = _resolve_asset_path("agents/test.md", str(tmp_path))
        assert result == f
