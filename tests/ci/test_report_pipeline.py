#!/usr/bin/env python3
"""
Pipeline Unit Tests: misra_report.py & review_selftest.py

Tests:
  1. misra_report.parse_cppcheck_output() — unique_files parsing, year normalization
  2. misra_report.compute_summary_stats() — KLOC, severity counts
  3. review_selftest._parse_junit_xml() — JUnit XML parsing
  4. review_selftest._auto_map_shall_coverage() — SHALL auto-mapping
  5. Edge cases: empty input, malformed XML, large output
  6. Golden-file snapshot tests

Usage:
    pytest tests/ci/test_report_pipeline.py -v
    pytest tests/ci/test_report_pipeline.py -v --cov=ci/misra_report.py
"""

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

# ---------------------------------------------------------------------------
# Import the modules under test
# ---------------------------------------------------------------------------
import sys
_SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "yuleosh" / "ci"
sys.path.insert(0, str(_SRC_DIR))

from misra_report import (
    parse_cppcheck_output,
    compute_summary_stats,
    group_by_rule,
    enrich_with_definitions,
    generate_json_report,
    _PATTERN_CPPCHECK,
    _PATTERN_MISRA_RULE,
    _PATTERN_TEXT_RULE,
)

# Import review_selftest functions
_REVIEW_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "yuleosh" / "pipeline" / "step_handlers"
)
sys.path.insert(0, str(_REVIEW_DIR.parent.parent.parent.parent))  # project root

from yuleosh.pipeline.step_handlers.review_selftest import (
    _parse_junit_xml,
    _auto_map_shall_coverage,
    _extract_shall_statements,
)
from yuleosh.ci.review_helpers import _SHALL_ID_PATTERN

# ---------------------------------------------------------------------------
# Golden test data directory
# ---------------------------------------------------------------------------
_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ===========================================================================
# 1. misra_report — parse_cppcheck_output & unique_files
# ===========================================================================

CPPCHECK_REAL_OUTPUT = """\
/src/main.c:42:5: style: misra violation (use --rule-texts=<file> to get proper output) [misra-c2012-17.7]
    printf("hello world");
    ^
/src/main.c:95:9: style: misra violation (use --rule-texts=<file> to get proper output) [misra-c2012-15.6]
        if (flag) { doSomething(); }
        ^
/src/utils.c:10:0: style: misra violation (use --rule-texts=<file> to get proper output) [misra-c2012-12.1]
    if (p == NULL) { return; }
              ^
/src/utils.c:12:0: information: Include file: "config.h" not found. [missingInclude]
#include "config.h"
^
nofile:0:0: information: Active checkers: 309/1056 [checkersReport]
"""


class TestMisraReportParser:
    """A1/A3: Verify misra_report.py parsing with real cppcheck output."""

    def test_parse_basic(self):
        """Parse real cppcheck --addon=misra output and verify violations."""
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        assert len(violations) == 4, f"Expected 4 violations, got {len(violations)}"

    def test_unique_files_no_newlines(self):
        """unique_files must not contain newline-corrupted paths (A3 fix)."""
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        files = set(v.get("file", "") for v in violations)
        for f in files:
            assert "\n" not in f, f"File path contains newline: {repr(f)}"

    def test_unique_files_correct_count(self):
        """Verify unique_files count matches real source files (not context lines)."""
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        summary = compute_summary_stats(violations, group_by_rule(violations))
        # Expected files: /src/main.c, /src/utils.c (nofile filtered by _extract_file_path)
        assert len(summary["unique_files"]) == 2, (
            f"Expected 2 unique files, got {summary['unique_files']}"
        )
        assert any("main.c" in f for f in summary["unique_files"])
        assert any("utils.c" in f for f in summary["unique_files"])

    def test_rule_extraction_c2012(self):
        """MISRA rule IDs (c2012 format) should be extracted correctly."""
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        misra_violations = [v for v in violations if v.get("rule_id")]
        assert len(misra_violations) == 3, f"Expected 3 MISRA violations, got {len(misra_violations)}"

        rule_ids = [v["rule_id"] for v in misra_violations]
        assert "misra-c2023-17.7" in rule_ids
        assert "misra-c2023-15.6" in rule_ids
        assert "misra-c2023-12.1" in rule_ids

    def test_parse_empty_input(self):
        """Empty input should return empty list."""
        assert parse_cppcheck_output("") == []
        assert parse_cppcheck_output("\n\n\n") == []

    def test_parse_no_misra_lines(self):
        """Input with no matching lines should return empty list."""
        text = "some random text\nwithout any:pattern:here\n"
        assert parse_cppcheck_output(text) == []

    def test_parse_code_context_only(self):
        """Context lines alone (no violation headers) should not match."""
        context = "    if (x == 0) {\n        ^\n"
        violations = parse_cppcheck_output(context)
        assert len(violations) == 0

    def test_parse_malformed_colon(self):
        """Lines with unusual colon placement should not corrupt parsing."""
        text = "/path/file.c:10:5: style: some:message:with:colons [misra-c2012-10.1]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        v = violations[0]
        assert v["file"] == "/path/file.c"
        assert v["line"] == 10
        assert v["col"] == 5
        assert "some:message:with:colons" in v["message"]


class TestMisraReportSummary:
    """Verify summary statistics generation."""

    def test_severity_counts(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)
        assert summary["total_violations"] == 4
        assert summary["severity_counts"]["style"] == 3
        assert summary["severity_counts"]["information"] == 1

    def test_rules_violated(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)
        assert summary["total_rules_violated"] == len(groups)

    def test_per_file_counts(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)
        # /src/main.c has 2 violations
        main_c_count = summary["per_file_counts"].get("/src/main.c", 0)
        assert main_c_count == 2, f"Expected 2 for main.c, got {main_c_count}"
        # /src/utils.c has 2 violations (missingInclude has valid file path)
        utils_c_count = summary["per_file_counts"].get("/src/utils.c", 0)
        assert utils_c_count == 2, f"Expected 2 for utils.c, got {utils_c_count}"


# ===========================================================================
# 2. misra_report — _PATTERN_CPPCHECK regex edge cases
# ===========================================================================

class TestPatternCppcheck:
    """Verify the regex pattern handles edge cases correctly."""

    def test_pattern_matches_standard_line(self):
        m = _PATTERN_CPPCHECK.match("/path/file.c:42:5: style: msg [rule]")
        assert m is not None
        assert m.group("file") == "/path/file.c"
        assert m.group("line") == "42"
        assert m.group("col") == "5"
        assert m.group("severity") == "style"
        assert m.group("message") == "msg [rule]"

    def test_pattern_rejects_lines_with_newline_in_file(self):
        """The fix: [^\n:]+ must reject multi-line file capture."""
        text = "    code context line\n      ^\n/path/file.c:42:5: style: msg [rule]\n"
        matches = list(_PATTERN_CPPCHECK.finditer(text))
        # Only the line /path/file.c:42:5: should match
        assert len(matches) == 1
        assert matches[0].group("file") == "/path/file.c"

    def test_pattern_all_severities(self):
        for sev in ["error", "warning", "style", "performance", "portability", "information"]:
            m = _PATTERN_CPPCHECK.match(f"/f.c:1:1: {sev}: msg")
            assert m is not None, f"Severity '{sev}' not matched"
            assert m.group("severity") == sev

    def test_pattern_line0(self):
        """Line/col 0 should parse correctly."""
        m = _PATTERN_CPPCHECK.match("nofile:0:0: information: msg [checkersReport]")
        assert m is not None
        assert m.group("line") == "0"
        assert m.group("col") == "0"


class TestYearNormalization:
    """Verify year handling in rule ID generation."""

    def test_misra_c2012_format(self):
        """c2012 format should produce misra-c2012-XX.XX rule IDs."""
        m = _PATTERN_MISRA_RULE.search("misra violation [misra-c2012-17.7]")
        assert m is not None
        assert m.group("year") == "2012"
        assert m.group("rule") == "17.7"

    def test_misra_c2023_format(self):
        """c2023 format should work identically."""
        m = _PATTERN_MISRA_RULE.search("misra violation [misra-c2023-10.1]")
        assert m is not None
        assert m.group("year") == "2023"

    def test_text_rule_fallback(self):
        """Fallback pattern for 'MISRA rule XX.XX' without year."""
        m = _PATTERN_TEXT_RULE.search("(information) MISRA rule 17.7")
        assert m is not None
        assert m.group("rule") == "17.7"


# ===========================================================================
# 3. review_selftest — JUnit XML parsing (A2)
# ===========================================================================

SAMPLE_JUNIT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="1" skipped="1" tests="5" time="1.234">
    <testcase classname="test_mod" name="test_passes" time="0.100" />
    <testcase classname="test_mod" name="test_fails" time="0.200">
      <failure message="AssertionError: assert 1 == 2">
        def test_fails():
    &gt;       assert 1 == 2
    E       assert 1 == 2
      </failure>
    </testcase>
    <testcase classname="test_mod" name="test_skipped" time="0.000">
      <skipped message="unimportant" />
    </testcase>
    <testcase classname="test_mod" name="test_errors" time="0.300">
      <error message="RuntimeError: boom!">
        raise RuntimeError("boom!")
      </error>
    </testcase>
    <testcase classname="test_mod" name="test_shall_10_1" time="0.150" />
  </testsuite>
</testsuites>
"""

SAMPLE_JUNIT_NO_FAILURES = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="0.500">
    <testcase classname="test_mod" name="test_alpha" time="0.100" />
    <testcase classname="test_mod" name="test_beta" time="0.200" />
  </testsuite>
</testsuites>
"""


class TestJunitXmlParsing:
    """Verify JUnit XML parsing in review_selftest."""

    @pytest.fixture
    def junit_path(self, tmp_path):
        p = tmp_path / "junit.xml"
        p.write_text(SAMPLE_JUNIT_XML)
        return p

    @pytest.fixture
    def junit_path_clean(self, tmp_path):
        p = tmp_path / "junit-clean.xml"
        p.write_text(SAMPLE_JUNIT_NO_FAILURES)
        return p

    def test_parse_count(self, junit_path):
        results = _parse_junit_xml(junit_path)
        assert len(results) == 5, f"Expected 5 test cases, got {len(results)}"

    def test_parse_status_passed(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        assert by_name["test_mod::test_passes"]["status"] == "passed"

    def test_parse_status_failed(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        assert by_name["test_mod::test_fails"]["status"] == "failed"
        assert "AssertionError" in by_name["test_mod::test_fails"].get("message", "")

    def test_parse_status_skipped(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        assert by_name["test_mod::test_skipped"]["status"] == "skipped"

    def test_parse_status_error(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        assert by_name["test_mod::test_errors"]["status"] == "error"

    def test_parse_duration(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        assert by_name["test_mod::test_passes"]["duration"] == 0.1

    def test_parse_empty_xml(self, tmp_path):
        p = tmp_path / "empty.xml"
        p.write_text("<testsuites></testsuites>")
        assert _parse_junit_xml(p) == []

    def test_parse_malformed_xml(self, tmp_path):
        p = tmp_path / "bad.xml"
        p.write_text("not xml at all")
        assert _parse_junit_xml(p) == []

    def test_structure_failure_info(self, junit_path):
        results = _parse_junit_xml(junit_path)
        by_name = {r["name"]: r for r in results}
        fail = by_name["test_mod::test_fails"]
        assert "failure" in fail
        assert fail["failure"]["type"] == "AssertionError"
        assert "assert 1 == 2" in fail["failure"]["message"]

    def test_parse_testsuite_root(self, tmp_path):
        """Handle <testsuite> at root without <testsuites> wrapper."""
        xml = """\
<?xml version="1.0"?>
<testsuite name="direct" errors="0" failures="0" skipped="0" tests="1" time="0.1">
  <testcase classname="mod" name="test_direct" time="0.05" />
</testsuite>"""
        p = tmp_path / "direct.xml"
        p.write_text(xml)
        results = _parse_junit_xml(p)
        assert len(results) == 1
        assert results[0]["name"] == "mod::test_direct"

    def test_clean_run_all_passed(self, junit_path_clean):
        results = _parse_junit_xml(junit_path_clean)
        assert all(r["status"] == "passed" for r in results)


# ===========================================================================
# 4. review_selftest — SHALL coverage auto-mapping
# ===========================================================================

SHALL_STATEMENTS = [
    {"statement": "SHALL-10.1 The system shall do X.", "section": "3.1", "line": 10},
    {"statement": "SHALL-10.2 The system shall do Y.", "section": "3.1", "line": 12},
    {"statement": "SHALL-17.7 No printf allowed.", "section": "5.2", "line": 20},
    {"statement": "MAY-1.0 The system may do Z.", "section": "6.0", "line": 30},
]

TEST_CASE_RESULTS = [
    {"name": "test_mod::test_shall_10_1", "status": "passed", "duration": 0.1},
    {"name": "test_mod::test_shall_17_7", "status": "passed", "duration": 0.2},
]


class TestShallCoverageMapping:
    """Verify SHALL auto-mapping from test function names."""

    def test_basic_mapping(self):
        covered_indices, shall_map, assertion_map = _auto_map_shall_coverage(
            SHALL_STATEMENTS, TEST_CASE_RESULTS
        )
        assert len(covered_indices) == 2  # 10.1 and 17.7
        assert 0 in covered_indices  # SHALL-10.1
        assert 2 in covered_indices  # SHALL-17.7
        assert 1 not in covered_indices  # SHALL-10.2 not tested

    def test_no_shall_statements(self):
        covered, s_map, a_map = _auto_map_shall_coverage([], TEST_CASE_RESULTS)
        assert len(covered) == 0
        assert s_map == {}

    def test_no_test_results(self):
        covered, s_map, a_map = _auto_map_shall_coverage(SHALL_STATEMENTS, [])
        assert len(covered) == 0

    def test_empty_inputs(self):
        covered, s_map, a_map = _auto_map_shall_coverage([], [])
        assert covered == set()

    def test_shall_id_pattern(self):
        """Verify regex matches various SHALL ID formats in test names."""
        assert _SHALL_ID_PATTERN.search("test_shall_10_1")
        assert _SHALL_ID_PATTERN.search("test_SHALL_10_1")
        assert _SHALL_ID_PATTERN.search("test_requirement_10_1")
        assert _SHALL_ID_PATTERN.search("test_SWE_4_BP1_shall_10_1")
        assert _SHALL_ID_PATTERN.search("test_req_10_1")
        assert not _SHALL_ID_PATTERN.search("test_just_a_name")


class TestExtractShallStatements:
    """Verify spec SHALL extraction."""

    def test_extract_basic(self):
        spec = """\
# Heading 1

The system SHALL do X.

## Section 2

The system SHALL do Y.
It MAY also do Z.
"""
        shalls = _extract_shall_statements(spec)
        assert len(shalls) == 3, f"Expected 3 statements, got {len(shalls)}"

    def test_no_shalls(self):
        spec = "This is just documentation with no requirements."
        assert _extract_shall_statements(spec) == []

    def test_empty_spec(self):
        assert _extract_shall_statements("") == []


# ===========================================================================
# 5. Full pipeline integration
# ===========================================================================

class TestFullPipelineIntegration:
    """End-to-end: cppcheck raw output → parsed → summary → report."""

    def test_full_pipeline_roundtrip(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)
        report = json.loads(generate_json_report(violations, groups, summary))

        assert report["summary"]["total_violations"] == 4
        assert report["summary"]["total_rules_violated"] == len(groups)
        # Verify no newline in any unique file
        for f in report["summary"]["unique_files"]:
            assert "\n" not in f, f"Corrupted file: {repr(f[:60])}..."
        # Verify each violation has correct file
        for v in report["violations_raw"]:
            assert "\n" not in v["file"], f"Violation file corrupted: {v}"

    @pytest.mark.slow
    def test_with_real_misra_output(self):
        """If the saved raw misra output exists, parse it end-to-end."""
        raw_path = _PROJECT_ROOT / ".yuleosh" / "reports" / "misra-raw-output.txt"
        if not raw_path.exists():
            pytest.skip("Real misra-raw-output.txt not found")
        text = raw_path.read_text()
        violations = parse_cppcheck_output(text)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)

        # Verify no newline in any unique file entry (A3 fix applied)
        for f in summary["unique_files"]:
            assert "\n" not in f, f"Corrupted file: {repr(f[:60])}..."
        # Must have 2+ real source files
        real_files = [f for f in summary["unique_files"] if f != "nofile"]
        assert len(real_files) > 0, "Expected at least one real source file"
        assert summary["total_violations"] > 0


# ===========================================================================
# 6. Edge case tests
# ===========================================================================

class TestEdgeCases:
    """Edge cases: large output, format variations, etc."""

    def test_large_output(self):
        """Generate 500 violations to test performance and memory."""
        lines = []
        for i in range(500):
            lines.append(f"/src/mod{i//10}.c:{i}:{i%80+1}: style: violation {i} [misra-c2012-10.1]")
            lines.append(f"    code line {i}")
            lines.append(f"    ^")
        text = "\n".join(lines)
        violations = parse_cppcheck_output(text)
        assert len(violations) == 500
        unique = set(v["file"] for v in violations)
        assert len(unique) == 50  # 500/10 files

    def test_mixed_severity(self):
        text = """\
/f.c:1:1: error: critical error [misra-c2012-1.1]
/f.c:2:2: warning: something [misra-c2012-2.2]
/f.c:3:3: style: formatting [misra-c2012-3.3]
/f.c:4:4: performance: slow [misra-c2012-4.4]
/f.c:5:5: portability: arch [misra-c2012-5.5]
/f.c:6:6: information: note [misra-c2012-6.6]
"""
        violations = parse_cppcheck_output(text)
        assert len(violations) == 6
        sevs = [v["severity"] for v in violations]
        assert "error" in sevs
        assert "portability" in sevs
        assert "information" in sevs

    def test_no_misra_rule_uses_fallback(self):
        """cppcheck non-misra messages (e.g. unusedFunction) should have rule_id=None."""
        text = "/f.c:1:1: style: The function 'foo' is never used. [unusedFunction]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        assert violations[0]["rule_id"] is None

    def test_year_2023_normalization(self):
        """Messages with misra-c2023 should parse correctly."""
        text = "/f.c:1:1: style: violation [misra-c2023-10.1]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "misra-c2023-10.1"


# ===========================================================================
# 7. misra_report JSON consistency
# ===========================================================================

class TestJsonOutputConsistency:
    """JSON output structure must be consistent and serializable."""

    def test_json_serializable(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        summary = compute_summary_stats(violations, groups)
        report_str = generate_json_report(violations, groups, summary)
        data = json.loads(report_str)
        assert "generated_at" in data
        assert "summary" in data
        assert "violations_raw" in data
        assert "groups" in data

    def test_no_sets_in_json(self):
        """JSON must not contain Python sets (not serializable)."""
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        groups = group_by_rule(violations)
        for g in groups.values():
            for v in g.values():
                assert not isinstance(v, set), f"Set found in group: {v}"
    def test_violation_raw_has_required_keys(self):
        violations = parse_cppcheck_output(CPPCHECK_REAL_OUTPUT)
        for v in violations:
            for key in ("file", "line", "col", "severity", "message", "rule_id"):
                assert key in v, f"Missing key {key} in violation: {v}"
            assert isinstance(v["line"], int)
            assert isinstance(v["col"], int)


# ===========================================================================
# 8. review_selftest edge cases
# ===========================================================================

class TestReviewSelftestEdgeCases:

    def test_empty_junit_no_crash(self, tmp_path):
        p = tmp_path / "empty.xml"
        p.write_text("")
        assert _parse_junit_xml(p) == []

    def test_junit_without_testsuite(self, tmp_path):
        """XML with <testsuites> wrapper but empty."""
        p = tmp_path / "empty-wrapper.xml"
        p.write_text('<?xml version="1.0"?><testsuites />')
        assert _parse_junit_xml(p) == []
