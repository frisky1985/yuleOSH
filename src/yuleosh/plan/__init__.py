#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — yuleOSH plan generation subsystem.

Plan Agent enables structured plan generation from natural-language
task descriptions.  It gathers project context (directory structure,
knowledge graph, pipeline capabilities), generates a step-by-step
implementation plan with agent assignments and effort estimates,
and produces Markdown / JSON / CheckpointEngine-compatible output.

Usage::

    from yuleosh.plan import PlanAgent, Plan, PlanStep

    agent = PlanAgent()
    plan = agent.plan("为 BCM Demo 增加 HIL 测试支持")
    print(agent.to_markdown(plan))
    pipeline_steps = agent.to_pipeline(plan)
"""

from yuleosh.plan.agent import PlanAgent, generate_plan
from yuleosh.plan.context import PlanContext, default_context
from yuleosh.plan.models import Plan, PlanStep, PlanStatus, AGENT_MAP
from yuleosh.plan.generator import PlanGenerator
from yuleosh.plan.output import to_markdown, to_json, to_pipeline_steps

__all__ = [
    # Main entry point
    "PlanAgent",
    "generate_plan",
    # Data models
    "Plan",
    "PlanStep",
    "PlanStatus",
    "AGENT_MAP",
    # Context
    "PlanContext",
    "default_context",
    # Generator
    "PlanGenerator",
    # Output
    "to_markdown",
    "to_json",
    "to_pipeline_steps",
]
