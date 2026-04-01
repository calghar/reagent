import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LoopConfig(BaseModel):
    """Configuration for a single autonomous loop run.

    All limits are hard guardrails — the loop stops as soon as any
    one is exceeded.
    """

    max_iterations: int = 5
    max_cost_usd: float = 2.0
    require_approval: bool = True
    min_improvement: float = 5.0  # minimum score delta per iteration
    min_quality_threshold: float = 60.0
    kill_switch: bool = False
    max_assets_per_iteration: int = 10
    cooldown_seconds: float = 30.0
    target_score: float = 80.0
    max_runtime_seconds: float = 1800.0  # 30 minutes


class GuardrailResult(BaseModel):
    """Result of a single guardrail check.

    ``passed=True`` means the loop may continue; ``passed=False`` means
    it must stop, with ``reason`` describing why.
    """

    passed: bool
    reason: str | None = None


class GuardrailChecker:
    """Stateless guardrail checker for loop iteration gates.

    Each ``check_*`` method returns a :class:`GuardrailResult`.
    :meth:`check_all` runs every check in priority order and returns
    the first failure, or a passing result when all pass.
    """

    def check_iteration_limit(self, current: int, max_iter: int) -> GuardrailResult:
        """Verify iteration count has not exceeded the configured maximum.

        Args:
            current: Current iteration number (1-based).
            max_iter: Maximum permitted iterations.

        Returns:
            Failing result when ``current > max_iter``, otherwise passing.
        """
        if current > max_iter:
            return GuardrailResult(
                passed=False,
                reason=f"Iteration limit reached ({max_iter})",
            )
        return GuardrailResult(passed=True)

    def check_cost_limit(self, spent: float, max_cost: float) -> GuardrailResult:
        """Verify accumulated cost has not reached the configured budget.

        Args:
            spent: Total USD spent so far.
            max_cost: Maximum permitted USD spend.

        Returns:
            Failing result when ``spent >= max_cost``, otherwise passing.
        """
        if spent >= max_cost:
            return GuardrailResult(
                passed=False,
                reason=f"Cost limit reached (${spent:.2f} >= ${max_cost:.2f})",
            )
        return GuardrailResult(passed=True)

    def check_improvement(
        self, prev_score: float, curr_score: float, min_delta: float
    ) -> GuardrailResult:
        """Verify scores are improving by at least ``min_delta`` points.

        Only applied when ``prev_score > 0`` (i.e. at least one prior
        iteration has a score to compare against).

        Args:
            prev_score: Score from the previous iteration.
            curr_score: Score from the current iteration.
            min_delta: Minimum required improvement.

        Returns:
            Failing result when improvement is insufficient, otherwise passing.
        """
        if prev_score > 0 and (curr_score - prev_score) < min_delta:
            delta = curr_score - prev_score
            return GuardrailResult(
                passed=False,
                reason=(
                    f"Insufficient improvement: {curr_score:.1f} - "
                    f"{prev_score:.1f} = {delta:.1f} < {min_delta}"
                ),
            )
        return GuardrailResult(passed=True)

    def check_kill_switch(self, kill_switch: bool) -> GuardrailResult:
        """Verify the kill switch has not been activated.

        Args:
            kill_switch: Current kill-switch state.

        Returns:
            Failing result when kill switch is ``True``, otherwise passing.
        """
        if kill_switch:
            return GuardrailResult(passed=False, reason="Kill switch activated")
        return GuardrailResult(passed=True)

    def check_all(
        self,
        iteration: int,
        config: LoopConfig,
        prev_score: float,
        curr_score: float,
        total_cost: float,
    ) -> GuardrailResult:
        """Run all guardrails in priority order.

        Checks are evaluated in the following order:
        1. Kill switch
        2. Iteration limit
        3. Cost limit
        4. Improvement gate

        Args:
            iteration: Current iteration number (1-based).
            config: Loop configuration providing limit values.
            prev_score: Score from the previous iteration (0 if none).
            curr_score: Score from the current iteration.
            total_cost: Accumulated USD cost so far.

        Returns:
            The first failing GuardrailResult, or a passing one if all pass.
        """
        checks = [
            self.check_kill_switch(config.kill_switch),
            self.check_iteration_limit(iteration, config.max_iterations),
            self.check_cost_limit(total_cost, config.max_cost_usd),
            self.check_improvement(prev_score, curr_score, config.min_improvement),
        ]
        for result in checks:
            if not result.passed:
                logger.info("Guardrail tripped: %s", result.reason)
                return result
        return GuardrailResult(passed=True)
