
# @tests src/yuleosh/llm/client.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for 方案 A — DeepSeek provider + 配置优先级体系 (YULEOSH_LLM_PROVIDER).

Covers:
- provider registry: _get_provider returns deepseek/anthropic/openai instances
- resolve_config priority: explicit config > YULEOSH_LLM_PROVIDER > TASK_ROUTES
- LLM_MODEL env compatibility
- DeepSeekProvider.chat: model alias mapping, success/retry/error paths
- DeepSeekProvider.estimate_cost pricing

All tests are mocked — no real network calls (AC9).
"""

import asyncio
import json
import os
from unittest import mock

import pytest

from yuleosh.llm.client import LLMClient, _get_provider, resolve_config
from yuleosh.llm.providers.anthropic import ClaudeProvider
from yuleosh.llm.providers.base import LLMConfig
from yuleosh.llm.providers.deepseek import DeepSeekProvider
from yuleosh.llm.providers.openai import OpenAIProvider


@pytest.fixture(autouse=True)
def _clean_env_and_registry():
    """Isolate each test: no host env leaks, fresh provider registry."""
    LLMClient.reset()
    with mock.patch.dict(os.environ, {}, clear=True):
        yield
    LLMClient.reset()


def _fake_urlopen(response_body: dict):
    """Build a urlopen mock returning *response_body* JSON (chat_completion style)."""
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = json.dumps(response_body).encode()
    fake_ctx = mock.MagicMock()
    fake_ctx.__enter__.return_value = fake_resp
    fake_ctx.__exit__.return_value = False
    mock_urlopen = mock.MagicMock(return_value=fake_ctx)
    return mock_urlopen


def _http_error(code: int = 500):
    import urllib.error

    return urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs={}, fp=None)


# ---------------------------------------------------------------------------
# Provider registry (AC1)
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_get_provider_deepseek(self):
        """GIVEN 'deepseek' WHEN _get_provider THEN DeepSeekProvider instance."""
        provider = _get_provider("deepseek")
        assert isinstance(provider, DeepSeekProvider)
        assert provider.provider_name == "deepseek"

    def test_get_provider_anthropic_skeleton(self):
        """GIVEN 'anthropic' WHEN _get_provider THEN ClaudeProvider instance."""
        provider = _get_provider("anthropic")
        assert isinstance(provider, ClaudeProvider)
        assert provider.provider_name == "anthropic"

    def test_get_provider_openai_skeleton(self):
        """GIVEN 'openai' WHEN _get_provider THEN OpenAIProvider instance."""
        provider = _get_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "openai"

    def test_get_provider_unknown_raises(self):
        """GIVEN unknown name WHEN _get_provider THEN ValueError."""
        with pytest.raises(ValueError):
            _get_provider("nope")

    def test_providers_package_exports(self):
        """GIVEN providers package THEN new classes exported."""
        import yuleosh.llm.providers as p

        assert p.DeepSeekProvider is DeepSeekProvider
        assert p.ClaudeProvider is ClaudeProvider
        assert p.OpenAIProvider is OpenAIProvider


# ---------------------------------------------------------------------------
# resolve_config — 配置优先级体系 (AC2/AC3/AC4)
# ---------------------------------------------------------------------------


class TestResolveConfigPriority:
    def test_default_deepseek_no_env(self):
        """GIVEN no env WHEN resolve_config THEN provider=deepseek (existing behavior)."""
        cfg = resolve_config("hi", None, None, None)
        assert cfg.provider == "deepseek"
        assert cfg.model == "deepseek-v4"

    def test_env_anthropic_overrides_default(self):
        """GIVEN YULEOSH_LLM_PROVIDER=anthropic WHEN resolve_config THEN provider=anthropic."""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "anthropic"}):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-4-sonnet"

    def test_env_openai_overrides_default(self):
        """GIVEN YULEOSH_LLM_PROVIDER=openai WHEN resolve_config THEN provider=openai."""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "openai"}):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"

    def test_env_mock(self):
        """GIVEN YULEOSH_LLM_PROVIDER=mock WHEN resolve_config THEN provider=mock."""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "mock"}):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.provider == "mock"

    def test_env_case_insensitive(self):
        """GIVEN YULEOSH_LLM_PROVIDER=' DeepSeek ' WHEN resolve_config THEN normalized."""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": " DeepSeek "}):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.provider == "deepseek"

    def test_explicit_config_beats_env(self):
        """GIVEN explicit config + env WHEN resolve_config THEN explicit config wins."""
        explicit = LLMConfig(model="custom-model", provider="mock")
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "anthropic"}):
            cfg = resolve_config("hi", None, None, explicit)
        assert cfg is explicit
        assert cfg.provider == "mock"
        assert cfg.model == "custom-model"

    def test_invalid_env_raises_value_error(self):
        """GIVEN invalid YULEOSH_LLM_PROVIDER WHEN resolve_config THEN ValueError."""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "bogus"}):
            with pytest.raises(ValueError) as exc_info:
                resolve_config("hi", None, None, None)
        msg = str(exc_info.value)
        assert "deepseek" in msg
        assert "anthropic" in msg
        assert "bogus" in msg

    def test_llm_model_env_respected(self):
        """GIVEN LLM_MODEL=deepseek-chat WHEN resolve_config THEN model from env."""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.model == "deepseek-chat"
        assert cfg.provider == "deepseek"

    def test_llm_model_env_with_provider_env(self):
        """GIVEN LLM_MODEL + YULEOSH_LLM_PROVIDER WHEN resolve_config THEN both honored."""
        with mock.patch.dict(
            os.environ,
            {"LLM_MODEL": "claude-4-haiku", "YULEOSH_LLM_PROVIDER": "anthropic"},
        ):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.model == "claude-4-haiku"
        assert cfg.provider == "anthropic"

    def test_task_routes_still_work(self):
        """GIVEN task_type=architecture_design WHEN resolve_config THEN TASK_ROUTES applies."""
        cfg = resolve_config("hi", None, "architecture_design", None)
        assert cfg.model == "claude-4-sonnet"
        assert cfg.provider == "anthropic"


# ---------------------------------------------------------------------------
# DeepSeekProvider.estimate_cost (AC6)
# ---------------------------------------------------------------------------


class TestDeepSeekEstimateCost:
    def test_pricing_1000_1000(self):
        """GIVEN 1000 in + 1000 out WHEN estimate_cost THEN $0.002 + $0.008 = $0.010."""
        provider = DeepSeekProvider()
        assert provider.estimate_cost(1000, 1000) == pytest.approx(0.010)

    def test_pricing_zero(self):
        """GIVEN 0 tokens WHEN estimate_cost THEN 0.0."""
        provider = DeepSeekProvider()
        assert provider.estimate_cost(0, 0) == 0.0

    def test_pricing_half_k(self):
        """GIVEN 500 in + 500 out WHEN estimate_cost THEN $0.001 + $0.004 = $0.005."""
        provider = DeepSeekProvider()
        assert provider.estimate_cost(500, 500) == pytest.approx(0.005)

    def test_pricing_matches_pricing_table(self):
        """GIVEN PRICING_TABLE WHEN estimate_cost THEN same numbers (no duplication)."""
        from yuleosh.llm.providers.base import PRICING_TABLE

        pricing = PRICING_TABLE["deepseek-v4"]
        provider = DeepSeekProvider()
        assert provider.estimate_cost(1000, 1000) == pytest.approx(
            pricing["input_per_1k"] + pricing["output_per_1k"]
        )


# ---------------------------------------------------------------------------
# DeepSeekProvider.chat — 错误路径 (AC5)
# ---------------------------------------------------------------------------


class TestDeepSeekChatErrors:
    def test_missing_api_key_error_contains_provider(self):
        """GIVEN no API key WHEN chat THEN RuntimeError naming provider + key env."""
        provider = DeepSeekProvider()
        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(
                provider.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(),
                )
            )
        msg = str(exc_info.value)
        assert "deepseek" in msg
        assert "DEEPSEEK_API_KEY" in msg

    def test_retry_exhausted_raises_with_provider(self):
        """GIVEN persistent HTTPError WHEN chat THEN RuntimeError naming provider."""
        mock_urlopen = mock.MagicMock(side_effect=_http_error(500))
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with mock.patch("time.sleep"):
                    with pytest.raises(RuntimeError) as exc_info:
                        asyncio.run(
                            DeepSeekProvider().chat(
                                messages=[{"role": "user", "content": "hi"}],
                                config=LLMConfig(max_retries=2),
                            )
                        )
        assert "deepseek" in str(exc_info.value)

    def test_no_choices_raises_with_provider(self):
        """GIVEN response without choices WHEN chat THEN RuntimeError naming provider."""
        mock_urlopen = _fake_urlopen({"model": "deepseek-chat", "usage": {}})
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with pytest.raises(RuntimeError) as exc_info:
                    asyncio.run(
                        DeepSeekProvider().chat(
                            messages=[{"role": "user", "content": "hi"}],
                            config=LLMConfig(max_retries=1),
                        )
                    )
        assert "deepseek" in str(exc_info.value)


# ---------------------------------------------------------------------------
# DeepSeekProvider.chat — 成功路径 (AC2/AC4)
# ---------------------------------------------------------------------------


class TestDeepSeekChatSuccess:
    def _response_body(self, **overrides):
        body = {
            "id": "chatcmpl-test",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello from DeepSeek!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 1000,
                "total_tokens": 2000,
            },
        }
        body.update(overrides)
        return body

    def test_chat_success_request_model_mapped(self):
        """GIVEN config.model=deepseek-v4 WHEN chat THEN request body model=deepseek-chat."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-test", "LLM_BASE_URL": "https://api.deepseek.com"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    DeepSeekProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="deepseek-v4"),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://api.deepseek.com/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-test"
        body = json.loads(req.data)
        assert body["model"] == "deepseek-chat"
        assert body["stream"] is False

        assert resp.content == "Hello from DeepSeek!"
        assert resp.model == "deepseek-chat"
        assert resp.provider == "deepseek"
        assert resp.token_usage == {"prompt": 1000, "completion": 1000, "total": 2000}
        assert resp.cost == pytest.approx(0.010)
        assert resp.error is None

    def test_chat_uses_llm_api_key_fallback(self):
        """GIVEN only LLM_API_KEY WHEN chat THEN request succeeds."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-llm"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    DeepSeekProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(max_retries=1),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.headers["Authorization"] == "Bearer sk-llm"
        assert resp.content == "Hello from DeepSeek!"

    def test_chat_deepseek_key_preferred_over_llm_key(self):
        """GIVEN both keys WHEN chat THEN DEEPSEEK_API_KEY wins."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-ds", "LLM_API_KEY": "sk-llm"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                asyncio.run(
                    DeepSeekProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(max_retries=1),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.headers["Authorization"] == "Bearer sk-ds"

    def test_chat_custom_base_url_and_model(self):
        """GIVEN LLM_BASE_URL + custom model WHEN chat THEN URL/model honored."""
        mock_urlopen = _fake_urlopen(
            self._response_body(model="deepseek-reasoner")
        )
        with mock.patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-test", "LLM_BASE_URL": "https://proxy.example.com"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    DeepSeekProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="deepseek-reasoner"),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://proxy.example.com/v1/chat/completions"
        body = json.loads(req.data)
        assert body["model"] == "deepseek-reasoner"
        assert resp.model == "deepseek-reasoner"

    def test_chat_retry_then_success(self):
        """GIVEN one HTTPError then success WHEN chat THEN returns content (CQ-P1-02)."""
        ok_ctx = _fake_urlopen(self._response_body())
        mock_urlopen = mock.MagicMock(side_effect=[_http_error(429), ok_ctx.return_value])
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with mock.patch("time.sleep") as m_sleep:
                    resp = asyncio.run(
                        DeepSeekProvider().chat(
                            messages=[{"role": "user", "content": "hi"}],
                            config=LLMConfig(max_retries=2),
                        )
                    )
        assert resp.content == "Hello from DeepSeek!"
        assert m_sleep.call_args[0][0] == 1.0  # backoff 1.0s after first attempt

    def test_chat_null_content_refusal(self):
        """GIVEN content=null WHEN chat THEN refusal message with finish_reason."""
        mock_urlopen = _fake_urlopen(
            self._response_body(
                choices=[{"message": {"role": "assistant", "content": None}, "finish_reason": "length"}]
            )
        )
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    DeepSeekProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(max_retries=1),
                    )
                )
        assert "refused" in resp.content
        assert "length" in resp.content


# ---------------------------------------------------------------------------
# 骨架 provider (AC7)
# ---------------------------------------------------------------------------


class TestSkeletonProviders:
    def test_anthropic_chat_not_implemented(self):
        """GIVEN ClaudeProvider WHEN chat THEN NotImplementedError with 预留 note."""
        with pytest.raises(NotImplementedError) as exc_info:
            asyncio.run(
                ClaudeProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="claude-4-sonnet"),
                )
            )
        assert "预留" in str(exc_info.value)
        assert "anthropic" in str(exc_info.value)

    def test_openai_no_longer_skeleton(self):
        """GIVEN OpenAIProvider WHEN chat with no key THEN RuntimeError (not NotImplementedError).

        方案 A 已落地真实调用（见 TestOpenAIProvider）；此处仅确认不再是 skeleton
        占位、缺 key 时抛 RuntimeError 且绝不抛 NotImplementedError。
        """
        assert not getattr(OpenAIProvider, "is_skeleton", False)
        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(
                OpenAIProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="gpt-4o"),
                )
            )
        assert "openai" in str(exc_info.value)
        assert "NotImplemented" not in str(exc_info.value)

    def test_skeleton_estimate_cost(self):
        """GIVEN skeleton providers WHEN estimate_cost THEN PRICING_TABLE numbers."""
        assert ClaudeProvider().estimate_cost(1000, 1000) == pytest.approx(0.015 + 0.075)
        assert OpenAIProvider().estimate_cost(1000, 1000) == pytest.approx(0.010 + 0.030)


# ---------------------------------------------------------------------------
# OpenAIProvider.chat — 真实实现 (方案 A, 替代原 skeleton NotImplementedError)
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    def _response_body(self, **overrides):
        body = {
            "id": "chatcmpl-test",
            "model": "gpt-4o",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello from OpenAI!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 1000,
                "total_tokens": 2000,
            },
        }
        body.update(overrides)
        return body

    def test_chat_success_default_model(self):
        """GIVEN config.model=gpt-4o WHEN chat THEN request model honored."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-openai", "LLM_BASE_URL": "https://api.openai.com"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="gpt-4o"),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://api.openai.com/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-openai"
        body = json.loads(req.data)
        assert body["model"] == "gpt-4o"
        assert body["stream"] is False
        assert resp.content == "Hello from OpenAI!"
        assert resp.provider == "openai"
        assert resp.model == "gpt-4o"
        assert resp.token_usage == {"prompt": 1000, "completion": 1000, "total": 2000}
        assert resp.cost == pytest.approx(0.010 + 0.030)
        assert resp.error is None

    def test_chat_uses_llm_api_key(self):
        """GIVEN only LLM_API_KEY WHEN chat THEN request succeeds (自建端点场景)."""
        mock_urlopen = _fake_urlopen(self._response_body(model="deepseek-r1:7b"))
        with mock.patch.dict(
            os.environ,
            {"LLM_API_KEY": "ollama", "LLM_BASE_URL": "http://localhost:11434/v1"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="deepseek-r1:7b"),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.headers["Authorization"] == "Bearer ollama"
        # OpenAI 兼容端点直接使用 config.model（Ollama tag）。
        assert json.loads(req.data)["model"] == "deepseek-r1:7b"
        assert resp.model == "deepseek-r1:7b"

    def test_chat_openai_key_preferred_over_llm_key(self):
        """GIVEN both keys WHEN chat THEN OPENAI_API_KEY wins (与 deepseek 对称)."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-oai", "LLM_API_KEY": "sk-llm"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="gpt-4o", max_retries=1),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.headers["Authorization"] == "Bearer sk-oai"

    def test_chat_custom_base_url(self):
        """GIVEN LLM_BASE_URL override WHEN chat THEN URL honored."""
        mock_urlopen = _fake_urlopen(self._response_body())
        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-openai", "LLM_BASE_URL": "https://proxy.example.com"},
        ):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="gpt-4o", max_retries=1),
                    )
                )
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://proxy.example.com/v1/chat/completions"
        assert resp.model == "gpt-4o"

    def test_chat_missing_api_key_error_contains_provider(self):
        """GIVEN no API key WHEN chat THEN RuntimeError naming provider + key envs."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="gpt-4o"),
                    )
                )
        msg = str(exc_info.value)
        assert "openai" in msg
        assert "OPENAI_API_KEY" in msg
        assert "LLM_API_KEY" in msg

    def test_chat_retry_exhausted_raises_with_provider(self):
        """GIVEN persistent HTTPError WHEN chat THEN RuntimeError naming provider."""
        mock_urlopen = mock.MagicMock(side_effect=_http_error(500))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with mock.patch("time.sleep"):
                    with pytest.raises(RuntimeError) as exc_info:
                        asyncio.run(
                            OpenAIProvider().chat(
                                messages=[{"role": "user", "content": "hi"}],
                                config=LLMConfig(max_retries=2),
                            )
                        )
        assert "openai" in str(exc_info.value)

    def test_chat_no_choices_raises_with_provider(self):
        """GIVEN response without choices WHEN chat THEN RuntimeError naming provider."""
        mock_urlopen = _fake_urlopen({"model": "gpt-4o", "usage": {}})
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with pytest.raises(RuntimeError) as exc_info:
                    asyncio.run(
                        OpenAIProvider().chat(
                            messages=[{"role": "user", "content": "hi"}],
                            config=LLMConfig(max_retries=1),
                        )
                    )
        assert "openai" in str(exc_info.value)

    def test_chat_null_content_refusal(self):
        """GIVEN content=null WHEN chat THEN refusal message with finish_reason."""
        mock_urlopen = _fake_urlopen(
            self._response_body(
                choices=[{"message": {"role": "assistant", "content": None}, "finish_reason": "length"}]
            )
        )
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(
                    OpenAIProvider().chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(max_retries=1),
                    )
                )
        assert "refused" in resp.content
        assert "length" in resp.content
