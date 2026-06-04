"""Extended tests for spec engine - CLI and edge cases."""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "spec"))

from validate import parse_spec, validate_spec, diff_specs, SpecDocument, _compute_coverage


def test_diff_same_spec():
    """Test diffing a spec against itself produces no changes."""
    spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "spec.md")
    delta = diff_specs(spec_path, spec_path)
    assert delta["total_changes"] == 0, "Same file should have no changes"


def test_parse_minimal_spec():
    """Test parsing a minimal spec."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: Test Req
- The system SHALL do something

#### Reason
Testing

## Scenario: Test scenario
- GIVEN condition
- WHEN action
- THEN result
""")
    temp.close()
    doc = parse_spec(temp.name)
    assert len(doc.requirements) == 1
    assert doc.requirements[0].name == "Test Req"
    assert len(doc.requirements[0].shall) == 1
    assert len(doc.scenarios) == 1
    os.unlink(temp.name)


def test_parse_multi_req():
    """Test parsing multiple requirements."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: First
- The system SHALL do a
- The system SHALL do b

#### Reason
First reason

## Requirement: Second
- The system SHALL do c
- The system MAY do d

#### Reason
Second reason
""")
    temp.close()
    doc = parse_spec(temp.name)
    assert len(doc.requirements) == 2
    assert doc.requirements[0].name == "First"
    assert doc.requirements[1].name == "Second"
    assert len(doc.requirements[0].shall) == 2
    assert len(doc.requirements[1].may) == 1
    os.unlink(temp.name)


def test_diff_added():
    """Test diff detects added requirements."""
    old = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    old.write("""## Requirement: Existing
- The system SHALL stay
""")
    old.close()
    
    new = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    new.write("""## Requirement: Existing
- The system SHALL stay

## Requirement: New
- The system SHALL appear
""")
    new.close()
    
    delta = diff_specs(old.name, new.name)
    assert "New" in delta["added_requirements"]
    assert delta["added_count"] == 1
    os.unlink(old.name)
    os.unlink(new.name)


def test_validate_empty():
    """Test validation catches missing SHALL."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("## Requirement: Empty\n")
    temp.close()
    doc = parse_spec(temp.name)
    issues = validate_spec(doc)
    assert any(i["type"] == "missing_shall" for i in issues)
    os.unlink(temp.name)


def test_incomplete_scenario():
    """Test validation catches incomplete scenarios."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: Test
- The system SHALL work

#### Reason
Testing

## Scenario: Incomplete
- GIVEN precondition
""")
    temp.close()
    doc = parse_spec(temp.name)
    issues = validate_spec(doc)
    assert any(i["type"] == "missing_when" for i in issues)
    os.unlink(temp.name)


def test_coverage_calculation():
    """Test coverage calculation."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: Complete
- The system SHALL work
- The system SHALL also work

#### Reason
Testing

## Scenario: OK
- GIVEN a
- WHEN b
- THEN c
""")
    temp.close()
    doc = parse_spec(temp.name)
    cov = _compute_coverage(doc)
    assert cov["score"] == 100.0
    assert cov["pass_threshold"] == True
    os.unlink(temp.name)


def test_spec_should_may():
    """Test parsing SHOULD and MAY statements."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: Optional
- The system SHOULD try
- The system MAY optional
- The system SHALL always

#### Reason
Testing
""")
    temp.close()
    doc = parse_spec(temp.name)
    req = doc.requirements[0]
    assert len(req.should) == 1
    assert len(req.may) == 1
    assert len(req.shall) == 1
    os.unlink(temp.name)


def test_and_statements():
    """Test AND routing to appropriate clause."""
    temp = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    temp.write("""## Requirement: Test
- The system SHALL work

#### Reason
Testing

## Scenario: WithAnd
- GIVEN condition A
- AND condition B
- WHEN action
- THEN result X
- AND result Y
""")
    temp.close()
    doc = parse_spec(temp.name)
    scenario = doc.scenarios[0]
    assert len(scenario.given) == 2, f"Expected 2 given, got {scenario.given}"
    assert len(scenario.then) == 2, f"Expected 2 then, got {scenario.then}"
    os.unlink(temp.name)
