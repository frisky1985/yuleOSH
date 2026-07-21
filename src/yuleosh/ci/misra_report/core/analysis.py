#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985

"""
MISRA Report — Analysis / Grouping / Statistics / Diff.

Split from core.py (Phase 2.2 → Phase 3).
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.misra_report")

from yuleosh.ci.misra_report.core.config import (
    _MISRA_SCHEMA_VERSION,
    _DEFAULT_REPORT_DIR,
    _count_source_lines,
    _extract_excluded_rules,
    _extract_excluded_files,
    load_rule_definitions,
    get_ruleset_version,
)


def group_by_rule(violations: list[dict]) -> dict:
    """Group violations by rule ID."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for v in violations:
        rid = v.get("rule_id")
        if rid is None:
            rid = "unknown"
        groups[rid].append(v)
    return dict(groups)


def _classify_rule_type(rule_id: str | None) -> str:
    """Classify a MISRA rule by its type category."""
    if not rule_id:
        return "unknown"
    rule_id = rule_id.strip()
    rule_id_lower = rule_id.lower()
    # Directive rules
    if rule_id_lower.startswith("dir"):
        return "directive"
    # Required rules
    if rule_id_lower.endswith(".1") or rule_id_lower.endswith(".2"):
        return "required"
    # Advisory rules
    if rule_id_lower.endswith(".3") or rule_id_lower.endswith(".4"):
        return "advisory"
    return "required"  # default


def _extract_rules(rule_defs: dict) -> dict:
    """Extract rule definitions from the YAML dict, filtering out meta keys.

    misra-rules.yaml stores rules as top-level keys alongside a "meta" key.
    This helper returns only the rule entries.
    """
    if not rule_defs:
        return {}
    # Check if rules are nested under a "rules" key (alternative format)
    if "rules" in rule_defs and isinstance(rule_defs["rules"], dict):
        return rule_defs["rules"]
    # Top-level format: filter out "meta"
    return {
        k: v for k, v in rule_defs.items()
        if k != "meta" and isinstance(v, dict) and "severity" in v
    }


def enrich_with_definitions(
    violations: list[dict] | dict,
    rule_defs: dict | None = None,
) -> list[dict]:
    """Enrich violations with rule definition info.

    Accepts either a list of violation dicts (standard) or a dict
    of rule_id → violation entries (from group_by_rule).
    In the dict case, iterates over the values (lists of dicts).

    Sets severity_category from the rule definition's 'severity' field
    (required/advisory) rather than the heuristic _classify_rule_type().
    """
    if not rule_defs:
        rule_defs = load_rule_definitions()
    enriched = []
    rules = _extract_rules(rule_defs)
    # Support both list[dict] and dict[str, list[dict]] inputs
    if isinstance(violations, dict):
        items = []
        for vlist in violations.values():
            items.extend(vlist if isinstance(vlist, list) else [vlist])
        violations = items
    for v in violations:
        rid = v.get("rule_id", "")
        defn = rules.get(rid, {})
        v["category"] = defn.get("category", _classify_rule_type(rid))
        v["description"] = defn.get("description", "")
        # Use actual rule definition severity (required/advisory) instead of heuristic
        v["severity_category"] = defn.get("severity", _classify_rule_type(rid))
        v["rule_type"] = defn.get("severity", _classify_rule_type(rid))
        enriched.append(v)
    return enriched


def compute_summary_stats(
    violations: list[dict],
    groups: dict,
    rule_defs: dict | None = None,
) -> dict:
    """Compute summary statistics from violations and groups."""
    total = len(violations)
    by_severity = defaultdict(int)
    by_rule_type = defaultdict(int)

    for v in violations:
        by_severity[v.get("severity", "unknown")] += 1
        # Use severity_category from enrichment (set from rule defs) when available,
        # fall back to heuristic for backward compat
        rule_type = v.get("severity_category", v.get("rule_type", _classify_rule_type(v.get("rule_id"))))
        by_rule_type[rule_type] += 1

    total_file_count = len({v.get("file") for v in violations if v.get("file")})
    total_source_lines = _count_source_lines(
        list({v["file"] for v in violations if v.get("file")})
    ) if violations else 0

    return {
        "total_violations": total,
        "unique_rules": len(groups),
        "affected_files": total_file_count,
        "total_source_lines": total_source_lines,
        "by_severity": dict(by_severity),
        "by_rule_type": dict(by_rule_type),
        "density_per_kloc": round(total / max(total_source_lines, 1) * 1000, 2),
    }


def _load_prev_report(output_dir: str | Path) -> dict | None:
    """Load the previous MISRA report for diff comparison."""
    output_dir = Path(output_dir) if isinstance(output_dir, str) else output_dir
    report_files = sorted(output_dir.glob("misra-report-*.json"))
    if not report_files:
        return None
    try:
        return json.loads(report_files[-1].read_text())
    except Exception as e:
        log.warning("Failed to load previous report: %s", e)
        return None


def _compute_prev_build_diff(
    current: dict,
    prev: dict,
) -> dict:
    """Compute diff between current and previous MISRA reports."""
    return {
        "delta_total": current.get("total_violations", 0) - prev.get("total_violations", 0),
        "previous_total": prev.get("total_violations", 0),
        "previous_build_id": prev.get("build_id"),
        "previous_date": prev.get("date"),
    }


def _compute_category_breakdown(violations: list[dict]) -> dict:
    """Compute breakdown by violation category."""
    breakdown: dict[str, int] = defaultdict(int)
    for v in violations:
        cat = v.get("category", v.get("severity", "unknown"))
        breakdown[cat] += 1
    return dict(breakdown)
