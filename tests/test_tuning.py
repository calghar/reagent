from __future__ import annotations

from pathlib import Path

import yaml

from agentguard._tuning import get_tuning
from agentguard.config import (
    AgentGuardConfig,
    EvaluationTuning,
    TuningConfig,
)


class TestTuningModels:
    def test_evaluation_defaults(self) -> None:
        t = EvaluationTuning()
        assert t.max_invocations_per_week == 5.0
        assert t.max_turn_efficiency == 19.0
        assert t.staleness_window_days == 90.0
        assert t.grade_a_threshold == 90
        assert t.grade_b_threshold == 80

    def test_tuning_config_aggregates_evaluation(self) -> None:
        tc = TuningConfig()
        assert isinstance(tc.evaluation, EvaluationTuning)

    def test_custom_values_override_defaults(self) -> None:
        tc = TuningConfig(
            evaluation=EvaluationTuning(staleness_window_days=30.0),
        )
        assert tc.evaluation.staleness_window_days == 30.0
        assert tc.evaluation.max_invocations_per_week == 5.0


class TestAgentGuardConfigTuning:
    def test_default_agentguard_config_has_tuning(self) -> None:
        cfg = AgentGuardConfig()
        assert isinstance(cfg.tuning, TuningConfig)
        assert cfg.tuning.evaluation.staleness_window_days == 90.0

    def test_load_from_yaml_with_tuning(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        data = {
            "tuning": {
                "evaluation": {"staleness_window_days": 30.0, "grade_a_threshold": 95},
            }
        }
        config_path.write_text(yaml.dump(data))
        cfg = AgentGuardConfig.load(path=config_path)
        assert cfg.tuning.evaluation.staleness_window_days == 30.0
        assert cfg.tuning.evaluation.grade_a_threshold == 95
        assert cfg.tuning.evaluation.max_invocations_per_week == 5.0

    def test_load_without_tuning_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"log": {"level": "DEBUG"}}))
        cfg = AgentGuardConfig.load(path=config_path)
        assert cfg.tuning == TuningConfig()

    def test_load_missing_file_gives_defaults(self, tmp_path: Path) -> None:
        cfg = AgentGuardConfig.load(path=tmp_path / "nonexistent.yaml")
        assert cfg.tuning.evaluation.staleness_window_days == 90.0


class TestGetTuning:
    def test_returns_tuning_config(self) -> None:
        get_tuning.cache_clear()
        result = get_tuning()
        assert isinstance(result, TuningConfig)

    def test_cached_across_calls(self) -> None:
        get_tuning.cache_clear()
        first = get_tuning()
        second = get_tuning()
        assert first is second
