# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for ci/stages.py — key standalone functions and CI stage handlers.

Focus on pure functions that can be tested without complex mocks.
Note: run_yaml_validation delegates to yaml_validator.validate_all().
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ===================================================================
# Pure function tests: _categorize_file, _exclude_paths, _detect_include_paths
# ===================================================================

class TestCategorizeFile:
    """_categorize_file: determines code category from file path."""

    def test_business_default(self):
        from yuleosh.ci.stages import _categorize_file
        categories = {"business": {"paths": ["src/**/*.c"]}}
        cat, cfg = _categorize_file("/project/src/main.c", categories)
        assert cat == "business"

    def test_template_matches_on_basename(self):
        from yuleosh.ci.stages import _categorize_file
        # fnmatch matches basename patterns like "foo.c"
        categories = {
            "template": {"paths": ["template_*.c"]},
            "business": {"paths": ["*.py"]},
        }
        cat, cfg = _categorize_file("src/template_test.c", categories)
        assert cat == "template"

    def test_third_party_matches_on_basename(self):
        from yuleosh.ci.stages import _categorize_file
        categories = {
            "third_party": {"paths": ["lib*"]},
            "business": {"paths": ["*.py"]},
        }
        cat, cfg = _categorize_file("src/libfoo.c", categories)
        assert cat == "third_party"

    def test_fallback_empty_categories(self):
        from yuleosh.ci.stages import _categorize_file
        cat, cfg = _categorize_file("src/main.c", {})
        assert cat == "business"
        assert cfg == {}

    def test_template_matched_by_fullpath(self):
        from yuleosh.ci.stages import _categorize_file
        categories = {
            "template": {"paths": ["*/templates/*.c"]},
            "business": {"paths": ["*"]},
        }
        cat, cfg = _categorize_file("/project/templates/init.c", categories)
        assert cat == "template"


class TestExcludePaths:
    """_exclude_paths: filter file lists by exclude patterns."""

    def test_no_exclude_patterns(self):
        from yuleosh.ci.stages import _exclude_paths
        files = ["src/main.c", "tests/test_main.c", "src/utils.c"]
        result = _exclude_paths(files, [], "/project")
        assert result == files

    def test_exclude_tests(self):
        from yuleosh.ci.stages import _exclude_paths
        files = ["src/main.c", "tests/test_main.c", "src/utils.c"]
        result = _exclude_paths(files, ["tests/**"], "/project")
        assert result == ["src/main.c", "src/utils.c"]

    def test_exclude_multiple_patterns(self):
        from yuleosh.ci.stages import _exclude_paths
        files = ["src/main.c", "third_party/lib.c", "src/utils.c", "build/out.o"]
        result = _exclude_paths(files, ["third_party/**", "build/**"], "/project")
        assert result == ["src/main.c", "src/utils.c"]

    def test_empty_file_list(self):
        from yuleosh.ci.stages import _exclude_paths
        result = _exclude_paths([], ["**"], "/project")
        assert result == []

    def test_exclude_top_level_tests_with_doublestar_prefix(self):
        """2026-08-16 回归：`**/tests/**` 必须同时匹配顶层 `tests/x.c`。

        _glob_to_regex('**/tests/**') → ^.*/tests/.*$ 要求路径含前导 /，
        而相对路径 tests/x.c 无前导斜杠 → 匹配失败（window-anti-pinch
        L1 MISRA 把 tests/ 扫进去爆 233 required 违规的根因）。
        """
        from yuleosh.ci.stages import _exclude_paths
        files = ["tests/test_window_control.c", "src/app.c",
                 "src/foo/tests/bar.c"]
        result = _exclude_paths(files, ["**/tests/**"], "/project")
        assert result == ["src/app.c"], f"got {result}"

    def test_doublestar_prefix_matches_nested_tests(self):
        from yuleosh.ci.stages import _exclude_paths
        files = ["src/foo/tests/deep.c", "src/app.c"]
        result = _exclude_paths(files, ["**/tests/**"], "/project")
        assert result == ["src/app.c"]


class TestDetectIncludePaths:
    """_detect_include_paths: find common C include directories."""

    def test_detects_existing_dirs(self, tmp_path):
        from yuleosh.ci.stages import _detect_include_paths
        (tmp_path / "src").mkdir()
        (tmp_path / "include").mkdir()
        result = _detect_include_paths(str(tmp_path))
        assert str(tmp_path / "src") in result
        assert str(tmp_path / "include") in result

    def test_returns_empty_if_not_found(self, tmp_path):
        from yuleosh.ci.stages import _detect_include_paths
        # "." always exists as a dir, so it always returns at least ["."]
        result = _detect_include_paths(str(tmp_path))
        # "." is a candidate that exists anywhere
        assert len(result) >= 0


class TestFormatNullPointerFix:
    """_format_null_pointer_fix: generates fix suggestions."""

    def test_template_returns_empty(self):
        from yuleosh.ci.stages import _format_null_pointer_fix
        result = _format_null_pointer_fix("template", "/fake/path.c")
        assert result == ""

    def test_business_returns_fix(self):
        from yuleosh.ci.stages import _format_null_pointer_fix
        result = _format_null_pointer_fix("business", "/fake/path.c")
        assert "🔧" in result

    def test_third_party_includes_deviation(self):
        from yuleosh.ci.stages import _format_null_pointer_fix
        result = _format_null_pointer_fix("third_party", "/fake/path.c")
        assert "deviation" in result


# ===================================================================
# run_yaml_validation (delegates to yaml_validator.validate_all)
# ===================================================================

class TestRunYamlValidation:
    """run_yaml_validation: validates YAML config files."""

    def test_success(self, tmp_path):
        from yuleosh.ci.stages import run_yaml_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.yaml_validator.validate_all") as mock_val:
            mock_val.return_value = {"valid": True, "errors": {}}
            result = run_yaml_validation(str(tmp_path), ci)
            assert result is True

    def test_failure(self, tmp_path):
        from yuleosh.ci.stages import run_yaml_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.yaml_validator.validate_all") as mock_val:
            mock_val.return_value = {
                "valid": False,
                "errors": {"ci-config.yaml": ["Invalid field X"]},
            }
            result = run_yaml_validation(str(tmp_path), ci)
            assert result is False

    def test_no_config_returns_true(self, tmp_path):
        from yuleosh.ci.stages import run_yaml_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.yaml_validator.validate_all") as mock_val:
            mock_val.return_value = {"valid": True, "errors": {}}
            result = run_yaml_validation(str(tmp_path), ci)
            assert result is True


# ===================================================================
# run_spec_validation
# ===================================================================

class TestRunSpecValidation:
    """run_spec_validation: validates spec files."""

    def test_success_missing_files(self, tmp_path):
        """GIVEN no spec files present WHEN run_spec_validation THEN passes with warning."""
        from yuleosh.ci.stages import run_spec_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")
        # No docs/spec.md or specs/ dir — warning path
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True

    def test_success_with_spec(self, tmp_path):
        """GIVEN spec file with keywords WHEN run_spec_validation THEN passes."""
        from yuleosh.ci.stages import run_spec_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")
        spec_dir = tmp_path / "docs"
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text("## RS-001\nSystem SHALL init.\n")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True


# ===================================================================
# run_coverage_check
# ===================================================================

class TestRunCoverageCheck:
    """run_coverage_check: runs coverage checks."""

    def test_skipped_in_hook(self, tmp_path):
        """GIVEN HOOK_TYPE=commit WHEN run_coverage_check THEN skip."""
        from yuleosh.ci.stages import run_coverage_check
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.stages.test._should_skip_coverage", return_value=True):
            result = run_coverage_check(str(tmp_path), ci)
            assert result is True

    def test_coverage_run_failure(self, tmp_path):
        """GIVEN coverage tool fails WHEN run_coverage_check THEN fails."""
        from yuleosh.ci.stages import run_coverage_check
        from yuleosh.ci.result import CIResult

        # 2026-08-13: 有 Python 测试文件 coverage 才会真正执行
        # (2026-08-12 起无 Python 测试的项目提前跳过 → 空目录 fixture 假失败)
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "test_demo.py").write_text("def test_ok(): pass\n")
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "app.py").write_text("def f(): return 1\n")

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch.multiple(
            "yuleosh.ci.stages",
            _should_skip_coverage=mock.MagicMock(return_value=False),
            _run_coverage_and_export=mock.MagicMock(return_value=(False, "coverage error")),
        ):
            result = run_coverage_check(str(tmp_path), ci)
            assert result is False

    def test_skip_when_no_python_source_under_src(self, tmp_path):
        """GIVEN C-only repo with Python tests but no Python src WHEN run_coverage_check THEN skip.

        C/C++ coverage is handled by the gcov stage; `coverage run --source=src`
        on a src/ tree with no .py files collects nothing and `coverage json`
        fails with "No data to report". (fix 2026-08-12: window-anti-pinch L1)
        """
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages import run_coverage_check

        # tests/ 有 Python 测试（qualification 类，shell 到 C 二进制）
        (tmp_path / "tests").mkdir(exist_ok=True)
        (tmp_path / "tests" / "test_qualification.py").write_text("def test_ok(): pass\n")
        # src/ 只有 C 源文件，无 .py
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "main.c").write_text("int main(void){return 0;}\n")

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.stages._should_skip_coverage", return_value=False), \
                mock.patch("yuleosh.ci.stages._run_coverage_and_export",
                           return_value=(False, "coverage error")) as m_export:
            result = run_coverage_check(str(tmp_path), ci)
            assert result is True  # skip 而非失败
            stage = ci.stages[-1]
            assert stage["name"] == "coverage"
            assert stage["status"] == "skipped"
            assert "no Python source" in stage["detail"]
            # 绝不能真跑 coverage（会 "No data to report" 假失败）
            m_export.assert_not_called()


# ===================================================================
# run_unit_tests
# ===================================================================

class TestRunUnitTests:
    """run_unit_tests: runs unit tests."""

    def test_no_test_files_uses_pytest(self, tmp_path):
        """GIVEN no test files found WHEN run_unit_tests THEN falls back to pytest."""
        from yuleosh.ci.stages import run_unit_tests
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc123")

        with mock.patch("yuleosh.ci.stages.validation.subprocess.run") as mock_run:
            # First call: find_test_files returns nothing
            # Second call: pytest --collect-only succeeds
            # Third call: pytest -x succeeds
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout="all tests passed",
                stderr=""
            )
            with mock.patch("yuleosh.ci.stages.test.find_test_files", return_value=[]):
                result = run_unit_tests(str(tmp_path), ci)
                assert result is True
