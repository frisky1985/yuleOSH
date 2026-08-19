#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): review-embedded-realtime — 合并 interrupt + timing + watchdog 专项审查。

2026-08-19 老板八轮拍板（checkpoint v9）: 头脑风暴识别盲区（中断/时序/
看门狗/NVM 是嵌入式最大风险源, 通用 review 必漏），新增 4 个专项 handler；
其中 interrupt/timing/watchdog 新建 embedded-realtime 组。本 handler
内部顺序调用:
  - step_review_interrupt   (中断系统审查, 2026-08-19 新增)
  - step_review_timing      (时序审查, 2026-08-19 新增)
  - step_review_watchdog    (看门狗审查, 2026-08-19 新增)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 embedded-realtime-review.json（sections: interrupt/timing/watchdog）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_embedded_realtime")

__all__ = ["step_review_embedded_realtime"]


@timed_step
def step_review_embedded_realtime(session: PipelineSession) -> str:
    """Step: embedded-realtime 组 — interrupt + timing + watchdog 专项审查（合并）。"""
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review_interrupt import step_review_interrupt
    from yuleosh.pipeline.step_handlers.review_timing import step_review_timing
    from yuleosh.pipeline.step_handlers.review_watchdog import step_review_watchdog

    print("  ⏱️  [embedded-realtime] 中断 → 时序 → 看门狗专项审查（合并）...")
    log.info("Running merged embedded-realtime review (interrupt/timing/watchdog)")

    report, out_path = run_substeps(
        session,
        "embedded-realtime-review",
        [
            ("interrupt", step_review_interrupt),
            ("timing", step_review_timing),
            ("watchdog", step_review_watchdog),
        ],
        summary_prefix="embedded-realtime",
    )
    log.info("embedded-realtime merged status: %s", report.get("status"))
    return out_path
