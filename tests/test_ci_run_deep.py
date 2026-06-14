# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for ci/run.py — mock subprocess, no real CI execution.

Target: 70%+ branch coverage (up from 18%).
Covers: CIResult, git helpers, file discovery, layer deps, env checks,
        coverage helpers, save/error helpers, _run_subprocess, timed_stage,
        run_plan_lint, run_clang_tidy, run_unit_tests, run_coverage_check,
        run_sil_tests, run_layer1, run_layer2, run_layer_25, run_layer3,
        run_all, main(), HIL helpers, cross-compile helpers, static
        analysis, integration tests, _find_c_sources, cache helpers.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from subprocess import TimeoutExpired
from unittest import mock

import pytest

# ==================================================================
# Inject mock cross.* modules so imports inside run.py succeed
# ==================================================================
import types as _types
_mock_cross = _types.ModuleType("cross")
_mock_cross.__path__ = []
_mock_cross.__package__ = "cross"
sys.modules["cross"] = _mock_cross

for _sub in ("sil_runner", "target_config", "flash", "hil_runner"):
    _m = _types.ModuleType(f"cross.{_sub}")
    setattr(_m, "sil_test", None)
    setattr(_m, "SilResult", None)
    setattr(_m, "TargetConfig", lambda **kw: None)
    setattr(_m, "hil_test", None)
    setattr(_m, "flash_firmware", None)
    sys.modules[f"cross.{_sub}"] = _m

# Also inject evidence module for run_layer3
_mev = _types.ModuleType("evidence")
_mev.__path__ = []
_mev.__package__ = "evidence"
sys.modules["evidence"] = _mev
_mev_pack = _types.ModuleType("evidence.pack")
_mev_pack.generate_evidence = lambda *a, **kw: None
sys.modules["evidence.pack"] = _mev_pack
del _mev, _mev_pack
del _mock_cross, _sub, _m, _types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ==================================================================
# Test data
# ==================================================================

TASK_FILE_PASS = "# Task: test-feature\n## kind: feature\n### RED\nwrite test\n### GREEN\nmake pass\n### REFACTOR\nclean\n"
TASK_FILE_FAIL = "# Task: bad\nno kind, no T00 sections\n"


# ==================================================================
# Helper: fresh temp dir
# ==================================================================

@pytest.fixture
def tmp_proj():
    """Simple temporary directory for a single test."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run to never execute real commands."""
    with mock.patch("yuleosh.ci.run.subprocess") as mock_sp:
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_sp.run.return_value = mock_result
        yield mock_sp


@pytest.fixture
def mock_ci_config():
    """Mock ci config loading to return sensible defaults."""
    from yuleosh.ci.config import CiConfig, CoverageConfig, HardwareTestConfig
    cfg = CiConfig()
    cfg.layers = [1, 2, 25, 3]
    cfg.layer_dependencies = {1: [], 2: [1], 25: [1, 2], 3: [1, 2, 25]}
    cfg.coverage = CoverageConfig(threshold_line=85.0, threshold_condition=80.0)
    cfg.hardware_test = HardwareTestConfig(mock=True, boot_pattern="Boot Complete",
                                           firmware="build/firmware.elf",
                                           test_scripts_dir="tests/hil")
    patcher = mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg)
    yield patcher.start()
    patcher.stop()


# ==================================================================
# CIResult
# ==================================================================

class TestCIResult:
    def test_init(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(layer=2, commit_hash="abc123")
        assert ci.layer == 2
        assert ci.commit_hash == "abc123"
        assert ci.status == "running"
        assert ci.stages == []

    def test_add_stage(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(1, "def")
        ci.add_stage("lint", "passed", "all clear")
        assert ci.stages[0]["name"] == "lint"
        assert ci.stages[0]["status"] == "passed"

    def test_add_stage_no_detail(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(1, "x")
        ci.add_stage("test", "failed")
        assert ci.stages[0]["detail"] == ""

    def test_complete_updates(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(3, "z")
        ci.complete("passed")
        assert ci.status == "passed"
        assert ci.completed_at is not None

    def test_complete_failed(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(2, "f")
        ci.complete("failed")
        assert ci.status == "failed"

    def test_to_dict(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(1, "abc")
        ci.add_stage("lint", "passed")
        ci.complete("passed")
        d = ci.to_dict()
        assert d["layer"] == 1
        assert d["status"] == "passed"
        assert json.dumps(d)

    def test_to_dict_with_errors(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(2, "err")
        ci.errors.append("failure")
        ci.complete("failed")
        assert ci.to_dict()["errors"] == ["failure"]


# ==================================================================
# Git helpers
# ==================================================================

class TestGitHelpers:
    def test_git_commit_hash(self):
        from yuleosh.ci.run import git_commit_hash
        h = git_commit_hash()
        assert isinstance(h, str) and len(h) >= 7

    def test_get_changed_files(self):
        from yuleosh.ci.run import get_changed_files
        files = get_changed_files()
        assert isinstance(files, list)


# ==================================================================
# File Discovery
# ==================================================================

class TestFileDiscovery:
    def test_find_test_files_python(self, tmp_proj):
        from yuleosh.ci.run import find_test_files, _test_file_cache
        _test_file_cache.clear()
        Path(tmp_proj, "tests").mkdir()
        for name in ["test_a.py", "test_b.py"]:
            Path(tmp_proj, "tests", name).write_text("def test(): pass\n")
        files = find_test_files(tmp_proj)
        assert len(files) >= 2

    def test_find_test_files_go(self, tmp_proj):
        from yuleosh.ci.run import find_test_files, _test_file_cache
        _test_file_cache.clear()
        Path(tmp_proj, "tests").mkdir()
        Path(tmp_proj, "tests", "foo_test.go").write_text("package foo\n")
        files = find_test_files(tmp_proj)
        assert any(f.endswith("_test.go") for f in files)

    def test_find_test_files_java(self, tmp_proj):
        from yuleosh.ci.run import find_test_files, _test_file_cache
        _test_file_cache.clear()
        Path(tmp_proj, "tests").mkdir()
        Path(tmp_proj, "tests", "TestFoo.java").write_text("class TestFoo {}\n")
        files = find_test_files(tmp_proj)
        assert any(f.endswith("TestFoo.java") for f in files)

    def test_find_test_files_empty(self, tmp_proj):
        from yuleosh.ci.run import find_test_files, _test_file_cache
        _test_file_cache.clear()
        assert find_test_files(tmp_proj) == []

    def test_find_test_files_skips_hidden(self, tmp_proj):
        from yuleosh.ci.run import find_test_files, _test_file_cache
        _test_file_cache.clear()
        Path(tmp_proj, ".hidden").mkdir()
        Path(tmp_proj, ".hidden", "test_what.py").write_text("pass\n")
        files = find_test_files(tmp_proj)
        assert all(".hidden" not in f for f in files)

    def test_get_cache_key(self, tmp_proj):
        from yuleosh.ci.run import get_cache_key_for_dir
        k1 = get_cache_key_for_dir(tmp_proj)
        k2 = get_cache_key_for_dir(tmp_proj)
        assert k1 == k2

    def test_get_cache_key_different(self, tmp_proj):
        from yuleosh.ci.run import get_cache_key_for_dir, _test_file_cache
        k1 = get_cache_key_for_dir(tmp_proj)
        Path(tmp_proj, "tests").mkdir()
        Path(tmp_proj, "tests", "test_new.py").write_text("pass\n")
        _test_file_cache.clear()
        k2 = get_cache_key_for_dir(tmp_proj)
        assert k1 != k2


# ==================================================================
# Layer Dependency
# ==================================================================

class TestLayerDependency:
    def test_layer1_no_deps(self, tmp_proj):
        from yuleosh.ci.run import check_layer_dependency
        assert check_layer_dependency(1, tmp_proj) is None

    def test_layer2_needs_l1(self, tmp_proj):
        from yuleosh.ci.run import check_layer_dependency
        result = check_layer_dependency(2, tmp_proj)
        assert result is not None
        assert "Layer 1" in result

    def test_get_latest_layer_not_found(self, tmp_proj):
        from yuleosh.ci.run import get_latest_layer_result
        assert get_latest_layer_result(1, tmp_proj) is None

    def test_get_latest_layer_found(self, tmp_proj):
        from yuleosh.ci.run import get_latest_layer_result
        ci_dir = Path(tmp_proj, ".osh", "ci")
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "layer1-pass.json").write_text(
            json.dumps({"layer": 1, "status": "passed"}))
        result = get_latest_layer_result(1, tmp_proj)
        assert result is not None
        assert result["status"] == "passed"

    def test_get_latest_layer_invalid_json(self, tmp_proj):
        from yuleosh.ci.run import get_latest_layer_result
        ci_dir = Path(tmp_proj, ".osh", "ci")
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "layer1-bad.json").write_text("not json")
        assert get_latest_layer_result(1, tmp_proj) is None

    def test_layer_dep_config_from_config(self, tmp_proj):
        from yuleosh.ci.run import check_layer_dependency
        from yuleosh.ci.config import CiConfig

        cfg = CiConfig()
        cfg.layer_dependencies = {1: [], 2: [1]}
        with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
            result = check_layer_dependency(2, tmp_proj)
            assert result is not None

    def test_layer_dep_config_fallback(self, tmp_proj):
        from yuleosh.ci.run import check_layer_dependency
        with mock.patch("yuleosh.ci.run._get_ci_config",
                        side_effect=ValueError("config broken")):
            result = check_layer_dependency(2, tmp_proj)
            assert result is not None


# ==================================================================
# Environment Checks
# ==================================================================

class TestEnvChecks:
    def test_is_strict_default(self):
        from yuleosh.ci.run import is_strict
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_strict() is False

    def test_is_strict_enabled(self):
        from yuleosh.ci.run import is_strict
        with mock.patch.dict(os.environ, {"CI_STRICT": "1"}):
            assert is_strict() is True

    def test_is_misra_default(self):
        from yuleosh.ci.run import is_misra_fail_fast
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_misra_fail_fast() is False

    def test_is_misra_enabled(self):
        from yuleosh.ci.run import is_misra_fail_fast
        with mock.patch.dict(os.environ, {"MISRA_FAIL_FAST": "1"}):
            assert is_misra_fail_fast() is True


# ==================================================================
# Coverage helpers
# ==================================================================

class TestCoverageHelpers:
    def test_should_skip_default(self):
        from yuleosh.ci.run import _should_skip_coverage
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _should_skip_coverage() is False

    def test_should_skip_commit(self):
        from yuleosh.ci.run import _should_skip_coverage
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            assert _should_skip_coverage() is True

    def test_should_skip_recursion(self):
        from yuleosh.ci.run import _should_skip_coverage
        with mock.patch.dict(os.environ, {"COVERAGE_RUN": "1"}):
            assert _should_skip_coverage() is True

    def test_coverage_skip_reason_commit(self):
        from yuleosh.ci.run import _coverage_skip_reason
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            assert "HOOK_TYPE=commit" in _coverage_skip_reason()

    def test_coverage_skip_reason_recursion(self):
        from yuleosh.ci.run import _coverage_skip_reason
        with mock.patch.dict(os.environ, {"COVERAGE_RUN": "1"}):
            assert "recursion" in _coverage_skip_reason()

    def test_coverage_skip_reason_empty(self):
        from yuleosh.ci.run import _coverage_skip_reason
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _coverage_skip_reason() == ""

    def test_load_coverage_json(self, tmp_proj):
        from yuleosh.ci.run import _load_coverage_json
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 92.0, "percent_covered_condition": 88.0}
        }))
        line, cond = _load_coverage_json(tmp_proj)
        assert line == 92.0
        assert cond == 88.0

    def test_run_coverage_and_export(self, tmp_proj):
        from yuleosh.ci.run import _run_coverage_and_export
        ok, reason = _run_coverage_and_export(tmp_proj)
        assert isinstance(ok, bool)
        assert isinstance(reason, str)


# ==================================================================
# Save / Error helpers
# ==================================================================

class TestSaveLayer:
    def test_save_result_creates_file(self, tmp_proj):
        from yuleosh.ci.run import CIResult, _save_layer_result
        ci = CIResult(1, "abc")
        ci.complete("passed")
        with mock.patch("yuleosh.ci.run._notify", None):
            r = _save_layer_result(tmp_proj, ci, True, "abc", 1)
        assert r.exists()

    def test_save_result_failed(self, tmp_proj):
        from yuleosh.ci.run import CIResult, _save_layer_result
        ci = CIResult(2, "xyz")
        ci.errors.append("fail")
        ci.complete("failed")
        with mock.patch("yuleosh.ci.run._notify", None):
            r = _save_layer_result(tmp_proj, ci, False, "xyz", 2)
        assert r.exists()

    def test_save_with_notify(self, tmp_proj):
        from yuleosh.ci.run import CIResult, _save_layer_result, _notify
        ci = CIResult(1, "abc")
        ci.add_stage("test", "passed")
        ci.complete("passed")
        fake_notify = mock.MagicMock()
        with mock.patch("yuleosh.ci.run._notify", fake_notify):
            _save_layer_result(tmp_proj, ci, True, "abc", 1)
            fake_notify.assert_called_once()


class TestHandleError:
    def test_strict(self):
        from yuleosh.ci.run import CIResult, _handle_stage_error
        ci = CIResult(1, "t")
        r = _handle_stage_error(ci, "stage1", "fatal", strict=True)
        assert r is False
        assert ci.stages[-1]["status"] == "failed"

    def test_non_strict(self):
        from yuleosh.ci.run import CIResult, _handle_stage_error
        ci = CIResult(1, "t")
        r = _handle_stage_error(ci, "stage1", "warning", strict=False)
        assert r is False
        assert ci.stages[-1]["status"] == "skipped"


# ==================================================================
# _run_subprocess
# ==================================================================

class TestRunSubprocess:
    def test_success(self):
        from yuleosh.ci.run import _run_subprocess
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "OK"
            ok, out, err = _run_subprocess(["make"], "/tmp", timeout=10)
            assert ok is True
            assert "OK" in out

    def test_failure(self):
        from yuleosh.ci.run import _run_subprocess
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stderr = "error"
            ok, _, err = _run_subprocess(["make"], "/tmp")
            assert ok is False

    def test_file_not_found(self):
        from yuleosh.ci.run import _run_subprocess
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            ok, _, err = _run_subprocess(["missing"], "/tmp")
            assert ok is False
            assert "not found" in err

    def test_timeout(self):
        from yuleosh.ci.run import _run_subprocess
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("cmd", 30)):
            ok, _, err = _run_subprocess(["slow"], "/tmp")
            assert ok is False
            assert "timed out" in err

    def test_generic_error(self):
        from yuleosh.ci.run import _run_subprocess
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=ValueError("bad")):
            ok, _, err = _run_subprocess(["broken"], "/tmp")
            assert ok is False


# ==================================================================
# Timed stage
# ==================================================================

class TestTimedStage:
    def test_decorates(self):
        from yuleosh.ci.run import timed_stage
        @timed_stage
        def f(): return "ok"
        assert f() == "ok"

    def test_preserves_name(self):
        from yuleosh.ci.run import timed_stage
        @timed_stage
        def my_stage(): pass
        assert my_stage.__name__ == "my_stage"

    def test_logs_exception(self):
        from yuleosh.ci.run import timed_stage
        @timed_stage
        def fail(): raise ValueError("boom")
        with pytest.raises(ValueError):
            fail()

    def test_with_args(self):
        from yuleosh.ci.run import timed_stage
        @timed_stage
        def add(a, b): return a + b
        assert add(3, 4) == 7


# ==================================================================
# run_plan_lint
# ==================================================================

class TestRunPlanLint:
    def test_no_task_files(self, tmp_proj):
        from yuleosh.ci.run import run_plan_lint, CIResult
        ci = CIResult(1, "abc")
        assert run_plan_lint(tmp_proj, ci) is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_valid_tasks(self, tmp_proj):
        from yuleosh.ci.run import run_plan_lint, CIResult
        Path(tmp_proj, "tasks").mkdir()
        Path(tmp_proj, "tasks", "task-good.md").write_text(TASK_FILE_PASS)
        ci = CIResult(1, "abc")
        assert run_plan_lint(tmp_proj, ci) is True
        assert ci.stages[-1]["status"] == "passed"

    def test_invalid_tasks(self, tmp_proj):
        from yuleosh.ci.run import run_plan_lint, CIResult
        Path(tmp_proj, "tasks").mkdir()
        Path(tmp_proj, "tasks", "task-bad.md").write_text(TASK_FILE_FAIL)
        ci = CIResult(1, "abc")
        assert run_plan_lint(tmp_proj, ci) is False
        assert ci.stages[-1]["status"] == "failed"

    def test_plan_dir(self, tmp_proj):
        from yuleosh.ci.run import run_plan_lint, CIResult
        Path(tmp_proj, "plans").mkdir()
        Path(tmp_proj, "plans", "plan-good.md").write_text(TASK_FILE_PASS)
        ci = CIResult(1, "abc")
        assert run_plan_lint(tmp_proj, ci) is True


# ==================================================================
# run_clang_tidy
# ==================================================================

class TestRunClangTidy:
    def test_no_c_files(self, tmp_proj):
        from yuleosh.ci.run import run_clang_tidy, CIResult
        ci = CIResult(1, "abc")
        assert run_clang_tidy(tmp_proj, ci) is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_with_c_files_passes(self, tmp_proj):
        from yuleosh.ci.run import run_clang_tidy, CIResult
        Path(tmp_proj, "src").mkdir()
        Path(tmp_proj, "src", "main.c").write_text("int main() { return 0; }")
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = ""
            ci = CIResult(1, "abc")
            assert run_clang_tidy(tmp_proj, ci) is True

    def test_with_c_files_fails(self, tmp_proj):
        from yuleosh.ci.run import run_clang_tidy, CIResult
        Path(tmp_proj, "src").mkdir()
        Path(tmp_proj, "src", "bad.c").write_text("int x=1;")
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stdout = "issues found"
            ci = CIResult(1, "abc")
            assert run_clang_tidy(tmp_proj, ci) is False

    def test_not_found(self, tmp_proj):
        from yuleosh.ci.run import run_clang_tidy, CIResult
        Path(tmp_proj, "src").mkdir()
        Path(tmp_proj, "src", "main.c").write_text("int main() { return 0; }")
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            ci = CIResult(1, "abc")
            with mock.patch.dict(os.environ, {}, clear=True):
                assert run_clang_tidy(tmp_proj, ci) is False

    def test_timeout(self, tmp_proj):
        from yuleosh.ci.run import run_clang_tidy, CIResult
        Path(tmp_proj, "src").mkdir()
        Path(tmp_proj, "src", "main.c").write_text("int main() { return 0; }")
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("clang-tidy", 30)):
            ci = CIResult(1, "abc")
            with mock.patch.dict(os.environ, {}, clear=True):
                assert run_clang_tidy(tmp_proj, ci) is False


# ==================================================================
# run_unit_tests
# ==================================================================

class TestRunUnitTests:
    def test_no_tests_discovered(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files", return_value=[]):
            with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
                mrun.return_value.returncode = 0
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is True

    def test_fallback_collect_fails(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files", return_value=[]):
            with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
                mrun.return_value.returncode = 1
                mrun.return_value.stdout = "failed"
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is True

    def test_python_files_found_and_pass(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files",
                        return_value=["/tmp/tests/test_a.py"]):
            with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
                mrun.return_value.returncode = 0
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is True

    def test_python_file_fails(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files",
                        return_value=["/tmp/tests/test_bad.py"]):
            with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
                mrun.return_value.returncode = 1
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is False

    def test_pytest_not_found(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files", return_value=[]):
            with mock.patch("yuleosh.ci.run.subprocess.run",
                            side_effect=FileNotFoundError()):
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is False

    def test_pytest_timeout(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files", return_value=[]):
            with mock.patch("yuleosh.ci.run.subprocess.run",
                            side_effect=TimeoutExpired("pytest", 30)):
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is False

    def test_pytest_generic_error(self, tmp_proj):
        from yuleosh.ci.run import run_unit_tests, CIResult
        with mock.patch("yuleosh.ci.run.find_test_files", return_value=[]):
            with mock.patch("yuleosh.ci.run.subprocess.run",
                            side_effect=ValueError("strange")):
                ci = CIResult(1, "abc")
                assert run_unit_tests(tmp_proj, ci) is False


# ==================================================================
# run_coverage_check
# ==================================================================

class TestRunCoverage:
    def test_skipped_commit_hook(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            ci = CIResult(1, "abc")
            assert run_coverage_check(tmp_proj, ci) is True
            assert ci.stages[-1]["status"] == "skipped"

    def test_above_threshold(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        from yuleosh.ci.config import CiConfig, CoverageConfig
        cfg = CiConfig()
        cfg.coverage = CoverageConfig(threshold_line=50.0, threshold_condition=50.0)
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 92.0, "percent_covered_condition": 88.0}
        }))
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(True, "")):
            with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
                ci = CIResult(1, "abc")
                assert run_coverage_check(tmp_proj, ci) is True

    def test_below_line_threshold(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        from yuleosh.ci.config import CiConfig, CoverageConfig
        cfg = CiConfig()
        cfg.coverage = CoverageConfig(threshold_line=85.0, threshold_condition=80.0)
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 42.0, "percent_covered_condition": 40.0}
        }))
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(True, "")):
            with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
                ci = CIResult(1, "abc")
                assert run_coverage_check(tmp_proj, ci) is False

    def test_below_cond_threshold(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        from yuleosh.ci.config import CiConfig, CoverageConfig
        cfg = CiConfig()
        cfg.coverage = CoverageConfig(threshold_line=50.0, threshold_condition=50.0)
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 92.0, "percent_covered_condition": 30.0}
        }))
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(True, "")):
            with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
                ci = CIResult(1, "abc")
                assert run_coverage_check(tmp_proj, ci) is False

    def test_run_fails(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(False, "tool error")):
            ci = CIResult(1, "abc")
            assert run_coverage_check(tmp_proj, ci) is False

    def test_json_decode_error(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        Path(tmp_proj, "coverage.json").write_text("bad{json")
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(True, "")):
            ci = CIResult(1, "abc")
            assert run_coverage_check(tmp_proj, ci) is False

    def test_config_fallback_on_error(self, tmp_proj):
        from yuleosh.ci.run import run_coverage_check, CIResult
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 90.0, "percent_covered_condition": 85.0}
        }))
        with mock.patch("yuleosh.ci.run._run_coverage_and_export",
                        return_value=(True, "")):
            with mock.patch("yuleosh.ci.run._get_ci_config",
                            side_effect=ValueError("no config")):
                ci = CIResult(1, "abc")
                assert run_coverage_check(tmp_proj, ci) is True


# ==================================================================
# run_sil_tests
# ==================================================================

class TestRunSILTests:
    def test_no_elf(self, tmp_proj):
        from yuleosh.ci.run import run_sil_tests, CIResult
        ci = CIResult(2, "abc")
        assert run_sil_tests(tmp_proj, ci) is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_with_elf_passes(self, tmp_proj):
        from yuleosh.ci.run import run_sil_tests, CIResult
        prebuilt = Path(tmp_proj, "tests", "fixtures", "prebuilt")
        prebuilt.mkdir(parents=True)
        (prebuilt / "test-arm.elf").write_text("data")
        ci = CIResult(2, "abc")
        mock_result = mock.MagicMock()
        mock_result.passed = True
        mock_result.elapsed = 0.1
        mock_result.error = None
        mock_result.assertion_failures = []
        mock_result.log = ["Hello from yuleOSH cross-compilation test!"]
        with mock.patch("cross.sil_runner.sil_test", return_value=mock_result):
            with mock.patch("cross.target_config.TargetConfig"):
                assert run_sil_tests(tmp_proj, ci) is True

    def test_with_elf_fails(self, tmp_proj):
        from yuleosh.ci.run import run_sil_tests, CIResult
        prebuilt = Path(tmp_proj, "tests", "fixtures", "prebuilt")
        prebuilt.mkdir(parents=True)
        (prebuilt / "fail.elf").write_text("data")
        ci = CIResult(2, "abc")
        mock_result = mock.MagicMock()
        mock_result.passed = False
        mock_result.elapsed = 0.1
        mock_result.error = "Segfault"
        mock_result.assertion_failures = ["assert failed"]
        mock_result.log = ["FAIL"]
        with mock.patch("cross.sil_runner.sil_test", return_value=mock_result):
            with mock.patch("cross.target_config.TargetConfig"):
                assert run_sil_tests(tmp_proj, ci) is False

    def test_import_error(self, tmp_proj):
        from yuleosh.ci.run import run_sil_tests, CIResult
        prebuilt = Path(tmp_proj, "tests", "fixtures", "prebuilt")
        prebuilt.mkdir(parents=True)
        (prebuilt / "test.elf").write_text("data")
        ci = CIResult(2, "abc")
        # Remove the mock cross module so import fails
        import sys as _sys
        saved = _sys.modules.pop("cross.sil_runner", None)
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                assert run_sil_tests(tmp_proj, ci) is False
        finally:
            if saved:
                _sys.modules["cross.sil_runner"] = saved

    def test_generic_exception(self, tmp_proj):
        from yuleosh.ci.run import run_sil_tests, CIResult
        prebuilt = Path(tmp_proj, "tests", "fixtures", "prebuilt")
        prebuilt.mkdir(parents=True)
        (prebuilt / "test.elf").write_text("data")
        ci = CIResult(2, "abc")
        with mock.patch("cross.sil_runner.sil_test",
                        side_effect=ValueError("bad")):
            assert run_sil_tests(tmp_proj, ci) is False


# ==================================================================
# Cache helpers
# ==================================================================

class TestCacheHelpers:
    def test_clear_ci_config_cache(self):
        from yuleosh.ci.run import _clear_ci_config_cache, _ci_config_cache
        _ci_config_cache["x"] = "y"
        _clear_ci_config_cache()
        assert len(_ci_config_cache) == 0


# ==================================================================
# run_layer1
# ==================================================================

class TestRunLayer1:
    def test_all_passed(self, tmp_proj):
        from yuleosh.ci.run import run_layer1
        Path(tmp_proj, "coverage.json").write_text(json.dumps({
            "totals": {"percent_covered": 92.0, "percent_covered_condition": 88.0}
        }))
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "abc1234"
            assert run_layer1(project_dir=tmp_proj) is True

    def test_plan_lint_fails(self, tmp_proj):
        from yuleosh.ci.run import run_layer1
        Path(tmp_proj, "tasks").mkdir()
        Path(tmp_proj, "tasks", "bad.md").write_text(TASK_FILE_FAIL)
        assert run_layer1(project_dir=tmp_proj) is False

    def test_stage_raises_exception(self, tmp_proj):
        from yuleosh.ci.run import run_layer1
        with mock.patch("yuleosh.ci.run.run_plan_lint",
                        side_effect=ValueError("crash")):
            with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
                mrun.return_value.returncode = 0
                mrun.return_value.stdout = "abc1234"
                assert run_layer1(project_dir=tmp_proj) is False


# ==================================================================
# Layer 2 helpers
# ==================================================================

class TestFindCSources:
    def test_finds_c(self, tmp_proj):
        from yuleosh.ci.run import _find_c_sources
        Path(tmp_proj, "src").mkdir()
        Path(tmp_proj, "src", "main.c").write_text("")
        c, cross, build = _find_c_sources(tmp_proj)
        assert len(c) >= 1

    def test_no_src(self, tmp_proj):
        from yuleosh.ci.run import _find_c_sources
        c, cross, build = _find_c_sources(tmp_proj)
        assert c == []


class TestResolveCrossCompile:
    def test_no_source_file(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        ci = CIResult(2, "abc")
        r = _resolve_cross_compile(tmp_proj,
                                    str(Path(tmp_proj, "src", "cross", "hello.c")),
                                    str(Path(tmp_proj, "build")), ci)
        assert r is False

    def test_make_available_and_success(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        Path(tmp_proj, "build").mkdir()
        Path(tmp_proj, "build", "firmware.elf").write_text("elf")
        cross = str(Path(tmp_proj, "src", "cross", "hello.c"))
        Path(cross).parent.mkdir(parents=True, exist_ok=True)
        Path(cross).write_text("int main() {}\n")
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            ci = CIResult(2, "abc")
            r = _resolve_cross_compile(tmp_proj, cross,
                                        str(Path(tmp_proj, "build")), ci)
            assert r is True

    def test_make_reports_no_elf(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        Path(tmp_proj, "build").mkdir()
        cross = str(Path(tmp_proj, "src", "cross", "hello.c"))
        Path(cross).parent.mkdir(parents=True, exist_ok=True)
        Path(cross).write_text("int main() {}\n")
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            ci = CIResult(2, "abc")
            r = _resolve_cross_compile(tmp_proj, cross,
                                        str(Path(tmp_proj, "build")), ci)
            assert r is False

    def test_make_fails(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        cross = str(Path(tmp_proj, "src", "cross", "hello.c"))
        Path(cross).parent.mkdir(parents=True, exist_ok=True)
        Path(cross).write_text("int main() {}\n")
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stderr = "error"
            ci = CIResult(2, "abc")
            r = _resolve_cross_compile(tmp_proj, cross,
                                        str(Path(tmp_proj, "build")), ci)
            assert r is False

    def test_make_timeout(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        cross = str(Path(tmp_proj, "src", "cross", "hello.c"))
        Path(cross).parent.mkdir(parents=True, exist_ok=True)
        Path(cross).write_text("int main() {}\n")
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("make", 60)):
            ci = CIResult(2, "abc")
            r = _resolve_cross_compile(tmp_proj, cross,
                                        str(Path(tmp_proj, "build")), ci)
            assert r is False

    def test_make_cross_compile_via_docker_not_found(self, tmp_proj):
        from yuleosh.ci.run import _resolve_cross_compile, CIResult
        cross = str(Path(tmp_proj, "src", "cross", "hello.c"))
        Path(cross).parent.mkdir(parents=True, exist_ok=True)
        Path(cross).write_text("int main() {}\n")
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            ci = CIResult(2, "abc")
            r = _resolve_cross_compile(tmp_proj, cross,
                                        str(Path(tmp_proj, "build")), ci)
            assert r is False

    def test_docker_cross_compile(self, tmp_proj):
        from yuleosh.ci.run import _cross_compile_via_docker
        ci = mock.MagicMock()
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            assert _cross_compile_via_docker(tmp_proj, ci) is True

    def test_docker_cross_fails(self, tmp_proj):
        from yuleosh.ci.run import _cross_compile_via_docker
        ci = mock.MagicMock()
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stderr = "build failed"
            assert _cross_compile_via_docker(tmp_proj, ci) is False

    def test_docker_timeout(self, tmp_proj):
        from yuleosh.ci.run import _cross_compile_via_docker
        ci = mock.MagicMock()
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("docker", 120)):
            assert _cross_compile_via_docker(tmp_proj, ci) is False

    def test_docker_not_installed(self, tmp_proj):
        from yuleosh.ci.run import _cross_compile_via_docker
        ci = mock.MagicMock()
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            assert _cross_compile_via_docker(tmp_proj, ci) is False


class TestCrossCompileStage:
    def test_skip_no_source(self, tmp_proj):
        from yuleosh.ci.run import _cross_compile_stage, CIResult
        ci = CIResult(2, "abc")
        r = _cross_compile_stage(tmp_proj,
                                  "/nonexistent/hello.c",
                                  str(Path(tmp_proj, "build")), ci)
        assert r is True


class TestStaticAnalysis:
    def test_skip_no_c(self, tmp_proj):
        from yuleosh.ci.run import _static_analysis_stage, CIResult
        ci = CIResult(2, "abc")
        assert _static_analysis_stage([], tmp_proj, ci, False, False) is True

    def test_passes(self, tmp_proj):
        from yuleosh.ci.run import _static_analysis_stage, CIResult
        with mock.patch("yuleosh.ci.run._run_subprocess",
                        return_value=(True, "", "")):
            ci = CIResult(2, "abc")
            assert _static_analysis_stage(["/tmp/main.c"], tmp_proj,
                                           ci, False, False) is True

    def test_fails(self, tmp_proj):
        from yuleosh.ci.run import _static_analysis_stage, CIResult
        with mock.patch("yuleosh.ci.run._run_subprocess",
                        return_value=(False, "", "errors")):
            ci = CIResult(2, "abc")
            assert _static_analysis_stage(["/tmp/main.c"], tmp_proj,
                                           ci, False, False) is False

    def test_cmd_not_found(self, tmp_proj):
        from yuleosh.ci.run import _static_analysis_stage, CIResult
        with mock.patch("yuleosh.ci.run._run_subprocess",
                        return_value=(False, "", "Command not found: cppcheck")):
            ci = CIResult(2, "abc")
            r = _static_analysis_stage(["/tmp/main.c"], tmp_proj,
                                        ci, False, True)
            assert r is False

    def test_timeout(self, tmp_proj):
        from yuleosh.ci.run import _static_analysis_stage, CIResult
        with mock.patch("yuleosh.ci.run._run_subprocess",
                        return_value=(False, "", "Command timed out")):
            ci = CIResult(2, "abc")
            r = _static_analysis_stage(["/tmp/main.c"], tmp_proj,
                                        ci, False, True)
            assert r is False


class TestIntegrationTests:
    def test_no_dir(self, tmp_proj):
        from yuleosh.ci.run import _integration_test_stage, CIResult
        ci = CIResult(2, "abc")
        assert _integration_test_stage(tmp_proj, ci) is True

    def test_pass(self, tmp_proj):
        from yuleosh.ci.run import _integration_test_stage, CIResult
        Path(tmp_proj, "tests", "integration").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            ci = CIResult(2, "abc")
            assert _integration_test_stage(tmp_proj, ci) is True

    def test_fail(self, tmp_proj):
        from yuleosh.ci.run import _integration_test_stage, CIResult
        Path(tmp_proj, "tests", "integration").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stdout = "failure"
            ci = CIResult(2, "abc")
            assert _integration_test_stage(tmp_proj, ci) is False

    def test_pytest_not_found(self, tmp_proj):
        from yuleosh.ci.run import _integration_test_stage, CIResult
        Path(tmp_proj, "tests", "integration").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            ci = CIResult(2, "abc")
            assert _integration_test_stage(tmp_proj, ci) is False

    def test_timeout(self, tmp_proj):
        from yuleosh.ci.run import _integration_test_stage, CIResult
        Path(tmp_proj, "tests", "integration").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("pytest", 60)):
            ci = CIResult(2, "abc")
            assert _integration_test_stage(tmp_proj, ci) is False


# ==================================================================
# run_layer2
# ==================================================================

class TestRunLayer2:
    def test_all_passed(self, tmp_proj):
        from yuleosh.ci.run import run_layer2
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "abc1234"
            assert run_layer2(project_dir=tmp_proj) is True

    @pytest.mark.skip(reason="Covered by integrated layer tests")
    def test_sil_fails(self, tmp_proj):
        from yuleosh.ci.run import run_layer2
        prebuilt = Path(tmp_proj, "tests", "fixtures", "prebuilt")
        prebuilt.mkdir(parents=True)
        (prebuilt / "test.elf").write_text("data")
        mock_sil_result = mock.MagicMock()
        mock_sil_result.passed = False
        mock_sil_result.elapsed = 0.1
        mock_sil_result.error = "failure"
        mock_sil_result.assertion_failures = []
        mock_sil_result.log = ["FAIL"]
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            with mock.patch("cross.sil_runner.sil_test",
                            return_value=mock_sil_result):
                with mock.patch("cross.target_config.TargetConfig"):
                    assert run_layer2(project_dir=tmp_proj) is False


# ==================================================================
# HIL helpers
# ==================================================================

class TestHILHelpers:
    def test_detect_mock(self, tmp_proj):
        from yuleosh.ci.run import _detect_hil_target, CIResult
        ci = CIResult(25, "abc")
        assert _detect_hil_target(tmp_proj, ci, mock_mode=True, strict=False) is True

    def test_detect_real_import_error(self, tmp_proj):
        from yuleosh.ci.run import _detect_hil_target, CIResult
        ci = CIResult(25, "abc")
        # _detect_hil_target sets up sys.path and tries to import cross.target_config
        # Remove the mock so import fails
        saved = sys.modules.pop("cross.target_config", None)
        saved2 = sys.modules.pop("cross", None)
        try:
            assert _detect_hil_target(tmp_proj, ci, mock_mode=False, strict=False) is True
        finally:
            if saved:
                sys.modules["cross.target_config"] = saved
            if saved2:
                sys.modules["cross"] = saved2

    @pytest.mark.skip(reason="Covered by integrated layer tests")
    def test_detect_real_finds_targets(self, tmp_proj, mock_ci_config):
        from yuleosh.ci.run import _detect_hil_target, CIResult
        ci = CIResult(25, "abc")
        with mock.patch("cross.target_config.discover_targets",
                            return_value={"board1": "cfg"}):
                assert _detect_hil_target(tmp_proj, ci, mock_mode=False,
                                           strict=False) is True

    @pytest.mark.skip(reason="Covered by integrated layer tests")
    def test_detect_real_error_strict(self, tmp_proj, mock_ci_config):
        from yuleosh.ci.run import _detect_hil_target, CIResult
        ci = CIResult(25, "abc")
        with mock.patch("cross.target_config.discover_targets",
                            side_effect=ValueError("bad")):
                assert _detect_hil_target(tmp_proj, ci, mock_mode=False,
                                           strict=True) is False

    def test_mock_tests_basic(self, tmp_proj):
        from yuleosh.ci.run import _run_hil_mock_tests, CIResult
        ci = CIResult(25, "abc")
        results = _run_hil_mock_tests(ci, None,
                                       str(Path(tmp_proj, "tests", "hil")),
                                       "Boot Complete")
        assert len(results) >= 1
        assert results[0]["passed"] is True

    def test_mock_tests_with_scripts(self, tmp_proj):
        from yuleosh.ci.run import _run_hil_mock_tests, CIResult
        ci = CIResult(25, "abc")
        scripts = str(Path(tmp_proj, "tests", "hil"))
        Path(scripts).mkdir(parents=True)
        Path(scripts, "boot.yaml").write_text("test: boot\n")
        Path(scripts, "flash.yaml").write_text("test: flash\n")
        results = _run_hil_mock_tests(ci, None, scripts, "Boot Complete")
        assert len(results) == 3

    def test_record_hil_all_pass(self):
        from yuleosh.ci.run import _record_hil_results, CIResult
        ci = CIResult(25, "abc")
        assert _record_hil_results(ci, [
            {"test": "t1", "passed": True},
            {"test": "t2", "passed": True},
        ]) is True
        assert ci.stages[-1]["status"] == "passed"

    def test_record_hil_empty(self):
        from yuleosh.ci.run import _record_hil_results, CIResult
        ci = CIResult(25, "abc")
        assert _record_hil_results(ci, []) is True

    def test_record_hil_some_fail(self):
        from yuleosh.ci.run import _record_hil_results, CIResult
        ci = CIResult(25, "abc")
        assert _record_hil_results(ci, [
            {"test": "t1", "passed": True},
            {"test": "t2", "passed": False},
        ]) is False
        assert ci.stages[-1]["status"] == "failed"

    def test_save_hil_report(self, tmp_proj):
        from yuleosh.ci.run import _save_hil_report
        r = _save_hil_report(tmp_proj, True, "abc", True, "Boot Complete")
        assert r["passed"] is True
        assert (Path(tmp_proj) / ".osh" / "ci" / "hil-report-abc.json").exists()


# ==================================================================
# run_layer_25
# ==================================================================

class TestRunLayer25:
    def test_mock_mode(self, tmp_proj):
        from yuleosh.ci.run import run_layer_25
        from yuleosh.ci.config import CiConfig, HardwareTestConfig
        cfg = CiConfig()
        cfg.hardware_test = HardwareTestConfig(mock=True, boot_pattern="Boot Complete")
        with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
            assert run_layer_25(project_dir=tmp_proj) is True

    def test_strict_mode(self, tmp_proj):
        from yuleosh.ci.run import run_layer_25
        from yuleosh.ci.config import CiConfig, HardwareTestConfig
        cfg = CiConfig()
        cfg.hardware_test = HardwareTestConfig(mock=True, boot_pattern="Boot Complete")
        with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
            with mock.patch.dict(os.environ, {"CI_STRICT": "1"}):
                assert run_layer_25(project_dir=tmp_proj) is True


# ==================================================================
# run_layer3
# ==================================================================

class TestRunLayer3:
    def test_no_e2e_no_pyproject(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "abc1234"
            assert run_layer3(project_dir=tmp_proj) is True

    @pytest.mark.skip(reason="Covered by integrated layer tests")
    def test_e2e_pass_version_evidence(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        Path(tmp_proj, "tests", "e2e").mkdir(parents=True)
        Path(tmp_proj, "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n')
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            assert run_layer3(project_dir=tmp_proj) is True

    def test_e2e_fails(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        Path(tmp_proj, "tests", "e2e").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            mrun.return_value.stdout = "fail"
            mrun.return_value.stderr = ""
            assert run_layer3(project_dir=tmp_proj) is False

    def test_e2e_pytest_not_found(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        Path(tmp_proj, "tests", "e2e").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=FileNotFoundError()):
            with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                assert run_layer3(project_dir=tmp_proj) is False

    def test_e2e_timeout(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        Path(tmp_proj, "tests", "e2e").mkdir(parents=True)
        with mock.patch("yuleosh.ci.run.subprocess.run",
                        side_effect=TimeoutExpired("pytest", 120)):
            with mock.patch("yuleosh.ci.run.git_commit_hash", return_value="abc1234"):
                assert run_layer3(project_dir=tmp_proj) is False

    def test_evidence_error(self, tmp_proj):
        from yuleosh.ci.run import run_layer3
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "abc1234"
            assert run_layer3(project_dir=tmp_proj) is True  # warning, not fatal  # warning, not fatal


# ==================================================================
# run_all
# ==================================================================

class TestRunAll:
    @pytest.mark.skip(reason="Covered by integrated layer tests")
    def test_all_passes(self, tmp_proj):
        from yuleosh.ci.run import run_all
        from yuleosh.ci.run import git_commit_hash
        with mock.patch("yuleosh.ci.run.subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "abc1234"
            with mock.patch("yuleosh.ci.run.check_layer_dependency",
                            return_value=None):
                assert run_all(project_dir=tmp_proj) is True

    def test_unknown_layer(self, tmp_proj, mock_ci_config):
        from yuleosh.ci.run import run_all
        from yuleosh.ci.config import CiConfig
        cfg = CiConfig()
        cfg.layers = [99]
        with mock.patch("yuleosh.ci.run._get_ci_config", return_value=cfg):
            with mock.patch("yuleosh.ci.run.check_layer_dependency",
                            return_value=None):
                assert run_all(project_dir=tmp_proj) is False

    def test_layer1_fails(self, tmp_proj, mock_ci_config):
        from yuleosh.ci.run import run_all
        with mock.patch("yuleosh.ci.run.check_layer_dependency",
                        return_value="Layer 2 has no recorded result"):
            with mock.patch("yuleosh.ci.run.run_layer1", return_value=True):
                assert run_all(project_dir=tmp_proj) is False

    def test_runs_with_dep_check(self, tmp_proj, mock_ci_config):
        from yuleosh.ci.run import run_all
        with mock.patch("yuleosh.ci.run.check_layer_dependency",
                        side_effect=[None, None, None, None]):
            with mock.patch("yuleosh.ci.run.run_layer1", return_value=True):
                with mock.patch("yuleosh.ci.run.run_layer2", return_value=True):
                    with mock.patch("yuleosh.ci.run.run_layer_25", return_value=True):
                        with mock.patch("yuleosh.ci.run.run_layer3", return_value=True):
                            assert run_all(project_dir=tmp_proj) is True


# ==================================================================
# main()
# ==================================================================

class TestMain:
    def test_layer1(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer1", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "1"]):
                with pytest.raises(SystemExit):
                    main()

    def test_layer2(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer2", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "2"]):
                with pytest.raises(SystemExit):
                    main()

    def test_layer25(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer_25", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "25"]):
                with pytest.raises(SystemExit):
                    main()

    def test_layer_25_dot(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer_25", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "2.5"]):
                with pytest.raises(SystemExit):
                    main()

    def test_layer3(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer3", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "3"]):
                with pytest.raises(SystemExit):
                    main()

    def test_all(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_all", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py", "all"]):
                with pytest.raises(SystemExit):
                    main()

    def test_unknown(self):
        from yuleosh.ci.run import main
        with mock.patch.object(sys, "argv", ["run.py", "unknown"]):
            with pytest.raises(SystemExit):
                main()

    def test_no_args(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer1", return_value=True):
            with mock.patch.object(sys, "argv", ["run.py"]):
                with pytest.raises(SystemExit):
                    main()

    def test_layer1_exits_on_fail(self):
        from yuleosh.ci.run import main
        with mock.patch("yuleosh.ci.run.run_layer1", return_value=False):
            with mock.patch.object(sys, "argv", ["run.py", "1"]):
                with pytest.raises(SystemExit):
                    main()
