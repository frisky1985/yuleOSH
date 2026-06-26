#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Compliance Overview API — serves compliance dashboard data.

Provides aggregated GSCR compliance overview for the dashboard.
Reads from the GSCR ruleset and the latest compliance/misra report.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error

log = logging.getLogger("api.compliance")

# Project root (same as in __init__.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OSH_HOME = PROJECT_ROOT


def handle_compliance(method: str, path_tail: str, body: dict,
                      query: dict, handler: Any) -> tuple[dict, int]:
    """Handle /api/v1/compliance/... requests.

    Supported routes:
        GET /api/v1/compliance/overview — 合规概览数据
    """
    if method != "GET":
        return json_error("Method not allowed", 405)

    if path_tail == "overview" or path_tail == "":
        return _get_compliance_overview()
    return json_error(f"Unknown compliance sub-path: {path_tail}", 404)


def _get_compliance_overview() -> tuple[dict, int]:
    """Build the compliance overview data for the dashboard.

    Aggregates:
    - MISRA violation count (from latest misra-report.json)
    - GSCR mapping rate
    - Severity distribution (S0/S1/S2)
    - Top 5 violated rules with trend
    - Files/lines checked and violation density
    - Last check timestamp
    """
    from yuleosh.ci.rulesets import RulesetRegistry

    data: dict[str, Any] = {
        "misra_total": 0,
        "gscr_mapped": 0,
        "gscr_mapping_rate": 0.0,
        "s0_count": 0,
        "s1_count": 0,
        "s2_count": 0,
        "files_checked": 0,
        "lines_checked": 0,
        "violation_density": 0.0,
        "top5": [],
        "last_check": None,
    }

    # Try to load the latest extended compliance report
    ext_report_path = OSH_HOME / ".yuleosh" / "reports" / "gscr-extended-compliance.json"
    if ext_report_path.exists():
        try:
            report = json.loads(ext_report_path.read_text(encoding="utf-8"))
            data["misra_total"] = report.get("summary", {}).get("misra_total", 0)
            data["gscr_mapped"] = report.get("summary", {}).get("gscr_mapped", 0)
            data["gscr_mapping_rate"] = report.get("summary", {}).get("gscr_mapping_rate", 0.0)
            data["s0_count"] = report.get("summary", {}).get("s0_count", 0)
            data["s1_count"] = report.get("summary", {}).get("s1_count", 0)
            data["s2_count"] = report.get("summary", {}).get("s2_count", 0)
            data["files_checked"] = report.get("summary", {}).get("files_checked", 0)
            data["lines_checked"] = report.get("summary", {}).get("lines_checked", 0)
            data["violation_density"] = report.get("summary", {}).get("violation_density", 0.0)
            data["last_check"] = report.get("generated_at", None)
            data["top5"] = report.get("top5", [])
            return json_ok(data)
        except Exception as e:
            log.debug("Failed to load extended compliance report: %s", e)

    # Fallback: try misra-report.json
    misra_path = OSH_HOME / ".yuleosh" / "reports" / "misra-report.json"
    if misra_path.exists():
        try:
            report = json.loads(misra_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            data["misra_total"] = summary.get("total_violations", 0)
            data["s0_count"] = summary.get("severity_counts", {}).get("S0",
                           summary.get("misra_classification", {}).get("required", 0))
            data["s1_count"] = summary.get("severity_counts", {}).get("S1",
                           summary.get("misra_classification", {}).get("advisory", 0))
            data["files_checked"] = len(summary.get("unique_files", []))
            data["last_check"] = report.get("generated_at", None)

            # Top 5 from groups
            groups = report.get("groups", [])
            for g in sorted(groups, key=lambda x: x.get("count", 0), reverse=True)[:5]:
                data["top5"].append({
                    "rule_id": g.get("rule_id", ""),
                    "title": g.get("title", g.get("rule_id", "")),
                    "count": g.get("count", 0),
                    "trend": g.get("trend", "→"),
                })
        except Exception as e:
            log.debug("Failed to load MISRA report: %s", e)

    # Fallback: try trend data for line/file counts
    trend_path = OSH_HOME / ".yuleosh" / "reports" / "misra-trend.jsonl"
    if trend_path.exists() and data["files_checked"] == 0:
        try:
            lines = [l.strip() for l in trend_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            if lines:
                last = json.loads(lines[-1])
                data["files_checked"] = last.get("files_checked", 0)
                data["lines_checked"] = last.get("lines_checked", 0)
        except Exception:
            pass

    # GSCR mapping rate estimate
    if data["misra_total"] > 0:
        # Estimate mapped count - we check from ruleset
        try:
            registry = RulesetRegistry()
            composite = registry.create("gscr")
            violations = [{"rule_id": "misra-c2012-17.7"}] * data["misra_total"]
            mapped = composite.translate_violations(violations)
            mapped_count = sum(1 for v in mapped if v.get("gscr_rule_ids"))
            data["gscr_mapped"] = mapped_count
            data["gscr_mapping_rate"] = round(mapped_count / max(len(mapped), 1) * 100, 1)
        except Exception:
            data["gscr_mapping_rate"] = 0.0

    return json_ok(data)
