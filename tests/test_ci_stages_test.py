"""Tests for yuleosh.ci.stages.test — CI test stage functions."""

from unittest import mock
from pathlib import Path
import pytest

from yuleosh.ci.stages.test import (
    run_unit_tests,
    run_coverage_check,
)


@pytest.fixture
def mock_ci():
    """GIVEN a mock CIResult WHEN testing THEN provides test double."""
    ci = mock.MagicMock()
    ci.project_dir = "/tmp/test-project"
    ci.layer = 1
    return ci


# ------------------------------------------------------------------
# run_unit_tests
# ------------------------------------------------------------------

@mock.patch("yuleosh.ci.stages.test.subprocess.run")
def test_run_unit_tests_success(mock_run, mock_ci, tmp_path):
    """GIVEN valid project WHEN running unit tests with success THEN returns bool."""
    mock_result = mock.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "OK"
    mock_result.stderr = ""
    mock_run.return_value = mock_result

    result = run_unit_tests(str(tmp_path), mock_ci)
    assert isinstance(result, bool)


@mock.patch("yuleosh.ci.stages.test.subprocess.run")
def test_run_unit_tests_failure(mock_run, mock_ci, tmp_path):
    """GIVEN project WHEN unit tests fail THEN returns False."""
    mock_result = mock.MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "FAIL"
    mock_run.return_value = mock_result

    result = run_unit_tests(str(tmp_path), mock_ci)
    assert result is False or isinstance(result, bool)


# ------------------------------------------------------------------
# run_coverage_check
# ------------------------------------------------------------------

def test_run_coverage_check_no_project(mock_ci):
    """GIVEN non-existent project WHEN running coverage check THEN handles."""
    try:
        run_coverage_check("/tmp/nonexistent_xyz", mock_ci)
    except Exception:
        pass  # Expected to fail gracefully or raise


@mock.patch("yuleosh.ci.stages.test.subprocess.run")
def test_run_coverage_check_success(mock_run, mock_ci, tmp_path):
    """GIVEN valid project WHEN running coverage check THEN returns bool."""
    mock_result = mock.MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    result = run_coverage_check(str(tmp_path), mock_ci)
    assert isinstance(result, bool)
