#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Trend Exporter — 飞书仪表盘 / 趋势图表数据导出

基于 run_history / trend 数据，生成结构化的趋势 JSON 格式，
可直接被飞书多维表格或 ECharts 使用。

支持两个维度：
  - MISRA: 违规数量趋势 (total_violations, required, advisory)
  - UT: 单元测试覆盖率趋势 (pass_rate, line_rate, branch_rate)

支持多项目隔离 (project_id 维度)。

数据源：
  - misra-trend.jsonl → MISRA 趋势
  - coverage-trend.jsonl → UT/覆盖率趋势
  - 文件目录隔离不同项目

Usage:
    from yuleosh.report.trend_exporter import export_misra_trend, export_ut_trend, export_all_trends

    # MISRA 趋势
    trend = export_misra_trend(project_dir="/path/to/project")
    # UT 趋势
    ut_trend = export_ut_trend(project_dir="/path/to/project")
    # 全部趋势
    all_trends = export_all_trends(project_dir="/path/to/project")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("report.trend_exporter")


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_DEFAULT_REPORT_DIR = ".yuleosh/reports"
_MISRA_TREND_FILE = "misra-trend.jsonl"
_COVERAGE_TREND_FILE = "coverage-trend.jsonl"

# Default project name when no explicit project context exists
_DEFAULT_PROJECT = "default"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict]:
    """Load all entries from a JSONL file. Returns [] on failure."""
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    log.debug("Skipping unparseable JSONL line: %s", line[:80])
        return entries
    except OSError as e:
        log.warning("Cannot read %s: %s", path, e)
        return []


def _get_project_name(project_dir: str) -> str:
    """Derive a project name from the project directory basename."""
    return Path(project_dir).resolve().name or _DEFAULT_PROJECT


def _normalize_timestamp(ts_str: str) -> str:
    """Normalize various timestamp formats to ISO 8601 (YYYY-MM-DDTHH:MM:SS)."""
    if not ts_str:
        return ""
    try:
        # Handle datetime objects
        if hasattr(ts_str, "isoformat"):
            return ts_str.isoformat()
        # Try ISO parse
        dt = datetime.fromisoformat(ts_str)
        return dt.isoformat()
    except (ValueError, TypeError):
        return ts_str


def _safe_float(val) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(val) -> int:
    """Safely convert a value to int, returning 0 on failure."""
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


# ------------------------------------------------------------------
# MISRA 趋势导出
# ------------------------------------------------------------------


def export_misra_trend(
    project_dir: str,
    project_id: Optional[str] = None,
    max_entries: int = 100,
    project_name: Optional[str] = None,
) -> dict:
    """导出 MISRA 违规趋势 JSON。

    从 misra-trend.jsonl 读取历史记录，转换为结构化趋势 JSON 格式，
    可直接供飞书多维表格或 ECharts 使用。

    Parameters
    ----------
    project_dir : str
        项目根目录。
    project_id : str, optional
        项目标识符。不提供时从目录名推演。
    max_entries : int
        最大返回条目数（取最近 N 条）。默认 100。

    Returns
    -------
    dict
        趋势 JSON，格式：
        ```json
        {
          "report_type": "misra",
          "project": "my-project",
          "project_name": "My Project",
          "generated_at": "2026-06-23T03:00:00",
          "total_entries": 50,
          "history": [
            {
              "build_id": "b001",
              "generated_at": "2026-06-22T10:00:00",
              "total_violations": 98,
              "required": 5,
              "advisory": 3,
              "files_checked": 12
            }
          ]
        }
        ```
    """
    trend_path = Path(project_dir) / _DEFAULT_REPORT_DIR / _MISRA_TREND_FILE
    entries = _load_jsonl(trend_path)

    project = project_id or _get_project_name(project_dir)
    proj_name = project_name or _get_project_name(project_dir)

    history = []
    for entry in entries[-max_entries:]:
        # Normalize: use isoformat-compatible timestamp
        ts = _normalize_timestamp(entry.get("timestamp", ""))

        history.append({
            "build_id": entry.get("commit", "")[:8] or f"run-{len(history) + 1}",
            "generated_at": ts,
            "total_violations": _safe_int(entry.get("total_violations", 0)),
            "required": _safe_int(entry.get("required", 0)),
            "advisory": _safe_int(entry.get("advisory", 0)),
            "files_checked": _safe_int(entry.get("files_checked", 0)),
        })

    return {
        "report_type": "misra",
        "project": project,
        "project_name": proj_name,
        "generated_at": datetime.now().isoformat(),
        "total_entries": len(entries),
        "returned_entries": len(history),
        "history": history,
    }


# ------------------------------------------------------------------
# UT / 覆盖率趋势导出
# ------------------------------------------------------------------


def export_ut_trend(
    project_dir: str,
    project_id: Optional[str] = None,
    max_entries: int = 100,
    project_name: Optional[str] = None,
) -> dict:
    """导出单元测试 / 覆盖率趋势 JSON。

    从 coverage-trend.jsonl 读取历史记录，转换为结构化趋势 JSON 格式。

    支持两种格式的覆盖率数据：
      - 旧格式：顶层 line_coverage / branch_coverage / function_coverage
      - 新格式：c.line_rate / c.branch_rate / python.line_rate

    对于 UT 维度，优先使用新格式 `c` 下的行覆盖率，
    回退到旧格式的 line_coverage。

    Parameters
    ----------
    project_dir : str
        项目根目录。
    project_id : str, optional
        项目标识符。不提供时从目录名推演。
    max_entries : int
        最大返回条目数（取最近 N 条）。默认 100。

    Returns
    -------
    dict
        趋势 JSON，格式：
        ```json
        {
          "report_type": "ut",
          "project": "my-project",
          "project_name": "My Project",
          "generated_at": "2026-06-23T03:00:00",
          "total_entries": 50,
          "history": [
            {
              "build_id": "b001",
              "generated_at": "2026-06-22T10:00:00",
              "line_rate": 85.5,
              "branch_rate": 72.3,
              "function_coverage": 80.0,
              "total_files": 12
            }
          ]
        }
        ```
    """
    trend_path = Path(project_dir) / _DEFAULT_REPORT_DIR / _COVERAGE_TREND_FILE
    entries = _load_jsonl(trend_path)

    project = project_id or _get_project_name(project_dir)
    proj_name = project_name or _get_project_name(project_dir)

    history = []
    for entry in entries[-max_entries:]:
        ts = _normalize_timestamp(entry.get("timestamp", ""))

        # 新格式: c.line_rate / c.branch_rate
        c_data = entry.get("c", {})
        line_rate = _safe_float(c_data.get("line_rate"))
        branch_rate = _safe_float(c_data.get("branch_rate"))
        total_files = _safe_int(c_data.get("total_files"))

        # 回退: 旧格式顶层字段
        if line_rate == 0.0 and c_data.get("line_rate") is None:
            line_rate = _safe_float(entry.get("line_coverage", 0.0))
            branch_rate = _safe_float(entry.get("branch_coverage", 0.0))
            if not total_files:
                total_files = _safe_int(entry.get("files_measured", 0))

        history.append({
            "build_id": entry.get("commit", "")[:8] or f"run-{len(history) + 1}",
            "generated_at": ts,
            "line_rate": round(line_rate, 2),
            "branch_rate": round(branch_rate, 2),
            "function_coverage": round(
                _safe_float(entry.get("function_coverage", 0.0)), 2
            ),
            "total_files": total_files,
        })

    return {
        "report_type": "ut",
        "project": project,
        "project_name": proj_name,
        "generated_at": datetime.now().isoformat(),
        "total_entries": len(entries),
        "returned_entries": len(history),
        "history": history,
    }


# ------------------------------------------------------------------
# 汇总导出
# ------------------------------------------------------------------


def export_all_trends(
    project_dir: str,
    project_id: Optional[str] = None,
    max_entries: int = 100,
) -> dict:
    """导出 MISRA 和 UT 两个维度的完整趋势数据。

    返回包含两个 trend 字典的汇总 JSON，适合飞书多维表展示。

    Parameters
    ----------
    project_dir : str
        项目根目录。
    project_id : str, optional
        项目标识符。
    max_entries : int
        最大返回条目数。

    Returns
    -------
    dict
        汇总 JSON，格式：
        ```json
        {
          "generated_at": "...",
          "project": "...",
          "project_name": "...",
          "trends": {
            "misra": { ... },
            "ut": { ... }
          }
        }
        ```
    """
    project = project_id or _get_project_name(project_dir)
    proj_name = _get_project_name(project_dir)

    misra = export_misra_trend(project_dir, project_id=project, max_entries=max_entries, project_name=proj_name)
    ut = export_ut_trend(project_dir, project_id=project, max_entries=max_entries, project_name=proj_name)

    return {
        "generated_at": datetime.now().isoformat(),
        "project": project,
        "project_name": proj_name,
        "trends": {
            "misra": misra,
            "ut": ut,
        },
    }


# ------------------------------------------------------------------
# File-based project isolation (多项目隔离)
# ------------------------------------------------------------------


def export_trend_for_project(
    project_dir: str,
    report_type: str,
    project_id: Optional[str] = None,
    max_entries: int = 100,
) -> Optional[dict]:
    """为指定项目导出趋势数据（基于文件目录隔离）。

    轻量实现——不引入数据库，基于 .yuleosh/reports/ 下的文件做隔离。
    每个项目有自己的 project_dir/.yuleosh/reports/ 目录。

    Parameters
    ----------
    project_dir : str
        项目根目录（每个项目独立）。
    report_type : str
        "misra" 或 "ut"。
    project_id : str, optional
        项目标识符。
    max_entries : int
        最大返回条目数。

    Returns
    -------
    dict or None
        趋势 JSON，若数据不存在返回 None。
    """
    if report_type == "misra":
        return export_misra_trend(project_dir, project_id=project_id, max_entries=max_entries)
    elif report_type == "ut":
        return export_ut_trend(project_dir, project_id=project_id, max_entries=max_entries)
    else:
        log.warning("Unsupported report_type: %s (use 'misra' or 'ut')", report_type)
        return None


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------


def main():
    """CLI entry point for trend export."""
    import argparse

    parser = argparse.ArgumentParser(
        description="yuleOSH Trend Exporter — export MISRA/UT trend data for Feishu dashboards"
    )
    parser.add_argument(
        "--project-dir", "-d",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--report-type", "-t",
        choices=["misra", "ut", "all"],
        default="all",
        help="Which trend to export: misra, ut, or all (default: all)",
    )
    parser.add_argument(
        "--project-id", "-p",
        default=None,
        help="Optional project identifier for multi-project setups",
    )
    parser.add_argument(
        "--max-entries", "-n",
        type=int,
        default=100,
        help="Maximum number of history entries to return (default: 100)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    if args.report_type == "all":
        result = export_all_trends(
            args.project_dir,
            project_id=args.project_id,
            max_entries=args.max_entries,
        )
    else:
        result = export_trend_for_project(
            args.project_dir,
            args.report_type,
            project_id=args.project_id,
            max_entries=args.max_entries,
        )

    json_str = json.dumps(result, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Trend exported to: {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
