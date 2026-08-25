"""Unit tests for yuleosh.engine.checkpoint — pure Python, no external deps."""

# @tests src/yuleosh/engine/

import pytest
from yuleosh.engine.checkpoint import StepRecord, StepStatus, CheckpointState, CheckpointEngine


class TestStepStatus:
    def test_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.PASSED.value == "passed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"

    def test_valid_statuses(self):
        statuses = set(StepStatus)
        assert len(statuses) == 5


class TestStepRecord:
    def test_create_minimal(self):
        sr = StepRecord(step_id="P1", name="Build")
        assert sr.step_id == "P1"
        assert sr.name == "Build"
        assert sr.status == StepStatus.PENDING
        assert sr.agent == ""

    def test_create_full(self):
        sr = StepRecord(
            step_id="P1", name="Test", agent="agent",
            status=StepStatus.PASSED, duration_s=5.5,
        )
        assert sr.agent == "agent"
        assert sr.status == StepStatus.PASSED
        assert sr.duration_s == 5.5


class TestCheckpointState:
    def test_create(self):
        state = CheckpointState(pipeline_name="test-pipeline")
        assert state.pipeline_name == "test-pipeline"
        assert state.status == "created"

    def test_create_with_steps(self):
        sr = StepRecord(step_id="P1", name="Step 1")
        state = CheckpointState(pipeline_name="p", steps=[sr])
        assert len(state.steps) == 1

    def test_to_dict(self):
        state = CheckpointState(pipeline_name="p")
        d = state.to_dict()
        assert d["pipeline_name"] == "p"
        assert d["steps"] == []

    def test_to_dict_with_steps(self):
        sr = StepRecord(step_id="P1", name="Step 1", status=StepStatus.PASSED)
        state = CheckpointState(pipeline_name="p", steps=[sr])
        d = state.to_dict()
        assert len(d["steps"]) == 1
        assert d["steps"][0]["step_id"] == "P1"
        assert d["steps"][0]["status"] == "passed"

    def test_from_dict(self):
        d = {
            "pipeline_name": "test",
            "steps": [
                {"step_id": "P1", "name": "Build", "status": "passed"},
            ],
        }
        state = CheckpointState.from_dict(d)
        assert state.pipeline_name == "test"
        assert len(state.steps) == 1
        assert state.steps[0].status == StepStatus.PASSED

    def test_from_dict_empty(self):
        state = CheckpointState.from_dict({})
        assert state.pipeline_name == ""
        assert state.steps == []


class TestCheckpointEngine:
    def test_create(self):
        engine = CheckpointEngine(
            pipeline_name="test",
            project_dir="/tmp/test"
        )
        assert engine.pipeline_name == "test"
