#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI MISRA Report — Traceability.

Part of the misra_report/ package split from misra_report.py (Phase 2.2).
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("ci.misra_report")

from yuleosh.ci.misra_report.deviation import _match_deviation


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------





def _enrich_traceability_with_tests(
    rule_defs: dict,
    test_dir: str | None = None,
) -> dict[str, dict]:
    """Map rules to their implementation and test IDs (R3-P0-1).

    Attempts to discover test files from the test directory that
    correspond to each rule. Returns a dict keyed by rule_id with:
      - spec_id: str (from rule_defs spec_ref)
      - impl_id: str (from rule_defs impl_ref or auto-generated)
      - test_id: str (discovered test file or ID)
    """
    result: dict[str, dict] = {}

    for rid, defn in rule_defs.items():
        if rid == "meta":
            continue
        spec_id = defn.get("spec_ref", "")
        impl_id = defn.get("impl_ref", defn.get("check_method", ""))
        test_id = ""

        # Try to discover test files from test directory
        if test_dir and impl_id:
            test_dir_path = Path(test_dir)
            if test_dir_path.is_dir():
                # Look for test files matching the rule or implementation
                rule_num = rid.split("-")[-1] if "-" in rid else rid
                for tf in test_dir_path.rglob("*.py"):
                    if rule_num.replace(".", "_") in tf.stem:
                        test_id = str(tf.relative_to(test_dir_path.parent) if test_dir_path.parent else tf)
                        break

        result[rid] = {
            "spec_id": spec_id,
            "impl_id": impl_id,
            "test_id": test_id,
        }
    return result


def generate_traceability_matrix(
    violations: list[dict],
    rule_defs: dict,
    deviations: list | None = None,
    test_dir: str | None = None,
) -> list[dict]:
    """Build traceability: Rule ID → File:Line → Spec Ref → Fix Status.

    R3-P0-1: Adds impl_id, test_ref for 3-way traceability (rule→spec→test).
    R3-P0-2: Adds risk_level_info, expiration_status for deviations.

    Returns a list of dicts, one per violation, with:
      - rule_id: str
      - file: str
      - line: int
      - col: int
      - severity: str
      - message: str
      - spec_ref: str (from rule_defs, or "" if unknown)
      - impl_id: str (R3-P0-1, from rule_defs impl_ref or check_method)
      - test_ref: str (R3-P0-1, discovered test file if any)
      - check_method: str (from rule_defs, or "" if unknown)
      - auto_checkable: bool (from rule_defs, default True)
      - fix_status: str ("unresolved" | "acknowledged" | "suppressed")
      - deviation_ref: dict | None (matched deviation details, if any)
      - risk_level_info: str | None (R3-P0-2, if deviation matched)
      - expiration_status: dict | None (R3-P0-2, if deviation matched)

    Backward compatible: deviations parameter accepts both list[tuple]
    and list[dict] formats.
    """
    deviations = deviations or []

    # R3-P0-1: Enrich with test discovery
    trace_tests = _enrich_traceability_with_tests(rule_defs, test_dir=test_dir)

    traceability = []
    for v in violations:
        rid = v.get("rule_id", "unknown")
        defn = rule_defs.get(rid, {})
        file_path = v.get("file", "")

        matched, dev_info = _match_deviation(rid, file_path, deviations)
        fix_status = "acknowledged" if matched else "unresolved"

        # R3-P0-1: 3-way traceability fields
        three_way = trace_tests.get(rid, {})
        spec_id = three_way.get("spec_id", defn.get("spec_ref", ""))
        impl_id = three_way.get("impl_id", defn.get("impl_ref", defn.get("check_method", "")))
        test_id = three_way.get("test_id", "")

        entry = {
            "rule_id": rid,
            "file": file_path,
            "line": v.get("line", 0),
            "col": v.get("col", 0),
            "severity": v.get("severity", ""),
            "message": v.get("message", ""),
            "spec_ref": spec_id,
            "impl_id": impl_id,
            "test_ref": test_id,
            "check_method": defn.get("check_method", ""),
            "auto_checkable": bool(defn.get("auto_checkable", True)),
            "fix_status": fix_status,
        }
        # R3-P0-2: Enrich with risk_level info + expiration if deviation matched
        if matched and dev_info:
            entry["deviation_ref"] = dev_info
            entry["risk_level_info"] = dev_info.get("risk_level_info", "")
            entry["expiration_status"] = dev_info.get("expiration_status", {})

        traceability.append(entry)
    return traceability


def generate_fix_tasks(
    project_dir: str,
    violations: list[dict],
    rule_defs: dict,
    deviations: list | None = None,
) -> list[str]:
    """Generate fix task .md files for each unresolved violation.

    Creates one .md file per violated rule under
    ``.yuleosh/fix-tasks/misra-{rule_id}.md``.

    Violations matching deviation records are excluded from fix tasks
    since they are already "acknowledged".

    Accepts both old tuple format and new dict format for deviations.

    Returns list of file paths created.
    """
    from datetime import datetime

    deviations = deviations or []
    fix_dir = Path(project_dir) / ".yuleosh" / "fix-tasks"
    fix_dir.mkdir(parents=True, exist_ok=True)

    # Group violations by rule_id, skipping acknowledged ones
    rule_groups: dict[str, list[dict]] = {}
    for v in violations:
        rid = v.get("rule_id", "unknown")
        file_path = v.get("file", "")
        # Skip deviations-acknowledged violations
        matched, _ = _match_deviation(rid, file_path, deviations)
        if matched:
            continue
        rule_groups.setdefault(rid, []).append(v)

    created_files: list[str] = []
    for rule_id, vs in sorted(rule_groups.items()):
        defn = rule_defs.get(rule_id, {})
        title = defn.get("title", rule_id)
        spec_ref = defn.get("spec_ref", "")
        severity = defn.get("severity", "unknown")

        lines = [
            f"# MISRA Fix Task: {rule_id}",
            "",
            f"> Generated: {datetime.now().isoformat()}",
            f"> Severity: {severity}",
            f"> Spec Ref: {spec_ref}",
            "",
            f"## Rule: {title}",
            "",
            f"{defn.get('description', '')}",
            "",
            "## Violations",
            "",
            "| # | File | Line | Col | Message |",
            "|--:|:-----|:----|:----|:--------|",
        ]
        for idx, v in enumerate(vs, 1):
            msg = v.get("message", "")[:80]
            lines.append(f"| {idx} | `{v.get('file', '')}` | {v.get('line', 0)} | {v.get('col', 0)} | {msg} |")

        lines.extend([
            "",
            "## Fix Checklist",
            "",
            "- [ ] Understand the violation context",
            "- [ ] Apply fix to source code",
            "- [ ] Re-run MISRA check to verify fix",
            "- [ ] Update traceability matrix",
            "- [ ] Document deviation if fix is not feasible",
            "",
            "---",
            "*Generated by yuleOSH MISRA fix-task generator*",
        ])

        file_path = fix_dir / f"misra-{rule_id}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")
        created_files.append(str(file_path))
        log.info("MISRA fix task created: %s", file_path)

    return created_files

