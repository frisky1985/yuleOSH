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
from yuleosh.pipeline.step_handlers.review_devplan import step_review_devplan
from yuleosh.pipeline.stages import _check_llm_key

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

    # ── Right side: SWE.5 Integration Testing ───────
    ("integration-test", "小克", "接口集成测试", step_integration_test),
    ("code-review", "Hermes", "集成代码审查",
     _resolve_handler("code-review", step_hermes_review)),
    ("misra-review", "小马", "MISRA 合规审查",
     _resolve_handler("misra-review", step_review_misra_ci)),
    ("coverage-review", "小马", "测试覆盖审查",
     _resolve_handler("coverage-review", step_review_test_coverage)),

    # ── Right side: SWE.6 Qualification Testing ─────
    ("final-report", "小明", "最终报告", step_final_report),
]
