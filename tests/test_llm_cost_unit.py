"""Unit tests for yuleosh.llm.cost — pure Python, no external deps."""

# @tests src/yuleosh/llm/client.py

import pytest
from yuleosh.llm.cost import LLMCallLog, CostLogger


class TestLLMCallLog:
    def test_create(self):
        log = LLMCallLog(
            timestamp="2024-01-01T00:00:00",
            task_type="analysis",
            model="gpt-4",
            provider="openai",
            tokens_in=100,
            tokens_out=50,
            cost=0.03,
            duration_s=1.5,
            status="success",
        )
        assert log.model == "gpt-4"
        assert log.tokens_in == 100
        assert log.tokens_out == 50
        assert log.cost == 0.03


class TestCostLogger:
    def test_create_default(self):
        logger = CostLogger()
        assert logger is not None
