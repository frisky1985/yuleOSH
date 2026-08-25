#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/deepseek.py — DeepSeek provider adapter (方案 A 默认 provider).

OpenAI-compatible chat completions protocol::

    POST {base_url}/v1/chat/completions

Model naming: TASK_ROUTES / LLMConfig use the *logical* model name
``deepseek-v4``; the provider maps it to the DeepSeek API model name
``deepseek-chat`` at the transport layer (see MODEL_ALIASES).

API key lookup order: ``DEEPSEEK_API_KEY`` > ``LLM_API_KEY``.
Base URL override: ``LLM_BASE_URL`` (default https://api.deepseek.com).

Pricing (docs/llm-strategy.md): input $0.002/1K, output $0.008/1K —
single source of truth is ``PRICING_TABLE["deepseek-v4"]`` in base.py.
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

log = logging.getLogger("llm.providers.deepseek")

# Logical model name (TASK_ROUTES / LLMConfig) → DeepSeek API model name.
MODEL_ALIASES: dict[str, str] = {
    "deepseek-v4": "deepseek-chat",
}

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_API_MODEL = "deepseek-chat"


class DeepSeekProvider(AbstractProvider):
    """DeepSeek LLM provider — OpenAI-compatible chat completions.

    Fully usable in 方案 A: it is the default provider for ``deepseek``
    routing. No API key is required at construction time; keys are read
    from the environment at call time (``DEEPSEEK_API_KEY`` > ``LLM_API_KEY``).
    """

    def __init__(self, base_url: str | None = None) -> None:
        # Optional explicit override; env LLM_BASE_URL is resolved per-call.
        self._base_url_override = base_url

    @property
    def provider_name(self) -> str:
        return "deepseek"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send an OpenAI-compatible chat completion request to DeepSeek.

        Raises:
            RuntimeError: Missing API key, or the request failed after
                ``config.max_retries`` attempts. The message always names
                the provider (``deepseek``).
        """
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        if not api_key:
            raise RuntimeError(
                "DeepSeek provider (deepseek): 缺少 API key，请配置环境变量 "
                "DEEPSEEK_API_KEY 或 LLM_API_KEY"
            )

        api_model = MODEL_ALIASES.get(config.model, config.model) or DEFAULT_API_MODEL
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
            raise RuntimeError(f"DeepSeek provider (deepseek): 响应缺少 choices: {data}")
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
        pricing = PRICING_TABLE.get("deepseek-v4", {})
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
                    "DeepSeek provider (deepseek): attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    backoff = 1.0 * (2 ** (attempt - 1))
                    time.sleep(backoff)
        raise RuntimeError(
            f"DeepSeek provider (deepseek): LLM 请求在 {max_retries} 次重试后失败: "
            f"{last_error}"
        ) from last_error
