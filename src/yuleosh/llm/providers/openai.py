#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/openai.py — OpenAI provider adapter (方案 A 真实实现).

OpenAI-compatible chat completions protocol::

    POST {base_url}/v1/chat/completions

Key lookup order: ``OPENAI_API_KEY`` > ``LLM_API_KEY``（与 deepseek 一致，
便于用自建 OpenAI 兼容端点如本机 Ollama 时填 ``LLM_API_KEY=任意非空串``）。
Base URL override: ``LLM_BASE_URL``（默认 https://api.openai.com）。

Model naming: OpenAI 兼容端点接受任意模型名作为请求体 ``model``（例如
Ollama 的 tag ``deepseek-r1:7b``），因此这里**直接使用** ``config.model``，
不做别名映射（与 deepseek provider 的 ``deepseek-v4 → deepseek-chat``
传输层别名不同——OpenAI 官方模型名本身即可直达）。

Pricing (docs/llm-strategy.md): input $0.010/1K, output $0.030/1K —
single source of truth is ``PRICING_TABLE["gpt-4o"]`` in base.py。
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

from yuleosh.llm.providers.base import (
    PRICING_TABLE,
    AbstractProvider,
    LLMConfig,
    LLMResponse,
)

log = logging.getLogger("llm.providers.openai")

DEFAULT_BASE_URL = "https://api.openai.com"
DEFAULT_API_MODEL = "gpt-4o"


class OpenAIProvider(AbstractProvider):
    """OpenAI provider — OpenAI-compatible chat completions.

    方案 A 真实可用实现：``YULEOSH_LLM_PROVIDER=openai`` 路由到此，也支持
    自建 OpenAI 兼容端点（如本机 Ollama）通过 ``LLM_BASE_URL`` 指向。

    无 key 不在构造时报错——key 在调用时按 env 读取
    （``OPENAI_API_KEY`` > ``LLM_API_KEY``）；缺 key 时 ``chat()`` 抛
    ``RuntimeError``（provider 名 + 缺失的 env，便于 fallback 记录）。
    """

    DEFAULT_BASE_URL = "https://api.openai.com"
    DEFAULT_API_MODEL = "gpt-4o"
    # 与 deepseek 一致支持 LLM_API_KEY：自建 OpenAI 兼容端点（如本机 Ollama）
    # 通常填 LLM_API_KEY=任意非空串。provider_fallback.PROVIDER_KEY_ENVS
    # 已同步包含 LLM_API_KEY，使 openai 路由在自建端点下可用。
    API_KEY_ENV = ("OPENAI_API_KEY", "LLM_API_KEY")

    # 方案 A 已落地真实实现：不再是预留骨架，fallback 不应跳过。
    is_skeleton: bool = False

    def __init__(self, base_url: str | None = None) -> None:
        # Optional explicit override; env LLM_BASE_URL is resolved per-call.
        self._base_url_override = base_url

    @property
    def provider_name(self) -> str:
        return "openai"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send an OpenAI-compatible chat completion request to the endpoint.

        Raises:
            RuntimeError: Missing API key, or the request failed after
                ``config.max_retries`` attempts. The message always names
                the provider (``openai``).
        """
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        if not api_key:
            raise RuntimeError(
                "OpenAI provider (openai): 缺少 API key，请配置环境变量 "
                "OPENAI_API_KEY 或 LLM_API_KEY"
            )

        # OpenAI 兼容端点直接用 config.model（Ollama tag 等任意模型名）。
        api_model = config.model or DEFAULT_API_MODEL
        base_url = self._resolve_base_url()
        url = f"{base_url}/v1/chat/completions"
        body: dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": False,
        }
        if config.seed is not None:
            body["seed"] = config.seed
        if config.frequency_penalty:
            body["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty:
            body["presence_penalty"] = config.presence_penalty
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        data = await asyncio.to_thread(
            self._post_json,
            url,
            headers,
            body,
            timeout_s=config.timeout_s,
            max_retries=config.max_retries,
        )

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI provider (openai): 响应缺少 choices: {data}")
        choice = choices[0]
        content = choice.get("message", {}).get("content")
        if content is None:
            content = (
                f"[LLM refused, finish_reason={choice.get('finish_reason', 'unknown')}]"
            )

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        token_usage = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": int(usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)),
        }

        return LLMResponse(
            content=content,
            model=data.get("model") or api_model,
            provider=self.provider_name,
            token_usage=token_usage,
            cost=self.estimate_cost(prompt_tokens, completion_tokens),
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD using PRICING_TABLE (single source of truth)."""
        pricing = PRICING_TABLE.get("gpt-4o", {})
        input_per_1k = pricing.get("input_per_1k", 0.0)
        output_per_1k = pricing.get("output_per_1k", 0.0)
        return (prompt_tokens / 1000.0) * input_per_1k + (
            completion_tokens / 1000.0
        ) * output_per_1k

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_base_url(self) -> str:
        return (
            self._base_url_override or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

    def _post_json(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        *,
        timeout_s: int,
        max_retries: int,
    ) -> dict[str, Any]:
        """POST JSON and return the parsed response, with retry + backoff.

        CQ-P1-02: a fresh ``urllib.request.Request`` is created for every
        attempt — a consumed Request object is never reused.
        """
        payload = json.dumps(body).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    raw = resp.read().decode("utf-8")
                return json.loads(raw)
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                json.JSONDecodeError,
                TimeoutError,
                OSError,
            ) as exc:
                last_error = exc
                log.warning(
                    "OpenAI provider (openai): attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    backoff = 1.0 * (2 ** (attempt - 1))
                    time.sleep(backoff)
        raise RuntimeError(
            f"OpenAI provider (openai): LLM 请求在 {max_retries} 次重试后失败: "
            f"{last_error}"
        ) from last_error
