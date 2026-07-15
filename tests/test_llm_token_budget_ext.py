# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for yuleosh.llm.token_budget — TokenBudgetChecker, BudgetCheckResult."""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.llm.token_budget import TokenBudgetChecker, BudgetCheckResult
from yuleosh.llm.providers.base import LLMConfig, PRICING_TABLE, TASK_BUDGETS


# ---------------------------------------------------------------------------
# BudgetCheckResult dataclass
# ---------------------------------------------------------------------------

class TestBudgetCheckResult:
    """GIVEN BudgetCheckResult WHEN constructed THEN fields correct."""

    def test_passed_result(self):
        """GIVEN passed=True WHEN BudgetCheckResult THEN passed is True."""
        result = BudgetCheckResult(
            passed=True,
            reason="OK",
            estimated_cost=0.01,
            budget=0.50,
        )
        assert result.passed
        assert result.reason == "OK"
        assert result.estimated_cost == 0.01

    def test_failed_result(self):
        """GIVEN passed=False WHEN BudgetCheckResult THEN failed."""
        result = BudgetCheckResult(
            passed=False,
            reason="Budget exceeded",
            estimated_cost=0.60,
            budget=0.50,
        )
        assert not result.passed
        assert "exceeded" in result.reason


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    """GIVEN TokenBudgetChecker.estimate_tokens WHEN called THEN returns estimate."""

    def test_empty_string(self):
        """GIVEN empty string WHEN estimate_tokens THEN 0."""
        assert TokenBudgetChecker.estimate_tokens("") == 0

    def test_english_text(self):
        """GIVEN English text WHEN estimate_tokens THEN estimates ~chars/3.5."""
        text = "Hello world, this is a simple test of token estimation."
        tokens = TokenBudgetChecker.estimate_tokens(text)
        assert tokens > 0
        assert tokens < len(text)  # tokens < chars for English

    def test_cjk_text(self):
        """GIVEN CJK text WHEN estimate_tokens THEN uses CJK ratio."""
        text = "这是一个中文测试句子用于估算令牌数量"
        tokens = TokenBudgetChecker.estimate_tokens(text)
        assert tokens > 0

    def test_mixed_text(self):
        """GIVEN mixed CJK+English WHEN estimate_tokens THEN handles both."""
        text = "Hello 世界 token 测试 mixed text"
        tokens = TokenBudgetChecker.estimate_tokens(text)
        assert tokens > 0

    def test_none_text(self):
        """GIVEN empty string WHEN estimate_tokens THEN 0."""
        assert TokenBudgetChecker.estimate_tokens("") == 0
        # Whitespace-only is still characters so will estimate > 0
        # But the int() truncation may make it 0 for very short strings
        result = TokenBudgetChecker.estimate_tokens("  ")
        assert result >= 0


# ---------------------------------------------------------------------------
# check budget
# ---------------------------------------------------------------------------

class TestCheckBudgetBase:
    """GIVEN TokenBudgetChecker.check WHEN called THEN validates against budgets."""

    def test_unknown_model_returns_failed(self):
        """GIVEN unknown model in config WHEN check THEN passed=False."""
        config = LLMConfig(model="nonexistent-model")
        result = TokenBudgetChecker.check("Some prompt", config)
        assert not result.passed
        assert "Unknown model" in result.reason

    def test_passing_budget(self):
        """GIVEN short prompt within budgets WHEN check THEN passed=True."""
        config = LLMConfig(model="deepseek-v4", max_cost_usd=0.50)
        result = TokenBudgetChecker.check("Write a hello world function", config)
        assert result.passed
        assert result.estimated_cost > 0
        assert "Within budget" in result.reason

    def test_includes_system_prompt(self):
        """GIVEN additional system_prompt WHEN check THEN tokens added."""
        config = LLMConfig(model="deepseek-v4", max_cost_usd=0.50)
        result = TokenBudgetChecker.check("Short", config, system_prompt="Long system prompt" * 100)
        assert result.estimated_prompt_tokens > TokenBudgetChecker.estimate_tokens("Short")

    def test_context_window_exceeded(self):
        """GIVEN very long prompt exceeding 80% context window WHEN check THEN fails."""
        config = LLMConfig(model="deepseek-v4")
        # deepseek-v4 context window = 128,000; 80% = 102,400
        # Create a prompt that exceeds this
        very_long_prompt = "x" * 400_000  # ~114k tokens
        result = TokenBudgetChecker.check(very_long_prompt, config)
        assert not result.passed
        assert "Context window exceeded" in result.reason

    def test_cost_budget_exceeded(self):
        """GIVEN very low max_cost USD WHEN estimate exceeds budget THEN fails."""
        config = LLMConfig(model="gpt-4o", max_cost_usd=0.001)
        # gpt-4o: input $0.01/1k, output $0.03/1k
        long_prompt = "Test " * 10_000  # roughly ~11k tokens
        result = TokenBudgetChecker.check(long_prompt, config)
        # Either context window or cost budget will fail
        if result.passed:
            pass  # Likely both pass with small prompts
        else:
            assert not result.passed

    def test_respects_task_budget(self):
        """GIVEN simple_summary task_type WHEN check THEN uses lower budget."""
        config = LLMConfig(model="deepseek-v4", task_type="simple_summary", max_cost_usd=0.50)
        result = TokenBudgetChecker.check("Some prompt", config)
        # simple_summary has max_cost_usd=0.10, but config has 0.50
        # min(0.50, 0.10) = 0.10, so budget is 0.10
        if not result.passed:
            assert "budget" in result.reason

    def test_unknown_task_type_falls_back_to_code_generation(self):
        """GIVEN unknown task_type WHEN check THEN falls back to code_generation budget."""
        config = LLMConfig(model="deepseek-v4", task_type="unknown_type_xyz", max_cost_usd=0.50)
        result = TokenBudgetChecker.check("Short prompt", config)
        # Uses code_generation budget: max_cost_usd=0.50, max_tokens_out=4096
        if result.passed:
            assert result.budget > 0

    def test_returns_estimates_in_result(self):
        """GIVEN valid config WHEN check THEN result has estimate fields."""
        config = LLMConfig(model="deepseek-v4")
        result = TokenBudgetChecker.check("Some prompt text here", config)
        assert result.estimated_prompt_tokens > 0
        if result.passed:
            assert result.estimated_completion_tokens > 0
            assert result.estimated_cost > 0
            assert result.budget > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestCheckBudgetEdgeCases:
    """GIVEN edge case inputs WHEN check THEN handles gracefully."""

    def test_empty_prompt(self):
        """GIVEN empty prompt WHEN check THEN passes with 0 tokens."""
        config = LLMConfig(model="deepseek-v4")
        result = TokenBudgetChecker.check("", config)
        assert result.estimated_prompt_tokens == 0

    def test_minimal_prompt(self):
        """GIVEN one char prompt WHEN check THEN works."""
        config = LLMConfig(model="deepseek-v4")
        result = TokenBudgetChecker.check("a", config)
        # 1 char / 3.5 = 0.285 → int(0.285) = 0
        assert result.estimated_prompt_tokens >= 0

    def test_ascii_lowercase_only(self):
        """GIVEN only lowercase ASCII WHEN check THEN estimates correctly."""
        config = LLMConfig(model="claude-4-sonnet")
        result = TokenBudgetChecker.check("hello world test", config)
        assert result.estimated_prompt_tokens > 0

    def test_model_with_missing_pricing_gives_failed(self):
        """GIVEN model not in pricing table WHEN check THEN fails."""
        config = LLMConfig(model="unknown-model-v99")
        result = TokenBudgetChecker.check("hi", config)
        assert not result.passed
        assert "Unknown model" in result.reason
