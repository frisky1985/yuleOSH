#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/base.py — AbstractProvider ABC and LLMConfig dataclass.

Every provider adapter (Claude, DeepSeek, OpenAI, Mock) inherits from
``AbstractProvider`` and implements ``chat()`` + ``estimate_cost()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class LLMConfig:
    """Per-call LLM configuration."""

    model: str = "deepseek-v4"
    provider: str = "deepseek"
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.95
    timeout_s: int = 60
    max_retries: int = 3

    # RAG
    rag_enabled: bool = True
    rag_sources: List[str] = field(default_factory=lambda: ["misra", "best_practices"])

    # Project memory (memory facts + session history → LLM context)
    memory_enabled: bool = True
    memory_max_facts: int = 5
    memory_max_sessions: int = 3
    memory_max_chars: int = 2000

    # Cost control
    max_cost_usd: float = 0.50

    # Provider-level fallback (provider_fallback.py) — degrade to a backup
    # provider when the primary fails at transport level.
    fallback_enabled: bool = True
    fallback_order: list[str] | None = None  # e.g. ["anthropic", "openai", "mock"]

    # Metadata
    task_type: Optional[str] = None
    task_id: Optional[str] = None
    user_id: Optional[str] = None

    # AI 生成溯源（合规专家 P1）：成功调用时把 model + prompt_hash 写入
    # SHA-256 审计链（ai.generation 事件）。设 False 可关闭。
    audit_ai: bool = True


@dataclass
class LLMResponse:
    """Standardised LLM response."""

    content: str
    model: str
    provider: str
    token_usage: Dict[str, int]  # {"prompt": N, "completion": N, "total": N}
    cost: float = 0.0
    duration_s: float = 0.0
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# Provider ABC
# ═══════════════════════════════════════════════════════════════════════


class AbstractProvider(ABC):
    """Base class for all LLM provider adapters."""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            config:  Per-call configuration.

        Returns:
            LLMResponse with content, model, usage, cost.
        """
        ...

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate the cost of a call in USD."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g. 'anthropic', 'deepseek', 'openai')."""
        ...


# ═══════════════════════════════════════════════════════════════════════
# Pricing lookup
# ═══════════════════════════════════════════════════════════════════════
#
# CP-P2-01: Single source of truth for pricing and task budgets.
# All consumers import from this module (token_budget.py, client.py).
# Do NOT duplicate these dicts elsewhere — add new entries here only.
#

PRICING_TABLE: Dict[str, Dict[str, float]] = {
    "claude-4-sonnet": {
        "input_per_1k": 0.015,
        "output_per_1k": 0.075,
        "context_window": 200_000,
    },
    "claude-4-haiku": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
        "context_window": 200_000,
    },
    "deepseek-v4": {
        "input_per_1k": 0.002,
        "output_per_1k": 0.008,
        "context_window": 128_000,
    },
    "gpt-4o": {
        "input_per_1k": 0.010,
        "output_per_1k": 0.030,
        "context_window": 128_000,
    },
}

TASK_BUDGETS: Dict[str, Dict[str, float]] = {
    "code_generation": {"max_cost_usd": 0.50, "max_tokens_out": 4096},
    "test_generation": {"max_cost_usd": 0.30, "max_tokens_out": 2048},
    "architecture_design": {"max_cost_usd": 0.80, "max_tokens_out": 6144},
    "misra_review": {"max_cost_usd": 0.40, "max_tokens_out": 3072},
    "simple_summary": {"max_cost_usd": 0.10, "max_tokens_out": 1024},
    # 方案 C (C3): agent 标签预算，与各自 AGENT_MODEL_ROUTES 的 task_type
    # 预算一致。resolve_config 会先把 agent 标签映射为 task_type 再查表，
    # 此处仅为路由表自洽（直接按 agent 标签取预算也成立）。
    "小明": {"max_cost_usd": 0.50, "max_tokens_out": 4096},  # review_blocking
    "小克": {"max_cost_usd": 0.50, "max_tokens_out": 4096},  # code_generation
    "小马": {"max_cost_usd": 0.40, "max_tokens_out": 3072},  # misra_review
    "Hermes": {"max_cost_usd": 0.80, "max_tokens_out": 6144},  # architecture_design
    "Claude": {"max_cost_usd": 0.80, "max_tokens_out": 6144},  # architecture_design
    "QEMU": {"max_cost_usd": 0.10, "max_tokens_out": 1024},  # simple_summary
}
