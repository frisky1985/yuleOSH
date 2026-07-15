#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for ci/misra_report — MISRA static analysis engine.

Tests the core data models directly (models.py has been extended with
MisraViolation and MisraSummary).
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.ci.misra_report.models import MisraViolation, MisraSummary


class TestMisraViolation:
    """MisraViolation dataclass."""

    def test_create_violation(self):
        v = MisraViolation(
            rule_id="Rule 10.1",
            category="Required",
            file="src/main.c",
            line=42,
            message="Implicit conversion",
            severity="high",
        )
        assert v.rule_id == "Rule 10.1"
        assert v.line == 42
        assert v.severity == "high"

    def test_to_dict(self):
        v = MisraViolation(
            rule_id="Rule 18.4",
            category="Required",
            file="src/uart.c",
            line=100,
            message="Pointer arithmetic",
        )
        d = v.to_dict()
        assert d["rule_id"] == "Rule 18.4"
        assert d["file"] == "src/uart.c"

    def test_defaults(self):
        v = MisraViolation("Rule 1.1", "Advisory", "test.c", 1, "Test")
        assert v.fix_proposed == ""
        assert v.suppressed is False

    def test_all_severities(self):
        for sev in ["high", "medium", "low", "info"]:
            v = MisraViolation("R1", "Req", "f.c", 1, "msg", severity=sev)
            assert v.severity == sev


class TestMisraSummary:
    """MisraSummary aggregation."""

    def test_empty_summary(self):
        s = MisraSummary()
        assert s.total_violations == 0
        assert s.passed is True
        assert s.high_severity == 0

    def test_with_violations(self):
        violations = [
            MisraViolation("Rule 10.1", "Required", "a.c", 10, "Msg1", severity="high"),
            MisraViolation("Rule 11.1", "Required", "b.c", 20, "Msg2", severity="medium"),
            MisraViolation("Rule 20.9", "Advisory", "c.c", 30, "Msg3", severity="low"),
        ]
        s = MisraSummary(violations=violations)
        assert s.total_violations == 3
        assert s.high_severity == 1
        assert s.passed is False

    def test_pass_threshold(self):
        violations = [
            MisraViolation("Rule 1.2", "Advisory", "a.c", 1, "Minor"),
        ]
        s = MisraSummary(violations=violations, max_allowed_total=5)
        assert s.passed is True

    def test_fail_threshold(self):
        violations = [
            MisraViolation("Rule 10.1", "Required", "a.c", 1, "Major", severity="high"),
        ]
        s = MisraSummary(violations=violations, max_allowed_critical=0)
        assert s.passed is False

    def test_violation_to_dict_roundtrip(self):
        v = MisraViolation("Rule 1.1", "Advisory", "file.c", 5, "Test violation", severity="low")
        d = v.to_dict()
        assert d["rule_id"] == "Rule 1.1"
        assert d["severity"] == "low"
        assert d["suppressed"] is False
