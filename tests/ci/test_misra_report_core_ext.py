# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for misra_report core modules.

Covers: analysis, config, parser, reporting, models, deviation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ===========================================================================
# core/config tests
# ===========================================================================


class TestCoreConfig:
    """Tests for misra_report/core/config.py."""

    def test_misra_schema_version(self):
        from yuleosh.ci.misra_report.core.config import _MISRA_SCHEMA_VERSION
        assert _MISRA_SCHEMA_VERSION

    def test_default_report_dir(self):
        from yuleosh.ci.misra_report.core.config import _DEFAULT_REPORT_DIR
        assert _DEFAULT_REPORT_DIR is not None

    def test_count_source_lines(self, tmp_path):
        from yuleosh.ci.misra_report.core.config import _count_source_lines
        f = tmp_path / "test.c"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = _count_source_lines([str(f)])
        assert result == 3

    def test_count_source_lines_nonexistent(self, tmp_path):
        from yuleosh.ci.misra_report.core.config import _count_source_lines
        result = _count_source_lines(["/nonexistent/file.c"])
        assert result == 0

    def test_count_source_lines_empty_list(self):
        from yuleosh.ci.misra_report.core.config import _count_source_lines
        assert _count_source_lines([]) == 0

    def test_extract_excluded_rules(self):
        from yuleosh.ci.misra_report.core.config import _extract_excluded_rules
        result = _extract_excluded_rules()  # Should return empty list when not configured
        assert isinstance(result, list)

    def test_extract_excluded_files(self):
        from yuleosh.ci.misra_report.core.config import _extract_excluded_files
        result = _extract_excluded_files()
        assert isinstance(result, list)

    def test_load_rule_definitions(self):
        from yuleosh.ci.misra_report.core.config import load_rule_definitions
        rules = load_rule_definitions()
        assert isinstance(rules, dict)

    def test_get_ruleset_version(self):
        from yuleosh.ci.misra_report.core.config import get_ruleset_version
        # get_ruleset_version needs rule_defs argument
        version = get_ruleset_version(rule_defs={"rules": {}})
        assert isinstance(version, str)

    def test_get_tool_version(self):
        from yuleosh.ci.misra_report.core.config import get_tool_version
        version = get_tool_version()
        assert isinstance(version, str)

    def test_get_ci_environ(self):
        from yuleosh.ci.misra_report.core.config import get_ci_environ
        env = get_ci_environ()
        assert isinstance(env, dict)


# ===========================================================================
# core/analysis tests
# ===========================================================================


class TestCoreAnalysis:
    """Tests for misra_report/core/analysis.py."""

    def test_group_by_rule_empty(self):
        from yuleosh.ci.misra_report.core.analysis import group_by_rule
        assert group_by_rule([]) == {}

    def test_group_by_rule_single(self):
        from yuleosh.ci.misra_report.core.analysis import group_by_rule
        v = [{"rule_id": "Rule 10.1"}]
        groups = group_by_rule(v)
        assert "Rule 10.1" in groups
        assert len(groups["Rule 10.1"]) == 1

    def test_group_by_rule_multiple(self):
        from yuleosh.ci.misra_report.core.analysis import group_by_rule
        v = [
            {"rule_id": "Rule 10.1"},
            {"rule_id": "Rule 10.1"},
            {"rule_id": "Rule 18.4"},
        ]
        groups = group_by_rule(v)
        assert len(groups["Rule 10.1"]) == 2
        assert len(groups["Rule 18.4"]) == 1

    def test_classify_rule_type(self):
        from yuleosh.ci.misra_report.core.analysis import _classify_rule_type
        assert _classify_rule_type("Dir 4.1") == "directive"
        assert _classify_rule_type("Rule 10.1") == "required"
        assert _classify_rule_type("Rule 10.3") == "advisory"
        assert _classify_rule_type("Rule 10.4") == "advisory"
        assert _classify_rule_type("") == "unknown"
        assert _classify_rule_type(None) == "unknown"

    def test_compute_summary_stats_basic(self):
        from yuleosh.ci.misra_report.core.analysis import (
            compute_summary_stats, group_by_rule, enrich_with_definitions,
        )
        violations = [
            {"rule_id": "Rule 10.1", "severity": "high", "file": "main.c"},
            {"rule_id": "Rule 18.4", "severity": "medium", "file": "uart.c"},
        ]
        # Enrich first to add rule_type
        enriched = enrich_with_definitions(violations, rule_defs={"rules": {}})
        groups = group_by_rule(enriched)
        stats = compute_summary_stats(enriched, groups)
        assert stats["total_violations"] == 2
        assert stats["unique_rules"] == 2
        assert stats["affected_files"] == 2

    def test_compute_summary_stats_empty(self):
        from yuleosh.ci.misra_report.core.analysis import compute_summary_stats, group_by_rule
        stats = compute_summary_stats([], {})
        assert stats["total_violations"] == 0
        assert stats["unique_rules"] == 0

    def test_compute_summary_stats_no_files(self):
        from yuleosh.ci.misra_report.core.analysis import compute_summary_stats, group_by_rule
        violations = [{"rule_id": "Rule 10.1", "severity": "high"}]
        groups = group_by_rule(violations)
        stats = compute_summary_stats(violations, groups)
        assert stats["total_violations"] == 1
        assert stats["affected_files"] == 0

    def test_load_prev_report_no_files(self, tmp_path):
        from yuleosh.ci.misra_report.core.analysis import _load_prev_report
        assert _load_prev_report(tmp_path) is None

    def test_load_prev_report_with_file(self, tmp_path):
        from yuleosh.ci.misra_report.core.analysis import _load_prev_report
        report = {"total_violations": 5, "build_id": "abc"}
        f = tmp_path / "misra-report-test.json"
        f.write_text(json.dumps(report), encoding="utf-8")
        loaded = _load_prev_report(str(tmp_path))
        assert loaded is not None
        assert loaded["total_violations"] == 5

    def test_compute_prev_build_diff(self):
        from yuleosh.ci.misra_report.core.analysis import _compute_prev_build_diff
        current = {"total_violations": 10}
        prev = {"total_violations": 5, "build_id": "old", "date": "2026-01-01"}
        diff = _compute_prev_build_diff(current, prev)
        assert diff["delta_total"] == 5
        assert diff["previous_total"] == 5
        assert diff["previous_build_id"] == "old"

    def test_compute_category_breakdown(self):
        from yuleosh.ci.misra_report.core.analysis import _compute_category_breakdown
        violations = [
            {"category": "required", "severity": "high"},
            {"category": "advisory"},
            {"category": "required"},
        ]
        breakdown = _compute_category_breakdown(violations)
        assert breakdown["required"] == 2
        assert breakdown["advisory"] == 1

    def test_compute_category_breakdown_with_severity(self):
        from yuleosh.ci.misra_report.core.analysis import _compute_category_breakdown
        violations = [
            {"severity": "error"},
            {"severity": "warning"},
        ]
        breakdown = _compute_category_breakdown(violations)
        assert "error" in breakdown
        assert "warning" in breakdown


# ===========================================================================
# core/parser tests
# ===========================================================================


class TestCoreParser:
    """Tests for misra_report/core/parser.py."""

    def test_extract_file_path(self):
        from yuleosh.ci.misra_report.core.parser import _extract_file_path
        # Non-existent file returns raw path
        result = _extract_file_path("/tmp/nonexistent/file.c")
        assert result is not None

    def test_extract_file_path_empty(self):
        from yuleosh.ci.misra_report.core.parser import _extract_file_path
        assert _extract_file_path("") is None

    def test_extract_file_path_stdin(self):
        from yuleosh.ci.misra_report.core.parser import _extract_file_path
        assert _extract_file_path("<stdin>") is None

    def test_is_valid_source_path(self):
        from yuleosh.ci.misra_report.core.parser import _is_valid_source_path
        assert _is_valid_source_path("main.c") is True
        assert _is_valid_source_path("file.hpp") is True
        assert _is_valid_source_path("file.asm") is True
        assert _is_valid_source_path("notes.txt") is False
        assert _is_valid_source_path("") is False

    def test_parse_cppcheck_output_bracketed(self):
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        text = (
            "[main.c:10:5] (error) Array access out of bounds [arrayIndexOutOfBounds]\n"
            "[main.c:25:1] (warning) Uninitialized variable [uninitvar]\n"
        )
        violations = parse_cppcheck_output(text)
        assert len(violations) == 2
        assert violations[0]["severity"] == "error"
        assert violations[1]["severity"] == "warning"

    def test_parse_cppcheck_output_legacy(self):
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        text = "main.c:10:5: error: Array access out of bounds [arrayIndexOutOfBounds]\n"
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1
        assert violations[0]["severity"] == "error"

    def test_parse_cppcheck_output_patterns(self):
        from yuleosh.ci.misra_report.core.parser import (
            _PATTERN_CPPCHECK, _PATTERN_MISRA_RULE, _PATTERN_TEXT_RULE,
        )
        assert _PATTERN_CPPCHECK is not None
        assert _PATTERN_MISRA_RULE is not None
        assert _PATTERN_TEXT_RULE is not None

    def test_normalize_rule_id(self):
        from yuleosh.ci.misra_report.core.parser import _normalize_rule_id
        # New behavior: normalize to canonical format
        result = _normalize_rule_id(" Rule 10.1 ")
        assert result == "misra-c2023-10.1", f"Expected 'misra-c2023-10.1', got '{result}'"

    def test_parse_empty_output(self):
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        assert parse_cppcheck_output("") == []


# ===========================================================================
# core/reporting tests
# ===========================================================================


class TestCoreReporting:
    """Tests for misra_report/core/reporting.py."""

    def test_generate_json_report_basic(self):
        from yuleosh.ci.misra_report.core.reporting import generate_json_report
        violations = [{"rule_id": "Rule 10.1", "severity": "high", "file": "main.c"}]
        groups = {"Rule 10.1": violations}
        report = generate_json_report(violations, groups, rule_defs={"rules": {}})
        assert report["total_violations"] == 1
        assert report["unique_rules"] == 1

    def test_generate_json_report_with_output_dir(self, tmp_path):
        from yuleosh.ci.misra_report.core.reporting import generate_json_report
        violations = [{"rule_id": "Rule 10.1", "severity": "high", "file": "main.c"}]
        groups = {"Rule 10.1": violations}
        report = generate_json_report(
            violations, groups,
            rule_defs={"rules": {}},
            output_dir=str(tmp_path),
        )
        assert "total_violations" in report

    def test_generate_json_report_with_deviation(self, tmp_path):
        from yuleosh.ci.misra_report.core.reporting import generate_json_report
        violations = [{"rule_id": "Rule 10.1", "severity": "high", "file": "main.c"}]
        groups = {"Rule 10.1": violations}
        report = generate_json_report(
            violations, groups,
            rule_defs={"rules": {}},
            output_dir=str(tmp_path),
            deviation_list=[{"rule_id": "Rule 10.1", "reason": "False positive"}],
        )
        assert "deviations" in report

    def test_save_report(self, tmp_path):
        from yuleosh.ci.misra_report.core.reporting import save_report
        report = {"total_violations": 5, "build_id": "b1"}
        # save_report may return None or path as str
        saved_path = save_report(report, str(tmp_path))
        assert saved_path is not None
        if isinstance(saved_path, str):
            assert saved_path.startswith("misra-report-") or Path(saved_path).exists()

    def test_generate_markdown_report(self):
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {
            "total_violations": 3,
            "unique_rules": 2,
            "affected_files": 1,
            "density_per_kloc": 1.5,
            "by_severity": {"error": 2, "warning": 1},
            "by_rule_type": {"required": 2, "advisory": 1},
            "generated_at": "2026-01-01",
            "tool_version": "1.0",
            "ruleset_version": "MISRA C:2012",
            "groups": {
                "Rule 10.1": {
                    "count": 2,
                    "violations": [{"file": "main.c", "line": 42, "message": "Implicit conversion"}],
                },
            },
        }
        md = generate_markdown_report(report)
        assert "MISRA" in md or "Rule 10.1" in md or "Violation" in md

    def test_generate_markdown_report_empty(self):
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        md = generate_markdown_report({})
        assert md is not None
        assert len(md) > 0

    def test_generate_markdown_report_with_diff(self):
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {
            "total_violations": 5,
            "diff": {"delta_total": -2, "previous_total": 7},
            "by_severity": {"error": 3, "warning": 2},
            "category_breakdown": {"required": 3, "advisory": 2},
            "generated_at": "2026-01-01",
        }
        md = generate_markdown_report(report)
        assert "Trend vs Previous" in md
        assert "category_breakdown" in report or "Category" in md


# ===========================================================================
# Deviation tests
# ===========================================================================


class TestDeviation:
    """Tests for misra_report/deviation.py."""

    def test_deviation_to_dict_from_tuple(self):
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict
        result = _deviation_to_dict(("Rule 10.1", "*.c"))
        assert result["deviation_rule"] == "Rule 10.1"
        assert result["file_pattern"] == "*.c"
        assert result["status"] == "pending"

    def test_deviation_to_dict_from_tuple_full(self):
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict
        result = _deviation_to_dict(("Rule 10.1", "*.c", "reason", "approver",
                                      "high", "2026-12-31", "approved", "JIRA-123"))
        assert result["deviation_rule"] == "Rule 10.1"
        assert result["status"] == "approved"
        assert result["alm_ticket"] == "JIRA-123"

    def test_deviation_to_dict_from_dict(self):
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict
        result = _deviation_to_dict({
            "rule_id": "Rule 10.1",
            "file_pattern": "*.c",
            "reason": "False positive",
            "approved_by": "manager",
            "risk_level": "low",
        })
        assert result["deviation_rule"] == "Rule 10.1"
        assert result["risk_level"] == "low"

    def test_deviation_to_dict_empty(self):
        from yuleosh.ci.misra_report.deviation import _deviation_to_dict
        result = _deviation_to_dict(())
        assert result["deviation_rule"] == ""

    def test_is_deviation_expired(self):
        from yuleosh.ci.misra_report.deviation import _is_deviation_expired
        # Past date should be expired
        assert _is_deviation_expired("2020-01-01T00:00:00") is True
        assert _is_deviation_expired("2099-01-01T00:00:00") is False
        assert _is_deviation_expired("") is False
        assert _is_deviation_expired("not-a-date") is False

    def test_match_deviation_basic(self):
        from yuleosh.ci.misra_report.deviation import _match_deviation
        deviations = [{"rule_id": "Rule 10.1", "file_pattern": "*.c"}]
        matched, info = _match_deviation("Rule 10.1", "main.c", deviations)
        assert matched is True
        assert info["deviation_rule"] == "Rule 10.1"

    def test_match_deviation_no_match(self):
        from yuleosh.ci.misra_report.deviation import _match_deviation
        matched, info = _match_deviation("Rule 99.9", "main.c", [])
        assert matched is False
        assert info is None
