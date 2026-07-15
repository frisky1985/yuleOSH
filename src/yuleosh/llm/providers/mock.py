#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
llm/providers/mock.py — Mock provider for testing.

Returns deterministic responses based on prompt content, no API calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from yuleosh.llm.providers.base import (
    AbstractProvider,
    LLMConfig,
    LLMResponse,
    PRICING_TABLE,
)


class MockProvider(AbstractProvider):
    """Mock LLM provider — returns canned responses for testing.

    Matches prompt content to response stubs:
    - "error" → returns error response
    - otherwise → returns a placeholder response
    """

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        self._responses = responses or {}

    @property
    def provider_name(self) -> str:
        return "mock"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        prompt = messages[-1]["content"] if messages else ""
        user_prompt = messages[-1].get("content", "") if messages else ""

        # Check for error trigger
        if "error" in user_prompt.lower() and "no error" not in user_prompt.lower():
            return LLMResponse(
                content="",
                model=config.model,
                provider="mock",
                token_usage={"prompt": 0, "completion": 0, "total": 0},
                cost=0.0,
                error="Mock forced error",
            )

        # Look for registered responses
        for key, resp in self._responses.items():
            if key.lower() in user_prompt.lower():
                token_usage = {"prompt": len(user_prompt) // 3, "completion": len(resp) // 3, "total": 0}
                token_usage["total"] = token_usage["prompt"] + token_usage["completion"]
                return LLMResponse(
                    content=resp,
                    model=config.model,
                    provider="mock",
                    token_usage=token_usage,
                    cost=self.estimate_cost(token_usage["prompt"], token_usage["completion"]),
                )

        # Default response
        response_text = (
            f"Mock response for: {user_prompt[:80]}...\n"
            f"This is a deterministic mock. Config: model={config.model}, "
            f"temp={config.temperature}, rag={config.rag_enabled}"
        )
        token_usage = {"prompt": len(user_prompt) // 3, "completion": len(response_text) // 3, "total": 0}
        token_usage["total"] = token_usage["prompt"] + token_usage["completion"]

        return LLMResponse(
            content=response_text,
            model=config.model,
            provider="mock",
            token_usage=token_usage,
            cost=self.estimate_cost(token_usage["prompt"], token_usage["completion"]),
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Mock cost: always $0.001."""
        return 0.001
