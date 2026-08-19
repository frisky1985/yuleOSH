#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): code-review-unified — 合并集成代码审查 + 4 个嵌入式专项组。

2026-08-19 老板八轮拍板（checkpoint v9）: code-review 超集 = 集成审查 +
build 组 + runtime 组(含 nvm) + peripheral 组 + realtime 组
（5 子单元 = 1 + 3 + 4 + 3 + 3 = 14 次 LLM 调用, 顺序执行可接受）。
专项检查一个不少, 仅对外显示一个步骤。

本 handler 内部顺序调用:
  - step_hermes_review            (code-review, 集成代码审查)
  - step_review_embedded_build    (linker + startup + build)
  - step_review_embedded_runtime  (rtos + memory + stack + nvm)
  - step_review_embedded_peripheral (bsp + power + mmio)
  - step_review_embedded_realtime (interrupt + timing + watchdog)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 code-review-unified.json（sections: code/embedded-build/
embedded-runtime/embedded-peripheral/embedded-realtime）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.code_review_unified")

__all__ = ["step_code_review_unified"]


@timed_step
def step_code_review_unified(session: PipelineSession) -> str:
    """Step: code-review 超集 — 集成审查 + 4 嵌入式专项组（合并）。"""
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review import step_hermes_review
    from yuleosh.pipeline.step_handlers.review_embedded_build import (
        step_review_embedded_build,
    )
    from yuleosh.pipeline.step_handlers.review_embedded_peripheral import (
        step_review_embedded_peripheral,
    )
    from yuleosh.pipeline.step_handlers.review_embedded_realtime import (
        step_review_embedded_realtime,
    )
    from yuleosh.pipeline.step_handlers.review_embedded_runtime import (
        step_review_embedded_runtime,
    )

    print("  🔮 [code-review] 集成审查 + 嵌入式专项组（合并超集）...")
    log.info("Running merged code-review unified (code + 4 embedded groups)")

    report, out_path = run_substeps(
        session,
        "code-review-unified",
        [
            ("code", step_hermes_review),
            ("embedded-build", step_review_embedded_build),
            ("embedded-runtime", step_review_embedded_runtime),
            ("embedded-peripheral", step_review_embedded_peripheral),
            ("embedded-realtime", step_review_embedded_realtime),
        ],
        summary_prefix="code-review",
    )
    log.info("code-review unified merged status: %s", report.get("status"))
    print(f"  {'✅' if report['status'] == 'passed' else '❌'} [code-review] "
          f"合并状态: {report['status']} → {out_path}")
    return out_path
