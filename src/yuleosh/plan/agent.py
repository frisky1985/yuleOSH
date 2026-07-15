#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — main entry point.

PlanAgent orchestrates context gathering, plan generation, and
output formatting.  This is the primary class consumers import.

Usage::

    from yuleosh.plan import PlanAgent

    agent = PlanAgent(project_dir=".")
    plan = agent.plan("为 BCM Demo 增加 HIL 测试支持")

    # Render outputs
    print(agent.to_markdown(plan))
    print(agent.to_json(plan))
    pipeline_steps = agent.to_pipeline(plan)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from yuleosh.plan.context import PlanContext
from yuleosh.plan.generator import PlanGenerator
from yuleosh.plan.models import Plan, PlanStep, PlanStatus
from yuleosh.plan.output import (
    to_markdown,
    to_json,
    to_pipeline_steps,
    to_cli_output,
)

log = logging.getLogger("yuleosh.plan.agent")


class PlanAgent:
    """Ultra-Plan Agent — generate structured plans from task descriptions.

    Typical workflow::

        agent = PlanAgent()
        plan = agent.plan("Add HIL test support for BCM Demo")
        agent.to_markdown(plan)      # → CLI-friendly Markdown
        agent.to_json(plan)           # → JSON string
        agent.to_pipeline(plan)       # → pipeline step definitions

    Args:
        project_dir:  Project root directory (default: CWD).
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self.context = PlanContext(str(self.project_dir))
        self.generator = PlanGenerator()

    # ── Core API ─────────────────────────────────────────────────────

    def plan(self, task: str) -> Plan:
        """Generate a structured Plan from a natural-language task.

        Gathers project context, KG data, and pipeline capabilities,
        then delegates to PlanGenerator.

        Args:
            task:  User's task description in natural language.

        Returns:
            A Plan instance (status=PlanStatus.DRAFT).
        """
        log.info("Generating plan for: %s", task[:80])

        # Gather all context in parallel
        project_summary = self.context.get_project_summary()
        kg_summary = self.context.get_kg_summary()
        pipeline_caps = self.context.get_pipeline_capabilities()
        existing_reqs = self.context.get_existing_requirements()

        merged_context = {
            "project_summary": project_summary,
            "kg": kg_summary,
            "pipeline_caps": pipeline_caps,
            "existing_requirements": existing_reqs,
        }

        plan = self.generator.generate(task, context=merged_context)
        log.info(
            "Plan generated: %s (%d steps, %.1f hours)",
            plan.title,
            len(plan.steps),
            plan.total_effort_hours,
        )

        return plan

    # ── Output helpers ───────────────────────────────────────────────

    def to_markdown(self, plan: Plan) -> str:
        """Render a Plan as Markdown (CLI-friendly)."""
        return to_markdown(plan, with_ansi=False)

    def to_json(self, plan: Plan) -> str:
        """Render a Plan as a JSON string."""
        return to_json(plan)

    def to_pipeline(self, plan: Plan) -> list[dict]:
        """Convert Plan steps to CheckpointEngine-compatible format.

        Returns a list of step definitions suitable for feeding
        into the PipelineSession or CheckpointEngine.
        """
        return to_pipeline_steps(plan)

    # ── Convenience ──────────────────────────────────────────────────

    def save(self, plan: Plan, path: str | Path) -> None:
        """Save a Plan as JSON to disk.

        Args:
            plan:  The Plan to persist.
            path:  Filesystem path for the output JSON file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(plan), encoding="utf-8")
        log.info("Plan saved to: %s", path)

    def save_markdown(self, plan: Plan, path: str | Path) -> None:
        """Save a Plan as Markdown to disk.

        Args:
            plan:  The Plan to persist.
            path:  Filesystem path for the output Markdown file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(plan), encoding="utf-8")
        log.info("Plan saved to: %s", path)

    # ── Status transitions ───────────────────────────────────────────

    def approve(self, plan: Plan) -> Plan:
        """Mark a plan as approved (ready for execution)."""
        plan.status = PlanStatus.APPROVED
        log.info("Plan '%s' approved", plan.title)
        return plan

    def start_execution(self, plan: Plan) -> Plan:
        """Mark a plan as executing."""
        plan.status = PlanStatus.EXECUTING
        log.info("Plan '%s' execution started", plan.title)
        return plan

    def complete(self, plan: Plan) -> Plan:
        """Mark a plan as done."""
        plan.status = PlanStatus.DONE
        log.info("Plan '%s' completed", plan.title)
        return plan


# ── Module-level convenience ────────────────────────────────────────────

def generate_plan(
    task: str,
    project_dir: str = ".",
    save_to: Optional[str] = None,
) -> Plan:
    """One-shot convenience: create agent, plan, optionally save, return plan.

    Args:
        task:         User task description.
        project_dir:  Project root directory.
        save_to:      Optional path to save JSON output.

    Returns:
        The generated Plan.
    """
    agent = PlanAgent(project_dir=project_dir)
    plan = agent.plan(task)
    if save_to:
        agent.save(plan, save_to)
    return plan
