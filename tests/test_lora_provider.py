#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
test_lora_provider.py — LoRA provider 测试（P2.1）。

覆盖:
- T1: Provider 初始化（backend 选择）
- T2: 可用性检查（Ollama / vLLM）
- T3: 聊天请求（Ollama 后端）
- T4: 聊天请求（vLLM 后端）
- T5: 费用估算（零费用）
- T6: LoRA 模型列表
- T7: 优雅降级（后端不可用）
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.llm.providers.base import LLMConfig, LLMResponse
from yuleosh.llm.providers.lora import (
    DEFAULT_LORA_BACKEND,
    LORA_BACKEND_OLLAMA,
    LORA_BACKEND_VLLM,
    LoraProvider,
)


@pytest.fixture
def lora_config():
    """标准 LoRA 测试配置。"""
    return LLMConfig(
        model="test-lora-model",
        provider="lora",
        max_tokens=1024,
        temperature=0.3,
        top_p=0.95,
        timeout_s=30,
    )


class TestLoraProviderInit:
    """T1: Provider 初始化。"""

    def test_default_backend(self):
        """GIVEN 无参数 WHEN 初始化 THEN 使用默认后端。"""
        provider = LoraProvider()
        assert provider._backend == DEFAULT_LORA_BACKEND

    def test_explicit_ollama_backend(self):
        """GIVEN backend=ollama WHEN 初始化 THEN 使用 Ollama。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        assert provider._backend == LORA_BACKEND_OLLAMA

    def test_explicit_vllm_backend(self):
        """GIVEN backend=vllm WHEN 初始化 THEN 使用 vLLM。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        assert provider._backend == LORA_BACKEND_VLLM

    def test_custom_hosts(self):
        """GIVEN 自定义 host WHEN 初始化 THEN 使用自定义值。"""
        provider = LoraProvider(
            backend=LORA_BACKEND_VLLM,
            vllm_host="http://custom:9000",
        )
        assert provider._vllm_host == "http://custom:9000"

    def test_provider_name(self):
        """GIVEN LoraProvider WHEN provider_name THEN 返回 'lora'。"""
        provider = LoraProvider()
        assert provider.provider_name == "lora"


class TestLoraProviderAvailability:
    """T2: 可用性检查。"""

    def test_ollama_available_when_reachable(self):
        """GIVEN Ollama 可达 WHEN is_available THEN True。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        with patch.object(
            provider._ollama_provider, "is_available", return_value=True
        ):
            assert provider.is_available() is True

    def test_ollama_unavailable_when_unreachable(self):
        """GIVEN Ollama 不可达 WHEN is_available THEN False。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        with patch.object(
            provider._ollama_provider, "is_available", return_value=False
        ):
            assert provider.is_available() is False

    def test_vllm_available_when_reachable(self):
        """GIVEN vLLM 可达 WHEN is_available THEN True。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        with patch.object(provider, "_vllm_available", return_value=True):
            assert provider.is_available() is True

    def test_vllm_unavailable_when_unreachable(self):
        """GIVEN vLLM 不可达 WHEN is_available THEN False。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        with patch.object(provider, "_vllm_available", return_value=False):
            assert provider.is_available() is False


class TestLoraProviderChat:
    """T3/T4: 聊天请求。"""

    @pytest.mark.asyncio
    async def test_chat_ollama_backend(self, lora_config):
        """GIVEN Ollama 后端 WHEN chat THEN 调用 Ollama provider。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        expected_response = LLMResponse(
            content="test response",
            model=lora_config.model,
            provider="lora",
            token_usage={"prompt": 10, "completion": 20, "total": 30},
            cost=0.0,
            duration_s=1.0,
        )
        with patch.object(
            provider._ollama_provider, "chat", return_value=expected_response
        ) as mock_chat:
            messages = [{"role": "user", "content": "test"}]
            response = await provider.chat(messages, lora_config)
            mock_chat.assert_called_once_with(messages, lora_config)
            assert response.content == "test response"
            assert response.cost == 0.0

    @pytest.mark.asyncio
    async def test_chat_vllm_backend(self, lora_config):
        """GIVEN vLLM 后端 WHEN chat THEN 发送 HTTP 请求。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        mock_response_data = {
            "choices": [{"message": {"content": "vllm response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"choices": [{"message": {"content": "vllm response"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=None)
            mock_urlopen.return_value = mock_resp

            messages = [{"role": "user", "content": "test"}]
            response = await provider.chat(messages, lora_config)
            assert response.content == "vllm response"
            assert response.provider == "lora"
            assert response.cost == 0.0

    @pytest.mark.asyncio
    async def test_chat_vllm_with_seed(self, lora_config):
        """GIVEN config.seed WHEN chat vLLM THEN 透传 seed 参数。"""
        lora_config.seed = 42
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"choices": [{"message": {"content": ""}}], "usage": {}}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=None)
            mock_urlopen.return_value = mock_resp

            await provider.chat([{"role": "user", "content": "test"}], lora_config)
            # 验证请求体包含 seed
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            body = request.data.decode("utf-8")
            assert '"seed": 42' in body

    @pytest.mark.asyncio
    async def test_chat_unknown_backend(self, lora_config):
        """GIVEN 未知后端 WHEN chat THEN 抛出 ValueError。"""
        provider = LoraProvider(backend="unknown")
        with pytest.raises(ValueError, match="Unknown LoRA backend"):
            await provider.chat([{"role": "user", "content": "test"}], lora_config)


class TestLoraProviderCost:
    """T5: 费用估算。"""

    def test_estimate_cost_zero(self):
        """GIVEN LoRA provider WHEN estimate_cost THEN 返回 0。"""
        provider = LoraProvider()
        assert provider.estimate_cost(1000, 500) == 0.0
        assert provider.estimate_cost(10000, 5000) == 0.0


class TestLoraProviderModelList:
    """T6: LoRA 模型列表。"""

    def test_list_lora_models_ollama(self):
        """GIVEN Ollama 后端 WHEN list_lora_models THEN 返回 LoRA 模型列表。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        mock_models = ["qwen2.5-coder:14b", "test-lora-model", "another-lora-adapter"]
        with patch.object(
            provider._ollama_provider, "_list_models", return_value=mock_models
        ):
            lora_models = provider.list_lora_models()
            # 应该过滤出包含 lora 或 adapter 的模型
            assert "test-lora-model" in lora_models
            assert "another-lora-adapter" in lora_models

    def test_list_lora_models_vllm(self):
        """GIVEN vLLM 后端 WHEN list_lora_models THEN 返回模型列表。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        mock_response = b'{"data": [{"id": "model1"}, {"id": "lora-model2"}]}'
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_response
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=None)
            mock_urlopen.return_value = mock_resp

            lora_models = provider.list_lora_models()
            assert "model1" in lora_models
            assert "lora-model2" in lora_models

    def test_list_lora_models_error_handling(self):
        """GIVEN 后端异常 WHEN list_lora_models THEN 返回空列表。"""
        provider = LoraProvider(backend=LORA_BACKEND_OLLAMA)
        with patch.object(
            provider._ollama_provider, "_list_models", side_effect=Exception("error")
        ):
            lora_models = provider.list_lora_models()
            assert lora_models == []


class TestLoraProviderDegradation:
    """T7: 优雅降级。"""

    @pytest.mark.asyncio
    async def test_chat_vllm_unreachable(self, lora_config):
        """GIVEN vLLM 不可达 WHEN chat THEN 返回错误响应。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            messages = [{"role": "user", "content": "test"}]
            response = await provider.chat(messages, lora_config)
            assert response.error is not None
            assert "Connection refused" in response.error
            assert response.content == ""
            assert response.cost == 0.0

    def test_list_models_vllm_unreachable(self):
        """GIVEN vLLM 不可达 WHEN list_lora_models THEN 返回空列表。"""
        provider = LoraProvider(backend=LORA_BACKEND_VLLM)
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            lora_models = provider.list_lora_models()
            assert lora_models == []
