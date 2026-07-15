# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for yuleosh.llm.providers — base dataclasses, pricing table, MockProvider."""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.llm.providers.base import (
    LLMConfig,
    LLMResponse,
    AbstractProvider,
    PRICING_TABLE,
    TASK_BUDGETS,
)
from yuleosh.llm.providers.mock import MockProvider


# ---------------------------------------------------------------------------
# LLMConfig dataclass
# ---------------------------------------------------------------------------

class TestLLMConfig:
    """GIVEN LLMConfig WHEN constructed THEN fields use defaults."""

    def test_default_config(self):
        """GIVEN no args WHEN LLMConfig THEN defaults set."""
        cfg = LLMConfig()
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.3
        assert cfg.top_p == 0.95
        assert cfg.timeout_s == 60
        assert cfg.max_retries == 3
        assert cfg.rag_enabled is True
        assert cfg.rag_sources == ["misra", "best_practices"]
        assert cfg.max_cost_usd == 0.50
        assert cfg.task_type is None
        assert cfg.task_id is None
        assert cfg.user_id is None

    def test_custom_config(self):
        """GIVEN custom args WHEN LLMConfig THEN overrides defaults."""
        cfg = LLMConfig(
            model="gpt-4o",
            provider="openai",
            max_tokens=8192,
            temperature=0.7,
            max_cost_usd=0.10,
            task_type="review",
        )
        assert cfg.model == "gpt-4o"
        assert cfg.max_tokens == 8192
        assert cfg.temperature == 0.7
        assert cfg.max_cost_usd == 0.10
        assert cfg.task_type == "review"

    def test_rag_sources_default_copy(self):
        """GIVEN two configs WHEN created THEN each has own rag_sources list."""
        cfg1 = LLMConfig()
        cfg2 = LLMConfig()
        # They should be independent lists
        cfg1.rag_sources.append("extra")
        assert len(cfg1.rag_sources) == 3
        assert len(cfg2.rag_sources) == 2


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------

class TestLLMResponse:
    """GIVEN LLMResponse WHEN constructed THEN fields match."""

    def test_minimal(self):
        """GIVEN required fields WHEN LLMResponse THEN created."""
        resp = LLMResponse(
            content="Hello",
            model="deepseek-v4",
            provider="deepseek",
            token_usage={"prompt": 10, "completion": 5, "total": 15},
        )
        assert resp.content == "Hello"
        assert resp.model == "deepseek-v4"
        assert resp.token_usage["total"] == 15
        assert resp.cost == 0.0
        assert resp.error is None

    def test_with_error(self):
        """GIVEN error field WHEN LLMResponse THEN error set."""
        resp = LLMResponse(
            content="",
            model="m", provider="mock",
            token_usage={"prompt": 0, "completion": 0, "total": 0},
            error="API timeout",
        )
        assert resp.error == "API timeout"
        assert resp.content == ""


# ---------------------------------------------------------------------------
# PRICING_TABLE and TASK_BUDGETS
# ---------------------------------------------------------------------------

class TestPricingTable:
    """GIVEN PRICING_TABLE WHEN inspected THEN has expected models."""

    def test_has_known_models(self):
        """GIVEN PRICING_TABLE WHEN accessed THEN contains expected models."""
        assert "deepseek-v4" in PRICING_TABLE
        assert "gpt-4o" in PRICING_TABLE
        assert "claude-4-sonnet" in PRICING_TABLE
        assert "claude-4-haiku" in PRICING_TABLE

    def test_deepseek_pricing(self):
        """GIVEN deepseek-v4 entry WHEN accessed THEN pricing correct."""
        pricing = PRICING_TABLE["deepseek-v4"]
        assert pricing["input_per_1k"] == 0.002
        assert pricing["output_per_1k"] == 0.008
        assert pricing["context_window"] == 128_000

    def test_gpt4o_pricing(self):
        """GIVEN gpt-4o entry WHEN accessed THEN pricing correct."""
        pricing = PRICING_TABLE["gpt-4o"]
        assert pricing["input_per_1k"] == 0.010
        assert pricing["output_per_1k"] == 0.030
        assert pricing["context_window"] == 128_000


class TestTaskBudgets:
    """GIVEN TASK_BUDGETS WHEN inspected THEN has expected task types."""

    def test_has_known_tasks(self):
        """GIVEN TASK_BUDGETS WHEN accessed THEN contains expected tasks."""
        assert "code_generation" in TASK_BUDGETS
        assert "simple_summary" in TASK_BUDGETS

    def test_code_generation_budget(self):
        """GIVEN code_generation WHEN accessed THEN max_cost_usd=0.50."""
        budget = TASK_BUDGETS["code_generation"]
        assert budget["max_cost_usd"] == 0.50
        assert budget["max_tokens_out"] == 4096


# ---------------------------------------------------------------------------
# AbstractProvider ABC
# ---------------------------------------------------------------------------

class TestAbstractProvider:
    """GIVEN AbstractProvider WHEN subclassed THEN contracts enforced."""

    def test_cannot_instantiate(self):
        """GIVEN AbstractProvider WHEN instantiated THEN TypeError."""
        with pytest.raises(TypeError):
            AbstractProvider()  # Can't instantiate ABC

    def test_subclass_must_implement_abstract_methods(self):
        """GIVEN partial subclass WHEN instantiated THEN TypeError."""
        with pytest.raises(TypeError):
            class PartialProvider(AbstractProvider):
                pass
            PartialProvider()


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

class TestMockProviderBasics:
    """GIVEN MockProvider WHEN created THEN returns canned responses."""

    @pytest.mark.asyncio
    async def test_default_response(self):
        """GIVEN no registered responses WHEN chat THEN returns default mock response."""
        provider = MockProvider()
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "Hello, how are you?"}],
            config=config,
        )
        assert resp.content != ""
        assert "deepseek-v4" in resp.content or "deepseek" in resp.content
        assert resp.provider == "mock"
        assert resp.error is None

    @pytest.mark.asyncio
    async def test_registered_response(self):
        """GIVEN registered responses WHEN chat matches key THEN returns response."""
        provider = MockProvider(responses={"hello": "Hi there! I'm a mock."})
        config = LLMConfig(model="gpt-4o")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "Say hello world"}],
            config=config,
        )
        assert "Hi there" in resp.content
        assert resp.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_forced_error(self):
        """GIVEN prompt with 'error' WHEN chat THEN returns error response."""
        provider = MockProvider()
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "trigger error"}],
            config=config,
        )
        assert resp.error == "Mock forced error"

    @pytest.mark.asyncio
    async def test_no_error_when_no_error_in_prompt(self):
        """GIVEN prompt with 'no error' WHEN chat THEN no forced error."""
        provider = MockProvider()
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "There is no error here"}],
            config=config,
        )
        assert resp.error is None

    @pytest.mark.asyncio
    async def test_empty_messages_list(self):
        """GIVEN empty messages WHEN chat THEN handles gracefully."""
        provider = MockProvider()
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(messages=[], config=config)
        assert resp.content != ""

    def test_provider_name(self):
        """GIVEN MockProvider WHEN provider_name accessed THEN 'mock'."""
        provider = MockProvider()
        assert provider.provider_name == "mock"

    def test_estimate_cost_constant(self):
        """GIVEN MockProvider WHEN estimate_cost THEN always 0.001."""
        provider = MockProvider()
        cost = provider.estimate_cost(100, 50)
        assert cost == 0.001


# ---------------------------------------------------------------------------
# MockProvider chat with registered multi-key match
# ---------------------------------------------------------------------------

class TestMockProviderMultiKey:
    """GIVEN MockProvider with multiple registered responses WHEN chat THEN correct match."""

    @pytest.mark.asyncio
    async def test_first_key_match(self):
        """GIVEN multiple keys WHEN chat THEN matches first key."""
        provider = MockProvider(responses={
            "hello": "Hi!",
            "world": "Earth!",
        })
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "hello world test"}],
            config=config,
        )
        assert resp.content == "Hi!"  # 'hello' matches first

    @pytest.mark.asyncio
    async def test_token_usage_estimate(self):
        """GIVEN chat with registered response WHEN chat THEN token_usage populated."""
        provider = MockProvider(responses={"test": "Short response"})
        config = LLMConfig(model="deepseek-v4")
        resp = await provider.chat(
            messages=[{"role": "user", "content": "this is a test"}],
            config=config,
        )
        assert resp.token_usage["prompt"] > 0
        assert resp.token_usage["completion"] > 0
        assert resp.token_usage["total"] > 0
