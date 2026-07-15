#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Step Handlers package.

Re-exports all step handler functions from sub-modules, plus the
pipeline step registry (PIPELINE_STEPS), handler resolution, and
LLM key check.

Import paths preserved:
  from yuleosh.pipeline.step_handlers import step_spec_check  (works)
  from yuleosh.pipeline.step_handlers import PIPELINE_STEPS    (works)
  from yuleosh.pipeline.step_handlers import _check_llm_key    (works)
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
    step_test_planning,
    step_claude_test,
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
from yuleosh.pipeline.step_handlers.review_devplan import step_review_devplan
from yuleosh.pipeline.step_handlers.review_linker import step_review_linker
from yuleosh.pipeline.step_handlers.review_startup import step_review_startup
from yuleosh.pipeline.step_handlers.review_rtos import step_review_rtos
from yuleosh.pipeline.step_handlers.review_memory import step_review_memory
from yuleosh.pipeline.step_handlers.review_bsp import step_review_bsp
from yuleosh.pipeline.step_handlers.review_build import step_review_build
from yuleosh.pipeline.step_handlers.review_power import step_review_power
from yuleosh.pipeline.step_handlers.review_stack import step_review_stack
from yuleosh.pipeline.step_handlers.review_mmio import step_review_mmio
from yuleosh.pipeline.step_handlers.review_critical_safety import step_review_critical_safety

# Fault Injection testing (SWE.5 / SWE.6)
from yuleosh.pipeline.step_handlers.fault_inject import step_fault_injection

from yuleosh.pipeline.stages import _check_llm_key


# Lazy import for step class registry
# Sprint 3 eliminated the dual-path; always use legacy step functions
_have_step_classes = False

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
    "step_review_arch",
    "step_review_code",
    "step_review_selftest",
    "step_integration_test",
    "step_hermes_review",
    "step_final_report",
    "step_review_prd",
    "step_review_misra_ci",
    "step_review_devplan",
    "step_review_test_coverage",
    "step_review_linker",
    "step_review_startup",
    "step_review_rtos",
    "step_review_memory",
    "step_review_stack",
    "step_review_mmio",
    "step_review_critical_safety",
    "step_fault_injection",
    "step_test_qualification",
    "step_c_unit_test",
    "PIPELINE_STEPS",
    "_check_llm_key",
    "_resolve_handler",
]


def _resolve_handler(step_key: str, legacy_fn) -> callable:
    """Return the legacy step function (Sprint 3 eliminated the dual-path)."""
    return legacy_fn


# ═══════════════════════════════════════════════════════════════
# yuleOSH Pipeline — ASPICE V-Model 对齐
#
# Left side (specification):      Steps 1-9    SWE.1→SWE.3
# Bottom (implementation):        Steps 10-11
# Right side (verification):      Steps 12-17  SWE.4→SWE.6
#
# Each left-side stage has a corresponding review step on the right
# ═══════════════════════════════════════════════════════════════
PIPELINE_STEPS = [
    # ── Left side: SWE.1 Requirements ────────────────
    ("spec-check", "小明", "OpenSpec 合规检查", step_spec_check),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析",
     _resolve_handler("super-analysis", step_super_analysis)),
    ("prd", "Hermes", "产品需求分析",
     _resolve_handler("prd", step_hermes_prd)),
    ("prd-review", "小马", "PRD 质量审查",
     _resolve_handler("prd-review", step_review_prd)),

    # ── Left side: SWE.2 Architecture Design ─────────
    ("architecture", "Claude", "架构设计",
     _resolve_handler("architecture", step_claude_arch)),
    ("arch-review", "小克", "架构审查", step_review_arch),

    # ── Left side: SWE.3 Detailed Design & Code ─────
    ("development", "Claude", "开发计划与代码实现",
     _resolve_handler("development", step_claude_dev)),
    ("devplan-review", "小克", "开发计划审查", step_review_devplan),

    # ── Bottom: Code Pre-Review ─────────────────────
    ("internal-code-review", "小克", "代码实现预审", step_review_code),
    ("test-planning", "Claude", "测试规划",
     _resolve_handler("test-planning", step_test_planning)),

    # ── Right side: SWE.4 Unit Testing ──────────────
    ("self-test", "Claude", "自测验证", step_claude_test),
    ("self-test-review", "小克", "自测结果审查", step_review_selftest),
    ("c-unit-test", "小克", "C 单元测试 (Unity)", step_c_unit_test),

    # ── Right side: SWE.5 Integration Testing ───────
    ("integration-test", "小克", "接口集成测试", step_integration_test),
    ("code-review", "Hermes", "集成代码审查",
     _resolve_handler("code-review", step_hermes_review)),
    ("misra-review", "小马", "MISRA 合规审查",
     _resolve_handler("misra-review", step_review_misra_ci)),
    ("coverage-review", "小马", "测试覆盖审查",
     _resolve_handler("coverage-review", step_review_test_coverage)),

    # ── Embedded review steps (SWE.5) ────────────────
    ("review-linker", "小克", "链接脚本审查", step_review_linker),
    ("review-startup", "小克", "启动代码审查", step_review_startup),
    ("review-rtos", "小克", "RTOS 配置审查", step_review_rtos),
    ("review-memory", "小克", "内存安全审查", step_review_memory),

    # ── P2: Embedded Special Focus ─────────────────
    ("review-bsp", "小克", "BSP 板级支持包验证", step_review_bsp),
    ("review-build", "小克", "编译输出验证", step_review_build),
    ("review-power", "小克", "低功耗审查", step_review_power),
    ("review-stack", "小克", "堆栈使用分析 (P0/DEF-007)", step_review_stack),
    ("review-mmio", "小克", "MMIO 配置审查 (P0/DEF-008)", step_review_mmio),

    # ── ⛔ P0 CRITICAL GATE: 关键安全异常阻塞检查 ──────
    ("review-critical-safety", "小明", "关键安全异常阻塞检查 (P0 GATE)", step_review_critical_safety),


    # ── SWE.5 / SWE.6: Fault Injection Testing ────
    ("fault-injection", "小克", "故障注入测试 (SWE.5/SWE.6)", step_fault_injection),

    # ── Right side: SWE.6 Qualification Testing ─────
    ("test-qualification", "小明", "合格性测试", step_test_qualification),
    ("final-report", "小明", "最终报告", step_final_report),
]
