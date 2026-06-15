# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep coverage tests for step_handlers/spec.py — branches not covered by
existing tests.

Target: spec.py from 65% → ≥80%

Covers:
  - subprocess.TimeoutExpired handler (lines 62-64)
  - subprocess.CalledProcessError handler (lines 65-67)
  - Generic Exception handler (lines 70-72)
  - returncode != 0 path (lines 38-41)
  - error_count > 0 path (lines 53-57)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Create a minimal PipelineSession for spec testing."""
    from yuleosh.pipeline.step_handlers.spec import step_spec_check
    from yuleosh.pipeline.session import PipelineSession

    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Test Spec\nSome content")
    session = PipelineSession("spec-deep-test", str(spec_file))
    return session


class SubprocessResult:
    """Fake subprocess.CompletedProcess."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ===================================================================
# spec.py — uncovered branches
# ===================================================================


class TestSpecReturncodeNonZero:
    """GIVEN subprocess returns non-zero exit code
    WHEN step_spec_check runs
    THEN PipelineStepError is raised with validation failure message."""

    def test_returncode_nonzero(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            return_value=SubprocessResult(returncode=1, stdout="", stderr="Validation error: missing SHALL"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "Spec validation failed" in str(exc.value)

    def test_returncode_nonzero_empty_stderr(self, tmp_session):
        """If both stderr and stdout empty, 'Unknown error' is used."""
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            return_value=SubprocessResult(returncode=2, stdout="", stderr=""),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "Unknown error" in str(exc.value)


class TestSpecNonZeroErrorCount:
    """GIVEN subprocess returns valid JSON with error_count > 0
    WHEN step_spec_check runs
    THEN PipelineStepError is raised listing the errors."""

    def test_error_count_positive(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        data = {
            "error_count": 2,
            "issues": [
                {"severity": "ERROR", "message": "Missing RS-001"},
                {"severity": "ERROR", "message": "Invalid SWR-002"},
            ],
            "coverage": {"score": 50},
        }
        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            return_value=SubprocessResult(returncode=0, stdout=json.dumps(data)),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "Missing RS-001" in str(exc.value)
            assert "Invalid SWR-002" in str(exc.value)

    def test_error_count_mixed_severity(self, tmp_session):
        """Only ERROR severity issues are included in the error message."""
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        data = {
            "error_count": 1,
            "issues": [
                {"severity": "ERROR", "message": "Critical issue"},
                {"severity": "WARNING", "message": "Minor warning"},
            ],
            "coverage": {"score": 70},
        }
        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            return_value=SubprocessResult(returncode=0, stdout=json.dumps(data)),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "Critical issue" in str(exc.value)
            assert "Minor warning" not in str(exc.value)


class TestSpecTimeoutExpired:
    """GIVEN subprocess raises subprocess.TimeoutExpired
    WHEN step_spec_check runs
    THEN PipelineStepError is raised with timeout message."""

    def test_timeout(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="test", timeout=10),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "timed out" in str(exc.value).lower()


class TestSpecCalledProcessError:
    """GIVEN subprocess raises subprocess.CalledProcessError
    WHEN step_spec_check runs
    THEN PipelineStepError is raised with subprocess error message."""

    def test_called_process_error(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            side_effect=subprocess.CalledProcessError(returncode=1, cmd="test"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "subprocess failed" in str(exc.value).lower()


class TestSpecGenericException:
    """GIVEN subprocess raises an unexpected Exception
    WHEN step_spec_check runs
    THEN PipelineStepError is raised with unexpected error message."""

    def test_generic_exception(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            side_effect=PermissionError("Access denied"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_spec_check(tmp_session)
            assert "unexpected error" in str(exc.value).lower()


class TestSpecHappyPath:
    """GIVEN everything works
    WHEN step_spec_check runs
    THEN it returns the output path."""

    def test_happy_path(self, tmp_session):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check

        data = {
            "error_count": 0,
            "issues": [],
            "coverage": {"score": 95},
        }
        with mock.patch(
            "yuleosh.pipeline.step_handlers.spec.subprocess.run",
            return_value=SubprocessResult(returncode=0, stdout=json.dumps(data)),
        ):
            result = step_spec_check(tmp_session)
            assert result is not None
            assert Path(result).exists()
