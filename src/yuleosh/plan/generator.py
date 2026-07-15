#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — plan generator.

Takes a natural-language task description and project context,
then produces a structured Plan with steps, agent assignments,
estimated effort, verification criteria, risks, and prerequisites.

Rules of thumb (heuristic):
  - "test" or "coverage" keywords → add review step
  - "ASIL" or "safety" → add compliance safety gate
  - "KG" or "traceability" → add KG verification step
  - "dashboard" or "UI" → add frontend step with UX review
  - "HIL" → add hardware availability prerequisite
  - Code steps → 小克 👨‍💻
  - Review steps → 小马 🐴
  - Orchestration → 小明
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from yuleosh.plan.models import Plan, PlanStep, PlanStatus, AGENT_MAP

log = logging.getLogger("yuleosh.plan.generator")


# ── Task keyword rules ─────────────────────────────────────────────────

# Tuples of (keyword_pattern, trigger → add_step callback info)
_RULES: list[tuple[re.Pattern, dict]] = [
    (
        re.compile(r"(?:test|coverage|unit.?test|integration.?test)", re.IGNORECASE),
        {
            "step_id": "test-planning",
            "name": "测试规划",
            "description": "制定测试策略，确定测试层级 (单元/集成/HIL)",
            "agent_key": "test",
            "effort_hours": 1.5,
            "depends_on": [],
            "verification": "测试计划文档通过审查",
        },
    ),
    (
        re.compile(r"(?:ASIL|safety|functional.?safety|ISO.?26262)", re.IGNORECASE),
        {
            "step_id": "safety-gate",
            "name": "功能安全审查门",
            "description": "检查安全机制、ASIL 分解、故障覆盖率",
            "agent_key": "compliance",
            "effort_hours": 2.0,
            "depends_on": [],
            "verification": "功能安全审查通过、无 blocking 项",
        },
    ),
    (
        re.compile(r"(?:KG|knowledge.?graph|traceab)", re.IGNORECASE),
        {
            "step_id": "kg-verify",
            "name": "KG 追溯验证",
            "description": "验证 KG implements/validates 边完整性",
            "agent_key": "compliance",
            "effort_hours": 1.0,
            "depends_on": [],
            "verification": "KG coverage 报告无缺失边",
        },
    ),
    (
        re.compile(r"(?:dashboard|UI|frontend|front.?end)", re.IGNORECASE),
        {
            "step_id": "ui-dev",
            "name": "前端开发",
            "description": "实现前端功能、接口对接",
            "agent_key": "code",
            "effort_hours": 3.0,
            "depends_on": [],
            "verification": "前端功能通过交互测试",
        },
    ),
    (
        re.compile(r"(?:HIL|hardware.?in.?loop)", re.IGNORECASE),
        {
            "step_id": "hil-framework",
            "name": "HIL 测试框架搭建",
            "description": "搭建 HIL 测试台架，配置 MCAL 层驱动",
            "agent_key": "code",
            "effort_hours": 2.0,
            "depends_on": [],
            "verification": "HIL 测试可编译并运行空用例",
        },
    ),
    (
        re.compile(r"(?:arch|architecture|design|结构)", re.IGNORECASE),
        {
            "step_id": "architecture-design",
            "name": "架构设计",
            "description": "进行架构设计，定义模块划分和接口",
            "agent_key": "architecture",
            "effort_hours": 2.0,
            "depends_on": [],
            "verification": "架构设计通过评审",
        },
    ),
    (
        re.compile(r"(?:requirement|spec|需求|规格)", re.IGNORECASE),
        {
            "step_id": "spec-analysis",
            "name": "需求分析",
            "description": "解析需求，进行 OpenSpec 合规检查",
            "agent_key": "spec",
            "effort_hours": 1.0,
            "depends_on": [],
            "verification": "需求通过 OpenSpec 校验",
        },
    ),
    (
        re.compile(r"(?:MISRA|misra|编码规范)", re.IGNORECASE),
        {
            "step_id": "misra-review",
            "name": "MISRA 合规审查",
            "description": "使用静态分析工具检查 MISRA 合规性",
            "agent_key": "compliance",
            "effort_hours": 1.5,
            "depends_on": [],
            "verification": "MISRA 偏差率 ≤ 5%",
        },
    ),
]


def _match_rules(task: str) -> list[dict]:
    """Return all matching rule trigger infos for a task description."""
    matches: list[dict] = []
    for pattern, info in _RULES:
        if pattern.search(task):
            matches.append(dict(info))
    return matches


def _detect_prerequisites(task: str) -> list[str]:
    """Detect prerequisites from task keywords."""
    prereqs: list[str] = []

    if re.search(r"(?:HIL|hardware)", task, re.IGNORECASE):
        prereqs.append("HIL 硬件台架可用（确认 yuleASR MCAL 配置）")
    if re.search(r"(?:KG|knowledge.?graph)", task, re.IGNORECASE):
        prereqs.append("KG store 已初始化并可查询")
    if re.search(r"(?:ASIL|safety)", task, re.IGNORECASE):
        prereqs.append("安全手册 / ASIL 分解文档已发布")
    if re.search(r"(?:MISRA)", task, re.IGNORECASE):
        prereqs.append("MISRA 规则集已配置 (misra-rules.yaml)")
    if re.search(r"(?:dashboard|UI|frontend)", task, re.IGNORECASE):
        prereqs.append("前端构建环境已配置 (Node.js, npm/yarn)")
    if re.search(r"(?:pipeline|流水线)", task, re.IGNORECASE):
        prereqs.append("CheckpointEngine 可用 (LLM API key 已配置)")

    return prereqs


def _detect_risks(task: str) -> list[str]:
    """Detect risks from task keywords."""
    risks: list[str] = []

    if re.search(r"(?:HIL|hardware)", task, re.IGNORECASE):
        risks.append("HIL 硬件台架可用性需确认 — 可能影响并行开发")
    if re.search(r"(?:migrate|migration|移?植)", task, re.IGNORECASE):
        risks.append("SIL → HIL 用例迁移可能 20%+ 需要重写")
    if re.search(r"(?:LLM|api.?key)", task, re.IGNORECASE):
        risks.append("LLM API 调用成本随用例规模线性增长")
    if re.search(r"(?:ASIL|safety)", task, re.IGNORECASE):
        risks.append("安全等级目标 (ASIL) 可能影响架构复杂度")
    if re.search(r"(?:third.?party|external|vendor)", task, re.IGNORECASE):
        risks.append("第三方依赖可能引入许可证或版本兼容风险")

    risks.append("估算基于启发式规则，实际工时可能有 ±30% 偏差")
    return risks


def _build_dependency_graph(matches: list[dict]) -> None:
    """Assign dependencies among matched steps.

    Heuristic: if a step mentions 'framework' or similar foundational
    work, later steps depend on it.  Otherwise order by detection
    and leave depends_on empty by default.
    """
    # Identify framework-like steps
    framework_ids = {
        m["step_id"] for m in matches
        if "framework" in m["step_id"] or "planning" in m["step_id"]
    }
    # Make later steps depend on framework steps
    for m in matches:
        if m["step_id"] in framework_ids:
            continue
        if framework_ids:
            m.setdefault("depends_on", []).extend(sorted(framework_ids))


def _assign_agent(match_info: dict) -> str:
    """Map agent_key to display name."""
    key = match_info.get("agent_key", "code")
    return AGENT_MAP.get(key, "小克 👨‍💻")


def _add_default_steps(matches: list[dict]) -> list[dict]:
    """Ensure any standard pipeline steps not yet matched are considered.

    Always includes a code step and a review step unless the plan
    is purely informational.
    """
    matched_ids = {m["step_id"] for m in matches}
    defaults: list[dict] = []

    if "code-implementation" not in matched_ids:
        defaults.append({
            "step_id": "code-implementation",
            "name": "代码实现",
            "description": "实现功能代码，含单元测试",
            "agent_key": "code",
            "effort_hours": 3.0,
            "depends_on": [],
            "verification": "代码编译通过，单元测试通过",
        })

    if "code-review" not in matched_ids:
        defaults.append({
            "step_id": "code-review",
            "name": "代码审查",
            "description": "审查代码逻辑、风格、安全实践",
            "agent_key": "review",
            "effort_hours": 1.0,
            "depends_on": [],
            "verification": "审查报告无 blocking 项",
        })

    if "final-summary" not in matched_ids:
        defaults.append({
            "step_id": "final-summary",
            "name": "最终总结与报告",
            "description": "汇总所有步骤结果，输出实施报告",
            "agent_key": "orchestration",
            "effort_hours": 0.5,
            "depends_on": [],
            "verification": "报告在 KG 中可追溯",
        })

    return matches + defaults


def _renumber_steps(steps: list[PlanStep]) -> list[PlanStep]:
    """Assign sequential step IDs (P1, P2, ...) based on dependency order."""
    # Simple topological sort: steps with fewer deps first
    # Create a copy sorted by number of dependencies (stable)
    sorted_steps = sorted(steps, key=lambda s: len(s.depends_on))
    seen = set()
    ordered: list[PlanStep] = []
    # Iterative topological sort
    remaining = list(sorted_steps)
    while remaining:
        for s in list(remaining):
            if all(dep in seen for dep in s.depends_on):
                ordered.append(s)
                seen.add(s.step_id)
                remaining.remove(s)
                break
        else:
            # Cycle or all remaining have unsatisfied deps — just append
            ordered.extend(remaining)
            break

    # Re-number
    for i, step in enumerate(ordered, 1):
        step.step_id = f"P{i}"
    return ordered


class PlanGenerator:
    """Generates a structured Plan from a task description and context."""

    def generate(
        self,
        task: str,
        context: dict | None = None,
    ) -> Plan:
        """Generate a Plan from a natural-language task description.

        Args:
            task:     User's task description in natural language.
            context:  Optional dict with project/KG/pipeline context.
                      Can contain keys: project_summary, kg, pipeline_caps.

        Returns:
            A fully populated Plan instance.
        """
        if context is None:
            context = {}

        project_summary = context.get("project_summary", {})
        kg_info = context.get("kg", {})

        # ── Title & objective ──────────────────────────────────────────
        title = self._generate_title(task)
        objective = self._generate_objective(task)

        # ── Background — mix task info with project context ─────────────
        background_parts = [f"任务: {task}"]
        if project_summary:
            modules = project_summary.get("module_dirs", [])
            if modules:
                background_parts.append(f"项目模块: {', '.join(modules[:6])}")
            if project_summary.get("test_files", 0) > 0:
                background_parts.append(
                    f"已有测试文件: {project_summary['test_files']} 个"
                )
        if kg_info.get("available"):
            background_parts.append(
                f"KG: {kg_info.get('node_count', 0)} 节点 "
                f"/ {kg_info.get('edge_count', 0)} 边"
            )
        background = " | ".join(background_parts)

        # ── Technical approach ──────────────────────────────────────────
        technical_approach = self._generate_technical_approach(
            task, project_summary, kg_info
        )

        # ── Steps ───────────────────────────────────────────────────────
        matches = _match_rules(task)
        matches = _add_default_steps(matches)
        _build_dependency_graph(matches)

        steps: list[PlanStep] = []
        for i, info in enumerate(matches):
            step = PlanStep(
                step_id=f"P{i + 1}",
                name=info["name"],
                description=info["description"],
                agent=_assign_agent(info),
                effort_hours=info["effort_hours"],
                depends_on=list(info.get("depends_on", [])),
                verification=info["verification"],
            )
            steps.append(step)

        steps = _renumber_steps(steps)

        # ── Risks & prerequisites ──────────────────────────────────────
        risks = _detect_risks(task)
        prerequisites = _detect_prerequisites(task)

        plan = Plan(
            title=title,
            objective=objective,
            background=background,
            technical_approach=technical_approach,
            steps=steps,
            risks=risks,
            prerequisites=prerequisites,
            generated_at=datetime.now(timezone.utc).isoformat(),
            status=PlanStatus.DRAFT,
        )
        return plan

    # ── Heuristic text generators ────────────────────────────────────

    def _generate_title(self, task: str) -> str:
        """Extract a condensed title from a task description."""
        # Strip common openings
        title = re.sub(
            r"^(?:为|给|对|编写|实现|开发|增加|添加|修改|创建|优化|重构)\s*",
            "",
            task,
        )
        # Truncate to first sentence
        title = re.split(r"[。.!！\n]", title, maxsplit=1)[0]
        if len(title) > 60:
            title = title[:57] + "..."
        return title.strip() or task[:60]

    def _generate_objective(self, task: str) -> str:
        """Generate a one-line objective from the task."""
        return f"{task[:120]}{'...' if len(task) > 120 else ''}"

    def _generate_technical_approach(
        self,
        task: str,
        project_summary: dict,
        kg_info: dict,
    ) -> str:
        """Generate a technical approach summary based on task keywords."""
        parts: list[str] = []

        if re.search(r"(?:test|coverage)", task, re.IGNORECASE):
            parts.append("基于现有测试框架 (pytest) 扩展，复用已有的 fixture 和模拟层。")
        if re.search(r"(?:HIL|hardware)", task, re.IGNORECASE):
            parts.append("基于 yuleASR MCAL 层搭建 HIL 测试台架，使用 Unity/CMock 框架。")
        if re.search(r"(?:KG|knowledge.?graph)", task, re.IGNORECASE):
            parts.append("使用 KG 追溯引擎验证 implements + validates 边完整性。")
        if re.search(r"(?:dashboard|UI)", task, re.IGNORECASE):
            parts.append("前端使用 FastAPI + Jinja2 模板或独立 SPA 框架。")
        if not parts:
            parts.append("按 yuleOSH 标准流水线 (CheckpointEngine 29 步) 执行。")
        if project_summary.get("source_files", 0) > 0:
            parts.append(
                f"项目已有 {project_summary['source_files']} 个源文件，"
                f"{project_summary.get('test_files', 0)} 个测试文件。"
            )

        return " ".join(parts)
