
# @tests src/yuleosh/spec/patterns.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for spec/patterns.py — pattern library, conflict detection, suggestions."""

import pytest
from yuleosh.spec.validate import SpecRequirement, SpecDocument
from yuleosh.spec.patterns import (
    REQUIREMENT_PATTERNS,
    check_conflicts,
    detect_pattern,
    suggest_missing_patterns,
    validate_spec_with_patterns,
)


def _req(name, shall, req_id=""):
    return SpecRequirement(name, shall, [], [], "", req_id, "", "", "PROPOSED")


def test_detect_pattern_sensor():
    req = _req("ADC Sensor Read", ["The system SHALL read ADC sensor data at 100Hz"], "RS-001")
    assert detect_pattern(req) == "sensor_read"


def test_detect_pattern_watchdog():
    req = _req("WDT", ["The system SHALL kick the watchdog every 50ms"], "RS-002")
    assert detect_pattern(req) == "watchdog"


def test_detect_pattern_can():
    req = _req("CAN TX", ["The system SHALL transmit CAN frame within 10ms"], "RS-003")
    assert detect_pattern(req) == "can_comm"


def test_detect_pattern_none():
    req = _req("Generic", ["The system SHALL process data"], "RS-004")
    result = detect_pattern(req)
    assert result is None or result in REQUIREMENT_PATTERNS


def test_check_conflicts_duplicate_shall():
    doc = SpecDocument("test")
    doc.requirements = [
        _req("R1", ["The system SHALL read sensor data at 100Hz"], "RS-001"),
        _req("R2", ["The system SHALL read sensor data at 100Hz"], "RS-002"),
    ]
    conflicts = check_conflicts(doc)
    dups = [c for c in conflicts if c["type"] == "duplicate_shall"]
    assert len(dups) >= 1
    assert "RS-001" in dups[0]["req_ids"] or "RS-002" in dups[0]["req_ids"]


def test_check_conflicts_clean_doc():
    doc = SpecDocument("test")
    doc.requirements = [
        _req("R1", ["The system SHALL initialise the watchdog"], "RS-001"),
        _req("R2", ["The system SHALL read ADC sensor data"], "RS-002"),
    ]
    conflicts = check_conflicts(doc)
    dups = [c for c in conflicts if c["type"] == "duplicate_shall"]
    assert len(dups) == 0


def test_check_conflicts_no_crash_on_timing():
    doc = SpecDocument("test")
    doc.requirements = [
        _req("R1", ["The system SHALL respond within < 10ms"], "RS-001"),
        _req("R2", ["The system SHALL wait > 100ms before retry"], "RS-002"),
    ]
    conflicts = check_conflicts(doc)
    assert isinstance(conflicts, list)


def test_suggest_missing_patterns_sensor_incomplete():
    doc = SpecDocument("test")
    doc.requirements = [
        _req("Sensor", ["The system SHALL read sensor data"], "RS-001"),
    ]
    suggestions = suggest_missing_patterns(doc)
    assert len(suggestions) >= 1
    assert suggestions[0]["pattern"] == "sensor_read"
    assert len(suggestions[0]["missing_shalls"]) >= 1


def test_validate_spec_with_patterns_empty():
    doc = SpecDocument("test")
    result = validate_spec_with_patterns(doc)
    assert "issues" in result
    assert "conflicts" in result
    assert "suggestions" in result
    assert isinstance(result["issue_count"], int)
    assert result["conflict_count"] == 0


def test_validate_spec_with_patterns_integrates_conflicts():
    doc = SpecDocument("test")
    doc.requirements = [
        _req("R1", ["The system SHALL read sensor data at 100Hz"], "RS-001"),
        _req("R2", ["The system SHALL read sensor data at 100Hz"], "RS-002"),
    ]
    result = validate_spec_with_patterns(doc)
    assert result["conflict_count"] >= 1
    # conflicts promoted to issues
    assert result["issue_count"] >= 1
