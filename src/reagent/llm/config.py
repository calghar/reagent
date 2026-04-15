import logging
import os
from enum import StrEnum

from pydantic import BaseModel, Field

from reagent.core.parsers import AssetType

logger = logging.getLogger(__name__)

# Canonical mapping of provider name → environment variable holding its API key.
# Providers that need no key (e.g. ollama) are intentionally absent.
PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "ollama": "OLLAMA_HOST",
}


class RoutingStrategy(StrEnum):
    """Provider routing strategy."""

    COST = "cost"
    LATENCY = "latency"
    FIXED = "fixed"


class CostTier(StrEnum):
    """Cost tier for model selection."""

    CHEAP = "cheap"
    STANDARD = "standard"
    PREMIUM = "premium"


class ProviderFallback(BaseModel):
    """A fallback entry in the provider chain."""

    provider: str
    model: str


class LLMFeatureFlags(BaseModel):
    """Feature flags for LLM generation."""

    enabled: bool = True
    use_critic: bool = False
    use_instincts: bool = False
    use_cache: bool = True


class LLMConfig(BaseModel):
    """Top-level LLM configuration."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    fallback: list[ProviderFallback] = Field(default_factory=list)
    temperature: float = 0.3
    max_output_tokens: int = 4096
    max_prompt_tokens: int = 2000
    routing: RoutingStrategy = RoutingStrategy.COST
    features: LLMFeatureFlags = Field(default_factory=LLMFeatureFlags)
    critic_model: str = "claude-haiku-4-20250414"
    api_keys: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Provider API keys from config file. "
            "Keys are provider names ('anthropic', 'openai', 'google'). "
            "Environment variables always take precedence over these values."
        ),
    )

    def apply_env_overrides(self) -> None:
        """Apply environment variable overrides in-place.

        Note: API keys are resolved at provider instantiation time by
        combining config-file values (``api_keys``) with environment
        variables.  Environment variables always win.  Keys are NOT
        stored back into this object to avoid serialising secrets.
        """
        if provider := os.environ.get("REAGENT_LLM_PROVIDER"):
            self.provider = provider
        if model := os.environ.get("REAGENT_LLM_MODEL"):
            self.model = model
        if enabled := os.environ.get("REAGENT_LLM_ENABLED"):
            self.features.enabled = enabled.lower() in ("1", "true", "yes")


class GenerationConfig(BaseModel):
    """Per-call generation overrides."""

    temperature: float | None = None
    max_output_tokens: int = 4096
    max_prompt_tokens: int | None = None


# Model pricing per 1M tokens (input/output) by provider and model.
COST_PER_1M: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-haiku-4-20250414": {"input": 0.25, "output": 1.25},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    },
    "openai": {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
    },
    "google": {
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    },
    "ollama": {},  # Local — zero cost
}

# Model mapping per provider and cost tier.
TIER_MODELS: dict[str, dict[CostTier, str]] = {
    "anthropic": {
        CostTier.CHEAP: "claude-haiku-4-20250414",
        CostTier.STANDARD: "claude-sonnet-4-20250514",
        CostTier.PREMIUM: "claude-sonnet-4-20250514",
    },
    "openai": {
        CostTier.CHEAP: "gpt-4o-mini",
        CostTier.STANDARD: "gpt-4o",
        CostTier.PREMIUM: "gpt-4o",
    },
    "google": {
        CostTier.CHEAP: "gemini-2.0-flash",
        CostTier.STANDARD: "gemini-2.5-pro",
        CostTier.PREMIUM: "gemini-2.5-pro",
    },
    "ollama": {
        CostTier.CHEAP: "llama3",
        CostTier.STANDARD: "llama3",
        CostTier.PREMIUM: "llama3:70b",
    },
}

# Asset type → cost tier mapping for model routing.
_ASSET_TIER: dict[AssetType, CostTier] = {
    AssetType.HOOK: CostTier.CHEAP,
    AssetType.COMMAND: CostTier.CHEAP,
    AssetType.AGENT: CostTier.STANDARD,
    AssetType.SKILL: CostTier.CHEAP,
    AssetType.RULE: CostTier.STANDARD,
    AssetType.CLAUDE_MD: CostTier.STANDARD,
}


def select_model(
    asset_type: AssetType,
    config: LLMConfig,
    *,
    is_critic: bool = False,
    is_regeneration: bool = False,
    model_override: str | None = None,
) -> tuple[str, CostTier]:
    """Select the appropriate model for the given generation task.

    Routing rules:
    - User ``--model`` override always takes precedence.
    - Critic pass always uses CHEAP tier.
    - Regeneration with evaluation uses STANDARD tier.
    - Otherwise, determined by asset type.

    Args:
        asset_type: The asset being generated.
        config: LLM configuration.
        is_critic: Whether this is a critic pass.
        is_regeneration: Whether regenerating with evaluation.
        model_override: Explicit model from user (``--model`` flag).

    Returns:
        (model_name, cost_tier) tuple.
    """
    if model_override:
        # Determine tier by checking pricing tables
        tier = CostTier.STANDARD
        for provider_models in TIER_MODELS.values():
            for t, m in provider_models.items():
                if m == model_override:
                    tier = t
                    break
        return model_override, tier

    if is_critic:
        model = TIER_MODELS.get(config.provider, {}).get(
            CostTier.CHEAP, config.critic_model
        )
        return model, CostTier.CHEAP

    if is_regeneration:
        model = TIER_MODELS.get(config.provider, {}).get(
            CostTier.STANDARD, config.model
        )
        return model, CostTier.STANDARD

    tier = _ASSET_TIER.get(asset_type, CostTier.STANDARD)
    model = TIER_MODELS.get(config.provider, {}).get(tier, config.model)
    return model, tier
