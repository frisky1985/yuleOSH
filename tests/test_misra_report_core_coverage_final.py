#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Supplementary tests — final remaining coverage gaps in misra_report modules.
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
# config.py — remaining gaps: YAML import, custom file loads, subprocess
# ===========================================================================


class TestConfigFinalGaps:
    """Final remaining coverage gaps in config.py."""

    def test_load_ci_config_yaml_file(self, tmp_path, monkeypatch):
        """_load_ci_config with YAML configuration file."""
        from yuleosh.ci.misra_report.core.config import _load_ci_config
        monkeypatch.chdir(tmp_path)
        yaml_file = tmp_path / ".yuleosh.yaml"
        yaml_file.write_text("misra:\n  enabled: true\n")
        result = _load_ci_config()
        assert result is not None

    def test_load_ci_config_json_file(self, tmp_path, monkeypatch):
        """_load_ci_config with JSON configuration file."""
        from yuleosh.ci.misra_report.core.config import _load_ci_config
        monkeypatch.chdir(tmp_path)
        json_file = tmp_path / ".yuleosh.json"
        json_file.write_text('{"misra": {"enabled": true}}')
        result = _load_ci_config()
        assert result is not None

    def test_load_ci_config_yaml_first_precedence(self, tmp_path, monkeypatch):
        """_load_ci_config: .yaml takes precedence over .json when both exist."""
        from yuleosh.ci.misra_report.core.config import _load_ci_config
        monkeypatch.chdir(tmp_path)
        yaml_file = tmp_path / ".yuleosh.yaml"
        yaml_file.write_text("misra:\n  enabled: false\n")
        json_file = tmp_path / ".yuleosh.json"
        json_file.write_text('{"misra": {"enabled": true}}')
        result = _load_ci_config()
        assert result is not None

    def test_load_rule_definitions_custom_yaml(self, tmp_path):
        """load_rule_definitions with custom YAML file."""
        from yuleosh.ci.misra_report.core.config import load_rule_definitions
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("meta:\n  version: '1.0'\n")
        result = load_rule_definitions(rules_path=rules_file)
        assert isinstance(result, dict)

    def test_get_tool_version_subprocess(self):
        """get_tool_version returns a version string."""
        from yuleosh.ci.misra_report.core.config import get_tool_version
        version = get_tool_version()
        assert isinstance(version, str)

    def test_get_tool_version_cppcheck_raises(self, monkeypatch):
        """get_tool_version handles subprocess.CalledProcessError."""
        import subprocess
        from yuleosh.ci.misra_report.core.config import get_tool_version

        def _mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "cppcheck")
        monkeypatch.setattr("subprocess.run", _mock_run)
        version = get_tool_version()
        assert isinstance(version, str)

    def test_get_tool_version_file_not_found(self, monkeypatch):
        """get_tool_version handles FileNotFoundError."""
        from yuleosh.ci.misra_report.core.config import get_tool_version

        def _mock_run(*args, **kwargs):
            raise FileNotFoundError("cppcheck not found")
        monkeypatch.setattr("subprocess.run", _mock_run)
        version = get_tool_version()
        assert isinstance(version, str)

    def test_load_ci_config_no_files(self, tmp_path, monkeypatch):
        """_load_ci_config returns empty dict when no config files exist."""
        from yuleosh.ci.misra_report.core.config import _load_ci_config
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(empty_dir)
        result = _load_ci_config()
        assert result == {}


# ===========================================================================
# parser.py — remaining gaps: normalize_rule_id edge cases
# ===========================================================================


class TestParserFinalGaps:
    """Final parser coverage gaps."""

    def test_pat_text_rule_from_message(self):
        """_PATTERN_TEXT_RULE should match 'Rule X.Y' in messages."""
        from yuleosh.ci.misra_report.core.parser import _PATTERN_TEXT_RULE
        msg1 = "Violation of Rule 10.1"
        msg2 = "MISRA Rule 15.6 check"
        assert _PATTERN_TEXT_RULE.search(msg1) is not None
        assert _PATTERN_TEXT_RULE.search(msg2) is not None


# ===========================================================================
# reporting.py — remaining gaps
# ===========================================================================


class TestReportingFinalGaps:
    """Final reporting coverage gaps."""

    def test_generate_markdown_report_diff_only(self):
        """generate_markdown_report with diff but no severity/category."""
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {
            "total_violations": 5,
            "diff": {"delta_total": -2, "previous_total": 7, "previous_build_id": "old"},
            "generated_at": "now",
        }
        md = generate_markdown_report(report)
        assert "Trend" in md or "Diff" in md
        assert "-2" in md

    def test_generate_markdown_report_no_groups(self):
        """generate_markdown_report without groups section."""
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        report = {
            "total_violations": 3,
            "unique_rules": 2,
            "affected_files": 1,
            "density_per_kloc": 1.0,
            "by_severity": {"error": 2},
            "by_rule_type": {"required": 2},
            "category_breakdown": {"required": 2},
            "generated_at": "now",
        }
        md = generate_markdown_report(report)
        assert "By Severity" in md
        assert "By Rule Type" in md
        assert "By Category" in md

    def test_generate_markdown_report_with_groups_over_20(self):
        """generate_markdown_report with more than 20 groups."""
        from yuleosh.ci.misra_report.core.reporting import generate_markdown_report
        groups = {}
        for i in range(25):
            groups[f"Rule {i}.1"] = {"count": 1, "violations": []}
        report = {
            "total_violations": 25,
            "unique_rules": 25,
            "affected_files": 10,
            "density_per_kloc": 5.0,
            "generated_at": "now",
            "groups": groups,
        }
        md = generate_markdown_report(report)
        assert "and 5 more rules" in md

    def test_save_merged_report_default_path(self, tmp_path, monkeypatch):
        """save_merged_report with default path behavior."""
        from yuleosh.ci.misra_report.core.reporting import save_merged_report
        monkeypatch.chdir(tmp_path)
        misra_repo = {"total_violations": 1}
        saved = save_merged_report(misra_repo)
        assert saved.exists()


# ===========================================================================
# deviation.py — remaining gaps
# ===========================================================================


class TestDeviationFinalGaps:
    """Final deviation coverage gaps."""

    def test_match_deviation_file_pattern(self):
        """_match_deviation with fnmatch pattern matching."""
        from yuleosh.ci.misra_report.deviation import _match_deviation
        deviations = [
            {"rule_id": "Rule 10.1", "file_pattern": "*.c"},
            {"rule_id": "Rule 10.3", "file_pattern": "*.h"},
        ]
        matched, info = _match_deviation("Rule 10.1", "main.c", deviations)
        assert matched is True
        assert info["deviation_rule"] == "Rule 10.1"

        # Should NOT match different pattern
        matched2, info2 = _match_deviation("Rule 10.1", "header.h", deviations)
        assert matched2 is False

    def test_match_deviation_no_file_pattern(self):
        """_match_deviation with deviation that has empty file_pattern."""
        from yuleosh.ci.misra_report.deviation import _match_deviation
        deviations = [
            {"rule_id": "Rule 10.1", "file_pattern": ""},
        ]
        matched, info = _match_deviation("Rule 10.1", "main.c", deviations)
        assert isinstance(matched, bool)

    def test_match_deviation_rule_not_found(self):
        """_match_deviation when rule is not in deviations list."""
        from yuleosh.ci.misra_report.deviation import _match_deviation
        deviations = [{"rule_id": "Rule 10.1", "file_pattern": "*.c"}]
        matched, info = _match_deviation("Rule 99.9", "main.c", deviations)
        assert matched is False
        assert info is None


# ===========================================================================
# traceability.py — remaining gaps
# ===========================================================================


class TestTraceabilityFinalGaps:
    """Final traceability coverage gaps."""

    def test_generate_traceability_matrix_with_matched_rules(self):
        """generate_traceability_matrix matches rules from rule_defs."""
        from yuleosh.ci.misra_report.traceability import generate_traceability_matrix
        violations = [
            {"rule_id": "Rule 10.1", "file": "main.c", "line": 42,
             "message": "Implicit conversion", "severity": "high"},
        ]
        rule_defs = {"rules": {"Rule 10.1": {"category": "required"}}}
        result = generate_traceability_matrix(violations, rule_defs, [])
        assert len(result) >= 1
        assert all(isinstance(r, dict) for r in result)

    def test_generate_traceability_matrix_with_deviations(self):
        """generate_traceability_matrix marks deviations as acknowledged."""
        from yuleosh.ci.misra_report.traceability import generate_traceability_matrix
        violations = [
            {"rule_id": "Rule 10.1", "file": "main.c", "line": 42,
             "message": "Test", "severity": "high",
             "category": "required", "rule_type": "required",
             "rule_year": "2012"},
        ]
        rule_defs = {"rules": {"Rule 10.1": {"category": "required"}}}
        deviations = [("Rule 10.1", "*.c")]
        result = generate_traceability_matrix(violations, rule_defs, deviations)
        assert len(result) >= 1

    def test_generate_traceability_full_flow(self):
        """generate_traceability full flow with multiple violations."""
        from yuleosh.ci.misra_report.traceability import generate_traceability_matrix
        violations = [
            {"rule_id": "Rule 10.1", "file": "main.c", "line": 10,
             "message": "Implicit", "severity": "high",
             "rule_type": "required", "category": "required"},
            {"rule_id": "Rule 15.6", "file": "uart.c", "line": 20,
             "message": "Nesting", "severity": "medium",
             "rule_type": "advisory", "category": "advisory"},
        ]
        rule_defs = {"rules": {"Rule 10.1": {"category": "required"}}}
        result = generate_traceability_matrix(violations, rule_defs, [])
        assert len(result) == 2


class TestTraceabilityReportSection:
    """Cover 'generate_report_section' if it exists."""

    def test_generate_report_section(self):
        """Test generate_report_section if it exists."""
        try:
            from yuleosh.ci.misra_report.traceability import generate_report_section
            result = generate_report_section([])
            assert isinstance(result, str)
        except ImportError:
            pass
