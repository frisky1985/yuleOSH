
# @tests src/yuleosh/pipeline/step_handlers/test_python_unit.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for test_python_unit step handler (H2-3)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.test_python_unit import (
    step_python_unit_test,
    run_python_test_suite,
    _find_python_test_files,
    _parse_pytest_counts,
    _parse_unittest_counts,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def session(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n")
    s = PipelineSession(name="test-py-unit", spec_path=str(spec))
    s.session_dir = tmp_path / ".osh" / "sessions" / "test-py-unit"
    s.session_dir.mkdir(parents=True, exist_ok=True)
    s.token_usage_total = 0
    s.token_usage_steps = []
    return s


def _write_test_file(project_dir: Path, name: str = "test_foo.py") -> Path:
    (project_dir / "tests").mkdir(exist_ok=True)
    p = project_dir / "tests" / name
    p.write_text("def test_example(): assert 1 + 1 == 2\n")
    return p


# ── _find_python_test_files ───────────────────────────────────────────────────

class TestFindPythonTestFiles:
    def test_finds_test_prefix(self, tmp_path):
        _write_test_file(tmp_path, "test_foo.py")
        files = _find_python_test_files(tmp_path)
        assert any(f.name == "test_foo.py" for f in files)

    def test_finds_test_suffix(self, tmp_path):
        (tmp_path / "foo_test.py").write_text("def test_x(): pass\n")
        files = _find_python_test_files(tmp_path)
        assert any(f.name == "foo_test.py" for f in files)

    def test_ignores_non_test_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        files = _find_python_test_files(tmp_path)
        assert not any(f.name == "main.py" for f in files)

    def test_excludes_venv_dir(self, tmp_path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "test_inside_venv.py").write_text("def test_x(): pass\n")
        files = _find_python_test_files(tmp_path)
        assert not any(".venv" in str(f) for f in files)

    def test_excludes_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "test_cached.py").write_text("def test_x(): pass\n")
        files = _find_python_test_files(tmp_path)
        assert not any("__pycache__" in str(f) for f in files)

    def test_empty_project_returns_empty(self, tmp_path):
        assert _find_python_test_files(tmp_path) == []


# ── _parse_pytest_counts / _parse_unittest_counts ────────────────────────────

class TestParseCounts:
    def test_pytest_all_passed(self):
        out = "5 passed in 0.12s"
        assert _parse_pytest_counts(out) == (5, 0)

    def test_pytest_mixed(self):
        out = "3 passed, 2 failed in 0.30s"
        assert _parse_pytest_counts(out) == (3, 2)

    def test_pytest_empty_output(self):
        assert _parse_pytest_counts("") == (0, 0)

    def test_unittest_ran_ok(self):
        out = "Ran 4 tests in 0.001s\n\nOK\n"
        passed, failed = _parse_unittest_counts(out)
        assert passed == 4
        assert failed == 0

    def test_unittest_with_failures(self):
        out = "Ran 5 tests in 0.005s\n\nFAILED (failures=2)\n"
        passed, failed = _parse_unittest_counts(out)
        assert failed == 2
        assert passed == 3

    def test_unittest_with_errors(self):
        out = "Ran 3 tests in 0.003s\n\nFAILED (errors=1)\n"
        passed, failed = _parse_unittest_counts(out)
        assert failed == 1
        assert passed == 2


# ── run_python_test_suite ────────────────────────────────────────────────────

class TestRunPythonTestSuite:
    def test_no_test_files_returns_skipped(self, tmp_path):
        result = run_python_test_suite(tmp_path)
        assert result["status"] == "skipped"
        assert result["runner"] == "none"
        assert result["py_test_files"] == 0

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.subprocess.run")
    def test_pytest_success(self, mock_run, tmp_path):
        _write_test_file(tmp_path)
        # probe: pytest --version succeeds
        # run: pytest passes
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="pytest 8.0", stderr=""),
            MagicMock(returncode=0, stdout="1 passed in 0.01s", stderr=""),
        ]
        result = run_python_test_suite(tmp_path)
        assert result["runner"] == "pytest"
        assert result["status"] == "passed"
        assert result["passed"] == 1
        assert result["failed"] == 0

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.subprocess.run")
    def test_pytest_failure(self, mock_run, tmp_path):
        _write_test_file(tmp_path)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="pytest 8.0", stderr=""),
            MagicMock(returncode=1, stdout="1 passed, 2 failed in 0.02s", stderr=""),
        ]
        result = run_python_test_suite(tmp_path)
        assert result["runner"] == "pytest"
        assert result["status"] == "failed"
        assert result["failed"] == 2

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.subprocess.run")
    def test_fallback_to_unittest_when_no_pytest(self, mock_run, tmp_path):
        _write_test_file(tmp_path)
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=""),  # pytest probe fails
            MagicMock(returncode=0, stdout="Ran 2 tests\n\nOK\n", stderr=""),
        ]
        result = run_python_test_suite(tmp_path)
        assert result["runner"] == "unittest"
        assert result["status"] == "passed"

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.subprocess.run")
    def test_pytest_timeout_returns_failed(self, mock_run, tmp_path):
        import subprocess as _sp
        _write_test_file(tmp_path)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="pytest 8.0", stderr=""),
            _sp.TimeoutExpired(cmd="pytest", timeout=1),
        ]
        result = run_python_test_suite(tmp_path, timeout=1)
        assert result["runner"] == "pytest-timeout"
        assert result["status"] == "failed"


# ── step_python_unit_test ────────────────────────────────────────────────────

class TestStepPythonUnitTest:
    def test_mock_mode_skips(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.mock_mode = True

        result = step_python_unit_test(session)

        out = Path(result)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["status"] == "skipped"
        assert data["reason"] == "mock mode — no real code to test"

    def test_no_test_files_skips(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.project_dir = str(tmp_path)

        result = step_python_unit_test(session)

        data = json.loads(Path(result).read_text())
        assert data["status"] == "skipped"
        assert data["test_runner"] == "none"

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.run_python_test_suite")
    def test_passed_writes_artifact(self, mock_suite, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.project_dir = str(tmp_path)
        mock_suite.return_value = {
            "runner": "pytest", "returncode": 0,
            "passed": 5, "failed": 0,
            "output": "5 passed", "status": "passed",
            "py_test_files": 2, "junit_xml_path": "",
        }

        result = step_python_unit_test(session)

        out = Path(result)
        assert out.name == "python-unit-test.json"
        data = json.loads(out.read_text())
        assert data["status"] == "passed"
        assert data["passed"] == 5
        assert "python-unit-test" in session.artifacts

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.run_python_test_suite")
    def test_failed_raises_pipeline_step_error(self, mock_suite, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.project_dir = str(tmp_path)
        mock_suite.return_value = {
            "runner": "pytest", "returncode": 1,
            "passed": 3, "failed": 2,
            "output": "3 passed, 2 failed", "status": "failed",
            "py_test_files": 3, "junit_xml_path": "",
        }

        with pytest.raises(PipelineStepError, match="Python unit tests failed"):
            step_python_unit_test(session)

    @patch("yuleosh.pipeline.step_handlers.test_python_unit.run_python_test_suite")
    def test_report_includes_junit_path(self, mock_suite, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.project_dir = str(tmp_path)
        junit = str(tmp_path / "junit.xml")
        mock_suite.return_value = {
            "runner": "pytest", "returncode": 0,
            "passed": 1, "failed": 0,
            "output": "1 passed", "status": "passed",
            "py_test_files": 1, "junit_xml_path": junit,
        }

        result = step_python_unit_test(session)

        data = json.loads(Path(result).read_text())
        assert data["junit_xml_path"] == junit
