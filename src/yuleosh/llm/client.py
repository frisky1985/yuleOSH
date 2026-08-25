#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/client.py — Unified LLMClient adapter.

Replaces all direct ``_call_llm`` usage with a single, configurable
entry point that handles routing, RAG, token budgeting, logging, and
retry.

Usage::

    from yuleosh.llm import LLMClient, LLMConfig

    response = await LLMClient.call(
        prompt="Generate a UART driver...",
        task_type="code_generation",
    )
    print(response.content)

Backward-compatible shim ``_call_llm()`` is provided at module bottom.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from yuleosh.llm.providers.base import (
    AbstractProvider,
    LLMConfig,
    LLMResponse,
    TASK_BUDGETS,
)
from yuleosh.llm.providers.mock import MockProvider
from yuleosh.llm.token_budget import TokenBudgetChecker
from yuleosh.llm.cost import CostLogger, LLMCallLog
from yuleosh.llm.provider_fallback import call_with_fallback, fallback_enabled
from yuleosh.llm.rag.engine import RAGEngine, get_default_engine

log = logging.getLogger("llm.client")


# ═══════════════════════════════════════════════════════════════════════
# Task → model routing table
# ═══════════════════════════════════════════════════════════════════════

TASK_ROUTES: Dict[str, str] = {
    "architecture_design": "claude-4-sonnet",
    "code_generation": "deepseek-v4",
    "safety_code_generation": "claude-4-sonnet",
    "test_generation": "deepseek-v4",
    "misra_review": "claude-4-sonnet",
    "misra_fix": "claude-4-sonnet",
    "review_blocking": "claude-4-sonnet",
    "review_selfcheck": "deepseek-v4",
    "simple_summary": "deepseek-v4",
}

TASK_RAG_SOURCES: Dict[str, List[str]] = {
    "code_generation": ["misra_c", "best_practices"],
    "safety_code_generation": ["misra_c", "best_practices"],
    "misra_review": ["misra_c"],
    "misra_fix": ["misra_c"],
    "test_generation": ["best_practices"],
    "architecture_design": ["best_practices"],
    "review_blocking": ["misra_c"],
    "review_selfcheck": ["repo_facts", "kg"],
    "simple_summary": [],
}


# ═══════════════════════════════════════════════════════════════════════
# 方案 A — provider 配置优先级体系
# ═══════════════════════════════════════════════════════════════════════
#
# 优先级（resolve_config，config is None 时）:
#   1. 显式 LLMConfig.provider           （调用方传入，直接 return）
#   2. YULEOSH_LLM_PROVIDER env          （deepseek|anthropic|openai|mock）
#   3. TASK_ROUTES 默认映射              （既有行为）
#
# LLM_MODEL env 覆盖模型名（保持既有 chat_completion 语义）；provider
# 随 env 或模型名推断。LLM_BASE_URL / LLM_API_KEY 由 provider 层读取。

VALID_PROVIDERS: tuple = ("deepseek", "anthropic", "openai", "mock")

# Provider env 覆盖时使用的默认模型（与 docs/llm-strategy.md 路由表一致）。
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-4-sonnet",
    "deepseek": "deepseek-v4",
    "openai": "gpt-4o",
    "mock": "deepseek-v4",
}

# 逻辑模型名 → provider（TASK_ROUTES 默认映射用）。
PROVIDER_MODEL_MAP: dict[str, str] = {
    "claude-4-sonnet": "anthropic",
    "claude-4-haiku": "anthropic",
    "deepseek-v4": "deepseek",
    "gpt-4o": "openai",
}


# ═══════════════════════════════════════════════════════════════════════
# 方案 C (C3) — agent → model 路由表 + 任务风险等级
# ═══════════════════════════════════════════════════════════════════════
#
# 评审决议 (2026-08-08):
#   - 路由键必须是 agent × 任务风险等级（L0 工具 / L1 生成 / L2 结构化 /
#     L3 审查 / L4 决策）；
#   - L3/L4 判定任务（审查 / 设计决策）禁止下钻小模型（防幻觉硬规则）。
#
# AGENT_MODEL_ROUTES 默认值 = 现状（deepseek-v4 / deepseek），不改变任何
# 现有 TASK_ROUTES 映射，保证 golden 测试不碎。task_type 字段用于承接
# TASK_BUDGETS / TASK_RAG_SOURCES / TASK_RISK_LEVELS 等既有体系。

# 已知小模型（低成本 / 快速，幻觉风险高）：L3/L4 任务禁止下钻到这些模型。
SMALL_MODELS: tuple = (
    "deepseek-chat",
    "deepseek-v3",
    "claude-4-haiku",
    "gpt-4o-mini",
    "mock",
)

# agent 标签（见 agent_registry.AGENT_ROLES）→ 路由条目。
AGENT_MODEL_ROUTES: dict[str, dict[str, str]] = {
    "小明": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "review_blocking",
        "risk_level": "L4",
    },
    "小克": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "code_generation",
        "risk_level": "L4",
    },
    "小马": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "misra_review",
        "risk_level": "L3",
    },
    "Hermes": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "architecture_design",
        "risk_level": "L4",
    },
    "Claude": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "architecture_design",
        "risk_level": "L4",
    },
    "Codex": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "review_blocking",
        "risk_level": "L4",
    },
    "小仓": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "review_blocking",
        "risk_level": "L4",  # 2026-08-19 第九轮: CM Gate（merge-gate P0 门禁，KG 一致性 + 仓库管理检查）
    },
    "QEMU": {
        "model": "deepseek-v4",
        "provider": "deepseek",
        "task_type": "simple_summary",
        "risk_level": "L1",
    },
}

# task_type → 风险等级。按 TASK_ROUTES 实际存在的 key 登记；评审建议的
# code_review / requirements_analysis / summary 等 key 在 TASK_ROUTES 中
# 不存在，故由 misra_review / review_*（审查类）与 simple_summary 承担。
TASK_RISK_LEVELS: dict[str, str] = {
    "architecture_design": "L4",  # 设计决策
    "code_generation": "L4",  # 代码生成（安全关键产物）
    "safety_code_generation": "L4",  # 安全关键代码生成
    "test_generation": "L2",  # 结构化测试生成
    "misra_review": "L3",  # MISRA 合规审查
    "misra_fix": "L3",  # 审查后修复判定
    "review_blocking": "L4",  # 阻塞性门禁决策
    "review_selfcheck": "L3",  # 审查自查
    "simple_summary": "L1",  # 简单摘要
}



# ═══════════════════════════════════════════════════════════════════════
# Provider registry (lazy-loaded)
# ═══════════════════════════════════════════════════════════════════════

_PROVIDER_REGISTRY: Dict[str, AbstractProvider] = {}


def _get_provider(provider_name: str) -> AbstractProvider:
    """Get or create a provider instance."""
    if provider_name not in _PROVIDER_REGISTRY:
        if provider_name == "mock":
            _PROVIDER_REGISTRY[provider_name] = MockProvider()
        elif provider_name == "anthropic":
            from yuleosh.llm.providers.anthropic import ClaudeProvider
            _PROVIDER_REGISTRY[provider_name] = ClaudeProvider()
        elif provider_name == "deepseek":
            from yuleosh.llm.providers.deepseek import DeepSeekProvider
            _PROVIDER_REGISTRY[provider_name] = DeepSeekProvider()
        elif provider_name == "openai":
            from yuleosh.llm.providers.openai import OpenAIProvider
            _PROVIDER_REGISTRY[provider_name] = OpenAIProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    return _PROVIDER_REGISTRY[provider_name]


def resolve_config(
    prompt: str,
    system_prompt: Optional[str],
    task_type: Optional[str],
    config: Optional[LLMConfig],
) -> LLMConfig:
    """Resolve the effective LLMConfig for a call.

    Fills in defaults based on task type when config is None.

    方案 A provider 优先级（config is None 时）:
        1. 显式 ``LLMConfig.provider``（调用方传入，直接返回）
        2. ``YULEOSH_LLM_PROVIDER`` env（deepseek|anthropic|openai|mock）
        3. TASK_ROUTES 默认映射（既有行为）

    同时尊重 ``LLM_MODEL`` env（覆盖模型名；provider 随 env 或模型名推断）。

    方案 C (C3) 增强:
        - ``task_type`` 为 agent 标签（如 "小克"）时，先查
          ``AGENT_MODEL_ROUTES`` 映射到 {model, provider, task_type}，
          再走既有 env / 预算 / RAG 逻辑；
        - L3/L4 判定任务（审查 / 设计决策）禁止下钻小模型：显式传入
          task_type 且其风险等级为 L3/L4 时，即使 ``LLM_MODEL`` env 覆盖
          为已知小模型（SMALL_MODELS），也回退到该任务的默认模型并
          log warning（防幻觉硬规则）。未显式传 task_type 时保持既有
          env 覆盖语义（历史 golden 测试兼容）。
    """
    if config is not None:
        return config

    # C3: 仅显式传入 task_type 时启用 L3/L4 禁下钻硬规则；未传时保持
    # 既有 LLM_MODEL env 覆盖语义（test_llm_provider_deepseek 等历史用例）。
    task_type_explicit = task_type is not None
    task_type = task_type or "code_generation"

    # C3: agent 标签路由 → {model, provider, task_type}
    agent_route = AGENT_MODEL_ROUTES.get(task_type)
    route_task_type = agent_route["task_type"] if agent_route is not None else task_type

    provider_env = os.environ.get("YULEOSH_LLM_PROVIDER")
    if provider_env is not None:
        provider_env = provider_env.strip().lower()
        if provider_env not in VALID_PROVIDERS:
            raise ValueError(
                f"YULEOSH_LLM_PROVIDER 必须是 {list(VALID_PROVIDERS)} 之一，"
                f"当前值: '{provider_env}'"
            )

    model_env = os.environ.get("LLM_MODEL")
    model_env = model_env.strip() if model_env else None

    # 无 LLM_MODEL 覆盖时的默认模型
    # （方案 A 优先级：env provider > agent 路由 > TASK_ROUTES）。
    if provider_env:
        default_model = PROVIDER_DEFAULT_MODELS[provider_env]
        provider = provider_env
    elif agent_route is not None:
        default_model = agent_route["model"]
        provider = agent_route["provider"]
    else:
        default_model = TASK_ROUTES.get(route_task_type, "deepseek-v4")
        provider = "deepseek"

    model = model_env or default_model
    if not provider_env:
        provider = PROVIDER_MODEL_MAP.get(model, provider)

    # C3 硬规则：L3/L4 判定任务禁止下钻小模型（防幻觉）。
    risk_level = TASK_RISK_LEVELS.get(route_task_type)
    if task_type_explicit and risk_level in ("L3", "L4") and model in SMALL_MODELS:
        log.warning(
            "L3/L4 硬规则：task_type=%s (risk=%s) 禁止下钻小模型 %r，"
            "回退到默认模型 %r",
            route_task_type,
            risk_level,
            model,
            default_model,
        )
        model = default_model
        if not provider_env:
            provider = PROVIDER_MODEL_MAP.get(model, provider)

    task_budget = TASK_BUDGETS.get(route_task_type, TASK_BUDGETS["code_generation"])

    # Q4: codegen must be deterministic — pin temperature=0.0, seed=42 so
    # repeated runs from the same spec produce byte-comparable outputs.
    is_codegen = route_task_type == "code_generation"
    return LLMConfig(
        model=model,
        provider=provider,
        max_tokens=min(4096, int(task_budget.get("max_tokens_out", 4096))),
        temperature=0.0 if is_codegen else 0.3,
        seed=42 if is_codegen else None,
        rag_enabled=route_task_type not in ("simple_summary",),
        rag_sources=TASK_RAG_SOURCES.get(route_task_type, []),
        max_cost_usd=task_budget.get("max_cost_usd", 0.50),
        task_type=route_task_type,
        memory_enabled=route_task_type not in ("simple_summary",),
    )


# ═══════════════════════════════════════════════════════════════════════
# LLMClient — Unified entry point
# ═══════════════════════════════════════════════════════════════════════


class LLMClient:
    """Unified LLM call entry point.

    Wraps: token budget check → RAG context assembly → provider call
    → cost logging → retry.

    All public methods are classmethods (singleton-like usage).
    """

    _rag_engine: Optional[RAGEngine] = None

    @classmethod
    def _get_rag_engine(cls) -> Optional[RAGEngine]:
        """Lazy-init RAG engine."""
        if cls._rag_engine is None:
            try:
                cls._rag_engine = get_default_engine()
            except Exception as e:
                log.warning("Failed to init RAG engine: %s", e)
                cls._rag_engine = None
        return cls._rag_engine

    @classmethod
    async def call(
        cls,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        config: Optional[LLMConfig] = None,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> LLMResponse:
        """Make a unified LLM call — the single entry point for all modules.

        Args:
            prompt: The user prompt / request text.
            system_prompt: Optional system-level instructions.
            task_type: Task category (for routing / budgeting).
            config: Explicit LLMConfig (auto-resolve if None).
            messages: Pre-built message list (overrides prompt+system).

        Returns:
            LLMResponse with content, model, usage, cost.
        """
        # 1. Resolve config
        resolved_config = resolve_config(prompt, system_prompt, task_type, config)

        # 2. Token budget pre-check
        # mock provider 是免费测试兜底：无真实定价数据（PRICING_TABLE 不含
        # 测试模型名），预算检查对它没有意义且会导致 skip primary 后链上
        # 无可用 provider。跳过 pre-check，让 call_with_fallback 正常走 mock。
        budget_skip_primary: str | None = None
        if resolved_config.provider == "mock":
            budget_check = None
        else:
            budget_check = TokenBudgetChecker.check(
                prompt, resolved_config, system_prompt
            )
        if budget_check is not None and not budget_check.passed:
            if fallback_enabled(resolved_config):
                # 预算超限 → warning + 降级（provider_fallback 跳过主 provider，
                # 降级到链上可用 provider；mock 免费兜底）。不直接报错。
                log.warning(
                    "Token budget check FAILED: %s — 降级到备用 provider",
                    budget_check.reason,
                )
                budget_skip_primary = "budget_exceeded"
            else:
                log.warning(
                    "Token budget check FAILED: %s", budget_check.reason
                )
                return LLMResponse(
                    content="",
                    model=resolved_config.model,
                    provider=resolved_config.provider,
                    token_usage={},
                    cost=0.0,
                    error=f"Budget check failed: {budget_check.reason}",
                )

        # 3. RAG context assembly (if enabled)
        effective_system = system_prompt or ""
        if resolved_config.rag_enabled and resolved_config.rag_sources:
            engine = cls._get_rag_engine()
            if engine:
                try:
                    rag_context = await engine.retrieve_as_context(
                        prompt,
                        sources=resolved_config.rag_sources,
                    )
                    if rag_context:
                        effective_system = (
                            f"{effective_system}\n\n{rag_context}"
                            if effective_system
                            else rag_context
                        )
                except Exception as e:
                    log.warning("RAG retrieval failed (non-fatal): %s", e)

        # 3.5 Project memory injection (if enabled) — memory facts +
        # session history as the "project memory" RAG knowledge source.
        _memory_assembler = None  # kept for H1-2c trust adjust below
        if resolved_config.memory_enabled:
            try:
                from yuleosh.memory.llm_context import (
                    MemoryContextAssembler,
                    is_memory_context_enabled,
                )

                if is_memory_context_enabled():
                    _memory_assembler = MemoryContextAssembler(
                        max_facts=resolved_config.memory_max_facts,
                        max_sessions=resolved_config.memory_max_sessions,
                        max_chars=resolved_config.memory_max_chars,
                    )
                    memory_context = _memory_assembler.assemble(prompt)
                    if memory_context:
                        effective_system = (
                            f"{effective_system}\n\n{memory_context}"
                            if effective_system
                            else memory_context
                        )
            except Exception as e:  # noqa: BLE001 — memory must never block LLM
                log.warning(
                    "Project memory injection failed (non-fatal): %s", e
                )

        # 4. Build messages
        if messages is None:
            msgs: List[Dict[str, str]] = []
            if effective_system:
                msgs.append({"role": "system", "content": effective_system})
            msgs.append({"role": "user", "content": prompt})
        else:
            msgs = messages

        # 5. Get provider and call — via the provider-level fallback chain
        # (provider_fallback.py). Transport failures degrade to the next
        # provider; business errors (4xx) and disabled fallback return an
        # error response as before.
        start_time = time.time()
        response = await call_with_fallback(
            msgs,
            resolved_config,
            skip_primary_reason=budget_skip_primary,
        )
        duration = time.time() - start_time
        response.duration_s = duration

        # 5.5 Memory trust auto-adjust (H1-2c): reinforce facts that were
        # injected into the context. +0.05 on a successful call, −0.10 on
        # error. Non-fatal — trust adjustment must never block the response.
        if _memory_assembler is not None:
            try:
                fact_ids = getattr(_memory_assembler, "last_fact_ids", [])
                if fact_ids:
                    _store = _memory_assembler._store
                    delta = -0.10 if response.error else 0.05
                    _store.adjust_trust_batch(fact_ids, delta)
            except Exception as e:  # noqa: BLE001
                log.warning("Memory trust auto-adjust failed (non-fatal): %s", e)

        # 6. Log the call — the provider field records the provider actually
        # used (after any degradation), not the configured primary.
        try:
            CostLogger.log_dict(
                timestamp=datetime.utcnow().isoformat() + "Z",
                task_type=resolved_config.task_type or "unknown",
                model=response.model,
                provider=response.provider or resolved_config.provider,
                tokens_in=response.token_usage.get("prompt", 0),
                tokens_out=response.token_usage.get("completion", 0),
                cost=response.cost,
                duration_s=duration,
                status=(
                    "success"
                    if not response.error
                    else f"failed: {response.error}"
                ),
                task_id=resolved_config.task_id,
                user_id=resolved_config.user_id,
            )
        except Exception as e:
            log.warning("Failed to log LLM call: %s", e)

        # 6.5 AI 生成溯源 → 审计链（合规专家 P1: AI 输出是「草稿」不是「证据」）。
        # 成功生成时把 model 版本 + prompt 的 SHA-256 写入 ai.generation 审计事件，
        # 使产物的输入可复现、可审计；人工评审通过 AuditLog.sign_ai_generation()
        # 追加签署事件后才升级为证据。审计写入失败只 warning，绝不阻塞主流程。
        # 数据根目录可用 YULEOSH_AUDIT_ROOT env 覆盖（默认同 AuditLog 默认值）。
        if resolved_config.audit_ai and not response.error:
            try:
                from yuleosh.audit.model import AuditLog

                audit_root = os.environ.get("YULEOSH_AUDIT_ROOT")
                audit_log = AuditLog(data_root=audit_root)
                task_type = resolved_config.task_type or "unknown"
                task_id = resolved_config.task_id or ""
                target = (
                    f"artifact:{task_id}" if task_id
                    else f"llm:{task_type}"
                )
                audit_log.record_ai_generation(
                    actor=resolved_config.user_id or "system",
                    target=target,
                    model=response.model,
                    prompt=prompt,
                    tenant="",
                    detail={
                        "task_type": task_type,
                        "provider": response.provider or resolved_config.provider,
                        "temperature": resolved_config.temperature,
                        "seed": resolved_config.seed,
                        "frequency_penalty": resolved_config.frequency_penalty,
                        "presence_penalty": resolved_config.presence_penalty,
                    },
                )
            except Exception as e:  # noqa: BLE001 — audit must never block the LLM call
                log.warning("Failed to record AI generation audit event: %s", e)

        return response

    @classmethod
    def call_sync(
        cls,
        prompt: str,
        system_prompt: str | None = None,
        task_type: str | None = None,
        config: LLMConfig | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> dict:
        """Synchronous bridge to :meth:`call` (方案 C, C1).

        Drives the async unified entry point from synchronous callers
        (e.g. the legacy ``chat_completion`` pipeline path) and adapts the
        returned ``LLMResponse`` back to the legacy dict shape::

            {"content": ..., "model": ..., "usage": {
                "prompt_tokens": N, "completion_tokens": N, "total_tokens": N}}

        Event-loop safety: when no loop is running in the current thread
        ``asyncio.run`` is used; when a loop is already running (async
        caller), a private loop is created with ``new_event_loop`` +
        ``run_until_complete`` so the running loop is never re-entered.

        Raises:
            RuntimeError: when the underlying LLMResponse carries an error,
                preserving the legacy ``chat_completion`` failure semantics.
        """
        coro = cls.call(
            prompt=prompt,
            system_prompt=system_prompt,
            task_type=task_type,
            config=config,
            messages=messages,
        )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running in this thread → asyncio.run is safe.
            response = asyncio.run(coro)
        else:
            # An event loop is already running. Python 3.12 forbids nesting
            # another loop's run_until_complete inside a running loop
            # ("Cannot run the event loop while another loop is running"),
            # so drive the coroutine on a worker thread via asyncio.run.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                response = pool.submit(asyncio.run, coro).result()

        if response.error:
            raise RuntimeError(f"LLM request failed: {response.error}")

        return {
            "content": response.content,
            "model": response.model,
            "usage": _adapt_token_usage(response.token_usage),
        }

    @classmethod
    def configure_providers(cls, providers: Dict[str, AbstractProvider]):
        """Inject custom provider instances (for testing)."""
        _PROVIDER_REGISTRY.clear()
        _PROVIDER_REGISTRY.update(providers)

    @classmethod
    def reset(cls):
        """Reset client state (test isolation)."""
        _PROVIDER_REGISTRY.clear()
        cls._rag_engine = None


# ═══════════════════════════════════════════════════════════════════════
# Backward-compatible shims
# ═══════════════════════════════════════════════════════════════════════


def _adapt_token_usage(token_usage: dict[str, int]) -> dict[str, int]:
    """Adapt ``LLMResponse.token_usage`` to the legacy OpenAI-style usage dict.

    ``LLMResponse`` uses ``{"prompt", "completion", "total"}`` while legacy
    callers expect ``{"prompt_tokens", "completion_tokens", "total_tokens"}``.
    Dicts that are already OpenAI-style pass through unchanged.
    """
    tu = token_usage or {}
    if "prompt" in tu or "completion" in tu or "total" in tu:
        return {
            "prompt_tokens": tu.get("prompt", 0),
            "completion_tokens": tu.get("completion", 0),
            "total_tokens": tu.get("total", 0),
        }
    return dict(tu)


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 60,
    retries: int = 3,
) -> dict:
    """DEPRECATED — backward-compatible synchronous chat completion.

    NOTE (AR-P2-02): This function duplicates the HTTPS/urllib logic that
    should be handled by the individual provider modules (providers/anthropic.py,
    providers/deepseek.py, etc.). It exists solely for backward compatibility
    with legacy callers that import ``chat_completion`` directly.

    Handles the actual OpenAI-compatible HTTP request directly so that
    all existing importers (stages.py etc.) continue to work without changes.

    Reads environment variables LLM_API_KEY, LLM_BASE_URL, LLM_MODEL.

    .. deprecated:: 2.0
        Use ``LLMClient.call()`` instead.
    """
    # 方案 C (C2): YULEOSH_LLM_UNIFIED=1 时走 LLMClient.call_sync 统一入口，
    # 获得预算检查 / provider 回退 / 成本审计；未设置时保留原 urllib 实现。
    if os.environ.get("YULEOSH_LLM_UNIFIED") == "1":
        cfg = LLMConfig(
            model=os.environ.get("LLM_MODEL", "deepseek-chat"),
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout,
            max_retries=retries,
            # 保持旧 chat_completion 语义：不注入 RAG / project memory。
            rag_enabled=False,
            memory_enabled=False,
        )
        return LLMClient.call_sync(
            prompt=user_prompt,
            system_prompt=system_prompt,
            config=cfg,
        )

    import json as _json
    import os as _os
    import time as _time
    import urllib.request as _ur
    import urllib.error as _ue

    api_key = (
        _os.environ.get("LLM_API_KEY")
        or _os.environ.get("DEEPSEEK_API_KEY")
        or _os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base_url = _os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _os.environ.get("LLM_MODEL", "deepseek-chat")

    if not api_key:
        raise RuntimeError("No LLM API key found in environment")

    url = f"{base_url}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            # Create a new Request for each attempt (CQ-P1-02: don't reuse consumed Request)
            req = _ur.Request(
                url,
                data=_json.dumps(body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with _ur.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = _json.loads(raw)

            choice = data["choices"][0]
            content = choice.get("message", {}).get("content", "")
            if content is None:
                content = f"[LLM refused, finish_reason={choice.get('finish_reason', 'unknown')}]"

            return {
                "content": content,
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
            }

        except (_ue.HTTPError, _ue.URLError, _json.JSONDecodeError, RuntimeError) as e:
            last_error = e
            if attempt < retries:
                backoff = 1.0 * (2 ** (attempt - 1))
                _time.sleep(backoff)
            else:
                raise RuntimeError(f"LLM request failed after {retries} retries: {last_error}")

    raise RuntimeError(f"LLM request failed after {retries} retries")



async def _call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    task_type: Optional[str] = None,
) -> str:
    """DEPRECATED — backward-compatible wrapper.

    Calls LLMClient.call() and returns just the content string.

    .. deprecated:: 2.0
        Use ``LLMClient.call()`` directly instead.
    """
    response = await LLMClient.call(
        prompt=prompt,
        system_prompt=system_prompt,
        task_type=task_type,
    )
    return response.content
