from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from pytest import approx

from agentguard.llm.config import (
    TIER_MODELS,
    CostTier,
    GenerationConfig,
    LLMConfig,
    ProviderFallback,
    RoutingStrategy,
)
from agentguard.llm.providers import (
    AnthropicProvider,
    GoogleProvider,
    HealthStatus,
    LLMAPIError,
    LLMAuthError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
    _raise_for_status,
    create_provider,
)
from agentguard.llm.router import NoProviderAvailableError, ProviderRouter


class TestLLMConfig:
    def test_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.routing == RoutingStrategy.COST
        assert cfg.features.enabled is True

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENTGUARD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AGENTGUARD_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("AGENTGUARD_LLM_ENABLED", "false")
        cfg = LLMConfig()
        cfg.apply_env_overrides()
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.features.enabled is False

    def test_env_override_enabled_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGENTGUARD_LLM_ENABLED", "1")
        cfg = LLMConfig()
        cfg.features.enabled = False
        cfg.apply_env_overrides()
        assert cfg.features.enabled is True

    def test_fallback_chain(self) -> None:
        cfg = LLMConfig(
            fallback=[
                ProviderFallback(provider="openai", model="gpt-4o-mini"),
                ProviderFallback(provider="ollama", model="llama3"),
            ]
        )
        assert len(cfg.fallback) == 2
        assert cfg.fallback[0].provider == "openai"

    def test_cost_tier_values(self) -> None:
        assert CostTier.CHEAP.value == "cheap"
        assert CostTier.STANDARD.value == "standard"
        assert CostTier.PREMIUM.value == "premium"

    def test_tier_models_coverage(self) -> None:
        for provider_name in ("anthropic", "openai", "google", "ollama"):
            for tier in CostTier:
                assert tier in TIER_MODELS[provider_name]


class TestGenerationConfig:
    def test_defaults(self) -> None:
        cfg = GenerationConfig()
        assert cfg.max_output_tokens == 4096
        assert cfg.temperature is None

    def test_override(self) -> None:
        cfg = GenerationConfig(temperature=0.7, max_output_tokens=1000)
        assert cfg.temperature == approx(0.7)
        assert cfg.max_output_tokens == 1000


class TestHelpers:
    def test_estimate_tokens(self) -> None:
        p = OllamaProvider()
        assert p.estimate_tokens("hello world") >= 1
        assert p.estimate_tokens("a" * 400) == 100

    @pytest.mark.parametrize(
        ("status", "error_cls"),
        [
            pytest.param(200, None, id="success"),
            pytest.param(401, LLMAuthError, id="auth"),
            pytest.param(429, LLMRateLimitError, id="rate_limit"),
            pytest.param(500, LLMAPIError, id="server_error"),
        ],
    )
    def test_raise_for_status(
        self, status: int, error_cls: type[Exception] | None
    ) -> None:
        resp = httpx.Response(status, text="error message")
        if error_cls is None:
            _raise_for_status("test", resp)
        else:
            with pytest.raises(error_cls) as exc_info:
                _raise_for_status("test", resp)
            if hasattr(exc_info.value, "status_code"):
                assert exc_info.value.status_code == status

    @pytest.mark.parametrize(
        ("name", "model", "expected_name"),
        [
            pytest.param("ollama", "llama3", "ollama", id="valid"),
            pytest.param("nonexistent", "x", None, id="unknown"),
        ],
    )
    def test_create_provider(
        self, name: str, model: str, expected_name: str | None
    ) -> None:
        if expected_name is None:
            with pytest.raises(ValueError, match="Unknown provider"):
                create_provider(name, model)
        else:
            p = create_provider(name, model)
            assert p.name == expected_name


class TestProviderNameAndAvailability:
    @pytest.mark.parametrize(
        ("provider_cls", "env_var", "env_val", "expected_name"),
        [
            pytest.param(
                AnthropicProvider,
                "ANTHROPIC_API_KEY",
                "sk-test",
                "anthropic",
                id="anthropic",
            ),
            pytest.param(
                OpenAIProvider,
                "OPENAI_API_KEY",
                "sk-test",
                "openai",
                id="openai",
            ),
            pytest.param(
                GoogleProvider,
                "GOOGLE_API_KEY",
                "test-key",
                "google",
                id="google",
            ),
            pytest.param(
                OllamaProvider,
                None,
                None,
                "ollama",
                id="ollama",
            ),
        ],
    )
    def test_name_and_availability(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider_cls: type,
        env_var: str | None,
        env_val: str | None,
        expected_name: str,
    ) -> None:
        if env_var and env_val:
            monkeypatch.setenv(env_var, env_val)
        p = provider_cls()
        assert p.name == expected_name
        assert p.available is True


class TestProviderEstimateCost:
    @pytest.mark.parametrize(
        (
            "provider_cls",
            "env_var",
            "env_val",
            "model",
            "input_tokens",
            "output_tokens",
            "expected_cost",
        ),
        [
            pytest.param(
                AnthropicProvider,
                "ANTHROPIC_API_KEY",
                "sk-test",
                "claude-sonnet-4-20250514",
                1_000_000,
                1_000_000,
                18.0,
                id="anthropic_sonnet",
            ),
            pytest.param(
                OpenAIProvider,
                "OPENAI_API_KEY",
                "sk-test",
                "gpt-4o-mini",
                1_000_000,
                1_000_000,
                0.75,
                id="openai_gpt4o_mini",
            ),
            pytest.param(
                GoogleProvider,
                "GOOGLE_API_KEY",
                "test-key",
                "gemini-2.0-flash",
                1_000_000,
                1_000_000,
                0.50,
                id="google_gemini_flash",
            ),
            pytest.param(
                AnthropicProvider,
                "ANTHROPIC_API_KEY",
                "sk-test",
                "claude-sonnet-4-20250514",
                1_000_000,
                0,
                3.0,
                id="anthropic_input_only",
            ),
            pytest.param(
                AnthropicProvider,
                "ANTHROPIC_API_KEY",
                "sk-test",
                "unknown-model",
                100,
                100,
                0.0,
                id="anthropic_unknown_model",
            ),
            pytest.param(
                OllamaProvider,
                None,
                None,
                None,
                100,
                100,
                0.0,
                id="ollama_zero_cost",
            ),
        ],
    )
    def test_estimate_cost(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider_cls: type,
        env_var: str | None,
        env_val: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        expected_cost: float,
    ) -> None:
        if env_var and env_val:
            monkeypatch.setenv(env_var, env_val)
        kwargs = {"model": model} if model else {}
        p = provider_cls(**kwargs)
        cost = p.estimate_cost(input_tokens, output_tokens)
        assert cost == approx(expected_cost)


class TestAnthropicProvider:
    def test_unavailable_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        assert p.available is False

    @pytest.mark.anyio()
    async def test_generate_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider(model="claude-sonnet-4-20250514")
        mock_response = httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello!"}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "stop_reason": "end_turn",
            },
        )
        p._client = AsyncMock()
        p._client.post = AsyncMock(return_value=mock_response)
        resp = await p.generate("Hi", "Be helpful", GenerationConfig())
        assert resp.text == "Hello!"
        assert resp.provider == "anthropic"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5
        assert resp.cost_usd > 0

    @pytest.mark.parametrize(
        ("has_key", "expect_healthy", "expect_error_substr"),
        [
            pytest.param(False, False, "not set", id="unavailable"),
            pytest.param(True, True, None, id="success"),
        ],
    )
    @pytest.mark.anyio()
    async def test_health_check(
        self,
        monkeypatch: pytest.MonkeyPatch,
        has_key: bool,
        expect_healthy: bool,
        expect_error_substr: str | None,
    ) -> None:
        if has_key:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        if has_key:
            p._client = AsyncMock()
            p._client.post = AsyncMock(return_value=httpx.Response(200, json={}))
        status = await p.health_check()
        assert status.healthy is expect_healthy
        if expect_error_substr:
            assert expect_error_substr in (status.error or "")


class TestOpenAIProvider:
    @pytest.mark.anyio()
    async def test_generate_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider(model="gpt-4o")
        mock_response = httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Hi there"}, "finish_reason": "stop"}
                ],
                "model": "gpt-4o",
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            },
        )
        p._client = AsyncMock()
        p._client.post = AsyncMock(return_value=mock_response)
        resp = await p.generate("Hello", "Be nice", GenerationConfig())
        assert resp.text == "Hi there"
        assert resp.provider == "openai"
        assert resp.finish_reason == "stop"


class TestGoogleProvider:
    @pytest.mark.anyio()
    async def test_generate_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        p = GoogleProvider(model="gemini-2.5-pro")
        mock_response = httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Response"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 4,
                },
            },
        )
        p._client = AsyncMock()
        p._client.post = AsyncMock(return_value=mock_response)
        resp = await p.generate("Hello", "Be helpful", GenerationConfig())
        assert resp.text == "Response"
        assert resp.provider == "google"
        assert resp.finish_reason == "stop"


class TestOllamaProvider:
    @pytest.mark.anyio()
    async def test_generate_success(self) -> None:
        p = OllamaProvider(model="llama3")
        mock_response = httpx.Response(
            200,
            json={
                "response": "Local response",
                "model": "llama3",
                "done": True,
                "prompt_eval_count": 20,
                "eval_count": 10,
            },
        )
        p._client = AsyncMock()
        p._client.post = AsyncMock(return_value=mock_response)
        resp = await p.generate("Hi", "System", GenerationConfig())
        assert resp.text == "Local response"
        assert resp.cost_usd == approx(0.0)
        assert resp.finish_reason == "stop"

    @pytest.mark.parametrize(
        ("mock_side_effect", "mock_return", "expect_healthy"),
        [
            pytest.param(
                None,
                httpx.Response(200, json={"models": []}),
                True,
                id="success",
            ),
            pytest.param(
                httpx.ConnectError("refused"),
                None,
                False,
                id="failure",
            ),
        ],
    )
    @pytest.mark.anyio()
    async def test_health_check(
        self,
        mock_side_effect: Exception | None,
        mock_return: httpx.Response | None,
        expect_healthy: bool,
    ) -> None:
        p = OllamaProvider()
        p._client = AsyncMock()
        if mock_side_effect:
            p._client.get = AsyncMock(side_effect=mock_side_effect)
        else:
            p._client.get = AsyncMock(return_value=mock_return)
        status = await p.health_check()
        assert status.healthy is expect_healthy

    @pytest.mark.parametrize(
        ("host_kwarg", "env_host", "expected_host"),
        [
            pytest.param(
                "http://myserver:11434",
                None,
                "http://myserver:11434",
                id="custom_kwarg",
            ),
            pytest.param(
                None,
                "http://remote:11434",
                "http://remote:11434",
                id="from_env",
            ),
        ],
    )
    def test_host_configuration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        host_kwarg: str | None,
        env_host: str | None,
        expected_host: str,
    ) -> None:
        if env_host:
            monkeypatch.setenv("OLLAMA_HOST", env_host)
        kwargs = {"host": host_kwarg} if host_kwarg else {}
        p = OllamaProvider(**kwargs)
        assert p._host == expected_host


class TestProviderRouter:
    def _mock_provider(
        self,
        name: str = "ollama",
        healthy: bool = True,
        response: LLMResponse | None = None,
        fail: bool = False,
    ) -> AsyncMock:
        """Create a mock LLMProvider."""
        p = AsyncMock()
        p.name = name
        p.available = True
        p.estimate_cost = lambda i, o: 0.0  # noqa: ARG005
        p.estimate_tokens = lambda t: max(1, len(t) // 4)
        p.health_check.return_value = HealthStatus(
            provider=name,
            healthy=healthy,
            latency_ms=10,
            checked_at=datetime.now(UTC),
        )
        if fail:
            p.generate.side_effect = LLMProviderError(name, "provider down")
        elif response:
            p.generate.return_value = response
        else:
            p.generate.return_value = LLMResponse(
                text="ok",
                model="llama3",
                provider=name,
                input_tokens=5,
                output_tokens=2,
                cost_usd=0.0,
                latency_ms=50,
                finish_reason="stop",
            )
        return p

    def _make_router(
        self,
        providers: list[AsyncMock] | None = None,
    ) -> ProviderRouter:
        cfg = LLMConfig(
            provider="ollama",
            model="llama3",
            fallback=[ProviderFallback(provider="ollama", model="llama3")],
            routing=RoutingStrategy.FIXED,
        )
        router = ProviderRouter(cfg)
        if providers is not None:
            router._providers = providers  # type: ignore[assignment]
        return router

    def test_provider_chain(self) -> None:
        router = self._make_router()
        assert len(router.providers) == 2

    @pytest.mark.anyio()
    async def test_generate_success(self) -> None:
        mock_p = self._mock_provider()
        router = self._make_router(providers=[mock_p])
        resp = await router.generate("test", "system")
        assert resp.text == "ok"

    @pytest.mark.anyio()
    async def test_fallback_on_failure(self) -> None:
        fallback_resp = LLMResponse(
            text="fallback",
            model="llama3",
            provider="ollama",
            input_tokens=5,
            output_tokens=2,
            cost_usd=0.0,
            latency_ms=50,
            finish_reason="stop",
        )
        p1 = self._mock_provider(name="primary", fail=True)
        p2 = self._mock_provider(name="secondary", response=fallback_resp)
        router = self._make_router(providers=[p1, p2])
        resp = await router.generate("test", "system")
        assert resp.text == "fallback"

    @pytest.mark.anyio()
    async def test_all_providers_fail(self) -> None:
        p1 = self._mock_provider(name="a", fail=True)
        p2 = self._mock_provider(name="b", fail=True)
        router = self._make_router(providers=[p1, p2])
        with pytest.raises(NoProviderAvailableError, match="All providers failed"):
            await router.generate("test", "system")

    @pytest.mark.parametrize(
        ("failures", "checked_ago_s", "expected_open"),
        [
            pytest.param(3, 0, True, id="opens"),
            pytest.param(3, 301, False, id="recovery"),
        ],
    )
    def test_circuit_breaker(
        self, failures: int, checked_ago_s: int, expected_open: bool
    ) -> None:
        router = self._make_router()
        router._failure_counts["ollama"] = failures
        router._health_cache["ollama"] = HealthStatus(
            provider="ollama",
            healthy=False,
            checked_at=datetime.now(UTC) - timedelta(seconds=checked_ago_s),
            consecutive_failures=failures,
        )
        assert router._is_circuit_open("ollama") is expected_open

    @pytest.mark.anyio()
    async def test_select_provider(self) -> None:
        p = self._mock_provider(name="ollama")
        router = self._make_router(providers=[p])
        provider, model = await router.select_provider(tier=CostTier.STANDARD)
        assert provider.name == "ollama"
        assert model == "llama3"

    @pytest.mark.anyio()
    async def test_select_provider_none_healthy(self) -> None:
        p = self._mock_provider(name="ollama", healthy=False)
        router = self._make_router(providers=[p])
        with pytest.raises(NoProviderAvailableError):
            await router.select_provider()


class TestErrors:
    @pytest.mark.parametrize(
        ("error_cls", "args", "expected_in_str", "extra_checks"),
        [
            pytest.param(
                LLMProviderError,
                ("test", "something broke"),
                "test",
                {"provider": "test"},
                id="provider_error",
            ),
            pytest.param(
                LLMAPIError,
                ("openai", 503, "Service unavailable"),
                "503",
                {"status_code": 503},
                id="api_error",
            ),
            pytest.param(
                NoProviderAvailableError,
                ("nothing works",),
                "nothing works",
                {},
                id="no_provider",
            ),
        ],
    )
    def test_error_types(
        self,
        error_cls: type[Exception],
        args: tuple[object, ...],
        expected_in_str: str,
        extra_checks: dict[str, object],
    ) -> None:
        err = error_cls(*args)
        assert expected_in_str in str(err)
        for attr, value in extra_checks.items():
            assert getattr(err, attr) == value


class TestAgentGuardConfigIntegration:
    def test_default_llm_config(self) -> None:
        from agentguard.config import AgentGuardConfig

        cfg = AgentGuardConfig()
        assert cfg.llm.provider == "anthropic"
        assert cfg.llm.features.enabled is True

    def test_load_with_llm_section(self, tmp_path: pytest.TempPathFactory) -> None:
        from agentguard.config import AgentGuardConfig

        config_path = tmp_path / "config.yaml"  # type: ignore[operator]
        config_path.write_text("llm:\n  provider: openai\n  model: gpt-4o\n")
        cfg = AgentGuardConfig.load(config_path)
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4o"
