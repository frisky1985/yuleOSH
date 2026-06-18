# ASPICE 3.1 Compliance Check Report

> Generated: 2026-06-16T09:46:41.324618
> Project: `.`
> Standard: ASPICE v3.1

## Summary

| Metric | Count |
|:-------|------:|
| Total Base Practices | 18 |
| ✅ Passed | 11 |
| ⚠️  Partial | 3 |
| ❌ Failed | 4 |

## SWE.1: Software Requirements Analysis

Transform system requirements into a structured set of software requirements.

### SWE.1.BP1: Specify software requirements

**Status**: ⚠️ (Checks: 2/3 passed)

  ❌ Missing evidence: Software Requirements Specification (SRS)
  ❌ Missing evidence: Alternative requirements document
  ❌ Check: Each requirement has a unique identifier (REQ-xxx)
  ✅ Check: Each requirement contains SHALL statements
  ✅ Check: Requirements are traced to system requirements

### SWE.1.BP2: Structure software requirements

**Status**: ✅ (Checks: 2/2 passed)

  ✅ Evidence found: Structured specs directory
  ✅ Check: Requirements are organized by functional area (source code present)
  ✅ Check: Requirements have defined attributes (priority, status)

### SWE.1.BP3: Evaluate impact of requirements

**Status**: ❌ (Checks: 0/2 passed)

  ❌ Missing evidence: Impact analysis document
  ❌ Check: Changes to requirements trigger impact analysis
  ❌ Check: Impact analysis covers schedule, resources, and risks

## SWE.2: Software Architectural Design

Establish a software architectural design that identifies components,
their interfaces, and data flow.

### SWE.2.BP1: Develop software architecture

**Status**: ❌ (Checks: 0/2 passed)

  ❌ Missing evidence: Software architecture document
  ❌ Missing evidence: Alternative architecture document
  ❌ Check: Architecture covers all software requirements
  ❌ Check: Architecture defines component boundaries and interfaces

### SWE.2.BP2: Define interfaces

**Status**: ❌ (Checks: 0/2 passed)

  ❌ Missing evidence: Header files defining interfaces
  ❌ Check: All external interfaces are defined
  ❌ Check: Interface specifications include data types and range

### SWE.2.BP3: Verify architecture

**Status**: ❌ (Checks: 0/2 passed)

  ❌ Missing evidence: Architecture review record
  ❌ Check: Architecture review is conducted and documented
  ❌ Check: Review findings are tracked to closure

## SWE.3: Software Detailed Design and Unit Construction

Develop a detailed design for each software component and construct units.

### SWE.3.BP1: Develop detailed design

**Status**: ✅ (Checks: 3/3 passed)

  ✅ Evidence found: Source code directory
  ✅ Check: Source code follows defined coding standards
  ✅ Check: Each function has a clear, single responsibility (source code present)
  ✅ Check: Code complexity is managed (functions < 50 lines) (source code present)

### SWE.3.BP2: Define unit test cases

**Status**: ✅ (Checks: 3/3 passed)

  ✅ Evidence found: Unit test directory
  ✅ Check: Unit tests exist for each software unit
  ✅ Check: Test cases cover normal, boundary, and error conditions
  ✅ Check: Test cases are traceable to requirements

### SWE.3.BP3: Verify detailed design

**Status**: ⚠️ (Checks: 1/2 passed)

  ❌ Missing evidence: Design review record
  ❌ Check: Design review is conducted per component
  ✅ Check: Review covers correctness, consistency, and testability

## SWE.4: Software Unit Verification

Verify software units against the detailed design and requirements.

### SWE.4.BP1: Perform unit verification

**Status**: ✅ (Checks: 3/3 passed)

  ✅ Evidence found: Unit test results
  ✅ Evidence found: CI test execution records
  ✅ Check: All unit tests pass (100% pass rate)
  ✅ Check: Statement coverage ≥ 80%
  ✅ Check: Branch/condition coverage ≥ 70%

### SWE.4.BP2: Establish bidirectional traceability

**Status**: ✅ (Checks: 2/2 passed)

  ✅ Evidence found: Traceability matrix
  ✅ Check: Each requirement is traced to unit tests
  ✅ Check: Traceability matrix is maintained and current

### SWE.4.BP3: Evaluate unit verification results

**Status**: ✅ (Checks: 2/2 passed)

  ✅ Evidence found: Evidence collection
  ✅ Check: Failed tests are analyzed and documented
  ✅ Check: Regression test strategy is defined

## SWE.5: Software Integration and Integration Test

Integrate software units and verify the integrated software against
the architecture and requirements.

### SWE.5.BP1: Develop integration strategy

**Status**: ⚠️ (Checks: 1/2 passed)

  ❌ Missing evidence: Integration strategy document
  ✅ Check: Integration sequence is defined and justified
  ❌ Check: Stubs/drivers are identified

### SWE.5.BP2: Integrate software units

**Status**: ✅ (Checks: 2/2 passed)

  ✅ Evidence found: CI integration records
  ✅ Check: Integration builds succeed
  ✅ Check: Integration follows the defined strategy

### SWE.5.BP3: Perform integration tests

**Status**: ✅ (Checks: 3/3 passed)

  ❌ Missing evidence: Integration test directory
  ✅ Evidence found: Integration test results
  ✅ Check: Integration tests cover component interfaces
  ✅ Check: Integration tests verify data flow between components
  ✅ Check: All integration tests pass

## SWE.6: Software Qualification Test

Test the complete software against software requirements in the target
environment or a simulated environment.

### SWE.6.BP1: Develop qualification test strategy

**Status**: ✅ (Checks: 2/2 passed)

  ❌ Missing evidence: Qualification test strategy
  ✅ Check: Qualification test scope covers all requirements
  ✅ Check: Acceptance criteria are defined for each requirement

### SWE.6.BP2: Perform qualification tests

**Status**: ✅ (Checks: 3/3 passed)

  ✅ Evidence found: Qualification test results
  ❌ Missing evidence: SIL/HIL test results
  ✅ Check: All qualification tests pass
  ✅ Check: Tests are executed in target or equivalent environment
  ✅ Check: Resulting evidence is archived

### SWE.6.BP3: Establish traceability

**Status**: ✅ (Checks: 2/2 passed)

  ✅ Evidence found: Acceptance matrix
  ✅ Evidence found: Requirement coverage report
  ✅ Check: Qualification tests are traceable to requirements
  ✅ Check: Coverage gaps are identified and documented

---
*Report generated by yuleOSH Compliance Checker*