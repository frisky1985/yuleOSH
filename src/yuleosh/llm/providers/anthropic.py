#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/anthropic.py — Claude (Anthropic) provider adapter.

⚠️ 预留骨架（方案 A）：仅保证配置可切换到 ``anthropic``，实际调用由用户
显式配置后使用。当前 ``chat()`` 抛 ``NotImplementedError``；后续轮次实现
Anthropic Messages API（``POST {base_url}/v1/messages``，非 OpenAI 兼容协议）。

环境变量: ``ANTHROPIC_API_KEY``。
"""

from __future__ import annotations

from yuleosh.llm.providers.base import (
    PRICING_TABLE,
    AbstractProvider,
    LLMConfig,
    LLMResponse,
)


class ClaudeProvider(AbstractProvider):
    """Anthropic Claude provider — 预留骨架（方案 A，配置可切换，调用未实现）。"""

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_MODEL = "claude-4-sonnet"
    API_KEY_ENV = "ANTHROPIC_API_KEY"

    # Provider-level fallback (provider_fallback.py) skips skeleton providers
    # WITHOUT calling chat() — calling would raise NotImplementedError.
    is_skeleton: bool = True

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """Not implemented — reservation skeleton for 方案 A.

        Raises:
            NotImplementedError: Always, until the Anthropic Messages API
                adapter lands in a later round.
        """
        raise NotImplementedError(
            "ClaudeProvider(anthropic) 为预留骨架：方案 A 仅保证配置可切换，"
            "实际调用由用户显式配置 ANTHROPIC_API_KEY 后使用"
            "（Anthropic Messages API 适配将在后续轮次实现）"
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD using PRICING_TABLE (offline, no API call)."""
        pricing = PRICING_TABLE.get("claude-4-sonnet", {})
        input_per_1k = pricing.get("input_per_1k", 0.0)
        output_per_1k = pricing.get("output_per_1k", 0.0)
        return (prompt_tokens / 1000.0) * input_per_1k + (
            completion_tokens / 1000.0
        ) * output_per_1k
