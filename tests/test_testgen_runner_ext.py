#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
"""
Extended tests for yuleOSH TestGen Runner — coverage boost for edge cases.

Targets uncovered branches in yuleosh.testgen.runner:
  - TestReport.pass_rate when total=0
  - run_tests() with dry_run=False (mocked)
  - coverage_report() when _last_coverage is None
  - print_report() with None report
  - _execute() with supported languages
  - _build_coverage() full coverage path
  - CoverageReport dataclass to_dict
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.testgen.runner import (
    TestRunner, TestReport, TestResult, CoverageReport, CoverageEntry,
)
from yuleosh.testgen.generator import TestCase


# ══════════════════════════════════════════════════════════════════════════════
# TestReport
# ══════════════════════════════════════════════════════════════════════════════


class TestTestReport:
    """Edge cases for TestReport dataclass."""

    def test_pass_rate_zero_total(self):
        """GIVEN zero total WHEN pass_rate accessed THEN returns 0.0."""
        report = TestReport(total=0, passed=0, failed=0)
        assert report.pass_rate == 0.0

    def test_pass_rate_half(self):
        """GIVEN 5 passed out of 10 WHEN pass_rate THEN returns 50.0."""
        report = TestReport(total=10, passed=5)
        assert report.pass_rate == 50.0

    def test_pass_rate_partial(self):
        """GIVEN 3 passed out of 4 WHEN pass_rate THEN returns 75.0."""
        report = TestReport(total=4, passed=3)
        assert report.pass_rate == 75.0

    def test_to_dict_empty(self):
        """GIVEN empty report WHEN to_dict THEN returns correct dict."""
        r = TestReport()
        d = r.to_dict()
        assert d["total"] == 0
        assert d["passed"] == 0
        assert d["duration_ms"] == 0.0
        assert d["results"] == []

    def test_to_dict_with_results(self):
        """GIVEN report with results WHEN to_dict THEN includes all fields."""
        results = [TestResult(test_id="TC-001", status="PASS")]
        r = TestReport(total=1, passed=1, results=results)
        d = r.to_dict()
        assert d["total"] == 1
        assert len(d["results"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# CoverageEntry + CoverageReport
# ══════════════════════════════════════════════════════════════════════════════


class TestCoverageDataClasses:
    """Tests for CoverageEntry and CoverageReport."""

    def test_coverage_entry_defaults(self):
        """GIVEN CoverageEntry defaults WHEN created THEN uncovered is False."""
        e = CoverageEntry(req_id="RS-001", shall_text="SHALL do X", covered_by=["TC-001"])
        assert e.uncovered is False
        assert e.req_id == "RS-001"

    def test_coverage_entry_uncovered(self):
        """GIVEN empty covered_by WHEN created THEN uncovered is True."""
        e = CoverageEntry(req_id="RS-001", shall_text="SHALL do X", covered_by=[], uncovered=True)
        assert e.uncovered is True

    def test_coverage_report_to_dict(self):
        """GIVEN CoverageReport with entries WHEN to_dict THEN serializes."""
        entry = CoverageEntry("RS-001", "SHALL do X", ["TC-001"])
        r = CoverageReport(total_shall=1, covered_shall=1, coverage_pct=100.0, entries=[entry])
        d = r.to_dict()
        assert d["total_shall"] == 1
        assert len(d["entries"]) == 1
        assert d["entries"][0]["req_id"] == "RS-001"

    def test_coverage_report_to_dict_empty(self):
        """GIVEN empty CoverageReport WHEN to_dict THEN returns empty dict structure."""
        r = CoverageReport()
        d = r.to_dict()
        assert d["total_shall"] == 0
        assert d["entries"] == []


# ══════════════════════════════════════════════════════════════════════════════
# TestRunner
# ══════════════════════════════════════════════════════════════════════════════


class TestTestRunner:
    """Extended tests for TestRunner."""

    def test_constructor(self):
        """GIVEN no args WHEN TestRunner created THEN internal state is None."""
        runner = TestRunner()
        assert runner._last_report is None
        assert runner._last_coverage is None

    def test_coverage_report_when_none(self):
        """GIVEN no coverage computed WHEN coverage_report() THEN returns empty report."""
        runner = TestRunner()
        cr = runner.coverage_report()
        assert cr["total_shall"] == 0
        assert cr["coverage_pct"] == 0.0
        assert cr["entries"] == []

    def test_print_report_none(self, capsys):
        """GIVEN no report WHEN print_report() with None THEN prints 'No report'."""
        runner = TestRunner()
        runner.print_report(None)
        captured = capsys.readouterr()
        assert "No report available." in captured.out

    def test_print_report_with_none(self, capsys):
        """GIVEN runner with no report WHEN print_report() no args THEN prints 'No report'."""
        runner = TestRunner()
        runner.print_report()
        captured = capsys.readouterr()
        assert "No report available." in captured.out

    def test_print_report_with_data(self, capsys):
        """GIVEN report with failures WHEN print_report() THEN prints failure details."""
        runner = TestRunner()
        results = [
            TestResult(test_id="TC-001", status="FAIL", message="GIVEN empty"),
            TestResult(test_id="TC-002", status="ERROR", message="Timeout"),
            TestResult(test_id="TC-003", status="PASS"),
        ]
        report = TestReport(total=3, passed=1, failed=1, errors=1, results=results)
        runner.print_report(report)
        captured = capsys.readouterr()
        assert "TestGen Execution Report" in captured.out
        assert "TC-001" in captured.out
        assert "TC-002" in captured.out
        assert "FAIL" in captured.out
        assert "ERROR" in captured.out

    # ── Dry-run edge cases ──────────────────────────────────────────────

    def test_dry_run_missing_fields(self):
        """GIVEN test case with empty GIVEN/when/then WHEN dry_run THEN FAIL."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="", when="", then="")]
        report = runner.run_tests(cases, "/tmp/project", dry_run=True)
        assert report.failed == 1
        assert report.passed == 0
        # Should identify all three missing fields
        assert "GIVEN empty" in report.results[0].message
        assert "WHEN empty" in report.results[0].message
        assert "THEN empty" in report.results[0].message

    def test_dry_run_invalid_priority(self):
        """GIVEN test case with invalid priority WHEN dry_run THEN FAIL."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z", priority="P5")]
        report = runner.run_tests(cases, "/tmp/project", dry_run=True)
        assert report.failed == 1
        assert "invalid priority 'P5'" in report.results[0].message

    def test_dry_run_empty_shall_ref(self):
        """GIVEN test case with empty shall_ref WHEN dry_run THEN FAIL."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="", scenario="test", given="x", when="y", then="z")]
        report = runner.run_tests(cases, "/tmp/project", dry_run=True)
        assert report.failed == 1
        assert "shall_ref empty" in report.results[0].message

    def test_dry_run_with_nonstandard_tags(self):
        """GIVEN test case with non-standard tags WHEN dry_run THEN still PASS."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test",
                          given="x", when="y", then="z", tags=["custom-e2e"])]
        report = runner.run_tests(cases, "/tmp/project", dry_run=True)
        assert report.passed == 1

    def test_dry_run_partial_failures(self):
        """GIVEN mix of valid and invalid test cases WHEN dry_run THEN reports correctly."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-001", shall_ref="RS-001", scenario="a", given="x", when="y", then="z"),
            TestCase(id="TC-002", shall_ref="", scenario="b", given="", when="", then=""),
            TestCase(id="TC-003", shall_ref="RS-003", scenario="c", given="x", when="y", then="z"),
        ]
        report = runner.run_tests(cases, "/tmp/project", dry_run=True)
        assert report.passed == 2
        assert report.failed == 1
        assert report.total == 3

    # ── _execute: real execution (mocked) ───────────────────────────────

    @patch("yuleosh.testgen.runner.subprocess.run")
    def test_execute_python_passes(self, mock_run):
        """GIVEN python test cases WHEN _execute with dry_run=False THEN runs pytest per case."""
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            report = runner.run_tests(cases, td, dry_run=False, lang="python")
            # Subprocess should have been called for pytest
            assert mock_run.called
            assert report.total == 1

    @patch("yuleosh.testgen.runner.subprocess.run")
    def test_execute_python_fails(self, mock_run):
        """GIVEN python test cases when pytest fails WHEN dry_run=False THEN status FAIL."""
        mock_run.return_value = MagicMock(returncode=1, stderr="AssertionError", stdout="")
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            report = runner.run_tests(cases, td, dry_run=False, lang="python")
            assert report.failed == 1

    @patch("yuleosh.testgen.runner.subprocess.run")
    def test_execute_python_skip(self, mock_run):
        """GIVEN python test when exit code 5 WHEN dry_run=False THEN status SKIP."""
        mock_run.return_value = MagicMock(returncode=5, stderr="", stdout="")
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            report = runner.run_tests(cases, td, dry_run=False, lang="python")
            assert report.skipped == 1

    @patch("yuleosh.testgen.runner.subprocess.run")
    def test_execute_python_timeout(self, mock_run):
        """GIVEN python test when subprocess times out WHEN dry_run=False THEN status ERROR."""
        mock_run.side_effect = __import__("subprocess").TimeoutExpired(cmd="pytest", timeout=60)
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            report = runner.run_tests(cases, td, dry_run=False, lang="python")
            assert report.errors == 1

    @patch("yuleosh.testgen.runner.subprocess.run")
    def test_execute_python_subprocess_error(self, mock_run):
        """GIVEN python test when subprocess raises generic exception WHEN dry_run=False THEN status ERROR."""
        mock_run.side_effect = RuntimeError("Something went wrong")
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            report = runner.run_tests(cases, td, dry_run=False, lang="python")
            assert report.errors == 1

    def test_execute_unsupported_lang(self):
        """GIVEN unsupported language WHEN _execute THEN raises ValueError."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with pytest.raises(ValueError, match="Unsupported language"):
            runner.run_tests(cases, "/tmp/project", dry_run=False, lang="rust")

    def test_execute_go_and_c_skip(self):
        """GIVEN Go/C test cases WHEN _execute THEN marks as SKIP (harness not configured)."""
        runner = TestRunner()
        cases = [TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z")]

        with tempfile.TemporaryDirectory() as td:
            for lang in ("go", "c"):
                report = runner.run_tests(cases, td, dry_run=False, lang=lang)
                assert report.skipped == 1
                assert report.total == 1

    # ── Coverage building ───────────────────────────────────────────────

    def test_run_tests_with_spec_path(self):
        """GIVEN spec_path provided WHEN run_tests THEN builds coverage report."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z"),
        ]

        # Create a temp spec file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Spec\n## RS-001: Requirement\n- The system SHALL do something\n")
            spec_path = f.name

        try:
            with tempfile.TemporaryDirectory() as td:
                report = runner.run_tests(cases, td, dry_run=True, spec_path=spec_path)
                assert report.passed == 1
                # Should have built coverage
                cr = runner.coverage_report()
                assert cr["total_shall"] >= 1
        finally:
            Path(spec_path).unlink(missing_ok=True)

    def test_run_tests_with_bad_spec_path(self):
        """GIVEN invalid spec_path WHEN run_tests THEN handles gracefully (no crash)."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-001", shall_ref="RS-001", scenario="test", given="x", when="y", then="z"),
        ]

        with tempfile.TemporaryDirectory() as td:
            # Spec path that doesn't exist
            report = runner.run_tests(cases, td, dry_run=True, spec_path="/nonexistent/spec.md")
            assert report.passed == 1
            # Coverage should have failed silently
            cr = runner.coverage_report()
            assert cr["total_shall"] == 0

    def test_coverage_report_after_spec_run(self):
        """GIVEN run_tests with valid spec WHEN coverage_report() THEN returns full data."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-001", shall_ref="RS-001", scenario="t1", given="x", when="y", then="z"),
            TestCase(id="TC-002", shall_ref="RS-002", scenario="t2", given="a", when="b", then="c"),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Spec\n"
                    "## RS-001: Requirement A\n- The system SHALL do X\n"
                    "## RS-002: Requirement B\n- The system SHALL do Y\n"
                    "## RS-003: Requirement C\n- The system SHALL do Z\n")
            spec_path = f.name

        try:
            with tempfile.TemporaryDirectory() as td:
                runner.run_tests(cases, td, dry_run=True, spec_path=spec_path)
                cr = runner.coverage_report()
                assert cr["total_shall"] == 3
                assert cr["covered_shall"] == 2
                assert cr["uncovered_shall"] == 1
                assert cr["coverage_pct"] == pytest.approx(66.7, rel=0.1)
        finally:
            Path(spec_path).unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# CoverageReport.to_dict
# ══════════════════════════════════════════════════════════════════════════════


class TestCoverageReportDict:
    """Comprehensive dict serialization tests."""

    def test_full_serialization_roundtrip(self):
        """GIVEN CoverageReport with data WHEN to_dict() THEN round-trips to JSON."""
        e1 = CoverageEntry("RS-001", "SHALL do A", ["TC-001", "TC-002"], uncovered=False)
        e2 = CoverageEntry("RS-002", "SHALL do B", [], uncovered=True)
        cr = CoverageReport(
            total_shall=2,
            covered_shall=1,
            uncovered_shall=1,
            coverage_pct=50.0,
            entries=[e1, e2],
        )
        d = cr.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        assert restored["total_shall"] == 2
        assert restored["covered_shall"] == 1
        assert len(restored["entries"]) == 2
