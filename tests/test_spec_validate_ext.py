"""Tests for spec/validate.py — OpenSpec parser, validator, diff engine."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from yuleosh.spec.validate import (
    SpecRequirement,
    SpecScenario,
    SpecDocument,
    parse_spec,
    validate_spec,
    diff_specs,
    _compute_coverage,
    _parse_id,
    _id_to_level,
    _id_to_parent,
    validate_status_transition,
    _detect_status_from_lines,
    ALLOWED_STATUSES,
    VALID_STATUS_TRANSITIONS,
)


class TestSpecRequirement:
    """Test SpecRequirement data class."""

    def test_to_dict(self):
        req = SpecRequirement(
            name="RS-001",
            shall=["The system SHALL do X"],
            should=["The system SHOULD do Y"],
            may=["The system MAY do Z"],
            reason="Safety",
            req_id="RS-001",
            level="SYS",
            parent="",
            status="PROPOSED",
        )
        d = req.to_dict()
        assert d["name"] == "RS-001"
        assert d["shall_count"] == 1
        assert d["should_count"] == 1
        assert d["may_count"] == 1
        assert d["level"] == "SYS"
        assert d["status"] == "PROPOSED"


class TestSpecScenario:
    """Test SpecScenario data class."""

    def test_to_dict(self):
        sc = SpecScenario("Login", ["user exists"], ["click login"], ["redirect"])
        d = sc.to_dict()
        assert d["name"] == "Login"
        assert len(d["given"]) == 1


class TestSpecDocument:
    """Test SpecDocument."""

    def test_to_dict(self):
        doc = SpecDocument("/path/to/spec.md")
        doc.requirements.append(SpecRequirement("RS-001", ["SHALL X"], [], [], ""))
        doc.scenarios.append(SpecScenario("S1", ["GIVEN"], ["WHEN"], ["THEN"]))
        d = doc.to_dict()
        assert d["requirement_count"] == 1
        assert d["scenario_count"] == 1
        assert d["total_shall"] == 1
        assert d["requirements"][0]["shall_count"] == 1


class TestParseId:
    """Test ID parsing."""

    def test_valid_id(self):
        assert _parse_id("RS-001") == ("RS", 1, None)
        assert _parse_id("SWR-002.1") == ("SWR", 2, 1)
        assert _parse_id("SCM-REQ-100") == ("SCM-REQ", 100, None)

    def test_invalid_id(self):
        assert _parse_id("") == (None, None, None)
        assert _parse_id("invalid") == (None, None, None)

    def test_table_id(self):
        from yuleosh.spec.validate import TABLE_ID_PATTERN
        m = TABLE_ID_PATTERN.match("KL-SHALL-01")
        assert m is not None
        assert m.group(1) == "KL"
        assert m.group(2) == "01"

        m = TABLE_ID_PATTERN.match("PE-SHALL-NOT-02")
        assert m is not None

    def test_id_to_level(self):
        assert _id_to_level("RS-001") == "SYS"
        assert _id_to_level("SWR-001.1") == "SW"
        assert _id_to_level("FEATURE-01") == "FEATURE"
        assert _id_to_level("SCM-REQ-01") == ""

    def test_id_to_parent(self):
        assert _id_to_parent("SWR-002.1") == "RS-002"
        assert _id_to_parent("SCM-REQ-010.2") == "SCM-REQ-010"
        assert _id_to_parent("RS-001") == ""


class TestStatusValidation:
    """Test status transitions."""

    def test_valid_transitions(self):
        valid, _ = validate_status_transition(None, "PROPOSED")
        assert valid
        valid, _ = validate_status_transition("PROPOSED", "APPROVED")
        assert valid
        valid, _ = validate_status_transition("APPROVED", "IMPLEMENTED")
        assert valid
        valid, _ = validate_status_transition("IMPLEMENTED", "VERIFIED")
        assert valid

    def test_invalid_transition(self):
        valid, msg = validate_status_transition("PROPOSED", "VERIFIED")
        assert valid is False
        assert "状态迁移非法" in msg

    def test_terminal_state(self):
        valid, msg = validate_status_transition("VERIFIED", "APPROVED")
        assert valid is False
        assert "终态" in msg


class TestDetectStatus:
    """Test status detection from lines."""

    def test_detect_status(self):
        lines = ["# Header", "Status: APPROVED", "Some text"]
        status = _detect_status_from_lines(lines, 0)
        assert status == "APPROVED"

    def test_detect_status_default(self):
        lines = ["# Header", "No status here"]
        status = _detect_status_from_lines(lines, 2)
        assert status == "PROPOSED"

    def test_detect_status_invalid(self):
        lines = ["# Header", "Status: INVALID"]
        status = _detect_status_from_lines(lines, 0)
        assert status == "INVALID"


class TestParseSpec:
    """Test spec parsing from markdown."""

    def test_parse_empty_spec(self, tmp_path):
        """Empty spec returns document with no requirements."""
        f = tmp_path / "empty.md"
        f.write_text("# Empty Spec")
        doc = parse_spec(str(f))
        assert len(doc.requirements) == 0
        assert len(doc.scenarios) == 0

    def test_parse_requirement_basic(self, tmp_path):
        """Basic requirement parsing."""
        f = tmp_path / "basic.md"
        f.write_text("""# Test Spec

## RS-001: Login System

- The system SHALL authenticate users
- The system SHALL validate passwords

### Reason

Security requirement

## RS-002: Logout

- The system SHALL end sessions

### Reason

Cleanup
""")
        doc = parse_spec(str(f))
        assert len(doc.requirements) == 2
        assert doc.requirements[0].req_id == "RS-001"
        assert len(doc.requirements[0].shall) == 2
        assert doc.requirements[0].reason == "Security requirement"

    def test_parse_scenario(self, tmp_path):
        """Scenario parsing."""
        f = tmp_path / "scenario.md"
        f.write_text("""# Test

## Scenario: User Login

- GIVEN user exists
- WHEN user enters valid credentials
- THEN user is logged in
""")
        doc = parse_spec(str(f))
        assert len(doc.scenarios) == 1
        assert doc.scenarios[0].name == "User Login"
        assert len(doc.scenarios[0].given) == 1
        assert len(doc.scenarios[0].when) == 1

    def test_parse_and_statements(self, tmp_path):
        """AND statements route to correct clause."""
        f = tmp_path / "and.md"
        f.write_text("""# Test

## Scenario: Complex Flow

- GIVEN user is registered
- AND user is verified
- WHEN user submits form
- AND form is valid
- THEN submission is saved
- AND confirmation is sent
""")
        doc = parse_spec(str(f))
        assert len(doc.scenarios) == 1
        sc = doc.scenarios[0]
        assert len(sc.given) == 2
        assert len(sc.when) == 2
        assert len(sc.then) == 2

    def test_parse_should_may_statements(self, tmp_path):
        """SHOULD and MAY statements."""
        f = tmp_path / "should_may.md"
        f.write_text("""# Test

## RS-001: Performance

- The system SHOULD respond within 2s
- The system MAY cache results

### Reason

Performance
""")
        doc = parse_spec(str(f))
        req = doc.requirements[0]
        assert len(req.should) == 1
        assert len(req.may) == 1
        assert len(req.shall) == 0

    def test_parse_table_format(self, tmp_path):
        """Table format SHALL requirements — section header matches ID pattern."""
        f = tmp_path / "table.md"
        f.write_text("""# Test Spec

## KEY-001: Key Features

### Reason

Required

## 其它要求

| ID | Description | Priority |
|---|---|---|
| KL-SHALL-01 | System shall initialize | P0 |
| KL-SHALL-02 | System shall monitor | P1 |
""")
        doc = parse_spec(str(f))
        # Table rows without a preceding requirement match the table parser
        # as long as columns are | delimited with ID/Description headers
        assert len(doc.requirements) >= 1  # KEY-001 requirement

    def test_parse_status_marker(self, tmp_path):
        """Status marker in requirement."""
        f = tmp_path / "status.md"
        f.write_text("""# Test

## RS-001: Feature

Status: APPROVED

- The system SHALL do X

### Reason

Safety
""")
        doc = parse_spec(str(f))
        assert doc.requirements[0].status == "APPROVED"

    def test_parse_hierarchical_swr(self, tmp_path):
        """SWR requirements with parent tracking."""
        f = tmp_path / "hier.md"
        f.write_text("""# Test

## RS-001: System

- The system SHALL start

### Reason

Required

## SWR-001.1: Software

- The software SHALL boot

### Reason

Required
""")
        doc = parse_spec(str(f))
        assert len(doc.requirements) == 2
        swr_req = doc.requirements[1]
        assert swr_req.level == "SW"
        assert swr_req.parent == "RS-001"


class TestValidateSpec:
    """Test spec validation."""

    def test_validate_clean(self, tmp_path):
        """Clean spec has no issues."""
        f = tmp_path / "clean.md"
        f.write_text("""# Spec

## RS-001: Feature

- The system SHALL work

### Reason

Needed
""")
        doc = parse_spec(str(f))
        issues = validate_spec(doc)
        assert len(issues) == 0

    def test_validate_missing_shall(self, tmp_path):
        """Requirement without SHALL creates error."""
        doc = SpecDocument("/f")
        doc.requirements.append(SpecRequirement("RS-001", [], [], [], "", "RS-001"))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_shall" for i in issues)

    def test_validate_missing_reason(self, tmp_path):
        """Requirement without Reason creates warning."""
        doc = SpecDocument("/f")
        doc.requirements.append(
            SpecRequirement("RS-001", ["SHALL X"], [], [], "", "RS-001")
        )
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_reason" for i in issues)

    def test_validate_invalid_status(self):
        """Invalid status creates error."""
        doc = SpecDocument("/f")
        req = SpecRequirement("RS-001", ["SHALL X"], [], [], "", "RS-001", status="INVALID")
        doc.requirements.append(req)
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_status" for i in issues)

    def test_validate_invalid_req_id(self):
        """Invalid req_id format creates error."""
        doc = SpecDocument("/f")
        req = SpecRequirement("RS-001", ["SHALL X"], [], [], "", "bad-id")
        doc.requirements.append(req)
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_req_id" for i in issues)

    def test_validate_missing_scenario_given(self):
        """Scenario without GIVEN creates error."""
        doc = SpecDocument("/f")
        doc.scenarios.append(SpecScenario("S1", [], ["WHEN X"], ["THEN Y"]))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_given" for i in issues)

    def test_validate_missing_scenario_when(self):
        doc = SpecDocument("/f")
        doc.scenarios.append(SpecScenario("S1", ["GIVEN X"], [], ["THEN Y"]))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_when" for i in issues)

    def test_validate_missing_scenario_then(self):
        doc = SpecDocument("/f")
        doc.scenarios.append(SpecScenario("S1", ["GIVEN X"], ["WHEN Y"], []))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_then" for i in issues)


class TestDiffSpecs:
    """Test spec diffing."""

    def test_diff_identical(self, tmp_path):
        """Identical specs produce empty diff."""
        content = """# Spec

## RS-001: Feature

- The system SHALL work

### Reason

Need
"""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text(content)
        new.write_text(content)

        delta = diff_specs(str(old), str(new))
        assert delta["total_changes"] == 0

    def test_diff_added_removed(self, tmp_path):
        """Added and removed requirements."""
        old_content = """# Spec

## RS-001: Old

- The system SHALL do old

### Reason

R1

## RS-002: Keep

- The system SHALL stay

### Reason

R2
"""
        new_content = """# Spec

## RS-002: Keep

- The system SHALL stay

### Reason

R2

## RS-003: New

- The system SHALL do new

### Reason

R3
"""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text(old_content)
        new.write_text(new_content)

        delta = diff_specs(str(old), str(new))
        assert delta["removed_count"] == 1
        assert delta["added_count"] == 1

    def test_diff_modified(self, tmp_path):
        """Modified SHALL statements."""
        old_content = """# Spec

## RS-001: Feature

- The system SHALL do old

### Reason

R1
"""
        new_content = """# Spec

## RS-001: Feature

- The system SHALL do new

### Reason

R1
"""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text(old_content)
        new.write_text(new_content)

        delta = diff_specs(str(old), str(new))
        assert delta["modified_count"] >= 1

    def test_diff_status_changed(self, tmp_path):
        """Status changes detected."""
        old_content = """# Spec

## RS-001: Feature

Status: PROPOSED

- The system SHALL work

### Reason

Need
"""
        new_content = """# Spec

## RS-001: Feature

Status: APPROVED

- The system SHALL work

### Reason

Need
"""
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text(old_content)
        new.write_text(new_content)

        delta = diff_specs(str(old), str(new))
        assert delta["status_changed_count"] >= 1


class TestComputeCoverage:
    """Test coverage computation."""

    def test_no_requirements(self):
        doc = SpecDocument("/f")
        cov = _compute_coverage(doc)
        assert cov["score"] == 0

    def test_full_coverage(self, tmp_path):
        f = tmp_path / "full.md"
        f.write_text("""# Spec

## RS-001: Feature

- The system SHALL work

### Reason

Yes

## Scenario: Flow

- GIVEN setup
- WHEN action
- THEN result
""")
        doc = parse_spec(str(f))
        cov = _compute_coverage(doc)
        assert cov["score"] >= 80
        assert cov["pass_threshold"] is True


class TestMain:
    """Test CLI entry points."""

    def test_validate_main(self):
        with patch("yuleosh.spec.validate.sys.argv", ["validate.py"]):
            with pytest.raises(SystemExit):
                from yuleosh.spec.validate import main as vmain
                vmain()

    def test_validate_main_with_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("""# Spec

## RS-001: Feature

- The system SHALL work

### Reason

Needed
""")
        with patch("yuleosh.spec.validate.sys.argv", ["validate.py", str(f)]):
            from yuleosh.spec.validate import main as vmain
            vmain()

    def test_validate_main_json(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("""# Spec

## RS-001: Feature

- The system SHALL work

### Reason

Needed
""")
        with patch("yuleosh.spec.validate.sys.argv", ["validate.py", str(f), "--json"]):
            from yuleosh.spec.validate import main as vmain
            vmain()

    def test_validate_main_error(self, tmp_path):
        """Spec with invalid status exits with error code."""
        f = tmp_path / "test.md"
        f.write_text("""# Spec

## RS-001: Feature

Status: BADSTATUS

- The system SHALL work
""")
        with patch("yuleosh.spec.validate.sys.argv", ["validate.py", str(f), "--json"]):
            from yuleosh.spec.validate import main as vmain
            with pytest.raises(SystemExit):
                vmain()
