#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
KPI 基线采集引擎 (E08/E09)

提供统一的 KPI 状态查询、基线保存/对比功能，整合 MISRA 趋势
和覆盖率趋势两大数据源。

Usage:
    from yuleosh.ci.kpi import kpi_status, kpi_baseline_save, kpi_baseline_compare
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.kpi")

BASELINE_FILE = Path(".yuleosh") / "kpi-baseline.json"

# 默认阈值 (可根据实际项目调整)
DEFAULT_THRESHOLDS = {
    "misra_total_violations": 50,
    "misra_required_violations": 5,
    "misra_advisory_violations": 20,
    "c_line_coverage_pct": 80.0,
    "c_branch_coverage_pct": 70.0,
    "python_line_coverage_pct": 85.0,
    "python_branch_coverage_pct": 75.0,
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


def _parse_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp, returning epoch on failure."""
    try:
        return datetime.fromisoformat(ts_str)
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


# ------------------------------------------------------------------
# Public API — KPI status
# ------------------------------------------------------------------


def kpi_status(
    project_dir: str,
    as_json: bool = False,
    thresholds: Optional[dict[str, Any]] = None,
) -> str:
    """Show current KPI dashboard — violations, coverage, and trend info.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    as_json : bool
        Return JSON string instead of formatted table.
    thresholds : dict, optional
        Custom threshold overrides (merged with defaults).

    Returns
    -------
    str
        Formatted dashboard or JSON.
    """
    misra_latest = _load_latest_misra_entry(project_dir)
    cov_latest = _load_latest_coverage_entry(project_dir)
    misra_avg = _get_misra_trend_avg(project_dir, days=28)
    cov_avg = _get_coverage_trend_avg(project_dir, days=28)

    thr = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    # Evaluate current vs thresholds
    status_entries: list[dict[str, Any]] = []

    # MISRA
    total_v = misra_latest.get("total_violations", 0)
    req_v = misra_latest.get("required", 0)
    adv_v = misra_latest.get("advisory", 0)

    status_entries.append({
        "metric": "misra_total_violations",
        "label": "MISRA 总违规",
        "value": total_v,
        "threshold": thr["misra_total_violations"],
        "status": "PASS" if total_v <= thr["misra_total_violations"] else "FAIL",
        "unit": "count",
    })
    status_entries.append({
        "metric": "misra_required_violations",
        "label": "MISRA Required 违规",
        "value": req_v,
        "threshold": thr["misra_required_violations"],
        "status": "PASS" if req_v <= thr["misra_required_violations"] else "FAIL",
        "unit": "count",
    })
    status_entries.append({
        "metric": "misra_advisory_violations",
        "label": "MISRA Advisory 违规",
        "value": adv_v,
        "threshold": thr["misra_advisory_violations"],
        "status": "PASS" if adv_v <= thr["misra_advisory_violations"] else "FAIL",
        "unit": "count",
    })

    # Coverage — C
    c = cov_latest.get("c", {})
    c_line = c.get("line_rate")
    c_branch = c.get("branch_rate")
    if c_line is not None:
        status_entries.append({
            "metric": "c_line_coverage_pct",
            "label": "C Line 覆盖率",
            "value": c_line,
            "threshold": thr["c_line_coverage_pct"],
            "status": "PASS" if c_line >= thr["c_line_coverage_pct"] else "FAIL",
            "unit": "%",
        })
    if c_branch is not None:
        status_entries.append({
            "metric": "c_branch_coverage_pct",
            "label": "C Branch 覆盖率",
            "value": c_branch,
            "threshold": thr["c_branch_coverage_pct"],
            "status": "PASS" if c_branch >= thr["c_branch_coverage_pct"] else "FAIL",
            "unit": "%",
        })

    # Coverage — Python
    py = cov_latest.get("python", {})
    py_line = py.get("line_rate")
    py_branch = py.get("branch_rate")
    if py_line is not None:
        status_entries.append({
            "metric": "python_line_coverage_pct",
            "label": "Python Line 覆盖率",
            "value": py_line,
            "threshold": thr["python_line_coverage_pct"],
            "status": "PASS" if py_line >= thr["python_line_coverage_pct"] else "FAIL",
            "unit": "%",
        })
    if py_branch is not None:
        status_entries.append({
            "metric": "python_branch_coverage_pct",
            "label": "Python Branch 覆盖率",
            "value": py_branch,
            "threshold": thr["python_branch_coverage_pct"],
            "status": "PASS" if py_branch >= thr["python_branch_coverage_pct"] else "FAIL",
            "unit": "%",
        })

    if as_json:
        result = {
            "timestamp": datetime.now().isoformat(),
            "project_dir": project_dir,
            "thresholds": thr,
            "entries": status_entries,
            "trend_28d": {
                "misra": misra_avg,
                "coverage": cov_avg,
            },
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    # Render as Markdown table
    pass_count = sum(1 for e in status_entries if e["status"] == "PASS")
    fail_count = sum(1 for e in status_entries if e["status"] == "FAIL")
    total_checks = len(status_entries)
    overall = "✅ ALL PASS" if fail_count == 0 else f"⚠️  {fail_count}/{total_checks} FAILING"

    rows = [
        "## KPI Dashboard",
        "",
        f"*整体状态: {overall} (PASS {pass_count}/{total_checks})*",
        "",
        "| Metric | 当前值 | 阈值 | 状态 |",
        "|:-------|-------:|-----:|:-----|",
    ]

    for e in status_entries:
        val_str = f"{e['value']:.1f} {e['unit']}" if isinstance(e["value"], (int, float)) else f"{e['value']} {e['unit']}"
        thr_str = f"{e['threshold']:.1f} {e['unit']}" if isinstance(e["threshold"], (int, float)) else f"{e['threshold']} {e['unit']}"
        icon = "✅" if e["status"] == "PASS" else "❌"
        rows.append(f"| {e['label']} | {val_str} | {thr_str} | {icon} {e['status']} |")

    # Trend summary
    if misra_avg:
        rows.append("")
        rows.append("### 28 天 MISRA 趋势均值")
        rows.append("")
        rows.append(f"| 指标 | 28 日均值 |")
        rows.append(f"|:-----|----------:|")
        rows.append(f"| 平均总违规 | {misra_avg.get('avg_total_violations', 'N/A')} |")
        rows.append(f"| 平均 Required | {misra_avg.get('avg_required', 'N/A')} |")
        rows.append(f"| 平均 Advisory | {misra_avg.get('avg_advisory', 'N/A')} |")
        rows.append(f"| 最小违规 | {misra_avg.get('min_total_violations', 'N/A')} |")
        rows.append(f"| 最大违规 | {misra_avg.get('max_total_violations', 'N/A')} |")
        rows.append(f"| 条目数 | {misra_avg.get('entry_count', 0)} |")

    if cov_avg:
        rows.append("")
        rows.append("### 28 天覆盖率趋势均值")
        rows.append("")
        rows.append(f"| 指标 | 28 日均值 |")
        rows.append(f"|:-----|----------:|")
        rows.append(f"| C Line | {cov_avg.get('avg_c_line_rate', 'N/A')}% |")
        rows.append(f"| C Branch | {cov_avg.get('avg_c_branch_rate', 'N/A')}% |")
        rows.append(f"| Python Line | {cov_avg.get('avg_py_line_rate', 'N/A')}% |")
        rows.append(f"| Python Branch | {cov_avg.get('avg_py_branch_rate', 'N/A')}% |")
        rows.append(f"| 条目数 | {cov_avg.get('entry_count', 0)} |")

    rows.append("")
    return "\n".join(rows)


# ------------------------------------------------------------------
# Public API — KPI baseline save / compare
# ------------------------------------------------------------------


def kpi_baseline_save(
    project_dir: str,
    label: str = "",
) -> dict[str, Any]:
    """Save current KPI state as a baseline snapshot.

    Captures the latest MISRA and coverage values as a repeatable baseline
    for future comparison.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    label : str
        Optional human-readable label for this baseline (e.g. "sprint-12").

    Returns
    -------
    dict
        The saved baseline data.
    """
    misra_latest = _load_latest_misra_entry(project_dir)
    cov_latest = _load_latest_coverage_entry(project_dir)
    misra_avg = _get_misra_trend_avg(project_dir, days=28)
    cov_avg = _get_coverage_trend_avg(project_dir, days=28)

    baseline = {
        "baseline_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "label": label,
        "saved_at": datetime.now().isoformat(),
        "project_dir": project_dir,
        "snapshot": {
            "misra": {
                "total_violations": misra_latest.get("total_violations", 0),
                "required": misra_latest.get("required", 0),
                "advisory": misra_latest.get("advisory", 0),
                "files_checked": misra_latest.get("files_checked", 0),
                "commit": misra_latest.get("commit", ""),
                "timestamp": misra_latest.get("timestamp", ""),
            },
            "coverage": {
                "c_line_rate": cov_latest.get("c", {}).get("line_rate"),
                "c_branch_rate": cov_latest.get("c", {}).get("branch_rate"),
                "python_line_rate": cov_latest.get("python", {}).get("line_rate"),
                "python_branch_rate": cov_latest.get("python", {}).get("branch_rate"),
                "commit": cov_latest.get("commit", ""),
                "timestamp": cov_latest.get("timestamp", ""),
            },
        },
        "trend_28d": {
            "misra": misra_avg,
            "coverage": cov_avg,
        },
        "thresholds": DEFAULT_THRESHOLDS,
    }

    path = Path(project_dir) / BASELINE_FILE
    _ensure_dir(project_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False, default=str)

    log.info(
        "KPI baseline saved: %s (label=%r, misra=%d, c_line=%s)",
        baseline["baseline_id"],
        label,
        baseline["snapshot"]["misra"]["total_violations"],
        baseline["snapshot"]["coverage"]["c_line_rate"],
    )
    return baseline


def kpi_baseline_compare(
    project_dir: str,
    as_json: bool = False,
) -> str:
    """Compare current KPI state against the saved baseline.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    as_json : bool
        Return JSON string instead of formatted table.

    Returns
    -------
    str
        Formatted comparison table or JSON.
    """
    baseline = _load_baseline(project_dir)
    if baseline is None:
        msg = "*No KPI baseline found. Run `yuleosh kpi baseline save` first.*"
        return json.dumps({"error": msg}) if as_json else msg

    current_misra = _load_latest_misra_entry(project_dir)
    current_cov = _load_latest_coverage_entry(project_dir)
    now = datetime.now().isoformat()

    base_misra = baseline.get("snapshot", {}).get("misra", {})
    base_cov = baseline.get("snapshot", {}).get("coverage", {})

    def _diff_val(current, baseline_val, lower_is_better: bool = False):
        """Return direction arrow. lower_is_better=True for violations."""
        if current is None or baseline_val is None:
            return "—", 0.0
        diff = current - baseline_val
        if lower_is_better:
            direction = "↓" if diff < 0 else ("↑" if diff > 0 else "→")
        else:
            direction = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
        return direction, diff

    comparisons: list[dict[str, Any]] = []
    metrics = [
        # (metric_name, label, current_fn, base_fn, lower_is_better)
        ("misra_total_violations", "MISRA 总违规",
         current_misra.get("total_violations", 0), base_misra.get("total_violations", 0), True),
        ("misra_required", "MISRA Required",
         current_misra.get("required", 0), base_misra.get("required", 0), True),
        ("misra_advisory", "MISRA Advisory",
         current_misra.get("advisory", 0), base_misra.get("advisory", 0), True),
        ("c_line_rate", "C Line 覆盖率",
         current_cov.get("c", {}).get("line_rate"),
         base_cov.get("c_line_rate"), False),
        ("c_branch_rate", "C Branch 覆盖率",
         current_cov.get("c", {}).get("branch_rate"),
         base_cov.get("c_branch_rate"), False),
        ("py_line_rate", "Python Line 覆盖率",
         current_cov.get("python", {}).get("line_rate"),
         base_cov.get("python_line_rate"), False),
        ("py_branch_rate", "Python Branch 覆盖率",
         current_cov.get("python", {}).get("branch_rate"),
         base_cov.get("python_branch_rate"), False),
    ]

    for metric, label, curr_val, base_val, lower_better in metrics:
        direction, diff = _diff_val(curr_val, base_val, lower_better)
        comparisons.append({
            "metric": metric,
            "label": label,
            "baseline": base_val,
            "current": curr_val,
            "diff": diff,
            "direction": direction,
        })

    if as_json:
        result = {
            "timestamp": now,
            "baseline_id": baseline.get("baseline_id", ""),
            "baseline_label": baseline.get("label", ""),
            "baseline_saved_at": baseline.get("saved_at", ""),
            "comparisons": comparisons,
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    # Render as markdown
    bl_label = baseline.get("label", "")
    bl_id = baseline.get("baseline_id", "")
    bl_ts = (baseline.get("saved_at", "") or "")[:19]

    header = f"基线: {bl_label}" if bl_label else f"基线 ID: {bl_id}"
    rows = [
        "## KPI 基线对比",
        "",
        f"*{header} (保存于 {bl_ts})*",
        "",
        "| Metric | 基线值 | 当前值 | 差值 | 趋势 |",
        "|:-------|-------:|-------:|-----:|:---:|",
    ]

    worse_count = 0
    for c in comparisons:
        base = c["baseline"]
        curr = c["current"]
        diff = c["diff"]
        direction = c["direction"]

        base_str = f"{base:.1f}" if base is not None else "—"
        curr_str = f"{curr:.1f}" if curr is not None else "—"
        diff_str = f"{diff:+.1f}" if isinstance(diff, (int, float)) and curr is not None else "—"

        if direction == "↑" and c["metric"].startswith("misra"):
            worse_count += 1
        elif direction == "↓" and not c["metric"].startswith("misra"):
            worse_count += 1

        rows.append(f"| {c['label']} | {base_str} | {curr_str} | {diff_str} | {direction} |")

    rows.append("")
    if worse_count > 0:
        rows.append(f"⚠️  {worse_count} 项指标恶化.")
    else:
        rows.append("✅ 所有指标相较基线持平或改善.")

    rows.append("")
    return "\n".join(rows)
