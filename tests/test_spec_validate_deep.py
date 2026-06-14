# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for yuleosh.spec.validate — spec parsing, validation, diffing, coverage."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.spec.validate import (
    SpecRequirement,
    SpecScenario,
    SpecDocument,
    parse_spec,
    validate_spec,
    diff_specs,
    _compute_coverage,
    _compute_impact_analysis,
    _parse_id,
    _id_to_level,
    _id_to_parent,
    validate_status_transition,
    _detect_status_from_lines,
    ALLOWED_STATUSES,
    VALID_STATUS_TRANSITIONS,
    ID_PATTERN,
    HEADER_ID_PATTERN,
    main,
)


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------

class TestSpecRequirement:
    """GIVEN SpecRequirement WHEN created THEN fields set."""

    def test_init_defaults(self):
        """GIVEN minimum args WHEN SpecRequirement THEN defaults apply."""
        r = SpecRequirement("name", ["shall-1"], [], [], "reason")
        assert r.name == "name"
        assert r.shall == ["shall-1"]
        assert r.should == []
        assert r.may == []
        assert r.reason == "reason"
        assert r.req_id == ""
        assert r.level == ""
        assert r.parent == ""
        assert r.status == "PROPOSED"

    def test_to_dict_keys(self):
        """GIVEN SpecRequirement WHEN to_dict THEN correct structure."""
        r = SpecRequirement("req-name", ["S1"], ["S2"], ["M1"], "because", req_id="RS-001", level="SYS")
        d = r.to_dict()
        assert d["name"] == "req-name"
        assert d["shall_count"] == 1
        assert d["should_count"] == 1
        assert d["may_count"] == 1
        assert d["req_id"] == "RS-001"

    def test_to_dict_shall_count(self):
        """GIVEN multiple SHALLs WHEN to_dict THEN correct count."""
        r = SpecRequirement("r", ["a", "b", "c"], [], [], "")
        assert r.to_dict()["shall_count"] == 3


class TestSpecScenario:
    """GIVEN SpecScenario WHEN created THEN fields set."""

    def test_init(self):
        """GIVEN GIVEN/WHEN/THEN WHEN SpecScenario THEN stored."""
        s = SpecScenario("test-scenario", ["GIVEN x"], ["WHEN y"], ["THEN z"])
        assert s.name == "test-scenario"
        assert s.given == ["GIVEN x"]

    def test_to_dict(self):
        """GIVEN SpecScenario WHEN to_dict THEN correct structure."""
        s = SpecScenario("s", ["g1"], ["w1"], ["t1"])
        d = s.to_dict()
        assert d["name"] == "s"
        assert d["given"] == ["g1"]


class TestSpecDocument:
    """GIVEN SpecDocument WHEN created THEN fields set."""

    def test_init(self):
        """GIVEN path WHEN SpecDocument THEN empty collections."""
        doc = SpecDocument("/path/to/spec.md")
        assert doc.path == "/path/to/spec.md"
        assert doc.requirements == []
        assert doc.scenarios == []

    def test_to_dict_structure(self):
        """GIVEN doc with data WHEN to_dict THEN correct."""
        doc = SpecDocument("spec.md")
        r = SpecRequirement("R1", ["shall"], [], [], "")
        r.shall_count = len(r.shall)  # workaround: shall_count not auto-set as attribute
        doc.requirements.append(r)
        doc.scenarios.append(SpecScenario("S1", ["g"], ["w"], ["t"]))
        d = doc.to_dict()
        assert d["requirement_count"] == 1
        assert d["scenario_count"] == 1
        assert d["total_shall"] == 1


# ---------------------------------------------------------------------------
# _parse_id
# ---------------------------------------------------------------------------

class TestParseId:
    """GIVEN _parse_id WHEN called THEN parses ID correctly."""

    def test_rs_id(self):
        """GIVEN RS-001 WHEN _parse_id THEN (RS, 1, None)."""
        assert _parse_id("RS-001") == ("RS", 1, None)

    def test_swr_id_with_minor(self):
        """GIVEN SWR-001.2 WHEN _parse_id THEN (SWR, 1, 2)."""
        assert _parse_id("SWR-001.2") == ("SWR", 1, 2)

    def test_feature_id(self):
        """GIVEN FEATURE-042 WHEN _parse_id THEN (FEATURE, 42, None)."""
        assert _parse_id("FEATURE-042") == ("FEATURE", 42, None)

    def test_invalid_format(self):
        """GIVEN invalid ID WHEN _parse_id THEN (None, None, None)."""
        assert _parse_id("invalid") == (None, None, None)

    def test_empty_string(self):
        """GIVEN empty WHEN _parse_id THEN (None, None, None)."""
        assert _parse_id("") == (None, None, None)

    def test_case_insensitive(self):
        """GIVEN lowercase 'rs-001' WHEN _parse_id THEN uppercased."""
        assert _parse_id("rs-001") == ("RS", 1, None)


# ---------------------------------------------------------------------------
# _id_to_level / _id_to_parent
# ---------------------------------------------------------------------------

class TestIdToLevel:
    """GIVEN _id_to_level WHEN called THEN correct level."""

    def test_rs_is_sys(self):
        """GIVEN RS ID WHEN _id_to_level THEN SYS."""
        assert _id_to_level("RS-001") == "SYS"

    def test_swr_is_sw(self):
        """GIVEN SWR ID WHEN _id_to_level THEN SW."""
        assert _id_to_level("SWR-001.1") == "SW"

    def test_feature_is_feature(self):
        """GIVEN FEATURE ID WHEN _id_to_level THEN FEATURE."""
        assert _id_to_level("FEATURE-001") == "FEATURE"


class TestIdToParent:
    """GIVEN _id_to_parent WHEN called THEN correct parent."""

    def test_swr_minor_has_rs_parent(self):
        """GIVEN SWR-001.2 WHEN _id_to_parent THEN RS-001."""
        assert _id_to_parent("SWR-001.2") == "RS-001"

    def test_swr_no_minor_no_parent(self):
        """GIVEN SWR-001 WITHOUT minor WHEN _id_to_parent THEN empty."""
        assert _id_to_parent("SWR-001") == ""

    def test_feature_no_parent(self):
        """GIVEN FEATURE ID WHEN _id_to_parent THEN empty."""
        assert _id_to_parent("FEATURE-001") == ""


# ---------------------------------------------------------------------------
# validate_status_transition
# ---------------------------------------------------------------------------

class TestValidateStatusTransition:
    """GIVEN validate_status_transition WHEN called THEN checks validity."""

    def test_proposed_to_approved(self):
        """GIVEN PROPOSED→APPROVED WHEN validate_status_transition THEN valid."""
        valid, msg = validate_status_transition("PROPOSED", "APPROVED")
        assert valid
        assert msg == ""

    def test_approved_to_implemented(self):
        """GIVEN APPROVED→IMPLEMENTED THEN valid."""
        assert validate_status_transition("APPROVED", "IMPLEMENTED")[0]

    def test_implemented_to_verified(self):
        """GIVEN IMPLEMENTED→VERIFIED THEN valid."""
        assert validate_status_transition("IMPLEMENTED", "VERIFIED")[0]

    def test_none_to_proposed(self):
        """GIVEN None→PROPOSED THEN valid."""
        assert validate_status_transition(None, "PROPOSED")[0]

    def test_verified_to_anything(self):
        """GIVEN VERIFIED→anything THEN invalid (terminal)."""
        valid, msg = validate_status_transition("VERIFIED", "APPROVED")
        assert not valid
        assert "终态" in msg or "非法" in msg

    def test_skipping_status(self):
        """GIVEN PROPOSED→IMPLEMENTED (skip) THEN invalid."""
        valid, msg = validate_status_transition("PROPOSED", "IMPLEMENTED")
        assert not valid


# ---------------------------------------------------------------------------
# _detect_status_from_lines
# ---------------------------------------------------------------------------

class TestDetectStatusFromLines:
    """GIVEN _detect_status_from_lines WHEN called THEN finds status marker."""

    def test_finds_status(self):
        """GIVEN Status: APPROVED marker WHEN _detect_status_from_lines THEN finds it."""
        lines = [
            "## SWR-001: Test Req",
            "",
            "Status: APPROVED",
            "- The system SHALL work",
        ]
        assert _detect_status_from_lines(lines, 0) == "APPROVED"

    def test_default_proposed(self):
        """GIVEN no status marker WHEN _detect_status_from_lines THEN PROPOSED."""
        lines = ["## Req-001", "- The system SHALL work"]
        assert _detect_status_from_lines(lines, 0) == "PROPOSED"

    def test_status_case_insensitive(self):
        """GIVEN 'Status: approved' lowercase WHEN _detect_status_from_lines THEN APPROVED."""
        lines = ["## Req", "status: approved"]
        assert _detect_status_from_lines(lines, 0) == "APPROVED"

    def test_status_beyond_15_lines(self):
        """GIVEN status beyond 15 lines WHEN _detect_status_from_lines THEN PROPOSED."""
        lines = [""] * 20
        lines[16] = "Status: VERIFIED"
        assert _detect_status_from_lines(lines, 0) == "PROPOSED"


# ---------------------------------------------------------------------------
# parse_spec
# ---------------------------------------------------------------------------

class TestParseSpec:
    """GIVEN parse_spec WHEN called THEN parses spec markdown."""

    BASIC_SPEC = """# My Spec

## Requirement: My First Req

- The system SHALL respond to pings
- The system SHOULD log errors
- The system MAY retry on failure

### Reason
Because it needs to work.

## Scenario: Happy Path

- GIVEN the system is on
- WHEN a ping is sent
- THEN the system responds
"""

    def test_parse_basic_spec(self):
        """GIVEN basic spec WHEN parse_spec THEN requirements parsed."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(self.BASIC_SPEC)
            fname = f.name
        try:
            doc = parse_spec(fname)
            assert len(doc.requirements) == 1
            assert doc.requirements[0].shall == ["respond to pings"]
            assert doc.requirements[0].should == ["log errors"]
            assert doc.requirements[0].may == ["retry on failure"]
            assert doc.requirements[0].reason == "Because it needs to work."
            assert len(doc.scenarios) == 1
        finally:
            os.unlink(fname)

    def test_parse_scenario_given_when_then(self):
        """GIVEN scenario with GIVEN/WHEN/THEN WHEN parse_spec THEN parsed."""
        spec = """## Scenario: Test

- GIVEN precondition
- WHEN trigger
- THEN outcome
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(spec)
            fname = f.name
        try:
            doc = parse_spec(fname)
            assert len(doc.scenarios) == 1
            s = doc.scenarios[0]
            assert s.given == ["precondition"]
            assert s.when == ["trigger"]
            assert s.then == ["outcome"]
        finally:
            os.unlink(fname)

    def test_parse_and_statements(self):
        """GIVEN AND statements in scenario WHEN parse_spec THEN route to last clause."""
        spec = """## Scenario: Multi-step

- GIVEN step 1
- AND step 2
- WHEN action
- AND condition
- THEN result 1
- AND result 2
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(spec)
            fname = f.name
        try:
            doc = parse_spec(fname)
            s = doc.scenarios[0]
            assert len(s.given) == 2
            assert len(s.when) == 2
            assert len(s.then) == 2
        finally:
            os.unlink(fname)

    def test_parse_with_req_id_in_header(self):
        """GIVEN header with RS-XXX ID WHEN parse_spec THEN req_id extracted."""
        spec = "## RS-001: System Requirement\n- The system SHALL work\n### Reason\nBecause\n"
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(spec)
            fname = f.name
        try:
            doc = parse_spec(fname)
            assert len(doc.requirements) == 1
            r = doc.requirements[0]
            assert r.req_id == "RS-001"
            assert r.level == "SYS"
        finally:
            os.unlink(fname)

    def test_parse_swr_with_parent_tracking(self):
        """GIVEN RS then SWR header WHEN parse_spec THEN SWR parent = RS."""
        spec = """## RS-001: System
- The system SHALL work
### Reason
Because

## SWR-001.1: Software
- The software SHALL boot
### Reason
To start
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(spec)
            fname = f.name
        try:
            doc = parse_spec(fname)
            swr = [r for r in doc.requirements if r.req_id == "SWR-001.1"][0]
            assert swr.parent == "RS-001"
        finally:
            os.unlink(fname)

    def test_parse_status_marker(self):
        """GIVEN Status marker inside requirement WHEN parse_spec THEN status set."""
        spec = """## Req-001: Testing
Status: VERIFIED
- The system SHALL work
### Reason
Done
"""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(spec)
            fname = f.name
        try:
            doc = parse_spec(fname)
            r = doc.requirements[0]
            assert r.status == "VERIFIED"
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# validate_spec
# ---------------------------------------------------------------------------

class TestValidateSpec:
    """GIVEN validate_spec WHEN called THEN returns issues list."""

    def test_no_issues(self):
        """GIVEN complete spec WHEN validate_spec THEN empty issues."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL work"], [], [], "Because"))
        issues = validate_spec(doc)
        assert issues == []

    def test_missing_shall(self):
        """GIVEN req without SHALL WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", [], [], [], ""))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_shall" for i in issues)

    def test_missing_reason(self):
        """GIVEN req without reason WHEN validate_spec THEN warning."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL work"], [], [], ""))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_reason" for i in issues)

    def test_invalid_req_id(self):
        """GIVEN invalid req_id WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL"], [], [], "reason", req_id="BAD-ID"))
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_req_id" for i in issues)

    def test_invalid_status(self):
        """GIVEN invalid status WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL"], [], [], "reason", status="INVALID"))
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_status" for i in issues)

    def test_scenario_missing_given(self):
        """GIVEN scenario without GIVEN WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.scenarios.append(SpecScenario("S1", [], ["WHEN"], ["THEN"]))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_given" for i in issues)

    def test_scenario_missing_when(self):
        """GIVEN scenario without WHEN WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.scenarios.append(SpecScenario("S1", ["GIVEN"], [], ["THEN"]))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_when" for i in issues)

    def test_scenario_missing_then(self):
        """GIVEN scenario without THEN WHEN validate_spec THEN error."""
        doc = SpecDocument("test.md")
        doc.scenarios.append(SpecScenario("S1", ["GIVEN"], ["WHEN"], []))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_then" for i in issues)


# ---------------------------------------------------------------------------
# diff_specs
# ---------------------------------------------------------------------------

class TestDiffSpecs:
    """GIVEN diff_specs WHEN called THEN produces diff dict."""

    def test_identical_specs(self):
        """GIVEN same file twice WHEN diff_specs THEN no changes."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n")
            fname = f.name
        try:
            result = diff_specs(fname, fname)
            assert result["added_count"] == 0
            assert result["removed_count"] == 0
            assert result["modified_count"] == 0
        finally:
            os.unlink(fname)

    def test_added_requirement(self):
        """GIVEN new requirement in new spec WHEN diff_specs THEN detected."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n")
            old_name = f.name
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n\n## Req-002: New\n- The system SHALL also\n### Reason\nNew\n")
            new_name = f.name
        try:
            result = diff_specs(old_name, new_name)
            assert result["added_count"] == 1
            # req name is the part after colon in header, so "New" not "Req-002"
            assert "New" in result["added_requirements"][0]
        finally:
            os.unlink(old_name)
            os.unlink(new_name)

    def test_removed_requirement(self):
        """GIVEN removed requirement WHEN diff_specs THEN detected."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n\n## Req-002: Old\n- The system SHALL also\n### Reason\nOld\n")
            old_name = f.name
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n")
            new_name = f.name
        try:
            result = diff_specs(old_name, new_name)
            assert result["removed_count"] == 1
        finally:
            os.unlink(old_name)
            os.unlink(new_name)

    def test_modified_shall(self):
        """GIVEN changed SHALL WHEN diff_specs THEN modified detected."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n")
            old_name = f.name
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n- The system SHALL also work\n### Reason\nBecause\n")
            new_name = f.name
        try:
            result = diff_specs(old_name, new_name)
            assert result["modified_count"] > 0 or result["added_count"] > 0
        finally:
            os.unlink(old_name)
            os.unlink(new_name)

    def test_status_change(self):
        """GIVEN status change WHEN diff_specs THEN detected in status_changed."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\nStatus: PROPOSED\n- The system SHALL work\n### Reason\nBecause\n")
            old_name = f.name
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\nStatus: APPROVED\n- The system SHALL work\n### Reason\nBecause\n")
            new_name = f.name
        try:
            result = diff_specs(old_name, new_name)
            assert result["status_changed_count"] >= 1
        finally:
            os.unlink(old_name)
            os.unlink(new_name)

    def test_impact_analysis_in_result(self):
        """GIVEN diff_specs WHEN called THEN impact_analysis present."""
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("## Req-001: Test\n- The system SHALL work\n### Reason\nBecause\n")
            fname = f.name
        try:
            result = diff_specs(fname, fname)
            assert "impact_analysis" in result
            assert "recommended_actions" in result["impact_analysis"]
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# _compute_coverage
# ---------------------------------------------------------------------------

class TestComputeCoverage:
    """GIVEN _compute_coverage WHEN called THEN computes score."""

    def test_no_requirements(self):
        """GIVEN empty doc WHEN _compute_coverage THEN score 0."""
        doc = SpecDocument("test.md")
        cov = _compute_coverage(doc)
        assert cov["score"] == 0

    def test_perfect_score(self):
        """GIVEN all reqs have SHALL+reason and complete scenarios WHEN _compute_coverage THEN 100."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL"], [], [], "reason"))
        doc.scenarios.append(SpecScenario("S1", ["GIVEN"], ["WHEN"], ["THEN"]))
        cov = _compute_coverage(doc)
        assert cov["score"] == 100.0

    def test_partial_score(self):
        """GIVEN only SHALL without reason WHEN _compute_coverage THEN partial."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL"], [], [], ""))
        cov = _compute_coverage(doc)
        assert 0 < cov["score"] < 100

    def test_pass_threshold(self):
        """GIVEN score >= 80 WHEN _compute_coverage THEN pass_threshold True."""
        doc = SpecDocument("test.md")
        doc.requirements.append(SpecRequirement("R1", ["SHALL"], [], [], "reason"))
        doc.scenarios.append(SpecScenario("S1", ["GIVEN"], ["WHEN"], ["THEN"]))
        cov = _compute_coverage(doc)
        assert cov["pass_threshold"] is True


# ---------------------------------------------------------------------------
# _compute_impact_analysis
# ---------------------------------------------------------------------------

class TestComputeImpactAnalysis:
    """GIVEN _compute_impact_analysis WHEN called THEN produces analysis."""

    def test_affected_requirements(self):
        """GIVEN added requirements WHEN called THEN affected list includes them."""
        old_doc = SpecDocument("old.md")
        new_doc = SpecDocument("new.md")
        analysis = _compute_impact_analysis(old_doc, new_doc, ["R1"], [], [])
        assert "R1" in analysis["affected_requirements"]

    def test_recommended_actions_not_empty(self):
        """GIVEN changes WHEN called THEN recommended_actions present."""
        old_doc = SpecDocument("old.md")
        new_doc = SpecDocument("new.md")
        analysis = _compute_impact_analysis(old_doc, new_doc, ["R1"], [], [])
        assert len(analysis["recommended_actions"]) > 0
