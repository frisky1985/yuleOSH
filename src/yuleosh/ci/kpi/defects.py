#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — Defects.

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



def _ensure_defect_escape_dir(project_dir: str) -> Path:
    """Ensure the defect escape JSONL file directory exists."""
    path = Path(project_dir) / DEFECT_ESCAPE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def record_defect_escape(
    project_dir: str,
    total_defects: int,
    escaped_defects: int,
    stage: str = "unknown",
    description: str = "",
) -> dict[str, Any]:
    """Record a defect escape entry.

    Tracks the number of defects found at customer/test stage (escaped)
    vs total defects found. Escape rate = escaped / total * 100.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    total_defects : int
        Total defects found (all stages).
    escaped_defects : int
        Defects found at customer or downstream test stage (escaped).
    stage : str
        Stage where escapement was detected (e.g. "customer", "system-test").
    description : str
        Optional description of the defect.

    Returns
    -------
    dict
        The recorded entry.
    """
    now = datetime.now()
    escape_rate = round(escaped_defects / total_defects * 100, 1) if total_defects > 0 else 0.0

    entry: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "total_defects": total_defects,
        "escaped_defects": escaped_defects,
        "escape_rate": escape_rate,
        "internal_defects": total_defects - escaped_defects,
        "stage": stage,
        "description": description,
    }

    path = _ensure_defect_escape_dir(project_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(
        "Defect escape recorded: escape_rate=%.1f%% (%d/%d escaped), stage=%s",
        escape_rate, escaped_defects, total_defects, stage,
    )
    return entry

def _load_defect_escape_entries(project_dir: str) -> list[dict]:
    """Load all defect escape entries from the JSONL file."""
    path = Path(project_dir) / DEFECT_ESCAPE_FILE
    if not path.exists():
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    return entries

def get_defect_escape_summary(
    project_dir: str,
    days: int = 90,
    as_json: bool = False,
) -> str:
    """Get defect escape rate summary.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    days : int
        Analysis window in days (default 90).
    as_json : bool
        Return JSON string instead of formatted table.

    Returns
    -------
    str
        Summary report.
    """
    entries = _load_defect_escape_entries(project_dir)
    if not entries:
        msg = "*No defect escape data found.*"
        return json.dumps({"error": msg}) if as_json else msg

    cutoff = datetime.now() - timedelta(days=days)
    recent = [e for e in entries if _parse_ts(e.get("timestamp", "")) >= cutoff]

    if not recent:
        msg = f"*No defect escape data within last {days} days.*"
        return json.dumps({"error": msg}) if as_json else msg

    total_defects = sum(e.get("total_defects", 0) for e in recent)
    total_escaped = sum(e.get("escaped_defects", 0) for e in recent)
    overall_escape_rate = round(total_escaped / total_defects * 100, 1) if total_defects > 0 else 0.0

    # Weighted average escape rate across entries
    weighted_rate = 0.0
    weights_sum = 0
    for e in recent:
        td = e.get("total_defects", 0)
        if td > 0:
            weighted_rate += e.get("escape_rate", 0) * td
            weights_sum += td
    avg_escape_rate = round(weighted_rate / weights_sum, 1) if weights_sum > 0 else 0.0

    # Trend: compare first half vs second half
    half = len(recent) // 2
    escape_trend = "→"
    if half > 0:
        first_half = recent[:half]
        second_half = recent[half:]
        fh_total = sum(e.get("total_defects", 0) for e in first_half)
        fh_escaped = sum(e.get("escaped_defects", 0) for e in first_half)
        sh_total = sum(e.get("total_defects", 0) for e in second_half)
        sh_escaped = sum(e.get("escaped_defects", 0) for e in second_half)
        fh_rate = round(fh_escaped / fh_total * 100, 1) if fh_total > 0 else 0
        sh_rate = round(sh_escaped / sh_total * 100, 1) if sh_total > 0 else 0
        escape_trend = "↑" if sh_rate > fh_rate else ("↓" if sh_rate < fh_rate else "→")

    result_data: dict[str, Any] = {
        "period_days": days,
        "total_entries": len(recent),
        "total_defects": total_defects,
        "total_escaped": total_escaped,
        "internal_defects": total_defects - total_escaped,
        "escape_rate": overall_escape_rate,
        "avg_escape_rate": avg_escape_rate,
        "threshold": DEFAULT_THRESHOLDS["defect_escape_rate_pct"],
        "trend": escape_trend,
        "status": "PASS" if overall_escape_rate <= DEFAULT_THRESHOLDS["defect_escape_rate_pct"] else "FAIL",
    }

    if as_json:
        return json.dumps(result_data, indent=2, ensure_ascii=False, default=str)

    icon = "✅" if result_data["status"] == "PASS" else "❌"
    rows = [
        "## 缺陷逃逸率 (Sprint E)",
        "",
        f"*分析周期: 近 {days} 天 ({len(recent)} 条记录)*",
        "",
        f"| 指标 | 当前值 | 阈值 | 状态 | 趋势 |",
        f"|:-----|-------:|-----:|:-----|:---:|",
        f"| 缺陷逃逸率 | {overall_escape_rate:.1f}% | "
        f"{DEFAULT_THRESHOLDS['defect_escape_rate_pct']:.0f}% | {icon} {result_data['status']} | {escape_trend} |",
        f"| 总缺陷数 | {total_defects} | — | — | — |",
        f"| 逃逸缺陷 | {total_escaped} | — | — | — |",
        f"| 内部发现 | {total_defects - total_escaped} | — | — | — |",
        "",
        "### 原始数据（最新 5 条）",
        "",
        "| # | 日期 | 总缺陷 | 逃逸 | 逃逸率 | 阶段 |",
        "|--:|:-----|:------:|:----:|:------:|:-----|",
    ]
    for idx, e in enumerate(recent[-5:], 1):
        rows.append(
            f"| {idx} | {e.get('date', '')[:10]} | {e.get('total_defects', 0)} | "
            f"{e.get('escaped_defects', 0)} | {e.get('escape_rate', 0):.1f}% | "
            f"{e.get('stage', '')} |"
        )
    rows.append("")
    return "\n".join(rows)

