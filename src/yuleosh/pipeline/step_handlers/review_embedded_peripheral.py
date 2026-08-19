#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): review-embedded-peripheral — 合并 bsp + power + mmio 专项审查。

2026-08-19 老板八轮拍板（checkpoint v9）: 外设领域专项合并组。本 handler
内部顺序调用:
  - step_review_bsp    (BSP 板级支持包验证, review_bsp/core.py)
  - step_review_power  (低功耗审查)
  - step_review_mmio   (MMIO 配置审查)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 embedded-peripheral-review.json（sections: bsp/power/mmio）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_embedded_peripheral")

__all__ = ["step_review_embedded_peripheral"]


@timed_step
def step_review_embedded_peripheral(session: PipelineSession) -> str:
    """Step: embedded-peripheral 组 — bsp + power + mmio 专项审查（合并）。"""
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review_bsp import step_review_bsp
    from yuleosh.pipeline.step_handlers.review_mmio import step_review_mmio
    from yuleosh.pipeline.step_handlers.review_power import step_review_power

    print("  🔌 [embedded-peripheral] BSP → 低功耗 → MMIO 专项审查（合并）...")
    log.info("Running merged embedded-peripheral review (bsp/power/mmio)")

    report, out_path = run_substeps(
        session,
        "embedded-peripheral-review",
        [
            ("bsp", step_review_bsp),
            ("power", step_review_power),
            ("mmio", step_review_mmio),
        ],
        summary_prefix="embedded-peripheral",
    )
    log.info("embedded-peripheral merged status: %s", report.get("status"))
    return out_path
