"""Unit tests for yuleosh.plan.models — pure Python, no external deps."""

import pytest

from yuleosh.plan.models import (
    Plan,
    PlanStep,
    PlanStatus,
    AGENT_MAP,
    AGENT_KEYS,
)


class TestPlanStatus:
    def test_status_values(self):
        assert PlanStatus.DRAFT == "draft"
        assert PlanStatus.REVIEW == "review"
        assert PlanStatus.APPROVED == "approved"
        assert PlanStatus.EXECUTING == "executing"
        assert PlanStatus.DONE == "done"
        assert PlanStatus.CANCELLED == "cancelled"

    def test_valid_statuses(self):
        assert "draft" in PlanStatus.VALID_STATUSES
        assert "done" in PlanStatus.VALID_STATUSES
        assert "invalid" not in PlanStatus.VALID_STATUSES


class TestAgentMap:
    def test_known_agents(self):
        assert AGENT_MAP["code"] is not None
        assert AGENT_MAP["review"] is not None
        assert AGENT_MAP["orchestration"] is not None

    def test_agent_keys(self):
        assert "code" in AGENT_KEYS
        assert "test" in AGENT_KEYS
        assert "architecture" in AGENT_KEYS


class TestPlanStep:
    def test_create_minimal(self):
        step = PlanStep(
            step_id="P1-build",
            name="Build",
            description="Build the project",
            agent="小克 👨💻",
            effort_hours=4.0,
        )
        assert step.step_id == "P1-build"
        assert step.name == "Build"
        assert step.effort_hours == 4.0
        assert step.depends_on == []
        assert step.verification == ""
        assert step.pipeline_step is None

    def test_create_with_all_fields(self):
        step = PlanStep(
            step_id="P2-test",
            name="Test",
            description="Run tests",
            agent="小克 👨💻",
            effort_hours=2.5,
            depends_on=["P1-build"],
            verification="All tests pass",
            pipeline_step="test",
        )
        assert step.depends_on == ["P1-build"]
        assert step.verification == "All tests pass"
        assert step.pipeline_step == "test"

    def test_to_dict(self):
        step = PlanStep(
            step_id="P3-review",
            name="Review",
            description="Code review",
            agent="小马 🐴",
            effort_hours=1.0,
        )
        d = step.to_dict()
        assert d["step_id"] == "P3-review"
        assert d["name"] == "Review"
        assert "description" in d


class TestPlan:
    def test_create_defaults(self):
        plan = Plan(
            title="Test Plan",
            objective="Test",
            background="Background info",
            technical_approach="Approach",
        )
        assert plan.title == "Test Plan"
        assert plan.steps == []
        assert plan.status == PlanStatus.DRAFT

    def test_create_with_steps(self):
        step = PlanStep(
            step_id="P1",
            name="Step 1",
            description="First step",
            agent="小明",
            effort_hours=1.0,
        )
        plan = Plan(
            title="My Plan",
            objective="Build",
            background="bg",
            technical_approach="ta",
            steps=[step],
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].step_id == "P1"

    def test_from_dict(self):
        d = {
            "title": "Plan",
            "objective": "Obj",
            "background": "Bg",
            "technical_approach": "TA",
        }
        plan = Plan.from_dict(d)
        assert plan.title == "Plan"
        assert plan.objective == "Obj"

    def test_to_dict(self):
        step = PlanStep(
            step_id="P1",
            name="S1",
            description="desc",
            agent="agent",
            effort_hours=1.0,
        )
        plan = Plan(
            title="Plan",
            objective="O",
            background="B",
            technical_approach="T",
            steps=[step],
        )
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert len(d["steps"]) == 1

    def test_to_json(self):
        plan = Plan(
            title="JSON Plan",
            objective="O",
            background="B",
            technical_approach="T",
        )
        j = plan.to_json()
        assert isinstance(j, str)
        assert "JSON Plan" in j

    def test_total_effort_hours(self):
        s1 = PlanStep("P1", "S1", "", "A", 2.0)
        s2 = PlanStep("P2", "S2", "", "B", 3.0)
        plan = Plan("P", "O", "B", "T", steps=[s1, s2])
        assert plan.total_effort_hours == 5.0

    def test_agent_breakdown(self):
        s1 = PlanStep("P1", "S1", "", "X", 2.0)
        s2 = PlanStep("P2", "S2", "", "X", 3.0)
        s3 = PlanStep("P3", "S3", "", "Y", 1.0)
        plan = Plan("P", "O", "B", "T", steps=[s1, s2, s3])
        assert plan.agent_breakdown["X"] == 5.0
        assert plan.agent_breakdown["Y"] == 1.0
        assert plan.agent_count == 2

    def test_invalid_status_raises(self):
        import pytest
        with pytest.raises(ValueError):
            Plan("P", "O", "B", "T", status="invalid_status")
