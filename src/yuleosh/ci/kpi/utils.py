#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — Utils.

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
    # KG 知识图谱 KPI 阈值
    "kg_coverage_pct": 80.0,               # KG 需求覆盖率 ≥80%
    "kg_health_min_nodes": 10,              # KG 最小节点数
    "kg_health_max_orphan_pct": 20.0,       # 孤立文件比例 ≤20%
    "kg_confidence_min": 0.8,              # 最低平均置信度 ≥0.8
    "kg_confidence_explicit_pct": 50.0,    # 显式追溯占边数比例 ≥50%
}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------



def _ensure_dir(project_dir: str) -> Path:
    """Ensure .yuleosh/ directory exists."""
    path = Path(project_dir) / ".yuleosh"
    path.mkdir(parents=True, exist_ok=True)
    return path

def _load_latest_misra_entry(project_dir: str) -> dict[str, Any]:
    """Load the most recent MISRA trend entry."""
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
    return entries[-1] if entries else {}

def _load_latest_coverage_entry(project_dir: str) -> dict[str, Any]:
    """Load the most recent coverage trend entry."""
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
    return entries[-1] if entries else {}

def _parse_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp, returning epoch on failure.

    Strips timezone info so all comparisons are naive vs naive.
    """
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1)

def _load_baseline(project_dir: str) -> Optional[dict]:
    """Load the saved KPI baseline, if it exists."""
    path = Path(project_dir) / BASELINE_FILE
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cannot read KPI baseline: %s", e)
        return None

