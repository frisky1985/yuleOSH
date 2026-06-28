#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — Trend.

Part of the kpi/ package split from kpi.py (Phase 2.2).
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.kpi")

from yuleosh.ci.kpi.utils import _parse_ts


BASELINE_FILE = Path(".yuleosh") / "kpi-baseline.json"
PROCESS_KPI_FILE = Path(".yuleosh") / "reports" / "process-kpi.jsonl"
DEFECT_ESCAPE_FILE = Path(".yuleosh") / "reports" / "defect-escape.jsonl"

# 默认阈值 (可根据实际项目调整)
DEFAULT_THRESHOLDS = {
    "misra_total_violations": 50,
    "misra_required_violations": 5,
    "misra_advisory_violations": 20,
    "c_line_coverage_pct": 80.0,
    "c_branch_coverage_pct": 70.0,
    "python_line_coverage_pct": 85.0,
    "python_branch_coverage_pct": 75.0,
    # G-49 过程稳定性 KPI 阈值
    "build_success_rate_pct": 95.0,         # §21.1: 构建成功率 ≥95%
    "regression_trigger_rate_pct": 5.0,     # §21.2: 回归触发率 ≤5%
    "required_fix_hours": 48.0,             # §21.4: Required 违规 48h 内修复/提偏差
    "advisory_fix_days": 15.0,              # §21.4: Advisory 违规 15d 内修复
    "defect_escape_rate_pct": 15.0,         # Sprint E: 缺陷逃逸率 ≤15%
}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------



def _get_misra_trend_avg(project_dir: str, days: int = 28) -> dict[str, float]:
    """Calculate average MISRA metrics over the last N days."""
    from yuleosh.ci.misra_trend import TREND_FILE as _misra_trend_file

    path = Path(project_dir) / _misra_trend_file
    if not path.exists():
        return {}

    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    if not entries:
        return {}

    cutoff = datetime.now() - timedelta(days=days)
    recent = [e for e in entries if _parse_ts(e.get("timestamp", "")) >= cutoff]
    if not recent:
        recent = entries[-28:] if len(entries) >= 28 else entries

    n = len(recent)
    if n == 0:
        return {}

    return {
        "avg_total_violations": round(sum(e.get("total_violations", 0) for e in recent) / n, 1),
        "avg_required": round(sum(e.get("required", 0) for e in recent) / n, 1),
        "avg_advisory": round(sum(e.get("advisory", 0) for e in recent) / n, 1),
        "min_total_violations": min(e.get("total_violations", 0) for e in recent),
        "max_total_violations": max(e.get("total_violations", 0) for e in recent),
        "entry_count": n,
    }

def _get_coverage_trend_avg(project_dir: str, days: int = 28) -> dict[str, float]:
    """Calculate average coverage metrics over the last N days."""
    from yuleosh.ci.coverage_trend import TREND_FILE as _cov_trend_file

    path = Path(project_dir) / _cov_trend_file
    if not path.exists():
        return {}

    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    if not entries:
        return {}

    cutoff = datetime.now() - timedelta(days=days)
    recent = [e for e in entries if _parse_ts(e.get("timestamp", "")) >= cutoff]
    if not recent:
        recent = entries[-28:] if len(entries) >= 28 else entries

    n = len(recent)
    if n == 0:
        return {}

    c_line_vals = [e.get("c", {}).get("line_rate") or 0 for e in recent]
    c_branch_vals = [e.get("c", {}).get("branch_rate") or 0 for e in recent]
    py_line_vals = [e.get("python", {}).get("line_rate") or 0 for e in recent]
    py_branch_vals = [e.get("python", {}).get("branch_rate") or 0 for e in recent]

    return {
        "avg_c_line_rate": round(sum(c_line_vals) / n, 1),
        "avg_c_branch_rate": round(sum(c_branch_vals) / n, 1),
        "avg_py_line_rate": round(sum(py_line_vals) / n, 1),
        "avg_py_branch_rate": round(sum(py_branch_vals) / n, 1),
        "entry_count": n,
    }

