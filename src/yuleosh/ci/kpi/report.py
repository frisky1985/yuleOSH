#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — Report.

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

from yuleosh.ci.kpi.utils import _load_latest_misra_entry, _load_latest_coverage_entry, _load_baseline, _ensure_dir
from yuleosh.ci.kpi.trend import _get_misra_trend_avg, _get_coverage_trend_avg
from yuleosh.ci.kpi.stability import get_process_stability_summary
from yuleosh.ci.kpi.defects import get_defect_escape_summary


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
    process_kpi = get_process_stability_summary(project_dir, days=28, as_json=True)
    try:
        process_data = json.loads(process_kpi)
    except (json.JSONDecodeError, TypeError):
        process_data = {}

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

    # G-49: Process stability KPIs
    br = process_data.get("build_success_rate")
    if br is not None:
        status_entries.append({
            "metric": "build_success_rate",
            "label": "构建成功率 (28d)",
            "value": br,
            "threshold": thr["build_success_rate_pct"],
            "status": process_data.get("build_success_status", "PASS"),
            "unit": "%",
        })
    rr = process_data.get("regression_trigger_rate")
    if rr is not None:
        status_entries.append({
            "metric": "regression_trigger_rate",
            "label": "回归触发率 (28d)",
            "value": rr,
            "threshold": thr["regression_trigger_rate_pct"],
            "status": process_data.get("regression_status", "PASS"),
            "unit": "%",
        })

    # Sprint E: 缺陷逃逸率
    try:
        dr_json = get_defect_escape_summary(project_dir, days=90, as_json=True)
        dr_data = json.loads(dr_json)
    except (json.JSONDecodeError, TypeError):
        dr_data = {}
    er_val = dr_data.get("escape_rate")
    if er_val is not None:
        status_entries.append({
            "metric": "defect_escape_rate",
            "label": "缺陷逃逸率 (90d)",
            "value": er_val,
            "threshold": thr["defect_escape_rate_pct"],
            "status": dr_data.get("status", "PASS"),
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
            "process_stability": process_data,
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str, allow_nan=False)

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

    if process_data:
        rows.append("")
        rows.append("### 过程稳定性 KPI (28d)")
        rows.append("")
        rows.append(f"| 指标 | 28 天值 |")
        rows.append(f"|:-----|--------:|")
        rows.append(f"| 构建成功率 | {process_data.get('build_success_rate', 'N/A')}% |")
        rows.append(f"| 回归触发率 | {process_data.get('regression_trigger_rate', 'N/A')}% |")
        rows.append(f"| 平均构建时长 | {process_data.get('avg_build_duration_s', 'N/A')}s |")

    rows.append("")
    return "\n".join(rows)

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

    # Load process stability summary
    process_summary = {}
    try:
        ps_json = get_process_stability_summary(project_dir, days=28, as_json=True)
        process_summary = json.loads(ps_json)
    except (json.JSONDecodeError, TypeError):
        pass

    # Load defect escape summary
    dr_summary = {}
    try:
        dr_json = get_defect_escape_summary(project_dir, days=90, as_json=True)
        dr_summary = json.loads(dr_json)
    except (json.JSONDecodeError, TypeError):
        pass

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
        "process_stability_28d": {
            "build_success_rate": process_summary.get("build_success_rate"),
            "regression_trigger_rate": process_summary.get("regression_trigger_rate"),
            "avg_build_duration_s": process_summary.get("avg_build_duration_s"),
            "total_builds": process_summary.get("total_builds"),
        },
        "defect_escape_90d": {
            "escape_rate": dr_summary.get("escape_rate"),
            "total_defects": dr_summary.get("total_defects"),
            "total_escaped": dr_summary.get("total_escaped"),
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

