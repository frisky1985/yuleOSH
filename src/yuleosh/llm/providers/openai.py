#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/openai.py — OpenAI provider adapter.

⚠️ 预留骨架（方案 A）：仅保证配置可切换到 ``openai``，实际调用由用户显式
配置后使用。当前 ``chat()`` 抛 ``NotImplementedError``；后续轮次实现
OpenAI Chat Completions API（``POST {base_url}/v1/chat/completions``）。

环境变量: ``OPENAI_API_KEY``。
"""

from __future__ import annotations

from yuleosh.llm.providers.base import (
    PRICING_TABLE,
    AbstractProvider,
    LLMConfig,
    LLMResponse,
)


class OpenAIProvider(AbstractProvider):
    """OpenAI provider — 预留骨架（方案 A，配置可切换，调用未实现）。"""

    DEFAULT_BASE_URL = "https://api.openai.com"
    DEFAULT_MODEL = "gpt-4o"
    API_KEY_ENV = "OPENAI_API_KEY"

    # Provider-level fallback (provider_fallback.py) skips skeleton providers
    # WITHOUT calling chat() — calling would raise NotImplementedError.
    is_skeleton: bool = True

    @property
    def provider_name(self) -> str:
        return "openai"

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """Not implemented — reservation skeleton for 方案 A.

        Raises:
            NotImplementedError: Always, until the OpenAI Chat Completions
                adapter lands in a later round.
        """
        raise NotImplementedError(
            "OpenAIProvider(openai) 为预留骨架：方案 A 仅保证配置可切换，"
            "实际调用由用户显式配置 OPENAI_API_KEY 后使用"
            "（OpenAI Chat Completions API 适配将在后续轮次实现）"
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD using PRICING_TABLE (offline, no API call)."""
        pricing = PRICING_TABLE.get("gpt-4o", {})
        input_per_1k = pricing.get("input_per_1k", 0.0)
        output_per_1k = pricing.get("output_per_1k", 0.0)
        return (prompt_tokens / 1000.0) * input_per_1k + (
            completion_tokens / 1000.0
        ) * output_per_1k
