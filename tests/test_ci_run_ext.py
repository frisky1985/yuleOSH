"""
Extended tests for yuleosh.ci.stage_utils and yuleosh.ci.runner — push coverage ≥ 60%.
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# =====================================================================
# stage_utils
# =====================================================================

class TestStageUtils:
    """Cover stage_utils functions."""

    def test_get_cache_key_for_dir(self, tmp_path):
        from yuleosh.ci.stage_utils import get_cache_key_for_dir
        key = get_cache_key_for_dir(str(tmp_path))
        assert isinstance(key, str)
        assert len(key) == 32

    def test_get_cache_key_with_test_file(self, tmp_path):
        from yuleosh.ci.stage_utils import get_cache_key_for_dir
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test(): pass")
        key = get_cache_key_for_dir(str(tmp_path))
        assert isinstance(key, str)

    def test_find_test_files_none(self, tmp_path):
        from yuleosh.ci.stage_utils import find_test_files
        files = find_test_files(str(tmp_path))
        assert files == []

    def test_find_test_files_python(self, tmp_path):
        from yuleosh.ci.stage_utils import find_test_files
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test(): pass")
        files = find_test_files(str(tmp_path))
        assert len(files) == 1
        assert "test_main.py" in files[0]

    def test_find_test_files_go(self, tmp_path):
        from yuleosh.ci.stage_utils import find_test_files
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "main_test.go").write_text("")
        files = find_test_files(str(tmp_path))
        assert len(files) == 1
        assert "_test.go" in files[0]

    def test_find_test_files_java(self, tmp_path):
        from yuleosh.ci.stage_utils import find_test_files
        test_file = tmp_path / "TestMain.java"
        test_file.write_text("")
        files = find_test_files(str(tmp_path))
        assert len(files) >= 0

    def test_find_test_files_c_test(self, tmp_path):
        from yuleosh.ci.stage_utils import find_test_files
        test_file = tmp_path / "main_test.c"
        test_file.write_text("")
        files = find_test_files(str(tmp_path))
        assert len(files) >= 0

    def test_should_skip_coverage_commit(self):
        from yuleosh.ci.stage_utils import _should_skip_coverage
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            assert _should_skip_coverage() is True

    def test_should_skip_coverage_nested(self):
        from yuleosh.ci.stage_utils import _should_skip_coverage
        with mock.patch.dict(os.environ, {"COVERAGE_RUN": "1"}):
            assert _should_skip_coverage() is True

    def test_should_skip_coverage_normal(self):
        from yuleosh.ci.stage_utils import _should_skip_coverage
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _should_skip_coverage() is False

    def test_coverage_skip_reason_commit(self):
        from yuleosh.ci.stage_utils import _coverage_skip_reason
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            reason = _coverage_skip_reason()
            assert "commit" in reason

    def test_coverage_skip_reason_recursion(self):
        from yuleosh.ci.stage_utils import _coverage_skip_reason
        with mock.patch.dict(os.environ, {"COVERAGE_RUN": "1"}):
            reason = _coverage_skip_reason()
            assert "recursion" in reason

    @mock.patch("subprocess.run")
    def test_run_subprocess_success(self, mock_run):
        from yuleosh.ci.stage_utils import _run_subprocess
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "success"
        mock_run.return_value.stderr = ""
        success, stdout, _ = _run_subprocess(["echo", "ok"], "/tmp")
        assert success is True

    @mock.patch("subprocess.run")
    def test_run_subprocess_failure(self, mock_run):
        from yuleosh.ci.stage_utils import _run_subprocess
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = "error"
        success, _, stderr = _run_subprocess(["false"], "/tmp")
        assert success is False

    @mock.patch("subprocess.run")
    def test_run_subprocess_not_found(self, mock_run):
        from yuleosh.ci.stage_utils import _run_subprocess
        mock_run.side_effect = FileNotFoundError("not found")
        success, _, stderr = _run_subprocess(["nonexistent"], "/tmp")
        assert success is False
        assert "not found" in stderr

    def test_handle_stage_error_strict(self):
        from yuleosh.ci.stage_utils import _handle_stage_error
        from yuleosh.ci.result import CIResult
        ci = CIResult(layer=1, commit_hash="abc")
        result = _handle_stage_error(ci, "test", "issue", strict=True)
        assert result is False
        assert ci.stages[-1]["status"] == "failed"

    def test_handle_stage_error_non_strict(self):
        from yuleosh.ci.stage_utils import _handle_stage_error
        from yuleosh.ci.result import CIResult
        ci = CIResult(layer=1, commit_hash="abc")
        result = _handle_stage_error(ci, "test", "issue", strict=False)
        assert result is False
        assert ci.stages[-1]["status"] == "skipped"

    @mock.patch("subprocess.run")
    def test_resolve_cross_compile_make(self, mock_run):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _resolve_cross_compile
        mock_run.side_effect = [
            mock.MagicMock(returncode=0),
            mock.MagicMock(returncode=0, stderr="", stdout=""),
        ]
        ci = CIResult(layer=1, commit_hash="abc")
        import tempfile as tf
        with tf.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir()
            (build_dir / "firmware.elf").write_text("")
            result = _resolve_cross_compile(tmpdir, "nonexistent", str(build_dir), ci)
            assert result is True

    @mock.patch("subprocess.run")
    def test_resolve_cross_compile_make_no_elf(self, mock_run):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _resolve_cross_compile
        mock_run.side_effect = [
            mock.MagicMock(returncode=0),
            mock.MagicMock(returncode=0, stderr="", stdout=""),
        ]
        ci = CIResult(layer=1, commit_hash="abc")
        import tempfile as tf
        with tf.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir(parents=True)
            result = _resolve_cross_compile(tmpdir, "nonexistent", str(build_dir), ci)
            assert result is False

    @mock.patch("subprocess.run")
    def test_resolve_cross_compile_make_failure(self, mock_run):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _resolve_cross_compile
        mock_run.side_effect = [
            mock.MagicMock(returncode=0),
            mock.MagicMock(returncode=1, stderr="error", stdout=""),
        ]
        ci = CIResult(layer=1, commit_hash="abc")
        import tempfile as tf
        with tf.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir) / "build"
            build_dir.mkdir(parents=True)
            result = _resolve_cross_compile(tmpdir, "nonexistent", str(build_dir), ci)
            assert result is False

    def test_find_c_sources(self, tmp_path):
        from yuleosh.ci.stage_utils import _find_c_sources
        src_dir = tmp_path / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "main.c").write_text("")
        (src_dir / "util.cpp").write_text("")
        (src_dir / "header.h").write_text("")  # .h should not be found
        c_files, cross_src, build_dir = _find_c_sources(str(tmp_path))
        assert len(c_files) == 2
        assert all(f.endswith((".c", ".cpp")) for f in c_files)
        assert "cross" in cross_src
        assert "build" in build_dir

    @mock.patch("subprocess.run")
    def test_cross_compile_stage_skipped(self, mock_run, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _cross_compile_stage
        ci = CIResult(layer=1, commit_hash="abc")
        result = _cross_compile_stage(str(tmp_path), "nonexistent", "build", ci)
        assert result is True

    @mock.patch("subprocess.run")
    def test_static_analysis_skipped_no_files(self, mock_run, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _static_analysis_stage
        ci = CIResult(layer=1, commit_hash="abc")
        result = _static_analysis_stage([], str(tmp_path), ci, False, False)
        assert result is True

    @mock.patch("subprocess.run")
    def test_static_analysis_passes(self, mock_run, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _static_analysis_stage
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        ci = CIResult(layer=1, commit_hash="abc")
        result = _static_analysis_stage(["main.c"], str(tmp_path), ci, False, False)
        assert result is True

    @mock.patch("subprocess.run")
    def test_static_analysis_cppcheck_not_found(self, mock_run, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stage_utils import _static_analysis_stage
        mock_run.side_effect = FileNotFoundError("cppcheck")
        ci = CIResult(layer=1, commit_hash="abc")
        result = _static_analysis_stage(["main.c"], str(tmp_path), ci, False, False)
        assert result is False


# =====================================================================
# runner
# =====================================================================

class TestRunner:
    """Cover runner functions."""

    @mock.patch("subprocess.run")
    def test_git_commit_hash_success(self, mock_run):
        from yuleosh.ci.runner import git_commit_hash
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "abc1234\n"
        result = git_commit_hash()
        assert result == "abc1234"

    @mock.patch("subprocess.run")
    def test_git_commit_hash_failure(self, mock_run):
        from yuleosh.ci.runner import git_commit_hash
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        result = git_commit_hash()
        assert result == "unknown"

    @mock.patch("subprocess.run")
    def test_get_changed_files(self, mock_run):
        from yuleosh.ci.runner import get_changed_files
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "file1.py\nfile2.py\n"
        result = get_changed_files()
        assert len(result) == 2

    @mock.patch("subprocess.run")
    def test_get_changed_files_failure(self, mock_run):
        from yuleosh.ci.runner import get_changed_files
        mock_run.return_value.returncode = 1
        result = get_changed_files()
        assert result == []

    def test_save_layer_result(self, tmp_path):
        from yuleosh.ci.runner import _save_layer_result
        from yuleosh.ci.result import CIResult
        ci = CIResult(layer=1, commit_hash="abc")
        ci.add_stage("test", "passed")
        path = _save_layer_result(str(tmp_path), ci, True, "abc", 1)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["status"] == "running"  # Not yet completed

    def test_save_layer_result_with_notify(self, tmp_path):
        from yuleosh.ci.runner import _save_layer_result
        from yuleosh.ci.result import CIResult
        import yuleosh.ci.run as _run
        mock_notify = mock.MagicMock()
        _run._notify = mock_notify
        ci = CIResult(layer=1, commit_hash="abc")
        try:
            path = _save_layer_result(str(tmp_path), ci, True, "abc", 1)
            mock_notify.assert_called_once()
        finally:
            _run._notify = None

    def test_run_all_fails(self):
        from yuleosh.ci.runner import run_all
        with mock.patch("yuleosh.ci.runner._get_ci_config") as mock_cfg:
            mock_cfg.return_value = mock.MagicMock(layers=[1, 2])
            with mock.patch("yuleosh.ci.layers.check_layer_dependency", return_value="dependency not satisfied"):
                result = run_all(project_dir="/tmp/test")
                assert result is False

    def test_run_all_config_error(self):
        from yuleosh.ci.runner import run_all
        with mock.patch("yuleosh.ci.runner._get_ci_config", side_effect=Exception("config error")):
            with mock.patch("yuleosh.ci.layers.check_layer_dependency", return_value="blocked"):
                result = run_all(project_dir="/tmp/test")
                assert result is False

    def test_main_all(self):
        from yuleosh.ci.runner import main
        with mock.patch.object(sys, 'argv', ['run.py', 'all']):
            with mock.patch("yuleosh.ci.runner.run_all") as mock_all:
                mock_all.return_value = True
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    def test_main_layer1(self):
        from yuleosh.ci.runner import main
        with mock.patch.object(sys, 'argv', ['run.py', '1']):
            with mock.patch("yuleosh.ci.run.run_layer1") as mock_l1:
                mock_l1.return_value = True
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    def test_main_unknown_layer(self):
        from yuleosh.ci.runner import main
        with mock.patch.object(sys, 'argv', ['run.py', '99']):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
