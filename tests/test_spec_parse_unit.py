"""Unit tests for yuleosh.spec.validate parse_spec — pure Python, no external deps."""

# @tests src/yuleosh/spec/validate.py

import tempfile
import os

import pytest

from yuleosh.spec.validate import (
    parse_spec,
    validate_spec,
    diff_specs,
    SpecRequirement,
    SpecScenario,
    SpecDocument,
)


SIMPLE_SPEC = """# Test Spec

> **Version**: 1.0.0

## RS-001: System Must Work

- The system SHALL operate correctly.
- The system SHOULD be fast.
- The system MAY be configurable.

Status: APPROVED

## RS-002: Security

- The system SHALL enforce access control.
- The system SHALL log all access attempts.
- The system SHOULD support RBAC.

Status: PROPOSED

### Reason

Security is critical for compliance.

### Acceptance

Test with penetration testing.
"""

SCENARIO_SPEC = """# Scenario Spec

## Requirement

## RS-001: Core Feature

- The system SHALL process requests.

Status: APPROVED

## Scenario: Happy Path

- GIVEN system is ready
- WHEN user sends a request
- THEN system processes it
- AND returns a response

## Scenario: Error Path

- GIVEN system is ready
- WHEN user sends invalid request
- THEN system returns error

### Reason

Edge case handling.
"""

TABLE_SPEC = """# Table Spec

## Requirements

| ID | Description |
|---|---|
| KL-SHALL-01 | SHALL initialize at boot |
| PE-SHALL-NOT-01 | SHALL NOT access null pointer |
| DCM-REQ-01 | SHALL support diagnostics |
"""

MINIMAL_SPEC = """# Minimal

## RS-001: Bare Minimum

Status: PROPOSED

### Reason

None.
"""

BULLET_SPEC = """# Bullet Spec

## BSW Services

- The MCU SHALL initialize in < 100ms.
- The system SHALL support CAN bus.
"""


class TestParseSpecSimple:
    def test_parse_simple_spec(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(SIMPLE_SPEC)
            doc = parse_spec(path)
            assert len(doc.requirements) == 2
            assert doc.requirements[0].name == "System Must Work"
            assert doc.requirements[0].req_id == "RS-001"
            assert doc.requirements[0].level == "SYS"
            assert len(doc.requirements[0].shall) == 1
            assert "operate correctly" in doc.requirements[0].shall[0]
            assert doc.requirements[0].status == "APPROVED"

    def test_parse_second_requirement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(SIMPLE_SPEC)
            doc = parse_spec(path)
            r2 = doc.requirements[1]
            assert r2.name == "Security"
            assert r2.req_id == "RS-002"
            assert len(r2.shall) == 2
            assert len(r2.should) == 1
            assert r2.reason == "Security is critical for compliance."

    def test_parse_no_file(self):
        with pytest.raises(FileNotFoundError):
            parse_spec("/nonexistent/nope.md")


class TestParseSpecScenarios:
    def test_parse_scenarios(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(SCENARIO_SPEC)
            doc = parse_spec(path)
            assert len(doc.scenarios) == 2
            assert doc.scenarios[0].name == "Happy Path"
            assert doc.scenarios[0].given == ["system is ready"]
            assert doc.scenarios[0].when == ["user sends a request"]
            assert doc.scenarios[0].then == ["system processes it", "returns a response"]
            assert doc.scenarios[1].name == "Error Path"

    def test_validates_scenario_completeness(self):
        # Both scenarios have GIVEN/WHEN/THEN, so no scenario issues expected
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(SCENARIO_SPEC)
            doc = parse_spec(path)
            assert len(doc.scenarios) == 2
            assert doc.scenarios[1].name == "Error Path"
            # 'system returns error' is the THEN statement
            assert "returns error" in doc.scenarios[1].then[0]

    def test_then_with_shall_not_captured_as_requirement(self):
        """Regression (v3.12.0): 'THEN the driver SHALL ...' lines inside a
        scenario must stay in the scenario — the standalone-bullet SHALL
        fallback must not steal them into requirements."""
        spec = """# Spec

## Requirements

- The system SHALL provide a UART driver.

## Scenario: UART init

- GIVEN a valid channel
- WHEN the driver initializes
- THEN the driver SHALL return success
- AND the channel SHALL be ready
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(spec)
            doc = parse_spec(path)
            assert len(doc.requirements) == 1, (
                f"Expected 1 requirement, got {len(doc.requirements)}"
            )
            assert len(doc.scenarios) == 1
            sc = doc.scenarios[0]
            assert sc.then == ["the driver SHALL return success",
                               "the channel SHALL be ready"], sc.then


class TestParseSpecTableFormat:
    def test_parse_table_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(TABLE_SPEC)
            doc = parse_spec(path)
            # At minimum, table rows with -SHALL- ID should be picked up
            # Remove potential 'empty string' IDs from consideratio
            reqs_with_shall = [r for r in doc.requirements if r.req_id and "-SHALL" in r.req_id.upper()]
            assert len(reqs_with_shall) >= 2, f"Expected >=2 SHALL reqs, got {len(reqs_with_shall)}: {[(r.req_id, r.name) for r in doc.requirements]}"


class TestParseSpecMinimal:
    def test_minimal_no_shall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(MINIMAL_SPEC)
            doc = parse_spec(path)
            assert len(doc.requirements) == 1
            assert doc.requirements[0].shall == []
            issues = validate_spec(doc)
            missing_shall = [i for i in issues if i["type"] == "missing_shall"]
            assert len(missing_shall) == 1


class TestParseSpecBulletFormat:
    def test_bullet_shall(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(BULLET_SPEC)
            doc = parse_spec(path)
            assert len(doc.requirements) >= 2
            # Both are standalone SHALLs in bullet format
            assert any("initialize" in r.shall[0] if r.shall else False for r in doc.requirements)


# ── Diff tests ─────────────────────────────────────────────────────────────


class TestDiffSpecs:
    def test_diff_add_remove(self):
        old_spec = "# Old\n\n## RS-001: A\n\n- The system SHALL do X.\n"
        new_spec = "# New\n\n## RS-001: A\n\n- The system SHALL do X.\n\n## RS-002: B\n\n- The system SHALL do Y.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old.md")
            new_path = os.path.join(tmpdir, "new.md")
            with open(old_path, "w") as f:
                f.write(old_spec)
            with open(new_path, "w") as f:
                f.write(new_spec)
            delta = diff_specs(old_path, new_path)
            assert delta["added_count"] == 1
            assert delta["removed_count"] == 0
            assert "RS-002" in delta["added_requirements"][0] or "B" in delta["added_requirements"][0]

    def test_diff_remove(self):
        old_spec = "# Old\n\n## RS-001: A\n\n- The system SHALL do X.\n\n## RS-002: B\n\n- The system SHALL do Y.\n"
        new_spec = "# New\n\n## RS-001: A\n\n- The system SHALL do X.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old.md")
            new_path = os.path.join(tmpdir, "new.md")
            with open(old_path, "w") as f:
                f.write(old_spec)
            with open(new_path, "w") as f:
                f.write(new_spec)
            delta = diff_specs(old_path, new_path)
            assert delta["added_count"] == 0
            assert delta["removed_count"] >= 1

    def test_diff_modified_shall(self):
        old_spec = "# Old\n\n## RS-001: A\n\n- The system SHALL do X.\n"
        new_spec = "# New\n\n## RS-001: A\n\n- The system SHALL do Y.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old.md")
            new_path = os.path.join(tmpdir, "new.md")
            with open(old_path, "w") as f:
                f.write(old_spec)
            with open(new_path, "w") as f:
                f.write(new_spec)
            delta = diff_specs(old_path, new_path)
            assert delta["modified_count"] == 1

    def test_diff_unchanged(self):
        spec = "# Same\n\n## RS-001: A\n\n- The system SHALL do X.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = os.path.join(tmpdir, "a.md")
            path2 = os.path.join(tmpdir, "b.md")
            with open(path1, "w") as f:
                f.write(spec)
            with open(path2, "w") as f:
                f.write(spec)
            delta = diff_specs(path1, path2)
            assert delta["total_changes"] == 0

    def test_diff_has_impact_analysis(self):
        spec = "# Test\n\n## RS-001: Pipeline\n\n- The system SHALL run pipelines.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "spec.md")
            with open(path, "w") as f:
                f.write(spec)
            delta = diff_specs(path, path)
            assert "impact_analysis" in delta
            assert isinstance(delta["impact_analysis"], dict)


class TestValidateSpec:
    def test_validates_missing_shall(self):
        doc = SpecDocument("/tmp/t.md")
        doc.requirements.append(SpecRequirement("R1", shall=[], should=[], may=[], reason=""))
        issues = validate_spec(doc)
        assert any(i["type"] == "missing_shall" for i in issues)
        assert any(i["type"] == "missing_reason" for i in issues)

    def test_validates_invalid_status(self):
        doc = SpecDocument("/tmp/t.md")
        doc.requirements.append(
            SpecRequirement("R1", shall=["do X"], should=[], may=[], reason="r", status="INVALID")
        )
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_status" for i in issues)

    def test_validates_invalid_req_id(self):
        doc = SpecDocument("/tmp/t.md")
        doc.requirements.append(
            SpecRequirement("R1", shall=["do X"], should=[], may=[], reason="r", req_id="BAD-ID-!")
        )
        issues = validate_spec(doc)
        assert any(i["type"] == "invalid_req_id" for i in issues)

    def test_valid_requirement_passes(self):
        doc = SpecDocument("/tmp/t.md")
        doc.requirements.append(
            SpecRequirement("R1", shall=["do X"], should=[], may=[], reason="valid reason",
                            req_id="RS-001", status="APPROVED")
        )
        issues = validate_spec(doc)
        assert not any(i for i in issues if i["item"] == "R1")
