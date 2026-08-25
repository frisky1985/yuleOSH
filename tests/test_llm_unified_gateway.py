
# @tests src/yuleosh/llm/client.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""方案 C (C1+C2) — LLM 统一入口同步桥接层测试。

C1: ``LLMClient.call_sync`` 同步桥接（async ``call`` → 旧 dict 格式）。
C2: ``chat_completion`` 支持 ``YULEOSH_LLM_UNIFIED=1`` 切换统一入口。

覆盖：
- call_sync 返回旧格式 dict（content/model/OpenAI 风格 usage）
- LLMResponse.token_usage 适配（prompt/completion/total → *_tokens）
- error 非空 → RuntimeError（旧语义）
- 已有 event loop 中调用不崩（new_event_loop 分支）
- 参数透传（prompt/system_prompt/task_type/config/messages）
- chat_completion 在 flag=1 时走 call_sync；未设置时走 urllib
- temperature/max_tokens/timeout/retries 透传

所有用例全 mock，无真实网络调用。
"""

import asyncio
import json
from unittest import mock

import pytest

from yuleosh.llm.client import LLMClient, _adapt_token_usage, chat_completion
from yuleosh.llm.providers.base import LLMConfig, LLMResponse


@pytest.fixture(autouse=True)
def _clean_unified_flag(monkeypatch):
    """默认清除 YULEOSH_LLM_UNIFIED / LLM_MODEL，测试按需 opt-in。"""
    monkeypatch.delenv("YULEOSH_LLM_UNIFIED", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)


def _ok_response(content="Hello unified!", model="deepseek-v4") -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        provider="deepseek",
        token_usage={"prompt": 10, "completion": 5, "total": 15},
        cost=0.001,
        duration_s=0.2,
    )


class TestCallSync:
    """C1 — LLMClient.call_sync 同步桥接。"""

    def test_returns_legacy_dict(self):
        """call_sync 返回 {content, model, usage}，usage 为 OpenAI 风格。"""
        with mock.patch.object(
            LLMClient, "call", new=mock.AsyncMock(return_value=_ok_response())
        ):
            result = LLMClient.call_sync(prompt="hi", system_prompt="sys")

        assert isinstance(result, dict)
        assert result["content"] == "Hello unified!"
        assert result["model"] == "deepseek-v4"
        assert result["usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }

    def test_token_usage_adaptation(self):
        """{"prompt":10,"completion":5,"total":15} → OpenAI 风格 *_tokens。"""
        assert _adapt_token_usage(
            {"prompt": 10, "completion": 5, "total": 15}
        ) == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        # 已是 OpenAI 风格 → 原样透传
        assert _adapt_token_usage({"prompt_tokens": 1}) == {"prompt_tokens": 1}
        # 空 dict → 空 dict（旧语义兼容）
        assert _adapt_token_usage({}) == {}

    def test_error_raises_runtime_error(self):
        """LLMResponse.error 非空 → RuntimeError（兼容旧语义）。"""
        err_resp = LLMResponse(
            content="", model="m", provider="p",
            token_usage={}, error="upstream exploded",
        )
        with mock.patch.object(
            LLMClient, "call", new=mock.AsyncMock(return_value=err_resp)
        ), pytest.raises(RuntimeError, match="upstream exploded"):
            LLMClient.call_sync(prompt="hi")

    def test_works_inside_running_loop(self):
        """已有 running loop 时走 new_event_loop 分支，不崩且结果正确。"""
        async def _inner():
            return LLMClient.call_sync(prompt="hi", system_prompt="sys")

        with mock.patch.object(
            LLMClient, "call", new=mock.AsyncMock(return_value=_ok_response())
        ):
            result = asyncio.run(_inner())

        assert result["content"] == "Hello unified!"
        assert result["usage"]["total_tokens"] == 15

    def test_passes_arguments_through(self):
        """prompt/system_prompt/task_type/config/messages 原样透传给 call。"""
        cfg = LLMConfig(provider="mock", model="deepseek-v4", rag_enabled=False)
        msgs = [{"role": "user", "content": "hi"}]

        with mock.patch.object(
            LLMClient, "call", new=mock.AsyncMock(return_value=_ok_response())
        ) as fake_call:
            LLMClient.call_sync(
                prompt="hello",
                system_prompt="be nice",
                task_type="simple_summary",
                config=cfg,
                messages=msgs,
            )

        fake_call.assert_awaited_once_with(
            prompt="hello",
            system_prompt="be nice",
            task_type="simple_summary",
            config=cfg,
            messages=msgs,
        )


class TestChatCompletionUnified:
    """C2 — chat_completion 的 YULEOSH_LLM_UNIFIED feature flag。"""

    def test_flag_on_delegates_to_call_sync(self, monkeypatch):
        """YULEOSH_LLM_UNIFIED=1 时 chat_completion 调 call_sync 并返回其 dict。"""
        monkeypatch.setenv("YULEOSH_LLM_UNIFIED", "1")
        legacy = {
            "content": "unified!",
            "model": "deepseek-v4",
            "usage": {"total_tokens": 3},
        }

        with mock.patch.object(
            LLMClient, "call_sync", return_value=legacy
        ) as fake_sync:
            result = chat_completion("Be helpful", "Hello")

        assert result == legacy
        fake_sync.assert_called_once()
        kwargs = fake_sync.call_args.kwargs
        assert kwargs["prompt"] == "Hello"
        assert kwargs["system_prompt"] == "Be helpful"

    def test_flag_on_passes_temperature_max_tokens(self, monkeypatch):
        """temperature/max_tokens/timeout/retries 透传进 LLMConfig。"""
        monkeypatch.setenv("YULEOSH_LLM_UNIFIED", "1")
        monkeypatch.setenv("LLM_MODEL", "custom-model")

        with mock.patch.object(
            LLMClient, "call_sync", return_value={"content": "x", "model": "m", "usage": {}}
        ) as fake_sync:
            chat_completion(
                "sys", "user",
                temperature=0.9, max_tokens=512, timeout=30, retries=5,
            )

        cfg = fake_sync.call_args.kwargs["config"]
        assert isinstance(cfg, LLMConfig)
        assert cfg.temperature == 0.9
        assert cfg.max_tokens == 512
        assert cfg.timeout_s == 30
        assert cfg.max_retries == 5
        assert cfg.model == "custom-model"
        # 保持旧 chat_completion 语义：不注入 RAG / project memory
        assert cfg.rag_enabled is False
        assert cfg.memory_enabled is False

    def test_flag_on_error_response_raises(self, monkeypatch):
        """unified 模式下底层 error → RuntimeError 透出。"""
        monkeypatch.setenv("YULEOSH_LLM_UNIFIED", "1")
        err_resp = LLMResponse(
            content="", model="m", provider="p",
            token_usage={}, error="provider 401",
        )

        with mock.patch.object(
            LLMClient, "call", new=mock.AsyncMock(return_value=err_resp)
        ), pytest.raises(RuntimeError, match="provider 401"):
            chat_completion("sys", "user", retries=1)

    def test_flag_off_uses_urllib(self, monkeypatch):
        """未设置 flag 时保留 urllib 实现，且不调 call_sync。"""
        monkeypatch.delenv("YULEOSH_LLM_UNIFIED", raising=False)
        monkeypatch.setenv("LLM_API_KEY", "sk-test")

        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "legacy!"}, "finish_reason": "stop"}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 3},
        }).encode()
        fake_ctx = mock.MagicMock()
        fake_ctx.__enter__.return_value = fake_resp
        fake_ctx.__exit__.return_value = False

        with mock.patch(
            "urllib.request.urlopen", return_value=fake_ctx
        ) as urlopen_m, mock.patch.object(
            LLMClient, "call_sync", return_value={}
        ) as fake_sync:
            result = chat_completion("sys", "user", retries=1)

        assert result["content"] == "legacy!"
        assert result["model"] == "deepseek-chat"
        urlopen_m.assert_called_once()
        fake_sync.assert_not_called()
