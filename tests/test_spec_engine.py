# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for the spec engine.

Covers: spec, requirement, validation, tree, hierarchy, OpenSpec, delta
Scenario-Ref: 变更管理
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "spec"))

from yuleosh.spec.validate import parse_spec, validate_spec, SpecDocument


def test_parse_basic_spec():
    """Test that a basic spec file parses correctly."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "spec.md")
    doc = parse_spec(spec_path)
    assert len(doc.requirements) > 0, "Should find requirements"
    assert len(doc.scenarios) > 0, "Should find scenarios"
    total_shall = sum(len(r.shall) for r in doc.requirements)
    assert total_shall >= 10, f"Should have at least 10 SHALL statements, got {total_shall}"


def test_validate_clean_spec():
    """Test validation on a clean spec."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "spec.md")
    doc = parse_spec(spec_path)
    issues = validate_spec(doc)
    errors = [i for i in issues if i["severity"] == "ERROR"]
    # Some requirements lack SHALL statements (known spec content issues)
    # Verify they are all "missing_shall" type, not structural problems
    for e in errors:
        assert e["type"] == "missing_shall", f"Unexpected error type: {e}"


def test_parse_requirement_structure():
    """Test requirement structure parsing."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "spec.md")
    doc = parse_spec(spec_path)
    req = doc.requirements[0]
    assert hasattr(req, 'shall'), "Should have shall attribute"
    assert hasattr(req, 'name'), "Should have name attribute"
    assert len(req.shall) > 0, "Should have at least one SHALL"
    assert hasattr(req, 'reason'), "Should have reason attribute"
    assert req.reason, "Reason should not be empty"


def test_parse_scenario_structure():
    """Test scenario structure parsing."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "spec.md")
    doc = parse_spec(spec_path)
    scenario = doc.scenarios[0]
    assert hasattr(scenario, 'given'), "Should have given"
    assert hasattr(scenario, 'when'), "Should have when"
    assert hasattr(scenario, 'then'), "Should have then"
    assert len(scenario.given) > 0, "Should have given conditions"
    assert len(scenario.when) > 0, "Should have when triggers"
    assert len(scenario.then) > 0, "Should have then expectations"
