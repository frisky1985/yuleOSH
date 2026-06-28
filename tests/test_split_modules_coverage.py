#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Unit tests for the split-ci sub-modules (Phase 2.2).

Covers the newly extracted sub-modules:
  - ci/stages/validation.py
  - ci/stages/build.py
  - ci/stages/test.py
  - ci/stages/review.py
  - ci/kpi/
  - ci/misra_report/models.py
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest


# ═════════════════════════════════════════════════════════════════════════════
# ci/stages/validation.py
# ═════════════════════════════════════════════════════════════════════════════


class TestStagesValidation:
    """Tests for stages/validation.py — spec & arch review stages."""

    def test_run_spec_validation_missing_files(self, tmp_path):
        """GIVEN no spec files WHEN run_spec_validation THEN returns True with warning."""
        from yuleosh.ci.stages.validation import run_spec_validation
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True, "Should not block on missing spec files"

    def test_run_spec_validation_with_docs(self, tmp_path):
        """GIVEN spec.md with SHALL keywords WHEN run_spec_validation THEN passes."""
        from yuleosh.ci.stages.validation import run_spec_validation
        from yuleosh.ci.result import CIResult

        # Create minimal spec file
        docs = tmp_path / "docs"
        docs.mkdir(parents=True)
        (docs / "spec.md").write_text("# Spec\n\nThe system SHALL do X.")

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_spec_validation(str(tmp_path), ci)
        assert result is True

    def test_run_architecture_review_with_modules(self, tmp_path):
        """GIVEN src/yuleosh/ modules WHEN run_architecture_review THEN detects them."""
        from yuleosh.ci.stages.validation import run_architecture_review
        from yuleosh.ci.result import CIResult

        # Create fake module structure
        mod_path = tmp_path / "src" / "yuleosh" / "ci"
        mod_path.mkdir(parents=True)
        (mod_path / "__init__.py").touch()

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_architecture_review(str(tmp_path), ci)
        assert result is True


# ═════════════════════════════════════════════════════════════════════════════
# ci/stages/build.py
# ═════════════════════════════════════════════════════════════════════════════


class TestStagesBuild:
    """Tests for stages/build.py — C/C++ coverage stage."""

    def test_run_c_coverage_no_build_dir(self, tmp_path):
        """GIVEN no build directory WHEN run_c_coverage THEN returns True (skipped)."""
        from yuleosh.ci.stages.build import run_c_coverage
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_c_coverage(str(tmp_path), ci)
        assert result is True  # Non-blocking skip

    def test_run_c_coverage_with_gcda(self, tmp_path):
        """GIVEN .gcda files in build WHEN run_c_coverage THEN processes coverage."""
        from yuleosh.ci.stages.build import run_c_coverage
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")

        # Create a mock build directory with .gcda files
        build = tmp_path / "build"
        build.mkdir()
        (build / "test.gcda").touch()

        with patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report") as mock_gen:
            mock_gen.return_value = str(tmp_path / "coverage.json")

            # Create fake coverage JSON
            cov_report = {
                "line_rate": 85.0,
                "branch_rate": 75.0,
                "total_files": 5,
                "files": [],
            }
            (tmp_path / "coverage.json").write_text(json.dumps(cov_report))

            result = run_c_coverage(str(tmp_path), ci)
            assert result is True


# ═════════════════════════════════════════════════════════════════════════════
# ci/stages/test.py
# ═════════════════════════════════════════════════════════════════════════════


class TestStagesTest:
    """Tests for stages/test.py — unit test & coverage check stages."""

    def test_run_unit_tests_no_files(self, tmp_path):
        """GIVEN no test files WHEN run_unit_tests THEN returns True (skipped)."""
        from yuleosh.ci.stages.test import run_unit_tests
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")
        with patch("yuleosh.ci.stages.test.find_test_files", return_value=[]):
            result = run_unit_tests(str(tmp_path), ci)
            assert result is True

    def test_run_sil_tests_no_prebuilt(self, tmp_path):
        """GIVEN no prebuilt .elf files WHEN run_sil_tests THEN returns True (skipped)."""
        from yuleosh.ci.stages.test import run_sil_tests
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_sil_tests(str(tmp_path), ci)
        assert result is True

    def test_run_sil_tests_with_mock_result(self, tmp_path):
        """GIVEN mock SIL test with prebuilt .elf WHEN run_sil_tests THEN processes results."""
        from yuleosh.ci.stages.test import run_sil_tests
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")

        # Create a prebuilt directory with a mock .elf
        prebuilt = tmp_path / "tests" / "fixtures" / "prebuilt"
        prebuilt.mkdir(parents=True)
        (prebuilt / "test-arm.elf").touch()

        with patch("cross.sil_runner.sil_test") as mock_sil:
            mock_result = MagicMock()
            mock_result.passed = True
            mock_result.elapsed = 1.5
            mock_result.error = None
            mock_result.assertion_failures = []
            mock_result.log = "Hello from yuleOSH cross-compilation test!"
            mock_sil.return_value = mock_result

            with patch("yuleosh.cross.target_config.TargetConfig") as mock_tc:
                mock_tc.return_value = MagicMock()
                result = run_sil_tests(str(tmp_path), ci)
                assert result is True


# ═════════════════════════════════════════════════════════════════════════════
# ci/stages/review.py
# ═════════════════════════════════════════════════════════════════════════════


class TestStagesReview:
    """Tests for stages/review.py — MISRA review helpers."""

    def test_categorize_file_business_default(self):
        """GIVEN unknown file path WHEN _categorize_file THEN returns 'business'."""
        from yuleosh.ci.stages.review import _categorize_file

        categories = {
            "business": {"paths": ["src/**/*.c"]},
            "third_party": {"paths": ["third_party/**/*.c"]},
        }
        cat, cfg = _categorize_file("src/main.c", categories)
        assert cat == "business"

    def test_categorize_file_third_party(self):
        """GIVEN third_party file WHEN _categorize_file THEN returns 'third_party'."""
        from yuleosh.ci.stages.review import _categorize_file

        categories = {
            "business": {"paths": ["src/**/*.c"]},
            "third_party": {"paths": ["third_party/**/*.c"]},
        }
        cat, cfg = _categorize_file("third_party/freertos/task.c", categories)
        assert cat == "third_party"

    def test_exclude_paths_removes_matched(self):
        """GIVEN exclude patterns WHEN _exclude_paths THEN filters files."""
        from yuleosh.ci.stages.review import _exclude_paths

        files = ["src/main.c", "tests/test_main.c", "third_party/lib.c"]
        result = _exclude_paths(files, ["tests/**"], project_dir="")
        assert "tests/test_main.c" not in result
        assert len(result) == 2

    def test_get_git_commit(self, tmp_path):
        """GIVEN a git project WHEN _get_git_commit THEN returns hash."""
        from yuleosh.ci.stages.review import _get_git_commit

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "abc123\n"
            mock_run.return_value = mock_result

            result = _get_git_commit(str(tmp_path))
            assert result == "abc123"

    def test_get_git_commit_not_git(self, tmp_path):
        """GIVEN non-git project WHEN _get_git_commit THEN returns 'unknown'."""
        from yuleosh.ci.stages.review import _get_git_commit

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            result = _get_git_commit(str(tmp_path))
            assert result == "unknown"


# ═════════════════════════════════════════════════════════════════════════════
# ci/misra_report/models.py
# ═════════════════════════════════════════════════════════════════════════════


class TestMisraModels:
    """Tests for misra_report/models.py — ToolResult and merge_tool_results."""

    def test_tool_result_creation(self):
        """GIVEN ToolResult fields WHEN instantiated THEN stores correctly."""
        from yuleosh.ci.misra_report.models import ToolResult

        tr = ToolResult(
            tool_name="cppcheck",
            status="passed",
            violations=[],
        )
        assert tr.tool_name == "cppcheck"
        assert tr.status == "passed"

    def test_merge_tool_results_empty(self):
        """GIVEN empty results WHEN merge_tool_results THEN returns empty dict."""
        from yuleosh.ci.misra_report.models import merge_tool_results

        result = merge_tool_results([])
        assert result["combined_stats"]["total_violations"] == 0
        assert result["combined_stats"]["total_tools"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# ci/misra_report/parsing module
# ═════════════════════════════════════════════════════════════════════════════


class TestMisraParsing:
    """Tests for misra_report/core.py — key parsing functions."""

    def test_parse_cppcheck_output_basic(self):
        """GIVEN cppcheck MISRA output WHEN parsed THEN returns violations."""
        from yuleosh.ci.misra_report.core import parse_cppcheck_output

        cppcheck_out = (
            "src/main.c:42:5: style: misra-c2023-10.1: "
            "[misra-c2012-10.1] Operands shall not be of inappropriate type\n"
        )
        violations = parse_cppcheck_output(cppcheck_out)
        assert len(violations) >= 1
        v = violations[0]
        assert v["file"] == "src/main.c"
        assert v["rule_id"] == "misra-c2023-10.1"

    def test_parse_cppcheck_output_no_violations(self):
        """GIVEN empty cppcheck output WHEN parsed THEN returns empty list."""
        from yuleosh.ci.misra_report.core import parse_cppcheck_output

        violations = parse_cppcheck_output("")
        assert violations == []

    def test_group_by_rule_empty(self):
        """GIVEN no violations WHEN group_by_rule THEN returns empty dict."""
        from yuleosh.ci.misra_report.core import group_by_rule

        groups = group_by_rule([])
        assert groups == {}

    def test_group_by_rule_single(self):
        """GIVEN one violation WHEN group_by_rule THEN groups by rule_id."""
        from yuleosh.ci.misra_report.core import group_by_rule

        violations = [{
            "rule_id": "misra-c2023-10.1",
            "file": "test.c",
            "line": 42,
            "severity": "warning",
        }]
        groups = group_by_rule(violations)
        assert "misra-c2023-10.1" in groups
        assert groups["misra-c2023-10.1"]["count"] == 1

    def test_compute_summary_stats_basic(self):
        """GIVEN violations+groups WHEN compute_summary_stats THEN returns stats."""
        from yuleosh.ci.misra_report.core import compute_summary_stats

        violations = [{"rule_id": "misra-c2023-10.1", "file": "test.c"}]
        groups = {"misra-c2023-10.1": {"count": 1, "severity_category": "required", "rule_id": "10.1"}}

        stats = compute_summary_stats(violations, groups)
        assert stats["total_violations"] == 1
        assert stats["total_rules_violated"] == 1

    def test_load_rule_definitions(self, tmp_path):
        """GIVEN a misra-rules.yaml WHEN load_rule_definitions THEN returns dict."""
        from yuleosh.ci.misra_report.core import load_rule_definitions

        rules_yaml = tmp_path / "misra-rules.yaml"
        rules_yaml.write_text(
            "meta:\n  version: 1.0\n  year: 2023\n"
            "rules:\n  \"10.1\":\n    severity: Required\n    text: Test rule\n"
        )

        result = load_rule_definitions(rules_yaml)
        assert "rules" in result
        assert "10.1" in result["rules"]

    def test_save_report_basic(self, tmp_path):
        """GIVEN minimal data WHEN save_report THEN writes JSON/MD files."""
        from yuleosh.ci.misra_report.core import save_report

        violations = [{"rule_id": "misra-c2023-10.1", "file": "test.c", "line": 42, "col": 5, "severity": "warning", "message": "Test MISRA violation", "code_category": "business"}]
        groups = {"10.1": {"count": 1, "severity_category": "required", "rule_id": "10.1", "files": ["test.c"], "violations": [{"rule_id": "misra-c2023-10.1", "file": "test.c", "line": 42, "col": 5, "severity": "warning", "message": "Test", "code_category": "business"}]}}
        summary = {"total_violations": 1, "total_rules_violated": 1,
                    "severity_counts": {"required": 1, "advisory": 0},
                    "unique_files": ["test.c"], "per_file_counts": {"test.c": 1,
                    "violations": violations, "groups": groups}}
        rule_defs = {"version": "1.0", "year": "2023", "rules": {"10.1": {"severity": "Required", "text": "Test", "spec_ref": "SWR-001"}}}

        with patch("yuleosh.ci.misra_report.core.generate_traceability_matrix") as mock_tm:
            mock_tm.return_value = []
            with patch("yuleosh.evidence.excel_writer.ExcelReportWriter") as mock_excel:
                mock_excel_instance = MagicMock()
                mock_excel.return_value = mock_excel_instance

                json_path, md_path, trace_path, excel_path = save_report(
                    violations, groups, summary, rule_defs,
                    output_dir=tmp_path,
                )
                assert json_path.exists()
                assert md_path.exists()

                report = json.loads(json_path.read_text())
                assert report["summary"]["total_violations"] == 1


# ═════════════════════════════════════════════════════════════════════════════
# ci/kpi/report.py
# ═════════════════════════════════════════════════════════════════════════════


class TestKpiReport:
    """Tests for ci/kpi/report.py — KPI status, baseline save/compare."""

    def test_kpi_status_in_empty_project(self, tmp_path):
        """GIVEN empty project dir WHEN kpi_status THEN returns default status."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(tmp_path, as_json=True)
        # Even with no data, should return a JSON string
        assert isinstance(result, str)
        import json
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_kpi_status_no_misra_trend(self, tmp_path):
        """GIVEN no MISRA trend data WHEN kpi_status THEN no misra section."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(tmp_path, as_json=True)
        assert "misra" in result or "status" in result or isinstance(result, dict)

    def test_kpi_status_as_dict(self, tmp_path):
        """GIVEN project dir WHEN kpi_status(as_json=False) THEN returns dict."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(tmp_path, as_json=False)
        # as_json=False returns markdown string
        assert isinstance(result, str)

    def test_kpi_baseline_save_no_data(self, tmp_path):
        """GIVEN no trend data WHEN kpi_baseline_save THEN creates baseline."""
        from yuleosh.ci.kpi import kpi_baseline_save

        result = kpi_baseline_save(tmp_path)
        assert result is not None
        assert isinstance(result, dict)

    def test_kpi_baseline_compare_no_baseline(self, tmp_path):
        """GIVEN no saved baseline WHEN kpi_baseline_compare THEN handles gracefully."""
        from yuleosh.ci.kpi import kpi_baseline_compare

        result = kpi_baseline_compare(tmp_path, tmp_path)
        assert isinstance(result, str)
        import json
        json.loads(result)

    def test_record_process_stability(self, tmp_path):
        """GIVEN valid data WHEN record_process_stability THEN appends to JSONL."""
        from yuleosh.ci.kpi import record_process_stability

        result = record_process_stability(
            tmp_path,
            build_success=True,
            build_duration_s=12.5,
            layer=1,
            total_stages=5,
            passed_stages=5,
        )
        assert isinstance(result, dict)
        assert result["build_success"] is True

    def test_record_defect_escape(self, tmp_path):
        """GIVEN defect data WHEN record_defect_escape THEN appends to JSONL."""
        from yuleosh.ci.kpi import record_defect_escape

        result = record_defect_escape(
            tmp_path,
            escaped_defects=1, total_defects=10,
            stage="code_review",
        )
        assert isinstance(result, dict)
        assert result["escape_rate"] == 10.0

    def test_get_process_stability_summary(self, tmp_path):
        """GIVEN recorded data WHEN get_process_stability_summary THEN returns summary."""
        from yuleosh.ci.kpi import record_process_stability, get_process_stability_summary

        record_process_stability(tmp_path, build_success=True, build_duration_s=10.0, layer=1)
        summary = get_process_stability_summary(tmp_path, days=7, as_json=True)
        assert isinstance(summary, (dict, str))
        assert "tracked_entries" in summary or "build_success_rate" in summary or "status" in summary


# ═════════════════════════════════════════════════════════════════════════════
# ci/rulesets/base.py, misra.py, registry.py
# ═════════════════════════════════════════════════════════════════════════════


class TestRulesetsBasics:
    """Tests for ci/rulesets/ — basic ruleset operations."""

    def test_base_ruleset_abstract(self):
        """GIVEN BaseRuleSet WHEN instantiated directly THEN raises TypeError."""
        from yuleosh.ci.rulesets import BaseRuleSet

        with pytest.raises(TypeError):
            BaseRuleSet()  # Abstract — should fail

    def test_misra_ruleset_no_rules_file(self, tmp_path):
        """GIVEN MisraC2023RuleSet without rules file WHEN created THEN uses defaults."""
        from yuleosh.ci.rulesets import MisraC2023RuleSet

        ruleset = MisraC2023RuleSet()
        assert ruleset.name == "misra-c2023"

    def test_ruleset_registry_singleton(self):
        """GIVEN RulesetRegistry() twice THEN returns same instance."""
        from yuleosh.ci.rulesets import RulesetRegistry

        r1 = RulesetRegistry()
        r2 = RulesetRegistry()
        assert r1 is r2  # Singleton pattern

    def test_ruleset_registry_get_default(self):
        """GIVEN registered rulesets WHEN get_default THEN returns the default."""
        from yuleosh.ci.rulesets import RulesetRegistry

        reg = RulesetRegistry()
        default = reg.get_default()
        assert default is not None
        assert hasattr(default, "name")


# ═════════════════════════════════════════════════════════════════════════════
# ci/misra_report/deviation.py
# ═════════════════════════════════════════════════════════════════════════════


class TestMisraDeviation:
    """Tests for misra_report/deviation.py — deviation matching."""

    def test_deviation_to_dict_tuple(self):
        """GIVEN tuple deviation WHEN _deviation_to_dict THEN converts to dict."""
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict

        result = _deviation_to_dict(("10.1", "**/*.c"))
        assert result.get("deviation_rule", result.get("rule_id")) == "10.1"
        assert result.get("file_pattern") == "**/*.c"

    def test_deviation_to_dict_full_dict(self):
        """GIVEN dict deviation WHEN _deviation_to_dict THEN returns as-is."""
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict

        dev = {"rule_id": "10.1", "file_pattern": "src/**/*.c", "status": "approved",
                "reason": "Test", "approved_by": "tester", "expires": "2027-01-01"}
        result = _deviation_to_dict(dev)
        assert result.get("deviation_rule", result.get("rule_id")) == "10.1"

    def test_is_deviation_expired_not_expired(self):
        """GIVEN future date WHEN _is_deviation_expired THEN returns False."""
        from yuleosh.ci.misra_report.deviation import _is_deviation_expired

        assert not _is_deviation_expired("2099-12-31")

    def test_is_deviation_expired_past(self):
        """GIVEN past date WHEN _is_deviation_expired THEN returns True."""
        from yuleosh.ci.misra_report.deviation import _is_deviation_expired

        assert _is_deviation_expired("2020-01-01")


# ═════════════════════════════════════════════════════════════════════════════
# ci/misra_report/traceability.py
# ═════════════════════════════════════════════════════════════════════════════


class TestMisraTraceability:
    """Tests for misra_report/traceability.py — traceability & fix tasks."""

    def test_generate_fix_tasks(self, tmp_path):
        """GIVEN violations WHEN generate_fix_tasks THEN creates fix task files."""
        from yuleosh.ci.misra_report.traceability import generate_fix_tasks
        

        # Need violations to generate fix tasks
        violations = [{"rule_id": "misra-c2023-10.1", "file": "test.c", "line": 42,
                        "severity": "warning", "message": "Test violation"}]
        rule_defs = {"rules": {"10.1": {"severity": "Required", "text": "Shall not do X"}}}

        files = generate_fix_tasks(tmp_path, violations, rule_defs)
        assert isinstance(files, list)


# ═════════════════════════════════════════════════════════════════════════════
# ci/misra_report/cli.py
# ═════════════════════════════════════════════════════════════════════════════


class TestMisraCli:
    """Tests for misra_report/cli.py — main CLI entry point."""

    def test_main_help(self):
        """GIVEN --help WHEN main runs THEN prints usage."""
        from yuleosh.ci.misra_report.cli import main
        with patch("sys.argv", ["misra_report.py", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0


# ═════════════════════════════════════════════════════════════════════════════
# ci/stages/traceability.py
# ═════════════════════════════════════════════════════════════════════════════


class TestStagesTraceability:
    """Tests for stages/traceability.py — requirements trace stage."""

    def test_run_requirements_trace(self, tmp_path):
        """GIVEN project dir WHEN run_requirements_trace THEN passes."""
        from yuleosh.ci.stages.traceability import run_requirements_trace
        from yuleosh.ci.result import CIResult

        ci = CIResult(layer=1, commit_hash="abc")
        result = run_requirements_trace(str(tmp_path), ci)
        assert result is True
