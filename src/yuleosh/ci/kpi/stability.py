#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — Stability.

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

