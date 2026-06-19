#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
KPI 基线采集引擎 (E08/E09) — 含过程稳定性 KPI (G-49)

提供统一的 KPI 状态查询、基线保存/对比、过程稳定性 KPI 采集功能。

DEF-011 (G-49) 扩展:
    - 构建成功率采集 (build_success_rate) — §21.1
    - 回归触发率采集 (regression_trigger_rate) — §21.2
    - 违规修复时效跟踪 (violation_fix_timeliness) — §21.4
    - 3类KPI自动采集≥2周生成基线报告

Usage:
    from yuleosh.ci.kpi import kpi_status, kpi_baseline_save, kpi_baseline_compare
    from yuleosh.ci.kpi import record_process_stability, get_process_stability_summary
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
PROCESS_KPI_FILE = Path(".yuleosh") / "reports" / "process-kpi.jsonl"

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


# ═══════════════════════════════════════════════════════════════════════
# DEF-011 / G-49: 过程稳定性 KPI 采集
# ═══════════════════════════════════════════════════════════════════════


def _ensure_process_kpi_dir(project_dir: str) -> Path:
    """Ensure the process KPI JSONL file directory exists."""
    path = Path(project_dir) / PROCESS_KPI_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_process_stability(
    project_dir: str,
    build_success: bool = True,
    build_duration_s: float = 0.0,
    layer: int = 1,
    total_stages: int = 0,
    passed_stages: int = 0,
    misra_required_new: int = 0,
    misra_total: int = 0,
) -> dict[str, Any]:
    """Record a process stability KPI entry (G-49: §21.1~§21.4).

    Tracks:
    - Build success/fail per invocation (§21.1)
    - Regression trigger rate (failed tests / total stages) (§21.2)
    - Violation fix timeliness baseline (§21.4)

    Parameters
    ----------
    project_dir : str
        Project root directory.
    build_success : bool
        Whether the build/layer succeeded.
    build_duration_s : float
        Build duration in seconds.
    layer : int
        CI layer number.
    total_stages : int
        Total stages in the layer.
    passed_stages : int
        Stages that passed.
    misra_required_new : int
        New Required violations found in this build.
    misra_total : int
        Total MISRA violations in this build.

    Returns
    -------
    dict
        The recorded entry.
    """
    now = datetime.now()
    entry: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "build_success": build_success,
        "build_duration_s": round(build_duration_s, 1),
        "layer": layer,
        "total_stages": total_stages,
        "passed_stages": passed_stages,
        "failed_stages": total_stages - passed_stages,
        "regression_triggered": (not build_success) and passed_stages < total_stages,
        "misra_required_new": misra_required_new,
        "misra_total": misra_total,
    }

    # Append to process KPI JSONL
    path = _ensure_process_kpi_dir(project_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(
        "Process KPI recorded: build_success=%s, regress=%s, layer=%d, duration=%.1fs",
        build_success,
        entry["regression_triggered"],
        layer,
        build_duration_s,
    )
    return entry


def _load_process_kpi_entries(project_dir: str) -> list[dict]:
    """Load all process KPI entries from the JSONL file."""
    path = Path(project_dir) / PROCESS_KPI_FILE
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


def get_process_stability_summary(
    project_dir: str,
    days: int = 14,
    as_json: bool = False,
) -> str:
    """Get a summary of process stability KPIs over the last N days.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    days : int
        Number of days to analyze (default 14).
    as_json : bool
        Return JSON string instead of formatted table.

    Returns
    -------
    str
        Formatted summary or JSON.
    """
    entries = _load_process_kpi_entries(project_dir)
    if not entries:
        msg = "*No process stability KPI data found.*"
        return json.dumps({"error": msg}) if as_json else msg

    # Filter by day range
    cutoff = datetime.now() - timedelta(days=days)
    recent = [e for e in entries if _parse_ts(e.get("timestamp", "")) >= cutoff]

    if not recent:
        msg = f"*No process stability data within the last {days} days.*"
        return json.dumps({"error": msg}) if as_json else msg

    n = len(recent)
    success_count = sum(1 for e in recent if e.get("build_success", False))
    regression_count = sum(1 for e in recent if e.get("regression_triggered", False))
    total_new_required = sum(e.get("misra_required_new", 0) for e in recent)

    build_success_rate = round(success_count / n * 100, 1) if n > 0 else 0.0
    regression_rate = round(regression_count / n * 100, 1) if n > 0 else 0.0
    avg_duration = round(sum(e.get("build_duration_s", 0) for e in recent) / n, 1) if n > 0 else 0.0

    # Trend direction
    half = n // 2
    if half > 0:
        recent_first = recent[:half]
        recent_second = recent[half:]
        first_success = sum(1 for e in recent_first if e.get("build_success", False))
        second_success = sum(1 for e in recent_second if e.get("build_success", False))
        first_rate = first_success / len(recent_first) * 100
        second_rate = second_success / len(recent_second) * 100
        success_trend = "↑" if second_rate > first_rate else ("↓" if second_rate < first_rate else "→")
    else:
        success_trend = "→"

    result_data: dict[str, Any] = {
        "period_days": days,
        "total_builds": n,
        "build_success_rate": build_success_rate,
        "build_success_rate_threshold": DEFAULT_THRESHOLDS["build_success_rate_pct"],
        "regression_trigger_rate": regression_rate,
        "regression_trigger_rate_threshold": DEFAULT_THRESHOLDS["regression_trigger_rate_pct"],
        "total_new_required_violations": total_new_required,
        "avg_build_duration_s": avg_duration,
        "success_trend": success_trend,
    }

    # Check thresholds
    if build_success_rate < DEFAULT_THRESHOLDS["build_success_rate_pct"]:
        result_data["build_success_status"] = "FAIL"
    else:
        result_data["build_success_status"] = "PASS"

    if regression_rate > DEFAULT_THRESHOLDS["regression_trigger_rate_pct"]:
        result_data["regression_status"] = "FAIL"
    else:
        result_data["regression_status"] = "PASS"

    if total_new_required > 0:
        result_data["fix_timeliness_hours"] = DEFAULT_THRESHOLDS["required_fix_hours"]
        result_data["fix_timeliness_status"] = "PENDING"  # Requires deviation tracking

    if as_json:
        return json.dumps(result_data, indent=2, ensure_ascii=False, default=str)

    # Render as Markdown
    rows = [
        "## 过程稳定性 KPI 基线 (G-49)",
        "",
        f"*分析周期: 近 {days} 天 ({n} 次构建)*",
        "",
        f"| 指标 | 当前值 | 阈值 | 状态 | 趋势 |",
        f"|:-----|-------:|-----:|:-----|:---:|",
    ]

    success_status_icon = "✅" if result_data["build_success_status"] == "PASS" else "❌"
    reg_status_icon = "✅" if result_data["regression_status"] == "PASS" else "❌"

    rows.append(
        f"| 构建成功率 | {build_success_rate:.1f}% | "
        f"{DEFAULT_THRESHOLDS['build_success_rate_pct']:.0f}% | "
        f"{success_status_icon} {result_data['build_success_status']} | {success_trend} |"
    )
    rows.append(
        f"| 回归触发率 | {regression_rate:.1f}% | "
        f"{DEFAULT_THRESHOLDS['regression_trigger_rate_pct']:.0f}% | "
        f"{reg_status_icon} {result_data['regression_status']} | — |"
    )
    rows.append(
        f"| 新增 Required 违规 | {total_new_required} | "
        f"0 | {'❌' if total_new_required > 0 else '✅'} "
        f"{result_data['fix_timeliness_status']} | — |"
    )
    rows.append(f"| 平均构建时长 | {avg_duration:.1f}s | — | — | — |")

    rows.append("")
    rows.append("### 原始数据（最新 5 条）")
    rows.append("")
    rows.append("| # | 时间 | 成功 | 层 | 阶段通过 | 时长(s) | Required新增 |")
    rows.append("|--:|:-----|:----:|:--:|:--------:|:--------:|:------------:|")
    for idx, e in enumerate(recent[-5:], 1):
        ts = e.get("timestamp", "")[:16]
        success = "✅" if e.get("build_success", False) else "❌"
        rows.append(
            f"| {idx} | {ts} | {success} | {e.get('layer', '?')} | "
            f"{e.get('passed_stages', 0)}/{e.get('total_stages', 0)} | "
            f"{e.get('build_duration_s', 0):.1f} | {e.get('misra_required_new', 0)} |"
        )

    rows.append("")
    return "\n".join(rows)


def generate_process_baseline_report(project_dir: str, label: str = "") -> str:
    """Generate a process stability baseline report (≥2 weeks data required).

    Creates a markdown report in ``.yuleosh/reports/process-baseline-report.md``.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    label : str
        Optional label for the baseline report.

    Returns
    -------
    str
        Path to the generated report.
    """
    entries = _load_process_kpi_entries(project_dir)
    if len(entries) < 14:
        log.warning(
            "Insufficient data for process baseline: need ≥14 entries, got %d",
            len(entries),
        )

    n = max(len(entries), 1)

    # Full statistics
    success_count = sum(1 for e in entries if e.get("build_success", False))
    regression_count = sum(1 for e in entries if e.get("regression_triggered", False))
    durations = [e.get("build_duration_s", 0) for e in entries]
    required_new_counts = [e.get("misra_required_new", 0) for e in entries]

    build_success_rate = round(success_count / n * 100, 1)
    regression_rate = round(regression_count / n * 100, 1)

    sorted_durations = sorted(durations)
    builds_with_required = sum(1 for e in entries if e.get("misra_required_new", 0) > 0)
    pct_with_required = round(builds_with_required / n * 100, 1) if n > 0 else 0.0

    # UCL / LCL for build duration
    mean_duration = sum(durations) / n
    if n > 1:
        variance = sum((d - mean_duration) ** 2 for d in durations) / (n - 1)
        std_duration = variance ** 0.5
        ucl = mean_duration + 3 * std_duration
        lcl = max(0, mean_duration - 3 * std_duration)
    else:
        std_duration = 0
        ucl = mean_duration
        lcl = mean_duration

    now = datetime.now()
    report_path = Path(project_dir) / ".yuleosh" / "reports" / "process-baseline-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""# 过程稳定性 KPI 基线报告

**生成时间**: {now.isoformat()[:19]}
**标签**: {label or '未命名'}
**数据周期**: {len(entries)} 次构建

---

## 1. 构建成功率

| 指标 | 值 |
|:-----|---:|
| 总构建次数 | {n} |
| 成功次数 | {success_count} |
| 失败次数 | {n - success_count} |
| 成功率 | {build_success_rate}% |
| 阈值 | {DEFAULT_THRESHOLDS['build_success_rate_pct']}% |
| 判定 | {"✅ PASS" if build_success_rate >= DEFAULT_THRESHOLDS['build_success_rate_pct'] else "❌ FAIL"} |

## 2. 回归触发率

| 指标 | 值 |
|:-----|---:|
| 回归触发次数 | {regression_count} |
| 回归触发率 | {regression_rate}% |
| 阈值 | {DEFAULT_THRESHOLDS['regression_trigger_rate_pct']}% |
| 判定 | {"✅ PASS" if regression_rate <= DEFAULT_THRESHOLDS['regression_trigger_rate_pct'] else "❌ FAIL"} |

## 3. 违规修复时效

| 指标 | 值 |
|:-----|---:|
| 新增 Required 违规总数 | {sum(required_new_counts)} |
| 带 Required 违规的构建数 | {pct_with_required}% |
| Required 修复时限 | {DEFAULT_THRESHOLDS['required_fix_hours']:.0f}h |
| Advisory 修复时限 | {DEFAULT_THRESHOLDS['advisory_fix_days']:.0f}d |

## 4. 构建时长统计

| 指标 | 值 |
|:-----|---:|
| 均值 | {mean_duration:.1f}s |
| 标准差 | {std_duration:.1f}s |
| P50 (中位数) | {sorted_durations[n//2]:.1f}s |
| P90 | {sorted_durations[int(n*0.9)-1]:.1f}s |
| UCL | {ucl:.1f}s |
| LCL | {lcl:.1f}s |
| 最长时间 | {max(durations):.1f}s |
| 最短时间 | {min(durations):.1f}s |

## 5. 汇总判定

| 判定项 | 状态 |
|:-------|:----:|
| 构建成功率 ≥{DEFAULT_THRESHOLDS['build_success_rate_pct']:.0f}% | {"✅" if build_success_rate >= DEFAULT_THRESHOLDS['build_success_rate_pct'] else "❌"} |
| 回归触发率 ≤{DEFAULT_THRESHOLDS['regression_trigger_rate_pct']:.0f}% | {"✅" if regression_rate <= DEFAULT_THRESHOLDS['regression_trigger_rate_pct'] else "❌"} |
| Required 违规修复跟踪 | {"✅" if sum(required_new_counts) == 0 else "⚠️ 存在待修复"} |
"""

    # Report for daily entries
    content += "\n## 6. 每日明细\n\n"
    content += "| 日期 | 构建成功 | 阶段通过 | 时长(s) | Required新增 |\n"
    content += "|:-----|:--------:|:--------:|:-------:|:------------:|\n"

    daily: dict[str, dict] = {}
    for e in entries:
        date = e.get("date", e.get("timestamp", "")[:10])
        if date not in daily:
            daily[date] = {
                "builds": 0,
                "successes": 0,
                "total_stages": 0,
                "passed_stages": 0,
                "total_duration": 0.0,
                "total_required_new": 0,
            }
        day = daily[date]
        day["builds"] += 1
        if e.get("build_success"):
            day["successes"] += 1
        day["total_stages"] += e.get("total_stages", 0)
        day["passed_stages"] += e.get("passed_stages", 0)
        day["total_duration"] += e.get("build_duration_s", 0)
        day["total_required_new"] += e.get("misra_required_new", 0)

    for date in sorted(daily.keys()):
        d = daily[date]
        content += f"| {date} | {d['successes']}/{d['builds']} | {d['passed_stages']}/{d['total_stages']} | {d['total_duration']:.1f} | {d['total_required_new']} |\n"

    report_path.write_text(content, encoding="utf-8")
    log.info("Process stability baseline report saved: %s", report_path)
    return str(report_path)


# ═══════════════════════════════════════════════════════════════════════
# Public API — KPI status
# ═══════════════════════════════════════════════════════════════════════


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

    # Load process stability summary
    process_summary = {}
    try:
        ps_json = get_process_stability_summary(project_dir, days=28, as_json=True)
        process_summary = json.loads(ps_json)
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
