#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5): qemu-verify — 合并 qemu-run + c-coverage-gate。

2026-08-19 老板八轮拍板（checkpoint v9）: qemu 仿真测试 + C 覆盖率门禁
合并为一个步骤（内部顺序执行, 保留各自阻断语义）。本 handler 内部调用:
  - qemu_run = QemuTestHandler() 实例 (qemu-run, 无 .elf 自动 skip)
  - coverage_gate_step            (c-coverage-gate, 覆盖率不达标阻断)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped。
输出 qemu-verify.json（sections: qemu-run/c-coverage-gate）。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.qemu_verify")

__all__ = ["step_qemu_verify"]


@timed_step
def step_qemu_verify(session: PipelineSession) -> str:
    """Step: qemu-verify — QEMU 仿真测试 + C 覆盖率门禁（合并）。"""
    from yuleosh.pipeline.step_handlers.c_coverage_gate import coverage_gate_step
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler

    # 实例化与 __init__.py 模块级 qemu_run 等价的 handler（避免循环导入）
    qemu_handler = QemuTestHandler()

    print("  🖥️  [qemu-verify] QEMU 仿真 → 覆盖率门禁（合并步骤）...")
    log.info("Running merged qemu-verify (qemu-run → c-coverage-gate)")

    report, out_path = run_substeps(
        session,
        "qemu-verify",
        [
            ("qemu-run", qemu_handler),
            ("c-coverage-gate", coverage_gate_step),
        ],
        summary_prefix="qemu-verify",
    )
    log.info("qemu-verify merged status: %s", report.get("status"))
    print(f"  {'✅' if report['status'] == 'passed' else '❌'} [qemu-verify] "
          f"合并状态: {report['status']} → {out_path}")
    return out_path
