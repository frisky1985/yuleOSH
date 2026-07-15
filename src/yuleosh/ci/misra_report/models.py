#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI MISRA Report — Models.

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


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------



@dataclass
class MisraViolation:
    """A single MISRA rule violation."""
    rule_id: str
    category: str  # "Required" | "Advisory"
    file: str
    line: int
    message: str
    severity: str = "medium"  # "high" | "medium" | "low" | "info"
    fix_proposed: str = ""
    suppressed: bool = False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
            "fix_proposed": self.fix_proposed,
            "suppressed": self.suppressed,
        }


@dataclass
class MisraSummary:
    """Aggregated MISRA analysis summary."""
    violations: list = field(default_factory=list)
    max_allowed_critical: int = 0
    max_allowed_total: int = 10

    @property
    def total_violations(self) -> int:
        return len(self.violations)

    @property
    def high_severity(self) -> int:
        return sum(1 for v in self.violations if v.severity == "high")

    @property
    def medium_severity(self) -> int:
        return sum(1 for v in self.violations if v.severity == "medium")

    @property
    def low_severity(self) -> int:
        return sum(1 for v in self.violations if v.severity == "low")

    @property
    def passed(self) -> bool:
        return (self.high_severity <= self.max_allowed_critical and
                self.total_violations <= self.max_allowed_total)


@dataclass
class ToolResult:
    """Result from a single MISRA analysis tool.

    Attributes
    ----------
    tool_name : str
        Tool identifier: "cppcheck" | "clang-tidy" | "ai-review" | etc.
    violations : list[dict]
        Parsed violation dicts (same format as parse_cppcheck_output returns).
    status : str
        Execution status: "passed" | "failed" | "skipped".
    """
    tool_name: str = ""
    violations: list[dict] = field(default_factory=list)
    status: str = "skipped"


def merge_tool_results(results: list[ToolResult]) -> dict:
    """Merge multiple tool results into a unified report.

    Deduplicates same rule/file/line/col combinations across tools,
    tags each violation with its source tool(s), and computes combined
    statistics.

    Parameters
    ----------
    results : list[ToolResult]
        Tool results from cppcheck, clang-tidy, AI-review, etc.

    Returns
    -------
    dict with keys:
        - merged_violations: list of unified violation dicts
        - combined_stats: combined summary statistics
        - tool_contributions: per-tool violation counts
    """
    seen: dict[tuple, dict] = {}
    tool_contributions: dict[str, int] = {}

    for tr in results:
        tool_contributions[tr.tool_name] = tool_contributions.get(tr.tool_name, 0) + len(tr.violations)
        for v in tr.violations:
            # Dedup key: (rule_id, file, line, col)
            key = (v.get("rule_id", ""), v.get("file", ""), v.get("line", 0), v.get("col", 0))
            if key in seen:
                # Merge tags — append tool if not already listed
                existing = seen[key]
                tools_set = set(existing.get("_tools", [tr.tool_name]))
                tools_set.add(tr.tool_name)
                existing["_tools"] = sorted(tools_set)
            else:
                v["_tools"] = [tr.tool_name]
                seen[key] = v

    merged = list(seen.values())

    # Combined stats
    total_violations = len(merged)
    severity_counts: dict[str, int] = defaultdict(int)
    unique_files: set[str] = set()

    for v in merged:
        sev = v.get("severity", "unknown")
        severity_counts[sev] += 1
        fname = v.get("file", "")
        if fname:
            unique_files.add(fname)

    return {
        "merged_violations": merged,
        "combined_stats": {
            "total_violations": total_violations,
            "total_tools": len(results),
            "severity_counts": dict(severity_counts),
            "unique_files": sorted(unique_files),
        },
        "tool_contributions": tool_contributions,
        "tool_statuses": {tr.tool_name: tr.status for tr in results},
    }
