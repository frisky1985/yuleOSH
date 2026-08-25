"""Unit tests for yuleosh.spec.validate — pure Python, no external deps."""

# @tests src/yuleosh/spec/validate.py

import json
import tempfile
import os
from pathlib import Path

import pytest

from yuleosh.spec.validate import (
    SpecRequirement,
    SpecScenario,
    SpecDocument,
    parse_spec,
    validate_spec,
    diff_specs,
    validate_status_transition,
    _parse_id,
    _id_to_level,
    _id_to_parent,
    _is_table_separator,
    _is_shall_table_header,
    ALLOWED_STATUSES,
    VALID_STATUS_TRANSITIONS,
    ID_PATTERN,
    HEADER_ID_PATTERN,
    TABLE_ID_PATTERN,
)


class TestSpecRequirement:
    def test_create_default(self):
        r = SpecRequirement(name="Test", shall=["must work"], should=[], may=[], reason="testing")
        assert r.name == "Test"
        assert r.shall == ["must work"]
        assert r.should == []
        assert r.may == []
        assert r.reason == "testing"
        assert r.req_id == ""
        assert r.level == ""
        assert r.parent == ""
        assert r.status == "PROPOSED"

    def test_to_dict(self):
        r = SpecRequirement(
            name="Test", shall=["a"], should=["b"], may=["c"],
            reason="why", req_id="RS-001", level="SYS", parent="", status="APPROVED",
        )
        d = r.to_dict()
        assert d["name"] == "Test"
        assert d["shall"] == ["a"]
        assert d["shall_count"] == 1
        assert d["status"] == "APPROVED"


class TestSpecScenario:
    def test_create(self):
        s = SpecScenario(name="SC1", given=["ready"], when=["go"], then=["done"])
        assert s.name == "SC1"
        assert s.given == ["ready"]
        assert s.when == ["go"]
        assert s.then == ["done"]

    def test_to_dict(self):
        s = SpecScenario(name="SC1", given=["ready"], when=["go"], then=["done"])
        d = s.to_dict()
        assert d["name"] == "SC1"
        assert d["given"] == ["ready"]


class TestSpecDocument:
    def test_create(self):
        doc = SpecDocument("/tmp/spec.md")
        assert doc.path == "/tmp/spec.md"
        assert doc.requirements == []
        assert doc.scenarios == []

    def test_to_dict_empty(self):
        doc = SpecDocument("/tmp/spec.md")
        d = doc.to_dict()
        assert d["requirement_count"] == 0
        assert d["scenario_count"] == 0

    def test_to_dict_with_data(self):
        doc = SpecDocument("/tmp/spec.md")
        doc.requirements.append(SpecRequirement("R1", shall=["x"], should=[], may=[], reason="r"))
        doc.scenarios.append(SpecScenario("S1", given=["g"], when=["w"], then=["t"]))
        d = doc.to_dict()
        assert d["requirement_count"] == 1
        assert d["scenario_count"] == 1
        assert d["total_shall"] == 1


# ── ID helpers ──────────────────────────────────────────────────────────────


class TestParseId:
    @pytest.mark.parametrize(
        "input_id, expected",
        [
            ("RS-001", ("RS", 1, None)),
            ("SWR-001", ("SWR", 1, None)),
            ("SWR-001.5", ("SWR", 1, 5)),
            ("SWR-42.99", ("SWR", 42, 99)),
            ("SCM-REQ-001", ("SCM-REQ", 1, None)),
            ("SCM-REQ-001.3", ("SCM-REQ", 1, 3)),
            ("FEATURE-001", ("FEATURE", 1, None)),
        ],
    )
    def test_valid_ids(self, input_id, expected):
        assert _parse_id(input_id) == expected

    @pytest.mark.parametrize(
        "input_id",
        ["", "invalid", "123", "RS-", "swr-a"],
    )
    def test_invalid_ids(self, input_id):
        assert _parse_id(input_id) == (None, None, None)


class TestIdToLevel:
    @pytest.mark.parametrize(
        "req_id, expected_level",
        [
            ("RS-001", "SYS"),
            ("RS-999", "SYS"),
            ("SWR-001", "SW"),
            ("SWR-001.1", "SW"),
            ("FEATURE-001", "FEATURE"),
            ("SCM-REQ-001", ""),
            ("BCM-REQ-001", ""),
            ("", ""),
        ],
    )
    def test_id_to_level(self, req_id, expected_level):
        assert _id_to_level(req_id) == expected_level


class TestIdToParent:
    @pytest.mark.parametrize(
        "req_id, expected_parent",
        [
            ("SWR-001.1", "RS-001"),
            ("SWR-042.3", "RS-042"),
            ("SWR-001", ""),  # top-level SWR has no parent
            ("RS-001", ""),
            ("SCM-REQ-001.2", "SCM-REQ-001"),
            ("SCM-REQ-001", ""),
        ],
    )
    def test_id_to_parent(self, req_id, expected_parent):
        assert _id_to_parent(req_id) == expected_parent


# ── Status helpers ─────────────────────────────────────────────────────────


class TestValidateStatusTransition:
    @pytest.mark.parametrize(
        "old_status, new_status",
        [
            ("PROPOSED", "APPROVED"),
            ("APPROVED", "IMPLEMENTED"),
            ("IMPLEMENTED", "VERIFIED"),
            (None, "PROPOSED"),
            ("PROPOSED", "PROPOSED"),  # same status is invalid per VALID_STATUS_TRANSITIONS
        ],
    )
    def test_valid_transitions(self, old_status, new_status):
        valid, msg = validate_status_transition(old_status, new_status)
        if old_status is None and new_status == "PROPOSED":
            assert valid is True
        elif old_status == new_status:
            assert valid is False  # No self-transition allowed
        else:
            assert valid is True

    @pytest.mark.parametrize(
        "old_status, new_status",
        [
            ("PROPOSED", "VERIFIED"),  # skip APPROVED + IMPLEMENTED
            ("APPROVED", "VERIFIED"),  # skip IMPLEMENTED
            ("VERIFIED", "PROPOSED"),  # terminal → anything
            ("PROPOSED", "IMPLEMENTED"),  # skip APPROVED
        ],
    )
    def test_invalid_transitions(self, old_status, new_status):
        valid, msg = validate_status_transition(old_status, new_status)
        assert valid is False
        assert "非法" in msg or "不允许" in msg or "终态" in msg


class TestAllowedStatuses:
    def test_constants(self):
        assert "PROPOSED" in ALLOWED_STATUSES
        assert "APPROVED" in ALLOWED_STATUSES
        assert "IMPLEMENTED" in ALLOWED_STATUSES
        assert "VERIFIED" in ALLOWED_STATUSES
        assert len(ALLOWED_STATUSES) == 4


# ── Table parsing helpers ──────────────────────────────────────────────────


class TestIsTableSeparator:
    @pytest.mark.parametrize(
        "line",
        [
            "|---|---|---|",
            "|:---|---:|:---|",
            "| --- | --- | --- |",
            "|:--|:--:|--:|",
        ],
    )
    def test_is_separator(self, line):
        assert _is_table_separator(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "| ID | Description |",
            "not a table",
            "# Header",
            "",
            "| --- incomplete",
        ],
    )
    def test_not_separator(self, line):
        assert _is_table_separator(line) is False


class TestIsShallTableHeader:
    @pytest.mark.parametrize(
        "col_names",
        [
            ["ID", "Description"],
            ["ID", "需求"],
            ["ID", "REQUIREMENT"],
            ["ID", "SHALL"],
        ],
    )
    def test_is_shall_header(self, col_names):
        assert _is_shall_table_header(col_names) is True

    @pytest.mark.parametrize(
        "col_names",
        [
            [],
            ["ID"],
            ["Name", "Value"],
        ],
    )
    def test_not_shall_header(self, col_names):
        assert _is_shall_table_header(col_names) is False


# ── Constants ──────────────────────────────────────────────────────────────


class TestConstants:
    def test_id_pattern_compiles(self):
        assert ID_PATTERN is not None
        assert HEADER_ID_PATTERN is not None
        assert TABLE_ID_PATTERN is not None

    def test_id_pattern_matches(self):
        assert ID_PATTERN.match("RS-001") is not None
        assert ID_PATTERN.match("SWR-042") is not None
        assert ID_PATTERN.match("SCM-REQ-001") is not None

    @pytest.mark.parametrize(
        "line",
        [
            "## RS-001: System Requirement",
            "### SWR-001.1: Software Requirement",
            "#### FEATURE-001: Feature Description",
        ],
    )
    def test_header_pattern_matches(self, line):
        assert HEADER_ID_PATTERN.match(line) is not None

    def test_header_pattern_no_match(self):
        assert HEADER_ID_PATTERN.match("## No ID Here") is None
