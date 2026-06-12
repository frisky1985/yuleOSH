#!/usr/bin/env python3
"""
Tests for yuleOSH TestGen — AI-powered test case generator from OpenSpec.

Validates:
  1. TestGenerator: LLM-based generation from spec → TestCase objects.
  2. Formatter: pytest, Go test, Ceedling output formats.
  3. Runner: dry-run validation and coverage reporting.
  4. Effectiveness estimation via LLM (mocked).
  5. Quick (deterministic) coverage analysis.
"""

import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/testgen is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from testgen.generator import TestGenerator, TestCase
from testgen.runner import TestRunner, TestReport, TestResult, CoverageReport
from testgen.formatter import format_pytest, format_gotest, format_ceedling


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


def _sample_spec_text() -> str:
    """Return a minimal OpenSpec document for testing."""
    return """# BLE Sensor — Test Spec

## RS-001: BLE Advertising
- The system SHALL advertise Eddystone frames at 100 ms interval
- The system SHALL support advertisement intervals between 100 ms and 10000 ms
- The system SHOULD dynamically adjust power
- The system MAY support iBeacon format

#### Reason
Core BLE beacon functionality.

## RS-002: Temperature Sensing
- The system SHALL read ambient temperature with ±0.5°C accuracy
- The system SHALL sample at configurable intervals

#### Reason
Primary sensing function.

## Scenario: Normal Operation
- GIVEN the sensor is powered
- WHEN it initialises
- THEN it SHALL begin advertising within 2 seconds

## Scenario: Config Update
- GIVEN the sensor is advertising
- WHEN a GATT write updates the interval
- THEN the new interval SHALL be persisted to flash
"""


def _write_temp_spec(text: str = None) -> str:
    """Write a spec to a temp file and return its path."""
    if text is None:
        text = _sample_spec_text()
    fd, path = tempfile.mkstemp(suffix=".md", prefix="test_spec_", text=True)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def _make_mock_llm(json_response: list | dict) -> MagicMock:
    """Create a mock LLM that returns a given JSON response."""
    mock = MagicMock()
    mock.chat_completion.return_value = {
        "content": json.dumps(json_response, ensure_ascii=False),
        "model": "mock-model",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    return mock


def _sample_test_cases() -> list[TestCase]:
    """Return a list of sample TestCase objects for formatting tests."""
    return [
        TestCase(
            id="TC-001",
            shall_ref="RS-001",
            scenario="BLE advertises Eddystone frames at default interval",
            given="BLE sensor is powered with fresh battery",
            when="sensor initialises with default configuration",
            then="system SHALL begin advertising Eddystone frames within 2 seconds",
            priority="P0",
            tags=["smoke", "unit"],
        ),
        TestCase(
            id="TC-002",
            shall_ref="RS-001",
            scenario="BLE advertising interval boundaries",
            given="BLE sensor is advertising with interval=100ms",
            when="configuration changes interval to 10000ms",
            then="system SHALL advertise at the new interval",
            priority="P1",
            tags=["boundary", "regression"],
        ),
        TestCase(
            id="TC-003",
            shall_ref="RS-002",
            scenario="Temperature accuracy within spec",
            given="sensor is in a controlled environment at 25°C",
            when="temperature is read from the sensor",
            then="reading SHALL be within ±0.5°C of reference",
            priority="P1",
            tags=["unit", "regression"],
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Test: TestGenerator — LLM-based generation
# ══════════════════════════════════════════════════════════════════════════════


class TestGeneratorFromSpec:
    """Verify the end-to-end flow: spec → LLM prompt → parsed TestCase objects."""

    def test_generate_returns_cases(self):
        """Happy path: mock LLM returns valid JSON array → returns TestCase list."""
        mock_llm = _make_mock_llm([
            {
                "id": "TC-001",
                "shall_ref": "RS-001",
                "scenario": "BLE starts advertising",
                "given": "Sensor powered",
                "when": "Init",
                "then": "Advertise within 2s",
                "priority": "P0",
                "tags": ["smoke"],
            },
        ])
        gen = TestGenerator(mock_llm)
        spec_path = _write_temp_spec()
        try:
            cases = gen.generate_from_spec(spec_path, temperature=0.1)
            assert len(cases) == 1
            assert cases[0].id == "TC-001"
            assert cases[0].shall_ref == "RS-001"
            assert cases[0].priority == "P0"
            assert cases[0].tags == ["smoke"]
        finally:
            os.unlink(spec_path)

    def test_generate_handles_empty_response(self):
        """Edge case: LLM returns empty string → empty list."""
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = {"content": "", "model": "m"}
        gen = TestGenerator(mock_llm)
        spec_path = _write_temp_spec()
        try:
            cases = gen.generate_from_spec(spec_path)
            assert cases == []
        finally:
            os.unlink(spec_path)

    def test_generate_handles_malformed_json(self):
        """Edge case: LLM returns non-JSON → empty list with log warning."""
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = {
            "content": "I think the test cases should be...",
            "model": "m",
        }
        gen = TestGenerator(mock_llm)
        spec_path = _write_temp_spec()
        try:
            cases = gen.generate_from_spec(spec_path)
            assert cases == []
        finally:
            os.unlink(spec_path)

    def test_generate_strips_markdown_fences(self):
        """Handles LLM responses wrapped in ```json ... ``` fences."""
        mock_llm = MagicMock()
        payload = [
            {"id": "TC-X1", "shall_ref": "RS-001", "scenario": "X", "given": "A",
             "when": "B", "then": "C", "priority": "P1", "tags": ["unit"]},
        ]
        mock_llm.chat_completion.return_value = {
            "content": f"```json\n{json.dumps(payload)}\n```",
            "model": "m",
        }
        gen = TestGenerator(mock_llm)
        spec_path = _write_temp_spec()
        try:
            cases = gen.generate_from_spec(spec_path)
            assert len(cases) == 1
            assert cases[0].id == "TC-X1"
        finally:
            os.unlink(spec_path)

    def test_quick_coverage_deterministic(self):
        """quick_coverage computes SHALL coverage without LLM."""
        mock_llm = _make_mock_llm([])
        gen = TestGenerator(mock_llm)
        spec_path = _write_temp_spec()

        try:
            # Build a manual Case
            cases = [
                TestCase(id="TC-001", shall_ref="RS-001",
                         scenario="S", given="A", when="B", then="C",
                         priority="P1", tags=["unit"]),
            ]
            cov = gen.quick_coverage(cases, spec_path=spec_path)
            assert cov["total_shall_refs"] > 0
            assert cov["total_test_cases"] == 1
            assert "shall_coverage_pct" in cov
            assert "boundary_coverage_pct" in cov
        finally:
            os.unlink(spec_path)

    def test_quick_coverage_no_spec_error(self):
        """quick_coverage raises if neither spec_path nor doc provided."""
        gen = TestGenerator(_make_mock_llm([]))
        try:
            gen.quick_coverage([])
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_estimate_effectiveness_mocked(self):
        """estimate_effectiveness calls LLM and returns parsed result."""
        mock_llm = _make_mock_llm({
            "shall_coverage_pct": 85.0,
            "boundary_coverage_pct": 40.0,
            "negative_tests": 2,
            "estimation": "good",
            "gaps": ["No negative test for sensor failure"],
        })
        gen = TestGenerator(mock_llm)
        cases = _sample_test_cases()
        result = gen.estimate_effectiveness(cases, spec_path=_write_temp_spec())
        assert result["shall_coverage_pct"] == 85.0
        assert result["estimation"] == "good"
        assert len(result["gaps"]) == 1

    def test_generate_code_tests_c(self):
        """generate_code_tests with lang='c' delegates to format_ceedling."""
        gen = TestGenerator(_make_mock_llm([]))
        cases = _sample_test_cases()
        code = gen.generate_code_tests(cases, lang="c")
        assert 'Unity' in code or 'unity.h' in code
        assert "TC-001" in code
        assert "TC-002" in code

    def test_generate_code_tests_python(self):
        """generate_code_tests with lang='python' delegates to format_pytest."""
        gen = TestGenerator(_make_mock_llm([]))
        cases = _sample_test_cases()
        code = gen.generate_code_tests(cases, lang="python")
        assert 'pytest' in code
        assert 'def test_' in code
        assert "TC-001" in code

    def test_generate_code_tests_go(self):
        """generate_code_tests with lang='go' delegates to format_gotest."""
        gen = TestGenerator(_make_mock_llm([]))
        cases = _sample_test_cases()
        code = gen.generate_code_tests(cases, lang="go")
        assert 'testing' in code
        assert 'func Test_' in code
        assert "TC-001" in code

    def test_generate_code_tests_unsupported(self):
        """generate_code_tests raises ValueError for unknown lang."""
        gen = TestGenerator(_make_mock_llm([]))
        try:
            gen.generate_code_tests([], lang="rust")
            assert False, "Expected ValueError"
        except ValueError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Test: TestRunner — Execution and coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestRunnerDryRun:
    """Verify the runner's dry-run mode validates test case structure."""

    def test_dry_run_all_pass(self):
        """Valid test cases should all pass dry-run validation."""
        runner = TestRunner()
        cases = _sample_test_cases()
        report = runner.run_tests(cases, "/tmp", dry_run=True)
        assert report.total == 3
        assert report.passed == 3
        assert report.failed == 0

    def test_dry_run_detects_missing_given(self):
        """Missing GIVEN should fail dry-run validation."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-BAD", shall_ref="RS-001",
                     scenario="Bad", given="", when="A", then="B"),
        ]
        report = runner.run_tests(cases, "/tmp", dry_run=True)
        assert report.failed == 1
        assert "GIVEN empty" in report.results[0].message

    def test_dry_run_detects_missing_then(self):
        """Missing THEN should fail dry-run validation."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-BAD", shall_ref="RS-001",
                     scenario="Bad", given="A", when="B", then=""),
        ]
        report = runner.run_tests(cases, "/tmp", dry_run=True)
        assert report.failed == 1

    def test_dry_run_detects_invalid_priority(self):
        """Unknown priority should fail dry-run."""
        runner = TestRunner()
        cases = [
            TestCase(id="TC-BAD", shall_ref="RS-001",
                     scenario="Bad", given="A", when="B", then="C",
                     priority="P99"),
        ]
        report = runner.run_tests(cases, "/tmp", dry_run=True)
        assert report.failed == 1
        assert "P99" in report.results[0].message

    def test_dry_run_empty_case_list(self):
        """Empty test case list produces empty report."""
        runner = TestRunner()
        report = runner.run_tests([], "/tmp", dry_run=True)
        assert report.total == 0
        assert report.pass_rate == 0.0

    def test_report_pass_rate(self):
        """TestReport pass_rate is computed correctly."""
        r = TestReport(total=4, passed=3, failed=1)
        assert r.pass_rate == 75.0

    def test_report_empty(self):
        """TestReport with zero total has 0% pass rate."""
        r = TestReport()
        assert r.pass_rate == 0.0


class TestRunnerCoverage:
    """Verify the runner's SHALL-level coverage report."""

    def test_coverage_basic(self):
        """Runner computes coverage from spec + test cases."""
        runner = TestRunner()
        cases = _sample_test_cases()
        spec_path = _write_temp_spec()
        try:
            report = runner.run_tests(cases, "/tmp", dry_run=True, spec_path=spec_path)
            cov = runner.coverage_report()
            assert cov["total_shall"] > 0
            assert cov["covered_shall"] > 0
            assert cov["coverage_pct"] > 0.0
        finally:
            os.unlink(spec_path)

    def test_coverage_no_spec(self):
        """Without spec_path, coverage_report returns empty."""
        runner = TestRunner()
        runner.run_tests(_sample_test_cases(), "/tmp", dry_run=True)
        cov = runner.coverage_report()
        assert cov["total_shall"] == 0

    def test_print_report_no_report(self, capsys):
        """print_report with no prior run shows fallback message."""
        runner = TestRunner()
        runner.print_report()
        captured = capsys.readouterr()
        assert "No report available" in captured.out

    def test_print_report_with_data(self, capsys):
        """print_report formats output correctly."""
        runner = TestRunner()
        cases = _sample_test_cases()
        report = runner.run_tests(cases, "/tmp", dry_run=True)
        runner.print_report(report)
        captured = capsys.readouterr()
        assert "TestGen Execution Report" in captured.out
        assert "Pass rate: 100.0%" in captured.out


# ══════════════════════════════════════════════════════════════════════════════
# Test: Formatters
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatterPytest:
    """Verify pytest-compatible output generation."""

    def test_format_pytest_creates_functions(self):
        """Each test case becomes a pytest function."""
        cases = _sample_test_cases()
        code = format_pytest(cases)
        assert code.count("def test_") == 3
        assert "pytest" in code
        assert "TC-001" in code
        assert "TC-002" in code
        assert "TC-003" in code

    def test_format_pytest_includes_tags(self):
        """pytest.mark.tag decorators contain test case tags."""
        cases = _sample_test_cases()
        code = format_pytest(cases)
        assert "@pytest.mark.tag('smoke', 'unit')" in code
        assert "@pytest.mark.tag('boundary', 'regression')" in code

    def test_format_pytest_empty_list(self):
        """Empty test case list produces minimal valid file."""
        code = format_pytest([])
        assert "pytest" in code
        assert "def test_" not in code

    def test_format_pytest_includes_todo(self):
        """Generated functions contain TODO placeholder."""
        cases = _sample_test_cases()
        code = format_pytest(cases)
        assert "TODO: implement assertion" in code


class TestFormatterGotest:
    """Verify Go test-compatible output generation."""

    def test_format_gotest_creates_functions(self):
        """Each test case becomes a Go test function."""
        cases = _sample_test_cases()
        code = format_gotest(cases)
        assert code.count("func Test_") == 3
        assert "testing" in code
        assert "TC-001" in code

    def test_format_gotest_empty_list(self):
        """Empty test case list produces minimal valid Go file."""
        code = format_gotest([])
        assert "package" in code
        assert "func Test_" not in code

    def test_format_gotest_includes_todo(self):
        """Generated functions contain TODO placeholder."""
        cases = _sample_test_cases()
        code = format_gotest(cases)
        assert "TODO: implement" in code


class TestFormatterCeedling:
    """Verify Ceedling / Unity test output generation."""

    def test_format_ceedling_creates_functions(self):
        """Each test case becomes a C test function."""
        cases = _sample_test_cases()
        code = format_ceedling(cases)
        assert code.count("void test_") == 3
        assert "unity.h" in code
        assert "setUp" in code
        assert "tearDown" in code
        assert "TEST_ASSERT_TRUE_MESSAGE" in code

    def test_format_ceedling_empty_list(self):
        """Empty test case list produces minimal valid C file."""
        code = format_ceedling([])
        assert "unity.h" in code
        assert "setUp" in code
        assert "tearDown" in code
        assert "void test_" not in code

    def test_format_ceedling_includes_todo(self):
        """Generated C functions contain TODO placeholder."""
        cases = _sample_test_cases()
        code = format_ceedling(cases)
        assert "TODO: implement assertion" in code


# ══════════════════════════════════════════════════════════════════════════════
# Test: Data classes
# ══════════════════════════════════════════════════════════════════════════════


class TestTestCaseDataclass:
    """Verify TestCase dataclass defaults and serialisation."""

    def test_default_priority(self):
        """Default priority is P1."""
        tc = TestCase(id="T1", shall_ref="R1", scenario="S", given="G", when="W", then="T")
        assert tc.priority == "P1"

    def test_default_tags(self):
        """Default tags is ['unit']."""
        tc = TestCase(id="T1", shall_ref="R1", scenario="S", given="G", when="W", then="T")
        assert tc.tags == ["unit"]

    def test_to_dict(self):
        """to_dict produces a plain dict."""
        tc = TestCase(id="TC-001", shall_ref="RS-001", scenario="S",
                      given="A", when="B", then="C", priority="P0",
                      tags=["smoke", "unit"])
        d = tc.to_dict()
        assert d["id"] == "TC-001"
        assert d["priority"] == "P0"
        assert d["tags"] == ["smoke", "unit"]
        assert d["scenario"] == "S"

    def test_default_tags_are_fresh(self):
        """Each TestCase gets its own tag list, not a shared mutable default."""
        tc1 = TestCase(id="T1", shall_ref="R1", scenario="S", given="G", when="W", then="T")
        tc2 = TestCase(id="T2", shall_ref="R1", scenario="S", given="G", when="W", then="T")
        tc1.tags.append("custom")
        assert "custom" not in tc2.tags


class TestTestResultDataclass:
    """Verify TestResult and TestReport dataclasses."""

    def test_result_defaults(self):
        """TestResult has sensible defaults."""
        r = TestResult(test_id="TC-001", status="PASS")
        assert r.duration_ms == 0.0
        assert r.message == ""

    def test_report_defaults(self):
        """TestReport has zero-valued defaults."""
        r = TestReport()
        assert r.total == 0
        assert r.passed == 0
        assert r.duration_ms == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Test: Internal helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractJson:
    """Verify the JSON extraction helpers in generator.py."""

    def test_extract_json_array_from_text(self):
        """Extracts first JSON array from surrounding text."""
        text = "Here is the result: [{\"id\":\"TC-001\"}], and more text."
        result = TestGenerator._extract_json_array(text)
        assert result is not None
        assert result[0]["id"] == "TC-001"

    def test_extract_json_array_no_bracket(self):
        """Returns None when no '[' found."""
        result = TestGenerator._extract_json_array("no brackets here")
        assert result is None

    def test_extract_json_object_from_text(self):
        """Extracts first JSON object from surrounding text."""
        text = "Result: {\"key\":\"value\"} and more text."
        result = TestGenerator._extract_json_object(text)
        assert result is not None
        assert result["key"] == "value"

    def test_extract_json_object_no_brace(self):
        """Returns None when no '{' found."""
        result = TestGenerator._extract_json_object("just text")
        assert result is None


class TestSanitize:
    """Verify the _sanitize helper in formatter.py."""

    def test_sanitize_basic(self):
        """Basic string sanitisation."""
        from testgen.formatter import _sanitize
        result = _sanitize("BLE starts advertising")
        assert result == "ble_starts_advertising"

    def test_sanitize_special_chars(self):
        """Special characters are replaced or removed."""
        from testgen.formatter import _sanitize
        result = _sanitize("Temp ±0.5°C / sensor")
        assert "per_" in result or "_" in result

    def test_sanitize_leading_digits(self):
        """Leading digits are stripped."""
        from testgen.formatter import _sanitize
        result = _sanitize("123 test case")
        assert result.startswith("test_")

    def test_sanitize_empty(self):
        """Empty string returns fallback name."""
        from testgen.formatter import _sanitize
        result = _sanitize("")
        assert result == "test_unnamed"


class TestCoverageReport:
    """Verify CoverageReport data class and conversion."""

    def test_coverage_report_to_dict(self):
        """to_dict produces expected keys."""
        from testgen.runner import CoverageEntry
        entries = [
            CoverageEntry(req_id="RS-001", shall_text="shall advertise",
                          covered_by=["TC-001"], uncovered=False),
        ]
        r = CoverageReport(total_shall=1, covered_shall=1, entries=entries)
        d = r.to_dict()
        assert d["total_shall"] == 1
        assert d["covered_shall"] == 1
        assert d["entries"][0]["req_id"] == "RS-001"
