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
from yuleosh.pipeline.stages import _check_llm_key

# Lazy import for step class registry
_have_step_classes = False
try:
    from yuleosh.pipeline.steps import get_step_instance  # noqa: E402
    _have_step_classes = True
except ImportError:
    pass


__all__ = [
    "step_spec_check",
    "step_super_analysis",
    "step_hermes_prd",
    "step_internal_review",
    "step_claude_arch",
    "step_claude_dev",
    "step_test_planning",
    "step_claude_test",
    "step_hermes_review",
    "step_final_report",
    "PIPELINE_STEPS",
    "_check_llm_key",
    "_resolve_handler",
]


def _resolve_handler(step_key: str, legacy_fn) -> callable:
    """Use the refactored PipelineStep class if available, else fall back."""
    if _have_step_classes:
        instance = get_step_instance(step_key)
        if instance is not None:
            return instance
    return legacy_fn


PIPELINE_STEPS = [
    ("spec-check", "小明", "OpenSpec 合规检查", step_spec_check),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析",
     _resolve_handler("super-analysis", step_super_analysis)),
    ("prd", "Hermes", "产品需求分析",
     _resolve_handler("prd", step_hermes_prd)),
    ("internal-review", "小明", "内部评审", step_internal_review),
    ("architecture", "Claude", "架构设计",
     _resolve_handler("architecture", step_claude_arch)),
    ("development", "Claude", "开发实现",
     _resolve_handler("development", step_claude_dev)),
    ("test-planning", "Claude", "测试规划",
     _resolve_handler("test-planning", step_test_planning)),
    ("self-test", "Claude", "自测验证", step_claude_test),
    ("code-review", "Hermes", "代码审查",
     _resolve_handler("code-review", step_hermes_review)),
    ("final-report", "小明", "最终报告", step_final_report),
]
