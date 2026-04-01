import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from pytest import approx

from reagent.llm.config import (
    TIER_MODELS,
    CostTier,
    GenerationConfig,
    LLMConfig,
    ProviderFallback,
    RoutingStrategy,
)
from reagent.llm.costs import BudgetStatus, CostEntry, CostTracker
from reagent.llm.providers import (
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
from reagent.llm.router import NoProviderAvailableError, ProviderRouter


class TestLLMConfig:
    def test_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.routing == RoutingStrategy.COST
        assert cfg.features.enabled is True
        assert cfg.monthly_budget == approx(10.0)

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REAGENT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("REAGENT_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("REAGENT_LLM_ENABLED", "false")
        cfg = LLMConfig()
        cfg.apply_env_overrides()
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.features.enabled is False

    def test_env_override_enabled_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REAGENT_LLM_ENABLED", "1")
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

    def test_compute_cost_known(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider(model="claude-sonnet-4-20250514")
        cost = p.estimate_cost(1_000_000, 0)
        assert cost == pytest.approx(3.0)

    def test_compute_cost_unknown_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider(model="unknown-model")
        assert p.estimate_cost(100, 100) == pytest.approx(0.0)

    def test_compute_cost_zero_for_ollama(self) -> None:
        p = OllamaProvider()
        assert p.estimate_cost(100, 100) == pytest.approx(0.0)

    def test_raise_for_status_success(self) -> None:
        resp = httpx.Response(200)
        _raise_for_status("test", resp)  # should not raise

    def test_raise_for_status_401(self) -> None:
        resp = httpx.Response(401, text="Unauthorized")
        with pytest.raises(LLMAuthError):
            _raise_for_status("test", resp)

    def test_raise_for_status_429(self) -> None:
        resp = httpx.Response(429, text="Rate limited")
        with pytest.raises(LLMRateLimitError):
            _raise_for_status("test", resp)

    def test_raise_for_status_500(self) -> None:
        resp = httpx.Response(500, text="Internal server error")
        with pytest.raises(LLMAPIError) as exc_info:
            _raise_for_status("test", resp)
        assert exc_info.value.status_code == 500

    def test_create_provider_factory(self) -> None:
        p = create_provider("ollama", "llama3")
        assert p.name == "ollama"

    def test_create_provider_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("nonexistent", "x")


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
        ],
    )
    def test_name_and_availability_with_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider_cls: type,
        env_var: str,
        env_val: str,
        expected_name: str,
    ) -> None:
        monkeypatch.setenv(env_var, env_val)
        p = provider_cls()
        assert p.name == expected_name
        assert p.available is True

    def test_ollama_name_and_availability(self) -> None:
        p = OllamaProvider()
        assert p.name == "ollama"
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
        ],
    )
    def test_estimate_cost(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider_cls: type,
        env_var: str,
        env_val: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        expected_cost: float,
    ) -> None:
        monkeypatch.setenv(env_var, env_val)
        p = provider_cls(model=model)
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

    @pytest.mark.anyio()
    async def test_health_check_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        status = await p.health_check()
        assert status.healthy is False
        assert "not set" in (status.error or "")

    @pytest.mark.anyio()
    async def test_health_check_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider()
        p._client = AsyncMock()
        p._client.post = AsyncMock(return_value=httpx.Response(200, json={}))
        status = await p.health_check()
        assert status.healthy is True


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
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4},
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

    @pytest.mark.anyio()
    async def test_health_check_success(self) -> None:
        p = OllamaProvider()
        p._client = AsyncMock()
        p._client.get = AsyncMock(return_value=httpx.Response(200, json={"models": []}))
        status = await p.health_check()
        assert status.healthy is True

    @pytest.mark.anyio()
    async def test_health_check_failure(self) -> None:
        p = OllamaProvider()
        p._client = AsyncMock()
        p._client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        status = await p.health_check()
        assert status.healthy is False

    def test_estimate_cost_zero(self) -> None:
        p = OllamaProvider()
        assert p.estimate_cost(10000, 10000) == approx(0.0)

    def test_custom_host(self) -> None:
        p = OllamaProvider(host="http://myserver:11434")
        assert p._host == "http://myserver:11434"

    def test_host_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_HOST", "http://remote:11434")
        p = OllamaProvider()
        assert p._host == "http://remote:11434"


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

    def test_circuit_breaker_opens(self) -> None:
        router = self._make_router()
        router._failure_counts["ollama"] = 3
        router._health_cache["ollama"] = HealthStatus(
            provider="ollama",
            healthy=False,
            checked_at=datetime.now(UTC),
            consecutive_failures=3,
        )
        assert router._is_circuit_open("ollama") is True

    def test_circuit_breaker_recovery(self) -> None:
        router = self._make_router()
        router._failure_counts["ollama"] = 3
        router._health_cache["ollama"] = HealthStatus(
            provider="ollama",
            healthy=False,
            checked_at=datetime.now(UTC) - timedelta(seconds=301),
            consecutive_failures=3,
        )
        assert router._is_circuit_open("ollama") is False

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


class TestCostTracker:
    def _make_entry(self, cost: float = 0.01) -> CostEntry:
        return CostEntry(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
            cost_usd=cost,
            latency_ms=200,
        )

    def test_record_and_session_total(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(0.05))
        tracker.record(self._make_entry(0.03))
        assert tracker.session_total() == pytest.approx(0.08)
        tracker.close()

    def test_monthly_total_sqlite(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(1.5))
        total = tracker.monthly_total()
        assert total >= 1.5
        tracker.close()

    def test_budget_ok(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(1.0))
        assert tracker.budget_status() == BudgetStatus.OK
        tracker.close()

    def test_budget_warning(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(8.5))
        assert tracker.budget_status() == BudgetStatus.WARNING
        tracker.close()

    def test_budget_exceeded(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(11.0))
        assert tracker.budget_status() == BudgetStatus.EXCEEDED
        tracker.close()

    def test_cost_by_provider(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=10.0)
        tracker.record(self._make_entry(0.5))
        by_provider = tracker.cost_by_provider()
        assert "anthropic" in by_provider
        assert by_provider["anthropic"] == pytest.approx(0.5)
        tracker.close()

    def test_jsonl_fallback(self, tmp_path: pytest.TempPathFactory) -> None:
        # Use a path that will fail for SQLite (dir as file)
        bad_path = tmp_path / "nodir" / "deep" / "test.db"  # type: ignore[operator]
        # Don't create the parent — SQLite will fail on connect
        # Actually CostTracker creates parent. Let's just test that JSONL works
        # by patching _init_db to fail
        tracker = CostTracker(db_path=bad_path, monthly_budget=10.0)
        # Force JSONL mode
        if tracker._db is not None:
            tracker._db.close()
            tracker._db = None
        entry = self._make_entry(0.02)
        tracker.record(entry)
        jsonl_path = bad_path.parent / "cost_log.jsonl"
        assert jsonl_path.exists()
        data = json.loads(jsonl_path.read_text().strip())
        assert data["cost_usd"] == approx(0.02)

    def test_budget_zero_is_ok(self, tmp_path: pytest.TempPathFactory) -> None:
        # monthly_budget=0 is documented as "no budget limit" in costs.py
        # (CostTracker.budget_status returns BudgetStatus.OK when budget <= 0).
        # This test verifies that sentinel value is honoured regardless of spend.
        db = tmp_path / "test.db"  # type: ignore[operator]
        tracker = CostTracker(db_path=db, monthly_budget=0.0)
        tracker.record(self._make_entry(100.0))
        assert tracker.budget_status() == BudgetStatus.OK
        tracker.close()


class TestErrors:
    def test_provider_error(self) -> None:
        err = LLMProviderError("test", "something broke")
        assert "test" in str(err)
        assert err.provider == "test"

    def test_api_error_status(self) -> None:
        err = LLMAPIError("openai", 503, "Service unavailable")
        assert err.status_code == 503
        assert "503" in str(err)

    def test_no_provider_error(self) -> None:
        err = NoProviderAvailableError("nothing works")
        assert "nothing works" in str(err)


class TestReagentConfigIntegration:
    def test_default_llm_config(self) -> None:
        from reagent.config import ReagentConfig

        cfg = ReagentConfig()
        assert cfg.llm.provider == "anthropic"
        assert cfg.llm.features.enabled is True

    def test_load_with_llm_section(self, tmp_path: pytest.TempPathFactory) -> None:
        from reagent.config import ReagentConfig

        config_path = tmp_path / "config.yaml"  # type: ignore[operator]
        config_path.write_text(
            "llm:\n  provider: openai\n  model: gpt-4o\n  monthly_budget: 5.0\n"
        )
        cfg = ReagentConfig.load(config_path)
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4o"
        assert cfg.llm.monthly_budget == approx(5.0)
