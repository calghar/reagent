import logging
import os
import time
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel

from agentguard.llm.config import COST_PER_1M, PROVIDER_ENV_KEYS, GenerationConfig

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GOOGLE_MODEL = "gemini-2.5-pro"
DEFAULT_OLLAMA_MODEL = "llama3"


class HealthStatus(BaseModel):
    """Provider health at a point in time."""

    provider: str
    healthy: bool
    latency_ms: int | None = None
    checked_at: datetime
    error: str | None = None
    consecutive_failures: int = 0


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""

    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    finish_reason: str  # "stop", "length", "error"


class LLMProviderError(Exception):
    """Base error for LLM provider failures."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class LLMAuthError(LLMProviderError):
    """Authentication failure (missing or invalid API key)."""


class LLMRateLimitError(LLMProviderError):
    """Rate limit exceeded."""


class LLMAPIError(LLMProviderError):
    """Generic API error."""

    def __init__(self, provider: str, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(provider, f"HTTP {status_code}: {message}")


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""

    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    async def generate(
        self, prompt: str, system: str, config: GenerationConfig
    ) -> LLMResponse: ...

    async def health_check(self) -> HealthStatus: ...

    def estimate_tokens(self, text: str) -> int: ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float: ...

    async def aclose(self) -> None: ...


def _raise_for_status(provider_name: str, response: httpx.Response) -> None:
    """Raise typed exception for HTTP error responses."""
    if response.is_success:
        return
    if response.status_code == 401:
        raise LLMAuthError(provider_name, "Invalid or missing API key")
    if response.status_code == 429:
        raise LLMRateLimitError(provider_name, "Rate limit exceeded")
    raise LLMAPIError(
        provider_name,
        response.status_code,
        response.text[:200],
    )


class BaseProvider:
    """Shared logic for all LLM providers.

    Subclasses must set ``_name`` and ``_env_key`` (or override ``available``),
    then implement ``generate`` and ``_ping``.
    """

    _name: str
    _env_key: str

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self._model = model
        # Resolution order: explicit api_key arg → env var → empty string
        if api_key is not None:
            self._api_key = api_key
        elif self._env_key:
            self._api_key = os.environ.get(self._env_key, "")
        else:
            self._api_key = ""
        self._client = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return not self._env_key or bool(self._api_key)

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Compute cost in USD from token counts and pricing tables."""
        pricing = COST_PER_1M.get(self._name, {}).get(self._model)
        if pricing is None:
            return 0.0
        return (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000

    async def _ping(self) -> httpx.Response:
        """Make a minimal request to verify reachability. Override per provider."""
        raise NotImplementedError

    async def _post(self, url: str, **kwargs: Any) -> tuple[Any, int]:
        """POST, return (parsed_json, latency_ms). Raises on HTTP errors."""
        start = time.monotonic()
        response = await self._client.post(url, **kwargs)
        latency = int((time.monotonic() - start) * 1000)
        _raise_for_status(self.name, response)
        return response.json(), latency

    async def health_check(self) -> HealthStatus:
        """Run a lightweight health check; subclasses only override ``_ping``."""
        if not self.available:
            return HealthStatus(
                provider=self.name,
                healthy=False,
                checked_at=datetime.now(UTC),
                error=f"{self._env_key} not set",
                consecutive_failures=1,
            )
        try:
            start = time.monotonic()
            response = await self._ping()
            latency = int((time.monotonic() - start) * 1000)
            if response.is_success:
                return HealthStatus(
                    provider=self.name,
                    healthy=True,
                    latency_ms=latency,
                    checked_at=datetime.now(UTC),
                )
            return HealthStatus(
                provider=self.name,
                healthy=False,
                latency_ms=latency,
                checked_at=datetime.now(UTC),
                error=f"HTTP {response.status_code}",
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return HealthStatus(
                provider=self.name,
                healthy=False,
                checked_at=datetime.now(UTC),
                error=str(exc),
            )


class AnthropicProvider(BaseProvider):
    """Anthropic (Claude) provider using the Messages API."""

    _name = "anthropic"
    _env_key = PROVIDER_ENV_KEYS["anthropic"]
    BASE_URL = ANTHROPIC_API_URL

    def __init__(
        self, model: str = DEFAULT_ANTHROPIC_MODEL, api_key: str | None = None
    ) -> None:
        super().__init__(model, api_key=api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def _ping(self) -> httpx.Response:
        return await self._client.post(
            self.BASE_URL,
            headers=self._headers(),
            json={
                "model": self._model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

    async def generate(
        self, prompt: str, system: str, config: GenerationConfig
    ) -> LLMResponse:
        data, latency = await self._post(
            self.BASE_URL,
            headers=self._headers(),
            json={
                "model": self._model,
                "max_tokens": config.max_output_tokens,
                **(
                    {"temperature": config.temperature}
                    if config.temperature is not None
                    else {}
                ),
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        text = "".join(
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        return LLMResponse(
            text=text,
            model=data.get("model", self._model),
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=self.estimate_cost(in_tok, out_tok),
            latency_ms=latency,
            finish_reason=data.get("stop_reason", "stop"),
        )


class OpenAIProvider(BaseProvider):
    """OpenAI provider using the Chat Completions API."""

    _name = "openai"
    _env_key = PROVIDER_ENV_KEYS["openai"]
    BASE_URL = OPENAI_API_URL

    def __init__(
        self, model: str = DEFAULT_OPENAI_MODEL, api_key: str | None = None
    ) -> None:
        super().__init__(model, api_key=api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _ping(self) -> httpx.Response:
        return await self._client.post(
            self.BASE_URL,
            headers=self._headers(),
            json={
                "model": self._model,
                "max_completion_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )

    async def generate(
        self, prompt: str, system: str, config: GenerationConfig
    ) -> LLMResponse:
        data, latency = await self._post(
            self.BASE_URL,
            headers=self._headers(),
            json={
                "model": self._model,
                "max_completion_tokens": config.max_output_tokens,
                **(
                    {"temperature": config.temperature}
                    if config.temperature is not None
                    else {}
                ),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        choices = data.get("choices", [{}])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        finish = choices[0].get("finish_reason", "stop") if choices else "error"
        return LLMResponse(
            text=text,
            model=data.get("model", self._model),
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=self.estimate_cost(in_tok, out_tok),
            latency_ms=latency,
            finish_reason=finish,
        )


class GoogleProvider(BaseProvider):
    """Google Gemini provider using the generateContent API."""

    _name = "google"
    _env_key = PROVIDER_ENV_KEYS["google"]
    BASE_URL = GOOGLE_API_URL

    def __init__(
        self, model: str = DEFAULT_GOOGLE_MODEL, api_key: str | None = None
    ) -> None:
        super().__init__(model, api_key=api_key)

    def _url(self) -> str:
        return f"{self.BASE_URL}/{self._model}:generateContent"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key
        return headers

    async def _ping(self) -> httpx.Response:
        return await self._client.post(
            self._url(),
            headers=self._headers(),
            json={
                "contents": [{"parts": [{"text": "ping"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            },
        )

    async def generate(
        self, prompt: str, system: str, config: GenerationConfig
    ) -> LLMResponse:
        data, latency = await self._post(
            self._url(),
            headers=self._headers(),
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": config.max_output_tokens,
                    **(
                        {"temperature": config.temperature}
                        if config.temperature is not None
                        else {}
                    ),
                },
            },
        )
        candidates = data.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount", 0)
        out_tok = usage.get("candidatesTokenCount", 0)
        finish = candidates[0].get("finishReason", "STOP") if candidates else "ERROR"
        return LLMResponse(
            text=text,
            model=self._model,
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=self.estimate_cost(in_tok, out_tok),
            latency_ms=latency,
            finish_reason=finish.lower(),
        )


class OllamaProvider(BaseProvider):
    """Local LLM via Ollama. Zero cost, privacy-preserving."""

    _name = "ollama"
    _env_key = ""  # No API key required

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        host: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model, api_key=api_key)
        self._host = host or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)

    async def _ping(self) -> httpx.Response:
        return await self._client.get(f"{self._host}/api/tags")

    async def generate(
        self, prompt: str, system: str, config: GenerationConfig
    ) -> LLMResponse:
        data, latency = await self._post(
            f"{self._host}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "num_predict": config.max_output_tokens,
                    **(
                        {"temperature": config.temperature}
                        if config.temperature is not None
                        else {}
                    ),
                },
            },
        )
        in_tok = data.get("prompt_eval_count", 0)
        out_tok = data.get("eval_count", 0)
        return LLMResponse(
            text=data.get("response", ""),
            model=data.get("model", self._model),
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            latency_ms=latency,
            finish_reason="stop" if data.get("done") else "length",
        )


_PROVIDER_CLASSES: dict[
    str, type[AnthropicProvider | OpenAIProvider | GoogleProvider | OllamaProvider]
] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider,
}


def create_provider(
    provider_name: str, model: str, api_key: str | None = None
) -> LLMProvider:
    """Factory: create a provider instance by name.

    Args:
        provider_name: One of 'anthropic', 'openai', 'google', 'ollama'.
        model: Model identifier for the provider.
        api_key: Optional API key. When supplied it takes precedence over
            the environment variable for that provider.

    Returns:
        An LLMProvider implementation.

    Raises:
        ValueError: If provider_name is unknown.
    """
    cls = _PROVIDER_CLASSES.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_name!r}")
    return cls(model=model, api_key=api_key)
