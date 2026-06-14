"""Smoke tests for yuleosh.ci — config, runner, and core utilities."""
from unittest.mock import patch, MagicMock
import os


class TestCiConfig:
    """Smoke tests for CI configuration module."""

    def test_import_ci_config(self):
        from yuleosh.ci.config import CiConfig, load_ci_config
        assert CiConfig is not None
        assert callable(load_ci_config)

    def test_ci_config_defaults(self):
        from yuleosh.ci.config import CiConfig
        cfg = CiConfig()
        assert cfg.layers is not None
        assert cfg.layers == [1, 2, 25, 3]

    def test_load_ci_config_missing_file(self):
        from yuleosh.ci.config import load_ci_config
        with patch("pathlib.Path.exists", return_value=False):
            cfg = load_ci_config("/tmp/nonexistent")
        assert cfg is not None
        assert cfg.layers == [1, 2, 25, 3]


class TestCiRun:
    """Smoke tests for CI runner utilities."""

    def test_ci_constants(self):
        from yuleosh.ci.run import (_get_ci_config, _clear_ci_config_cache,
                                     is_strict, is_misra_fail_fast)
        assert callable(_get_ci_config)
        assert callable(_clear_ci_config_cache)
        assert isinstance(is_strict(), bool)
        assert isinstance(is_misra_fail_fast(), bool)

    def test_cache_key(self):
        from yuleosh.ci.run import get_cache_key_for_dir
        key = get_cache_key_for_dir("/tmp")
        assert isinstance(key, str)
        assert len(key) > 8

    def test_coverage_skip_defaults(self):
        from yuleosh.ci.run import _should_skip_coverage, _coverage_skip_reason
        assert isinstance(_should_skip_coverage(), bool)
        assert isinstance(_coverage_skip_reason(), str)

    def test_git_commit_hash(self):
        from yuleosh.ci.run import git_commit_hash
        with patch("yuleosh.ci.run.subprocess.run") as m:
            m.return_value.stdout = "abc1234\n"
            m.return_value.returncode = 0
            result = git_commit_hash()
            assert result == "abc1234"

    def test_get_changed_files(self):
        from yuleosh.ci.run import get_changed_files
        with patch("yuleosh.ci.run.subprocess.run") as m:
            m.return_value.stdout = "src/main.c\ntests/test_main.c\n"
            m.return_value.returncode = 0
            result = get_changed_files("HEAD~1")
            assert "src/main.c" in result

    def test_find_test_files(self):
        from yuleosh.ci.run import find_test_files
        with patch("pathlib.Path.rglob") as m:
            m.return_value = [MagicMock()]
            m.return_value[0].name = "test_main.py"
            result = find_test_files("/tmp/project")
            assert isinstance(result, list)

    def test_should_skip_coverage_hook(self):
        from yuleosh.ci.run import _should_skip_coverage
        with patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            assert _should_skip_coverage() is True

    def test_coverage_skip_reason_hook(self):
        from yuleosh.ci.run import _coverage_skip_reason
        with patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            reason = _coverage_skip_reason()
            assert "commit" in reason

    def test_clear_ci_config_cache(self):
        from yuleosh.ci.run import _clear_ci_config_cache, _get_ci_config
        _clear_ci_config_cache()
        cfg = _get_ci_config()
        assert cfg is not None

    def test_get_latest_layer_result(self):
        from yuleosh.ci.run import get_latest_layer_result
        with patch("pathlib.Path.exists", return_value=False):
            result = get_latest_layer_result(1, "/tmp")
            assert result is None

    def test_check_layer_dependency(self):
        from yuleosh.ci.run import check_layer_dependency
        result = check_layer_dependency(1, "")
        # Layer 1 has no dependencies, so should return None (no missing deps)
        assert result is None or isinstance(result, str)

    def test_ci_result_basic(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(layer=1, commit_hash="abc123")
        assert ci.layer == 1
        assert ci.commit_hash == "abc123"
        assert ci.status == "running"

    def test_ci_result_add_stage(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(layer=2, commit_hash="def456")
        ci.add_stage("lint", "passed", "All OK")
        assert len(ci.stages) == 1
        assert ci.stages[0]["name"] == "lint"
        assert ci.stages[0]["status"] == "passed"

    def test_ci_result_complete(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(layer=3, commit_hash="ghi789")
        ci.complete("passed")
        assert ci.status == "passed"
        assert ci.completed_at is not None

    def test_ci_result_to_dict(self):
        from yuleosh.ci.run import CIResult
        ci = CIResult(layer=1, commit_hash="abc")
        d = ci.to_dict()
        assert d["layer"] == 1
        assert d["commit"] == "abc"
        assert d["status"] == "running"
        assert "stages" in d

    def test_run_coverage_check_function_exists(self):
        from yuleosh.ci.run import run_coverage_check
        assert callable(run_coverage_check)

    def test_run_plan_lint_function_exists(self):
        from yuleosh.ci.run import run_plan_lint
        assert callable(run_plan_lint)

    def test_run_clang_tidy_function_exists(self):
        from yuleosh.ci.run import run_clang_tidy
        assert callable(run_clang_tidy)

    def test_run_unit_tests_function_exists(self):
        from yuleosh.ci.run import run_unit_tests
        assert callable(run_unit_tests)

    def test_run_sil_tests_function_exists(self):
        from yuleosh.ci.run import run_sil_tests
        assert callable(run_sil_tests)

    def test_resolve_cross_compile_exists(self):
        from yuleosh.ci.run import _resolve_cross_compile
        assert callable(_resolve_cross_compile)

    def test_run_subprocess(self):
        from yuleosh.ci.run import _run_subprocess
        with patch("yuleosh.ci.run.subprocess.run") as m:
            m.return_value.returncode = 0
            m.return_value.stdout = "ok output"
            m.return_value.stderr = ""
            ok, out, err = _run_subprocess(["echo", "test"], "/tmp")
            assert ok
            assert "ok" in out
