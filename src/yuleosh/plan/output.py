#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — output formatting.

Renders a Plan as:
  - Markdown (CLI-friendly with ANSI terminal markers)
  - JSON (programmatic consumption)
  - CheckpointEngine-compatible step definitions

CLI output example::

    $ yuleosh plan "为 BCM Demo 增加 HIL 测试支持"

    📋 Ultra-Plan: BCM Demo HIL 测试支持
    ══════════════════════════════════════
    ...
"""

from __future__ import annotations

import json
import logging
import shutil
from typing import Optional

from yuleosh.plan.models import Plan, PlanStep, PlanStatus, AGENT_MAP

log = logging.getLogger("yuleosh.plan.output")

# ── ANSI color constants ────────────────────────────────────────────────

_BOLD = "\033[1m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RED = "\033[91m"
_MAGENTA = "\033[95m"
_RESET = "\033[0m"
_DIM = "\033[2m"

_STATUS_ICONS = {
    PlanStatus.DRAFT: "📋",
    PlanStatus.REVIEW: "🔍",
    PlanStatus.APPROVED: "✅",
    PlanStatus.EXECUTING: "⚡",
    PlanStatus.DONE: "🏁",
    PlanStatus.CANCELLED: "🚫",
}


def _term_width() -> int:
    """Return terminal width or default 80."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


# ── Markdown rendering ─────────────────────────────────────────────────

def to_markdown(plan: Plan, with_ansi: bool = False) -> str:
    """Render a Plan as structured Markdown.

    Args:
        plan:         The Plan to render.
        with_ansi:    If True, embed ANSI escape codes for CLI display.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────────────
    status_icon = _STATUS_ICONS.get(plan.status, "📋")
    title = plan.title
    if with_ansi:
        lines.append(f"\n{_BOLD}{status_icon} Ultra-Plan: {title}{_RESET}")
        sep = "═" * min(len(title) + 14, _term_width() - 4)
        lines.append(f"{_CYAN}{sep}{_RESET}\n")
    else:
        lines.append(f"# {status_icon} Ultra-Plan: {title}\n")

    # ── Metadata ────────────────────────────────────────────────────
    lines.append(f"**目标**: {plan.objective}\n")
    if plan.background:
        lines.append(f"**背景**: {plan.background}\n")
    lines.append(f"**状态**: {plan.status} ({plan.generated_at})\n")

    # ── Technical approach ──────────────────────────────────────────
    if plan.technical_approach:
        lines.append("## 技术方案\n")
        lines.append(f"{plan.technical_approach}\n")

    # ── Steps ───────────────────────────────────────────────────────
    lines.append("## 实施步骤\n")
    for i, step in enumerate(plan.steps, 1):
        dep_str = f"  依赖: [{', '.join(step.depends_on)}]" if step.depends_on else "  依赖: -"
        pipeline_str = ""
        if step.pipeline_step:
            pipeline_str = f"  流水线: {step.pipeline_step}"

        if with_ansi:
            lines.append(
                f"  [{i}] {_GREEN}{step.agent}{_RESET}  "
                f"{_BOLD}{step.name}{_RESET}  "
                f"{_YELLOW}{step.effort_hours}h{_RESET}"
            )
            lines.append(f"       {_DIM}{step.description}{_RESET}")
            lines.append(f"       {dep_str}")
            if step.verification:
                lines.append(f"       ✅ 验证: {step.verification}")
            if pipeline_str:
                lines.append(f"       🔗 {pipeline_str}")
        else:
            lines.append(f"  [{i}] **{step.agent}**  {step.name}  ({step.effort_hours}h)")
            lines.append(f"       {step.description}")
            lines.append(f"       {dep_str}")
            if step.verification:
                lines.append(f"       ✅ 验证: {step.verification}")
            if pipeline_str:
                lines.append(f"       🔗 流水线: {pipeline_str}")
        lines.append("")

    # ── Summary bar ─────────────────────────────────────────────────
    total_h = plan.total_effort_hours
    n_steps = len(plan.steps)
    n_agents = plan.agent_count
    if with_ansi:
        sep = "─" * min(48, _term_width() - 4)
        lines.append(f"  {_DIM}{sep}{_RESET}")
        lines.append(
            f"  总计: ~{total_h:.1f}h | {n_steps} 步骤 | "
            f"{n_agents} agents{_RESET}"
        )
    else:
        lines.append("  " + "─" * 48)
        lines.append(f"  总计: ~{total_h:.1f}h | {n_steps} 步骤 | {n_agents} agents")

    # Agent breakdown
    breakdown = plan.agent_breakdown
    if breakdown:
        agents_str = " | ".join(
            f"{agent}: {h:.1f}h" for agent, h in sorted(breakdown.items())
        )
        if with_ansi:
            lines.append(f"  {_DIM}按 agent: {agents_str}{_RESET}")
        else:
            lines.append(f"  按 agent: {agents_str}")
    lines.append("")

    # ── Risks ───────────────────────────────────────────────────────
    if plan.risks:
        lines.append("## 风险\n")
        for r in plan.risks:
            lines.append(f"  - ⚠️  {r}")
        lines.append("")

    # ── Prerequisites ──────────────────────────────────────────────
    if plan.prerequisites:
        lines.append("## 前置条件\n")
        for p in plan.prerequisites:
            lines.append(f"  - 🔧 {p}")
        lines.append("")

    # ── Footer / CLI hint ──────────────────────────────────────────
    if with_ansi:
        lines.append(f"{_DIM}yuleosh plan --apply  # 确认执行{_RESET}\n")
    else:
        lines.append("```\nyuleosh plan --apply  # 确认执行\n```\n")

    return "\n".join(lines)


# ── JSON rendering ──────────────────────────────────────────────────────

def to_json(plan: Plan, **kwargs) -> str:
    """Render a Plan as a JSON string.

    Args:
        plan:      The Plan to serialize.
        **kwargs:  Extra kwargs for json.dumps (indent, ensure_ascii, etc.)

    Returns:
        JSON string.
    """
    opts = {"indent": 2, "ensure_ascii": False, "default": str}
    opts.update(kwargs)
    return json.dumps(plan.to_dict(), **opts)


# ── Pipeline conversion ────────────────────────────────────────────────

def to_pipeline_steps(plan: Plan) -> list[dict]:
    """Convert Plan steps to CheckpointEngine-compatible step definitions.

    Each PlanStep optionally maps to a PIPELINE_STEPS entry via the
    ``pipeline_step`` field.  Steps without a pipeline mapping are
    synthesised as generic user-defined steps.

    Returns:
        List of dicts matching CheckpointEngine step format::

            {"step_id": ..., "agent": ..., "action": ..., "description": ...}
    """
    result: list[dict] = []
    for step in plan.steps:
        entry = {
            "step_id": step.step_id,
            "agent": step.agent,
            "action": step.name,
            "description": step.description,
            "verification": step.verification,
            "effort_hours": step.effort_hours,
            "depends_on": list(step.depends_on),
        }
        if step.pipeline_step:
            entry["pipeline_step"] = step.pipeline_step
        result.append(entry)
    return result


# ── CLI preview format ─────────────────────────────────────────────────

def to_cli_output(plan: Plan) -> str:
    """Render a Plan for CLI display (ANSI-colored)."""
    return to_markdown(plan, with_ansi=True)
