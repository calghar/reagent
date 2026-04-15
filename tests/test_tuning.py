"""Tests for tuning configuration models and accessor."""

from __future__ import annotations

from pathlib import Path

import yaml

from reagent._tuning import get_tuning
from reagent.config import (
    CacheTuning,
    EvaluationTuning,
    InstinctTuning,
    ReagentConfig,
    RouterTuning,
    TuningConfig,
)


class TestTuningModels:
    """Validate default values and serialisation of tuning sub-models."""

    def test_instinct_defaults(self) -> None:
        t = InstinctTuning()
        assert t.category_match_boost == 1.5
        assert t.recency_half_life_days == 180.0
        assert t.confidence_divisor == 8
        assert t.confidence_cap == 0.8
        assert t.default_top_k == 5
        assert t.trust_tier_weights == {"managed": 0.8, "workspace": 0.6}

    def test_evaluation_defaults(self) -> None:
        t = EvaluationTuning()
        assert t.max_invocations_per_week == 5.0
        assert t.max_turn_efficiency == 19.0
        assert t.staleness_window_days == 90.0

    def test_router_defaults(self) -> None:
        t = RouterTuning()
        assert t.health_check_interval_seconds == 60
        assert t.circuit_breaker_threshold == 3
        assert t.circuit_breaker_recovery_seconds == 300

    def test_cache_defaults(self) -> None:
        t = CacheTuning()
        assert t.default_max_age_days == 7

    def test_tuning_config_aggregates_all(self) -> None:
        tc = TuningConfig()
        assert isinstance(tc.instinct, InstinctTuning)
        assert isinstance(tc.evaluation, EvaluationTuning)
        assert isinstance(tc.router, RouterTuning)
        assert isinstance(tc.cache, CacheTuning)

    def test_custom_values_override_defaults(self) -> None:
        tc = TuningConfig(
            instinct=InstinctTuning(category_match_boost=2.0),
        )
        assert tc.instinct.category_match_boost == 2.0
        # Other instinct fields keep defaults
        assert tc.instinct.recency_half_life_days == 180.0


class TestReagentConfigTuning:
    """TuningConfig integrates with ReagentConfig."""

    def test_default_reagent_config_has_tuning(self) -> None:
        cfg = ReagentConfig()
        assert isinstance(cfg.tuning, TuningConfig)
        assert cfg.tuning.instinct.category_match_boost == 1.5

    def test_load_from_yaml_with_tuning(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        data = {
            "tuning": {
                "instinct": {"category_match_boost": 3.0, "default_top_k": 10},
                "router": {"circuit_breaker_threshold": 5},
            }
        }
        config_path.write_text(yaml.dump(data))
        cfg = ReagentConfig.load(path=config_path)
        assert cfg.tuning.instinct.category_match_boost == 3.0
        assert cfg.tuning.instinct.default_top_k == 10
        # Untouched fields keep defaults
        assert cfg.tuning.instinct.confidence_cap == 0.8
        assert cfg.tuning.router.circuit_breaker_threshold == 5
        assert cfg.tuning.evaluation.staleness_window_days == 90.0

    def test_load_without_tuning_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"log": {"level": "DEBUG"}}))
        cfg = ReagentConfig.load(path=config_path)
        assert cfg.tuning == TuningConfig()

    def test_load_missing_file_gives_defaults(self, tmp_path: Path) -> None:
        cfg = ReagentConfig.load(path=tmp_path / "nonexistent.yaml")
        assert cfg.tuning.instinct.category_match_boost == 1.5


class TestGetTuning:
    """Tests for the lazy get_tuning() accessor."""

    def test_returns_tuning_config(self) -> None:
        # Clear the lru_cache for isolation
        get_tuning.cache_clear()
        result = get_tuning()
        assert isinstance(result, TuningConfig)

    def test_cached_across_calls(self) -> None:
        get_tuning.cache_clear()
        first = get_tuning()
        second = get_tuning()
        assert first is second

    def test_cache_clear_resets(self) -> None:
        get_tuning.cache_clear()
        first = get_tuning()
        get_tuning.cache_clear()
        second = get_tuning()
        # Both are TuningConfig but may be different objects
        assert isinstance(first, TuningConfig)
        assert isinstance(second, TuningConfig)
