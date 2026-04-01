import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AssetSummary(BaseModel):
    """Summary of a unique asset derived from its latest evaluation."""

    asset_path: str
    asset_type: str
    asset_name: str
    repo_path: str
    latest_score: float
    evaluation_count: int
    last_evaluated: str
    status: str = "evaluated"


class EvaluationPoint(BaseModel):
    """A single evaluation record for time-series charts."""

    evaluation_id: str
    asset_name: str
    asset_type: str
    quality_score: float
    evaluated_at: str
    repo_path: str = ""


class CostSummary(BaseModel):
    """Aggregated cost data for the Cost Monitor page."""

    total_usd: float
    by_provider: dict[str, float]
    by_model: dict[str, float]
    entry_count: int
    cache_hit_rate: float


class CostEntry(BaseModel):
    """A single cost entry row."""

    cost_id: str
    timestamp: str
    provider: str
    model: str
    asset_type: str
    asset_name: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    tier: str
    was_fallback: bool


class CostEntriesPage(BaseModel):
    """Paginated list of cost entries."""

    items: list[CostEntry]
    total: int
    page: int
    per_page: int


class InstinctRow(BaseModel):
    """A single instinct record."""

    instinct_id: str
    content: str
    category: str
    trust_tier: str
    confidence: float
    use_count: int
    success_rate: float
    created_at: str


class ProviderStatus(BaseModel):
    """Status snapshot for a configured LLM provider."""

    provider: str
    model: str
    available: bool
    key_configured: bool


class GenerationRow(BaseModel):
    """A single entry from the generations cache table."""

    cache_key: str
    asset_type: str
    name: str
    generated_at: str
    provider: str
    model: str
    cost_usd: float


class LoopTriggerResult(BaseModel):
    """Result returned when a loop is triggered."""

    job_id: str
    status: str
    message: str
    command: str = ""
    loop_type: str = "improve"
    repo_path: str = "."


class AssetContent(BaseModel):
    """Full file content for a single asset."""

    asset_path: str
    asset_name: str
    asset_type: str
    content: str
    repo_path: str
    quality_score: float | None
    last_evaluated: str | None


class LoopRun(BaseModel):
    """A single autonomous loop run record."""

    loop_id: str
    loop_type: str
    repo_path: str
    status: str
    stop_reason: str | None
    iteration: int
    total_cost: float
    avg_score: float | None
    started_at: str
    completed_at: str | None


class PendingAssetRow(BaseModel):
    """An asset awaiting human approval before deployment."""

    pending_id: str
    asset_type: str
    asset_name: str
    file_path: str
    content: str
    previous_content: str | None
    previous_score: float | None
    new_score: float
    generation_method: str
    loop_id: str
    iteration: int
    created_at: str
    status: str


class EvaluateResult(BaseModel):
    """Result from triggering an asset evaluation."""

    asset_path: str
    quality_score: float | None
    status: str
    message: str


class RegenerateResult(BaseModel):
    """Result from triggering an asset regeneration."""

    asset_path: str
    status: str
    message: str


class ScanResult(BaseModel):
    """Result from a security scan of a single asset."""

    asset_path: str
    findings: list[dict[str, str]]
    status: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    db: str
