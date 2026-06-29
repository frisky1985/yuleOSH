# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.spec — step_spec_check."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.spec import step_spec_check


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession pointing at a temp dir."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-spec-check",
        spec_path=str(spec_file),
    )
    # Override session_dir to tmp_path for test isolation
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-spec-check"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _make_valid_payload(coverage_score: float = 85.0, error_count: int = 0):
    """Generate a realistic valid spec-check JSON payload."""
    return {
        "coverage": {"score": coverage_score},
        "error_count": error_count,
        "issues": [],
        "warnings": [],
    }


# =============================================================================
# Tests
# =============================================================================

class TestStepSpecCheck:
    """Test suite for step_spec_check — OpenSpec compliance validation."""

    # ── Happy path ──────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_happy_path_valid_spec(self, mock_run, mock_session):
        """GIVEN a valid spec file
           WHEN step_spec_check runs
           THEN it returns the output path and writes spec-check.json."""
        payload = _make_valid_payload(coverage_score=91.0)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        result = step_spec_check(mock_session)

        assert isinstance(result, str)
        out_file = Path(result)
        assert out_file.exists()
        assert out_file.name == "spec-check.json"
        written = json.loads(out_file.read_text())
        assert written["coverage"]["score"] == 91.0

        # Verify subprocess was invoked correctly
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert "-m" in args[0]
        assert "yuleosh.spec.validate" in args[0]

    # ── Error: subprocess non-zero return code ──────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_nonzero_return_code(self, mock_run, mock_session):
        """GIVEN the validator exits with non-zero
           WHEN step_spec_check runs
           THEN it raises PipelineStepError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Validation error: missing SHALL statements",
        )

        with pytest.raises(PipelineStepError, match="Spec validation failed"):
            step_spec_check(mock_session)

    # ── Error: subprocess TimeoutExpired ────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_subprocess_timeout(self, mock_run, mock_session):
        """GIVEN the validator subprocess times out
           WHEN step_spec_check runs
           THEN it raises PipelineStepError with timeout message."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="validate", timeout=30)

        with pytest.raises(PipelineStepError, match="timed out"):
            step_spec_check(mock_session)

    # ── Error: subprocess CalledProcessError ────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_called_process_error(self, mock_run, mock_session):
        """GIVEN the validator raises CalledProcessError
           WHEN step_spec_check runs
           THEN it raises PipelineStepError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=2, cmd="validate", stderr="process crashed"
        )

        with pytest.raises(PipelineStepError, match="subprocess failed"):
            step_spec_check(mock_session)

    # ── Error: non-JSON stdout ─────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_non_json_output(self, mock_run, mock_session):
        """GIVEN the validator returns non-JSON output
           WHEN step_spec_check runs
           THEN it raises PipelineStepError with JSONDecodeError message."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="this is not json",
            stderr="",
        )

        with pytest.raises(PipelineStepError, match="not valid JSON"):
            step_spec_check(mock_session)

    # ── Error: JSON with error_count > 0 ───────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_json_with_errors(self, mock_run, mock_session):
        """GIVEN the validator returns JSON with error_count > 0
           WHEN step_spec_check runs
           THEN it raises PipelineStepError with error details."""
        payload = {
            "coverage": {"score": 45.0},
            "error_count": 2,
            "issues": [
                {"severity": "ERROR", "message": "Missing requirement SHALL-001"},
                {"severity": "ERROR", "message": "Invalid scenario format"},
                {"severity": "WARNING", "message": "Low coverage"},
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with pytest.raises(PipelineStepError, match="2 error"):
            step_spec_check(mock_session)

    # ── Edge: only WARNING issues, no ERROR ─────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_warnings_only_no_error_raise(self, mock_run, mock_session):
        """GIVEN the validator returns only WARNING issues (zero errors)
           WHEN step_spec_check runs
           THEN it succeeds and returns the output path."""
        payload = {
            "coverage": {"score": 72.0},
            "error_count": 0,
            "issues": [
                {"severity": "WARNING", "message": "Coverage below 80%"},
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        result = step_spec_check(mock_session)
        out_file = Path(result)
        written = json.loads(out_file.read_text())
        assert written["coverage"]["score"] == 72.0

    # ── Edge: empty stdout ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_empty_stdout(self, mock_run, mock_session):
        """GIVEN the validator returns empty stdout and non-zero return code
           WHEN step_spec_check runs
           THEN it raises PipelineStepError."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="",
        )

        with pytest.raises(PipelineStepError, match="Unknown error"):
            step_spec_check(mock_session)

    # ── Edge: missing coverage field in JSON ───────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_missing_coverage_field(self, mock_run, mock_session):
        """GIVEN the validator JSON lacks expected fields
           WHEN step_spec_check runs
           THEN it raises PipelineStepError on KeyError (internally caught)."""
        payload = {"error_count": 0}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with pytest.raises(PipelineStepError, match="unexpected error"):
            step_spec_check(mock_session)

    # ── Edge: output file write error ──────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    @patch("builtins.open", side_effect=OSError("Permission denied"))
    def test_output_write_error(self, mock_open, mock_run, mock_session):
        """GIVEN writing the output file fails
           WHEN step_spec_check runs
           THEN it raises PipelineStepError."""
        payload = _make_valid_payload()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with pytest.raises(PipelineStepError, match="unexpected error"):
            step_spec_check(mock_session)

    # ── Error output captured when return code != 0 ────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_stderr_captured_in_output_file(self, mock_run, mock_session):
        """GIVEN the validator fails with stderr output
           WHEN step_spec_check raises
           THEN the output file still contains the error text (written before raise)."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="line1: error\nline2: missing SHALL",
        )

        with pytest.raises(PipelineStepError):
            step_spec_check(mock_session)

        out_file = mock_session.session_dir / "spec-check.json"
        assert out_file.exists()
        assert "line1: error" in out_file.read_text()

    # ── Error: unhandled exception ─────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_unexpected_exception_wrapping(self, mock_run, mock_session):
        """GIVEN an unexpected exception occurs
           WHEN step_spec_check runs
           THEN it is wrapped in PipelineStepError."""
        mock_run.side_effect = RuntimeError("Something went terribly wrong")

        with pytest.raises(PipelineStepError, match="unexpected error"):
            step_spec_check(mock_session)

    # ── Coverage score printed to console ──────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_coverage_score_in_stdout(self, mock_run, mock_session, capsys):
        """GIVEN a valid spec with 67% coverage
           WHEN step_spec_check succeeds
           THEN the coverage score is printed to stdout."""
        payload = _make_valid_payload(coverage_score=67.0)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        step_spec_check(mock_session)
        captured = capsys.readouterr()
        assert "67.0%" in captured.out

    # ── Verify session_dir path ────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_output_in_correct_session_dir(self, mock_run, mock_session):
        """GIVEN a session with a custom session_dir
           WHEN step_spec_check succeeds
           THEN the output file is placed in that session_dir."""
        payload = _make_valid_payload()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        result = step_spec_check(mock_session)
        result_path = Path(result)
        assert result_path.parent == mock_session.session_dir

    # ── Multiple issues concatenated in error message ──────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_multiple_issues_concatenated(self, mock_run, mock_session):
        """GIVEN multiple ERROR issues in the validation result
           WHEN step_spec_check fails
           THEN all error messages appear in the exception."""
        payload = {
            "coverage": {"score": 30.0},
            "error_count": 3,
            "issues": [
                {"severity": "ERROR", "message": "Err-A"},
                {"severity": "ERROR", "message": "Err-B"},
                {"severity": "ERROR", "message": "Err-C"},
            ],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with pytest.raises(PipelineStepError) as exc_info:
            step_spec_check(mock_session)
        msg = str(exc_info.value)
        assert "Err-A" in msg
        assert "Err-B" in msg
        assert "Err-C" in msg

    # ── Session spec_path resolved correctly ───────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.spec.subprocess.run")
    def test_spec_path_passed_to_subprocess(self, mock_run, mock_session):
        """GIVEN a session with a spec_path
           WHEN step_spec_check runs
           THEN the spec path is passed to the subprocess."""
        payload = _make_valid_payload()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        step_spec_check(mock_session)

        call_args = mock_run.call_args[0][0]
        assert mock_session.spec_path in call_args
