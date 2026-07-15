"""Depth tests for engine/ci_checkpoint.py — CI pipeline checkpoint creation and helper functions.

Covers:
  - create_ci_pipeline: all 4 layers (1, 2, 2.5, 3)
  - _wrap and _bool_wrap closures
  - Layer 2 helpers: _dummy_memory_check
  - Layer 2.5 helpers: _detect_hil_target_dummy, _hil_tests_wrapper, _save_hil_report_stub
  - Layer 3 helpers: _run_e2e_tests, _run_version_check, _run_evidence_pack
  - main(): CLI argument parsing, list-steps mode
  - Error case: unsupported layer
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.engine.ci_checkpoint import (
    create_ci_pipeline,
    _wrap,
    _bool_wrap,
    _dummy_memory_check,
    _detect_hil_target_dummy,
    _hil_tests_wrapper,
    _save_hil_report_stub,
    _run_e2e_tests,
    _run_version_check,
    _run_evidence_pack,
    main,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project():
    """Create a temporary project directory with minimal structure."""
    with tempfile.TemporaryDirectory() as tmp:
        # Set up minimal project structure
        src_dir = Path(tmp) / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        yield tmp


@pytest.fixture
def mock_ci_result():
    """Return a mock CIResult-like object."""
    m = mock.MagicMock()
    m.add_stage = mock.MagicMock()
    m.layer = 1
    m.name = "test"
    return m


# ── create_ci_pipeline ─────────────────────────────────────────────────

class TestCreateCiPipeline:
    def test_layer1_has_all_steps(self, tmp_project):
        """GIVEN layer 1 WHEN creating pipeline THEN has all 12 L1 steps."""
        engine = create_ci_pipeline(1, tmp_project)
        assert engine is not None
        assert engine._step_defs is not None
        step_ids = [s["step_id"] for s in engine._step_defs]
        expected = [
            "yaml-validation", "spec-validation", "architecture-review",
            "requirements-trace", "plan-lint", "docsync-gate",
            "clang-tidy", "misra-check",
            "unit-tests", "coverage", "c-coverage", "c-coverage-gate",
        ]
        for e in expected:
            assert e in step_ids, f"Missing L1 step: {e}"

    def test_layer2_has_all_steps(self, tmp_project):
        """GIVEN layer 2 WHEN creating pipeline THEN has 5 L2 steps."""
        engine = create_ci_pipeline(2, tmp_project)
        step_ids = [s["step_id"] for s in engine._step_defs]
        expected = ["cross-compile", "static-analysis", "sil-tests",
                     "integration-tests", "memory-safety"]
        for e in expected:
            assert e in step_ids, f"Missing L2 step: {e}"

    def test_layer_2_5_has_all_steps(self, tmp_project):
        """GIVEN layer 2.5 WHEN creating pipeline THEN has 3 L2.5 steps."""
        engine = create_ci_pipeline(2.5, tmp_project)
        step_ids = [s["step_id"] for s in engine._step_defs]
        expected = ["hil-target-detect", "hil-tests", "hil-report"]
        for e in expected:
            assert e in step_ids, f"Missing L2.5 step: {e}"

    def test_layer3_has_all_steps(self, tmp_project):
        """GIVEN layer 3 WHEN creating pipeline THEN has 3 L3 steps."""
        engine = create_ci_pipeline(3, tmp_project)
        step_ids = [s["step_id"] for s in engine._step_defs]
        expected = ["e2e-tests", "version-check", "evidence-pack"]
        for e in expected:
            assert e in step_ids, f"Missing L3 step: {e}"

    def test_unsupported_layer_raises(self, tmp_project):
        """GIVEN unsupported layer WHEN creating pipeline THEN raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported CI layer"):
            create_ci_pipeline(999, tmp_project)


# ── _wrap and _bool_wrap ──────────────────────────────────────────────

class TestWrapClosures:
    def test_wrap_returns_callable(self, tmp_project):
        """GIVEN _wrap with a simple handler WHEN called THEN returns a callable that returns a path."""
        def handler(pd, ci):
            ci.add_stage("test", "passed")
            return str(Path(pd) / ".osh" / "ci")

        wrapped = _wrap(handler, tmp_project, 1)
        result = wrapped()
        assert result is not None
        assert ".osh" in str(result)

    def test_bool_wrap_success(self, tmp_project):
        """GIVEN _bool_wrap with a returning-True handler WHEN called THEN returns path."""
        def handler(pd, ci):
            return True

        wrapped = _bool_wrap(handler, tmp_project, 1)
        result = wrapped()
        assert ".osh" in str(result)

    def test_bool_wrap_failure_raises(self, tmp_project):
        """GIVEN _bool_wrap with a returning-False handler WHEN called THEN raises RuntimeError."""
        def handler(pd, ci):
            return False

        wrapped = _bool_wrap(handler, tmp_project, 1)
        with pytest.raises(RuntimeError, match="Stage failed"):
            wrapped()

    def test_wrap_preserves_name(self, tmp_project):
        """GIVEN _wrap with a named function WHEN queried THEN preserves __name__."""
        def my_handler(pd, ci):
            return "ok"
        wrapped = _wrap(my_handler, tmp_project, 1)
        assert wrapped.__name__ == "my_handler"
        assert wrapped.__qualname__ == "my_handler"


# ── Layer 2 helpers ───────────────────────────────────────────────────

class TestLayer2Helpers:
    def test_dummy_memory_check_asan_dir_exists(self, tmp_project, mock_ci_result):
        """GIVEN asan directory exists WHEN _dummy_memory_check THEN True."""
        asan_dir = Path(tmp_project) / "tests" / "asan"
        asan_dir.mkdir(parents=True)
        result = _dummy_memory_check(tmp_project, mock_ci_result)
        assert result is True
        mock_ci_result.add_stage.assert_called_with("memory-safety", "info", mock.ANY)

    def test_dummy_memory_check_no_asan(self, tmp_project, mock_ci_result):
        """GIVEN no asan directory WHEN _dummy_memory_check THEN True with skipped."""
        result = _dummy_memory_check(tmp_project, mock_ci_result)
        assert result is True
        mock_ci_result.add_stage.assert_called_with("memory-safety", "skipped", mock.ANY)


# ── Layer 2.5 helpers ────────────────────────────────────────────────

class TestLayer25Helpers:
    def test_detect_hil_target_dummy(self, tmp_project, mock_ci_result):
        """GIVEN _detect_hil_target_dummy WHEN called THEN returns bool."""
        result = _detect_hil_target_dummy(tmp_project, mock_ci_result)
        assert result is True or result is False

    def test_hil_tests_wrapper(self, mock_ci_result):
        """GIVEN _hil_tests_wrapper WHEN called THEN returns True."""
        result = _hil_tests_wrapper("/tmp", mock_ci_result)
        assert result is True

    def test_save_hil_report_stub(self, tmp_project, mock_ci_result):
        """GIVEN _save_hil_report_stub WHEN called THEN returns True."""
        result = _save_hil_report_stub(tmp_project, mock_ci_result)
        assert result is True


# ── Layer 3 helpers ───────────────────────────────────────────────────

class TestLayer3Helpers:
    def test_run_e2e_tests_no_dir(self, tmp_project, mock_ci_result):
        """GIVEN no e2e test dir WHEN _run_e2e_tests THEN returns True (skipped)."""
        result = _run_e2e_tests(tmp_project, mock_ci_result)
        assert result is True

    def test_run_e2e_tests_with_dir_but_no_pytest(self, tmp_project, mock_ci_result):
        """GIVEN e2e dir but subprocess fails WHEN _run_e2e_tests THEN handles error."""
        e2e_dir = Path(tmp_project) / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_dummy.py").write_text("")
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("pytest not found")):
            result = _run_e2e_tests(tmp_project, mock_ci_result)
            assert result is False

    def test_run_e2e_tests_timeout(self, tmp_project, mock_ci_result):
        """GIVEN subprocess timeout WHEN _run_e2e_tests THEN returns False."""
        e2e_dir = Path(tmp_project) / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        import subprocess as sp
        with mock.patch("subprocess.run", side_effect=sp.TimeoutExpired("cmd", 120)):
            result = _run_e2e_tests(tmp_project, mock_ci_result)
            assert result is False

    def test_run_version_check_with_pyproject(self, tmp_project, mock_ci_result):
        """GIVEN pyproject.toml with version WHEN _run_version_check THEN passes."""
        pp = Path(tmp_project) / "pyproject.toml"
        pp.write_text('[project]\nversion = "1.2.3"\n')
        result = _run_version_check(tmp_project, mock_ci_result)
        assert result is True

    def test_run_version_check_no_pyproject(self, tmp_project, mock_ci_result):
        """GIVEN no pyproject.toml WHEN _run_version_check THEN skipped."""
        result = _run_version_check(tmp_project, mock_ci_result)
        assert result is True

    def test_run_evidence_pack_success(self, tmp_project, mock_ci_result):
        """GIVEN evidence module loads WHEN _run_evidence_pack THEN True."""
        with mock.patch("yuleosh.engine.ci_checkpoint.sys.path", []):
            with mock.patch.dict("sys.modules", {"evidence": mock.MagicMock()}):
                result = _run_evidence_pack(tmp_project, mock_ci_result)
                assert result is True

    def test_run_evidence_pack_failure(self, tmp_project, mock_ci_result):
        """GIVEN evidence module not found WHEN _run_evidence_pack THEN True (warning)."""
        result = _run_evidence_pack(tmp_project, mock_ci_result)
        assert result is True


# ── main() CLI ────────────────────────────────────────────────────────

class TestMainCLI:
    def test_main_list_steps(self, tmp_project):
        """GIVEN --list-steps flag WHEN main() THEN returns None (no exit)."""
        test_args = ["ci_checkpoint.py", "1", "--list-steps", "--project-dir", tmp_project]
        with mock.patch.object(sys, "argv", test_args):
            result = main()
            assert result is None

    def test_main_run_layer1(self, tmp_project):
        """GIVEN layer 1 with resume WHEN main() THEN exits."""
        test_args = ["ci_checkpoint.py", "1", "--resume", "--project-dir", tmp_project]
        with mock.patch.object(sys, "argv", test_args):
            with mock.patch("yuleosh.engine.ci_checkpoint.CheckpointEngine.run", return_value=True):
                result = main()
                assert result is None or result == 0

    def test_main_run_inject_at(self, tmp_project):
        """GIVEN --inject-at flag WHEN main() THEN runs with injection."""
        test_args = ["ci_checkpoint.py", "1", "--inject-at", "misra-check", "--project-dir", tmp_project]
        with mock.patch.object(sys, "argv", test_args):
            with mock.patch("yuleosh.engine.ci_checkpoint.CheckpointEngine.run", return_value=True):
                result = main()
                assert result is None or result == 0

    def test_main_layer2_5(self, tmp_project):
        """GIVEN layer 2.5 WHEN main() THEN runs."""
        test_args = ["ci_checkpoint.py", "2.5", "--project-dir", tmp_project]
        with mock.patch.object(sys, "argv", test_args):
            with mock.patch("yuleosh.engine.ci_checkpoint.CheckpointEngine.run", return_value=True):
                result = main()
                assert result is None or result == 0
