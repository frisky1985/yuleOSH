"""Tests for engine/executor.py — Executor interface + LocalExecutor (EI-M1A)."""

# @tests src/yuleosh/pipeline/orchestrator.py

import os
import sys
import tempfile
from pathlib import Path

import pytest

from yuleosh.engine.executor import Executor, LocalExecutor, make_executor
from yuleosh.engine.handler_adapter import StepResult


def test_executor_interface_abstract():
    """GIVEN base Executor WHEN execute THEN NotImplementedError."""
    ex = Executor()
    with pytest.raises(NotImplementedError):
        ex.execute({"step_id": "x"})


def test_make_executor_local():
    """GIVEN name='local' WHEN factory THEN LocalExecutor."""
    ex = make_executor("local", project_dir=".")
    assert isinstance(ex, LocalExecutor)


def test_make_executor_unknown():
    """GIVEN unknown name WHEN factory THEN ValueError."""
    with pytest.raises(ValueError):
        make_executor("bogus")


def test_local_executor_as_runner_signature():
    """GIVEN LocalExecutor WHEN as_runner THEN callable(step_def, artifacts) -> StepResult."""
    ex = make_executor("local", project_dir=".")
    runner = ex.as_runner()
    assert callable(runner)
    # 空 step_def 会走到 worker 解析失败（找不到 step），返回 failed 而非崩溃
    result = runner({"step_id": "no-such-step"})
    assert isinstance(result, StepResult)
    assert result.verdict == "failed"


def test_local_executor_python_executable_default():
    """GIVEN LocalExecutor 未配 venv WHEN _python_executable THEN sys.executable（零回归）。"""
    ex = LocalExecutor(project_dir=".")
    assert ex._python_executable() == sys.executable


def test_local_executor_venv_missing_fallback():
    """GIVEN venv_dir 不存在 bin/python WHEN _python_executable THEN 回退 sys.executable。"""
    ex = LocalExecutor(project_dir=".", venv_dir="/nonexistent/venv")
    assert ex._python_executable() == sys.executable
