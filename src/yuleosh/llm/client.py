#!/usr/bin/env python3
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
    "review_selfcheck": [],
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
    """
    if config is not None:
        return config

    task_type = task_type or "code_generation"

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

    if provider_env:
        provider = provider_env
        model = model_env or PROVIDER_DEFAULT_MODELS[provider]
    else:
        model = model_env or TASK_ROUTES.get(task_type, "deepseek-v4")
        provider = PROVIDER_MODEL_MAP.get(model, "deepseek")

    task_budget = TASK_BUDGETS.get(task_type, TASK_BUDGETS["code_generation"])

    return LLMConfig(
        model=model,
        provider=provider,
        max_tokens=min(4096, int(task_budget.get("max_tokens_out", 4096))),
        temperature=0.3,
        rag_enabled=task_type not in ("simple_summary",),
        rag_sources=TASK_RAG_SOURCES.get(task_type, []),
        max_cost_usd=task_budget.get("max_cost_usd", 0.50),
        task_type=task_type,
        # Project memory follows the same routing rule as RAG: cheap
        # "simple_summary" tasks skip memory injection too.
        memory_enabled=task_type not in ("simple_summary",),
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
        budget_check = TokenBudgetChecker.check(
            prompt, resolved_config, system_prompt
        )
        budget_skip_primary: str | None = None
        if not budget_check.passed:
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
        if resolved_config.memory_enabled:
            try:
                from yuleosh.memory.llm_context import assemble_memory_context

                memory_context = assemble_memory_context(
                    query=prompt,
                    max_facts=resolved_config.memory_max_facts,
                    max_sessions=resolved_config.memory_max_sessions,
                    max_chars=resolved_config.memory_max_chars,
                )
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

        return response

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
