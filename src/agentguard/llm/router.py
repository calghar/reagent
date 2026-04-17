import logging
import time
from datetime import UTC, datetime

import httpx

from agentguard._tuning import get_tuning
from agentguard.llm.config import (
    TIER_MODELS,
    CostTier,
    GenerationConfig,
    LLMConfig,
    RoutingStrategy,
)
from agentguard.llm.providers import (
    HealthStatus,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    create_provider,
)

logger = logging.getLogger(__name__)


class NoProviderAvailableError(LLMProviderError):
    """All providers in the chain have failed or are unavailable."""

    def __init__(self, message: str = "No healthy providers available") -> None:
        # Bypass LLMProviderError.__init__ which requires provider arg
        Exception.__init__(self, message)
        self.provider = "router"


class ProviderRouter:
    """Routes generation requests to healthy, cost-appropriate providers."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._providers: list[LLMProvider] = []
        self._health_cache: dict[str, HealthStatus] = {}
        self._failure_counts: dict[str, int] = {}

        # Build provider chain: primary + fallbacks
        primary = create_provider(
            config.provider,
            config.model,
            api_key=config.api_keys.get(config.provider),
        )
        self._providers.append(primary)
        for fb in config.fallback:
            self._providers.append(
                create_provider(
                    fb.provider,
                    fb.model,
                    api_key=config.api_keys.get(fb.provider),
                )
            )

    @property
    def providers(self) -> list[LLMProvider]:
        """Return the ordered list of configured providers."""
        return list(self._providers)

    def _is_stale(self, status: HealthStatus) -> bool:
        age = (datetime.now(UTC) - status.checked_at).total_seconds()
        return age > get_tuning().router.health_check_interval_seconds

    def _is_circuit_open(self, provider_name: str) -> bool:
        """Check if provider circuit breaker is open."""
        status = self._health_cache.get(provider_name)
        if status is None:
            return False
        if status.consecutive_failures < get_tuning().router.circuit_breaker_threshold:
            return False
        # Allow retry after recovery period
        age = (datetime.now(UTC) - status.checked_at).total_seconds()
        return age < get_tuning().router.circuit_breaker_recovery_seconds

    def _record_failure(self, provider_name: str) -> None:
        count = self._failure_counts.get(provider_name, 0) + 1
        self._failure_counts[provider_name] = count
        self._health_cache[provider_name] = HealthStatus(
            provider=provider_name,
            healthy=False,
            checked_at=datetime.now(UTC),
            error="generation failure",
            consecutive_failures=count,
        )

    def _record_success(self, provider_name: str) -> None:
        self._failure_counts[provider_name] = 0

    async def health_check(self, provider: LLMProvider) -> HealthStatus:
        """Run a health check and update cache."""
        status = await provider.health_check()
        if status.healthy:
            self._failure_counts[provider.name] = 0
        else:
            count = self._failure_counts.get(provider.name, 0) + 1
            self._failure_counts[provider.name] = count
            status = status.model_copy(update={"consecutive_failures": count})
        self._health_cache[provider.name] = status
        return status

    async def _get_healthy_candidates(
        self,
        tier: CostTier,
        exclude: set[str],
    ) -> list[tuple[LLMProvider, str, int]]:
        """Return healthy providers with their tier model and latency."""
        candidates: list[tuple[LLMProvider, str, int]] = []
        for provider in self._providers:
            if provider.name in exclude or self._is_circuit_open(provider.name):
                continue
            status = self._health_cache.get(provider.name)
            if status is None or self._is_stale(status):
                status = await self.health_check(provider)
            if not status.healthy:
                continue
            model = TIER_MODELS.get(provider.name, {}).get(tier)
            if model:
                candidates.append((provider, model, status.latency_ms or 9999))
        return candidates

    async def select_provider(
        self,
        tier: CostTier = CostTier.STANDARD,
        exclude: set[str] | None = None,
    ) -> tuple[LLMProvider, str]:
        """Select the best available provider for the given cost tier.

        Returns:
            Tuple of (provider, model_name) to use.

        Raises:
            NoProviderAvailableError: If no healthy provider is available.
        """
        candidates = await self._get_healthy_candidates(tier, exclude or set())
        if not candidates:
            raise NoProviderAvailableError(
                f"No healthy providers available for tier {tier.value}"
            )

        if self._config.routing == RoutingStrategy.COST:
            candidates.sort(key=lambda c: c[0].estimate_cost(500, 500))
        elif self._config.routing == RoutingStrategy.LATENCY:
            candidates.sort(key=lambda c: c[2])
        # else: fixed order (first configured)

        return candidates[0][0], candidates[0][1]

    async def generate(
        self,
        prompt: str,
        system: str,
        config: GenerationConfig | None = None,
    ) -> LLMResponse:
        """Generate text, falling through providers on failure.

        Tries providers in order (primary, then fallbacks). Records failures
        for circuit breaker tracking.

        Raises:
            NoProviderAvailableError: If all providers fail.
        """
        gen_config = config or GenerationConfig()
        errors: list[str] = []

        for provider in self._providers:
            if self._is_circuit_open(provider.name):
                continue
            try:
                start = time.monotonic()
                response = await provider.generate(prompt, system, gen_config)
                self._record_success(provider.name)
                logger.debug(
                    "Generated via %s in %dms",
                    provider.name,
                    int((time.monotonic() - start) * 1000),
                )
                return response
            except (
                LLMProviderError,
                httpx.HTTPError,
                OSError,
                ValueError,
                KeyError,
            ) as exc:
                self._record_failure(provider.name)
                errors.append(f"{provider.name}: {exc}")
                logger.warning("Provider %s failed: %s", provider.name, exc)

        raise NoProviderAvailableError(f"All providers failed: {'; '.join(errors)}")

    async def aclose(self) -> None:
        """Close all provider HTTP clients."""
        for provider in self._providers:
            await provider.aclose()
