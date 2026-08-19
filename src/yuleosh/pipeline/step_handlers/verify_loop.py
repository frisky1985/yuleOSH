#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.4): verify-loop — 合并 self-test + codex-verify + self-test-review。

2026-08-19 老板八轮拍板（checkpoint v9）: 合理下限合并，不牺牲 pipeline
能力。本 handler 内部顺序调用 3 个旧 handler（各自保留专属 prompt /
检查深度 / 超时），收集子报告 status 合并:

  - step_claude_test      (self-test, 真实测试运行)
  - step_codex_verify     (codex-verify, 外部 Codex CLI 验证, 缺陷即阻断)
  - step_review_selftest  (self-test-review, 自测结果审查)

合并语义: 任一 failed → failed；任一 retry → retry；全 skipped → skipped；
否则 passed。子 handler 抛 PipelineStepError（codex-verify 缺陷）→ 记录
section failed 并 re-raise（保留原阻断语义）。

兼容性: self-test-review 依赖 ``session.artifacts[\"self-test\"]`` 发现
JUnit/coverage 产物 — 合并 handler 在 self-test 完成后显式 set_artifact
（orchestrator 只在合并步骤整体完成后才注册 artifacts，旧依赖会断）。

旧 handler 文件保留不删。输出 verify-loop.json（sections: self-test /
codex-verify / self-test-review）到 session.session_dir。
"""

import logging

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.verify_loop")

__all__ = ["step_verify_loop"]


@timed_step
def step_verify_loop(session: PipelineSession) -> str:
    """Step: verify-loop — 自测 + Codex 外部验证 + 自测结果审查（合并）。

    Returns path to verify-loop.json. Raises PipelineStepError when a
    sub-handler blocks (codex-verify defects → same hard-fail semantics).
    """
    from yuleosh.pipeline.step_handlers.execution import step_claude_test
    from yuleosh.pipeline.step_handlers.external_agents import step_codex_verify
    from yuleosh.pipeline.step_handlers.merged_step import run_substeps
    from yuleosh.pipeline.step_handlers.review_selftest import step_review_selftest

    def _self_test(session: PipelineSession) -> str:
        """Run self-test and register the artifact for self-test-review."""
        path = step_claude_test(session)
        try:
            session.set_artifact("self-test", path)
        except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
            log.warning("set_artifact('self-test') failed (non-fatal): %s", e)
        return path

    print("  🔄 [verify-loop] 自测 → Codex 验证 → 自测审查（合并步骤）...")
    log.info("Running merged verify-loop (self-test → codex-verify → self-test-review)")

    report, out_path = run_substeps(
        session,
        "verify-loop",
        [
            ("self-test", _self_test),
            ("codex-verify", step_codex_verify),
            ("self-test-review", step_review_selftest),
        ],
        summary_prefix="verify-loop",
    )
    log.info("verify-loop merged status: %s", report.get("status"))
    print(f"  {'✅' if report['status'] == 'passed' else '❌'} [verify-loop] "
          f"合并状态: {report['status']} → {out_path}")
    return out_path