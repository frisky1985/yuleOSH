#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Thread-local pipeline step context (D2, 2026-08-19).

并行执行 (orchestrator PARALLEL_GROUPS) 时, session.pipeline_knowledge_step_key
是共享字段 — 多个线程同时写会互相覆盖, 导致 _call_llm 的 knowledge injection
用错 step_key。本模块提供 thread-local 的 step_key 存取:

  - orchestrator 在调用 handler 前 ``set_step_key(step_key)`` (线程内)
  - ``_call_llm`` / ``llm_gateway`` 优先读 ``get_step_key()``, 回退到
    ``session.pipeline_knowledge_step_key`` (串行路径行为不变)

threading.local 每个线程独立副本, ThreadPoolExecutor worker 线程间互不
干扰, 无需锁。
"""

from __future__ import annotations

import threading

_local = threading.local()


def set_step_key(step_key: str) -> None:
    """Set the current step key for the calling thread."""
    _local.step_key = step_key


def get_step_key() -> str:
    """Return the calling thread's current step key ('' if unset)."""
    return getattr(_local, "step_key", "")


def clear_step_key() -> None:
    """Clear the calling thread's step key (defensive; worker reuse)."""
    if hasattr(_local, "step_key"):
        del _local.step_key
