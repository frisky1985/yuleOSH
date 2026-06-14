#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Engine — backward-compatible re-exports.

This module re-exports all public symbols from the split modules
(session, stages, orchestrator, steps) so that existing imports
like ``from yuleosh.pipeline.run import run_pipeline`` continue
to work without modification.
"""

# Orchestrator — entry points
from yuleosh.pipeline.orchestrator import run_pipeline, status_pipeline, main

# Session — state and exceptions
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

# Stages — step definitions and helpers
from yuleosh.pipeline.stages import (
    PIPELINE_STEPS,
    _get_spec_mtime,
    _parse_spec,
    _parse_requirements,
    _parse_scenarios,
    _call_llm,
    _check_llm_key,
    _try_parse_hermes_json,
    timed_step,
)

# Steps — PipelineStep classes
from yuleosh.pipeline.steps import PipelineStep

__all__ = [
    "PipelineSession",
    "PipelineStep",
    "PipelineStepError",
    "PIPELINE_STEPS",
    "run_pipeline",
    "status_pipeline",
    "main",
    "_get_spec_mtime",
    "_parse_spec",
    "_parse_requirements",
    "_parse_scenarios",
    "_call_llm",
    "_check_llm_key",
    "timed_step",
]
