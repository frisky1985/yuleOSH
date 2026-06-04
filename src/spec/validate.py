#!/usr/bin/env python3
"""
OSH Spec Engine — OpenSpec parser, validator, and diff engine.

Supports RFC 2119: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN scenarios.
Outputs structured JSON for pipeline consumption.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional


class SpecRequirement:
    def __init__(self, name: str, shall: list[str], should: list[str], may: list[str], reason: str):
        self.name = name
        self.shall = shall
        self.should = should
        self.may = may
        self.reason = reason

    def to_dict(self):
        return {
            "name": self.name,
            "shall": self.shall,
            "should": self.should,
            "may": self.may,
            "reason": self.reason,
            "shall_count": len(self.shall),
            "should_count": len(self.should),
            "may_count": len(self.may),
        }


class SpecScenario:
    def __init__(self, name: str, given: list[str], when: list[str], then: list[str]):
        self.name = name
        self.given = given
        self.when = when
        self.then = then

    def to_dict(self):
        return {
            "name": self.name,
            "given": self.given,
            "when": self.when,
            "then": self.then,
        }


class SpecDocument:
    def __init__(self, path: str):
        self.path = path
        self.requirements: list[SpecRequirement] = []
        self.scenarios: list[SpecScenario] = []

    def to_dict(self):
        return {
            "path": self.path,
            "requirements": [r.to_dict() for r in self.requirements],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "requirement_count": len(self.requirements),
            "scenario_count": len(self.scenarios),
            "total_shall": sum(r.shall_count for r in self.requirements),
        }


def parse_spec(filepath: str) -> SpecDocument:
    """Parse an OpenSpec markdown file into structured data."""
    doc = SpecDocument(filepath)
    text = Path(filepath).read_text(encoding="utf-8")
    lines = text.split("\n")

    current_req: Optional[SpecRequirement] = None
    current_scenario: Optional[SpecScenario] = None
    current_section: Optional[str] = None  # "req", "scenario", "intro"

    req_pattern = re.compile(r"^#{2,4}\s+(?:Requirement|Req-\w+):?\s*(.+)$", re.IGNORECASE)
    scenario_pattern = re.compile(r"^#{2,4}\s+Scenario:\s*(.+)$", re.IGNORECASE)
    reason_pattern = re.compile(r"^#{2,4}\s+Reason\s*$", re.IGNORECASE)
    acceptance_pattern = re.compile(r"^#{2,4}\s+(?:Acceptance|验收)", re.IGNORECASE)

    shall_pattern = re.compile(r"^\s*-\s*The\s+system\s+SHALL\s+(.+)$", re.IGNORECASE)
    should_pattern = re.compile(r"^\s*-\s*The\s+system\s+SHOULD\s+(.+)$", re.IGNORECASE)
    may_pattern = re.compile(r"^\s*-\s*The\s+system\s+MAY\s+(.+)$", re.IGNORECASE)
    given_pattern = re.compile(r"^\s*-\s*GIVEN\s+(.+)$", re.IGNORECASE)
    when_pattern = re.compile(r"^\s*-\s*WHEN\s+(.+)$", re.IGNORECASE)
    then_pattern = re.compile(r"^\s*-\s*THEN\s+(.+)$", re.IGNORECASE)
    and_pattern = re.compile(r"^\s*-\s*AND\s+(.+)$", re.IGNORECASE)

    for line in lines:
        stripped = line.strip()

        # Detect section header
        req_match = req_pattern.match(stripped)
        if req_match:
            if current_req:
                doc.requirements.append(current_req)
            current_req = SpecRequirement(req_match.group(1), [], [], [], "")
            current_section = "req"
            continue

        scenario_match = scenario_pattern.match(stripped)
        if scenario_match:
            if current_scenario:
                doc.scenarios.append(current_scenario)
            current_scenario = SpecScenario(scenario_match.group(1), [], [], [])
            current_section = "scenario"
            continue

        if reason_pattern.match(stripped):
            current_section = "reason"
            continue

        if acceptance_pattern.match(stripped):
            current_section = "acceptance"
            continue

        # Parse requirement items
        if current_section == "req" and current_req:
            shall_m = shall_pattern.match(stripped)
            if shall_m:
                current_req.shall.append(shall_m.group(1).strip())
                continue
            should_m = should_pattern.match(stripped)
            if should_m:
                current_req.should.append(should_m.group(1).strip())
                continue
            may_m = may_pattern.match(stripped)
            if may_m:
                current_req.may.append(may_m.group(1).strip())
                continue

        # Parse reason
        if current_section == "reason" and current_req and stripped:
            if not stripped.startswith("#"):
                current_req.reason += (" " if current_req.reason else "") + stripped

        # Parse scenario items
        if current_section == "scenario" and current_scenario:
            given_m = given_pattern.match(stripped)
            if given_m:
                current_scenario.given.append(given_m.group(1).strip())
                continue
            when_m = when_pattern.match(stripped)
            if when_m:
                current_scenario.when.append(when_m.group(1).strip())
                continue
            then_m = then_pattern.match(stripped)
            if then_m:
                current_scenario.then.append(then_m.group(1).strip())
                continue
            and_m = and_pattern.match(stripped)
            if and_m:
                # Route AND to the last active clause type
                if current_scenario.then:
                    current_scenario.then.append(and_m.group(1).strip())
                elif current_scenario.when:
                    current_scenario.when.append(and_m.group(1).strip())
                elif current_scenario.given:
                    current_scenario.given.append(and_m.group(1).strip())
                continue

    # Flush remaining
    if current_req:
        doc.requirements.append(current_req)
    if current_scenario:
        doc.scenarios.append(current_scenario)

    return doc


def validate_spec(doc: SpecDocument) -> list[dict]:
    """Validate spec completeness. Returns list of issues."""
    issues = []

    for req in doc.requirements:
        if not req.shall:
            issues.append({
                "severity": "ERROR",
                "type": "missing_shall",
                "item": req.name,
                "message": "Requirement has no SHALL statements"
            })
        if not req.reason:
            issues.append({
                "severity": "WARN",
                "type": "missing_reason",
                "item": req.name,
                "message": "Requirement has no Reason section"
            })

    # Check scenario completeness
    for scenario in doc.scenarios:
        if not scenario.given:
            issues.append({
                "severity": "ERROR",
                "type": "missing_given",
                "item": scenario.name,
                "message": "Scenario has no GIVEN precondition"
            })
        if not scenario.when:
            issues.append({
                "severity": "ERROR",
                "type": "missing_when",
                "item": scenario.name,
                "message": "Scenario has no WHEN trigger"
            })
        if not scenario.then:
            issues.append({
                "severity": "ERROR",
                "type": "missing_then",
                "item": scenario.name,
                "message": "Scenario has no THEN expectation"
            })

    return issues


def diff_specs(old_path: str, new_path: str) -> dict:
    """Diff two OpenSpec files, producing delta output."""
    old_doc = parse_spec(old_path)
    new_doc = parse_spec(new_path)

    old_map = {r.name: r for r in old_doc.requirements}
    new_map = {r.name: r for r in new_doc.requirements}

    added = [name for name in new_map if name not in old_map]
    removed = [name for name in old_map if name not in new_map]
    modified = []

    for name in set(old_map) & set(new_map):
        old_r = old_map[name]
        new_r = new_map[name]
        changes = []
        if old_r.shall != new_r.shall:
            for s in set(new_r.shall) - set(old_r.shall):
                changes.append(f"+ SHALL {s}")
            for s in set(old_r.shall) - set(new_r.shall):
                changes.append(f"- SHALL {s}")
        if changes:
            modified.append({"name": name, "changes": changes})

    return {
        "old": old_path,
        "new": new_path,
        "added_requirements": added,
        "removed_requirements": removed,
        "modified_requirements": modified,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
        "total_changes": len(added) + len(removed) + len(modified),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate.py <file> [--json]", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    to_json = "--json" in sys.argv

    try:
        doc = parse_spec(filepath)
    except Exception as e:
        print(f"❌ Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    issues = validate_spec(doc)
    coverage = _compute_coverage(doc)

    result = {
        "file": filepath,
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "total_shall": sum(len(r.shall) for r in doc.requirements),
        "issues": issues,
        "issue_count": len(issues),
        "error_count": sum(1 for i in issues if i["severity"] == "ERROR"),
        "coverage": coverage,
    }

    if to_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_human(result)

    if result["error_count"] > 0:
        sys.exit(1)


def _compute_coverage(doc: SpecDocument) -> dict:
    """Compute spec coverage score."""
    total = len(doc.requirements)
    if total == 0:
        return {"score": 0, "details": "No requirements found"}
    has_shall = sum(1 for r in doc.requirements if r.shall)
    has_reason = sum(1 for r in doc.requirements if r.reason)

    scenario_ok = sum(
        1 for s in doc.scenarios if s.given and s.when and s.then
    )
    scenario_count = len(doc.scenarios)

    score = (has_shall / total) * 40 + (has_reason / total) * 20
    if scenario_count:
        score += (scenario_ok / scenario_count) * 40

    pass_threshold = score >= 80
    return {
        "score": round(score, 1),
        "total_requirements": total,
        "with_shall": has_shall,
        "with_reason": has_reason,
        "scenarios_total": scenario_count,
        "scenarios_complete": scenario_ok,
        "pass_threshold": pass_threshold,
    }


def _print_human(result: dict):
    print(f"\n📋 OpenSpec Validation: {result['file']}")
    print(f"{'='*50}")
    print(f"  Requirements: {result['requirements']}")
    print(f"  Scenarios:    {result['scenarios']}")
    print(f"  Total SHALLs: {result['total_shall']}")
    print()
    print(f"🔬 Coverage Score: {result['coverage']['score']}%")
    print(f"   (threshold: 80%) {'✅ PASS' if result['coverage']['pass_threshold'] else '❌ FAIL'}")
    print()
    if result["issues"]:
        print(f"⚠️  Issues ({result['issue_count']}):")
        for issue in result["issues"]:
            emoji = "❌" if issue["severity"] == "ERROR" else "⚠️"
            print(f"  {emoji} [{issue['type']}] {issue['item']}: {issue['message']}")
    else:
        print("✅ No issues found — spec is clean!")
    print()


if __name__ == "__main__":
    main()
