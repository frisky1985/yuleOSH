#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Targeted tests for uncovered paths in misra_report/core modules.

Covers gaps identified by coverage analysis:
- analysis.py: enrich_with_definitions non-default rule_defs,
  compute_summary_stats with all branches, category breakdown fallback
- config.py: normalize_misra_year, load_ci_config, excluded_rules string,
  rule_defs custom path, get_ci_environ, count_source_lines exceptions
- parser.py: MISRA rule extraction from message, legacy format columns
- reporting.py: delta formatting, full md report generation,
  save_report legacy mode, save_report new dict mode, save_merged_report,
  print_summary, serialize_group dict
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ===========================================================================
# core/analysis - fill gaps
# ===========================================================================


class TestAnalysisGaps:
    """Target remaining uncovered paths in analysis.py."""

    def test_enrich_with_rule_defs_from_param(self):
        """enrich_with_definitions with explicit rule_defs."""
        from yuleosh.ci.misra_report.core.analysis import enrich_with_definitions
        violations = [{"rule_id": "Rule 10.1"}]
        rule_defs = {
            "rules": {
                "Rule 10.1": {
                    "category": "required",
                    "description": "Test description",
                }
            }
        }
        enriched = enrich_with_definitions(violations, rule_defs=rule_defs)
        assert len(enriched) == 1
        assert enriched[0]["category"] == "required"
        assert enriched[0]["description"] == "Test description"

    def test_enrich_with_definitions_none_rules(self):
        """enrich_with_definitions with empty rule_defs."""
        from yuleosh.ci.misra_report.core.analysis import enrich_with_definitions
        violations = [{"rule_id": "Rule 10.1"}]
        enriched = enrich_with_definitions(violations, rule_defs={})
        assert len(enriched) == 1
        # Should default via _classify_rule_type
        assert "category" in enriched[0]

    def test_compute_summary_stats_all_severities(self):
        """compute_summary_stats with multiple severity and rule_type values."""
        from yuleosh.ci.misra_report.core.analysis import compute_summary_stats, group_by_rule
        violations = [
            {"rule_id": "Rule 10.1", "severity": "high", "rule_type": "required"},
            {"rule_id": "Rule 10.3", "severity": "medium", "rule_type": "advisory"},
            {"rule_id": "Dir 4.1", "severity": "low", "rule_type": "directive"},
            {"rule_id": "unknown", "severity": "style", "rule_type": "unknown"},
        ]
        groups = group_by_rule(violations)
        stats = compute_summary_stats(violations, groups)
        assert stats["total_violations"] == 4
        assert stats["unique_rules"] == 4
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["medium"] == 1
        assert stats["by_severity"]["low"] == 1
        assert stats["by_rule_type"]["required"] == 1
        assert stats["by_rule_type"]["advisory"] == 1
        assert stats["by_rule_type"]["directive"] == 1

    def test_compute_summary_stats_with_files(self, tmp_path):
        """compute_summary_stats using real files for source line counting."""
        from yuleosh.ci.misra_report.core.analysis import compute_summary_stats, group_by_rule
        f = tmp_path / "main.c"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        violations = [
            {"rule_id": "Rule 10.1", "severity": "high", "file": str(f)},
            {"rule_id": "Rule 10.1", "severity": "high", "file": str(f)},
        ]
        groups = group_by_rule(violations)
        stats = compute_summary_stats(violations, groups)
        assert stats["total_violations"] == 2
        assert stats["total_source_lines"] == 3
        assert stats["density_per_kloc"] > 0

    def test_classify_rule_type_directive(self):
        """_classify_rule_type with directive and edge cases."""
        from yuleosh.ci.misra_report.core.analysis import _classify_rule_type
        assert _classify_rule_type("Dir 4.1") == "directive"
        assert _classify_rule_type("dir 1.1") == "directive"
        assert _classify_rule_type("Rule 10.2") == "required"
        assert _classify_rule_type("Rule 99.4") == "advisory"

    def test_load_prev_report_bad_json(self, tmp_path):
        """_load_prev_report with corrupted JSON file, should handle gracefully."""
        from yuleosh.ci.misra_report.core.analysis import _load_prev_report
        f = tmp_path / "misra-report-bad.json"
        f.write_text("not valid json", encoding="utf-8")
        result = _load_prev_report(tmp_path)
        assert result is None  # Should gracefully return None

    def test_compute_prev_build_diff_full(self):
        """_compute_prev_build_diff with all fields."""
        from yuleosh.ci.misra_report.core.analysis import _compute_prev_build_diff
        current = {"total_violations": 10}
        prev = {"total_violations": 7, "build_id": "build-123", "date": "2026-06-01"}
        diff = _compute_prev_build_diff(current, prev)
        assert diff["delta_total"] == 3
        assert diff["previous_total"] == 7
        assert diff["previous_build_id"] == "build-123"
        assert diff["previous_date"] == "2026-06-01"

    def test_compute_category_breakdown_fallback(self):
        """_compute_category_breakdown falls back to severity when category missing."""
        from yuleosh.ci.misra_report.core.analysis import _compute_category_breakdown
        violations = [
            {"severity": "error"},
            {"severity": "warning"},
            {"category": "required"},
        ]
        breakdown = _compute_category_breakdown(violations)
        assert breakdown["error"] == 1
        assert breakdown["warning"] == 1
        assert breakdown["required"] == 1


# ===========================================================================
# core/config - fill gaps
# ===========================================================================


class TestConfigGaps:
    """Target remaining uncovered paths in config.py."""

    def test_normalize_misra_year(self):
        """_normalize_misra_year with various formats."""
        from yuleosh.ci.misra_report.core.config import _normalize_misra_year
        assert _normalize_misra_year("MISRA Rule 10.1") == "10.1"
        assert _normalize_misra_year("Rule 10.3") == "10.3"
        assert _normalize_misra_year("10.1") == "10.1"
        assert _normalize_misra_year("") == ""

    def test_extract_excluded_rules_string(self):
        """_extract_excluded_rules with string value instead of list."""
        from yuleosh.ci.misra_report.core.config import _extract_excluded_rules
        config = {"misra": {"exclude_rules": "Rule 10.1"}}
        result = _extract_excluded_rules(config)
        assert isinstance(result, list)
        assert "Rule 10.1" in result

    def test_extract_excluded_files_string(self):
        """_extract_excluded_files with string value."""
        from yuleosh.ci.misra_report.core.config import _extract_excluded_files
        config = {"misra": {"exclude_files": "*.test.c"}}
        result = _extract_excluded_files(config)
        assert isinstance(result, list)
        assert "*.test.c" in result

    def test_load_rule_definitions_custom_path(self, tmp_path):
        """load_rule_definitions with custom path."""
        from yuleosh.ci.misra_report.core.config import load_rule_definitions
        rules_file = tmp_path / "custom-rules.yaml"
        rules_file.write_text("""meta:\n  version: \"1.0\"\nrules:\n  Rule 10.1:\n    category: required\n""", encoding="utf-8")
        rules = load_rule_definitions(rules_path=rules_file)
        assert "meta" in rules
        assert rules["meta"]["version"] == "1.0"

    def test_load_rule_definitions_nonexistent_path(self):
        """load_rule_definitions with nonexistent path returns empty dict."""
        from yuleosh.ci.misra_report.core.config import load_rule_definitions
        rules = load_rule_definitions(rules_path=Path("/nonexistent/path/to/rules.yaml"))
        assert rules == {}

    def test_get_ruleset_version_empty(self):
        """get_ruleset_version with no meta returns 'unknown'."""
        from yuleosh.ci.misra_report.core.config import get_ruleset_version
        version = get_ruleset_version(rule_defs={"rules": {}})
        assert version == "unknown"

    def test_get_ci_environ_with_vals(self):
        """get_ci_environ with environment variables set."""
        from yuleosh.ci.misra_report.core.config import get_ci_environ
        old_vars = {}
        for k in ("BUILD_ID", "GIT_COMMIT", "BRANCH_NAME", "JOB_NAME", "WORKSPACE"):
            old_vars[k] = os.environ.get(k)
            os.environ[k] = f"test-{k}"
        try:
            env = get_ci_environ()
            assert env["build_id"] == "test-BUILD_ID"
            assert env["commit_sha"] == "test-GIT_COMMIT"
            assert env["branch"] == "test-BRANCH_NAME"
            assert env["job_name"] == "test-JOB_NAME"
            assert env["workspace"] == "test-WORKSPACE"
        finally:
            for k, v in old_vars.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def test_count_source_lines_exception(self):
        """_count_source_lines handles exception gracefully."""
        from yuleosh.ci.misra_report.core.config import _count_source_lines
        # Path with invalid encoding characters
        result = _count_source_lines(["/dev/null/invalid\x00path.c"])
        assert result == 0


# ===========================================================================
# core/parser - fill gaps
# ===========================================================================


class TestParserGaps:
    """Target remaining uncovered paths in parser.py."""

    def test_parse_misra_rule_from_text(self):
        """parse_cppcheck_output extracts MISRA rule IDs from text markers."""
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        # MISRA text rule format
        text = "[main.c:10:5] (error) MISRA Rule 10.1 violation [arrayIndexOutOfBounds]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        # The MISRA rule ID should be extracted

    def test_parse_misra_text_rule_pattern(self):
        """Parse cppcheck output with MISRA rule in message text."""
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        text = "[file.c:42:3] (style) MISRA-C:2012 Rule 15.6 violation detected\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        assert violations[0]["severity"] == "style"

    def test_parse_legacy_format(self):
        """Parse legacy cppcheck format with column."""
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        text = "file.c:10:1: error: Array access [arrayIndexOutOfBounds]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        assert violations[0]["severity"] == "error"

    def test_extract_file_path_nonexistent(self):
        """_extract_file_path returns raw path for non-existent files."""
        from yuleosh.ci.misra_report.core.parser import _extract_file_path
        result = _extract_file_path("/nonexistent/file.c")
        assert result == "/nonexistent/file.c"

    def test_extract_file_path_exception(self):
        """_extract_file_path handles exception gracefully."""
        from yuleosh.ci.misra_report.core.parser import _extract_file_path
        result = _extract_file_path(None)
        assert result is None


# ===========================================================================
# core/reporting - fill gaps
# ===========================================================================


class TestReportingGaps:
    """Target remaining uncovered paths in reporting.py."""

    def test_format_delta_positive(self):
        """_format_delta with positive, zero, and negative values."""
        from yuleosh.ci.misra_report.core.reporting import _format_delta
        assert _format_delta(5) == "+5"
        assert _format_delta(0) == "0"
        assert _format_delta(-3) == "-3"

    def test_serialize_group_dict(self):
        """_serialize_group with dict input passes through."""
        from yuleosh.ci.misra_report.core.reporting import _serialize_group
        group_dict = {"count": 3, "violations": [], "total": 3}
        result = _serialize_group(group_dict)
        assert result["count"] == 3

    def test_generate_markdown_report_full(self):
        """generate_markdown_report with all sections populated."""
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {
            "total_violations": 10,
            "unique_rules": 5,
            "affected_files": 3,
            "density_per_kloc": 2.5,
            "generated_at": "2026-07-05T10:00:00",
            "tool_version": "cppcheck 2.10",
            "ruleset_version": "MISRA C:2012",
            "by_severity": {"error": 4, "warning": 3, "style": 2, "performance": 1},
            "by_rule_type": {"required": 6, "advisory": 3, "directive": 1},
            "category_breakdown": {"Required": 6, "Advisory": 3, "Directive": 1},
            "diff": {
                "delta_total": -2,
                "previous_total": 12,
                "previous_build_id": "build-122",
                "previous_date": "2026-07-04",
            },
            "groups": {
                "Rule 10.1": {
                    "count": 4,
                    "violations": [
                        {"file": "main.c", "line": 42, "message": "Implicit conversion"},
                        {"file": "main.c", "line": 55, "message": "Another issue"},
                    ],
                },
                "Rule 15.6": {
                    "count": 3,
                    "violations": [],
                },
                "Rule 20.9": {
                    "count": 2,
                    "violations": [
                        {"file": "uart.c", "line": 88, "message": "Pointer issue"},
                    ],
                },
            },
        }
        md = generate_markdown_report(report)
        assert "MISRA Compliance Report" in md
        assert "Trend vs Previous" in md
        assert "Rule 10.1" in md
        assert "main.c:42" in md
        assert "4 violations" in md or "4)" in md
        assert len(md) > 300

    def test_generate_markdown_report_no_diff(self):
        """generate_markdown_report without diff section."""
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {"total_violations": 5, "unique_rules": 3, "affected_files": 2,
                  "density_per_kloc": 1.0, "generated_at": "now"}
        md = generate_markdown_report(report)
        assert "Trend vs Previous" not in md

    def test_save_report_new_style(self, tmp_path):
        """save_report with new-style dict+output_dir calling convention."""
        from yuleosh.ci.misra_report.core.reporting import save_report
        report = {"total_violations": 5, "build_id": "build-1",
                  "generated_at": "now", "groups": {}}
        saved = save_report(report, str(tmp_path), "custom-report")
        assert saved is not None
        if isinstance(saved, list):
            assert len(saved) >= 1
            assert all(Path(p).exists() for p in saved)

    def test_save_report_legacy(self, tmp_path):
        """save_report with legacy violations+groups calling convention."""
        from yuleosh.ci.misra_report.core.reporting import save_report
        violations = [
            {"rule_id": "Rule 10.1", "severity": "high", "file": "main.c", "line": 42, "message": "Test"},
        ]
        groups = {"Rule 10.1": violations}
        result = save_report(violations, groups, {}, {}, str(tmp_path))
        assert isinstance(result, tuple)
        assert len(result) == 4
        for p in result:
            assert Path(p).exists(), f"Path {p} does not exist"

    def test_save_merged_report(self, tmp_path):
        """save_merged_report with both misra and selftest.review data."""
        from yuleosh.ci.misra_report.core.reporting import save_merged_report
        misra_repo = {"total_violations": 5, "build_id": "b1"}
        selftest = {"passed": 10, "failed": 2}
        output = tmp_path / "merged.json"
        saved = save_merged_report(misra_repo, selftest, output)
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data["_schema"] is not None
        assert data["misra"]["total_violations"] == 5
        assert data["selftest"]["passed"] == 10

    def test_save_merged_report_no_selftest(self, tmp_path):
        """save_merged_report without selftest data."""
        from yuleosh.ci.misra_report.core.reporting import save_merged_report
        misra_repo = {"total_violations": 3}
        output = tmp_path / "merged-no-selftest.json"
        saved = save_merged_report(misra_repo, output_path=output)
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data["selftest"] == {}

    def test_print_summary(self, capsys):
        """print_summary outputs formatted text to stdout."""
        from yuleosh.ci.misra_report.core.reporting import print_summary
        summary = {
            "total_violations": 10,
            "unique_rules": 5,
            "affected_files": 3,
            "density_per_kloc": 2.5,
            "by_severity": {"error": 4, "warning": 3, "style": 2},
        }
        print_summary(summary)
        captured = capsys.readouterr()
        assert "MISRA Report Summary" in captured.out
        assert "Total violations:" in captured.out
        assert "2.5" in captured.out

    def test_generate_json_report_with_exclusions(self, tmp_path):
        """generate_json_report with explicit excluded_rules and excluded_files."""
        from yuleosh.ci.misra_report.core.reporting import generate_json_report
        violations = [{"rule_id": "Rule 10.1", "severity": "high", "file": "main.c"}]
        groups = {"Rule 10.1": violations}
        report = generate_json_report(
            violations, groups,
            rule_defs={"rules": {}},
            output_dir=str(tmp_path),
            excluded_rules=["Rule 99.9"],
            excluded_files=["*.test.c"],
        )
        assert "deviations" in report
        assert report["excluded_rules"] == ["Rule 99.9"]
        assert report["excluded_files"] == ["*.test.c"]

    def test_generate_json_report_empty_violations(self):
        """generate_json_report with empty violations list."""
        from yuleosh.ci.misra_report.core.reporting import generate_json_report
        report = generate_json_report([], {}, rule_defs={"rules": {}})
        assert report["total_violations"] == 0
        assert report["unique_rules"] == 0
        assert "deviations" in report


# ===========================================================================
# Deviation - fill remaining gaps
# ===========================================================================


class TestDeviationGaps:
    """Fill uncovered paths in deviation.py."""

    def test_deviation_to_dict_empty_tuple(self):
        """_deviation_to_dict with empty tuple returns default values."""
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict
        result = _deviation_to_dict(())
        assert result["deviation_rule"] == ""
        assert result["status"] == "pending"

    def test_is_deviation_expired_none(self):
        """_is_deviation_expired with None input."""
        from yuleosh.ci.misra_report.deviation import _is_deviation_expired
        assert _is_deviation_expired(None) is False

    def test_match_deviation_with_patterns(self):
        """_match_deviation with file_pattern patterns."""
        from yuleosh.ci.misra_report.deviation import _match_deviation
        deviations = [{"rule_id": "Rule 10.1", "file_pattern": "src/*.c"}]
        # Should match
        matched, info = _match_deviation("Rule 10.1", "src/main.c", deviations)
        assert matched is True
        assert info is not None


# ===========================================================================
# Traceability - fill gaps
# ===========================================================================


class TestTraceabilityGaps:
    """Fill uncovered paths in traceability.py."""

    def test_generate_traceability_matrix_basic(self):
        """generate_traceability_matrix creates rows for each violation."""
        from yuleosh.ci.misra_report.traceability import generate_traceability_matrix
        violations = [
            {"rule_id": "Rule 10.1", "file": "main.c", "line": 42,
             "message": "Test", "severity": "high"},
        ]
        rule_defs = {"rules": {"Rule 10.1": {"category": "required"}}}
        result = generate_traceability_matrix(violations, rule_defs, [])
        assert len(result) >= 1

    def test_generate_traceability_matrix_empty(self):
        """generate_traceability_matrix with empty violations."""
        from yuleosh.ci.misra_report.traceability import generate_traceability_matrix
        result = generate_traceability_matrix([], {}, [])
        assert result == []
