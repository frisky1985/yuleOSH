#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): review-embedded-runtime — 合并 rtos + memory + stack + nvm 专项审查。

2026-08-19 老板八轮拍板（checkpoint v9）: 8 轮新增 nvm 专项并入
embedded-runtime 组（4 子审查）。本 handler 内部顺序调用:
  - step_review_rtos      (RTOS 配置审查)
  - step_review_memory    (内存安全审查)
  - step_review_stack     (堆栈使用分析)
  - step_review_nvm       (NVM 存储审查, 2026-08-19 新增, 对齐 spec SW-006)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 embedded-runtime-review.json（sections: rtos/memory/stack/nvm）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_embedded_runtime")

__all__ = ["step_review_embedded_runtime"]


@timed_step
def step_review_embedded_runtime(session: PipelineSession) -> str:
    """Step: embedded-runtime 组 — rtos + memory + stack + nvm 专项审查（合并）。"""
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review_memory import step_review_memory
    from yuleosh.pipeline.step_handlers.review_nvm import step_review_nvm
    from yuleosh.pipeline.step_handlers.review_rtos import step_review_rtos
    from yuleosh.pipeline.step_handlers.review_stack import step_review_stack

    print("  🧠 [embedded-runtime] RTOS → 内存 → 堆栈 → NVM 专项审查（合并）...")
    log.info("Running merged embedded-runtime review (rtos/memory/stack/nvm)")

    report, out_path = run_substeps(
        session,
        "embedded-runtime-review",
        [
            ("rtos", step_review_rtos),
            ("memory", step_review_memory),
            ("stack", step_review_stack),
            ("nvm", step_review_nvm),
        ],
        summary_prefix="embedded-runtime",
    )
    log.info("embedded-runtime merged status: %s", report.get("status"))
    return out_path
