#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Autonomy layer — 任务协调能力（不替换确定性 pipeline 内核）。

模块：
  watchdog — 无实质进展检测（返工/重试的连续相同失败签名）
  triggers — 信号 → 工单（Fast Path 确定性规则 + 可选 Slow Path LLM）
  router   — 领取工单并驱动 ``run_pipeline``（并发、可回写结果）
  recall   — 以 spec 指纹召回历史运行结果，注入避坑提示

边界：所有执行都必须经过 ``run_pipeline`` 的确定性 Gate 与审计链；
本层只决定「何时跑、跑什么」，不参与「是否放行」的判定。
"""

from yuleosh.pipeline.autonomy.watchdog import (  # noqa: F401
    DEFAULT_MAX_STALLS,
    ProgressRecord,
    Watchdog,
    artifact_digest,
    findings_signature,
    get_watchdog,
)
from yuleosh.pipeline.autonomy.recall import (  # noqa: F401
    RecallStore,
    spec_fingerprint,
)
from yuleosh.pipeline.autonomy.triggers import (  # noqa: F401
    Ticket,
    TicketStore,
    Trigger,
    autonomy_mode,
    propose_tickets,
)
from yuleosh.pipeline.autonomy.router import Router  # noqa: F401

__all__ = [
    "DEFAULT_MAX_STALLS",
    "ProgressRecord",
    "Watchdog",
    "artifact_digest",
    "findings_signature",
    "get_watchdog",
    "RecallStore",
    "spec_fingerprint",
    "Ticket",
    "TicketStore",
    "Trigger",
    "autonomy_mode",
    "propose_tickets",
    "Router",
]
