#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
tests/test_llm_local_fallback.py — 外部 LLM 不可用 → 本地 Ollama 降级。

覆盖：
- chat_completion 默认路径：外部调用 is_provider_unavailable → 自动改调本地
  Ollama 并返回真实内容；本地也不可用 → re-raise 原始错误（handler 仍 skipped）。
- OllamaProvider：模型自动解析（偏好 coder 模型）、可用时 is_available=True、
  无模型/不可达时抛错。
- provider_fallback：ollama 纳入 VALID_PROVIDERS / DEFAULT_FALLBACK_ORDER，
  provider_available 按可达性判断，401/402/403 纳入可降级码。

本地路径（真实 Ollama）用 skipif 守卫，避免 CI 无 Ollama 时飘；其余用 mock，
不依赖网络。
"""

from __future__ import annotations

import asyncio
import os
import sys
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

# 在导入被测模块前清掉可能干扰的 env（测试显式 setenv）
for _v in ("YULEOSH_LLM_UNIFIED", "YULEOSH_LLM_LOCAL_FALLBACK", "OLLAMA_HOST"):
    os.environ.pop(_v, None)

from yuleosh.llm.client import (  # noqa: E402
    _call_local_ollama,
    _get_provider,
    _local_llm_fallback_enabled,
    chat_completion,
    is_provider_unavailable,
)
from yuleosh.llm.providers.base import LLMConfig  # noqa: E402
from yuleosh.llm.providers.ollama import OllamaProvider  # noqa: E402
from yuleosh.llm.provider_fallback import (  # noqa: E402
    DEFAULT_FALLBACK_ORDER,
    VALID_PROVIDERS,
    _DEGRADE_HTTP_CODES,
    is_fallback_eligible,
    provider_available,
    resolve_fallback_order,
)


def _ollama_running() -> bool:
    try:
        return OllamaProvider().is_available()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
# OllamaProvider 单元
# ═══════════════════════════════════════════════════════════════════════


class TestOllamaProvider:
    def test_provider_name(self):
        assert OllamaProvider().provider_name == "ollama"

    def test_estimate_cost_zero(self):
        assert OllamaProvider().estimate_cost(100, 50) == 0.0

    def test_resolve_model_prefers_coder(self):
        # _resolve_model 仅在 Ollama 可用时调用；用 mock 隔离网络
        p = OllamaProvider()
        with patch.object(p, "_list_models", return_value=["qwen:latest", "qwen2.5-coder:14b"]):
            assert p._resolve_model("qwen2.5-coder:14b") == "qwen2.5-coder:14b"

    def test_resolve_model_falls_back_to_preference(self):
        p = OllamaProvider()
        with patch.object(p, "_list_models", return_value=["qwen:latest"]):
            # qwen:latest 命中偏好列表末位 → 选中
            assert p._resolve_model("deepseek-chat") == "qwen:latest"

    def test_resolve_model_raises_when_no_models(self):
        p = OllamaProvider()
        with patch.object(p, "_list_models", return_value=[]):
            with pytest.raises(RuntimeError, match="无可用模型"):
                p._resolve_model("qwen2.5-coder:14b")

    def test_is_available_true_when_reachable(self):
        p = OllamaProvider()
        with patch.object(p, "_list_models", return_value=["qwen2.5-coder:14b"]):
            assert p.is_available() is True

    def test_is_available_false_when_unreachable(self):
        p = OllamaProvider()
        with patch.object(
            p, "_list_models", side_effect=urllib.error.URLError("connection refused")
        ):
            assert p.is_available() is False

    def test_registered_in_get_provider(self):
        prov = _get_provider("ollama")
        assert isinstance(prov, OllamaProvider)

    def test_chat_sync_returns_legacy_dict_shape(self):
        """真实直连本地 Ollama（若可用），验证返回 dict 形态与内容。"""
        if not _ollama_running():
            pytest.skip("本地 Ollama 未运行，跳过真实调用")
        p = OllamaProvider()
        out = p.chat_sync(
            [
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "Reply with exactly: UNITTEST_OK"},
            ],
            LLMConfig(model="qwen2.5-coder:14b", max_tokens=64, temperature=0.2,
                      timeout_s=600, context_window=8192),
        )
        assert "content" in out and "model" in out and "usage" in out
        assert "UNITTEST_OK" in out["content"]
        assert out["usage"]["total_tokens"] > 0


# ═══════════════════════════════════════════════════════════════════════
# provider_fallback 链集成
# ═══════════════════════════════════════════════════════════════════════


class TestProviderFallbackChain:
    def test_ollama_in_valid_providers(self):
        assert "ollama" in VALID_PROVIDERS

    def test_ollama_in_default_order(self):
        assert "ollama" in DEFAULT_FALLBACK_ORDER
        # ollama 在 mock 之前
        assert DEFAULT_FALLBACK_ORDER.index("ollama") < DEFAULT_FALLBACK_ORDER.index("mock")

    def test_resolve_order_contains_ollama(self):
        order = resolve_fallback_order()
        assert order == list(DEFAULT_FALLBACK_ORDER)
        assert "ollama" in order

    def test_provider_available_ollama_true_when_running(self):
        with patch.object(OllamaProvider, "is_available", lambda self: True):
            assert provider_available("ollama", OllamaProvider()) is True

    def test_provider_available_ollama_false_when_down(self):
        with patch.object(OllamaProvider, "is_available", lambda self: False):
            assert provider_available("ollama", OllamaProvider()) is False

    def test_402_now_degradable(self):
        # 外部账户级失败（402）现在应触发 provider 降级，使链能落到本地 Ollama
        assert 402 in _DEGRADE_HTTP_CODES
        assert 401 in _DEGRADE_HTTP_CODES
        assert 403 in _DEGRADE_HTTP_CODES

    def test_is_fallback_eligible_on_402_http_error(self):
        err = urllib.error.HTTPError(
            "http://x", 402, "Payment Required", {}, None
        )
        assert is_fallback_eligible(err) is True


# ═══════════════════════════════════════════════════════════════════════
# chat_completion 本地降级（网络无关，全 mock）
# ═══════════════════════════════════════════════════════════════════════


def _http402() -> RuntimeError:
    """模拟 deepseek 客户端把 402 包装后的 RuntimeError（字符串含 '402'）。"""
    return RuntimeError("LLM request failed after 3 retries: HTTP Error 402: Payment Required")


class TestChatCompletionLocalFallback:
    def test_external_402_falls_back_to_local(self, monkeypatch):
        """外部不可用 → 本地 Ollama 返回真实内容（无真实网络）。"""
        monkeypatch.setattr(
            urllib.request, "urlopen", MagicMock(side_effect=_http402())
        )
        local_out = {
            "content": "LOCAL_CONTENT",
            "model": "qwen2.5-coder:14b",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        monkeypatch.setattr(
            "yuleosh.llm.client._call_local_ollama", lambda *a, **k: local_out
        )
        out = chat_completion("sys", "user", max_tokens=64, timeout=10, retries=1)
        assert out["content"] == "LOCAL_CONTENT"
        assert out["model"] == "qwen2.5-coder:14b"

    def test_local_unavailable_reraises_original_error(self, monkeypatch):
        """本地也不可用 → re-raise 原始外部错误（handler 仍按 is_provider_unavailable 跳过）。"""
        monkeypatch.setattr(
            urllib.request, "urlopen", MagicMock(side_effect=_http402())
        )
        monkeypatch.setattr(
            "yuleosh.llm.client._call_local_ollama",
            MagicMock(side_effect=RuntimeError("本地 Ollama 不可用")),
        )
        with pytest.raises(RuntimeError) as exc:
            chat_completion("sys", "user", max_tokens=32, timeout=10, retries=1)
        # 原始外部错误可被 handler 识别为「provider 不可用」→ 仍 skipped（不退化）
        assert is_provider_unavailable(exc.value) is True

    def test_fallback_disabled_keeps_original_behaviour(self, monkeypatch):
        """YULEOSH_LLM_LOCAL_FALLBACK=0 → 不做本地降级，直接抛原始错误。"""
        monkeypatch.setenv("YULEOSH_LLM_LOCAL_FALLBACK", "0")
        monkeypatch.setattr(
            urllib.request, "urlopen", MagicMock(side_effect=_http402())
        )
        called = {"local": False}

        def _fake_local(*a, **k):
            called["local"] = True
            raise RuntimeError("should not be called")

        monkeypatch.setattr("yuleosh.llm.client._call_local_ollama", _fake_local)
        with pytest.raises(RuntimeError):
            chat_completion("sys", "user", max_tokens=32, timeout=10, retries=1)
        assert called["local"] is False

    def test_local_fallback_enabled_default_true(self):
        # 清掉 env（模块顶部已 pop），默认开启
        assert _local_llm_fallback_enabled() is True
