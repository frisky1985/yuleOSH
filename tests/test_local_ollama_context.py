"""本地 Ollama 闭环守卫：num_ctx 透传 + 本地模型预算检查不误降级。

背景（2026-09-03）：ollama 服务默认 context=4096，真实 step 输入（spec+RULES+
knowledge injection）常超 4096 → 400 exceed_context_size_error。同时本地模型
不在 PRICING_TABLE 时预算检查判失败、统一入口会把调用降级到云端备用 provider。
两处修复后，本地端点请求须自带 num_ctx，且本地 tag 须过预算检查、不误回退。
"""
import importlib

import pytest

from yuleosh.llm.providers.base import LLMConfig, PRICING_TABLE
from yuleosh.llm.providers.deepseek import DeepSeekProvider


def _reload_base():
    """PRICING_TABLE / _DEFAULT_LLM_CONTEXT_WINDOW 在 import 时读 env，需干净重载。"""
    import yuleosh.llm.providers.base as base

    return importlib.reload(base)


def test_local_endpoint_detection():
    assert DeepSeekProvider._is_local_ollama("http://localhost:11434") is True
    assert DeepSeekProvider._is_local_ollama("http://127.0.0.1:11434") is True
    assert DeepSeekProvider._is_local_ollama("http://0.0.0.0:11434") is True
    assert DeepSeekProvider._is_local_ollama("http://ollama:11434") is True
    assert DeepSeekProvider._is_local_ollama("https://api.deepseek.com") is False
    assert DeepSeekProvider._is_local_ollama("https://api.openai.com") is False


def test_context_window_default_32768(monkeypatch):
    monkeypatch.delenv("YULEOSH_LLM_CONTEXT_WINDOW", raising=False)
    base = _reload_base()
    assert base.LLMConfig().context_window == 32768
    # 恢复模块（避免影响其它测试）
    _reload_base()


def test_context_window_env_override(monkeypatch):
    monkeypatch.setenv("YULEOSH_LLM_CONTEXT_WINDOW", "65536")
    base = _reload_base()
    assert base.LLMConfig().context_window == 65536
    _reload_base()


def test_local_model_pricing_registered_no_fallback():
    # 本地 tag 必须在 PRICING_TABLE，否则统一入口预算检查失败 → 降级云端
    for tag in ("qwen2.5-coder:14b", "qwen2.5-coder:7b", "deepseek-r1:7b"):
        assert tag in PRICING_TABLE, f"{tag} 必须在 PRICING_TABLE（否则误降级）"
        assert PRICING_TABLE[tag]["input_per_1k"] == 0.0
        assert PRICING_TABLE[tag]["context_window"] >= 32768


def test_chat_completion_injects_num_ctx_for_local(monkeypatch):
    """本地端点请求体须含 num_ctx；云端端点不含。"""
    import json

    captured = {}

    def fake_post_json(url, headers, body, *, timeout_s, max_retries):
        captured["body"] = body
        captured["url"] = url
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(DeepSeekProvider, "_post_json", staticmethod(fake_post_json))
    monkeypatch.setenv("LLM_API_KEY", "ollama")  # provider 调用时读 key

    import asyncio

    cfg = LLMConfig(model="qwen2.5-coder:14b", provider="deepseek", context_window=32768)
    prov = DeepSeekProvider(base_url="http://localhost:11434")
    resp = asyncio.run(
        prov.chat(messages=[{"role": "user", "content": "hi"}], config=cfg)
    )
    assert resp.content == "ok"
    assert captured["body"].get("num_ctx") == 32768

    # 云端端点不注入 num_ctx
    cfg2 = LLMConfig(model="deepseek-v4", provider="deepseek", context_window=32768)
    prov2 = DeepSeekProvider(base_url="https://api.deepseek.com")
    resp2 = asyncio.run(
        prov2.chat(messages=[{"role": "user", "content": "hi"}], config=cfg2)
    )
    assert "num_ctx" not in captured.get("body", {})
