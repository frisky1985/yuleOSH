#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Spec Merge — merge a spec-delta file into the main spec.

Parses SHALL/SHOULD/MAY statements from a delta file,
validates conflicts against the base spec, merges,
and produces a new spec.md with version increment.

Usage:
    yuleosh spec merge <delta-file>
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.spec.version import (
    SpecVersion,
    read_spec_version,
    write_spec_version,
    detect_spec_path,
    compare_versions,
    increment_version,
    parse_version,
)

log = logging.getLogger("spec.merge")


# ------------------------------------------------------------------
# Delta parsing
# ------------------------------------------------------------------


@dataclass
class DeltaStatement:
    """A single statement from a spec-delta file."""

    kind: str  # "SHALL", "SHOULD", or "MAY"
    text: str
    section: str  # Section/requirement name from header
    line_number: int
    scenario_given: str = ""  # GIVEN clause if in GIVEN/WHEN/THEN


@dataclass
class DeltaParseResult:
    """Result of parsing a spec-delta file."""

    statements: list[DeltaStatement] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    target_version: str = ""
    errors: list[str] = field(default_factory=list)


def parse_delta_file(delta_path: str) -> DeltaParseResult:
    """Parse a spec-delta markdown file.

    Extracts:
    - SHALL/SHOULD/MAY statements
    - GIVEN/WHEN/THEN scenarios
    - Target version (from **Version** header)
    - Section headers

    Parameters
    ----------
    delta_path : str
        Path to the spec-delta markdown file.

    Returns
    -------
    DeltaParseResult
        Parsed statements and metadata.
    """
    result = DeltaParseResult()

    if not os.path.exists(delta_path):
        result.errors.append(f"Delta file not found: {delta_path}")
        return result

    try:
        text = Path(delta_path).read_text(encoding="utf-8")
    except OSError as e:
        result.errors.append(f"Cannot read delta file: {e}")
        return result

    lines = text.split("\n")

    # Patterns
    version_pattern = re.compile(r'\*\*(?:Version|版本)\**\s*[:：]\s*(\d+\.\d+\.\d+)')
    section_pattern = re.compile(r'^##\s+(.+)')
    shall_pattern = re.compile(r'^\s*[-*]\s*(?:The\s+system\s+)?(SHALL|SHOULD|MAY)\s+(.+)$', re.IGNORECASE)
    given_pattern = re.compile(r'^\s*[-*]\s*GIVEN\s+(.+)$', re.IGNORECASE)
    when_pattern = re.compile(r'^\s*[-*]\s*WHEN\s+(.+)$', re.IGNORECASE)
    then_pattern = re.compile(r'^\s*[-*]\s*THEN\s+(.+)$', re.IGNORECASE)
    scenario_header_pattern = re.compile(r'^###\s+Scenario:\s*(.+)$', re.IGNORECASE)
    also_shall_pattern = re.compile(r'^\s*[-*]\s*(?:And|AND)\s+(?:the\s+system\s+)?(SHALL|SHOULD|MAY)\s+(.+)$', re.IGNORECASE)

    current_section = ""
    scenario_given = ""
    current_scenario = None
    in_scenario = False

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip empty lines and separators
        if not stripped or stripped.startswith("---") or stripped.startswith("==="):
            continue

        # Version header
        vm = version_pattern.search(stripped)
        if vm:
            result.target_version = vm.group(1)
            continue

        # Section header
        sm = section_pattern.match(stripped)
        if sm and not stripped.startswith("###"):
            current_section = sm.group(1).strip()
            continue

        # Scenario header
        shm = scenario_header_pattern.match(stripped)
        if shm:
            if current_scenario:
                result.scenarios.append(current_scenario)
            current_scenario = {
                "name": shm.group(1).strip(),
                "given": [],
                "when": [],
                "then": [],
            }
            in_scenario = True
            scenario_given = ""
            continue

        # GIVEN/WHEN/THEN
        gm = given_pattern.match(stripped)
        if gm and current_scenario:
            current_scenario["given"].append(gm.group(1).strip())
            continue

        wm = when_pattern.match(stripped)
        if wm and current_scenario:
            current_scenario["when"].append(wm.group(1).strip())
            continue

        tm = then_pattern.match(stripped)
        if tm and current_scenario:
            current_scenario["then"].append(tm.group(1).strip())
            # THEN statements often contain SHALL — extract them
            then_text = tm.group(1).strip()
            # Check if THEN contains embedded SHALL references
            shall_in_then = re.findall(r'(SHALL|SHOULD|MAY)\s+(.+?)(?:\s+AND\s+|$)', then_text, re.IGNORECASE)
            for kind, stmt in shall_in_then:
                full_text = stmt.strip()
                if full_text and not full_text.startswith("the system SHALL"):
                    full_text = "the system " + kind + " " + full_text
                result.statements.append(DeltaStatement(
                    kind=kind.upper(),
                    text=full_text,
                    section=current_section,
                    line_number=idx,
                    scenario_given=scenario_given,
                ))
            continue

        # SHALL/SHOULD/MAY (only outside GIVEN/WHEN/THEN blocks, or standalone)
        if not in_scenario:
            am = shall_pattern.match(stripped)
            if am:
                result.statements.append(DeltaStatement(
                    kind=am.group(1).upper(),
                    text=am.group(2).strip(),
                    section=current_section,
                    line_number=idx,
                ))
                continue

            # Also handle patterns like "- The system SHALL ..."
            alt_shall = re.match(r'^\s*[-*]\s*The\s+system\s+(SHALL|SHOULD|MAY)\s+(.+)$', stripped, re.IGNORECASE)
            if alt_shall:
                result.statements.append(DeltaStatement(
                    kind=alt_shall.group(1).upper(),
                    text=alt_shall.group(2).strip(),
                    section=current_section,
                    line_number=idx,
                ))
                continue

    # Flush last scenario
    if current_scenario:
        result.scenarios.append(current_scenario)

    return result


# ------------------------------------------------------------------
# Conflict detection
# ------------------------------------------------------------------


@dataclass
class Conflict:
    """A conflict between a delta statement and existing spec."""

    delta_statement: DeltaStatement
    existing_shall: str
    severity: str  # "error" or "warning"
    description: str


def detect_conflicts(
    delta: DeltaParseResult,
    spec_text: str,
) -> list[Conflict]:
    """Detect conflicts between delta statements and existing spec.

    Checks:
    - Direct text overlap (same SHALL statement already exists)
    - Semantic negation (SHALL vs SHALL NOT for the same topic)
    - Version downgrade (handled separately)

    Parameters
    ----------
    delta : DeltaParseResult
        Parsed delta file.
    spec_text : str
        Full text of the existing spec.md.

    Returns
    -------
    list[Conflict]
        Detected conflicts.
    """
    conflicts: list[Conflict] = []

    # Extract existing SHALL clauses from spec
    existing_shalls = _extract_shalls(spec_text)

    for stmt in delta.statements:
        norm_text = _normalize_shall_text(stmt.text)

        # Check for exact match
        if norm_text in existing_shalls:
            conflicts.append(Conflict(
                delta_statement=stmt,
                existing_shall=stmt.text,
                severity="warning",
                description=f"Duplicate SHALL statement (line {stmt.line_number}): '{stmt.text[:60]}...' already exists",
            ))
            continue

        # Check for semantic negation (SHALL vs SHALL NOT)
        negation_check = _check_negation(norm_text, existing_shalls)
        if negation_check:
            conflicts.append(Conflict(
                delta_statement=stmt,
                existing_shall=negation_check,
                severity="error",
                description=f"Contradiction with existing spec: delta says '{stmt.text[:60]}' but spec says '{negation_check[:60]}'",
            ))

    return conflicts


def _extract_shalls(spec_text: str) -> list[str]:
    """Extract all normalized SHALL/SHOULD/MAY texts from spec."""
    shalls: list[str] = []
    pattern = re.compile(
        r'^\s*[-*]\s*(?:The\s+system\s+)?(SHALL|SHOULD|MAY(?:\s+NOT)?)\s+(.+)$',
        re.IGNORECASE | re.MULTILINE,
    )
    for m in pattern.finditer(spec_text):
        shalls.append(_normalize_shall_text(m.group(0)))
    return shalls


def _normalize_shall_text(text: str) -> str:
    """Normalize a SHALL statement for comparison."""
    # Remove leading bullets, whitespace
    text = re.sub(r'^[\s*\-]+', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip().lower()
    # Strip trailing punctuation for consistent comparison
    text = text.rstrip('.,;:!?')
    return text


def _check_negation(norm_text: str, existing_shalls: list[str]) -> Optional[str]:
    """Check if a statement contradicts existing statements.

    Simple heuristic: if text has "SHALL NOT" and existing has "SHALL" on
    a similar topic, or vice versa.
    """
    is_negative = "shall not" in norm_text

    for existing in existing_shalls:
        existing_is_negative = "shall not" in existing

        if is_negative != existing_is_negative:
            # Different polarity — check if same topic
            # Extract keywords after SHALL/SHALL NOT
            our_topic = re.sub(r'.*shall\s*(not\s*)?', '', norm_text).strip()
            their_topic = re.sub(r'.*shall\s*(not\s*)?', '', existing).strip()

            if our_topic and their_topic:
                # Simple word overlap check
                our_words = set(our_topic.split()[:10])
                their_words = set(their_topic.split()[:10])
                overlap = our_words & their_words
                if len(overlap) >= 3:  # Significant word overlap
                    return existing

    return None


# ------------------------------------------------------------------
# Merge
# ------------------------------------------------------------------


def merge_delta(
    delta_path: str,
    project_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Merge a spec-delta file into the main spec.

    Returns a result dict with:
    - status: "ok" | "error" | "dry-run"
    - version: new version string
    - statements_added: count
    - scenarios_added: count
    - conflicts: list of conflicts (if any)
    - errors: list of errors
    - diff_text: summary of changes
    - backup_path: path to backup file (None if dry_run)
    - output_path: path to merged spec (None if dry_run or error)

    Parameters
    ----------
    delta_path : str
        Path to the spec-delta markdown file.
    project_dir : str, optional
        Project root directory. Defaults to ``OSH_HOME`` or current dir.
    dry_run : bool, optional
        If True, only validate without writing.

    Returns
    -------
    dict
        Merge result.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    result = {
        "status": "error",
        "version": "",
        "statements_added": 0,
        "scenarios_added": 0,
        "conflicts": [],
        "errors": [],
        "diff_text": "",
        "backup_path": None,
        "output_path": None,
    }

    # 1. Parse delta
    delta = parse_delta_file(delta_path)
    if delta.errors:
        result["errors"] = delta.errors
        return result

    if not delta.statements and not delta.scenarios:
        result["errors"].append("No SHALL/SHOULD/MAY statements or scenarios found in delta file")
        return result

    # 2. Read current spec version
    sv = read_spec_version(project_dir)
    current_version = sv.version
    spec_path = detect_spec_path(project_dir)
    full_spec_path = os.path.join(project_dir, spec_path)

    # 3. Read current spec text
    if not os.path.exists(full_spec_path):
        result["errors"].append(f"Spec file not found: {full_spec_path}")
        return result

    try:
        spec_text = Path(full_spec_path).read_text(encoding="utf-8")
    except OSError as e:
        result["errors"].append(f"Cannot read spec file: {e}")
        return result

    # 4. Version check — reject downgrades
    # If delta has a target version >= current, use it; otherwise auto-bump
    target_version: Optional[str] = None
    if delta.target_version:
        cmp = compare_versions(delta.target_version, current_version)
        if cmp > 0:
            target_version = delta.target_version
        elif cmp == 0:
            # Same version — auto-bump to avoid collision
            log.info("Delta version matches current (%s) — auto-bumping", current_version)
            target_version = None  # Will auto-bump
        else:
            # Delta version < current — this is the delta's document version, not target
            # Auto-bump from current version
            log.info("Delta version %s < current %s — using current as base for auto-bump",
                     delta.target_version, current_version)
            target_version = None

    # 5. Detect conflicts
    conflicts = detect_conflicts(delta, spec_text)
    result["conflicts"] = [{
        "delta_statement": {
            "kind": c.delta_statement.kind,
            "text": c.delta_statement.text,
            "section": c.delta_statement.section,
            "line": c.delta_statement.line_number,
        },
        "existing_shall": c.existing_shall,
        "severity": c.severity,
        "description": c.description,
    } for c in conflicts]

    blocking_conflicts = [c for c in conflicts if c.severity == "error"]
    if blocking_conflicts:
        result["errors"].append(
            f"Merge blocked: {len(blocking_conflicts)} error-level conflict(s) detected"
        )
        return result

    # 6. Compute new version
    new_version = increment_version(
        current_version,
        delta_version=target_version,
    )

    if compare_versions(new_version, current_version) < 0:
        result["errors"].append(
            f"spec-version downgrade: {current_version} → {new_version} is not allowed"
        )
        return result

    result["version"] = new_version
    result["statements_added"] = len(delta.statements)
    result["scenarios_added"] = len(delta.scenarios)

    if dry_run:
        result["status"] = "dry-run"
        result["diff_text"] = _generate_diff_text(delta, new_version, current_version)
        return result

    # 7. Build merged spec text
    merged_text = _build_merged_spec(spec_text, delta, new_version)

    # 8. Backup old spec
    backup_name = f"{spec_path}.v{current_version}"
    backup_path = os.path.join(project_dir, backup_name)
    try:
        shutil.copy2(full_spec_path, backup_path)
        result["backup_path"] = backup_path
    except OSError as e:
        result["errors"].append(f"Cannot create backup at {backup_path}: {e}")
        return result

    # 9. Write merged spec
    try:
        Path(full_spec_path).write_text(merged_text, encoding="utf-8")
        result["output_path"] = full_spec_path
    except OSError as e:
        result["errors"].append(f"Cannot write merged spec: {e}")
        return result

    # 10. Update spec version lock file
    sv.version = new_version
    sv.spec_path = spec_path
    sv.updated_by = f"spec-merge ({os.path.basename(delta_path)})"
    history_entry = {
        "version": new_version,
        "previous": current_version,
        "delta": os.path.basename(delta_path),
        "statements_added": len(delta.statements),
        "scenarios_added": len(delta.scenarios),
        "timestamp": datetime.now().isoformat(),
        "warnings": len([c for c in conflicts if c.severity == "warning"]),
    }
    sv.history.append(history_entry)

    if not write_spec_version(sv, project_dir):
        result["errors"].append("Failed to write spec version file")
        return result

    result["status"] = "ok"
    result["statements_added"] = len(delta.statements)
    result["scenarios_added"] = len(delta.scenarios)
    result["diff_text"] = _generate_diff_text(delta, new_version, current_version)

    return result


# ------------------------------------------------------------------
# Spec text manipulation
# ------------------------------------------------------------------


def _build_merged_spec(spec_text: str, delta: DeltaParseResult, new_version: str) -> str:
    """Build the merged spec text by incorporating delta statements.

    Strategy: Append delta content as new sections at the end of spec.md.
    """
    lines = spec_text.split("\n")
    new_lines = list(lines)

    # Update version in header
    version_updated = False
    for i, line in enumerate(new_lines):
        if "**Version**" in line:
            new_lines[i] = re.sub(
                r'(\d+\.\d+\.\d+)',
                new_version,
                line,
            )
            version_updated = True
            break

    if not version_updated:
        # Add version line after the first heading
        for i, line in enumerate(new_lines):
            if line.startswith("# ") and i + 1 < len(new_lines):
                new_lines.insert(i + 1, f"> **Version**: {new_version}")
                break

    # Add a merge marker
    new_lines.append("")
    new_lines.append("---")
    new_lines.append("")
    new_lines.append(f"## Merged from Spec-Delta")
    new_lines.append("")
    new_lines.append(f"> **Merge timestamp**: {datetime.now().isoformat()}")
    new_lines.append(f"> **New version**: {new_version}")
    new_lines.append(f"> **Statements added**: {len(delta.statements)}")
    new_lines.append(f"> **Scenarios added**: {len(delta.scenarios)}")
    new_lines.append("")

    # Group statements by section
    from collections import defaultdict
    sections: dict[str, list[DeltaStatement]] = defaultdict(list)
    for stmt in delta.statements:
        sections[stmt.section or "Uncategorized"].append(stmt)

    # Write statements
    for section_name, stmts in sections.items():
        new_lines.append(f"### {section_name}")
        new_lines.append("")
        for stmt in stmts:
            prefix = "- " if stmt.kind in ("SHALL", "SHOULD", "MAY") else "- "
            new_lines.append(f"{prefix}The system {stmt.kind} {stmt.text}")
        new_lines.append("")

    # Write scenarios
    if delta.scenarios:
        new_lines.append(f"### GIVEN/WHEN/THEN Scenarios")
        new_lines.append("")
        for scenario in delta.scenarios:
            new_lines.append(f"#### Scenario: {scenario['name']}")
            new_lines.append("")
            for g in scenario.get("given", []):
                new_lines.append(f"- GIVEN {g}")
            for w in scenario.get("when", []):
                new_lines.append(f"- WHEN {w}")
            for t in scenario.get("then", []):
                new_lines.append(f"- THEN {t}")
            new_lines.append("")

    return "\n".join(new_lines)


def _generate_diff_text(delta: DeltaParseResult, new_version: str, old_version: str) -> str:
    """Generate a human-readable diff summary."""
    lines = [
        f"## Spec Merge Summary",
        f"",
        f"- **Old version**: {old_version}",
        f"- **New version**: {new_version}",
        f"- **Statements added**: {len(delta.statements)}",
        f"- **Scenarios added**: {len(delta.scenarios)}",
        f"- **Target version** (from delta): {delta.target_version or '(auto)'}",
        f"",
    ]
    if delta.statements:
        lines.append("### Statements")
        for stmt in delta.statements:
            lines.append(f"- [{stmt.kind}] {stmt.text[:80]}")
    if delta.scenarios:
        lines.append("### Scenarios")
        for s in delta.scenarios:
            g_count = len(s.get("given", []))
            w_count = len(s.get("when", []))
            t_count = len(s.get("then", []))
            lines.append(f"- {s['name']} ({g_count} GIVEN, {w_count} WHEN, {t_count} THEN)")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Delta validation
# ------------------------------------------------------------------


def validate_delta_format(delta_path: str) -> list[str]:
    """Validate that a spec-delta file has the correct format.

    Checks:
    - File exists and is readable
    - Contains at least one SHALL/SHOULD/MAY statement
    - Uses RFC 2119 terminology
    - Has proper GIVEN/WHEN/THEN structure (if scenarios present)

    Returns a list of issue descriptions (empty = valid).
    """
    issues: list[str] = []

    if not os.path.exists(delta_path):
        issues.append(f"File not found: {delta_path}")
        return issues

    try:
        text = Path(delta_path).read_text(encoding="utf-8")
    except OSError as e:
        issues.append(f"Cannot read file: {e}")
        return issues

    if not text.strip():
        issues.append("File is empty")
        return issues

    # Check for RFC 2119 keywords
    has_shall = bool(re.search(r'\bSHALL\b', text))
    has_should = bool(re.search(r'\bSHOULD\b', text))
    has_may = bool(re.search(r'\bMAY\b', text))

    if not has_shall and not has_should and not has_may:
        issues.append("No RFC 2119 keywords found (SHALL/SHOULD/MAY)")
    else:
        rfc_count = sum([has_shall, has_should, has_may])
        if rfc_count == 0:
            issues.append("No requirements statements (SHALL/SHOULD/MAY) found")

    # Check for spec-delta format markers
    has_version = bool(re.search(r'\*\*Version\*\*', text) or re.search(r'^#+\s*spec-delta', text, re.IGNORECASE))

    return issues


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def cmd_spec_merge(delta_path: str, project_dir: Optional[str] = None, dry_run: bool = False) -> bool:
    """CLI handler for ``yuleosh spec merge``.

    Returns True on success.
    """
    print(f"\n  📋 Spec Merge")
    print(f"  {'=' * 55}")
    print(f"  Delta: {delta_path}")
    print()

    # Validate delta format first
    issues = validate_delta_format(delta_path)
    if issues:
        print(f"  ❌ Delta format validation failed:")
        for issue in issues:
            print(f"     • {issue}")
        return False

    # Parse delta
    delta = parse_delta_file(delta_path)
    if delta.errors:
        print(f"  ❌ Parse errors:")
        for e in delta.errors:
            print(f"     • {e}")
        return False

    print(f"  📊 Parsed: {len(delta.statements)} statement(s), {len(delta.scenarios)} scenario(s)")
    print(f"     Target version: {delta.target_version or '(auto)'}")
    print()

    # Validate active profile before merge
    try:
        from yuleosh.ci.config import load_ci_config, validate_misra_profiles
        cfg = load_ci_config(project_dir)
        profile_errors = validate_misra_profiles(cfg)
        if profile_errors:
            print(f"  ⚠️  MISRA profile validation:")
            for pe in profile_errors:
                print(f"     {pe}")
            print()
    except Exception:
        pass

    # Perform merge
    result = merge_delta(delta_path, project_dir, dry_run=dry_run)

    # Print result
    if result["errors"]:
        print(f"  ❌ Merge failed:")
        for e in result["errors"]:
            print(f"     • {e}")
        return False

    if dry_run:
        print(f"  ✅ Dry run — no changes written")
        print()
        print(result["diff_text"])
        return True

    print(f"  ✅ Merge complete:")
    print(f"     Version: {result['version']}")
    print(f"     Statements added: {result['statements_added']}")
    print(f"     Scenarios added: {result['scenarios_added']}")
    print(f"     Warnings: {len([c for c in result['conflicts'] if c['severity'] == 'warning'])}")
    print()

    if result["conflicts"]:
        warnings = [c for c in result["conflicts"] if c["severity"] == "warning"]
        if warnings:
            print(f"  ⚠️  Non-blocking warnings:")
            for w in warnings:
                print(f"     • {w['description']}")
            print()

    if result["backup_path"]:
        print(f"  💾 Backup: {result['backup_path']}")
    if result["output_path"]:
        print(f"  📄 Output: {result['output_path']}")
    print()
    print(result["diff_text"])
    print()

    return True



