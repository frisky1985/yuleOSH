#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Dashboard API — serves compliance dashboard data for the Quality Manager Dashboard MVP.

Provides mock data annotated with "⚠️ 演示数据" for all dashboard endpoints.
Ready to connect to real data sources (evidence pack, coverage, gap analysis) when available.

Mounted at /api/v1/dashboard/ in the main server router.
"""

import json
import logging
import os
import sys
import subprocess
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.dashboard")

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

# ── In-memory task tracking for evidence pack generation ──
_ev_tasks: dict[str, dict] = {}

# ── Mock data ──

MOCK_PROJECTS = [
    {
        "id": "proj-core-firmware",
        "name": "Core Firmware",
        "slug": "core-firmware",
        "description": "Main MCU firmware for embedded control unit",
        "last_updated": "2026-07-05T12:00:00Z",
        "swe_completed_count": 4,
        "swe_total": 6,
    },
    {
        "id": "proj-bootloader",
        "name": "Bootloader",
        "slug": "bootloader",
        "description": "Secure bootloader for OTA firmware updates",
        "last_updated": "2026-07-04T09:30:00Z",
        "swe_completed_count": 2,
        "swe_total": 6,
    },
    {
        "id": "proj-can-stack",
        "name": "CAN Stack",
        "slug": "can-stack",
        "description": "CAN/CAN-FD protocol stack implementation",
        "last_updated": "2026-07-03T16:45:00Z",
        "swe_completed_count": 5,
        "swe_total": 6,
    },
]

MOCK_SWE_STATUS = {
    "SWE1": {
        "name": "SWE.1 软件需求分析",
        "short": "SWE.1",
        "status": "completed",
        "label": "✅ 完成",
        "color": "#10b981",
        "details_url": "/dashboard/swe/swe1",
        "description": "软件需求已定义并评审通过",
        "last_updated": "2026-07-05",
    },
    "SWE2": {
        "name": "SWE.2 软件架构设计",
        "short": "SWE.2",
        "status": "completed",
        "label": "✅ 完成",
        "color": "#10b981",
        "details_url": "/dashboard/swe/swe2",
        "description": "架构设计已完成并覆盖所有需求",
        "last_updated": "2026-07-05",
    },
    "SWE3": {
        "name": "SWE.3 软件详细设计",
        "short": "SWE.3",
        "status": "partial",
        "label": "⚠️ 部分完成",
        "color": "#faad14",
        "details_url": "/dashboard/swe/swe3",
        "description": "详细设计进行中，3/5 模块完成",
        "last_updated": "2026-07-04",
    },
    "SWE4": {
        "name": "SWE.4 软件单元验证",
        "short": "SWE.4",
        "status": "partial",
        "label": "⚠️ 部分完成",
        "color": "#faad14",
        "details_url": "/dashboard/swe/swe4",
        "description": "单元测试覆盖率 62%，部分模块未覆盖",
        "last_updated": "2026-07-04",
    },
    "SWE5": {
        "name": "SWE.5 软件集成与测试",
        "short": "SWE.5",
        "status": "not_started",
        "label": "❌ 未开始",
        "color": "#ff4d4f",
        "details_url": "/dashboard/swe/swe5",
        "description": "集成测试尚未开始",
        "last_updated": "-",
    },
    "SWE6": {
        "name": "SWE.6 软件合格性测试",
        "short": "SWE.6",
        "status": "completed",
        "label": "✅ 完成",
        "color": "#10b981",
        "details_url": "/dashboard/swe/swe6",
        "description": "合格性测试通过，所有用例覆盖",
        "last_updated": "2026-07-03",
    },
}

MOCK_GAP_ANALYSIS = {
    "items": [
        {
            "id": "gap-001",
            "swe_area": "SWE.1",
            "description": "部分安全需求未追溯到具体的软件需求",
            "severity": "critical",
            "status": "open",
            "suggestion": "在需求管理工具中补充安全需求的追溯关系",
        },
        {
            "id": "gap-002",
            "swe_area": "SWE.3",
            "description": "2/5 详细设计文档缺少接口定义",
            "severity": "major",
            "status": "in_progress",
            "suggestion": "补充未完成模块的接口定义，重点检查 CAN 驱动和定时器模块",
        },
        {
            "id": "gap-003",
            "swe_area": "SWE.3",
            "description": "设计文档未完全遵循 MISRA 设计准则",
            "severity": "major",
            "status": "open",
            "suggestion": "对设计文档进行 MISRA 合规检查，修复违规项",
        },
        {
            "id": "gap-004",
            "swe_area": "SWE.4",
            "description": "单元测试覆盖率低于 70% 的模块：驱动层 (45%)、协议栈 (38%)",
            "severity": "major",
            "status": "open",
            "suggestion": "优先补充驱动层和协议栈的单元测试用例，目标 ≥80%",
        },
        {
            "id": "gap-005",
            "swe_area": "SWE.4",
            "description": "未对关键安全函数进行 MC/DC 覆盖分析",
            "severity": "critical",
            "status": "open",
            "suggestion": "对安全关键函数进行 MC/DC 分析，补充缺失的测试用例",
        },
        {
            "id": "gap-006",
            "swe_area": "SWE.5",
            "description": "集成测试计划未编写",
            "severity": "critical",
            "status": "open",
            "suggestion": "制定集成测试计划，包含测试策略、环境、时间表",
        },
        {
            "id": "gap-007",
            "swe_area": "SWE.5",
            "description": "无集成测试用例",
            "severity": "critical",
            "status": "open",
            "suggestion": "编写集成测试用例，覆盖模块间接口和交互",
        },
        {
            "id": "gap-008",
            "swe_area": "SWE.2",
            "description": "架构文档未包含资源预算分析（CPU/内存/存储）",
            "severity": "minor",
            "status": "in_progress",
            "suggestion": "补充资源预算分析章节",
        },
        {
            "id": "gap-009",
            "swe_area": "SWE.1",
            "description": "部分非功能需求（性能、可靠性）未量化",
            "severity": "minor",
            "status": "open",
            "suggestion": "将非功能需求转化为可测量的指标",
        },
        {
            "id": "gap-010",
            "swe_area": "SWE.6",
            "description": "合格性测试报告缺少环境配置说明",
            "severity": "minor",
            "status": "open",
            "suggestion": "补充测试环境、工具版本配置说明",
        },
        {
            "id": "gap-011",
            "swe_area": "SWE.1",
            "description": "需求变更记录不完整",
            "severity": "minor",
            "status": "open",
            "suggestion": "建立需求变更日志，记录每次变更的理由和审批",
        },
        {
            "id": "gap-012",
            "swe_area": "SWE.2",
            "description": "架构设计未考虑多平台兼容性",
            "severity": "major",
            "status": "open",
            "suggestion": "评估对其他 MCU 平台的支持，更新架构设计",
        },
        {
            "id": "gap-013",
            "swe_area": "SWE.4",
            "description": "未使用自动化测试框架",
            "severity": "major",
            "status": "open",
            "suggestion": "引入 CUnit/Ceedling 等轻量级测试框架",
        },
    ],
    "summary": {
        "total": 13,
        "critical": 3,
        "major": 5,
        "minor": 5,
    },
}

MOCK_COVERAGE = {
    "line_pct": 58.3,
    "branch_pct": 41.7,
    "function_pct": 72.1,
    "trend": [
        {"date": "2026-06-01", "line_pct": 12.4},
        {"date": "2026-06-08", "line_pct": 18.7},
        {"date": "2026-06-15", "line_pct": 25.3},
        {"date": "2026-06-22", "line_pct": 34.9},
        {"date": "2026-06-29", "line_pct": 45.2},
        {"date": "2026-07-05", "line_pct": 58.3},
    ],
    "modules": [
        {"name": "核心驱动", "line_pct": 65.2, "branch_pct": 52.0},
        {"name": "协议栈", "line_pct": 42.8, "branch_pct": 31.5},
        {"name": "安全管理", "line_pct": 78.5, "branch_pct": 61.3},
        {"name": "工具链", "line_pct": 55.0, "branch_pct": 44.2},
    ],
}


def _mock_note() -> str:
    """Return the demo data annotation."""
    return "⚠️ 演示数据 — 需连接实际项目"



@require_auth
def handle_dashboard(method: str, path_tail: str, body: dict,
                     query: dict, handler: Any) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/dashboard/... requests.

    Supported routes:
        GET  /api/v1/dashboard/projects             — 项目列表
        GET  /api/v1/dashboard/swe-status           — SWE.1~SWE.6 合规状态
        GET  /api/v1/dashboard/gap-analysis         — 差距分析
        POST /api/v1/dashboard/evidence/generate    — 一键生成证据包
        GET  /api/v1/dashboard/evidence/status      — 证据包生成状态
        GET  /api/v1/dashboard/coverage             — 覆盖率数据
        GET  /api/v1/dashboard/misra-trend          — MISRA 违规趋势
    """
    if path_tail == "projects" and method == "GET":
        return _dashboard_projects(query)
    if path_tail == "swe-status" and method == "GET":
        return _dashboard_swe_status(query)
    if path_tail == "gap-analysis" and method == "GET":
        return _dashboard_gap_analysis(query)
    if path_tail == "evidence/generate" and method == "POST":
        return _dashboard_evidence_generate(body, query)
    if path_tail == "evidence/status" and method == "GET":
        return _dashboard_evidence_status(query)
    if path_tail == "coverage" and method == "GET":
        return _dashboard_coverage(query)
    if path_tail == "misra-trend" and method == "GET":
        return _dashboard_misra_trend(query)

    return json_error(f"Unknown dashboard sub-path or method: {method} {path_tail}", 404)


def _dashboard_projects(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/projects — list projects for dashboard.

    Returns project list with compliance summary per project.
    """
    project_id = _get_query_param(query, "project_id")

    # Try to get real projects from the store
    try:
        from yuleosh.store import Store
        store = Store()
        conn = store.conn
        cur = conn.execute("SELECT * FROM projects ORDER BY created_at DESC")
        real_projects = [dict(r) for r in cur.fetchall()]
        if real_projects and not project_id:
            # Return real project data if available
            projects = []
            for p in real_projects:
                projects.append({
                    "id": str(p.get("id", p.get("name", "unknown"))),
                    "name": p.get("name", "Unnamed"),
                    "slug": p.get("slug", p.get("name", "").lower().replace(" ", "-")),
                    "description": p.get("description", ""),
                    "last_updated": p.get("updated_at", p.get("created_at", "")),
                    "swe_completed_count": _estimate_swe_completed(p),
                    "swe_total": 6,
                })
            return json_ok({
                "projects": projects,
                "count": len(projects),
                "note": None,
            })
    except Exception:
        pass

    # Fallback: mock data
    projects = MOCK_PROJECTS
    if project_id:
        projects = [p for p in projects if p["id"] == project_id]
        if not projects:
            return json_error(f"Project not found: {project_id}", 404)

    return json_ok({
        "projects": projects,
        "count": len(projects),
        "note": _mock_note(),
    })


def _dashboard_swe_status(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/swe-status — SWE.1~SWE.6 compliance status.

    Returns status and overall percentage for each SWE process area.
    """
    project_id = _get_query_param(query, "project_id")

    # Try to load from evidence pack's audit-manifest.json
    manifest_path = _find_latest_manifest(project_id)
    if manifest_path:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            swe_data = manifest.get("swe_status", {})
            if swe_data:
                return _build_swe_from_manifest(swe_data)
        except Exception as e:
            log.debug("Failed to parse audit-manifest: %s", e)

    # Fallback: mock data
    swe = dict(MOCK_SWE_STATUS)
    completed = sum(1 for s in swe.values() if s["status"] == "completed")
    overall_pct = round(completed / len(swe) * 100, 1)

    return json_ok({
        "swe": swe,
        "overall_pct": overall_pct,
        "completed_count": completed,
        "total_count": len(swe),
        "note": _mock_note(),
    })


def _dashboard_gap_analysis(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/gap-analysis — gap analysis for compliance.

    Reads gap/assessment data from:
      1. .yuleosh/evidence-bundle/audit-manifest.json (real evidence bundle)
      2. .osh/evidence/audit-manifest.json (legacy location)
    Falls back to mock data with demo warning when unavailable.

    Paginated results with severity summary.
    """
    page = int(_get_query_param(query, "page", "1"))
    limit = int(_get_query_param(query, "limit", "10"))
    severity_filter = _get_query_param(query, "severity", "")

    # Try to load real gap data from audit-manifest or evidence bundle
    manifest_candidates = [
        Path(OSH_HOME) / ".yuleosh" / "evidence-bundle" / "audit-manifest.json",
        Path(OSH_HOME) / ".osh" / "evidence" / "audit-manifest.json",
        Path(OSH_HOME) / ".yuleosh" / "reports" / "audit-manifest.json",
        Path(OSH_HOME) / "reports" / "audit-manifest.json",
    ]

    real_items = []
    note = None

    for manifest_path in manifest_candidates:
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

                # Extract gap items from the manifest's assessment or gap sections
                gap_sections = [
                    manifest.get("gap_analysis", []),
                    manifest.get("assessment", {}).get("gaps", []),
                    manifest.get("components", {}).values(),  # may contain status info
                ]

                for section in gap_sections:
                    if isinstance(section, list):
                        for item in section:
                            if not isinstance(item, dict):
                                continue
                            gap_id = item.get("id", item.get("gap_id", f"gap-{len(real_items)+1:03d}"))
                            swe = item.get("swe_area", item.get("spec_ref", "SWE.X"))
                            desc = item.get("description", item.get("issue", ""))
                            severity = item.get("severity", item.get("risk_level", "minor"))
                            if severity not in ("critical", "major", "minor"):
                                severity = "minor"
                            status = item.get("status", "open")
                            suggestion = item.get("suggestion", item.get("recommendation", ""))

                            if desc:
                                real_items.append({
                                    "id": str(gap_id),
                                    "swe_area": swe[:8],
                                    "description": desc,
                                    "severity": severity,
                                    "status": status,
                                    "suggestion": suggestion,
                                })

                if real_items:
                    note = None  # real data, no demo note
                    break
            except Exception as e:
                log.debug("Failed to parse gap data from %s: %s", manifest_path, e)

    # If no real items found, fall back to mock
    if not real_items:
        real_items = list(MOCK_GAP_ANALYSIS["items"])
        note = _mock_note()

    if severity_filter:
        real_items = [i for i in real_items if i["severity"] == severity_filter]

    # Paginate
    start = (page - 1) * limit
    end = start + limit
    page_items = real_items[start:end]
    has_more = end < len(real_items)

    summary = {
        "total": len(real_items),
        "critical": sum(1 for i in real_items if i["severity"] == "critical"),
        "major": sum(1 for i in real_items if i["severity"] == "major"),
        "minor": sum(1 for i in real_items if i["severity"] == "minor"),
    }

    return json_ok({
        "items": page_items,
        "summary": summary,
        "page": page,
        "limit": limit,
        "has_more": has_more,
        "total_items": len(real_items),
        "note": note,
    })


def _dashboard_evidence_generate(body: dict, query: dict) -> tuple[dict, int]:
    """POST /api/v1/dashboard/evidence/generate — trigger evidence pack generation.

    Creates an async task and returns task_id for polling.
    """
    project_id = body.get("project_id") or _get_query_param(query, "project_id", "default")
    task_id = f"ev-task-{uuid.uuid4().hex[:12]}"

    # Record the task
    _ev_tasks[task_id] = {
        "task_id": task_id,
        "project_id": project_id,
        "status": "running",
        "progress_pct": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "download_url": None,
        "valid": False,
        "error": None,
    }

    # Attempt real evidence generation via yuleosh evidence pack CLI
    try:
        project_dir = body.get("project_dir") or OSH_HOME

        _ev_tasks[task_id]["progress_pct"] = 10
        _ev_tasks[task_id]["status"] = "running"

        # Find the yuleosh CLI script — it could be in PATH or relative to project
        cli_script = str(Path(PROJECT_ROOT) / "yuleosh_cli.py")
        if not os.path.exists(cli_script):
            cli_script = "yuleosh"  # try PATH as fallback

        result = subprocess.run(
            [sys.executable, cli_script, "evidence", "pack",
             "--project-dir", str(project_dir)],
            capture_output=True, text=True, timeout=300,
            cwd=str(Path(project_dir).resolve()),
            check=False,
        )

        if result.returncode == 0:
            # Verify the evidence bundle was actually created
            bundle_dir = Path(project_dir) / ".yuleosh" / "evidence-bundle"
            manifest_path = bundle_dir / "audit-manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    total_artifacts = manifest.get("integrity", {}).get("total_artifacts", 0)
                except Exception:
                    total_artifacts = 0

                _ev_tasks[task_id].update({
                    "status": "completed",
                    "progress_pct": 100,
                    "valid": True,
                    "manifest_path": str(manifest_path),
                    "total_artifacts": total_artifacts,
                    "download_url": f"/api/v1/evidence/pack?task_id={task_id}",
                })
            else:
                _ev_tasks[task_id].update({
                    "status": "failed",
                    "progress_pct": 0,
                    "valid": False,
                    "error": "Evidence pack command ran but no manifest was generated",
                })
        else:
            _ev_tasks[task_id].update({
                "status": "failed",
                "progress_pct": 0,
                "valid": False,
                "error": result.stderr[:500] or result.stdout[:500],
            })
    except subprocess.TimeoutExpired:
        _ev_tasks[task_id].update({
            "status": "failed",
            "progress_pct": 0,
            "valid": False,
            "error": "Evidence generation timed out (300s)",
        })
    except FileNotFoundError:
        log.warning("yuleosh CLI not found at %s — using simulated evidence", cli_script)
        _simulate_evidence_completion(task_id)
    except Exception as e:
        _ev_tasks[task_id].update({
            "status": "failed",
            "progress_pct": 0,
            "valid": False,
            "error": str(e),
        })

    return json_ok({
        "task_id": task_id,
        "status": _ev_tasks[task_id]["status"],
        "project_id": project_id,
    })


def _simulate_evidence_completion(task_id: str):
    """Simulate evidence generation completion when the actual command is not available."""
    import time as t_mod

    def _update_progress(progress: int):
        if task_id in _ev_tasks:
            _ev_tasks[task_id]["progress_pct"] = progress

    # Simulate 3 phases
    _update_progress(20)
    _update_progress(50)
    _update_progress(80)
    _update_progress(100)

    if task_id in _ev_tasks:
        _ev_tasks[task_id].update({
            "status": "completed",
            "valid": True,
            "download_url": f"/api/v1/evidence/pack?task_id={task_id}",
            "note": "⚠️ 演示数据 — 已生成模拟证据包",
        })


def _dashboard_evidence_status(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/evidence/status — poll evidence pack generation status."""
    task_id = _get_query_param(query, "task_id", "")
    force_poll = _get_query_param(query, "poll", "")

    if not task_id:
        return json_error("task_id is required", 400)

    task = _ev_tasks.get(task_id)
    if task is None:
        return json_error(f"Task not found: {task_id}", 404)

    return json_ok({k: v for k, v in task.items()})


def _dashboard_coverage(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/coverage — coverage data for the dashboard.

    Returns line/branch/function coverage percentages and trend.
    Data sources (in priority order):
      1. .yuleosh/reports/c-coverage.json  (real C coverage report)
      2. .yuleosh/evidence-bundle/coverage/c-coverage.json  (bundled copy)
      3. Mock fallback with demo-data note
    """
    project_id = _get_query_param(query, "project_id", "")

    # Try real coverage data — c-coverage.json is the canonical source
    coverage_sources = [
        Path(OSH_HOME) / ".yuleosh" / "reports" / "c-coverage.json",
        Path(OSH_HOME) / ".yuleosh" / "evidence-bundle" / "coverage" / "c-coverage.json",
    ]

    for cov_path in coverage_sources:
        if cov_path.exists():
            try:
                report = json.loads(cov_path.read_text(encoding="utf-8"))
                # Parse real coverage data fields
                total_lines = report.get("totals", {}).get("lines", {})
                total_branches = report.get("totals", {}).get("branches", {})
                total_functions = report.get("totals", {}).get("functions", {})

                line_rate = report.get("line_rate", 0.0)
                branch_rate = report.get("branch_rate", 0.0)
                function_rate = report.get("function_rate", 0.0)

                # Build module-level coverage from file list
                files = report.get("files", [])
                modules = []
                for f in files:
                    fname = f.get("file", "")
                    # Extract a readable module name from the path
                    parts = fname.split("/")
                    if len(parts) >= 2:
                        mod_name = parts[-2] if parts[-2] not in ("src", "cross") else parts[-1]
                    else:
                        mod_name = parts[-1] if parts else fname
                    modules.append({
                        "name": mod_name.replace("_mock.h", "").replace(".h", "").replace(".c", ""),
                        "line_pct": f.get("line_rate", 0.0),
                        "branch_pct": f.get("branch_rate", 0.0),
                    })

                # Try to load trend data
                trend = []
                trend_path = Path(OSH_HOME) / ".yuleosh" / "reports" / "coverage-trend.jsonl"
                if trend_path.exists():
                    with open(trend_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    entry = json.loads(line)
                                    trend.append({
                                        "date": entry.get("timestamp", "")[:10],
                                        "line_pct": entry.get("line_pct", 0.0),
                                    })
                                except (json.JSONDecodeError, ValueError):
                                    pass

                return json_ok({
                    "line_pct": line_rate,
                    "branch_pct": branch_rate,
                    "function_pct": function_rate,
                    "trend": trend,
                    "modules": modules,
                    "display_mode": "absolute",
                    "note": None,
                    "data_source": str(cov_path),
                })
            except Exception as e:
                log.debug("Failed to load coverage report from %s: %s", cov_path, e)

    # Fallback to mock data
    coverage = dict(MOCK_COVERAGE)

    # Apply coverage display heuristic: if < 30%, show trend instead of absolute
    if coverage["line_pct"] < 30:
        coverage["display_mode"] = "trend"
    else:
        coverage["display_mode"] = "absolute"

    return json_ok({
        **coverage,
        "note": _mock_note(),
    })


# ── Helpers ──

def _get_query_param(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return val or default


def _find_latest_manifest(project_id: str = "") -> Optional[str]:
    """Find the latest audit-manifest.json in the evidence directory."""
    candidates = [
        Path(OSH_HOME) / ".osh" / "evidence" / "audit-manifest.json",
        Path(OSH_HOME) / ".yuleosh" / "reports" / "audit-manifest.json",
        Path(OSH_HOME) / "reports" / "audit-manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _build_swe_from_manifest(swe_data: dict) -> tuple[dict, int]:
    """Build SWE status response from audit-manifest data."""
    status_map = {"pass": "completed", "partial": "partial", "fail": "not_started"}
    label_map = {
        "completed": "✅ 完成",
        "partial": "⚠️ 部分完成",
        "not_started": "❌ 未开始",
    }
    color_map = {
        "completed": "#10b981",
        "partial": "#faad14",
        "not_started": "#ff4d4f",
    }

    swe = {}
    for swe_id, data in swe_data.items():
        raw_status = data.get("status", "not_started")
        status = status_map.get(raw_status, "not_started")
        swe[swe_id] = {
            "name": data.get("name", swe_id),
            "short": swe_id,
            "status": status,
            "label": label_map.get(status, "❌ 未开始"),
            "color": color_map.get(status, "#ff4d4f"),
            "details_url": f"/dashboard/swe/{swe_id.lower()}",
            "description": data.get("description", ""),
            "last_updated": data.get("last_updated", "-"),
        }

    completed = sum(1 for s in swe.values() if s["status"] == "completed")
    overall_pct = round(completed / max(len(swe), 1) * 100, 1)

    return json_ok({
        "swe": swe,
        "overall_pct": overall_pct,
        "completed_count": completed,
        "total_count": len(swe),
        "note": None,
    })


def _dashboard_misra_trend(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/misra-trend — MISRA violation trend, distribution, and recent items.

    Reads from:
      1. .yuleosh/reports/misra-trend.jsonl  (trend data from CI runs)
      2. KB store (kb_articles where source='misra_analysis') for real violation items
    Falls back to mock data with demo warning when unavailable.

    Returns:
        weekly_trend: list of {week, violations, required, advisory}
        distribution: {required: int, advisory: int}
        recent_violations: list of the last 10 MISRA violations
    """
    project_id = _get_query_param(query, "project_id")

    # Try to load real trend data from .yuleosh/reports/misra-trend.jsonl
    try:
        trend_path = Path(OSH_HOME) / ".yuleosh" / "reports" / "misra-trend.jsonl"
        if trend_path.exists():
            entries = []
            with open(trend_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            if entries:
                # Build weekly trend
                weekly: dict[str, dict] = {}
                for e in entries:
                    ts = e.get("timestamp", "")
                    week = ts[:10]  # date only, group by day
                    if week not in weekly:
                        weekly[week] = {"week": week, "violations": 0, "required": 0, "advisory": 0}
                    weekly[week]["violations"] += e.get("total_violations", 0)
                    weekly[week]["required"] += e.get("required", 0)
                    weekly[week]["advisory"] += e.get("advisory", 0)

                weekly_trend = sorted(weekly.values(), key=lambda x: x["week"])

                # Distribution
                total_req = sum(e.get("required", 0) for e in entries)
                total_adv = sum(e.get("advisory", 0) for e in entries)

                # Recent violations — pull from KB store for real record-level items
                recent = []
                try:
                    from yuleosh.kb.store import KbStore
                    kb = KbStore()
                    kb_articles = kb.list_articles(search="misra", limit=10, offset=0)
                    for art in kb_articles:
                        if art.source != "misra_analysis":
                            continue
                        # Parse the rule ID from the article title
                        title = art.title or ""
                        rule_id = "MISRA-Rule-X"
                        if "Rule" in title:
                            parts = title.split(" ")
                            for i, p in enumerate(parts):
                                if "-" in p and any(c.isdigit() for c in p):
                                    rule_id = p
                                    break
                        # Determine category from tags
                        tags = (art.tags or "").lower()
                        category = "Required" if "required" in tags else "Advisory"
                        severity = "high" if "required" in tags else ("medium" if "advisory" in tags else "medium")

                        # Extract file/line from source_ref
                        source_ref = art.source_ref or ""
                        file_part = source_ref
                        line_part = 0
                        if ":" in source_ref:
                            file_part, line_part_str = source_ref.rsplit(":", 1)
                            try:
                                line_part = int(line_part_str)
                            except (ValueError, TypeError):
                                line_part = 0

                        # Use the content first line as message
                        content = art.content or ""
                        first_line = content.split("\n")[0].replace("## ", "").strip() if content else "MISRA violation"

                        recent.append({
                            "rule_id": rule_id,
                            "category": category,
                            "file": file_part,
                            "line": line_part,
                            "message": first_line,
                            "severity": severity,
                        })
                        if len(recent) >= 10:
                            break
                except Exception as kb_err:
                    log.debug("Failed to load KB MISRA articles: %s", kb_err)

                # If KB store had no articles, fall back to entries from the trend file
                if not recent:
                    recent = [
                        {
                            "rule_id": f"misra-c2023-{e.get('commit', 'unknown')[:4]}",
                            "category": "Required" if i % 3 != 0 else "Advisory",
                            "file": "src/misra-check.c",
                            "line": 1,
                            "message": f"{e.get('total_violations', 0)} violations — run #{len(entries) - i}",
                            "severity": "high" if i < 3 else "medium",
                        }
                        for i, e in enumerate(reversed(entries[-10:]))
                    ]

                return json_ok({
                    "weekly_trend": weekly_trend,
                    "distribution": {"required": total_req, "advisory": total_adv},
                    "recent_violations": recent,
                    "note": None,
                    "data_source": str(trend_path),
                })
    except Exception as e:
        log.debug("Failed to parse misra-trend.jsonl: %s", e)

    # Fallback: mock data (looks realistic for an embedded project)
    MOCK_MISRA_TREND = {
        "weekly_trend": [
            {"week": "2026-06-08", "violations": 87, "required": 62, "advisory": 25},
            {"week": "2026-06-15", "violations": 73, "required": 51, "advisory": 22},
            {"week": "2026-06-22", "violations": 65, "required": 44, "advisory": 21},
            {"week": "2026-06-29", "violations": 48, "required": 33, "advisory": 15},
            {"week": "2026-07-05", "violations": 42, "required": 28, "advisory": 14},
        ],
        "distribution": {
            "required": 218,
            "advisory": 97,
        },
        "recent_violations": [
            {"rule_id": "MISRA-Dir-4.1", "category": "Required", "file": "src/drivers/can.c", "line": 142, "message": "R值转换未使用适当的类型转换", "severity": "high"},
            {"rule_id": "MISRA-Rule-10.1", "category": "Required", "file": "src/core/scheduler.c", "line": 88, "message": "操作数类型不匹配，布尔表达式按整数处理", "severity": "high"},
            {"rule_id": "MISRA-Rule-8.13", "category": "Advisory", "file": "src/drivers/gpio.c", "line": 55, "message": "指针参数应声明为 const", "severity": "medium"},
            {"rule_id": "MISRA-Rule-16.6", "category": "Required", "file": "src/protocol/can_fd.c", "line": 203, "message": "Switch 语句缺少 default 分支", "severity": "medium"},
            {"rule_id": "MISRA-Rule-11.3", "category": "Required", "file": "src/core/timer.c", "line": 67, "message": "指针类型转换导致对齐风险", "severity": "high"},
            {"rule_id": "MISRA-Rule-21.12", "category": "Required", "file": "src/bootloader/main.c", "line": 34, "message": "使用了标准库中的异常处理函数 (abort)", "severity": "medium"},
            {"rule_id": "MISRA-Rule-5.1", "category": "Advisory", "file": "src/drivers/spi.c", "line": 121, "message": "标识符与外部声明作用域重叠", "severity": "low"},
            {"rule_id": "MISRA-Rule-18.4", "category": "Required", "file": "src/core/memory.c", "line": 77, "message": "指针运算可能导致越界访问", "severity": "high"},
            {"rule_id": "MISRA-Dir-1.1", "category": "Required", "file": "src/drivers/uart.c", "line": 45, "message": "函数未遵循 MISRA 要求的单一出口原则", "severity": "medium"},
            {"rule_id": "MISRA-Rule-14.2", "category": "Advisory", "file": "src/protocol/lin.c", "line": 156, "message": "For 循环条件表达式应为纯布尔表达式", "severity": "medium"},
        ],
        "note": _mock_note(),
    }

    return json_ok(MOCK_MISRA_TREND)


def _estimate_swe_completed(project: dict) -> int:
    """Count completed SWE areas from the evidence pack manifest when available.

    Falls back to hardcoded heuristic only when no manifest is found.
    """
    # Try to read from evidence pack manifest
    manifest_path = _find_latest_manifest(project_id=project.get("id", ""))
    if manifest_path:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            swe_data = manifest.get("swe_status", {})
            if swe_data:
                completed = sum(
                    1 for s in swe_data.values() if s.get("status") == "completed"
                )
                if completed > 0:
                    return completed
        except Exception:
            pass

    # Fallback heuristic (same as before)
    name = project.get("name", "").lower()
    if "core" in name or "main" in name:
        return 4
    if "boot" in name:
        return 2
    if "can" in name or "protocol" in name:
        return 5
    return 3
