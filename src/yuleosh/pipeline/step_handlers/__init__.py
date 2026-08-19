#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Step Handlers package.

Re-exports all step handler functions from sub-modules, plus the
pipeline step registry (PIPELINE_STEPS), handler resolution, and
LLM key check.

Import paths preserved:
  from yuleosh.pipeline.step_handlers import step_spec_check  (works)
  from yuleosh.pipeline.step_handlers import PIPELINE_STEPS    (works)
  from yuleosh.pipeline.step_handlers import _check_llm_key    (works)

24 子步骤执行层 + 10 Gate 编排层（2026-08-19 老板八轮拍板, checkpoint v9）:
  - 执行层 PIPELINE_STEPS = 24 个子步骤（合并后）; checkpoint/resume /
    step_cache / --from-step 全按 24 步
  - 编排层 GATES（yuleosh.pipeline.gates）: 10 Gate 对外稳定契约,
    gate status = 内部子步骤最差状态; 报告聚合 gate-summary.json
"""

from yuleosh.pipeline.step_handlers.spec import step_spec_check
from yuleosh.pipeline.step_handlers.analysis import (
    step_super_analysis,
    step_hermes_prd,
    step_internal_review,
)
from yuleosh.pipeline.step_handlers.execution import (
    step_claude_arch,
    step_claude_dev,
    step_codegen_deploy,
    step_test_planning,
    step_claude_test,
)
from yuleosh.pipeline.step_handlers.external_agents import (
    step_codex_verify,
    step_claude_review,
)
from yuleosh.pipeline.step_handlers.review import (
    step_hermes_review,
    step_final_report,
)
from yuleosh.pipeline.step_handlers.review_prd import step_review_prd
from yuleosh.pipeline.step_handlers.review_misra_ci import step_review_misra_ci
from yuleosh.pipeline.step_handlers.review_test_coverage import step_review_test_coverage
from yuleosh.pipeline.step_handlers.review_arch import step_review_arch
from yuleosh.pipeline.step_handlers.review_code import step_review_code
from yuleosh.pipeline.step_handlers.review_selftest import step_review_selftest
from yuleosh.pipeline.step_handlers.test_integration import step_integration_test
from yuleosh.pipeline.step_handlers.test_qualification import step_test_qualification
from yuleosh.pipeline.step_handlers.test_c_unit import step_c_unit_test
from yuleosh.pipeline.step_handlers.review_development import step_review_development
from yuleosh.pipeline.step_handlers.review_linker import step_review_linker
from yuleosh.pipeline.step_handlers.review_startup import step_review_startup
from yuleosh.pipeline.step_handlers.review_rtos import step_review_rtos
from yuleosh.pipeline.step_handlers.review_memory import step_review_memory
from yuleosh.pipeline.step_handlers.review_bsp import step_review_bsp  # noqa: F401
from yuleosh.pipeline.step_handlers.review_build import step_review_build  # noqa: F401
from yuleosh.pipeline.step_handlers.review_power import step_review_power  # noqa: F401
from yuleosh.pipeline.step_handlers.review_stack import step_review_stack
from yuleosh.pipeline.step_handlers.review_mmio import step_review_mmio
from yuleosh.pipeline.step_handlers.review_critical_safety import step_review_critical_safety
# 2026-08-19 第八轮新增 4 专项（并入 code-review 超集组, 不注册为独立步骤）
from yuleosh.pipeline.step_handlers.review_interrupt import step_review_interrupt
from yuleosh.pipeline.step_handlers.review_nvm import step_review_nvm
from yuleosh.pipeline.step_handlers.review_watchdog import step_review_watchdog
from yuleosh.pipeline.step_handlers.review_timing import step_review_timing
# 2026-08-19 八轮决策: 合并 handler（PIPELINE_STEPS 引用, 旧 handler 保留不删）
from yuleosh.pipeline.step_handlers.verify_loop import step_verify_loop
from yuleosh.pipeline.step_handlers.code_review_unified import step_code_review_unified
from yuleosh.pipeline.step_handlers.review_embedded_build import step_review_embedded_build
from yuleosh.pipeline.step_handlers.review_embedded_runtime import step_review_embedded_runtime
from yuleosh.pipeline.step_handlers.review_embedded_peripheral import step_review_embedded_peripheral
from yuleosh.pipeline.step_handlers.review_embedded_realtime import step_review_embedded_realtime
from yuleosh.pipeline.step_handlers.qemu_verify import step_qemu_verify

# QEMU firmware emulation test (L2)
from yuleosh.pipeline.step_handlers.test_qemu import QemuTestHandler

# C coverage gate check (L2)
from yuleosh.pipeline.step_handlers.c_coverage_gate import coverage_gate_step

# Fault Injection testing (SWE.5 / SWE.6)
from yuleosh.pipeline.step_handlers.fault_inject import step_fault_injection

# KG Merge Gate (KG-42) — 第九轮: 扩展为 CM Gate（小仓）
from yuleosh.knowledge_graph.merge_gate import step_merge_gate

from yuleosh.pipeline.stages import _check_llm_key

# 编排层 10 Gate（方案 B, 2026-08-19）
from yuleosh.pipeline.gates import GATES, write_gate_summary, validate_gates_contract


# Lazy import for step class registry
# Sprint 3 eliminated the dual-path; always use legacy step functions
_have_step_classes = False


__all__ = [
    "step_spec_check",
    "step_super_analysis",
    "step_hermes_prd",
    "step_internal_review",
    "step_claude_arch",
    "step_claude_dev",
    "step_test_planning",
    "step_claude_test",
    "step_codex_verify",
    "step_claude_review",
    "step_review_arch",
    "step_review_code",
    "step_review_selftest",
    "step_integration_test",
    "step_hermes_review",
    "step_final_report",
    "step_review_prd",
    "step_review_misra_ci",
    "step_review_development",
    "step_review_test_coverage",
    "step_review_linker",
    "step_review_startup",
    "step_review_rtos",
    "step_review_memory",
    "step_review_stack",
    "step_review_mmio",
    "step_review_critical_safety",
    "step_review_interrupt",
    "step_review_nvm",
    "step_review_watchdog",
    "step_review_timing",
    "step_verify_loop",
    "step_code_review_unified",
    "step_review_embedded_build",
    "step_review_embedded_runtime",
    "step_review_embedded_peripheral",
    "step_review_embedded_realtime",
    "step_qemu_verify",
    "step_fault_injection",
    "step_merge_gate",
    "step_test_qualification",
    "step_c_unit_test",
    "QemuTestHandler",
    "qemu_run",
    "coverage_gate_step",
    "PIPELINE_STEPS",
    "GATES",
    "write_gate_summary",
    "validate_gates_contract",
    "_check_llm_key",
    "_resolve_handler",
]


def _resolve_handler(step_key: str, legacy_fn) -> callable:
    """Return the legacy step function (Sprint 3 eliminated the dual-path)."""
    return legacy_fn


# Create handler instances for pipeline step registration
qemu_run = QemuTestHandler()


# ═══════════════════════════════════════════════════════════════
# yuleOSH Pipeline — ASPICE V-Model 对齐（24 子步骤执行层）
#
# 2026-08-19 老板八轮拍板（checkpoint v9）: 合理下限合并，不牺牲能力。
# 36 → 24 步；旧 handler 文件保留不删（子逻辑复用）；外部 agent 独立
# 超时/重试保留（verify-loop 内部 codex-verify 仍独立调用）；
# P0 门禁（review-critical-safety）独立步骤；--from-step 按 24 步编号。
#
# 编排层 10 Gate 视图见 yuleosh.pipeline.gates.GATES（对外稳定契约）。
# ═══════════════════════════════════════════════════════════════
PIPELINE_STEPS = [
    # ── G1 SWE.1 Requirements ──────────────────────────────
    ("spec-check", "小明", "OpenSpec 合规检查", step_spec_check),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析",
     _resolve_handler("super-analysis", step_super_analysis)),
    ("prd", "Hermes", "产品需求分析",
     _resolve_handler("prd", step_hermes_prd)),
    ("prd-review", "小马", "PRD 质量审查",
     _resolve_handler("prd-review", step_review_prd)),

    # ── G2 SWE.2 Architecture Design ───────────────────────
    ("architecture", "Claude", "架构设计",
     _resolve_handler("architecture", step_claude_arch)),
    ("arch-review", "小克", "架构审查", step_review_arch),

    # ── G3 SWE.3 Detailed Design & Code ────────────────────
    ("development", "Claude", "开发计划与代码实现",
     _resolve_handler("development", step_claude_dev)),
    ("development-review", "小克", "开发产物审查", step_review_development),
    ("codegen-deploy", "小明", "代码产物部署",
     step_codegen_deploy),
    ("internal-code-review", "小克", "代码实现预审", step_review_code),

    # ── G4 方案评审（外部 agent）───────────────────────────
    # 2026-08-19 三轮决策: claude-review 提前到 test-planning 前 —
    # 方案评审应在测试规划前完成（评审结论注入 test-planning prompt）
    ("claude-review", "Claude", "Claude 方案评审 (外部 agent)", step_claude_review),

    # ── G5 测试规划 ────────────────────────────────────────
    # 挪后: 读 claude-review 结论（blockers/suggestions 注入 prompt）
    ("test-planning", "Claude", "测试规划",
     _resolve_handler("test-planning", step_test_planning)),

    # ── G6 SWE.4 Unit Testing ──────────────────────────────
    # verify-loop = 合并 self-test + codex-verify + self-test-review
    # （内部顺序调用旧 handler, 任一 failed → failed）
    ("verify-loop", "小克", "自测 + Codex 验证 + 自测审查 (合并)", step_verify_loop),
    ("c-unit-test", "小克", "C 单元测试 (Unity)", step_c_unit_test),

    # ── G7 SWE.5 Integration Testing ───────────────────────
    # code-review 超集 = 集成审查 + 4 嵌入式专项组（build/runtime/peripheral/realtime）
    ("code-review", "小克", "集成代码审查 + 嵌入式专项 (合并超集)",
     step_code_review_unified),
    # misra-review 前置（测试前评估，避免测试白跑）
    ("misra-review", "小马", "MISRA 合规审查",
     _resolve_handler("misra-review", step_review_misra_ci)),
    ("integration-test", "小克", "接口集成测试", step_integration_test),
    # qemu-verify = 合并 qemu-run + c-coverage-gate
    ("qemu-verify", "小克", "QEMU 仿真 + 覆盖率门禁 (合并)", step_qemu_verify),
    # coverage-review 保持测试后（依赖覆盖率数据）
    ("coverage-review", "小马", "测试覆盖审查",
     _resolve_handler("coverage-review", step_review_test_coverage)),

    # ── G8 安全门禁 ────────────────────────────────────────
    # ⛔ P0 CRITICAL GATE: 确定性 cppcheck 非 LLM，保留独立阻断
    ("review-critical-safety", "小明", "关键安全异常阻塞检查 (P0 GATE)",
     step_review_critical_safety),
    ("fault-injection", "小克", "故障注入测试 (SWE.5/SWE.6)", step_fault_injection),

    # ── G9 合并门禁（CM Gate, 小仓）────────────────────────
    # 第九轮决策 (2026-08-19): merge-gate 扩展为 CM Gate — KG 图一致性/
    # 置信度检查 + 4 项确定性 CM 检查（工作区/提交规范/产物泄漏/部署护栏）
    ("merge-gate", "小仓", "CM Gate — KG 一致性 + 仓库管理检查", step_merge_gate),

    # ── G10 SWE.6 Qualification Testing ────────────────────
    ("test-qualification", "小明", "合格性测试", step_test_qualification),
    ("final-report", "小明", "最终报告", step_final_report),
]


def _step_keys() -> list[str]:
    """Return the ordered step keys of PIPELINE_STEPS."""
    return [s[0] for s in PIPELINE_STEPS]
