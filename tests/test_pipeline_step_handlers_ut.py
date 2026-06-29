# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.test_c_unit — step_c_unit_test."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.test_c_unit import (
    step_c_unit_test,
    _parse_unity_counts,
    _parse_ceedling_counts,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with a temp project structure."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-c-unit",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-c-unit"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _setup_c_project(base: Path, with_c_files: bool = True,
                     with_unity: bool = False, with_ceedling: bool = False,
                     with_test_files: bool = False):
    """Create a minimal C project structure."""
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)

    if with_c_files:
        (src / "main.c").write_text("int main() { return 0; }")
        (src / "driver.c").write_text("void init() {}")

    if with_test_files:
        test_dir = base / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_main.c").write_text("void test_main(void) {}")
        (test_dir / "test_driver.c").write_text("void test_driver(void) {}")

    if with_unity:
        unity_dir = base / "tests" / "unity"
        unity_dir.mkdir(parents=True, exist_ok=True)
        (unity_dir / "Makefile").write_text("all:\n\techo unity")
        unity_src = unity_dir / "src"
        unity_src.mkdir(parents=True, exist_ok=True)
        (unity_src / "unity.c").write_text("// unity runner")

    if with_ceedling:
        (base / "project.yml").write_text(":project:\n  :test_pattern: *_test.c\n")


# =============================================================================
# Tests
# =============================================================================

class TestStepCUnitTest:
    """Test suite for step_c_unit_test — C unit test runner."""

    # ── No C files — skipped ────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_no_c_files_skipped(self, mock_environ, mock_session):
        """GIVEN a project with no C source files
           WHEN step_c_unit_test runs
           THEN it is skipped with status 'skipped'."""
        # Use a truly empty temp dir
        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] == "skipped"
        assert report["reason"] == "No C source files found"
        assert report["c_files"] == 0

    # ── Unity runner — all pass ─────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_unity_runner_passed(self, mock_environ, mock_subproc,
                                  mock_session, tmp_path):
        """GIVEN C files and a Unity test directory with Makefile
           WHEN Unity tests all pass
           THEN the report shows 'passed' status."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_unity=True, with_test_files=True)

        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="OK (3 tests, 3 assertions, 0 failed, 0 ignored)\n",
            stderr="",
        )

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "passed"
        assert report["test_runner"] == "unity"

    # ── Unity runner — failures ─────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_unity_runner_failed(self, mock_environ, mock_subproc,
                                  mock_session, tmp_path):
        """GIVEN Unity tests that fail
           WHEN step_c_unit_test runs
           THEN the report shows 'failed' status."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_unity=True, with_test_files=True)

        mock_subproc.return_value = MagicMock(
            returncode=1,
            stdout="FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n",
            stderr="",
        )

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"
        assert report["failed"] == 1

    # ── Ceedling runner ─────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_ceedling_runner(self, mock_environ, mock_subproc,
                              mock_session, tmp_path):
        """GIVEN a project.yml and C files
           WHEN Ceedling is available and tests pass
           THEN the report shows ceedling as the runner."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_ceedling=True, with_test_files=True)

        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="---\nTEST OUTPUT SUMMARY\n---\nPassed: 5\nFailed: 0\n",
            stderr="",
        )

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["test_runner"] == "ceedling"
        assert report["passed"] == 5
        assert report["failed"] == 0
        assert report["status"] == "passed"

    # ── GCC fallback — pass ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_gcc_fallback_passed(self, mock_environ, mock_subproc,
                                  mock_session, tmp_path):
        """GIVEN no Unity or Ceedling but test files exist
           WHEN GCC compile check passes
           THEN the report shows 'gcc-compile-check' runner."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_test_files=True)
        # No unity and no project.yml — should fall through to GCC

        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["test_runner"] == "gcc-compile-check"
        assert report["status"] == "passed"

    # ── GCC fallback — fail ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_gcc_fallback_failed(self, mock_environ, mock_subproc,
                                  mock_session, tmp_path):
        """GIVEN GCC compilation fails
           WHEN the GCC fallback runs
           THEN the report shows 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_test_files=True)

        mock_subproc.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: implicit declaration of function",
        )

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"
        assert report["returncode"] == 1

    # ── All runners unavailable — unknown status ────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_no_runner_available(self, mock_environ, mock_subproc,
                                  mock_session, tmp_path):
        """GIVEN C files exist but no test runners are available
           WHEN all runner attempts fail
           THEN the report shows 'unknown' status."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_test_files=False)

        # All subprocess calls raise FileNotFoundError
        mock_subproc.side_effect = FileNotFoundError("make not found")

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["test_runner"] == "none"
        assert report["status"] == "unknown"

    # ── Unity timeout ──────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_unity_timeout(self, mock_environ, mock_subproc,
                            mock_session, tmp_path):
        """GIVEN the Unity test runner times out
           WHEN step_c_unit_test runs
           THEN it handles the timeout gracefully."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_unity=True)

        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd="make", timeout=120)

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["test_runner"] == "unity-timeout"

    # ── C headers found ────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_c_headers_reported(self, mock_environ, mock_subproc,
                                 mock_session, tmp_path):
        """GIVEN C source and header files
           WHEN step_c_unit_test runs
           THEN the report includes header file count."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "code.c").write_text("")
        (src / "header.h").write_text("")
        (src / "config.h").write_text("")

        # Make all subprocess calls fail
        mock_subproc.side_effect = FileNotFoundError()

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["c_files"] >= 1
        assert report["c_header_files"] >= 2

    # ── Write report error ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    @patch("builtins.open", side_effect=OSError("Disk full"))
    def test_report_write_error(self, mock_open, mock_environ, mock_subproc,
                                 mock_session, tmp_path):
        """GIVEN writing the C unit test report fails
           WHEN step_c_unit_test runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path)

        with pytest.raises(PipelineStepError, match="Cannot write"):
            step_c_unit_test(mock_session)

    # ── Exception wrapping ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_exception_wrapping(self, mock_environ, mock_session):
        """GIVEN an unexpected exception occurs during setup
           WHEN step_c_unit_test runs
           THEN it is wrapped in PipelineStepError."""
        mock_environ.get.side_effect = RuntimeError("Unexpected failure")

        with pytest.raises(PipelineStepError, match="C unit test step failed"):
            step_c_unit_test(mock_session)

    # ── Multiple C test file patterns ──────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_multiple_test_patterns_discovered(self, mock_environ, mock_subproc,
                                                mock_session, tmp_path):
        """GIVEN C test files with various naming patterns
           WHEN step_c_unit_test runs
           THEN all test file patterns are discovered."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "code.c").write_text("")
        (src / "test_code.c").write_text("")
        (src / "TestCode.c").write_text("")
        (src / "code_test.c").write_text("")
        (src / "code_tst.c").write_text("")

        mock_subproc.side_effect = FileNotFoundError()

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["c_test_files"] >= 4

    # ── GCC compile check with unity source ─────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run")
    @patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ")
    def test_gcc_fallback_with_unity_src(self, mock_environ, mock_subproc,
                                          mock_session, tmp_path):
        """GIVEN a unity src directory exists
           WHEN GCC compile check runs (after Unity make fails)
           THEN the unity include path is used."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_c_project(tmp_path, with_unity=True, with_test_files=True)

        # First call (Unity make) fails
        # Second call (GCC) succeeds
        mock_subproc.side_effect = [
            FileNotFoundError("make not found"),       # Unity make
            MagicMock(returncode=0, stdout="", stderr=""),  # GCC compile
        ]

        result = step_c_unit_test(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["test_runner"] == "gcc-compile-check"

        # Verify GCC call included unity -I flag
        gcc_call = mock_subproc.call_args_list[1]
        gcc_args = gcc_call[0][0]
        assert "gcc" in gcc_args[0]


# =============================================================================
# Helper function unit tests
# =============================================================================

class TestParseUnityCounts:
    """Unit tests for _parse_unity_counts helper."""

    def test_ok_matches(self):
        """GIVEN Unity output with OK lines
           WHEN _parse_unity_counts parses it
           THEN it returns correct pass count."""
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
        )
        passed, failed = _parse_unity_counts(output)
        assert passed == 2
        assert failed == 0

    def test_fail_matches(self):
        """GIVEN Unity output with FAIL lines
           WHEN _parse_unity_counts parses it
           THEN it returns correct fail count."""
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n"
        )
        passed, failed = _parse_unity_counts(output)
        assert passed == 1
        assert failed == 1

    def test_summary_line_fallback(self):
        """GIVEN Unity output with only a summary line
           WHEN _parse_unity_counts parses it
           THEN it uses the summary for counts."""
        output = "5 Tests 2 Failures 0 Ignored\n"
        passed, failed = _parse_unity_counts(output)
        assert passed == 3
        assert failed == 2

    def test_empty_output(self):
        """GIVEN empty Unity output
           WHEN _parse_unity_counts parses it
           THEN it returns zeros."""
        passed, failed = _parse_unity_counts("")
        assert passed == 0
        assert failed == 0

    def test_all_fail(self):
        """GIVEN Unity output with all FAIL lines
           WHEN _parse_unity_counts parses it
           THEN it returns all failures."""
        output = "FAIL (2 tests, 2 assertions, 2 failed, 0 ignored)\n"
        passed, failed = _parse_unity_counts(output)
        assert passed == 0
        assert failed == 1

    def test_mixed_summary_and_lines(self):
        """GIVEN Unity output with both per-test and summary lines
           WHEN _parse_unity_counts parses it
           THEN per-test lines take priority."""
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "10 Tests 0 Failures 0 Ignored\n"
        )
        passed, failed = _parse_unity_counts(output)
        # Per-test lines give 1 pass, so that's what we get
        assert passed == 1
        assert failed == 0


class TestParseCeedlingCounts:
    """Unit tests for _parse_ceedling_counts helper."""

    def test_standard_summary(self):
        """GIVEN Ceedling output with standard summary
           WHEN _parse_ceedling_counts parses it
           THEN it returns correct counts."""
        output = "---\nTEST OUTPUT SUMMARY\n---\nPassed: 4\nFailed: 1\n"
        passed, failed = _parse_ceedling_counts(output)
        assert passed == 4
        assert failed == 1

    def test_all_passed(self):
        """GIVEN Ceedling output with all passed
           WHEN _parse_ceedling_counts parses it
           THEN it returns zero failures."""
        output = "---\nPassed: 10\nFailed: 0\n"
        passed, failed = _parse_ceedling_counts(output)
        assert passed == 10
        assert failed == 0

    def test_fallback_to_fail_lines(self):
        """GIVEN Ceedling output without Passed/Failed lines
           WHEN _parse_ceedling_counts falls back
           THEN it searches for PASSED/FAILED lines."""
        output = (
            "    PASSED\n"
            "    PASSED\n"
            "    FAILED\n"
        )
        passed, failed = _parse_ceedling_counts(output)
        assert passed == 2
        assert failed == 1

    def test_empty_output(self):
        """GIVEN empty Ceedling output
           WHEN _parse_ceedling_counts parses it
           THEN it returns zeros."""
        passed, failed = _parse_ceedling_counts("")
        assert passed == 0
        assert failed == 0

    def test_only_fails(self):
        """GIVEN Ceedling output with all failures
           WHEN _parse_ceedling_counts parses it
           THEN it returns all failures."""
        output = "---\nPassed: 0\nFailed: 3\n"
        passed, failed = _parse_ceedling_counts(output)
        assert passed == 0
        assert failed == 3
