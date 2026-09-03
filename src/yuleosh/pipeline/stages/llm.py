#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Stages — LLM call helpers.

Extracted from stages.py (Phase 2.1 refactor, P0-4).

These functions provide pipeline-wide LLM access. They are planned for
migration to llm/client.py (see tech-debt P0-2).
"""

import logging
import os
from typing import Optional

from yuleosh.pipeline.session import PipelineSession
from yuleosh.llm.client import chat_completion
from yuleosh.agent_registry import (
    AGENT_SAFE_BASELINE,
    resolve_agent_for_step,
    resolve_agent_role,
)

log = logging.getLogger("pipeline.stages.llm")


def _build_effective_system_prompt(
    session: PipelineSession,
    system_prompt: str,
) -> str:
    """Prepend agent constraints to the system prompt.

    A1-A4 (2026-08-08): constraints are injected per role.  When the
    session carries ``agent_constraints_by_role`` (dict[role, text]),
    only the *current step's* role constraints are injected together
    with the shared safety baseline.  If the current step's role has no
    matching file, only the shared baseline is injected — other roles'
    rules are never mixed in.  Sessions without
    ``agent_constraints_by_role`` keep the legacy
    ``session.agent_constraints`` behaviour.

    The wrapper marker starts with ``[Agent Constraints``; if the step
    prompt already contains it (or the legacy ``# AGENTS.md`` /
    ``# RULES.md`` markers), constraints are not duplicated.
    """
    # 统一去重标记 (A3): wrapper 标记前缀 + 兼容旧标记。
    if (
        "[Agent Constraints" in system_prompt
        or "# AGENTS.md" in system_prompt
        or "# RULES.md" in system_prompt
    ):
        return system_prompt

    # A1-A4: per-role isolation path (real dict only — MagicMock sessions
    # without the field must keep falling through to the legacy path).
    by_role = getattr(session, "agent_constraints_by_role", None)
    if isinstance(by_role, dict) and by_role:
        return _build_role_scoped_prompt(session, system_prompt, by_role)

    # 向后兼容：session 无 by_role 字段时走原 session.agent_constraints 逻辑
    if not session.agent_constraints:
        return system_prompt

    effective = (
        "[Agent Constraints — loaded from .yuleosh/agents/]\n\n"
        f"{session.agent_constraints}\n\n"
        "[End Agent Constraints]\n\n"
        f"{system_prompt}"
    )
    return effective


def _build_role_scoped_prompt(
    session: PipelineSession,
    system_prompt: str,
    by_role: dict,
) -> str:
    """Inject only the current step's role constraints + shared baseline.

    Resolution chain (A1): session.pipeline_knowledge_step_key ->
    resolve_agent_for_step -> resolve_agent_role -> by_role lookup.
    Never mixes other roles' constraints: when the step's role has no
    matching file, only the shared safety baseline is injected (绝不
    静默混合其他角色).
    """
    step_key = getattr(session, "pipeline_knowledge_step_key", "") or ""
    if not isinstance(step_key, str):
        step_key = ""
    # D2 (2026-08-19): 并行组执行时优先读 thread-local step_key —
    # session.pipeline_knowledge_step_key 是共享字段, 多线程并发会互相覆盖。
    from yuleosh.pipeline.step_context import get_step_key as _tl_step_key

    _tl = _tl_step_key()
    if _tl:
        step_key = _tl
    agent = resolve_agent_for_step(step_key)
    role = resolve_agent_role(agent) if agent else None

    baseline = getattr(session, "agent_shared_baseline", "") or AGENT_SAFE_BASELINE
    parts: list[str] = []
    if baseline:
        parts.append(baseline.strip())
    role_constraints = by_role.get(role) if role else None
    if role_constraints:
        parts.append(role_constraints.strip())

    if not parts:
        return system_prompt

    body = "\n\n".join(parts)
    scope = role or "shared"
    return (
        f"[Agent Constraints — role-scoped ({scope})]\n\n"
        f"{body}\n\n"
        "[End Agent Constraints]\n\n"
        f"{system_prompt}"
    )


def _gateway_step_keys() -> set:
    """Parse ``YULEOSH_LLM_GATEWAY_STEPS`` (comma-separated step keys).

    方案 C (C5, 2026-08-08): 灰度迁移名单。命中名单的步骤改走
    ``llm_gateway.call_step_llm`` 统一入口，其余步骤保持旧路径。
    """
    raw = os.environ.get("YULEOSH_LLM_GATEWAY_STEPS", "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def _call_llm(
    session: PipelineSession,
    system_prompt: str,
    user_prompt: str,
    **kwargs,
) -> dict:
    """Call LLM using the session's injected client or fall back to global chat_completion.

    This is the single point of dependency injection for LLM calls in pipeline steps.
    Tests can inject a mock via ``PipelineSession(llm_client=mock_fn)``.

    Before calling the LLM, ``session.agent_constraints`` (loaded from
    ``.yuleosh/agents/`` by the orchestrator) are prepended to the
    ``system_prompt`` so that all pipeline steps receive agent behavior
    rules as system context.

    Pipeline knowledge injection (方案 A, 2026-08-07): when the session is
    not in mock mode, the unified knowledge context (memory + RAG + skills
    + active knowledge) is assembled with ``user_prompt`` as the retrieval
    query and prepended to the effective system prompt.  Any retrieval
    failure degrades non-fatally (empty context, warning) — the LLM call
    always proceeds.  Mock mode skips injection so placeholder runs stay
    deterministic and fast.

    灰度迁移 (方案 C, C5, 2026-08-08): 当
    ``session.pipeline_knowledge_step_key`` 命中 ``YULEOSH_LLM_GATEWAY_STEPS``
    （逗号分隔 step_key 列表）时改走 ``llm_gateway.call_step_llm`` 统一
    入口（token 预算 + usage 记录 + 失败包装），返回 dict 形态不变
    （``{"content": ...}``，usage 由网关直接记入 session，避免 handler
    二次累计）；其余步骤保持旧路径，签名与行为完全向后兼容。

    For backward-compatible test mock paths, the global fallback is looked up
    through the ``run`` shim module at call time (deferred import avoids cycles).
    """
    # 方案 C (C5): 灰度切换到 llm_gateway 统一入口。
    # D2 (2026-08-19): 并行组执行时优先读 thread-local step_key。
    from yuleosh.pipeline.step_context import get_step_key as _tl_step_key

    step_key = _tl_step_key() or (
        getattr(session, "pipeline_knowledge_step_key", "") or ""
    )
    if isinstance(step_key, str) and step_key in _gateway_step_keys():
        from yuleosh.pipeline.llm_gateway import call_step_llm

        temperature = kwargs.pop("temperature", 0.3)
        max_tokens = kwargs.pop("max_tokens", 4096)
        if kwargs:
            log.warning(
                "llm_gateway step '%s': unsupported kwargs ignored: %s",
                step_key,
                sorted(kwargs),
            )
        content = call_step_llm(
            session,
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {"content": content}

    # Inject agent constraints into the system prompt
    effective_system = _build_effective_system_prompt(session, system_prompt)

    # Inject unified pipeline knowledge context (方案 A).
    # Strict `is True` mock check (MagicMock honesty — same as mock_skip).
    if getattr(session, "mock_mode", None) is not True:
        try:
            from yuleosh.pipeline.knowledge_injection import (
                assemble_pipeline_knowledge,
                load_pipeline_knowledge_config,
            )

            config = getattr(session, "pipeline_knowledge_config", None)
            if config is None:
                config = load_pipeline_knowledge_config(session.project_dir)
                session.pipeline_knowledge_config = config
            knowledge_ctx = assemble_pipeline_knowledge(
                step_key=getattr(session, "pipeline_knowledge_step_key", ""),
                prompt=user_prompt,
                config=config,
                project_dir=session.project_dir,
            )
            if knowledge_ctx:
                effective_system = (
                    f"{effective_system}\n\n[knowledge context — injected by "
                    f"yuleOSH pipeline]\n{knowledge_ctx}"
                    if effective_system
                    else f"[knowledge context — injected by yuleOSH pipeline]\n{knowledge_ctx}"
                )
        except Exception as e:  # noqa: BLE001 — injection must never block LLM
            log.warning("Pipeline knowledge injection failed (non-fatal): %s", e)

    # Deferred import from the run shim so that test mocks on
    # yuleosh.pipeline.run.chat_completion take effect.
    from yuleosh.pipeline.run import chat_completion as _fallback

    # 9.3.1 (2026-08-19 第九轮): 上下文安全强制化 — 运行时估算水位,
    # >50% 自动切换引用式注入（不静默截断）, >80% 保持 TokenBudgetChecker
    # 拒绝/降级逻辑但带 context_mode=over_limit 标记。mock 模式不触发
    # （上方 mock 分支已短路; 此处再加一道守卫保持诚实）。
    if getattr(session, "mock_mode", None) is not True:
        try:
            from yuleosh.pipeline.context_guard import (
                CONTEXT_OVER_LIMIT,
                CONTEXT_REFERENCE,
                estimate_context_level,
                reference_inject,
            )

            level = estimate_context_level(effective_system, user_prompt)
            mode = level.get("mode", CONTEXT_OVER_LIMIT)
            if mode == CONTEXT_REFERENCE:
                new_user, changes = reference_inject(
                    user_prompt, getattr(session, "session_dir", ".")
                )
                if changes:
                    log.info(
                        "context_guard: reference injection replaced %d "
                        "artifact block(s) (%s)",
                        len(changes),
                        ", ".join(c["key"] for c in changes[:5]),
                    )
                    user_prompt = new_user
                    level["changes"] = changes
            elif mode == CONTEXT_OVER_LIMIT:
                log.warning(
                    "context_guard: %s — keep TokenBudgetChecker reject/"
                    "degrade (context_mode=over_limit)",
                    level.get("reason", ""),
                )
            # 记录到 session（报告 JSON 可见, 不静默）
            try:
                session.context_guard = level
            except Exception:  # pragma: no cover - defensive  # noqa: BLE001
                pass
        except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
            log.warning("context_guard check failed (non-fatal): %s", e)

    client = session.llm_client if session.llm_client is not None else _fallback
    from yuleosh.pipeline.session import PipelineStepError

    try:
        return client(effective_system, user_prompt, **kwargs)
    except PipelineStepError:
        # 已是明确的"不可 fallback"失败语义（如阻塞门禁），原样上抛。
        raise
    except Exception as _llm_err:  # noqa: BLE001
        # 单步 LLM 调用失败（超时 / 网络 / 模型错误）须上报，不可静默成
        # 空内容假绿，也不可被 orchestrator 的模板 fallback 假绿掩盖。
        # 包装为 PipelineStepError → orchestrator:1007 的 except 分支直接
        # 标记 step failed（不 fallback），整链继续而非崩溃。
        log.error(
            "LLM call failed for step '%s' (model=%s): %s",
            step_key,
            os.environ.get("LLM_MODEL", getattr(session, "llm_model", "") or "?"),
            _llm_err,
        )
        raise PipelineStepError(
            f"LLM call failed for step '{step_key}': {_llm_err}"
        ) from _llm_err


def _check_llm_key() -> Optional[str]:
    """Check for a valid LLM API key in environment variables.

    Returns the key if found, or None if neither LLM_API_KEY nor
    OPENAI_API_KEY is set.
    """
    key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        print("""
❌ LLM API key not found

yuleOSH's pipeline requires an LLM API key to run AI agent steps.
Set one of these environment variables:

    export LLM_API_KEY=sk-...        # OpenAI/OpenAI-compatible API
    export DEEPSEEK_API_KEY=sk-...   # DeepSeek
    export OPENAI_API_KEY=sk-...     # OpenAI

Then re-run: yuleosh pipeline run <spec>

\U0001f4a1 For demo/testing without a real LLM, use the --mock flag:
    yuleosh pipeline run --mock docs/spec.md
""")
    return key