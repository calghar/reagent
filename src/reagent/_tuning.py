from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reagent.config import TuningConfig

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_tuning() -> TuningConfig:
    """Return the global tuning configuration, loading once on first call.

    Falls back to defaults if loading the user config file fails.

    Returns:
        The active ``TuningConfig`` instance.
    """
    from reagent.config import ReagentConfig, TuningConfig

    try:
        config = ReagentConfig.load()
        return config.tuning
    except (OSError, ValueError):
        logger.debug("Failed to load config; using default tuning values")
        return TuningConfig()


def score_to_grade(score: float) -> str:
    """Convert a numeric quality score (0-100) to a letter grade.

    Args:
        score: Quality score in the range 0-100.

    Returns:
        Letter grade A-F.
    """
    t = get_tuning().evaluation
    if score >= t.grade_a_threshold:
        return "A"
    if score >= t.grade_b_threshold:
        return "B"
    if score >= t.grade_c_threshold:
        return "C"
    if score >= t.grade_d_threshold:
        return "D"
    return "F"
