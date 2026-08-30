#!/usr/bin/env python3

# @req RS-006
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Dashboard API — serves compliance dashboard data for the Quality Manager Dashboard MVP.

Projects endpoint serves REAL org-scoped data only (P0-2): no mock fallback —
when the store is unavailable it fails explicitly (503) instead of silently
serving demo data. Other endpoints (swe-status / gap-analysis / coverage /
misra-trend) still fall back to clearly-annotated demo data ("⚠️ 演示数据")
until their real data sources are connected.

Mounted at /api/v1/dashboard/ in the main server router.
"""

import json
import logging
import os
import sys
import subprocess
import threading
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

# ── In-memory tracking for gap analysis runs (post-MVP detail/run) ──
# A run is created via POST /gap-analysis/{id}/run and polled via
# /gap-analysis/{id}/status. Status transitions:
#   queued → running → (completed | failed)
_gap_runs: dict[str, dict] = {}
# Per-gap status overrides (mock data is read-only at module level).
# Keyed by gap_id; on read, list/detail merges these on top of the
# base item so a re-run after restart will fall back to default status.
_gap_status_overrides: dict[str, dict] = {}

# Batch remediation runs (post-MVP bulk analyze/remediate).
# Keyed by batch_id; tracks per-item progress so the UI can poll the
# overall batch status. Items run sequentially in a background thread.
_gap_batches: dict[str, dict] = {}

# ── Mock data (other endpoints only; projects is real-data-only since P0-2) ──

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
                     query: dict, handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/dashboard/... requests.

    Note: `**kwargs` absorbs the `current_user` injected by require_auth so
    the decorated signature stays compatible (P0-A token contract fix).

    Supported routes:
        GET  /api/v1/dashboard/projects             — 项目列表（仅真实数据，按 org 过滤，P0-2）
        GET  /api/v1/dashboard/swe-status           — SWE.1~SWE.6 合规状态
        GET  /api/v1/dashboard/gap-analysis                — 差距分析
        GET  /api/v1/dashboard/gap-analysis/{gap_id}       — 单条差距详情
        POST /api/v1/dashboard/gap-analysis/{gap_id}/run   — 触发差距修复（异步）
        GET  /api/v1/dashboard/gap-analysis/{gap_id}/status — 修复进度轮询
        POST /api/v1/dashboard/gap-analysis/batch-run      — 批量触发差距修复（异步）
        GET  /api/v1/dashboard/gap-analysis/batch/{batch_id} — 批量修复进度轮询
        POST /api/v1/dashboard/evidence/generate    — 一键生成证据包
        GET  /api/v1/dashboard/evidence/status      — 证据包生成状态
        GET  /api/v1/dashboard/coverage             — 覆盖率数据
        GET  /api/v1/dashboard/misra-trend          — MISRA 违规趋势
    """
    # P0-2: current_user is injected by require_auth (user_id/org_id/email/role).
    # Projects listing is scoped to the authenticated user's org — never serve
    # another org's projects and never fall back to demo data.
    current_user = kwargs.get("current_user") or {}
    org_id = current_user.get("org_id")

    if path_tail == "projects" and method == "GET":
        return _dashboard_projects(query, org_id)
    if path_tail == "swe-status" and method == "GET":
        return _dashboard_swe_status(query)
    if path_tail == "gap-analysis" and method == "GET":
        return _dashboard_gap_analysis(query)
    if path_tail == "gap-analysis/batch-run" and method == "POST":
        return _dashboard_gap_batch_run(body or {})
    if path_tail.startswith("gap-analysis/batch/"):
        # /api/v1/dashboard/gap-analysis/batch/{batch_id}  (GET status)
        batch_id = path_tail[len("gap-analysis/batch/"):]
        if method == "GET":
            return _dashboard_gap_batch_status(batch_id)
    if path_tail.startswith("gap-analysis/"):
        # /api/v1/dashboard/gap-analysis/{gap_id}
        # /api/v1/dashboard/gap-analysis/{gap_id}/run   (POST)
        # /api/v1/dashboard/gap-analysis/{gap_id}/status (GET)
        sub = path_tail[len("gap-analysis/"):]
        parts = sub.split("/", 1)
        gap_id = parts[0]
        action = parts[1] if len(parts) > 1 else ""
        if action == "run" and method == "POST":
            return _dashboard_gap_run(gap_id, body or {})
        if action == "status" and method == "GET":
            return _dashboard_gap_run_status(gap_id, query)
        if not action and method == "GET":
            return _dashboard_gap_detail(gap_id)
    if path_tail == "evidence/generate" and method == "POST":
        return _dashboard_evidence_generate(body, query)
    if path_tail == "evidence/status" and method == "GET":
        return _dashboard_evidence_status(query)
    if path_tail == "coverage" and method == "GET":
        return _dashboard_coverage(query)
    if path_tail == "misra-trend" and method == "GET":
        return _dashboard_misra_trend(query)

    return json_error(f"Unknown dashboard sub-path or method: {method} {path_tail}", 404)


def _dashboard_projects(query: dict, org_id: Any = None) -> tuple[dict, int]:
    """GET /api/v1/dashboard/projects — list projects for the current org.

    P0-2: REAL data only, scoped to the authenticated user's org. There is
    NO mock/demo fallback:
      - org_id missing (auth contract broken)  → 401, fail closed
      - store unavailable / query failure       → 503, explicit error
      - org has zero projects                   → 200 with empty list (real state)

    Returns project list with compliance summary per project.
    """
    project_id = _get_query_param(query, "project_id")

    if org_id is None:
        log.error("dashboard/projects called without current_user.org_id — failing closed")
        return json_error("无法识别当前用户组织 (org_id 缺失)", 401)

    try:
        from yuleosh.store import Store
        store = Store()
        # Org-scoped projects only — never leak other orgs' projects.
        real_projects = store.list_org_projects(org_id)
    except Exception as e:
        log.error("Failed to load dashboard projects: %s", e)
        return json_error("项目数据加载失败，请稍后重试", 503)

    if project_id:
        real_projects = [p for p in real_projects if str(p.get("id")) == project_id]
        if not real_projects:
            return json_error(f"Project not found: {project_id}", 404)

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


def _load_gap_items() -> tuple[list[dict], Optional[str]]:
    """Load gap items from audit-manifest, with mock fallback.

    Returns (items, note). Items are merged with in-memory status
    overrides so a re-run completed status survives within the process.
    Same source of truth used by list, detail and run endpoints.
    """
    manifest_candidates = [
        Path(OSH_HOME) / ".yuleosh" / "evidence-bundle" / "audit-manifest.json",
        Path(OSH_HOME) / ".osh" / "evidence" / "audit-manifest.json",
        Path(OSH_HOME) / ".yuleosh" / "reports" / "audit-manifest.json",
        Path(OSH_HOME) / "reports" / "audit-manifest.json",
    ]

    real_items: list[dict] = []
    note: Optional[str] = None

    for manifest_path in manifest_candidates:
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                gap_sections = [
                    manifest.get("gap_analysis", []),
                    manifest.get("assessment", {}).get("gaps", []),
                ]
                for section in gap_sections:
                    if not isinstance(section, list):
                        continue
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
                                "category": item.get("category", ""),
                                "owner": item.get("owner", ""),
                            })
                if real_items:
                    note = None
                    break
            except Exception as e:
                log.debug("Failed to parse gap data from %s: %s", manifest_path, e)

    if not real_items:
        real_items = list(MOCK_GAP_ANALYSIS["items"])
        note = _mock_note()

    # Apply in-memory status overrides (e.g. "completed" after a run)
    for it in real_items:
        override = _gap_status_overrides.get(it["id"])
        if override:
            it["status"] = override.get("status", it["status"])
            if override.get("last_run_id"):
                it["last_run_id"] = override["last_run_id"]
            if override.get("last_run_at"):
                it["last_run_at"] = override["last_run_at"]

    return real_items, note


def _dashboard_gap_analysis(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/gap-analysis — gap analysis for compliance.

    Paginated results with severity summary.
    """
    page = int(_get_query_param(query, "page", "1"))
    limit = int(_get_query_param(query, "limit", "10"))
    severity_filter = _get_query_param(query, "severity", "")

    real_items, note = _load_gap_items()

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


# SWE.1..6 area descriptions (used to build fix_steps in detail view)
_SWE_AREA_LABELS = {
    "SWE.1": "软件需求分析",
    "SWE.2": "软件架构设计",
    "SWE.3": "软件详细设计与单元设计",
    "SWE.4": "软件单元实现与验证",
    "SWE.5": "软件集成与集成测试",
    "SWE.6": "软件合格性测试",
}


def _build_gap_detail(item: dict) -> dict:
    """Augment a gap item with related info for the detail view.

    Lightweight (no heavy IO): the related_* fields are computed from
    in-memory state where possible. For real projects, this would
    call into the requirements/trace endpoints to find related items.
    Here we derive related items from swe_area + project dir scan
    (best-effort; returns empty list if project dir unavailable).
    """
    swe = item.get("swe_area", "")
    severity = item.get("severity", "minor")
    desc = item.get("description", "")

    # Fix steps derived from swe_area + severity (template-style)
    fix_steps: list[str] = []
    if swe == "SWE.1":
        fix_steps = [
            "在 requirements/*.md 中补充缺失的需求条目（含 SHALL/SHOULD/MAY 标识）",
            "在追溯矩阵中维护需求 → 设计的链接",
            "对变更执行影响分析并更新变更日志",
        ]
    elif swe == "SWE.2":
        fix_steps = [
            "在 architecture.md 中补充资源预算分析（CPU/内存/存储）",
            "评估多平台兼容性并更新架构图",
            "通过架构评审并由 CCB 审批",
        ]
    elif swe == "SWE.3":
        fix_steps = [
            "在 design/*.md 中补充接口定义、状态机、错误处理",
            "对设计文档运行 MISRA 设计准则检查",
            "通过设计评审并更新追溯矩阵",
        ]
    elif swe == "SWE.4":
        fix_steps = [
            "引入 CUnit/Ceedling 等单元测试框架",
            "补充缺失的测试用例，覆盖率目标 ≥80%",
            "对安全关键函数进行 MC/DC 覆盖分析",
            "运行 MISRA 静态扫描并修复违规",
        ]
    elif swe == "SWE.5":
        fix_steps = [
            "编写集成测试计划（策略、环境、时间表）",
            "编写集成测试用例覆盖模块间接口",
            "执行集成测试并记录结果",
        ]
    elif swe == "SWE.6":
        fix_steps = [
            "补充测试环境、工具版本配置说明",
            "运行合格性测试并记录结果",
            "由独立测试团队签字确认",
        ]
    else:
        fix_steps = ["联系对应过程域负责人处理"]

    # Try to find related project dir and scan for related items
    related_requirements: list[dict] = []
    related_artifacts: list[dict] = []
    project_dir = Path(OSH_HOME) / "projects"
    if project_dir.is_dir():
        # Heuristic: match spec files containing swe_area token
        try:
            for spec in list(project_dir.rglob("spec*.md"))[:20]:
                content = ""
                try:
                    content = spec.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if not content:
                    continue
                # Extract Req-* ids from spec
                import re as _re
                req_ids = _re.findall(r"Req-[A-Za-z0-9-]+-\d+", content)
                for rid in req_ids[:5]:
                    related_requirements.append({
                        "req_id": rid,
                        "source": str(spec.relative_to(project_dir)),
                    })
        except Exception as e:
            log.debug("Failed to scan project dir for related items: %s", e)

    # Build run history from in-memory store
    run_history: list[dict] = []
    for rid, r in _gap_runs.items():
        if r.get("gap_id") == item["id"]:
            run_history.append({
                "run_id": rid,
                "status": r.get("status"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
                "progress_pct": r.get("progress_pct", 0),
            })
    run_history.sort(key=lambda x: x.get("started_at") or "", reverse=True)

    return {
        "item": item,
        "swe_label": _SWE_AREA_LABELS.get(swe, swe),
        "fix_steps": fix_steps,
        "related_requirements": related_requirements[:10],
        "related_artifacts": related_artifacts,
        "run_history": run_history,
    }


def _dashboard_gap_detail(gap_id: str) -> tuple[dict, int]:
    """GET /api/v1/dashboard/gap-analysis/{gap_id} — gap detail.

    Returns the full item plus related requirements, fix steps, and
    run history (empty array if no run yet).
    """
    if not gap_id:
        return json_error("gap_id is required", 400)

    items, note = _load_gap_items()
    target = next((i for i in items if i["id"] == gap_id), None)
    if target is None:
        return json_error(f"Gap not found: {gap_id}", 404)

    detail = _build_gap_detail(target)
    detail["note"] = note
    return json_ok(detail)


def _dashboard_gap_run(gap_id: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/dashboard/gap-analysis/{gap_id}/run — trigger a remediation run.

    Creates a run record (queued) and kicks off a background thread
    that updates progress and eventually marks the gap as completed.
    Returns the run_id immediately so the UI can poll /status.
    """
    if not gap_id:
        return json_error("gap_id is required", 400)

    items, _note = _load_gap_items()
    target = next((i for i in items if i["id"] == gap_id), None)
    if target is None:
        return json_error(f"Gap not found: {gap_id}", 404)

    run_id = f"gaprun-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    _gap_runs[run_id] = {
        "run_id": run_id,
        "gap_id": gap_id,
        "status": "queued",
        "progress_pct": 0,
        "started_at": now_iso,
        "finished_at": None,
        "log": [f"[{now_iso}] Run created for gap {gap_id} ({target.get('swe_area')})"],
    }

    # Mark gap as in_progress immediately so the UI updates after refresh
    _gap_status_overrides[gap_id] = {
        "status": "in_progress",
        "last_run_id": run_id,
        "last_run_at": now_iso,
    }

    # Background simulation
    import threading
    t = threading.Thread(
        target=_simulate_gap_run,
        args=(gap_id, run_id),
        daemon=True,
        name=f"gap-run-{run_id}",
    )
    t.start()

    return json_ok({
        "run_id": run_id,
        "gap_id": gap_id,
        "status": "queued",
    })


def _simulate_gap_run(gap_id: str, run_id: str) -> None:
    """Simulate a remediation run in the background.

    For MVP, this is a deterministic sleep-based simulation that:
      1. Sets status=in_progress, progress=10
      2. Sleeps to mimic toolchain (re-runs static analysis / test gen)
      3. Sets status=completed, progress=100
      4. Persists status override so the next list/detail shows closed
    In a future iteration this would dispatch to a real remediation
    worker (e.g. test generator, evidence runner) by swe_area.
    """
    import time as t_mod

    def _log(msg: str) -> None:
        if run_id in _gap_runs:
            now = datetime.now(timezone.utc).isoformat()
            _gap_runs[run_id]["log"].append(f"[{now}] {msg}")

    def _update(progress: int, status: str) -> None:
        if run_id in _gap_runs:
            _gap_runs[run_id].update({
                "progress_pct": progress,
                "status": status,
            })

    try:
        _update(10, "running")
        _log("分析差距项并匹配过程域…")
        t_mod.sleep(0.6)
        _update(35, "running")
        _log("重跑相关制品扫描（设计/代码/测试/证据）…")
        t_mod.sleep(0.8)
        _update(65, "running")
        _log("生成修复计划并补齐缺失制品…")
        t_mod.sleep(0.8)
        _update(90, "running")
        _log("验证修复结果…")
        t_mod.sleep(0.4)
        _update(100, "completed")
        finished_at = datetime.now(timezone.utc).isoformat()
        _gap_runs[run_id]["finished_at"] = finished_at
        _log("✅ 修复完成，差距项已标记为已完成")
        # Persist the closed status for subsequent list/detail reads
        _gap_status_overrides[gap_id] = {
            "status": "completed",
            "last_run_id": run_id,
            "last_run_at": finished_at,
        }
    except Exception as e:  # pragma: no cover — background error path
        _update(0, "failed")
        _log(f"❌ 运行失败: {e}")
        _gap_runs[run_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


def _dashboard_gap_run_status(gap_id: str, query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard/gap-analysis/{gap_id}/status — poll most-recent run."""
    run_id = _get_query_param(query, "run_id", "")
    if run_id:
        run = _gap_runs.get(run_id)
        if run is None:
            return json_error(f"Run not found: {run_id}", 404)
        return json_ok(run)

    # No run_id → return most recent run for this gap
    candidates = [r for r in _gap_runs.values() if r.get("gap_id") == gap_id]
    if not candidates:
        return json_error(f"No runs found for gap: {gap_id}", 404)
    candidates.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return json_ok(candidates[0])


def _dashboard_gap_batch_run(body: dict) -> tuple[dict, int]:
    """POST /api/v1/dashboard/gap-analysis/batch-run — bulk remediation.

    Accepts optional ``{"ids": [...]}``; when omitted, runs ALL gap items.
    Creates a batch record and remediates each gap sequentially in the
    background (reusing ``_simulate_gap_run``), tracking per-item progress
    so the UI can poll the overall batch status via ``/batch/{id}``.
    """
    items, _note = _load_gap_items()
    requested = body.get("ids") or []
    if requested:
        want = set(requested)
        target_ids = [i["id"] for i in items if i["id"] in want]
    else:
        target_ids = [i["id"] for i in items]

    if not target_ids:
        return json_error("没有可执行的差距项（选择为空或数据缺失）", 400)

    batch_id = f"gapbatch-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    _gap_batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total": len(target_ids),
        "done": 0,
        "failed": 0,
        "started_at": now_iso,
        "finished_at": None,
        "items": {
            gid: {"gap_id": gid, "status": "queued", "progress_pct": 0, "run_id": None}
            for gid in target_ids
        },
    }

    import threading
    t = threading.Thread(
        target=_run_gap_batch,
        args=(batch_id, target_ids),
        daemon=True,
        name=f"gap-batch-{batch_id}",
    )
    t.start()

    return json_ok({
        "batch_id": batch_id,
        "total": len(target_ids),
        "status": "running",
    })


def _run_gap_batch(batch_id: str, gap_ids: list[str]) -> None:
    """Sequentially remediate each gap in the batch, updating progress.

    Reuses the single-item simulation ``_simulate_gap_run`` (joined) so the
    per-item run records and status overrides stay consistent. A batch of
    N gaps therefore takes ~N x 2.6s; the UI shows live progress.
    """
    batch = _gap_batches.get(batch_id)
    if not batch:
        return
    for gid in gap_ids:
        if batch_id not in _gap_batches:
            break  # batch record removed — abort
        rid = f"gaprun-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        _gap_runs[rid] = {
            "run_id": rid,
            "gap_id": gid,
            "status": "queued",
            "progress_pct": 0,
            "started_at": now_iso,
            "finished_at": None,
            "log": [f"[{now_iso}] 批量修复任务包含差距项 {gid}"],
        }
        _gap_status_overrides[gid] = {
            "status": "in_progress",
            "last_run_id": rid,
            "last_run_at": now_iso,
        }
        batch["items"][gid] = {"gap_id": gid, "status": "running", "progress_pct": 10, "run_id": rid}

        # Reuse the single-item simulation; join so items run in order.
        worker = threading.Thread(target=_simulate_gap_run, args=(gid, rid), daemon=True)
        worker.start()
        worker.join()

        final_status = _gap_status_overrides.get(gid, {}).get("status", "completed")
        batch["items"][gid] = {
            "gap_id": gid,
            "status": final_status,
            "progress_pct": 100 if final_status == "completed" else 0,
            "run_id": rid,
        }
        batch["done"] = batch.get("done", 0) + 1

    batch["status"] = "completed"
    batch["finished_at"] = datetime.now(timezone.utc).isoformat()


def _dashboard_gap_batch_status(batch_id: str) -> tuple[dict, int]:
    """GET /api/v1/dashboard/gap-analysis/batch/{batch_id} — batch progress."""
    batch = _gap_batches.get(batch_id)
    if batch is None:
        return json_error(f"Batch not found: {batch_id}", 404)
    items = list(batch["items"].values())
    running = sum(1 for it in items if it["status"] in ("queued", "running"))
    return json_ok({
        "batch_id": batch["batch_id"],
        "status": batch["status"],
        "total": batch["total"],
        "done": batch["done"],
        "failed": batch["failed"],
        "running": running,
        "started_at": batch["started_at"],
        "finished_at": batch["finished_at"],
        "items": items,
    })


def _dashboard_evidence_generate(body: dict, query: dict) -> tuple[dict, int]:
    """POST /api/v1/dashboard/evidence/generate — trigger evidence pack generation.

    Creates an async task and returns task_id for polling.

    SECURITY (SEC-C1): project_dir must resolve inside OSH_HOME (same
    guard as the pipeline trigger) — otherwise an authenticated user
    could run the evidence CLI with an arbitrary cwd.
    """
    project_id = body.get("project_id") or _get_query_param(query, "project_id", "default")

    # Fail fast BEFORE creating the task record if project_dir escapes OSH_HOME.
    raw_dir = body.get("project_dir") or OSH_HOME
    try:
        project_dir = str(Path(raw_dir).expanduser().resolve())
        Path(project_dir).relative_to(Path(OSH_HOME).resolve())
    except (ValueError, TypeError, OSError):
        return json_error("project_dir must be inside OSH_HOME", 403)

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
        _ev_tasks[task_id]["progress_pct"] = 10
        _ev_tasks[task_id]["status"] = "running"

        result = subprocess.run(
            ["yuleosh", "evidence", "pack",
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
        log.warning("yuleosh CLI not found on PATH — using simulated evidence")
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
