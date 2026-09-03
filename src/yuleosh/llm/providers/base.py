#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/providers/base.py — AbstractProvider ABC and LLMConfig dataclass.

Every provider adapter (Claude, DeepSeek, OpenAI, Mock) inherits from
``AbstractProvider`` and implements ``chat()`` + ``estimate_cost()``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

# 本地大模型（Ollama / 非推理模型）单步生成可能耗时数分钟；默认把超时从
# 60s 提到 1800s，并允许通过 YULEOSH_LLM_TIMEOUT 覆盖（秒）。
_DEFAULT_LLM_TIMEOUT_S = int(os.environ.get("YULEOSH_LLM_TIMEOUT", "1800"))

# 本地 ollama 默认 context 窗口（ollama 服务默认仅 4096，真实 step 输入常超限
# 触发 400 exceed_context_size_error）。通过 YULEOSH_LLM_CONTEXT_WINDOW 可覆盖。
# 仅对本地端点透传 num_ctx；0 表示不发送（留给云端自行管理）。
_DEFAULT_LLM_CONTEXT_WINDOW = int(os.environ.get("YULEOSH_LLM_CONTEXT_WINDOW", "32768"))


@dataclass
class LLMConfig:
    """Per-call LLM configuration."""

    model: str = "deepseek-v4"
    provider: str = "deepseek"
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.95
    timeout_s: int = _DEFAULT_LLM_TIMEOUT_S
    max_retries: int = 3

    # 本地 ollama 透传的 context 窗口（num_ctx）。默认 32768；>0 时仅对本地
    # 端点注入请求体，避免把无效参数发给真实 DeepSeek/OpenAI 云端。
    # 0 = 不发送 num_ctx。可用 YULEOSH_LLM_CONTEXT_WINDOW 覆盖。
    context_window: int = _DEFAULT_LLM_CONTEXT_WINDOW

    # Reproducibility (H1-1): seed for deterministic output; penalties to
    # reduce repetition/fixation. Supported by DeepSeek, Anthropic, OpenAI.
    seed: Optional[int] = None
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0

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

    # Anti-hallucination: KG anchoring (双层幻觉防护)
    anchoring_enabled: bool = True
    anchoring_tasks: list[str] = field(default_factory=lambda: [
        "code_generation", "safety_code_generation", "spec_review",
        "architecture_design", "test_generation",
    ])
    voting_n_variants: int = 3
    voting_consensus_threshold: float = 0.7


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
    # H3-1a: LLM self-reported output confidence (0.0–1.0). None means not
    # reported. Parsed from LLM output by the L1 fallback layer.
    confidence: Optional[float] = None

    # Anti-hallucination: KG anchoring (双层幻觉防护)
    anchored: bool = True
    anchor_method: str = "none"  # "kg-entity" | "voting-consensus" | "voting-divergent" | "none"
    anchor_ids: list[str] = field(default_factory=list)


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
    # 兼容别名（T11）：``deepseek-chat`` 是 DeepSeek API 的传输层模型名
    # （providers/deepseek.py MODEL_ALIASES 把 deepseek-v4 映射过去），但
    # legacy chat_completion() 与 LLM_MODEL 的默认值直接拿它当逻辑模型名用。
    # 缺这条时预算检查以 "no pricing data" 失败 → 静默降级到 mock provider，
    # 真实 LLM 链路因此一直打不通。定价与 deepseek-v4 一致。
    "deepseek-chat": {
        "input_per_1k": 0.002,
        "output_per_1k": 0.008,
        "context_window": 128_000,
    },
    "gpt-4o": {
        "input_per_1k": 0.010,
        "output_per_1k": 0.030,
        "context_window": 128_000,
    },
    # 本地模型（Ollama / 自建 OpenAI 兼容端点）：零费用，pricing 全 0。
    # 预算检查（token_budget.py）对无 pricing 条目的模型会判失败并降级跳过
    # 主 provider，故本地常用 tag 需在此登记；否则 YULEOSH_LLM_UNIFIED=1
    # （统一入口）路径下真实调用会被降级到备用 provider。换其它本地 tag 时
    # 复制此条并改模型名即可。
    "deepseek-r1:7b": {
        "input_per_1k": 0.0,
        "output_per_1k": 0.0,
        "context_window": 128_000,
    },
    # qwen2.5-coder 系列（Mac Mini M4 16GB 推荐 14b，7b 用于快速链路验证）：
    # 非推理模型，直接输出 content；本地零费用。context 按本地透传的
    # num_ctx（默认 32768）设定，预算检查不会因窗口过小误报。
    "qwen2.5-coder:14b": {
        "input_per_1k": 0.0,
        "output_per_1k": 0.0,
        "context_window": 32768,
    },
    "qwen2.5-coder:7b": {
        "input_per_1k": 0.0,
        "output_per_1k": 0.0,
        "context_window": 32768,
    },
}

TASK_BUDGETS: Dict[str, Dict[str, float]] = {
    "code_generation": {"max_cost_usd": 0.50, "max_tokens_out": 4096},
    "test_generation": {"max_cost_usd": 0.30, "max_tokens_out": 8192},
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
    "Codex": {"max_cost_usd": 0.50, "max_tokens_out": 4096},  # review_blocking
    "小仓": {"max_cost_usd": 0.50, "max_tokens_out": 4096},  # review_blocking (CM Gate, 2026-08-19)
    "QEMU": {"max_cost_usd": 0.10, "max_tokens_out": 1024},  # simple_summary
}
