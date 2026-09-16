#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/ollama.py — Local Ollama provider (零费用 fallback).

当外部 LLM provider（DeepSeek / OpenAI / Anthropic）因余额/鉴权/网络不可用
而无法服务时，自动降级到本机 Ollama 上运行的模型（默认 http://127.0.0.1:11434）。

设计要点：
- 自动探测 Ollama 可达性与可用模型：优先 qwen2.5-coder 系列（14b/7b，代码
  审查/生成质量最好），其次任何已安装的 coder/通用模型（如 qwen:latest），
  保证「外部挂 → 本地」平滑切换，无需手动改任何配置。
- 通过 Ollama 原生 ``/api/chat`` 调用（无需 API key）；通过 ``options`` 透传
  temperature / num_ctx / num_predict，避免把 ollama 专有参数发给云端。
- estimate_cost 恒为 0（本地零费用），预算检查（token_budget）对本地模型
  不会因无定价而误降级。
- 同时提供异步 ``chat``（供 provider_fallback 链 / LLMClient 统一入口使用）
  与同步 ``chat_sync``（供遗留同步 chat_completion 默认路径直接调用）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from yuleosh.llm.providers.base import AbstractProvider, LLMConfig, LLMResponse

log = logging.getLogger("llm.providers.ollama")

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# 模型选择偏好：优先 coder 模型（代码审查/生成质量最好），其次通用模型。
# 任一前缀匹配即选中（如 "qwen2.5-coder" 命中 "qwen2.5-coder:14b"）。
_MODEL_PREFERENCE: tuple[str, ...] = (
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder",
    "qwen3-coder",
    "codellama",
    "deepseek-coder",
    "qwen:latest",
    "qwen2.5",
)


class OllamaProvider(AbstractProvider):
    """Local Ollama LLM provider — zero-cost fallback for unavailable cloud LLMs."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or DEFAULT_OLLAMA_HOST).rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        """Ollama 可达且至少有一个模型即视为可用。"""
        try:
            return bool(self._list_models())
        except Exception as e:  # noqa: BLE001 — 不可达即不可用
            log.debug("OllamaProvider.is_available: Ollama 不可达: %s", e)
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """异步 chat（供 provider_fallback 链 / LLMClient 统一入口使用）。"""
        model = self._resolve_model(config.model)
        url = f"{self._base_url}/api/chat"
        options: dict[str, Any] = {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
        }
        if config.context_window and config.context_window > 0:
            options["num_ctx"] = config.context_window
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        data = await asyncio.to_thread(
            self._post_json, url, body, config.timeout_s, config.max_retries
        )
        return self._to_response(data, model)

    def chat_sync(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> dict:
        """同步 chat（供遗留 chat_completion 默认路径直接调用，返回 legacy dict）。"""
        model = self._resolve_model(config.model)
        url = f"{self._base_url}/api/chat"
        options: dict[str, Any] = {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
        }
        if config.context_window and config.context_window > 0:
            options["num_ctx"] = config.context_window
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        data = self._post_json(url, body, config.timeout_s, config.max_retries)
        resp = self._to_response(data, model)
        return {
            "content": resp.content,
            "model": resp.model,
            "usage": {
                "prompt_tokens": resp.token_usage.get("prompt", 0),
                "completion_tokens": resp.token_usage.get("completion", 0),
                "total_tokens": resp.token_usage.get("total", 0),
            },
        }

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """本地模型零费用。"""
        return 0.0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _to_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        content = (data.get("message") or {}).get("content")
        if content is None:
            content = f"[LLM refused, done_reason={data.get('done_reason', 'unknown')}]"
        # Ollama 原生响应携带 prompt_eval_count / eval_count（亦兼容 usage 字段）
        usage = data.get("usage") or {}
        prompt_tokens = int(
            usage.get("prompt_tokens", data.get("prompt_eval_count", 0) or 0) or 0
        )
        completion_tokens = int(
            usage.get("completion_tokens", data.get("eval_count", 0) or 0) or 0
        )
        total = int(usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens))
        return LLMResponse(
            content=content,
            model=model,
            provider=self.provider_name,
            token_usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total,
            },
            cost=0.0,
        )

    def _list_models(self) -> list[str]:
        req = urllib.request.Request(f"{self._base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]

    def _resolve_model(self, configured: str) -> str:
        """解析实际使用的本地模型。

        1) 配置模型本身是已安装的本地模型 → 直接用；
        2) 按偏好顺序挑第一个已安装的（前缀匹配）；
        3) 兜底用第一个可用模型。
        """
        models = self._list_models()
        if not models:
            raise RuntimeError(
                f"Ollama provider (ollama): 本地 Ollama 在 {self._base_url} 无可用模型，"
                "请先 `ollama pull <model>`（如 qwen2.5-coder:14b）"
            )
        if configured and configured in models:
            return configured
        for pref in _MODEL_PREFERENCE:
            for m in models:
                if m == pref or m.startswith(pref + ":") or m.startswith(pref):
                    return m
        return models[0]

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        timeout_s: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """POST JSON 并返回解析结果，带重试 + 退避（与 DeepSeekProvider 同语义）。"""
        payload = json.dumps(body).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                json.JSONDecodeError,
                TimeoutError,
                OSError,
            ) as exc:
                last_error = exc
                log.warning(
                    "Ollama provider (ollama): attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    time.sleep(1.0 * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"Ollama provider (ollama): LLM 请求在 {max_retries} 次重试后失败: "
            f"{last_error}"
        ) from last_error
