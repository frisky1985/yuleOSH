#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
OSH Spec Engine — OpenSpec parser, validator, and diff engine.

Supports RFC 2119: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN scenarios.
Hierarchical requirement IDs: RS-XXX (System), SWR-XXX.Y (Software).
Status tracking: PROPOSED → APPROVED → IMPLEMENTED → VERIFIED.
Outputs structured JSON for pipeline consumption.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

# ── Status constants ──────────────────────────────────────────────────────────

ALLOWED_STATUSES = ("PROPOSED", "APPROVED", "IMPLEMENTED", "VERIFIED")
VALID_STATUS_TRANSITIONS = {
    None: ("PROPOSED",),
    "PROPOSED": ("APPROVED",),
    "APPROVED": ("IMPLEMENTED",),
    "IMPLEMENTED": ("VERIFIED",),
    "VERIFIED": (),  # Terminal state
}

# ── ID patterns ───────────────────────────────────────────────────────────────

ID_PATTERN = re.compile(r"^([A-Z][A-Z0-9]*(?:-REQ)?(?:-SHALL(?:\-NOT)?)?)-(\d+)(?:\.(\d+))?$", re.IGNORECASE)
# Pattern for SHALL table-style IDs like KL-SHALL-01, PE-SHALL-NOT-01
TABLE_ID_PATTERN = re.compile(r"^([A-Za-z]+)-SHALL(?:\-NOT)?-(\d+)$")
HEADER_ID_PATTERN = re.compile(
    r"^#{2,4}\s+((?:[A-Z][A-Z0-9]*(?:-REQ)?)-[\d.]+):?\s*(.+)$", re.IGNORECASE
)
# ── Data classes ──────────────────────────────────────────────────────────────


class SpecRequirement:
    def __init__(
        self,
        name: str,
        shall: list[str],
        should: list[str],
        may: list[str],
        reason: str,
        req_id: str = "",
        level: str = "",
        parent: str = "",
        status: str = "PROPOSED",
    ):
        self.name = name
        self.shall = shall
        self.should = should
        self.may = may
        self.reason = reason
        self.req_id = req_id
        self.level = level
        self.parent = parent
        self.status = status

    def to_dict(self):
        return {
            "name": self.name,
            "shall": self.shall,
            "should": self.should,
            "may": self.may,
            "reason": self.reason,
            "req_id": self.req_id,
            "level": self.level,
            "parent": self.parent,
            "status": self.status,
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
            "total_shall": sum(len(r.shall) for r in self.requirements),
        }


# ── ID helpers ────────────────────────────────────────────────────────────────


def _parse_id(req_id: str) -> tuple:
    """Parse a requirement ID into (prefix, major, minor).

    Returns (None, None, None) for invalid IDs.
    """
    m = ID_PATTERN.match(req_id)
    if not m:
        return (None, None, None)
    prefix = m.group(1).upper()
    major = int(m.group(2))
    minor = int(m.group(3)) if m.group(3) else None
    return (prefix, major, minor)


def _id_to_level(req_id: str) -> str:
    """Derive level from ID prefix."""
    prefix, _, _ = _parse_id(req_id)
    # Map known prefixes; project-specific (e.g. SCM-REQ, BCM-REQ) return ""
    # and rely on project-context or user override.
    return {"RS": "SYS", "SWR": "SW", "FEATURE": "FEATURE"}.get(prefix, "")


def _id_to_parent(req_id: str) -> str:
    """Derive parent ID. SWR-001.1 parent = RS-001."""
    prefix, major, minor = _parse_id(req_id)
    # SWR child → RS parent; project-specific child → project parent
    if prefix == "SWR" and minor is not None:
        return f"RS-{major:03d}"
    # Generic {PROJECT}-REQ-XXX.Y → {PROJECT}-REQ-XXX
    if prefix.endswith("-REQ") and minor is not None:
        return f"{prefix}-{major:03d}"
    return ""


# ── Status helpers ────────────────────────────────────────────────────────────


def validate_status_transition(old_status: str, new_status: str) -> tuple[bool, str]:
    """Check if a status transition is valid.

    Returns (is_valid, error_message).
    """
    allowed = VALID_STATUS_TRANSITIONS.get(old_status, ())
    if new_status not in allowed:
        valid_next = " → ".join(allowed) if allowed else "（终态，不可变更）"
        return (
            False,
            f"状态迁移非法：{old_status} → {new_status}（允许: {valid_next}）",
        )
    return (True, "")


def _detect_status_from_lines(lines: list[str], start_idx: int) -> str:
    """Scan lines around start_idx for a status marker.

    Returns the status value as-is from the spec, or "PROPOSED" as default.
    Invalid status values are returned verbatim so validate_spec can flag them.
    """
    raw_pattern = re.compile(r"^\s*Status:\s*(\S+)\s*$", re.IGNORECASE)
    for i in range(start_idx, min(start_idx + 15, len(lines))):
        m = raw_pattern.match(lines[i])
        if m:
            val = m.group(1).upper()
            return val
    return "PROPOSED"


# ── Parsing ───────────────────────────────────────────────────────────────────



# ── Table parsing helpers (extracted for CQ-P2-04) ───────────────────────────


def _is_table_separator(line: str) -> bool:
    """Check if a line is a markdown table separator.

    Accepts both ``|:---|---:|`` (with colons) and ``|---|---|`` (plain dashes) formats.
    """
    s = line.strip()
    if not s.startswith("|"):
        return False
    # Allowable chars: |, -, :, and optional spaces
    for c in s:
        if c not in "|:- " and c != "|":
            return False
    # Must have at least 2 dashes somewhere (table separator has >2 dashes between pipes)
    stripped_dashes = s.replace("|", "").replace(":", "").replace(" ", "")
    return len(stripped_dashes) >= 2 and all(c == "-" for c in stripped_dashes)


def _is_shall_table_header(col_names: list[str]) -> bool:
    """Detect table header for SHALL requirement tables."""
    if len(col_names) < 2:
        return False
    id_found = col_names[0].upper() == "ID" or "ID" in col_names[0].upper()
    desc_found = (
        "描述" in col_names[1]
        or "需求" in col_names[1]
        or "REQUIREMENT" in col_names[1].upper()
        or "SHALL" in col_names[1].upper()
        or "DESCRIPTION" in col_names[1].upper()
        or "STATEMENT" in col_names[1].upper()
    )
    return id_found and desc_found


def parse_spec(filepath: str) -> SpecDocument:
    """Parse an OpenSpec markdown file into structured data.

    NOTE (CQ-P2-04): This function is ~200 lines due to the multi-format parsing
    (legacy list format + markdown table format). If it grows further, extract
    per-format parsers into separate private functions.
    """
    doc = SpecDocument(filepath)
    text = Path(filepath).read_text(encoding="utf-8")
    lines = text.split("\n")

    current_req: SpecRequirement | None = None
    current_scenario: SpecScenario | None = None
    current_section: str | None = None  # "req", "scenario", "intro"

    req_pattern = re.compile(r"^#{2,4}\s+(?:Requirement|[A-Za-z]+-\d[\w.]*):?\s*(.+)$", re.IGNORECASE)
    scenario_pattern = re.compile(r"^#{2,4}\s+Scenario:\s*(.+)$", re.IGNORECASE)
    reason_pattern = re.compile(r"^#{2,5}\s+Reason\s*$", re.IGNORECASE)
    acceptance_pattern = re.compile(r"^#{2,5}\s+(?:Acceptance|验收)", re.IGNORECASE)
    status_pattern = re.compile(r"^\s*Status:\s*(\S+)\s*$", re.IGNORECASE)

    shall_pattern = re.compile(r"^\s*-\s*The\s+system\s+SHALL\s+(.+)$", re.IGNORECASE)
    should_pattern = re.compile(r"^\s*-\s*The\s+system\s+SHOULD\s+(.+)$", re.IGNORECASE)
    may_pattern = re.compile(r"^\s*-\s*The\s+system\s+MAY\s+(.+)$", re.IGNORECASE)
    given_pattern = re.compile(r"^\s*-\s*GIVEN\s+(.+)$", re.IGNORECASE)
    when_pattern = re.compile(r"^\s*-\s*WHEN\s+(.+)$", re.IGNORECASE)
    then_pattern = re.compile(r"^\s*-\s*THEN\s+(.+)$", re.IGNORECASE)
    and_pattern = re.compile(r"^\s*-\s*AND\s+(.+)$", re.IGNORECASE)

    # Track the last RS-ID for parent assignment
    last_rs_id = ""

    # Table parsing state
    in_shall_table = False
    table_sep_seen = False
    table_section_name = ""

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Exit table mode on any non-table line
        if in_shall_table and (not stripped.startswith("|") or stripped.startswith("#")):
            in_shall_table = False
            table_sep_seen = False

        # Detect section header
        req_match = req_pattern.match(stripped)
        if req_match:
            # Exit table mode
            in_shall_table = False
            table_sep_seen = False

            if current_req:
                doc.requirements.append(current_req)
            name = req_match.group(1).strip()

            # Extract req_id from the header pattern
            header_id_match = HEADER_ID_PATTERN.match(stripped)
            req_id = ""
            if header_id_match:
                req_id = header_id_match.group(1).upper()

            level = _id_to_level(req_id) if req_id else ""
            parent = _id_to_parent(req_id) if req_id else ""

            # Track last RS for SWR parent assignment
            if level == "SYS":
                last_rs_id = req_id
            elif level == "SW" and not parent and last_rs_id:
                parent = last_rs_id

            # Detect status from upcoming lines
            status = _detect_status_from_lines(lines, idx + 1)

            current_req = SpecRequirement(name, [], [], [], "", req_id, level, parent, status)
            current_section = "req"
            continue

        scenario_match = scenario_pattern.match(stripped)
        if scenario_match:
            # Exit table mode
            in_shall_table = False
            table_sep_seen = False

            if current_scenario:
                doc.scenarios.append(current_scenario)
            current_scenario = SpecScenario(scenario_match.group(1), [], [], [])
            current_section = "scenario"
            continue

        # Track section heading names for table context
        if stripped.startswith("#") and not stripped.startswith("######"):
            in_shall_table = False
            table_sep_seen = False
            table_section_name = stripped.lstrip("#").strip()

        if reason_pattern.match(stripped):
            current_section = "reason"
            continue

        if acceptance_pattern.match(stripped):
            current_section = "acceptance"
            continue

        # ── Detect markdown table with SHALL requirements ──
        if stripped.startswith("|") and not in_shall_table and not current_req:
            cols = [c.strip() for c in stripped.split("|")]
            col_names = [c for c in cols if c]
            if _is_shall_table_header(col_names):
                in_shall_table = True
                table_sep_seen = False
                continue

        # ── Parse table separator row ──
        if in_shall_table and not table_sep_seen and _is_table_separator(stripped):
            table_sep_seen = True
            continue

        # ── Parse table rows: each row becomes a SpecRequirement ──
        if in_shall_table and table_sep_seen and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.split("|")]
            if len(cols) >= 3:
                row_id = cols[1].strip()
                row_desc = cols[2].strip()

                # Create requirements for SHALL/SHALL-NOT rows (ID-based)
                # or for REQ rows whose description starts with SHALL
                is_shall_row = "-SHALL" in row_id
                if not is_shall_row and row_desc.upper().startswith("SHALL"):
                    # REQ-xxx rows like DCM-REQ-01 with "SHALL support ..."
                    is_shall_row = True

                if is_shall_row:
                    # Determine the proper ID to use
                    use_id = row_id
                    if "-SHALL" not in row_id and "-REQ-" in row_id:
                        use_id = row_id.replace("-REQ-", "-SHALL-")

                    new_req = SpecRequirement(
                        name=use_id,
                        shall=[row_desc],
                        should=[],
                        may=[],
                        reason="",
                        req_id=use_id,
                        level="",
                        parent="",
                        status="PROPOSED",
                    )
                    doc.requirements.append(new_req)
            continue

        # Parse requirement items (legacy list format)
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

            # Detect Status: marker inside req section
            status_m = status_pattern.match(stripped)
            if status_m:
                current_req.status = status_m.group(1).upper()
                continue

        # Fallback: capture standalone bullet-point SHALLs outside a requirement section
        # (e.g. bullet-point specs like bsw-services-spec.md, mcal-drivers-spec.md)
        if not current_req and not in_shall_table:
            if stripped.startswith("- ") or stripped.startswith("* ") or stripped.startswith("+ "):
                if re.search(r'\bSHALL\b', stripped, re.IGNORECASE):
                    statement = stripped.strip()
                    statement = re.sub(r"^[\s]*[-*+]\s+(The\s+system\s+)?", "", statement, flags=re.IGNORECASE)
                    # Generate fallback requirement name from section
                    sec_name = re.sub(r'[^A-Z0-9]', '', (table_section_name or 'SPEC').upper())[:8]
                    if not sec_name or len(sec_name) < 2:
                        sec_name = "SPEC"
                    fallback_id = f"{sec_name}-SHALL-{len(doc.requirements) + 1}"
                    new_req = SpecRequirement(
                        name=fallback_id,
                        shall=[statement],
                        should=[], may=[], reason="",
                        req_id=fallback_id,
                        level="", parent="",
                        status="PROPOSED",
                    )
                    doc.requirements.append(new_req)
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


# ── Validation ────────────────────────────────────────────────────────────────


def validate_spec(doc: SpecDocument) -> list[dict]:
    """Validate spec completeness. Returns list of issues."""
    issues = []

    for req in doc.requirements:
        if not req.shall:
            issues.append({
                "severity": "ERROR",
                "type": "missing_shall",
                "item": req.name,
                "req_id": req.req_id,
                "message": "Requirement has no SHALL statements"
            })
        if not req.reason:
            issues.append({
                "severity": "WARN",
                "type": "missing_reason",
                "item": req.name,
                "req_id": req.req_id,
                "message": "Requirement has no Reason section"
            })

        # Validate req_id format if present
        if req.req_id:
            prefix, major, minor = _parse_id(req.req_id)
            if prefix is None:
                issues.append({
                    "severity": "ERROR",
                    "type": "invalid_req_id",
                    "item": req.name,
                    "req_id": req.req_id,
                    "message": f"Requirement ID '{req.req_id}' does not match expected prefix-number format (e.g. RS-001, SWR-001.1, SCM-REQ-001)"
                })

        # Validate status
        if req.status not in ALLOWED_STATUSES:
            issues.append({
                "severity": "ERROR",
                "type": "invalid_status",
                "item": req.name,
                "req_id": req.req_id,
                "message": f"Invalid status '{req.status}'. Allowed: {', '.join(ALLOWED_STATUSES)}"
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


# ── Diff ──────────────────────────────────────────────────────────────────────


def diff_specs(old_path: str, new_path: str) -> dict:
    """Diff two OpenSpec files, producing delta with impact analysis."""
    old_doc = parse_spec(old_path)
    new_doc = parse_spec(new_path)

    old_map = {r.name: r for r in old_doc.requirements}
    new_map = {r.name: r for r in new_doc.requirements}

    added = [name for name in new_map if name not in old_map]
    removed = [name for name in old_map if name not in new_map]
    modified = []
    status_changed = []

    for name in set(old_map) & set(new_map):
        old_r = old_map[name]
        new_r = new_map[name]
        changes = []
        if old_r.shall != new_r.shall:
            for s in set(new_r.shall) - set(old_r.shall):
                changes.append(f"+ SHALL {s}")
            for s in set(old_r.shall) - set(new_r.shall):
                changes.append(f"- SHALL {s}")
        if old_r.should != new_r.should:
            for s in set(new_r.should) - set(old_r.should):
                changes.append(f"+ SHOULD {s}")
        if old_r.may != new_r.may:
            for s in set(new_r.may) - set(old_r.may):
                changes.append(f"+ MAY {s}")
        if old_r.status != new_r.status:
            status_changed.append({
                "name": name,
                "req_id": new_r.req_id,
                "old_status": old_r.status,
                "new_status": new_r.status,
            })
            changes.append(f"🔀 Status: {old_r.status} → {new_r.status}")

        if changes:
            modified.append({"name": name, "req_id": new_r.req_id, "changes": changes})

    # ── Impact analysis ──
    impact_analysis = _compute_impact_analysis(
        old_doc, new_doc, added, removed, modified
    )

    return {
        "old": old_path,
        "new": new_path,
        "added_requirements": added,
        "removed_requirements": removed,
        "modified_requirements": modified,
        "status_changed": status_changed,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
        "status_changed_count": len(status_changed),
        "total_changes": len(added) + len(removed) + len(modified) + len(status_changed),
        "impact_analysis": impact_analysis,
    }


def _compute_impact_analysis(
    old_doc: SpecDocument,
    new_doc: SpecDocument,
    added: list[str],
    removed: list[str],
    modified: list[dict],
) -> dict:
    """Compute impact analysis based on spec changes.

    Analyses affected requirements, tests, architecture components,
    scenarios, and recommended actions.
    """
    affected_reqs = list(set(added + removed + [m["name"] for m in modified]))

    # Build parent-child relationships from the new doc
    new_map = {r.name: r for r in new_doc.requirements}

    # Find children of affected requirements
    children_affected = []
    for req_name in affected_reqs:
        req = new_map.get(req_name)
        if req and req.req_id:
            for other_name, other_req in new_map.items():
                if other_req.parent == req.req_id and other_name not in affected_reqs:
                    children_affected.append(other_name)

    # Find affected scenarios (keyword matching)
    scenario_names = [s.name for s in new_doc.scenarios]
    scenario_terms = {
        "CI/CD 三层验证": ["CI", "三层", "流水线", "CI/CD"],
        "SDD → DDD → TDD 全流程": ["Agent", "SDD", "DDD", "TDD", "流水线", "pipeline"],
        "变更管理": ["变更", "delta", "更新", "spec"],
    }

    affected_scenarios = []
    for req_name in affected_reqs:
        for sname, keywords in scenario_terms.items():
            if any(k.lower() in req_name.lower() for k in keywords):
                if sname not in affected_scenarios:
                    affected_scenarios.append(sname)

    # Find affected architecture components (keyword-based)
    component_map = {
        "RS-001": ["pipeline", "agent pipeline spec"],
        "SWR-001.1": ["pipeline run", "step orchestration"],
        "SWR-001.2": ["test plan", "traceability", "evidence pack"],
        "RS-002": ["spec parser", "validate", "diff engine"],
        "SWR-002.1": ["spec parser", "validation rules"],
        "SWR-002.2": ["diff engine", "spec tracking"],
        "RS-003": ["review engine", "review routing"],
        "RS-004": ["CI runner", "Dockerfile", "cross compile"],
        "RS-005": ["evidence pack", "traceability matrix"],
        "RS-006": ["UI routes", "server", "auth"],
        "RS-007": ["auth", "project", "org hierarchy"],
    }

    affected_components = []
    for req_name in affected_reqs:
        req = new_map.get(req_name)
        req_id = req.req_id if req else ""
        comps = component_map.get(req_id, [])
        for c in comps:
            if c not in affected_components:
                affected_components.append(c)

    # Build recommended actions
    recommended_actions = []
    for name in removed:
        recommended_actions.append(f"从 spec 中移除 '{name}' 的所有引用和相关测试")
    for name in added:
        recommended_actions.append(f"为 '{name}' 编写架构设计、测试用例和开发计划")
    for m in modified:
        changes_desc = "; ".join(m["changes"][:3])
        recommended_actions.append(
            f"根据 '{m['name']}' 的变更 ({changes_desc}) 更新相关设计文档和测试"
        )
    for name in children_affected:
        child = new_map.get(name)
        if child:
            recommended_actions.append(
                f"子需求 '{name}' ({child.req_id}) 可能受父需求变更影响，请审阅"
            )

    return {
        "affected_requirements": affected_reqs,
        "affected_children": children_affected,
        "affected_scenarios": affected_scenarios,
        "affected_architecture_components": affected_components,
        "recommended_actions": recommended_actions,
        "action_count": len(recommended_actions),
    }


# ── Coverage ──────────────────────────────────────────────────────────────────


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


# ── CLI ───────────────────────────────────────────────────────────────────────


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
            rid = f" [{issue.get('req_id', '?')}]" if issue.get("req_id") else ""
            print(f"  {emoji}[{issue['type']}] {issue['item']}{rid}: {issue['message']}")
    else:
        print("✅ No issues found — spec is clean!")
    print()


if __name__ == "__main__":
    main()
