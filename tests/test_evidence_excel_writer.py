# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for evidence/excel_writer.py — coverage target ≥50%."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# ExcelReportWriter — MISRA report
# ===================================================================


class TestExcelReportWriter:
    def test_init_creates_dir(self, tmp_path):
        """GIVEN output dir WHEN initializing writer THEN creates parent directory."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        out_dir = tmp_path / "deep" / "nested"
        writer = ExcelReportWriter(out_dir)
        assert out_dir.exists()

    def test_write_misra_report_basic(self, tmp_path):
        """GIVEN basic misra data WHEN writing Excel THEN creates file."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        violations = [
            {"rule_id": "R1", "file": "test.c", "line": 10, "col": 1,
             "message": "Violation", "severity": "error", "fix_status": "unresolved"},
        ]
        groups = {
            "R1": {"severity_category": "required", "count": 1, "title": "R1 title", "files": ["test.c"]},
        }
        summary = {
            "total_violations": 1, "total_kloc": 1.0,
            "misra_classification": {"required": 1, "advisory": 0, "directive": 0, "project_specific": 0},
            "violations_per_kloc": 1.0, "unique_files": ["test.c"],
            "severity_counts": {"error": 1, "warning": 0, "style": 0, "information": 0},
        }
        rule_defs = {}
        out = writer.write_misra_report(violations, groups, summary, rule_defs)
        assert out.exists()
        assert out.suffix == ".xlsx"

    def test_misra_report_with_deviations(self, tmp_path):
        """GIVEN deviations data WHEN writing MISRA Excel THEN Deviations sheet is written."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        violations = []
        groups = {}
        summary = {
            "total_violations": 0, "total_kloc": 0,
            "misra_classification": {"required": 0, "advisory": 0, "directive": 0, "project_specific": 0},
            "violations_per_kloc": 0, "unique_files": [],
            "severity_counts": {"error": 0, "warning": 0, "style": 0, "information": 0},
        }
        rule_defs = {}
        deviations = [
            {"rule_id": "D1", "file_pattern": "*.c", "reason": "Deviation reason",
             "status": "pending", "risk_level": "mid", "expires": "2099-01-01",
             "approved_by": "reviewer", "alm_ticket": "TICKET-1"},
        ]
        out = writer.write_misra_report(violations, groups, summary, rule_defs, deviations)
        assert out.exists()

    def test_misra_report_expired_deviation(self, tmp_path):
        """GIVEN expired deviation WHEN writing THEN highlights it."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        violations = []
        groups = {}
        summary = {
            "total_violations": 0, "total_kloc": 0,
            "misra_classification": {"required": 0, "advisory": 0, "directive": 0, "project_specific": 0},
            "violations_per_kloc": 0, "unique_files": [],
            "severity_counts": {"error": 0, "warning": 0, "style": 0, "information": 0},
        }
        rule_defs = {}
        deviations = [
            {"rule_id": "E1", "file_pattern": "old.c", "reason": "Old",
             "status": "approved", "risk_level": "low", "expires": "2020-01-01",
             "approved_by": "dev", "alm_ticket": ""},
        ]
        out = writer.write_misra_report(violations, groups, summary, rule_defs, deviations)
        assert out.exists()

    def test_misra_traceability_sheet(self, tmp_path):
        """GIVEN violations with rule_defs WHEN writing Excel THEN Traceability sheet has entries."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        violations = [{"rule_id": "R1", "file": "a.c", "line": 1, "col": 1,
                       "message": "m", "severity": "error", "fix_status": "open"}]
        groups = {"R1": {"severity_category": "required", "count": 1, "title": "T", "files": ["a.c"]}}
        summary = {
            "total_violations": 1, "total_kloc": 0.5,
            "misra_classification": {"required": 1, "advisory": 0, "directive": 0, "project_specific": 0},
            "violations_per_kloc": 2.0, "unique_files": ["a.c"],
            "severity_counts": {"error": 1, "warning": 0, "style": 0, "information": 0},
        }
        rule_defs = {"R1": {"spec_ref": "SPEC-01", "impl_ref": "impl()", "test_ref": "test_R1",
                            "check_method": "cppcheck", "auto_checkable": True}}
        out = writer.write_misra_report(violations, groups, summary, rule_defs)
        assert out.exists()

    def test_deviation_tuple_input(self, tmp_path):
        """GIVEN deviation as tuple WHEN writing Excel THEN converts to dict."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        # Test _deviation_to_dict with tuple input
        result = writer._deviation_to_dict(("R1", "*.c", "reason", "approver", "mid", "", "pending", ""))
        assert result["deviation_rule"] == "R1"
        assert result["file_pattern"] == "*.c"

    def test_deviation_object_input(self, tmp_path):
        """GIVEN deviation as object WHEN writing Excel THEN extracts attributes."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        class DevObj:
            rule_id = "R2"
            file_pattern = "*.h"
            reason = "test"
            approved_by = "user"
            risk_level = "high"
            expires = ""
            status = "approved"
            alm_ticket = "T-2"
        result = writer._deviation_to_dict(DevObj())
        assert result["deviation_rule"] == "R2"


# ===================================================================
# ExcelReportWriter — Self-test report
# ===================================================================


class TestExcelReportWriterSelftest:
    def test_write_selftest_report_basic(self, tmp_path):
        """GIVEN basic review data WHEN writing self-test Excel THEN creates file."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        review = {
            "session": "test-session",
            "pass_rate": 85.0, "total_passed": 4, "total_failed": 1,
            "total_skipped": 0, "total_errors": 0, "duration_sec": 10.0,
            "status": "passed",
            "shall_total": 5, "shall_covered": 4,
            "shall_unknown": 1, "shall_uncovered": ["Missing SHALL"],
            "shall_statements": [
                {"statement": "System SHALL work", "section": "Req1", "line": 1},
                {"statement": "System MAY log", "section": "Req2", "line": 2},
            ],
            "shall_auto_mapping": {"System SHALL work": ["test_work"]},
            "shall_assertion_map": {"System SHALL work": {"test_work": [10, 20]}},
            "test_case_results": [
                {"name": "test_work", "status": "passed", "duration": 0.5, "type": "unit"},
                {"name": "test_fail", "status": "failed", "duration": 0.3,
                 "message": "assert 0", "failure": {"type": "AssertionError",
                 "stacktrace": "File test.py:10"}},
                {"name": "test_skip", "status": "skipped", "duration": 0.0, "type": "unit"},
            ],
            "coverage": {
                "line_rate": 80.0, "branch_rate": 70.0, "function_rate": 75.0,
                "per_file": [
                    {"file": "src/main.py", "line_rate": 90.0, "branch_rate": 80.0,
                     "function_rate": 85.0},
                ],
            },
            "test_gap_areas": ["Missing alert test"],
            "findings": [{"severity": "major", "message": "Gap in coverage"}],
            "finding_breakdown": {"critical": 0, "major": 1, "minor": 0, "info": 0},
            "environment": {"platform": "linux"},
            "regression_analysis": {},
            "build_id": "CI-1",
        }
        out = writer.write_selftest_report(review)
        assert out.exists()
        assert out.suffix == ".xlsx"

    def test_selftest_with_no_statements(self, tmp_path):
        """GIVEN review without shall_statements WHEN writing Excel THEN falls back to auto_mapping."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        review = {
            "session": "test", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed",
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "shall_statements": [],
            "shall_auto_mapping": {"SHALL x": ["test_x"]},
            "shall_assertion_map": {},
            "test_case_results": [{"name": "test_x", "status": "passed", "duration": 0.1, "type": "unit"}],
            "coverage": {"line_rate": 100, "branch_rate": 100, "function_rate": 100,
                         "per_file": []},
            "test_gap_areas": [],
            "findings": [],
            "finding_breakdown": {},
        }
        out = writer.write_selftest_report(review)
        assert out.exists()

    def test_selftest_coverage_no_perfile(self, tmp_path):
        """GIVEN review without per_file coverage WHEN writing Excel THEN handles gracefully."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        review = {
            "session": "test", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed",
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "shall_statements": [],
            "test_case_results": [],
            "coverage": {"line_rate": 0, "branch_rate": 0, "function_rate": 0},
            "test_gap_areas": [],
            "findings": [],
            "finding_breakdown": {},
        }
        out = writer.write_selftest_report(review)
        assert out.exists()


# ===================================================================
# Helper functions
# ===================================================================


class TestHelperFunctions:
    def test_get_tool_version(self, tmp_path):
        """GIVEN _get_tool_version WHEN called THEN returns string."""
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        writer = ExcelReportWriter(tmp_path)
        version = writer._get_tool_version()
        assert isinstance(version, str)

    def test_to_absolute_path(self):
        """GIVEN relative path WHEN converting to absolute THEN returns file:// URI."""
        from yuleosh.evidence.excel_writer import _to_absolute_path
        result = _to_absolute_path("test.py")
        assert result.startswith("file://")

    def test_to_absolute_path_absolute(self, tmp_path):
        """GIVEN absolute path WHEN converting THEN returns file:// URI."""
        from yuleosh.evidence.excel_writer import _to_absolute_path
        result = _to_absolute_path(str(tmp_path / "test.py"))
        assert result.startswith("file://")

    def test_severity_fill_required(self):
        """GIVEN required severity WHEN getting fill THEN returns red fill."""
        from yuleosh.evidence.excel_writer import _severity_fill
        fill = _severity_fill("required")
        assert fill is not None
        assert "FFD7D7" in str(fill.start_color.rgb)

    def test_severity_fill_advisory(self):
        """GIVEN advisory severity WHEN getting fill THEN returns yellow fill."""
        from yuleosh.evidence.excel_writer import _severity_fill
        fill = _severity_fill("advisory")
        assert fill is not None
        assert "FFFFE0" in str(fill.start_color.rgb)

    def test_severity_fill_unknown(self):
        """GIVEN unknown severity WHEN getting fill THEN returns None."""
        from yuleosh.evidence.excel_writer import _severity_fill
        fill = _severity_fill("unknown")
        assert fill is None

    def test_status_fill(self):
        """GIVEN various statuses WHEN getting fill THEN returns correct colors."""
        from yuleosh.evidence.excel_writer import _status_fill
        assert _status_fill("failed") is not None
        assert _status_fill("error") is not None
        assert _status_fill("passed") is not None
        assert _status_fill("skipped") is not None
        assert _status_fill("unknown") is None

    def test_coverage_fill(self):
        """GIVEN various coverage rates WHEN getting fill THEN returns correct thresholds."""
        from yuleosh.evidence.excel_writer import _coverage_fill
        assert _coverage_fill(95.0) is not None  # green
        assert _coverage_fill(85.0) is not None  # yellow
        assert _coverage_fill(50.0) is not None  # red
