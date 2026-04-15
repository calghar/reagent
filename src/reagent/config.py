from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ScanConfig(BaseModel):
    roots: list[Path] = Field(default_factory=lambda: [Path.home() / "Development"])
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["node_modules", ".git", "__pycache__", "venv", ".venv"]
    )
    max_depth: int = 5


class CatalogConfig(BaseModel):
    path: Path = Field(
        default_factory=lambda: Path.home() / ".reagent" / "catalog.jsonl"
    )
    auto_refresh: bool = True
    refresh_interval: int = 3600


class TelemetryConfig(BaseModel):
    enabled: bool = True
    event_store: Path = Field(
        default_factory=lambda: Path.home() / ".reagent" / "events.jsonl"
    )
    claude_projects_path: Path = Field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )
    hash_file_paths: bool = False
    exclude_content: bool = False
    retention_days: int = 90


class VersioningConfig(BaseModel):
    strategy: str = "auto"
    snapshot_retention: int = 90
    max_snapshots_per_asset: int = 50


class SecurityConfig(BaseModel):
    rules_path: Path | None = None
    auto_scan: bool = True
    block_on_critical: bool = True


class CodeIntelConfig(BaseModel):
    # TODO: Wire to MCP server integration when gitnexus support is implemented.
    enabled: bool = False
    gitnexus_command: str = "npx -y gitnexus@latest mcp"
    timeout: int = 30
    fallback_on_error: bool = True


class LogConfig(BaseModel):
    level: str = "WARNING"
    file: Path = Field(default_factory=lambda: Path.home() / ".reagent" / "reagent.log")
    max_bytes: int = 5_000_000
    backup_count: int = 3


class HarnessConfig(BaseModel):
    """Configuration for cross-harness asset generation.

    Uses plain strings rather than the HarnessFormat enum to avoid
    circular import issues between config and harness packages.
    """

    default: str = "claude-code"
    generate: list[str] = Field(default_factory=lambda: ["claude-code"])


class InstinctTuning(BaseModel):
    """Tunable constants for instinct scoring and evolution."""

    category_match_boost: float = 1.5
    recency_half_life_days: float = 180.0
    name_overlap_factor: float = 0.1
    confidence_increment: float = 0.1
    confidence_divisor: int = 8
    confidence_cap: float = 0.8
    correction_rate_threshold: float = 0.15
    quality_score_threshold: int = 70
    confidence_reward: float = 0.05
    confidence_penalty: float = 0.1
    min_use_count_for_promotion: int = 5
    default_top_k: int = 5
    trust_tier_weights: dict[str, float] = Field(
        default_factory=lambda: {"managed": 0.8, "workspace": 0.6}
    )


class EvaluationTuning(BaseModel):
    """Tunable normalization constants for quality evaluation."""

    max_invocations_per_week: float = 5.0
    max_turn_efficiency: float = 19.0
    staleness_window_days: float = 90.0
    grade_a_threshold: int = 90
    grade_b_threshold: int = 80
    grade_c_threshold: int = 60
    grade_d_threshold: int = 40
    critic_revision_threshold: int = 7


class RouterTuning(BaseModel):
    """Tunable timing constants for the provider router."""

    health_check_interval_seconds: int = 60
    circuit_breaker_threshold: int = 3
    circuit_breaker_recovery_seconds: int = 300


class CacheTuning(BaseModel):
    """Tunable constants for the generation cache."""

    default_max_age_days: int = 7


class TuningConfig(BaseModel):
    """Top-level tuning configuration aggregating all sub-models."""

    instinct: InstinctTuning = Field(default_factory=InstinctTuning)
    evaluation: EvaluationTuning = Field(default_factory=EvaluationTuning)
    router: RouterTuning = Field(default_factory=RouterTuning)
    cache: CacheTuning = Field(default_factory=CacheTuning)


class ReagentConfig(BaseModel):
    log: LogConfig = Field(default_factory=LogConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    code_intel: CodeIntelConfig = Field(default_factory=CodeIntelConfig)
    llm: Any = Field(default=None)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    tuning: TuningConfig = Field(default_factory=TuningConfig)

    @model_validator(mode="after")
    def _init_llm(self) -> ReagentConfig:
        from reagent.llm.config import LLMConfig

        if self.llm is None:
            self.llm = LLMConfig()
        elif isinstance(self.llm, dict):
            self.llm = LLMConfig(**self.llm)
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Load configuration from YAML file, falling back to defaults.

        Args:
            path: Optional path to the config YAML file. Defaults to
                ``~/.reagent/config.yaml``.

        Returns:
            Loaded configuration, or defaults if the file doesn't exist.
        """
        config_path = path or Path.home() / ".reagent" / "config.yaml"
        if not config_path.exists():
            return cls()

        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
