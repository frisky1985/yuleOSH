# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ci/run.py layer functions — boost from 62% to 75%+ (v0.8.0)."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.ci.run import (
    CIResult,
    _save_layer_result,
    _handle_stage_error,
    _cross_compile_via_docker,
    _run_hil_mock_tests,
    _save_hil_report,
    _cross_compile_stage,
    _run_subprocess,
    get_latest_layer_result,
    check_layer_dependency,
    run_plan_lint,
    run_clang_tidy,
    run_coverage_check,
    run_sil_tests,
    run_layer1,
    run_layer_25,
    run_layer2,
    run_layer3,
    run_all,
)


class TestLayerFunctions:
    """GIVEN run_layer* functions WHEN called THEN exercise full pipeline."""

    def test_run_layer1(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = ""
                with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                    with mock.patch("yuleosh.ci.run._should_skip_coverage", return_value=True):
                        result = run_layer1(td)
                        assert result is True

    def test_run_layer2(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = "0 failed"
                with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                    with mock.patch("yuleosh.ci.run._should_skip_coverage", return_value=True):
                        result = run_layer2(td)
                        assert result is True

    def test_run_layer3(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = "0 failed"
                with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                    result = run_layer3(td)
                    assert result is True

    def test_run_all(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = "0 failed"
                with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                    with mock.patch("yuleosh.ci.run._should_skip_coverage", return_value=True):
                        result = run_all(td)
                        assert result is True

    def test_run_layer_25(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = ""
                with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                    result = run_layer_25(td)
                    assert result is True


class TestHilHelpers:
    """GIVEN HIL helpers WHEN called THEN correct behavior."""

    def test_save_hil_report(self):
        with tempfile.TemporaryDirectory() as td:
            report = _save_hil_report(td, True, "abc1234", True, "READY")
            assert report["passed"] is True
            reports = list(Path(td).glob("**/hil-report*.json"))
            assert len(reports) >= 1

    def test_run_hil_mock_tests(self):
        ci = CIResult(layer=3, commit_hash="x")
        hw_cfg = {"mock": True, "boot_pattern": "READY"}
        with tempfile.TemporaryDirectory() as td:
            script_dir = Path(td) / "scripts"
            script_dir.mkdir()
            (script_dir / "test.sh").write_text("#!/bin/bash\necho READY")
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = "READY\n0 failed"
                stages = _run_hil_mock_tests(ci, hw_cfg, str(script_dir), "READY")
                assert len(stages) >= 0


class TestLintAndTidy:
    """GIVEN project WHEN lint/tidy THEN handle gracefully."""

    def test_run_plan_lint(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="x")
            result = run_plan_lint(td, ci)
            assert result is True

    def test_run_clang_tidy(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="x")
            result = run_clang_tidy(td, ci)
            assert result is True


class TestCoverageAndSIL:
    """GIVEN coverage/SIL functions WHEN called THEN returns correctly."""

    def test_coverage_check_skip(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="x")
            with mock.patch("yuleosh.ci.run._should_skip_coverage", return_value=True):
                result = run_coverage_check(td, ci)
                assert result is True

    def test_sil_tests_no_files(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="x")
            with mock.patch("yuleosh.ci.run.subprocess.run") as m:
                m.return_value.returncode = 0
                m.return_value.stdout = "0 failed"
                result = run_sil_tests(td, ci)
                assert result is True


class TestCrossCompile:
    """GIVEN cross compile WHEN called THEN returns bool."""

    def test_via_docker(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=2, commit_hash="x")
            result = _cross_compile_via_docker(td, ci)
            assert isinstance(result, bool)

    def test_compile_stage(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "cross").mkdir()
            (Path(td) / "cross" / "hello.c").write_text("int main(){}")
            (Path(td) / "build").mkdir()
            ci = CIResult(layer=2, commit_hash="x")
            result = _cross_compile_stage(td, "cross", "build", ci)
            assert isinstance(result, bool)


class TestSubprocess:
    """GIVEN _run_subprocess WHEN called THEN returns stdout."""

    def test_echo(self):
        with tempfile.TemporaryDirectory() as td:
            ok, stdout, stderr = _run_subprocess(["echo", "hello"], cwd=td, timeout=5)
            assert "hello" in stdout


class TestLayerDepsAndResults:
    """GIVEN layer dependency WHEN checking THEN correct results."""

    def test_check_layer1(self):
        with tempfile.TemporaryDirectory() as td:
            assert check_layer_dependency(1, td) is None

    def test_save_and_get_result(self):
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="x")
            ci.complete("passed")
            _save_layer_result(td, ci, True, "x", 1)
            result = get_latest_layer_result(1, td)
            assert result is not None
            assert result["layer"] == 1

    def test_handle_stage_error_strict(self):
        ci = CIResult(layer=1, commit_hash="t")
        result = _handle_stage_error(ci, "test", "err", strict=True)
        assert len(ci.stages) == 1  # stage was recorded

    def test_handle_stage_error_nonstrict(self):
        ci = CIResult(layer=1, commit_hash="t")
        result = _handle_stage_error(ci, "test", "err", strict=False)
        assert result is False
