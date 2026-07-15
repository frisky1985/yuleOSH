#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for Ultra-Plan Agent (yuleosh.plan).
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from yuleosh.plan import (
    PlanAgent,
    Plan,
    PlanStep,
    PlanStatus,
    AGENT_MAP,
    PlanGenerator,
    to_markdown,
    to_json,
    to_pipeline_steps,
)


# ═══════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════

class TestPlanStep:
    def test_minimal_step(self):
        step = PlanStep(step_id="P1", name="测试", description="do it", agent="小克 👨‍💻", effort_hours=1.0)
        assert step.step_id == "P1"
        assert step.name == "测试"
        assert step.agent == "小克 👨‍💻"
        assert step.effort_hours == 1.0
        assert step.depends_on == []
        assert step.verification == ""
        assert step.pipeline_step is None

    def test_step_to_dict_and_from_dict(self):
        step = PlanStep(
            step_id="P2",
            name="审查",
            description="代码审查",
            agent="小马 🐴",
            effort_hours=1.5,
            depends_on=["P1"],
            verification="通过审查报告",
            pipeline_step="code-review",
        )
        d = step.to_dict()
        restored = PlanStep.from_dict(d)
        assert restored == step

    def test_step_roundtrip(self):
        step = PlanStep(
            step_id="P3-hil",
            name="HIL 框架搭建",
            description="搭建 HIL 测试台架",
            agent="小克 👨‍💻",
            effort_hours=2.0,
        )
        d = step.to_dict()
        restored = PlanStep.from_dict(d)
        assert restored.step_id == "P3-hil"
        assert restored.agent == "小克 👨‍💻"
        assert restored.effort_hours == 2.0
        assert restored.depends_on == []


class TestPlan:
    def test_minimal_plan(self):
        plan = Plan(title="Test Plan", objective="Test", background="", technical_approach="")
        assert plan.title == "Test Plan"
        assert plan.status == PlanStatus.DRAFT
        assert plan.steps == []
        assert plan.total_effort_hours == 0.0

    def test_plan_with_steps(self):
        steps = [
            PlanStep(step_id="P1", name="Step 1", description="", agent="小克 👨‍💻", effort_hours=2.0),
            PlanStep(step_id="P2", name="Step 2", description="", agent="小马 🐴", effort_hours=1.0),
        ]
        plan = Plan(
            title="Multi-step",
            objective="Test multi-step",
            background="Test",
            technical_approach="Approach",
            steps=steps,
        )
        assert len(plan.steps) == 2
        assert plan.total_effort_hours == 3.0
        assert plan.agent_count == 2

    def test_plan_agent_breakdown(self):
        steps = [
            PlanStep(step_id="P1", name="Dev", description="", agent="小克 👨‍💻", effort_hours=3.0),
            PlanStep(step_id="P2", name="Review", description="", agent="小马 🐴", effort_hours=1.5),
            PlanStep(step_id="P3", name="More Dev", description="", agent="小克 👨‍💻", effort_hours=2.0),
        ]
        plan = Plan(title="BD", objective="Test BD", background="", technical_approach="", steps=steps)
        breakdown = plan.agent_breakdown
        assert breakdown.get("小克 👨‍💻") == 5.0
        assert breakdown.get("小马 🐴") == 1.5

    def test_plan_serialization_roundtrip(self):
        steps = [
            PlanStep(step_id="P1", name="S1", description="Desc", agent="小克 👨‍💻", effort_hours=1.0),
        ]
        plan = Plan(
            title="Roundtrip",
            objective="Test",
            background="BG",
            technical_approach="TA",
            steps=steps,
            risks=["Risk A"],
            prerequisites=["Prereq A"],
        )
        json_str = plan.to_json()
        restored = Plan.from_json(json_str)
        assert restored.title == plan.title
        assert restored.objective == plan.objective
        assert len(restored.steps) == 1
        assert restored.steps[0].step_id == "P1"
        assert restored.risks == ["Risk A"]
        assert restored.prerequisites == ["Prereq A"]

    def test_plan_from_json(self):
        raw = {
            "title": "JSON Plan",
            "objective": "From JSON",
            "background": "BG",
            "technical_approach": "TA",
            "steps": [
                {"step_id": "X1", "name": "X", "description": "", "agent": "小克 👨‍💻",
                 "effort_hours": 0.5, "depends_on": [], "verification": "", "pipeline_step": None},
            ],
            "risks": [],
            "prerequisites": [],
            "generated_at": "2026-01-01T00:00:00",
            "status": "draft",
        }
        json_str = json.dumps(raw, ensure_ascii=False)
        plan = Plan.from_json(json_str)
        assert plan.title == "JSON Plan"
        assert plan.steps[0].effort_hours == 0.5

    def test_plan_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid plan status"):
            Plan(title="X", objective="X", background="X", technical_approach="X", status="bogus")


class TestPlanStepFields:
    """Verify each PlanStep has all required fields."""

    REQUIRED_FIELDS = {"step_id", "name", "description", "agent", "effort_hours", "depends_on", "verification"}

    def test_all_steps_have_fields(self):
        plan = _make_sample_plan()
        for step in plan.steps:
            d = step.to_dict()
            for field in self.REQUIRED_FIELDS:
                assert field in d, f"Step {step.step_id} missing field: {field}"

    def test_agent_assignment(self):
        """Code steps → 小克, review → 小马."""
        steps = [
            PlanStep(step_id="P1", name="Code", description="", agent="小克 👨‍💻", effort_hours=1.0),
            PlanStep(step_id="P2", name="Review", description="", agent="小马 🐴", effort_hours=1.0),
            PlanStep(step_id="P3", name="Orch", description="", agent="小明", effort_hours=1.0),
        ]
        assert steps[0].agent == "小克 👨‍💻"
        assert steps[1].agent == "小马 🐴"
        assert steps[2].agent == "小明"


# ═══════════════════════════════════════════════════════════════════
# PlanAgent
# ═══════════════════════════════════════════════════════════════════

class TestPlanAgent:
    def test_plan_agent_creates_plan(self):
        """PlanAgent.plan("write unit tests") → Plan object."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("write unit tests")
        assert isinstance(plan, Plan)
        assert plan.title is not None
        assert plan.objective is not None

    def test_plan_has_steps(self):
        """Generated Plan has at least 1 step."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("Add HIL test support for BCM Demo")
        assert len(plan.steps) >= 1

    def test_plan_to_markdown(self):
        """to_markdown() returns a string."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("implement BCM door control")
        md = agent.to_markdown(plan)
        assert isinstance(md, str)
        assert len(md) > 50
        assert plan.title in md or "Ultra-Plan" in md

    def test_plan_to_json(self):
        """to_json() returns valid JSON string."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("Add coverage tracking for KG")
        js = agent.to_json(plan)
        parsed = json.loads(js)
        assert "title" in parsed
        assert "steps" in parsed
        assert "risks" in parsed

    def test_plan_to_pipeline(self):
        """to_pipeline() returns CheckpointEngine-compatible format."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("Write integration tests for BCM")
        pipeline = agent.to_pipeline(plan)
        assert isinstance(pipeline, list)
        for entry in pipeline:
            assert "step_id" in entry
            assert "agent" in entry
            assert "action" in entry

    def test_agent_type_assignments(self):
        """Steps assigned to correct agent based on content."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("Add HIL test support and MISRA review")
        agents = {s.agent for s in plan.steps}
        # Should have at least 小克 and 小马
        assert any("小克" in a for a in agents)
        assert any("小马" in a for a in agents)

    def test_plan_effort_summary(self):
        """Steps have reasonable effort estimates."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("Add HIL test for BCM demo")
        assert plan.total_effort_hours > 0
        assert plan.agent_count >= 1

    def test_save_to_disk(self):
        """Plan agent saves to disk correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = PlanAgent(project_dir=".")
            plan = agent.plan("add unit test")
            out_path = Path(tmpdir) / "plan.json"
            agent.save(plan, str(out_path))
            assert out_path.exists()
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            assert saved["title"] == plan.title

    def test_status_transitions(self):
        """Plan lifecycle transitions work."""
        agent = PlanAgent(project_dir=".")
        plan = agent.plan("simple task")
        assert plan.status == PlanStatus.DRAFT

        agent.approve(plan)
        assert plan.status == PlanStatus.APPROVED

        agent.start_execution(plan)
        assert plan.status == PlanStatus.EXECUTING

        agent.complete(plan)
        assert plan.status == PlanStatus.DONE

    def test_save_markdown(self):
        """save_markdown writes a .md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = PlanAgent(project_dir=".")
            plan = agent.plan("test markdown output")
            out_path = Path(tmpdir) / "plan.md"
            agent.save_markdown(plan, str(out_path))
            assert out_path.exists()
            content = out_path.read_text(encoding="utf-8")
            assert "Ultra-Plan" in content or plan.title in content


# ═══════════════════════════════════════════════════════════════════
# Context
# ═══════════════════════════════════════════════════════════════════

class TestPlanContext:
    def test_context_project_summary(self):
        """PlanContext reads project structure."""
        from yuleosh.plan.context import PlanContext
        # Use the yuleOSH project itself
        ctx = PlanContext(project_dir=_project_root())
        summary = ctx.get_project_summary()
        assert "project_dir" in summary
        assert "module_dirs" in summary
        assert "src" in summary["module_dirs"] or len(summary["module_dirs"]) > 0

    def test_context_kg_summary_graceful(self):
        """KG summary returns graceful empty when no KG."""
        from yuleosh.plan.context import PlanContext
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PlanContext(project_dir=tmpdir)
            kg = ctx.get_kg_summary()
            assert isinstance(kg, dict)
            assert kg["available"] is False
            assert kg["node_count"] == 0

    def test_context_pipeline_capabilities(self):
        """Pipeline capabilities returns list (empty if unavailable)."""
        from yuleosh.plan.context import PlanContext
        ctx = PlanContext(project_dir=_project_root())
        caps = ctx.get_pipeline_capabilities()
        assert isinstance(caps, list)
        # In the real project, should have steps
        if caps:
            assert "step_id" in caps[0]
            assert "agent" in caps[0]

    def test_context_existing_requirements(self):
        """Existing requirements returns list."""
        from yuleosh.plan.context import PlanContext
        ctx = PlanContext(project_dir=_project_root())
        reqs = ctx.get_existing_requirements()
        assert isinstance(reqs, list)

    def test_context_aspice_coverage_graceful(self):
        """ASPICE coverage returns empty dict when no KG."""
        from yuleosh.plan.context import PlanContext
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PlanContext(project_dir=tmpdir)
            coverage = ctx.get_aspice_coverage()
            assert isinstance(coverage, dict)
            assert len(coverage) == 0


# ═══════════════════════════════════════════════════════════════════
# Output format tests
# ═══════════════════════════════════════════════════════════════════

class TestOutput:
    def test_markdown_output_formatted(self):
        """to_markdown() produces readable output."""
        plan = _make_sample_plan()
        md = to_markdown(plan)
        assert "Ultra-Plan" in md
        assert "目标" in md
        assert "技术方案" in md
        assert "实施步骤" in md
        assert "总计" in md
        assert "风险" in md
        assert "前置条件" in md

    def test_markdown_with_ansi(self):
        """to_markdown with ansi escapes."""
        plan = _make_sample_plan()
        md = to_markdown(plan, with_ansi=True)
        assert "\033[" in md  # ANSI escape present

    def test_json_output_valid(self):
        """to_json() produces valid JSON."""
        plan = _make_sample_plan()
        js = to_json(plan)
        parsed = json.loads(js)
        assert parsed["title"] == "Sample Plan"
        assert len(parsed["steps"]) == 2

    def test_pipeline_output_format(self):
        """to_pipeline_steps() produces correct structure."""
        plan = _make_sample_plan()
        steps = to_pipeline_steps(plan)
        assert len(steps) == 2
        for s in steps:
            assert "step_id" in s
            assert "action" in s
            assert s["step_id"] in ("P1", "P2")

    def test_pipeline_output_maps_pipeline_step(self):
        """pipeline_step is included when set."""
        step = PlanStep(
            step_id="P99",
            name="Spec Check",
            description="",
            agent="小明",
            effort_hours=0.5,
            pipeline_step="spec-check",
        )
        plan = Plan(title="X", objective="X", background="X", technical_approach="X", steps=[step])
        steps = to_pipeline_steps(plan)
        assert steps[0]["pipeline_step"] == "spec-check"


# ═══════════════════════════════════════════════════════════════════
# Generator tests
# ═══════════════════════════════════════════════════════════════════

class TestPlanGenerator:
    def test_generator_detects_test_keyword(self):
        """HIL keyword produces HIL-related steps."""
        gen = PlanGenerator()
        plan = gen.generate("Add HIL test for BCM demo", context={})
        step_names = [s.name for s in plan.steps]
        assert any("HIL" in n for n in step_names)

    def test_generator_detects_safety_keyword(self):
        """Safety keyword produces safety gate step."""
        gen = PlanGenerator()
        plan = gen.generate("ASIL B safety mechanism", context={})
        step_names = [s.name for s in plan.steps]
        assert any("安全" in n or "safety" in n.lower() for n in step_names)

    def test_generator_detects_requirement_keyword(self):
        """Requirement keyword produces analysis step."""
        gen = PlanGenerator()
        plan = gen.generate("Analyze new requirements", context={})
        step_names = [s.name for s in plan.steps]
        assert any("需求" in n for n in step_names)

    def test_generator_always_has_default_steps(self):
        """Even minimal tasks get code + review + summary steps."""
        gen = PlanGenerator()
        plan = gen.generate("Fix typo in README", context={})
        step_names = [s.name for s in plan.steps]
        assert any("代码实现" in n or "Code" in n for n in step_names)
        assert any("代码审查" in n or "Review" in n for n in step_names)
        assert any("总结" in n or "报告" in n for n in step_names)

    def test_generator_detects_risks(self):
        """HIL tasks include hardware availability risk."""
        gen = PlanGenerator()
        plan = gen.generate("HIL test bench setup", context={})
        risk_texts = " ".join(plan.risks)
        assert "HIL" in risk_texts or "硬件" in risk_texts

    def test_generator_detects_prerequisites(self):
        """HIL tasks include hardware prerequisite."""
        gen = PlanGenerator()
        plan = gen.generate("HIL test bench setup", context={})
        prereq_texts = " ".join(plan.prerequisites)
        assert "HIL" in prereq_texts or "硬件" in prereq_texts

    def test_generator_with_kg_context(self):
        """Context with KG data is reflected in plan."""
        gen = PlanGenerator()
        context = {
            "project_summary": {"module_dirs": ["bcm", "hil"], "test_files": 12, "source_files": 45},
            "kg": {"available": True, "node_count": 150, "edge_count": 300},
        }
        plan = gen.generate("Traceability check for BCM", context=context)
        assert "BCM" in plan.background or "bcm" in plan.background
        assert "KG" in plan.background or "150" in plan.background

    def test_generator_risks_always_includes_estimate_warning(self):
        gen = PlanGenerator()
        plan = gen.generate("Simple task", context={})
        assert any("±30%" in r for r in plan.risks)

    def test_generator_title_truncation(self):
        """Long titles are truncated gracefully."""
        gen = PlanGenerator()
        long_task = "Implement " + "very " * 30 + "complex feature that spans many modules and requires extensive testing"
        plan = gen.generate(long_task, context={})
        assert len(plan.title) <= 63  # 60 + "..." if truncated


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _project_root() -> str:
    """Return the yuleOSH project root (where src/ lives)."""
    # Walk up from tests/
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "src").is_dir():
            return str(p)
        p = p.parent
    return os.getcwd()


def _make_sample_plan() -> Plan:
    """Create a dummy plan for output-format tests."""
    steps = [
        PlanStep(
            step_id="P1",
            name="HIL 测试框架搭建",
            description="搭建 HIL 测试台架，配置驱动",
            agent="小克 👨‍💻",
            effort_hours=2.0,
            verification="HIL 测试可编译运行",
        ),
        PlanStep(
            step_id="P2",
            name="BCM 门控 HIL 用例",
            description="编写门控 HIL 测试用例",
            agent="小克 👨‍💻",
            effort_hours=1.5,
            depends_on=["P1"],
            verification="门控 HIL 3 用例通过",
        ),
    ]
    return Plan(
        title="Sample Plan",
        objective="Test the output format",
        background="Sample background for testing",
        technical_approach="Sample technical approach",
        steps=steps,
        risks=["Risk: hardware availability", "Risk: estimate ±30%"],
        prerequisites=["HIL hardware available"],
    )
