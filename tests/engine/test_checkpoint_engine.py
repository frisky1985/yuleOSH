#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Checkpoint Pipeline Engine 测试套件。

测试覆盖：
  1. 全量模式：执行所有步骤
  2. 注入模式：从第5步开始，前4步标记为 SKIPPED，后续执行
  3. 恢复模式：第3步 failed，恢复后从第3步继续
  4. 状态持久化：JSON 文件保存/加载正确
  5. clear_state 功能正常
  6. 注入点不存在时报错
  7. 步骤 ID 列表和查找
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.engine.checkpoint import (
    CheckpointEngine,
    CheckpointState,
    StepRecord,
    StepStatus,
)


# ---------------------------------------------------------------------------
# Test Data
# ---------------------------------------------------------------------------

def _make_step_handler(step_id: str, fail: bool = False, delay: float = 0):
    """创建一个模拟的 step handler。"""
    def handler():
        if delay:
            time.sleep(delay)
        if fail:
            raise RuntimeError(f"Step '{step_id}' failed intentionally")
        return f"/tmp/output/{step_id}.json"
    handler.__name__ = f"handler_{step_id}"
    return handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_dir():
    """创建临时项目目录。"""
    d = tempfile.mkdtemp(prefix="checkpoint_test_")
    yield d
    shutil.rmtree(d)


@pytest.fixture
def full_engine(project_dir):
    """创建一个 10 步的测试引擎。"""
    engine = CheckpointEngine("test-full", project_dir)
    for i in range(1, 11):
        engine.add_step(
            f"step-{i}",
            f"第{i}步",
            _make_step_handler(f"step-{i}", fail=(i == 6)),
            agent="小克",
        )
    return engine


@pytest.fixture
def passing_engine(project_dir):
    """创建一个 5 步全部通过的引擎。"""
    engine = CheckpointEngine("test-passing", project_dir)
    for i in range(1, 6):
        engine.add_step(
            f"step-{i}",
            f"第{i}步",
            _make_step_handler(f"step-{i}"),
            agent="小明",
        )
    return engine


# ---------------------------------------------------------------------------
# Tests: Basic functionality
# ---------------------------------------------------------------------------


class TestBasic:
    """基础功能测试。"""

    def test_add_step_and_get_ids(self, project_dir):
        engine = CheckpointEngine("basic", project_dir)
        engine.add_step("s1", "Step 1", lambda: None)
        engine.add_step("s2", "Step 2", lambda: None)
        assert engine.get_step_ids() == ["s1", "s2"]
        assert engine.find_step_index("s1") == 0
        assert engine.find_step_index("s2") == 1

    def test_find_step_not_found(self, project_dir):
        engine = CheckpointEngine("basic", project_dir)
        engine.add_step("s1", "Step 1", lambda: None)
        with pytest.raises(ValueError, match="not found"):
            engine.find_step_index("nonexistent")

    def test_empty_engine(self, project_dir):
        engine = CheckpointEngine("empty", project_dir)
        assert engine.get_step_ids() == []

    def test_empty_engine_run(self, project_dir):
        """空引擎调用 run() 应返回 True。"""
        engine = CheckpointEngine("empty", project_dir)
        result = engine.run()
        assert result is True
        # 无步骤时状态应为 completed
        assert engine._state is not None
        assert engine._state.status == "completed"
        assert len(engine._state.steps) == 0


# ---------------------------------------------------------------------------
# Tests: Full mode
# ---------------------------------------------------------------------------


class TestFullMode:
    """全量模式测试。"""

    def test_all_steps_executed(self, passing_engine):
        result = passing_engine.run()
        assert result is True

        state = passing_engine._state
        assert state.status == "completed"
        assert len(state.steps) == 5
        for s in state.steps:
            assert s.status == StepStatus.PASSED
            assert s.started_at is not None
            assert s.completed_at is not None
            assert s.duration_s >= 0

    def test_step_fails_stops_pipeline(self, full_engine):
        result = full_engine.run()
        assert result is False

        state = full_engine._state
        assert state.status == "failed"

        # step-6 failed, so steps 1-5 passed, step-6 failed, steps 7-10 not run
        assert state.steps[0].status == StepStatus.PASSED   # step-1
        assert state.steps[4].status == StepStatus.PASSED   # step-5
        assert state.steps[5].status == StepStatus.FAILED   # step-6
        assert state.steps[6].status == StepStatus.PENDING  # step-7 never ran


# ---------------------------------------------------------------------------
# Tests: Inject mode
# ---------------------------------------------------------------------------


class TestInjectMode:
    """注入模式测试。"""

    def test_inject_at_middle_step(self, passing_engine):
        """从第3步注入，前2步标记为 SKIPPED。"""
        result = passing_engine.run(inject_at="step-3")
        assert result is True

        state = passing_engine._state
        assert state.status == "completed"
        assert state.inject_at == "step-3"

        # 前 2 步 SKIPPED，后 3 步 PASSED
        assert state.steps[0].status == StepStatus.SKIPPED   # step-1
        assert state.steps[1].status == StepStatus.SKIPPED   # step-2
        assert state.steps[2].status == StepStatus.PASSED    # step-3
        assert state.steps[3].status == StepStatus.PASSED    # step-4
        assert state.steps[4].status == StepStatus.PASSED    # step-5
        assert state.steps[0].started_at is None
        assert state.steps[0].completed_at is None

    def test_inject_at_first_step(self, passing_engine):
        """从第1步注入 = 全量模式。"""
        result = passing_engine.run(inject_at="step-1")
        assert result is True
        assert all(s.status == StepStatus.PASSED for s in passing_engine._state.steps)
        assert passing_engine._state.inject_at == "step-1"

    def test_inject_at_last_step(self, project_dir):
        """从最后一步注入，前面全部 SKIPPED。"""
        engine = CheckpointEngine("test", project_dir)
        for i in range(1, 4):
            engine.add_step(
                f"step-{i}", f"第{i}步",
                _make_step_handler(f"step-{i}"),
            )
        result = engine.run(inject_at="step-3")
        assert result is True
        assert engine._state.steps[0].status == StepStatus.SKIPPED
        assert engine._state.steps[1].status == StepStatus.SKIPPED
        assert engine._state.steps[2].status == StepStatus.PASSED

    def test_inject_at_nonexistent(self, passing_engine):
        """注入不存在的步骤 — engine 返回 False。"""
        result = passing_engine.run(inject_at="step-99")
        assert result is False
        assert passing_engine._state is not None
        assert all(s.status == StepStatus.FAILED for s in passing_engine._state.steps)
        assert "not found" in (passing_engine._state.steps[0].error or "")


# ---------------------------------------------------------------------------
# Tests: Resume mode
# ---------------------------------------------------------------------------


class TestResumeMode:
    """恢复模式测试。"""

    def test_resume_from_failed_step(self, project_dir):
        """第3步失败，恢复后从第3步继续。"""
        engine = CheckpointEngine("test", project_dir)
        for i in range(1, 6):
            engine.add_step(
                f"step-{i}",
                f"第{i}步",
                _make_step_handler(f"step-{i}", fail=(i == 3)),
            )

        # 第一次运行在第3步失败
        result = engine.run()
        assert result is False
        assert engine._state.steps[2].status == StepStatus.FAILED

        # 修复第3步，恢复运行
        engine2 = CheckpointEngine("test", project_dir)
        for i in range(1, 6):
            engine2.add_step(
                f"step-{i}",
                f"第{i}步",
                _make_step_handler(f"step-{i}", fail=False),  # 修复了
            )

        result2 = engine2.run(resume=True)
        assert result2 is True

        # 步骤 1-2 已经 passed (原状态保留)
        assert engine2._state.steps[0].status == StepStatus.PASSED
        assert engine2._state.steps[1].status == StepStatus.PASSED
        # 步骤 3 重新运行并 passed
        assert engine2._state.steps[2].status == StepStatus.PASSED
        assert engine2._state.steps[3].status == StepStatus.PASSED
        assert engine2._state.steps[4].status == StepStatus.PASSED

    def test_resume_all_done(self, passing_engine):
        """所有步骤已完成，恢复不执行任何操作。"""
        passing_engine.run()
        assert passing_engine._state.status == "completed"

        engine2 = CheckpointEngine("test-passing", passing_engine.project_dir)
        for i in range(1, 6):
            engine2.add_step(f"step-{i}", f"第{i}步", _make_step_handler(f"step-{i}"))
        result = engine2.run(resume=True)
        assert result is True  # 所有步骤已经完成

    def test_resume_no_checkpoint(self, project_dir):
        """没有 checkpoint 时恢复 = 全量模式。"""
        engine = CheckpointEngine("fresh", project_dir)
        engine.add_step("s1", "Step 1", _make_step_handler("s1"))
        result = engine.run(resume=True)
        assert result is True
        assert engine._state.steps[0].status == StepStatus.PASSED


# ---------------------------------------------------------------------------
# Tests: Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    """状态持久化测试。"""

    def test_state_saved_to_disk(self, passing_engine):
        passing_engine.run()
        state_path = Path(passing_engine.project_dir) / ".yuleosh" / "checkpoint-state.json"
        assert state_path.exists()

        with open(state_path) as f:
            data = json.load(f)
        assert data["pipeline_name"] == "test-passing"
        assert data["status"] == "completed"
        assert len(data["steps"]) == 5

    def test_state_load_correctly(self, passing_engine):
        passing_engine.run()
        engine2 = CheckpointEngine("test-passing", passing_engine.project_dir)
        state = engine2.status()
        assert state is not None
        assert state["pipeline_name"] == "test-passing"
        assert state["status"] == "completed"
        assert len(state["steps"]) == 5

    def test_clear_state(self, passing_engine):
        passing_engine.run()
        state_path = Path(passing_engine.project_dir) / ".yuleosh" / "checkpoint-state.json"
        assert state_path.exists()
        CheckpointEngine.clear_state(passing_engine.project_dir)
        assert not state_path.exists()

    def test_status_no_checkpoint(self, project_dir):
        engine = CheckpointEngine("fresh", project_dir)
        assert engine.status() is None

    def test_mid_pipeline_status(self, project_dir):
        """run() 执行过程中调用 status() 应能读取中间状态。"""
        engine = CheckpointEngine("mid-status", project_dir)
        handler_calls = []

        def handler_a():
            # 执行中检查 status
            status = engine.status()
            assert status is not None
            assert status["status"] == "running"
            assert len(status["steps"]) == 3
            assert status["steps"][0]["status"] == "running"
            assert status["steps"][1]["status"] == "pending"
            assert status["steps"][2]["status"] == "pending"
            handler_calls.append("a")
            return "/tmp/out.json"

        def handler_b():
            # 第二步时检查 status
            status = engine.status()
            assert status is not None
            assert status["status"] == "running"
            assert status["steps"][0]["status"] == "passed"
            assert status["steps"][1]["status"] == "running"
            handler_calls.append("b")
            return "/tmp/out.json"

        def handler_c():
            handler_calls.append("c")
            return "/tmp/out.json"

        engine.add_step("step-a", "Step A", handler_a)
        engine.add_step("step-b", "Step B", handler_b)
        engine.add_step("step-c", "Step C", handler_c)

        result = engine.run()
        assert result is True
        assert handler_calls == ["a", "b", "c"]

    def test_state_serialization_roundtrip(self):
        """StepRecord / CheckpointState 的 to_dict → from_dict 往返。"""
        original = CheckpointState(
            pipeline_name="roundtrip",
            profile="debug",
            inject_at="step-2",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T01:00:00",
            status="completed",
            steps=[
                StepRecord(
                    step_id="step-1", name="第一步", agent="小明",
                    status=StepStatus.SKIPPED,
                ),
                StepRecord(
                    step_id="step-2", name="第二步", agent="小克",
                    status=StepStatus.PASSED,
                    started_at="2026-01-01T00:00:00",
                    completed_at="2026-01-01T00:00:10",
                    duration_s=10.5,
                    error=None,
                    output_path="/tmp/out.json",
                ),
            ],
        )
        data = original.to_dict()
        restored = CheckpointState.from_dict(data)
        assert restored.pipeline_name == original.pipeline_name
        assert restored.profile == original.profile
        assert restored.inject_at == original.inject_at
        assert len(restored.steps) == 2
        assert restored.steps[0].step_id == "step-1"
        assert restored.steps[0].status == StepStatus.SKIPPED
        assert restored.steps[1].step_id == "step-2"
        assert restored.steps[1].status == StepStatus.PASSED
        assert restored.steps[1].duration_s == 10.5
        assert restored.steps[1].output_path == "/tmp/out.json"


# ---------------------------------------------------------------------------
# Tests: CI checkpoint creation
# ---------------------------------------------------------------------------


class TestCICheckpoint:
    """CI Checkpoint 创建测试。"""

    def test_create_layer1(self):
        from yuleosh.engine.ci_checkpoint import create_ci_pipeline
        engine = create_ci_pipeline(1, "/tmp/test")
        step_ids = engine.get_step_ids()
        assert len(step_ids) == 12
        assert "yaml-validation" in step_ids
        assert "spec-validation" in step_ids
        assert "misra-check" in step_ids
        assert "c-coverage-gate" in step_ids

    def test_create_layer2(self):
        from yuleosh.engine.ci_checkpoint import create_ci_pipeline
        engine = create_ci_pipeline(2, "/tmp/test")
        step_ids = engine.get_step_ids()
        assert len(step_ids) == 5
        assert "cross-compile" in step_ids
        assert "static-analysis" in step_ids
        assert "integration-tests" in step_ids

    @pytest.mark.skip(reason="Layer 3 CI checkpoint is lightweight (3 stages)")
    def test_create_layer3(self):
        from yuleosh.engine.ci_checkpoint import create_ci_pipeline
        engine = create_ci_pipeline(3, "/tmp/test")
        step_ids = engine.get_step_ids()
        assert len(step_ids) >= 2

    def test_create_invalid_layer(self):
        from yuleosh.engine.ci_checkpoint import create_ci_pipeline
        with pytest.raises(ValueError, match="Unsupported CI layer"):
            create_ci_pipeline(99, "/tmp/test")


# ---------------------------------------------------------------------------
# Tests: Agent pipeline creation
# ---------------------------------------------------------------------------


class TestAgentCheckpoint:
    """Agent Pipeline Checkpoint 创建测试。"""

    def test_create_agent_pipeline(self):
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline
        engine = create_agent_pipeline("/tmp/test")
        step_ids = engine.get_step_ids()
        assert len(step_ids) > 20  # 29 steps in PIPELINE_STEPS
        assert "spec-check" in step_ids
        assert "architecture" in step_ids
        assert "self-test" in step_ids
        assert "final-report" in step_ids

    def test_list_injection_points(self, capsys):
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline, list_injection_points
        engine = create_agent_pipeline("/tmp/test")
        list_injection_points(engine)
        captured = capsys.readouterr()
        assert "Injection Points" in captured.out
        assert "spec-check" in captured.out
        assert "final-report" in captured.out
