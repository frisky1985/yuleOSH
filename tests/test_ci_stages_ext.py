"""
Extended tests for yuleosh.ci.stages (build, traceability, validation) — push coverage ≥ 60%.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# =====================================================================
# run_c_coverage (from stages/build.py)
# =====================================================================

class TestRunCCoverage:
    """Cover run_c_coverage from stages/build.py."""

    def test_no_build_dir(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.build import run_c_coverage
        ci = CIResult(layer=1, commit_hash="abc")
        with mock.patch("os.path.isdir", return_value=False):
            with mock.patch("os.path.isfile", return_value=False):
                with mock.patch("os.walk", return_value=[]):
                    result = run_c_coverage("/tmp/project", ci)
        assert result is True  # non-blocking
        assert any("skipped" in s["status"] for s in ci.stages)

    def test_build_dir_with_gcda(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.build import run_c_coverage
        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("os.walk", return_value=[("/tmp/project/build", [], ["main.gcda"])]):
                with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report", return_value=None):
                    ci = CIResult(layer=1, commit_hash="abc")
                    result = run_c_coverage("/tmp/project", ci)
                    assert result is True

    def test_c_coverage_report_json(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.build import run_c_coverage

        report_path = tmp_path / ".yuleosh" / "reports" / "c-coverage.json"
        report_path.parent.mkdir(parents=True)

        with mock.patch("os.path.isdir", return_value=True):
            with mock.patch("os.walk", return_value=[("/tmp/project/build", [], ["main.gcda"])]):
                with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report", return_value=str(report_path)):
                    with mock.patch("builtins.open", mock.mock_open()):
                        with mock.patch("json.load", return_value={"line_rate": 85.5, "branch_rate": 75.0, "total_files": 10}):
                            ci = CIResult(layer=1, commit_hash="abc")
                            result = run_c_coverage(str(tmp_path), ci)
                            assert result is True

    def test_import_error_is_caught(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.build import run_c_coverage
        ci = CIResult(layer=1, commit_hash="abc")
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        side_effect=ImportError("no module")):
            with mock.patch("os.path.isdir", return_value=True):
                with mock.patch("os.walk", return_value=[("/tmp", [], [])]):
                    result = run_c_coverage("/tmp", ci)
                    assert result is True


# =====================================================================
# run_requirements_trace (from stages/traceability.py)
# =====================================================================

class TestRunRequirementsTrace:
    """Cover run_requirements_trace from stages/traceability.py."""

    def test_typical_project(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.traceability import run_requirements_trace

        # Create some test files
        (tmp_path / "specs").mkdir()
        (tmp_path / "specs" / "spec.md").write_text("The system SHALL do X.\nIt SHALL also do Y.\n")
        (tmp_path / "src" / "yuleosh").mkdir(parents=True)
        (tmp_path / "src" / "yuleosh" / "main.py").write_text("")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("")

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_requirements_trace(str(tmp_path), ci)
        assert result is True
        assert any("requirements-trace" in s["name"] for s in ci.stages)

    def test_no_specs_no_src(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.traceability import run_requirements_trace
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_requirements_trace(str(tmp_path), ci)
        assert result is True

    def test_no_shall_keywords(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.traceability import run_requirements_trace
        (tmp_path / "specs").mkdir()
        (tmp_path / "specs" / "spec.md").write_text("No keywords here.")
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_requirements_trace(str(tmp_path), ci)
        assert result is True


# =====================================================================
# Stages: validation.py 
# =====================================================================

class TestRunYamlValidation:
    """Cover run_yaml_validation from stages/validation.py."""

    def test_valid(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_yaml_validation
        with mock.patch("yuleosh.ci.yaml_validator.validate_all",
                        return_value={"valid": True, "errors": {}}):
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_yaml_validation("/tmp/project", ci)
            assert result is True
            assert any("yaml-validation" in s["name"] for s in ci.stages)

    def test_invalid(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_yaml_validation
        with mock.patch("yuleosh.ci.yaml_validator.validate_all",
                        return_value={
                            "valid": False,
                            "errors": {"ci-config": ["error1"], "misra-rules": []},
                        }):
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_yaml_validation("/tmp/project", ci)
            assert result is False
            assert any("yaml-validation" in s["name"] for s in ci.stages)
            assert ci.stages[-1]["status"] == "failed"

    def test_invalid_multiple(self):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_yaml_validation
        with mock.patch("yuleosh.ci.yaml_validator.validate_all",
                        return_value={
                            "valid": False,
                            "errors": {
                                "ci-config": ["err1", "err2", "err3", "err4", "err5", "err6"],
                                "misra-rules": ["err_a"],
                            },
                        }):
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_yaml_validation("/tmp/project", ci)
            assert result is False


class TestRunPlanLint:
    """Cover run_plan_lint from stages/validation.py."""

    def test_no_task_files(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_plan_lint
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_plan_lint(str(tmp_path), ci)
        assert result is True  # skipped

    def test_task_files_present_passing(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_plan_lint
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "task-feature.md").write_text("""
# Feature
kind: feature

RED: test
GREEN: test
REFACTOR: test
""")
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_plan_lint(str(tmp_path), ci)
        assert result is True

    def test_task_files_present_failing(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_plan_lint
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "task-bad.md").write_text("# Bad Task\nNo proper format.\n")
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_plan_lint(str(tmp_path), ci)
        assert result is False  # blocks pipeline


class TestRunClangTidy:
    """Cover run_clang_tidy from stages/validation.py."""

    def test_no_c_files(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_clang_tidy
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_clang_tidy(str(tmp_path), ci)
        assert result is True

    def test_passes(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_clang_tidy
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.c").write_text("int main() { return 0; }")
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_clang_tidy(str(tmp_path), ci)
            assert result is True

    def test_fails(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_clang_tidy
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.c").write_text("int main() { return 0; }")
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = "error: something"
            mock_run.return_value.stderr = ""
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_clang_tidy(str(tmp_path), ci)
            assert result is False

    def test_not_found(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_clang_tidy
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.c").write_text("int main() { return 0; }")
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("clang-tidy")):
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_clang_tidy(str(tmp_path), ci)
            assert result is False

    def test_timeout(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_clang_tidy
        import subprocess as sp
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.c").write_text("int main() { return 0; }")
        with mock.patch("subprocess.run", side_effect=sp.TimeoutExpired("clang-tidy", 30)):
            ci = CIResult(layer=1, commit_hash="abc")
            result = run_clang_tidy(str(tmp_path), ci)
            assert result is False


class TestRunSpecValidation:
    """Cover run_spec_validation from stages/validation.py."""

    def test_missing_specs(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_spec_validation
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True  # warning only

    def test_with_spec_file(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_spec_validation
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "spec.md").write_text("SHALL\nSHOULD\n")
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True

    def test_no_docs_dir(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_spec_validation
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True


class TestRunArchitectureReview:
    """Cover run_architecture_review from stages/validation.py."""

    def test_missing_docs(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_architecture_review
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_architecture_review(str(tmp_path), ci)
        assert result is True  # warning only

    def test_with_docs(self, tmp_path):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages.validation import run_architecture_review
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "positioning-unified.md").write_text("content")
        (docs_dir / "spec.md").write_text("content")
        (tmp_path / "src" / "yuleosh" / "api").mkdir(parents=True)
        (tmp_path / "src" / "yuleosh" / "ci").mkdir()
        ci = CIResult(layer=1, commit_hash="abc")
        result = run_architecture_review(str(tmp_path), ci)
        assert result is True
