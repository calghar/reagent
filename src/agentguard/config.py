import logging
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ScanConfig(BaseModel):
    roots: list[Path] = Field(default_factory=lambda: [Path.home() / "Development"])
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["node_modules", ".git", "__pycache__", "venv", ".venv"]
    )
    max_depth: int = 5


class CatalogConfig(BaseModel):
    path: Path = Field(
        default_factory=lambda: Path.home() / ".agentguard" / "catalog.jsonl"
    )
    auto_refresh: bool = True
    refresh_interval: int = 3600


class TelemetryConfig(BaseModel):
    enabled: bool = True
    event_store: Path = Field(
        default_factory=lambda: Path.home() / ".agentguard" / "events.jsonl"
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


class AttestationConfig(BaseModel):
    enabled: bool = True
    signing_key_path: Path = Field(
        default_factory=lambda: Path.home() / ".agentguard" / "keys" / "attestation.key"
    )
    sandbox_timeout_seconds: int = 120
    corpus_path: Path | None = None


class LogConfig(BaseModel):
    level: str = "WARNING"
    file: Path = Field(
        default_factory=lambda: Path.home() / ".agentguard" / "agentguard.log"
    )
    max_bytes: int = 5_000_000
    backup_count: int = 3


class HarnessConfig(BaseModel):
    """Configuration for cross-harness asset generation.

    Uses plain strings rather than the HarnessFormat enum to avoid
    circular import issues between config and harness packages.
    """

    default: str = "claude-code"
    generate: list[str] = Field(default_factory=lambda: ["claude-code"])


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


class TuningConfig(BaseModel):
    """Top-level tuning configuration aggregating all sub-models."""

    evaluation: EvaluationTuning = Field(default_factory=EvaluationTuning)


class AgentGuardConfig(BaseModel):
    log: LogConfig = Field(default_factory=LogConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    attestation: AttestationConfig = Field(default_factory=AttestationConfig)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    tuning: TuningConfig = Field(default_factory=TuningConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> Self:
        """Load configuration from YAML file, falling back to defaults.

        Args:
            path: Optional path to the config YAML file. Defaults to
                ``~/.agentguard/config.yaml``.

        Returns:
            Loaded configuration, or defaults if the file doesn't exist.
        """
        config_path = path or Path.home() / ".agentguard" / "config.yaml"
        if not config_path.exists():
            return cls()

        with config_path.open() as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
