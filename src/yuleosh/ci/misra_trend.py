#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
MISRA KPI / 违规趋势分析

每次 run_misra_check() 运行后在 .yuleosh/reports/misra-trend.jsonl 追加记录，
并提供趋势摘要 Markdown 表格。

Usage:
    from yuleosh.ci.misra_trend import append_entry, show_trend, get_violations_per_kloc
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.misra_trend")

TREND_FILE = Path(".yuleosh") / "reports" / "misra-trend.jsonl"


def _ensure_trend_dir(project_dir: str) -> Path:
    """Ensure the trend file directory exists and return the full path."""
    path = Path(project_dir) / TREND_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_entry(
    project_dir: str,
    total_violations: int,
    required: int = 0,
    advisory: int = 0,
    files_checked: int = 0,
    is_delta: bool = False,
    commit: str = "",
) -> None:
    """Append one trend entry to ``.yuleosh/reports/misra-trend.jsonl``.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    total_violations : int
        Total MISRA violations found.
    required : int
        Number of required (must-fix) violations.
    advisory : int
        Number of advisory violations.
    files_checked : int
        Number of C/C++ files scanned.
    is_delta : bool
        Whether this was an incremental (delta) check.
    commit : str
        Git commit hash (short form).
    """
    path = _ensure_trend_dir(project_dir)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "total_violations": total_violations,
        "required": required,
        "advisory": advisory,
        "files_checked": files_checked,
        "is_delta": is_delta,
        "commit": commit,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log.info("MISRA trend entry appended: %d violations", total_violations)


def show_trend(
    project_dir: str,
    lines: int = 30,
    days: int = 0,
    as_json: bool = False,
) -> str:
    """Return a Markdown table (or JSON) of the last N trend entries.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    lines : int
        Number of most recent entries to display (max, after day filter).
    days : int
        If > 0, filter to entries within this many days.
    as_json : bool
        Return JSON string instead of markdown table.

    Returns
    -------
    str
        Markdown-formatted trend table or JSON string.
    """
    path = Path(project_dir) / TREND_FILE
    if not path.exists():
        msg = f"*No trend data found at {path}*"
        return json.dumps({"error": msg}) if as_json else msg

    entries_raw: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries_raw.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    if not entries_raw:
        msg = "*No valid trend entries*"
        return json.dumps({"error": msg}) if as_json else msg

    # Filter by day range if requested
    if days > 0:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        entries_raw = [
            e for e in entries_raw
            if _parse_timestamp(e.get("timestamp", "")) >= cutoff
        ]

    if not entries_raw:
        msg = f"*No entries within the last {days} days*"
        return json.dumps({"error": msg}) if as_json else msg

    # Take the last N
    recent = entries_raw[-lines:]

    if as_json:
        result = {
            "total_entries": len(entries_raw),
            "returned_entries": len(recent),
            "entries": recent,
        }
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    rows = [
        "## MISRA 违规趋势",
        "",
        f"*最近 {len(recent)} 次检查（共 {len(entries_raw)} 次记录）*",
        "",
        "| # | 时间戳 | 总违规 | Required | Advisory | 文件数 | 增量 | Commit |",
        "|--:|:-------|-------:|---------:|---------:|-------:|:-----|:-------|",
    ]

    for idx, e in enumerate(recent, 1):
        ts = e.get("timestamp", "")[:19]  # Truncate to seconds
        total = e.get("total_violations", 0)
        req = e.get("required", 0)
        adv = e.get("advisory", 0)
        files = e.get("files_checked", 0)
        delta = "\u2713" if e.get("is_delta") else ""
        commit = e.get("commit", "")[:8]
        rows.append(
            f"| {idx} | {ts} | {total} | {req} | {adv} | {files} | {delta} | {commit} |"
        )

    rows.append("")
    return "\n".join(rows)


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO timestamp string, returning epoch (1970-01-01) on failure."""
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1)


def get_violations_per_kloc(violations: int, kloc: float) -> float:
    """Calculate violations per thousand lines of code (KLOC).

    Parameters
    ----------
    violations : int
        Number of MISRA violations.
    kloc : float
        Thousand lines of code (e.g. 5.2 for 5200 LOC).

    Returns
    -------
    float
        Density of violations per KLOC, rounded to 2 decimal places.
        Returns 0.0 if kloc <= 0.
    """
    if kloc <= 0:
        return 0.0
    return round(violations / kloc, 2)


def _print_trend_summary(project_dir: str, lines: int = 5) -> None:
    """Print a condensed trend summary to CI logs (used at end of run_misra_check)."""
    path = Path(project_dir) / TREND_FILE
    if not path.exists():
        return

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
        return

    recent = entries[-lines:]
    req_avg = sum(e.get("required", 0) for e in recent) / len(recent)
    adv_avg = sum(e.get("advisory", 0) for e in recent) / len(recent)
    total_avg = sum(e.get("total_violations", 0) for e in recent) / len(recent)

    print(f"\n    📈 MISRA Trend (last {len(recent)} runs):")
    print(f"       Avg total: {total_avg:.1f} | Avg Required: {req_avg:.1f} | Avg Advisory: {adv_avg:.1f}")
    latest = recent[-1]
    if len(recent) >= 2:
        prev_total = recent[-2].get("total_violations", 0)
        curr_total = latest.get("total_violations", 0)
        if curr_total > prev_total:
            direction = "↑"
        elif curr_total < prev_total:
            direction = "↓"
        else:
            direction = "→"
    else:
        direction = "−"
    print(f"       Latest: {latest.get('total_violations', 0)} violations {direction}")
    print()
