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

log = logging.getLogger("pipeline.stages.llm")


def _build_effective_system_prompt(
    session: PipelineSession,
    system_prompt: str,
) -> str:
    """Prepend agent constraints from .yuleosh/agents/ to the system prompt.

    The constraints (loaded into ``session.agent_constraints`` by the
    orchestrator) are added before the step-specific system prompt so that
    they act as foundational behavior rules.

    If the step's system prompt already contains agent constraint markers,
    the constraints are not duplicated.
    """
    if not session.agent_constraints:
        return system_prompt

    # Avoid duplicate injection: check if constraints are already present
    if "# AGENTS.md" in system_prompt or "# RULES.md" in system_prompt:
        return system_prompt

    effective = (
        "[Agent Constraints — loaded from .yuleosh/agents/]\n\n"
        f"{session.agent_constraints}\n\n"
        "[End Agent Constraints]\n\n"
        f"{system_prompt}"
    )
    return effective


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

    For backward-compatible test mock paths, the global fallback is looked up
    through the ``run`` shim module at call time (deferred import avoids cycles).
    """
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
    client = session.llm_client if session.llm_client is not None else _fallback
    return client(effective_system, user_prompt, **kwargs)


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
