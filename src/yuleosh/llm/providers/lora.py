#!/usr/bin/env python3
# Copyright (c) 2025 frisky1685
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/lora.py — LoRA 微调模型 provider（P2.1）。

支持本地部署的 LoRA 微调模型，通过 Ollama 或 vLLM 提供服务。

设计要点：
- LoRA 模型定义在 model_registry.yaml（is_lora=true）
- 支持两种后端：ollama（默认）和 vllm
- 自动探测可用模型，降级到基础模型
- 零费用（本地部署）
- 与 OllamaProvider 共享部分逻辑（本地零费用 + 可达性探测）

使用场景：
- 项目特定代码风格微调（如 AUTOSAR 命名规范）
- 领域知识增强（如 MISRA 规则、ASPICE 流程）
- 降低幻觉（项目代码库锚定）

依赖：
- Ollama: 需要本地运行 ollama serve，且已 pull LoRA 模型
- vLLM: 需要部署 vLLM 服务并加载 LoRA adapter

配置示例（model_registry.yaml）：
  models:
    autosar-coder-lora:
      provider: lora
      context_window: 32768
      risk_level: L3
      capabilities: [code_generation, autosar_compliance]
      pricing:
        input_per_1k: 0.0
        output_per_1k: 0.0
      is_local: true
      is_lora: true
      lora_base_model: qwen2.5-coder:14b
"""

from __future__ import annotations

import logging
import os
from typing import Any

from yuleosh.llm.providers.base import AbstractProvider, LLMConfig, LLMResponse
from yuleosh.llm.providers.ollama import OllamaProvider

log = logging.getLogger("llm.providers.lora")

# LoRA 后端类型
LORA_BACKEND_OLLAMA = "ollama"
LORA_BACKEND_VLLM = "vllm"

# 默认后端（可通过环境变量覆盖）
DEFAULT_LORA_BACKEND = os.environ.get("LORA_BACKEND", LORA_BACKEND_OLLAMA)

# vLLM 默认端点
DEFAULT_VLLM_HOST = os.environ.get("VLLM_HOST", "http://127.0.0.1:8000").rstrip("/")


class LoraProvider(AbstractProvider):
    """LoRA 微调模型 provider — 本地部署，零费用。"""

    def __init__(
        self,
        backend: str | None = None,
        ollama_host: str | None = None,
        vllm_host: str | None = None,
    ) -> None:
        self._backend = backend or DEFAULT_LORA_BACKEND
        self._ollama_provider = OllamaProvider(base_url=ollama_host)
        self._vllm_host = (vllm_host or DEFAULT_VLLM_HOST).rstrip("/")

    @property
    def provider_name(self) -> str:
        return "lora"

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """LoRA provider 可用当且仅当后端服务可达。"""
        if self._backend == LORA_BACKEND_OLLAMA:
            return self._ollama_provider.is_available()
        elif self._backend == LORA_BACKEND_VLLM:
            return self._vllm_available()
        return False

    def _vllm_available(self) -> bool:
        """vLLM 服务可达性检查。"""
        try:
            import urllib.request
            url = f"{self._vllm_host}/v1/models"
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status == 200
        except Exception as e:  # noqa: BLE001
            log.debug("LoraProvider._vllm_available: vLLM 不可达: %s", e)
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """发送聊天请求到 LoRA 模型。"""
        if self._backend == LORA_BACKEND_OLLAMA:
            return await self._chat_ollama(messages, config)
        elif self._backend == LORA_BACKEND_VLLM:
            return await self._chat_vllm(messages, config)
        else:
            raise ValueError(f"Unknown LoRA backend: {self._backend}")

    async def _chat_ollama(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """通过 Ollama 后端调用 LoRA 模型。"""
        # Ollama 原生支持 LoRA，直接透传 model 名
        return await self._ollama_provider.chat(messages, config)

    async def _chat_vllm(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """通过 vLLM 后端调用 LoRA 模型。"""
        import time
        import urllib.request

        url = f"{self._vllm_host}/v1/chat/completions"
        body = {
            "model": config.model,  # vLLM 需要指定 LoRA adapter 名
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": False,
        }

        # 透传 LoRA 特有参数（vLLM 支持）
        if config.seed is not None:
            body["seed"] = config.seed
        if config.frequency_penalty != 0.0:
            body["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty != 0.0:
            body["presence_penalty"] = config.presence_penalty

        data = _json_dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        t0 = time.monotonic()
        try:
            # 2026-11-02: urlopen 是同步阻塞调用 (timeout 默认 1800s) —
            # async 方法内直连会卡死事件循环, 与 OllamaProvider 一致改用
            # asyncio.to_thread。
            import asyncio

            def _post() -> bytes:
                with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:
                    return resp.read()

            raw = await asyncio.to_thread(_post)
            result = _json_loads(raw.decode("utf-8"))
        except Exception as e:
            # 2026-11-02: 传输失败改抛异常 — 返回带 error 的 LLMResponse
            # 不会被 call_with_fallback 降级 (只对抛出的异常降级),
            # 与 DeepSeek/Ollama provider 的失败语义保持一致。
            raise RuntimeError(f"vLLM request failed: {e}") from e

        duration = time.monotonic() - t0
        choices = result.get("choices") or [{}]
        choice = choices[0]
        content = choice.get("message", {}).get("content", "")
        usage = result.get("usage", {})

        return LLMResponse(
            content=content,
            model=config.model,
            provider=self.provider_name,
            token_usage={
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            },
            cost=0.0,  # 本地零费用
            duration_s=duration,
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """LoRA 本地部署零费用。"""
        return 0.0

    # ------------------------------------------------------------------
    # LoRA-specific methods
    # ------------------------------------------------------------------
    def list_lora_models(self) -> list[str]:
        """列出可用的 LoRA 模型。"""
        if self._backend == LORA_BACKEND_OLLAMA:
            return self._list_ollama_lora_models()
        elif self._backend == LORA_BACKEND_VLLM:
            return self._list_vllm_lora_models()
        return []

    def _list_ollama_lora_models(self) -> list[str]:
        """从 Ollama 获取 LoRA 模型列表。"""
        try:
            models = self._ollama_provider._list_models()
            # Ollama 的 LoRA 模型通常带有 -lora 或 -adapter 后缀
            return [m for m in models if "lora" in m.lower() or "adapter" in m.lower()]
        except Exception as e:
            log.warning("Failed to list Ollama LoRA models: %s", e)
            return []

    def _list_vllm_lora_models(self) -> list[str]:
        """从 vLLM 获取 LoRA 模型列表。"""
        try:
            import urllib.request
            url = f"{self._vllm_host}/v1/models"
            with urllib.request.urlopen(url, timeout=5) as resp:
                result = _json_loads(resp.read().decode("utf-8"))
                models = [m["id"] for m in result.get("data", [])]
                # vLLM 的 LoRA 模型通过 --enable-lora 加载，名称自定义
                return models
        except Exception as e:
            log.warning("Failed to list vLLM LoRA models: %s", e)
            return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _json_dumps(obj: Any) -> str:
    """JSON 序列化（避免循环导入）。"""
    import json
    return json.dumps(obj)


def _json_loads(s: str) -> Any:
    """JSON 反序列化（避免循环导入）。"""
    import json
    return json.loads(s)
