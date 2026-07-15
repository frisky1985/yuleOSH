#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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


def _call_llm(
    session: PipelineSession,
    system_prompt: str,
    user_prompt: str,
    **kwargs,
) -> dict:
    """Call LLM using the session's injected client or fall back to global chat_completion.

    This is the single point of dependency injection for LLM calls in pipeline steps.
    Tests can inject a mock via ``PipelineSession(llm_client=mock_fn)``.

    For backward-compatible test mock paths, the global fallback is looked up
    through the ``run`` shim module at call time (deferred import avoids cycles).
    """
    # Deferred import from the run shim so that test mocks on
    # yuleosh.pipeline.run.chat_completion take effect.
    from yuleosh.pipeline.run import chat_completion as _fallback
    client = session.llm_client if session.llm_client is not None else _fallback
    return client(system_prompt, user_prompt, **kwargs)


def _check_llm_key() -> Optional[str]:
    """Check for a valid LLM API key in environment variables.

    Returns the key if found, or None if neither LLM_API_KEY nor
    OPENAI_API_KEY is set.
    """
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("""
❌ LLM API key not found

yuleOSH's pipeline requires an LLM API key to run AI agent steps.
Set one of these environment variables:

    export LLM_API_KEY=sk-...    # OpenAI/OpenAI-compatible API
    export OPENAI_API_KEY=sk-... # OpenAI

Then re-run: yuleosh pipeline run <spec>

\U0001f4a1 For demo/testing without a real LLM, use the --mock flag:
    yuleosh pipeline run --mock docs/spec.md
""")
    return key
