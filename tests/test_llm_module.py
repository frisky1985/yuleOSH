#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for llm module — client, token_budget, cost, RAG engine.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from yuleosh.llm import LLMClient, LLMConfig, LLMResponse
from yuleosh.llm.token_budget import TokenBudgetChecker
from yuleosh.llm.cost import CostLogger, LLMCallLog
from yuleosh.llm.rag.engine import RAGEngine
from yuleosh.llm.providers.base import PRICING_TABLE, TASK_BUDGETS
from yuleosh.llm.providers.mock import MockProvider


class TestLLMConfig:
    """LLMConfig dataclass."""

    def test_default_config(self):
        c = LLMConfig()
        assert c.model == "deepseek-v4"
        assert c.provider == "deepseek"
        assert c.temperature == 0.3
        assert c.rag_enabled is True
        assert c.max_cost_usd == 0.50

    def test_custom_config(self):
        c = LLMConfig(
            model="claude-4-sonnet",
            provider="anthropic",
            temperature=0.1,
            rag_enabled=False,
            task_type="architecture_design",
        )
        assert c.model == "claude-4-sonnet"
        assert c.rag_enabled is False


class TestLLMResponse:
    """LLMResponse dataclass."""

    def test_success_response(self):
        r = LLMResponse(
            content="# UART Driver\n\nvoid uart_init(void) { ... }",
            model="claude-4-sonnet",
            provider="anthropic",
            token_usage={"prompt": 100, "completion": 50, "total": 150},
            cost=0.015,
            duration_s=3.2,
        )
        assert r.content.startswith("# UART Driver")
        assert r.cost == 0.015

    def test_error_response(self):
        r = LLMResponse(
            content="",
            model="deepseek-v4",
            provider="deepseek",
            token_usage={},
            error="API timeout after 60s",
        )
        assert r.error is not None
        assert "timeout" in r.error


class TestTokenBudgetChecker:
    """Token budget pre-check."""

    def test_budget_check_passes(self):
        config = LLMConfig(
            model="deepseek-v4",
            provider="deepseek",
            task_type="simple_summary",
        )
        result = TokenBudgetChecker.check(
            prompt="Summarize the pipeline results.",
            config=config,
        )
        assert result.passed is True
        assert result.estimated_cost > 0

    def test_budget_check_fails_on_context(self):
        config = LLMConfig(model="deepseek-v4", provider="deepseek")
        # Very long prompt to exceed context
        long_prompt = "x" * 500_000
        result = TokenBudgetChecker.check(prompt=long_prompt, config=config)
        assert result.passed is False
        assert "Context" in result.reason

    def test_budget_estimates_reasonable(self):
        config = LLMConfig(
            model="deepseek-v4",
            provider="deepseek",
            task_type="code_generation",
        )
        result = TokenBudgetChecker.check(
            prompt="Generate a UART driver for stm32\n" * 10,
            config=config,
            system_prompt="You are an embedded C expert.",
        )
        assert result.estimated_prompt_tokens > 0
        assert result.estimated_cost > 0

    def test_unknown_model_fails(self):
        config = LLMConfig(model="nonexistent-model", provider="fake")
        result = TokenBudgetChecker.check(prompt="test", config=config)
        assert result.passed is False
        assert "Unknown model" in result.reason

    def test_estimate_tokens_empty(self):
        tokens = TokenBudgetChecker.estimate_tokens("")
        assert tokens == 0

    def test_estimate_tokens_simple(self):
        tokens = TokenBudgetChecker.estimate_tokens("Hello, world!")
        assert tokens > 0

    def test_estimate_tokens_cjk(self):
        tokens = TokenBudgetChecker.estimate_tokens("你好，世界")
        assert tokens > 0

    def test_pricing_table_exists(self):
        assert "deepseek-v4" in PRICING_TABLE
        assert "claude-4-sonnet" in PRICING_TABLE
        assert "gpt-4o" in PRICING_TABLE

    def test_task_budgets_exist(self):
        assert "code_generation" in TASK_BUDGETS
        assert "simple_summary" in TASK_BUDGETS


class TestCostLogger:
    """LLM call audit logging."""

    @pytest.fixture
    def log_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            CostLogger._log_dir = tmp
            yield tmp

    def test_log_entry(self, log_dir):
        entry = LLMCallLog(
            timestamp="2026-07-05T14:00:00Z",
            task_type="code_generation",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=100,
            tokens_out=50,
            cost=0.002,
            duration_s=5.0,
            status="success",
            task_id="T001",
        )
        CostLogger.log(entry)
        log_path = os.path.join(log_dir, "llm_calls.jsonl")
        assert os.path.exists(log_path)
        with open(log_path) as f:
            line = f.readline().strip()
            data = json.loads(line)
        assert data["task_type"] == "code_generation"
        assert data["cost"] == 0.002
        assert data["status"] == "success"

    def test_log_dict_convenience(self, log_dir):
        CostLogger.log_dict(
            timestamp="2026-07-05T15:00:00Z",
            task_type="misra_review",
            model="claude-4-sonnet",
            provider="anthropic",
            tokens_in=500,
            tokens_out=200,
            cost=0.0225,
            duration_s=12.0,
            status="success",
        )
        log_path = os.path.join(log_dir, "llm_calls.jsonl")
        with open(log_path) as f:
            data = json.loads(f.readline())
        assert data["model"] == "claude-4-sonnet"

    def test_get_daily_summary(self, log_dir):
        CostLogger.log_dict(
            timestamp="2026-07-05T10:00:00Z",
            task_type="code_generation",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=100,
            tokens_out=50,
            cost=0.002,
            duration_s=3.0,
            status="success",
        )
        CostLogger.log_dict(
            timestamp="2026-07-05T11:00:00Z",
            task_type="misra_review",
            model="claude-4-sonnet",
            provider="anthropic",
            tokens_in=500,
            tokens_out=200,
            cost=0.0225,
            duration_s=12.0,
            status="success",
        )

        summary = CostLogger.get_daily_summary("2026-07-05")
        assert summary["total_calls"] == 2
        assert summary["total_cost"] == pytest.approx(0.0245, rel=1e-3)
        assert summary["successful"] == 2

    def test_get_daily_summary_empty_date(self, log_dir):
        summary = CostLogger.get_daily_summary("2099-01-01")
        assert summary["total_calls"] == 0

    def test_get_task_cost(self, log_dir):
        CostLogger.log_dict(
            timestamp="2026-07-05T10:00:00Z",
            task_type="code_generation",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=100,
            tokens_out=50,
            cost=0.002,
            duration_s=3.0,
            status="success",
            task_id="T001",
        )
        cost = CostLogger.get_task_cost("T001")
        assert cost == pytest.approx(0.002, rel=1e-3)

    def test_get_task_cost_nonexistent(self, log_dir):
        cost = CostLogger.get_task_cost("NONEXISTENT")
        assert cost == 0.0

    def test_log_failure(self, log_dir):
        CostLogger.log_dict(
            timestamp="2026-07-05T12:00:00Z",
            task_type="code_generation",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=0,
            tokens_out=0,
            cost=0.0,
            duration_s=10.0,
            status="failed: API timeout",
        )
        summary = CostLogger.get_daily_summary("2026-07-05")
        assert summary["failed"] == 1


class TestRAGEngine:
    """RAG retrieval engine prototype."""

    @pytest.fixture
    def engine(self):
        return RAGEngine()

    def test_empty_retrieval(self, engine):
        import asyncio
        results = asyncio.run(engine.retrieve("test query"))
        assert len(results) == 0  # Empty engine

    def test_index_misra_rules(self, engine):
        count = engine.index_misra_rules()
        assert count >= 5  # At least our sample rules
        assert engine.chunk_count >= 5

    def test_retrieve_misra_rule(self, engine):
        engine.index_misra_rules()
        import asyncio
        results = asyncio.run(engine.retrieve(
            "How to fix implicit integer conversion?",
            sources=["misra_c"],
            top_k=3,
        ))
        assert len(results) > 0
        # Rule 10.1 should be among the top results
        rule_ids = [r.chunk.id for r in results]
        assert any("10.1" in rid for rid in rule_ids)

    def test_retrieve_as_context(self, engine):
        engine.index_misra_rules()
        import asyncio
        context = asyncio.run(engine.retrieve_as_context(
            "Pointer arithmetic and conversion rules",
            sources=["misra_c"],
            top_k=2,
        ))
        assert len(context) > 0
        assert "Knowledge Context" in context

    def test_retrieve_filter_by_source(self, engine):
        engine.index_misra_rules()
        # Index some best practices
        practices = [
            {"id": "bp_uart", "title": "UART Ring Buffer", "content": "Use ring buffer for UART RX"},
        ]
        engine.index_best_practices(practices)
        assert engine.chunk_count >= 6

        import asyncio
        # Filter to only misra
        misra_results = asyncio.run(engine.retrieve(
            "UART buffer",
            sources=["misra_c"],
            top_k=5,
        ))
        misra_ids = [r.chunk.id for r in misra_results]
        assert all("bp_" not in id for id in misra_ids)

    def test_clear_engine(self, engine):
        engine.index_misra_rules()
        assert engine.chunk_count > 0
        engine.clear()
        assert engine.chunk_count == 0

    def test_retrieve_with_min_score(self, engine):
        engine.index_misra_rules()
        import asyncio
        results = asyncio.run(engine.retrieve(
            "zzzzz_nonexistent_keyword_xyzzy",
            min_score=0.5,
        ))
        assert len(results) == 0  # Should not match at high threshold


class TestMockProvider:
    """Mock LLM provider for testing."""

    @pytest.fixture
    def provider(self):
        return MockProvider(responses={
            "UART": "void uart_init(void) { /* UART init */ }",
            "error": "__ERROR__",
        })

    def test_default_response(self, provider):
        import asyncio
        config = LLMConfig(model="test-model", provider="mock")
        response = asyncio.run(provider.chat(
            messages=[{"role": "user", "content": "Hello"}],
            config=config,
        ))
        assert response.content is not None
        assert "Mock response" in response.content
        assert response.provider == "mock"

    def test_registered_response(self, provider):
        import asyncio
        config = LLMConfig(model="test", provider="mock")
        response = asyncio.run(provider.chat(
            messages=[{"role": "user", "content": "Generate UART driver"}],
            config=config,
        ))
        assert "void uart_init" in response.content

    def test_error_trigger(self, provider):
        import asyncio
        config = LLMConfig(model="test", provider="mock")
        response = asyncio.run(provider.chat(
            messages=[{"role": "user", "content": "trigger error test"}],
            config=config,
        ))
        assert response.error is not None

    def test_estimate_cost(self, provider):
        cost = provider.estimate_cost(100, 50)
        assert cost == 0.001  # Fixed mock cost


class TestLLMClient:
    """Unified LLMClient."""

    def setup_method(self):
        LLMClient.reset()

    def test_call_with_mock_provider(self):
        LLMClient.configure_providers({"mock": MockProvider()})
        import asyncio
        response = asyncio.run(LLMClient.call(
            prompt="Generate code",
            config=LLMConfig(provider="mock", model="test-model"),
        ))
        assert response is not None
        assert response.content is not None

    def test_call_with_task_type(self):
        LLMClient.configure_providers({"mock": MockProvider()})
        import asyncio
        response = asyncio.run(LLMClient.call(
            prompt="Write test",
            task_type="test_generation",
            config=LLMConfig(provider="mock", model="test-model"),
        ))
        assert response is not None

    def test_resolve_config_defaults(self):
        LLMClient.configure_providers({"mock": MockProvider()})
        import asyncio
        response = asyncio.run(LLMClient.call(
            prompt="Test",
            config=LLMConfig(provider="mock", model="test-model"),
        ))
        assert response.provider == "mock"
