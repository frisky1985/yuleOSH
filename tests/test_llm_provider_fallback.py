# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Unit tests for src/llm/provider_fallback.py — provider-level fallback chain.

Covers:
- B1: degradation chain behaviour (transport failure → degrade; 4xx → no
  degrade; fallback disabled → no degrade; skeleton skip; budget overrun;
  chain exhausted)
- B2: configuration parsing (env / LLMConfig, order validation, primary first)
- B3: audit logging (provider_fallback_events.jsonl + final provider in
  llm_calls.jsonl)
- Regression: LLMClient.call integration path.

All tests are fully mocked — no real network calls.
"""

import asyncio
import urllib.error

import pytest

from yuleosh.llm.client import LLMClient
from yuleosh.llm.cost import CostLogger
from yuleosh.llm.provider_fallback import (
    DEFAULT_FALLBACK_ORDER,
    call_with_fallback,
    fallback_enabled,
    is_fallback_eligible,
    provider_available,
    resolve_fallback_order,
)
from yuleosh.llm.providers.base import AbstractProvider, LLMConfig, LLMResponse

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeProvider(AbstractProvider):
    """Deterministic provider double: fails with a given exception or succeeds."""

    def __init__(
        self,
        name: str,
        fail_with: BaseException | None = None,
        skeleton: bool = False,
        calls: list | None = None,
    ):
        self._name = name
        self._fail_with = fail_with
        self.is_skeleton = skeleton
        self._calls = calls if calls is not None else []

    @property
    def provider_name(self) -> str:
        return self._name

    async def chat(self, messages, config: LLMConfig) -> LLMResponse:
        self._calls.append(self._name)
        if self._fail_with is not None:
            raise self._fail_with
        return LLMResponse(
            content=f"ok from {self._name}",
            model=config.model,
            provider=self._name,
            token_usage={"prompt": 1, "completion": 1, "total": 2},
            cost=0.001,
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.001


def make_factory(
    specs: dict[str, BaseException | None],
    calls: list | None = None,
    skeletons: list | None = None,
):
    """Build a provider_factory from {name: fail_exc_or_None} specs."""
    skeletons = skeletons or []

    def factory(name: str) -> AbstractProvider:
        return FakeProvider(
            name,
            fail_with=specs.get(name),
            skeleton=name in skeletons,
            calls=calls,
        )

    return factory


def run(coro):
    """Run an async coroutine synchronously (matches repo test style)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_audit_log(monkeypatch):
    """Route audit logging to in-memory records; never touch real JSONL files.

    Also clears the real CostLogger log-path state so tests are isolated.
    """
    records: dict[str, list] = {"calls": [], "fallback": []}

    def fake_log_dict(**kwargs):
        records["calls"].append(kwargs)

    def fake_log_fallback_event(**kwargs):
        records["fallback"].append(kwargs)

    monkeypatch.setattr(CostLogger, "log_dict", staticmethod(fake_log_dict))
    monkeypatch.setattr(
        CostLogger, "log_fallback_event", staticmethod(fake_log_fallback_event)
    )
    monkeypatch.setattr(CostLogger, "_log_dir", None)
    monkeypatch.setattr(CostLogger, "_fallback_log_path", None)

    # Clean provider registry between tests.
    LLMClient.reset()

    yield records


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove fallback-related env vars by default (tests opt in via setenv)."""
    for var in (
        "YULEOSH_LLM_FALLBACK_ENABLED",
        "YULEOSH_LLM_FALLBACK_ORDER",
        "YULEOSH_LLM_PROVIDER",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "LLM_API_KEY",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


def base_config(**overrides) -> LLMConfig:
    """Convenience config for fallback tests (no RAG/memory side effects)."""
    cfg = LLMConfig(
        provider="deepseek",
        model="deepseek-v4",
        rag_enabled=False,
        memory_enabled=False,
        task_type="simple_summary",
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


# ---------------------------------------------------------------------------
# B1 — degradation chain behaviour
# ---------------------------------------------------------------------------


class TestDegradationChain:
    def test_connection_failure_degrades_to_mock(self, monkeypatch):
        """B1.1: primary transport failure → automatic degrade to mock."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError(
                    "DeepSeek provider (deepseek): LLM 请求在 3 次重试后失败: "
                    "<urlopen error timed out>"
                ),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.error is None
        assert resp.provider == "mock"
        assert "ok from mock" in resp.content
        assert calls == ["deepseek", "mock"]

    def test_order_configurable_via_env(self, monkeypatch):
        """B1.2: YULEOSH_LLM_FALLBACK_ORDER controls the follow-up order."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ORDER", "openai,mock")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "openai": RuntimeError("openai down"),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.provider == "mock"
        # primary first, then the env-supplied order.
        assert calls == ["deepseek", "openai", "mock"]

    def test_4xx_business_error_does_not_degrade(self, monkeypatch):
        """B1.3: HTTP 4xx (e.g. invalid key) never triggers degradation."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError(
                    "DeepSeek provider (deepseek): LLM 请求在 3 次重试后失败: "
                    "HTTP Error 401: Unauthorized"
                ),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.error is not None
        assert "401" in resp.error
        # No degrade: mock never called.
        assert calls == ["deepseek"]

    def test_fallback_disabled_no_degrade(self, monkeypatch):
        """B1.4: fallback_enabled=False → legacy single-provider behaviour."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(fallback_enabled=False),
                factory,
            )
        )
        assert resp.error is not None
        assert resp.provider == "deepseek"
        assert calls == ["deepseek"]

    def test_skeleton_providers_skipped_without_call(self, monkeypatch):
        """B1.5: skeleton providers (anthropic/openai) are skipped, chat() not called."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "anthropic": None,
                "openai": None,
                "mock": None,
            },
            calls=calls,
            skeletons=["anthropic", "openai"],
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.provider == "mock"
        # anthropic/openai chat() never invoked.
        assert calls == ["deepseek", "mock"]

    def test_provider_without_key_skipped(self, monkeypatch):
        """Skeleton-like: provider with no API key is skipped, not called."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("should not be called"),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.provider == "mock"
        assert calls == ["mock"]

    def test_budget_overrun_skips_primary(self, monkeypatch):
        """B1.6: budget overrun → skip primary, degrade, warn (no error)."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("should not be called"),
                "mock": None,
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
                skip_primary_reason="budget_exceeded",
            )
        )
        assert resp.error is None
        assert resp.provider == "mock"
        # Primary never attempted when skipped for budget.
        assert calls == ["mock"]

    def test_chain_exhausted_returns_last_error(self, monkeypatch):
        """B1.7: whole chain fails → error response with last failure."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        calls: list = []
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "anthropic": RuntimeError("anthropic down"),
                "openai": RuntimeError("openai down"),
                "mock": RuntimeError("mock down"),
            },
            calls=calls,
        )
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.error is not None
        assert resp.provider == "deepseek"  # primary reported
        assert calls == ["deepseek", "anthropic", "openai", "mock"]

    def test_primary_success_no_degrade(self, monkeypatch):
        """Happy path: primary succeeds — no degrade, no event log."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        factory = make_factory({"deepseek": None, "mock": None}, calls=calls)
        resp = run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        assert resp.provider == "deepseek"
        assert calls == ["deepseek"]


# ---------------------------------------------------------------------------
# B2 — configuration parsing
# ---------------------------------------------------------------------------


class TestConfigParsing:
    def test_fallback_enabled_default_true(self):
        assert fallback_enabled() is True
        assert fallback_enabled(base_config()) is True

    def test_fallback_enabled_env_false(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "false")
        assert fallback_enabled() is False
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "0")
        assert fallback_enabled() is False
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "off")
        assert fallback_enabled() is False

    def test_fallback_enabled_env_true_forms(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "true")
        assert fallback_enabled() is True
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "1")
        assert fallback_enabled() is True

    def test_config_overrides_env(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ENABLED", "false")
        assert fallback_enabled(base_config(fallback_enabled=True)) is True

    def test_invalid_order_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ORDER", "bogus,mock")
        with pytest.raises(ValueError, match="bogus"):
            resolve_fallback_order()

    def test_invalid_config_order_raises_value_error(self):
        with pytest.raises(ValueError, match="nope"):
            resolve_fallback_order(base_config(fallback_order=["nope"]))

    def test_default_order(self):
        assert resolve_fallback_order() == list(DEFAULT_FALLBACK_ORDER)

    def test_config_order_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ORDER", "openai,mock")
        chain = resolve_fallback_order(base_config(fallback_order=["mock"]))
        assert chain == ["deepseek", "mock"]

    def test_env_order_with_primary_first(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_PROVIDER", "anthropic")
        chain = resolve_fallback_order()
        assert chain[0] == "anthropic"
        # anthropic deduped from the fixed-order tail.
        assert chain == ["anthropic", "deepseek", "openai", "mock"]

    def test_mock_appended_when_order_omits_it(self, monkeypatch):
        """mock is always the final safety net, even if the order omits it."""
        monkeypatch.setenv("YULEOSH_LLM_FALLBACK_ORDER", "openai,anthropic")
        chain = resolve_fallback_order()
        assert chain == ["deepseek", "openai", "anthropic", "mock"]
        assert chain[-1] == "mock"

    def test_primary_first_with_config_order(self):
        chain = resolve_fallback_order(
            base_config(provider="openai", fallback_order=["mock"])
        )
        assert chain == ["openai", "mock"]

    def test_custom_provider_kept_as_primary(self):
        """Configured (custom/injected) provider stays at chain head."""
        chain = resolve_fallback_order(base_config(provider="capture"))
        assert chain[0] == "capture"
        assert chain[-1] == "mock"


# ---------------------------------------------------------------------------
# B3 — audit logging
# ---------------------------------------------------------------------------


class TestAuditLogging:
    def test_fallback_event_recorded(self, monkeypatch, _no_real_audit_log):
        """B3.1: degradation writes a fallback event (from/to/reason/duration)."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        factory = make_factory(
            {
                "deepseek": RuntimeError(
                    "DeepSeek provider (deepseek): LLM 请求在 3 次重试后失败: "
                    "HTTP Error 503: Service Unavailable"
                ),
                "mock": None,
            }
        )
        run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        events = _no_real_audit_log["fallback"]
        # deepseek 503 → degrade event; anthropic/openai skipped (no key);
        # mock succeeds. The FIRST event is the actual degradation.
        assert events
        first = events[0]
        assert first["from_provider"] == "deepseek"
        assert first["reason"] == "http_5xx"
        assert "duration_s" in first

    def test_skeleton_skip_recorded(self, monkeypatch, _no_real_audit_log):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "anthropic": None,
                "mock": None,
            },
            skeletons=["anthropic"],
        )
        run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        reasons = [ev["reason"] for ev in _no_real_audit_log["fallback"]]
        assert "skeleton" in reasons

    def test_budget_overrun_event_recorded(self, monkeypatch, _no_real_audit_log):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        factory = make_factory({"deepseek": None, "mock": None})
        run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
                skip_primary_reason="budget_exceeded",
            )
        )
        events = _no_real_audit_log["fallback"]
        assert events and events[0]["reason"] == "budget_exceeded"
        assert events[0]["from_provider"] == "deepseek"

    def test_llm_calls_log_final_provider(self, monkeypatch, _no_real_audit_log):
        """B3.2: llm_calls.jsonl provider = final provider actually used."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        factory = make_factory(
            {
                "deepseek": RuntimeError("deepseek down"),
                "mock": None,
            }
        )
        run(
            call_with_fallback(
                [{"role": "user", "content": "hi"}],
                base_config(),
                factory,
            )
        )
        # call_with_fallback itself does not write llm_calls.jsonl; LLMClient
        # does. Verify via LLMClient integration below.
        assert _no_real_audit_log["calls"] == []


# ---------------------------------------------------------------------------
# Unit tests for classification / availability helpers
# ---------------------------------------------------------------------------


class TestClassification:
    def test_http_4xx_not_eligible(self):
        assert not is_fallback_eligible(
            RuntimeError("... HTTP Error 401: Unauthorized")
        )
        assert not is_fallback_eligible(
            urllib.error.HTTPError("url", 403, "Forbidden", None, None)
        )

    def test_http_5xx_and_429_eligible(self):
        assert is_fallback_eligible(
            RuntimeError("... HTTP Error 503: Service Unavailable")
        )
        assert is_fallback_eligible(
            urllib.error.HTTPError("url", 429, "Too Many", None, None)
        )
        assert is_fallback_eligible(
            urllib.error.HTTPError("url", 500, "Internal", None, None)
        )

    def test_network_errors_eligible(self):
        assert is_fallback_eligible(ConnectionError("refused"))
        assert is_fallback_eligible(TimeoutError("timed out"))
        assert is_fallback_eligible(OSError("network unreachable"))

    def test_value_error_not_eligible(self):
        assert not is_fallback_eligible(ValueError("bad config"))

    def test_generic_runtime_error_eligible(self):
        # DeepSeekProvider raises RuntimeError after retries.
        assert is_fallback_eligible(RuntimeError("provider transport failure"))


class TestAvailability:
    def test_mock_always_available(self):
        assert provider_available("mock", object()) is True

    def test_skeleton_not_available(self):
        assert provider_available("anthropic", FakeProvider("anthropic", skeleton=True)) is False

    def test_key_gating(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        assert provider_available("deepseek", FakeProvider("deepseek")) is False
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        assert provider_available("deepseek", FakeProvider("deepseek")) is True
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setenv("LLM_API_KEY", "sk-llm")
        assert provider_available("deepseek", FakeProvider("deepseek")) is True


# ---------------------------------------------------------------------------
# LLMClient.call integration (regression for the client path)
# ---------------------------------------------------------------------------


class TestClientIntegration:
    def test_call_degrades_to_mock(self, monkeypatch, _no_real_audit_log):
        """End-to-end: LLMClient.call with failing primary → mock response."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        LLMClient.configure_providers(
            {
                "deepseek": FakeProvider(
                    "deepseek",
                    fail_with=RuntimeError(
                        "DeepSeek provider (deepseek): LLM 请求在 3 次重试后失败: "
                        "<urlopen error timed out>"
                    ),
                    calls=calls,
                ),
                "mock": FakeProvider("mock", calls=calls),
            }
        )
        resp = run(
            LLMClient.call(
                prompt="hello",
                config=base_config(),
            )
        )
        assert resp.error is None
        assert resp.provider == "mock"
        # llm_calls.jsonl records the final provider (B3.2).
        logged = _no_real_audit_log["calls"]
        assert logged and logged[0]["provider"] == "mock"
        assert logged[0]["status"] == "success"
        # fallback event recorded too.
        assert _no_real_audit_log["fallback"]

    def test_call_4xx_no_degrade(self, monkeypatch, _no_real_audit_log):
        """End-to-end: 4xx business error returns error, no degrade."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        LLMClient.configure_providers(
            {
                "deepseek": FakeProvider(
                    "deepseek",
                    fail_with=RuntimeError(
                        "DeepSeek provider (deepseek): LLM 请求在 3 次重试后失败: "
                        "HTTP Error 401: Unauthorized"
                    ),
                    calls=calls,
                ),
                "mock": FakeProvider("mock", calls=calls),
            }
        )
        resp = run(
            LLMClient.call(
                prompt="hello",
                config=base_config(),
            )
        )
        assert resp.error is not None
        assert resp.provider == "deepseek"
        assert calls == ["deepseek"]
        logged = _no_real_audit_log["calls"]
        assert logged and logged[0]["status"].startswith("failed:")

    def test_call_budget_overrun_degrades(self, monkeypatch, _no_real_audit_log):
        """End-to-end: budget pre-check failure → warning + degrade to mock."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        LLMClient.configure_providers(
            {
                "deepseek": FakeProvider(
                    "deepseek",
                    fail_with=RuntimeError("should not be called"),
                    calls=calls,
                ),
                "mock": FakeProvider("mock", calls=calls),
            }
        )
        resp = run(
            LLMClient.call(
                prompt="hello",
                config=base_config(max_cost_usd=1e-9),
            )
        )
        # Budget check failed for primary → skipped, degraded to mock.
        assert resp.error is None
        assert resp.provider == "mock"
        assert calls == ["mock"]
        assert _no_real_audit_log["fallback"]
        assert _no_real_audit_log["fallback"][0]["reason"] == "budget_exceeded"

    def test_call_fallback_disabled_returns_error(self, monkeypatch, _no_real_audit_log):
        """End-to-end: fallback disabled → failure surfaces as error response."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        calls: list = []
        LLMClient.configure_providers(
            {
                "deepseek": FakeProvider(
                    "deepseek",
                    fail_with=RuntimeError("deepseek down"),
                    calls=calls,
                ),
                "mock": FakeProvider("mock", calls=calls),
            }
        )
        resp = run(
            LLMClient.call(
                prompt="hello",
                config=base_config(fallback_enabled=False),
            )
        )
        assert resp.error is not None
        assert resp.provider == "deepseek"
        assert calls == ["deepseek"]
        assert _no_real_audit_log["fallback"] == []

    def test_call_happy_path_no_events(self, monkeypatch, _no_real_audit_log):
        """End-to-end: primary success → no fallback events, final provider logged."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        LLMClient.configure_providers(
            {
                "deepseek": FakeProvider("deepseek"),
                "mock": FakeProvider("mock"),
            }
        )
        resp = run(
            LLMClient.call(
                prompt="hello",
                config=base_config(),
            )
        )
        assert resp.provider == "deepseek"
        assert _no_real_audit_log["fallback"] == []
        logged = _no_real_audit_log["calls"]
        assert logged and logged[0]["provider"] == "deepseek"
