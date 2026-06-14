#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
OSH Pipeline Engine — Agent orchestration pipeline.

Modules:
  orchestrator — run_pipeline, status_pipeline, main
  session      — PipelineSession, PipelineStepError
  stages       — step handler functions, helpers, PIPELINE_STEPS
  steps        — PipelineStep base class and subclasses
  run          — backward-compatible re-exports (original module name)
  prompts      — LLM prompt builders
  async_runner — async execution support
"""
