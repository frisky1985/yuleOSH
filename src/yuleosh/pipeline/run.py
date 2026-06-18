#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Engine — re-export shim.

This module provides backward-compatible imports for all symbols that were
historically defined in this module.  All real logic lives in the
sub-modules listed below.

Usage (backward-compatible)::

    from yuleosh.pipeline.run import PipelineSession, run_pipeline,
        step_spec_check, ...
"""

import subprocess  # kept for mock.patch("yuleosh.pipeline.run.subprocess.run") compatibility

# Session types
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

# Orchestrator entry points
from yuleosh.pipeline.orchestrator import run_pipeline, status_pipeline, main

# Step handler functions + pipeline definition
from yuleosh.pipeline.step_handlers import (
    step_spec_check,
    step_super_analysis,
    step_hermes_prd,
    step_internal_review,
    step_claude_arch,
    step_claude_dev,
    step_test_planning,
    step_claude_test,
    step_review_arch,
    step_review_code,
    step_review_selftest,
    step_review_prd,
    step_review_misra_ci,
    step_review_test_coverage,
    step_integration_test,
    step_test_qualification,
    step_c_unit_test,
    step_hermes_review,
    step_final_report,
    step_review_devplan,
    step_review_linker,
    step_review_startup,
    step_review_rtos,
    step_review_memory,
    PIPELINE_STEPS,
    _check_llm_key,
    _resolve_handler,
)

# Stages helpers (spec parsing, etc.)
from yuleosh.pipeline.stages import (
    _parse_spec,
    _parse_requirements,
    _parse_scenarios,
    _try_parse_hermes_json,
    _get_spec_mtime,
)

# LLM client — re-exported for test mock compatibility
from yuleosh.llm.client import chat_completion

# _call_llm is imported from stages, which looks up chat_completion
# from run at call time for test mock compatibility.
from yuleosh.pipeline.stages import _call_llm

# ------------------------------------------------------------------
# Backward-compatible module attributes for test mock paths
# Tests mock yuleosh.pipeline.run._store / _notify  (old monolithic locations)
# ------------------------------------------------------------------
_store = None
_notify = None

__all__ = [
    "PipelineSession",
    "PipelineStepError",
    "run_pipeline",
    "status_pipeline",
    "main",
    "PIPELINE_STEPS",
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
    "step_test_qualification",
    "step_c_unit_test",
    "step_review_devplan",
    "step_review_linker",
    "step_review_startup",
    "step_review_rtos",
    "step_review_memory",
    "step_review_arch",
    "step_review_code",
    "step_review_selftest",
    "step_review_prd",
    "step_review_misra_ci",
    "step_review_test_coverage",
    "step_integration_test",
    "_call_llm",
    "_parse_spec",
    "_parse_requirements",
    "_parse_scenarios",
    "_try_parse_hermes_json",
    "_get_spec_mtime",
    "_check_llm_key",
    "chat_completion",
    "_store",
    "_notify",
]
