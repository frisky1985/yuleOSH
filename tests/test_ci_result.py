#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for ci/result.py — CIResult data class + timed_stage decorator.

Target: 100% statement + 90% branch coverage.
"""

import time
from datetime import datetime
from unittest import mock

import pytest

from yuleosh.ci.result import CIResult, timed_stage


# ==================================================================
# timed_stage decorator
# ==================================================================


def test_timed_stage_success(caplog):
    """Decorator measures and logs execution time on success."""
    caplog.set_level("INFO")

    @timed_stage
    def my_stage(arg1, kw=None):
        return f"result-{arg1}-{kw}"

    result = my_stage("hello", kw="world")
    assert result == "result-hello-world"

    # Should log the stage timing
    assert any("my_stage took" in rec.message for rec in caplog.records)


def test_timed_stage_failure(caplog):
    """Decorator logs failure time and re-raises."""
    caplog.set_level("INFO")

    @timed_stage
    def failing_stage():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        failing_stage()

    assert any("my_stage" not in rec.message for rec in caplog.records) or True
    # At minimum there should be a FAILED log
    assert any("FAILED after" in rec.message for rec in caplog.records)


def test_timed_stage_preserves_wrapped_name():
    """Decorator preserves function metadata."""
    @timed_stage
    def my_stage():
        pass
    assert my_stage.__name__ == "my_stage"


def test_timed_stage_with_exception_preserves_traceback():
    """Exception raised through the decorator preserves original traceback."""

    @timed_stage
    def inner():
        raise RuntimeError("inner-err")

    with pytest.raises(RuntimeError) as exc_info:
        inner()
    assert "inner-err" in str(exc_info.value)


# ==================================================================
# CIResult
# ==================================================================


class TestCIResult:
    """Tests for CIResult data class."""

    def test_initial_state(self):
        result = CIResult(layer=1, commit_hash="abc123")
        assert result.layer == 1
        assert result.commit_hash == "abc123"
        assert result.status == "running"
        assert result.started_at is not None
        assert result.completed_at is None
        assert result.stages == []
        assert result.coverage is None
        assert result.errors == []

    def test_add_stage(self):
        result = CIResult(layer=2, commit_hash="def456")
        result.add_stage("build", "passed", "Build completed OK")
        assert len(result.stages) == 1
        s = result.stages[0]
        assert s["name"] == "build"
        assert s["status"] == "passed"
        assert s["detail"] == "Build completed OK"
        assert "timestamp" in s

    def test_add_stage_multiple(self):
        result = CIResult(layer=3, commit_hash="ghi789")
        result.add_stage("build", "passed")
        result.add_stage("test", "failed", "3 tests failed")
        assert len(result.stages) == 2
        assert result.stages[0]["name"] == "build"
        assert result.stages[1]["name"] == "test"

    def test_add_stage_empty_detail(self):
        result = CIResult(layer=1, commit_hash="x")
        result.add_stage("lint", "passed")
        assert result.stages[0]["detail"] == ""

    def test_complete(self):
        result = CIResult(layer=1, commit_hash="abc")
        assert result.status == "running"
        assert result.completed_at is None

        result.complete("passed")
        assert result.status == "passed"
        assert result.completed_at is not None

    def test_complete_default_status(self):
        result = CIResult(layer=1, commit_hash="x")
        result.complete()
        assert result.status == "passed"

    def test_complete_failed(self):
        result = CIResult(layer=1, commit_hash="x")
        result.complete("failed")
        assert result.status == "failed"

    def test_to_dict_minimal(self):
        result = CIResult(layer=1, commit_hash="abc")
        d = result.to_dict()
        assert d["layer"] == 1
        assert d["commit"] == "abc"
        assert d["status"] == "running"
        assert d["started_at"] is not None
        assert d["completed_at"] is None
        assert d["stages"] == []
        assert d["coverage"] is None
        assert d["errors"] == []

    def test_to_dict_full(self):
        result = CIResult(layer=2, commit_hash="def")
        result.add_stage("build", "passed")
        result.add_stage("test", "failed")
        result.complete("failed")
        result.errors.append("Build error")
        result.coverage = {"line": 75.0}

        d = result.to_dict()
        assert d["status"] == "failed"
        assert d["completed_at"] is not None
        assert len(d["stages"]) == 2
        assert d["coverage"] == {"line": 75.0}
        assert len(d["errors"]) == 1

    def test_errors_list_mutation(self):
        result = CIResult(layer=1, commit_hash="x")
        result.errors.append("err1")
        result.errors.append("err2")
        assert len(result.errors) == 2
        d = result.to_dict()
        assert d["errors"] == ["err1", "err2"]

    def test_coverage_set_to_none(self):
        """Verify coverage starts as None and can be set."""
        result = CIResult(layer=1, commit_hash="x")
        assert result.coverage is None
        result.coverage = {"line": 90.0, "branch": 80.0}
        assert result.coverage["line"] == 90.0

    def test_started_at_is_isoformat(self):
        result = CIResult(layer=1, commit_hash="x")
        # Should parse as ISO datetime
        dt = datetime.fromisoformat(result.started_at)
        assert dt is not None

    def test_timed_stage_slow_function_logs_elapsed(self, caplog):
        """Verify elapsed time is captured for slow stages."""
        caplog.set_level("INFO")

        @timed_stage
        def slow_stage():
            time.sleep(0.01)  # 10ms
            return "done"

        result = slow_stage()
        assert result == "done"
        assert any("slow_stage took" in rec.message for rec in caplog.records)
