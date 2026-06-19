# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
覆盖趋势基线 (E04).

每次运行后记录 C 覆盖率和 Python 覆盖率到 ``.yuleosh/reports/coverage-trend.jsonl``，
并提供 CLI 命令展示覆盖趋势表格。

Usage:
    from yuleosh.ci.coverage_trend import record_coverage, show_coverage_trend
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.coverage_trend")

TREND_FILE = Path(".yuleosh") / "reports" / "coverage-trend.jsonl"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _ensure_trend_dir(project_dir: str) -> Path:
    """Ensure the trend file directory exists and return the full path."""
    path = Path(project_dir) / TREND_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_json_report(project_dir: str, rel_path: str) -> dict | None:
    """Load a JSON report file, returning None on failure."""
    path = Path(project_dir) / rel_path
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Cannot read %s: %s", rel_path, e)
        return None


def _get_c_coverage(project_dir: str) -> dict:
    """Extract C coverage metrics from ``c-coverage.json``."""
    report = _load_json_report(project_dir, ".yuleosh/reports/c-coverage.json")
    if not report:
        return {"line_rate": None, "branch_rate": None, "total_files": None}
    return {
        "line_rate": report.get("line_rate"),
        "branch_rate": report.get("branch_rate"),
        "total_files": report.get("total_files"),
    }


def _get_py_coverage(project_dir: str) -> dict:
    """Extract Python coverage metrics from ``coverage.json`` (pytest-cov)."""
    # Try coverage.json from .yuleosh/reports first
    report = _load_json_report(project_dir, ".yuleosh/reports/coverage.json")
    if report and "line_rate" in report:
        return {
            "line_rate": report.get("line_rate"),
            "branch_rate": report.get("branch_rate"),
        }

    # Try .osh/ci/coverage.json
    report = _load_json_report(project_dir, ".osh/ci/coverage.json")
    if report and "line_rate" in report:
        return {
            "line_rate": report.get("line_rate"),
            "branch_rate": report.get("branch_rate"),
        }

    # Try coverage/coverage.json from .coverage XML/Cobertura fallback
    report = _load_json_report(project_dir, "coverage/coverage.json")
    if report:
        totals = report.get("totals", {})
        return {
            "line_rate": totals.get("percent_covered"),
            "branch_rate": totals.get("percent_covered_branches"),
        }

    return {"line_rate": None, "branch_rate": None}


def _get_git_commit(project_dir: str) -> str:
    """Get short git commit hash."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def record_coverage(project_dir: str) -> None:
    """Record C and Python coverage data to the trend JSONL file.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    """
    c_cov = _get_c_coverage(project_dir)
    py_cov = _get_py_coverage(project_dir)
    commit = _get_git_commit(project_dir)

    entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "commit": commit,
        "c": c_cov,
        "python": py_cov,
    }

    path = _ensure_trend_dir(project_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    c_line = c_cov.get("line_rate")
    py_line = py_cov.get("line_rate")
    c_line_str = f"{c_line:.1f}%" if c_line is not None else "N/A"
    py_line_str = f"{py_line:.1f}%" if py_line is not None else "N/A"
    log.info(
        "Coverage trend recorded: C=%s Python=%s commit=%s",
        c_line_str, py_line_str, commit or "unknown",
    )


def show_coverage_trend(
    project_dir: str,
    days: int = 30,
    lines: int = 50,
    as_json: bool = False,
) -> str:
    """Return a Markdown table (or JSON) of the coverage trend.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    days : int
        Filter to entries within this many days (default 30).
    lines : int
        Max number of entries to show (after day filter).
    as_json : bool
        Return JSON string instead of Markdown table.

    Returns
    -------
    str
        Markdown-formatted trend table or JSON string.
    """
    path = Path(project_dir) / TREND_FILE
    if not path.exists():
        msg = f"*No coverage trend data found at {path}*"
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
        msg = "*No valid coverage trend entries*"
        return json.dumps({"error": msg}) if as_json else msg

    # Filter by day range
    if days > 0:
        cutoff = datetime.now() - timedelta(days=days)
        entries_raw = [
            e for e in entries_raw
            if _parse_timestamp(e.get("timestamp", "")) >= cutoff
        ]

    if not entries_raw:
        msg = f"*No coverage entries within the last {days} days*"
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
        "## 覆盖趋势",
        "",
        f"*最近 {len(recent)} 次记录（共 {len(entries_raw)} 次）*",
        "",
        "| # | 时间戳 | C Line% | C Branch% | Py Line% | Py Branch% | Commit |",
        "|--:|:-------|--------:|----------:|---------:|-----------:|:-------|",
    ]

    for idx, e in enumerate(recent, 1):
        ts = e.get("timestamp", "")[:19]
        c = e.get("c", {})
        py = e.get("python", {})

        c_line = c.get("line_rate")
        c_branch = c.get("branch_rate")
        py_line = py.get("line_rate")
        py_branch = py.get("branch_rate")

        c_line_s = f"{c_line:.1f}" if c_line is not None else "—"
        c_branch_s = f"{c_branch:.1f}" if c_branch is not None else "—"
        py_line_s = f"{py_line:.1f}" if py_line is not None else "—"
        py_branch_s = f"{py_branch:.1f}" if py_branch is not None else "—"

        commit = (e.get("commit") or "")[:8] or "—"

        rows.append(
            f"| {idx} | {ts} | {c_line_s} | {c_branch_s} | {py_line_s} | {py_branch_s} | {commit} |"
        )

    rows.append("")
    return "\n".join(rows)


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp string, returning epoch on failure.

    Strips timezone info so all comparisons are naive vs naive.
    """
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1)


# ------------------------------------------------------------------
# CL2-E04 step 4: Coverage regression alert
# ------------------------------------------------------------------


def check_coverage_regression(
    project_dir: str,
    line_drop_threshold: float = 5.0,
    branch_drop_threshold: float = 5.0,
    window: int = 3,
) -> dict:
    """Check for coverage regression against recent history.

    Compares the **latest** entry against the **window**-entry rolling average.
    Flags a regression if the drop exceeds *line_drop_threshold* or
    *branch_drop_threshold* percentage points.

    Returns a dict with:
        - regression: bool (True if any metric regressed)
        - alerts: list of alert dicts
        - latest: latest coverage entry
        - baseline_avg: rolling average over window entries
        - status: "passed" | "warning"
    """
    result: dict = {
        "regression": False,
        "alerts": [],
        "latest": {},
        "baseline_avg": {},
        "status": "passed",
    }

    path = Path(project_dir) / TREND_FILE
    if not path.exists():
        result["status"] = "warning"
        result["alerts"].append({
            "type": "no_data",
            "message": f"No coverage trend data found at {path}",
        })
        return result

    entries_raw: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries_raw.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    if len(entries_raw) < 2:
        result["status"] = "warning"
        result["alerts"].append({
            "type": "insufficient_data",
            "message": f"Need at least 2 trend entries, got {len(entries_raw)}",
        })
        return result

    latest = entries_raw[-1]
    result["latest"] = latest

    # Compute rolling average over the last `window` entries (excluding latest)
    baseline_entries = entries_raw[-(window + 1):-1] if len(entries_raw) > window + 1 else entries_raw[:-1]

    def _avg(key: str, sub_key: str) -> Optional[float]:
        vals = [e.get(key, {}).get(sub_key) for e in baseline_entries
                if e.get(key, {}).get(sub_key) is not None]
        return sum(vals) / len(vals) if vals else None

    c_line_avg = _avg("c", "line_rate")
    c_branch_avg = _avg("c", "branch_rate")
    py_line_avg = _avg("python", "line_rate")
    py_branch_avg = _avg("python", "branch_rate")

    result["baseline_avg"] = {
        "c_line_rate": f"{c_line_avg:.1f}" if c_line_avg is not None else None,
        "c_branch_rate": f"{c_branch_avg:.1f}" if c_branch_avg is not None else None,
        "py_line_rate": f"{py_line_avg:.1f}" if py_line_avg is not None else None,
        "py_branch_rate": f"{py_branch_avg:.1f}" if py_branch_avg is not None else None,
    }

    # Check C line rate regression
    latest_c_line = latest.get("c", {}).get("line_rate")
    if latest_c_line is not None and c_line_avg is not None:
        drop = c_line_avg - latest_c_line
        if drop > line_drop_threshold:
            result["regression"] = True
            result["alerts"].append({
                "type": "c_line_regression",
                "severity": "warning",
                "metric": "C line coverage",
                "current": latest_c_line,
                "baseline_avg": round(c_line_avg, 2),
                "drop": round(drop, 2),
                "threshold": line_drop_threshold,
                "message": (
                    f"C line coverage dropped by {drop:.1f}pp "
                    f"({latest_c_line:.1f}% vs avg {c_line_avg:.1f}%, "
                    f"threshold {line_drop_threshold}pp)"
                ),
            })

    # Check C branch rate regression
    latest_c_branch = latest.get("c", {}).get("branch_rate")
    if latest_c_branch is not None and c_branch_avg is not None:
        drop = c_branch_avg - latest_c_branch
        if drop > branch_drop_threshold:
            result["regression"] = True
            result["alerts"].append({
                "type": "c_branch_regression",
                "severity": "warning",
                "metric": "C branch coverage",
                "current": latest_c_branch,
                "baseline_avg": round(c_branch_avg, 2),
                "drop": round(drop, 2),
                "threshold": branch_drop_threshold,
                "message": (
                    f"C branch coverage dropped by {drop:.1f}pp "
                    f"({latest_c_branch:.1f}% vs avg {c_branch_avg:.1f}%, "
                    f"threshold {branch_drop_threshold}pp)"
                ),
            })

    # Check Python line rate regression
    latest_py_line = latest.get("python", {}).get("line_rate")
    if latest_py_line is not None and py_line_avg is not None:
        drop = py_line_avg - latest_py_line
        if drop > line_drop_threshold:
            result["regression"] = True
            result["alerts"].append({
                "type": "py_line_regression",
                "severity": "warning",
                "metric": "Python line coverage",
                "current": latest_py_line,
                "baseline_avg": round(py_line_avg, 2),
                "drop": round(drop, 2),
                "threshold": line_drop_threshold,
                "message": (
                    f"Python line coverage dropped by {drop:.1f}pp "
                    f"({latest_py_line:.1f}% vs avg {py_line_avg:.1f}%, "
                    f"threshold {line_drop_threshold}pp)"
                ),
            })

    # Check Python branch rate regression
    latest_py_branch = latest.get("python", {}).get("branch_rate")
    if latest_py_branch is not None and py_branch_avg is not None:
        drop = py_branch_avg - latest_py_branch
        if drop > branch_drop_threshold:
            result["regression"] = True
            result["alerts"].append({
                "type": "py_branch_regression",
                "severity": "warning",
                "metric": "Python branch coverage",
                "current": latest_py_branch,
                "baseline_avg": round(py_branch_avg, 2),
                "drop": round(drop, 2),
                "threshold": branch_drop_threshold,
                "message": (
                    f"Python branch coverage dropped by {drop:.1f}pp "
                    f"({latest_py_branch:.1f}% vs avg {py_branch_avg:.1f}%, "
                    f"threshold {branch_drop_threshold}pp)"
                ),
            })

    if result["alerts"]:
        result["status"] = "warning"
    else:
        c_line_trend = (
            f"{latest_c_line:.1f}%" if latest_c_line is not None else "N/A"
        )
        log.info(
            "Coverage regression check passed: latest C line=%s vs avg C line=%s",
            c_line_trend,
            f"{c_line_avg:.1f}%" if c_line_avg is not None else "N/A",
        )

    return result
