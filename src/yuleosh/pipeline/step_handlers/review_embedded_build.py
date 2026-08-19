#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): review-embedded-build — 合并 linker + startup + build 专项审查。

2026-08-19 老板八轮拍板（checkpoint v9）: 9 个嵌入式专项（linker/startup/
rtos/memory/bsp/build/power/stack/mmio）是 code-review 的深度补充层，
按领域合并为超集 handler，专项检查一个不少，仅对外显示一个步骤。

本 handler（embedded-build 组）内部顺序调用:
  - step_review_linker    (链接脚本审查)
  - step_review_startup   (启动代码审查)
  - step_review_build     (编译输出验证)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 embedded-build-review.json（sections: linker/startup/build）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_embedded_build")

__all__ = ["step_review_embedded_build"]


@timed_step
def step_review_embedded_build(session: PipelineSession) -> str:
    """Step: embedded-build 组 — linker + startup + build 专项审查（合并）。"""
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review_build import step_review_build
    from yuleosh.pipeline.step_handlers.review_linker import step_review_linker
    from yuleosh.pipeline.step_handlers.review_startup import step_review_startup

    print("  🔗 [embedded-build] 链接 → 启动 → 构建专项审查（合并）...")
    log.info("Running merged embedded-build review (linker/startup/build)")

    report, out_path = run_substeps(
        session,
        "embedded-build-review",
        [
            ("linker", step_review_linker),
            ("startup", step_review_startup),
            ("build", step_review_build),
        ],
        summary_prefix="embedded-build",
    )
    log.info("embedded-build merged status: %s", report.get("status"))
    return out_path
