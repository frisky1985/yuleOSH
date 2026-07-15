#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
llm/token_budget.py — Pre-call token budget checker.

Estimates prompt token count, checks context window limits and cost
budget before the actual LLM API call is made.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from yuleosh.llm.providers.base import LLMConfig, PRICING_TABLE, TASK_BUDGETS

log = logging.getLogger("llm.token_budget")


@dataclass
class BudgetCheckResult:
    """Result of a pre-call budget check."""

    passed: bool
    reason: str
    estimated_cost: float = 0.0
    budget: float = 0.0
    estimated_prompt_tokens: int = 0
    estimated_completion_tokens: int = 0


class TokenBudgetChecker:
    """Estimate token consumption and cost before making an LLM call."""

    # Rough token estimation: English text ~3.5 chars/token, CJK ~1.5 chars/token
    CHARS_PER_TOKEN_EN = 3.5
    CHARS_PER_TOKEN_CJK = 1.5

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Rough token count estimation.

        This is a fast heuristic — not a tokenizer.  For exact counts,
        use the model's tokenizer at call time.
        """
        if not text:
            return 0
        # Simple length-based estimate (conservative)
        cjk_count = sum(1 for c in text if ord(c) > 0x4E00)
        en_chars = len(text) - cjk_count
        return int(
            en_chars / cls.CHARS_PER_TOKEN_EN
            + cjk_count / cls.CHARS_PER_TOKEN_CJK
        )

    @classmethod
    def check(
        cls,
        prompt: str,
        config: LLMConfig,
        system_prompt: Optional[str] = None,
    ) -> BudgetCheckResult:
        """Pre-check token usage against model and task budgets.

        Args:
            prompt: The user/assistant prompt text.
            config: LLM configuration for this call.
            system_prompt: Optional system prompt text.

        Returns:
            BudgetCheckResult — ``passed`` is True only when within budget.
        """
        # Estimate tokens
        prompt_tokens = cls.estimate_tokens(prompt)
        if system_prompt:
            prompt_tokens += cls.estimate_tokens(system_prompt)

        # Look up pricing for the requested model
        pricing = PRICING_TABLE.get(config.model)
        if pricing is None:
            return BudgetCheckResult(
                passed=False,
                reason=f"Unknown model '{config.model}' — no pricing data",
                estimated_prompt_tokens=prompt_tokens,
            )

        # Check context window (80% threshold for safety)
        max_context = pricing.get("context_window", 128_000)
        if prompt_tokens > max_context * 0.8:
            return BudgetCheckResult(
                passed=False,
                reason=(
                    f"Context window exceeded: ~{prompt_tokens} tokens > "
                    f"{int(max_context * 0.8)} (80% of {max_context})"
                ),
                estimated_cost=0.0,
                budget=config.max_cost_usd,
                estimated_prompt_tokens=prompt_tokens,
            )

        # Look up task budget
        task_type = config.task_type or "code_generation"
        task_budget = TASK_BUDGETS.get(task_type, TASK_BUDGETS["code_generation"])
        max_out_tokens = min(config.max_tokens, int(task_budget["max_tokens_out"]))
        max_cost = min(config.max_cost_usd, task_budget["max_cost_usd"])

        # Estimate completion tokens (conservative: use max allowed)
        completion_tokens = min(max_out_tokens, 1024)

        # Estimate cost
        input_cost = (prompt_tokens / 1000) * pricing["input_per_1k"]
        output_cost = (completion_tokens / 1000) * pricing["output_per_1k"]
        total_cost = input_cost + output_cost

        if total_cost > max_cost:
            return BudgetCheckResult(
                passed=False,
                reason=(
                    f"Cost budget exceeded: ~${total_cost:.4f} estimated > "
                    f"${max_cost:.2f} budget ({task_type})"
                ),
                estimated_cost=total_cost,
                budget=max_cost,
                estimated_prompt_tokens=prompt_tokens,
                estimated_completion_tokens=completion_tokens,
            )

        return BudgetCheckResult(
            passed=True,
            reason=(
                f"Within budget: ~${total_cost:.4f} estimated "
                f"(budget ${max_cost:.2f})"
            ),
            estimated_cost=total_cost,
            budget=max_cost,
            estimated_prompt_tokens=prompt_tokens,
            estimated_completion_tokens=completion_tokens,
        )
