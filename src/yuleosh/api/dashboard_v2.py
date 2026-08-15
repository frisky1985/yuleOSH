#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Dashboard v2 API — 数据座舱增强聚合端点（docs/architecture/dashboard-design.md 模块⑧）。

新增端点（路由注册由主 agent 统一在 api/router.py 完成，本模块不碰 router）:

    GET /api/v1/dashboard-v2/overview          — 座舱聚合（合规总分五维加权 + 各指标卡）
    GET /api/v1/dashboard-v2/recent-pipelines  — 最近 10 条流水线（store.pipelines）
    GET /api/v1/dashboard-v2/device-status     — 设备状态汇总（device.db）
    GET /api/v1/dashboard-v2/tests-summary     — 三层测试汇总（unit/integration/qualification）

数据真实优先：无数据时显式返回 0/空 + note 标注，禁止造演示数据
（对齐 dashboard.py 现有原则；dashboard 端点的演示回退数据不会泄漏进 v2）。

合规总分（第七章决策 5）：五维加权可配置，默认权重
    覆盖率 30 / 测试通过率 25 / MISRA 违规 20 / 需求追溯 15 / 证据完整性 10。
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.dashboard_v2")

# Project root / OSH_HOME（与 dashboard.py 相同约定）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

# ── 第七章决策 5：合规总分五维权重（默认值，可配置）──────────────────
DIMENSION_WEIGHTS = {
    "coverage": 0.30,        # 覆盖率
    "test_pass_rate": 0.25,  # 测试通过率
    "misra": 0.20,           # MISRA 违规
    "traceability": 0.15,    # 需求追溯
    "evidence": 0.10,        # 证据完整性
}

DIMENSION_LABELS = {
    "coverage": "覆盖率",
    "test_pass_rate": "测试通过率",
    "misra": "MISRA 违规",
    "traceability": "需求追溯",
    "evidence": "证据完整性",
}

# 设备状态（yuleosh.device.models.DeviceState 的 value 集合）
DEVICE_STATES = ("online", "busy", "offline", "fault", "unknown")

# 测试通过率统计窗口（第七章指标定义：最近 100 次 run）
TEST_PASS_RUN_LIMIT = 100

# MISRA 维度分：每个违规扣 5 分，20 个及以上归零（0 违规 = 100 分）
MISRA_PENALTY_PER_VIOLATION = 5.0

# 证据完整性维度分：每个 artifact 计 10 分，10 个及以上满分
EVIDENCE_POINTS_PER_ARTIFACT = 10.0

# 三层测试 stage 名关键词 → 层
_TEST_LAYER_KEYWORDS = {
    "unit": ("unit",),
    "integration": ("integ", "e2e", "sil"),
    "qualification": ("qualif",),
}


@require_auth
def handle_dashboard_v2(method: str, path_tail: str, body: dict, query: dict,
                        handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/dashboard-v2/... requests.

    Note: `**kwargs` absorbs the `current_user` injected by require_auth
    (user_id/org_id/email/role) so the decorated signature stays compatible.

    Supported routes:
        GET  /api/v1/dashboard-v2/overview          — 数据座舱聚合
        GET  /api/v1/dashboard-v2/recent-pipelines  — 最近流水线
        GET  /api/v1/dashboard-v2/device-status     — 设备状态汇总
        GET  /api/v1/dashboard-v2/tests-summary     — 三层测试汇总
    """
    current_user = kwargs.get("current_user") or {}
    org_id = current_user.get("org_id")

    if path_tail == "overview" and method == "GET":
        return _overview(query, org_id)
    if path_tail == "recent-pipelines" and method == "GET":
        return _recent_pipelines(query, org_id)
    if path_tail == "device-status" and method == "GET":
        return _device_status(query)
    if path_tail == "tests-summary" and method == "GET":
        return _tests_summary(query)

    return json_error(f"Unknown dashboard-v2 sub-path or method: {method} {path_tail}", 404)


# ── GET /api/v1/dashboard-v2/overview ─────────────────────────────────

def _overview(query: dict, org_id: Any = None) -> tuple[dict, int]:
    """GET /api/v1/dashboard-v2/overview — 数据座舱聚合。

    返回合规总分（五维加权）、五维明细、覆盖率、测试通过率、MISRA 违规数、
    活跃流水线数、项目数、设备状态汇总。所有指标均来自真实数据源；无数据
    时显式返回 0/空并在 note 标注原因（禁止造演示数据）。
    """
    coverage, cov_note = _load_coverage()
    pass_rate, pass_note = _load_test_pass_rate()
    misra_count, misra_note = _load_misra_violations()
    trace_score, trace_note = _load_traceability_score()
    evidence_score, ev_note = _load_evidence_score()

    # MISRA 无数据时不得按"0 违规"给满分 —— 无数据即 0 分 + note（数据真实优先）
    misra_score = _misra_score(misra_count) if misra_note is None else 0.0

    dimension_inputs = [
        ("coverage", coverage, cov_note),
        ("test_pass_rate", pass_rate, pass_note),
        ("misra", misra_score, misra_note),
        ("traceability", trace_score, trace_note),
        ("evidence", evidence_score, ev_note),
    ]

    dimensions = []
    total = 0.0
    for key, raw_score, note in dimension_inputs:
        score = max(0.0, min(100.0, float(raw_score)))
        dim = {
            "key": key,
            "label": DIMENSION_LABELS[key],
            "score": round(score, 2),
            "weight": DIMENSION_WEIGHTS[key],
            "status": _dimension_status(score),
            "note": note,
        }
        dimensions.append(dim)
        total += dim["score"] * dim["weight"]

    pipelines = _load_pipelines()
    active_pipelines = sum(
        1 for p in pipelines
        if (p.get("status") or "").lower() in ("running", "in_progress")
    )

    projects_count, projects_note = _load_projects_count(org_id)
    devices_summary, devices_note = _load_device_summary()

    notes = []
    for _, _, n in dimension_inputs:
        if n and n not in notes:
            notes.append(n)
    for n in (projects_note, devices_note):
        if n and n not in notes:
            notes.append(n)
    note = "；".join(notes) if notes else None

    return json_ok({
        "compliance_score": round(total, 1),
        "dimensions": dimensions,
        "coverage": round(float(coverage), 2),
        "test_pass_rate": round(float(pass_rate), 2),
        "misra_violations": int(misra_count),
        "active_pipelines": int(active_pipelines),
        "projects_count": int(projects_count),
        "devices_summary": devices_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    })


def _dimension_status(score: float) -> str:
    """维度健康状态：>=80 good / >=60 warning / 其余 critical。"""
    if score >= 80:
        return "good"
    if score >= 60:
        return "warning"
    return "critical"


def _misra_score(violations: int) -> float:
    """MISRA 维度分（0-100）：每个违规扣 5 分，20 个及以上归零。"""
    return max(0.0, 100.0 - float(violations) * MISRA_PENALTY_PER_VIOLATION)


# ── 各指标真实数据加载器（无数据 → 0/空 + note，禁止演示数据）────────

def _load_coverage() -> tuple[float, Optional[str]]:
    """覆盖率 line_rate —— 复用现有 dashboard._dashboard_coverage。

    dashboard 的 coverage 端点在无真实报告时回退演示数据（note 含 ⚠️ 演示数据）。
    v2 数据真实优先：识别到演示回退即视为无数据，返回 0.0 + note。
    """
    try:
        from yuleosh.api.dashboard import _dashboard_coverage
        payload, _ = _dashboard_coverage({})
        data = payload.get("data") or {}
        if data.get("note"):
            # dashboard 端点的演示数据回退 —— 不泄漏进 v2
            return 0.0, "覆盖率无真实数据（.yuleosh/reports/c-coverage.json 缺失）"
        return float(data.get("line_pct", 0.0) or 0.0), None
    except Exception as e:
        log.debug("Failed to load coverage for dashboard-v2: %s", e)
        return 0.0, "覆盖率数据加载失败"


def _load_test_pass_rate() -> tuple[float, Optional[str]]:
    """测试通过率 —— store.ci_runs 最近 TEST_PASS_RUN_LIMIT 次运行。"""
    try:
        from yuleosh.store import Store
        runs = Store().list_ci(limit=TEST_PASS_RUN_LIMIT)
    except Exception as e:
        log.debug("Failed to load test runs for dashboard-v2: %s", e)
        return 0.0, "测试运行数据加载失败"

    finished = [r for r in runs if (r.get("status") or "").lower() in ("passed", "failed")]
    if not finished:
        return 0.0, f"无测试运行数据（最近 {TEST_PASS_RUN_LIMIT} 次运行无完成记录）"
    passed = sum(1 for r in finished if (r.get("status") or "").lower() == "passed")
    return round(passed / len(finished) * 100.0, 2), None


def _load_misra_violations() -> tuple[int, Optional[str]]:
    """MISRA 违规数 —— .yuleosh/reports/misra-trend.jsonl 最近一条记录。"""
    try:
        trend_path = Path(OSH_HOME) / ".yuleosh" / "reports" / "misra-trend.jsonl"
        if trend_path.exists():
            entries = []
            with open(trend_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError):
                            continue
            if entries:
                latest = entries[-1]
                return int(latest.get("total_violations", 0) or 0), None
    except Exception as e:
        log.debug("Failed to load misra trend for dashboard-v2: %s", e)
    return 0, "无 MISRA 违规数据（.yuleosh/reports/misra-trend.jsonl 缺失）"


def _find_manifest() -> Optional[Path]:
    """定位最新 audit-manifest.json（对齐 dashboard.py 的候选路径）。"""
    candidates = [
        Path(OSH_HOME) / ".yuleosh" / "evidence-bundle" / "audit-manifest.json",
        Path(OSH_HOME) / ".osh" / "evidence" / "audit-manifest.json",
        Path(OSH_HOME) / ".yuleosh" / "reports" / "audit-manifest.json",
        Path(OSH_HOME) / "reports" / "audit-manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_traceability_score() -> tuple[float, Optional[str]]:
    """需求追溯维度分（0-100）—— audit-manifest.traceability。

    支持三种形态（按优先级）：
      - {"score": 0-100}
      - {"ratio": 0-1}
      - {"linked": N, "total": M}
      - [链接列表] → 每 10 条计满分（min(len*10, 100)）
    """
    manifest_path = _find_manifest()
    if manifest_path is None:
        return 0.0, "无需求追溯数据（audit-manifest.json 缺失）"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        trace = manifest.get("traceability")
        if isinstance(trace, dict):
            score = trace.get("score")
            if isinstance(score, (int, float)):
                return float(score), None
            ratio = trace.get("ratio")
            if isinstance(ratio, (int, float)):
                return float(ratio) * 100.0, None
            linked, total = trace.get("linked"), trace.get("total")
            if isinstance(linked, (int, float)) and isinstance(total, (int, float)) and total:
                return float(linked) / float(total) * 100.0, None
        if isinstance(trace, list) and trace:
            return min(100.0, len(trace) * 10.0), None
    except Exception as e:
        log.debug("Failed to parse traceability from manifest: %s", e)
    return 0.0, "无需求追溯数据（audit-manifest.json 无 traceability 段）"


def _load_evidence_score() -> tuple[float, Optional[str]]:
    """证据完整性维度分（0-100）—— audit-manifest.integrity.total_artifacts。"""
    manifest_path = _find_manifest()
    if manifest_path is None:
        return 0.0, "无证据完整性数据（audit-manifest.json 缺失）"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        integrity = manifest.get("integrity") or {}
        total_artifacts = integrity.get("total_artifacts")
        if isinstance(total_artifacts, (int, float)):
            return min(100.0, float(total_artifacts) * EVIDENCE_POINTS_PER_ARTIFACT), None
    except Exception as e:
        log.debug("Failed to parse evidence integrity from manifest: %s", e)
    return 0.0, "无证据完整性数据（audit-manifest.json 无 integrity 段）"


def _load_pipelines() -> list[dict]:
    """流水线列表 —— store.pipelines（pipelines 表当前无 org 列，全局数据）。"""
    try:
        from yuleosh.store import Store
        return Store().list_pipelines()
    except Exception as e:
        log.debug("Failed to load pipelines for dashboard-v2: %s", e)
        return []


def _load_projects_count(org_id: Any = None) -> tuple[int, Optional[str]]:
    """项目数 —— store.list_org_projects(org_id) 按当前用户组织过滤。"""
    if org_id is None:
        return 0, "无法识别当前用户组织（org_id 缺失）"
    try:
        from yuleosh.store import Store
        return len(Store().list_org_projects(org_id)), None
    except Exception as e:
        log.debug("Failed to load projects count for dashboard-v2: %s", e)
        return 0, "项目数据加载失败"


def _load_device_summary() -> tuple[dict, Optional[str]]:
    """设备状态汇总 —— DeviceRegistry.list_devices() 按 state 聚合。

    db_path 使用 DeviceRegistry 默认值：~/.yuleosh/device.db 或
    YULEOSH_DEVICE_DB 环境变量（registry 内部解析）。
    """
    summary = {s: 0 for s in DEVICE_STATES}
    try:
        from yuleosh.device.registry import DeviceRegistry
        devices = DeviceRegistry().list_devices()
    except Exception as e:
        log.debug("Failed to load devices for dashboard-v2: %s", e)
        return summary, "设备数据不可用（device.db 未初始化）"
    for dev in devices:
        state = getattr(getattr(dev, "state", None), "value", None)
        if state not in summary:
            state = "unknown"
        summary[state] += 1
    if not devices:
        return summary, "无设备数据"
    return summary, None


# ── GET /api/v1/dashboard-v2/recent-pipelines ─────────────────────────

def _recent_pipelines(query: dict, org_id: Any = None) -> tuple[dict, int]:
    """GET /api/v1/dashboard-v2/recent-pipelines — 最近 10 条流水线。

    复用 store.pipelines 表（list_pipelines 按 created_at DESC）。
    org_id 保留在签名中以便后续接入 org 过滤；当前 pipelines 表无 org 列。
    """
    try:
        from yuleosh.store import Store
        rows = Store().list_pipelines()
    except Exception as e:
        log.error("Failed to load recent pipelines: %s", e)
        return json_error("流水线数据加载失败，请稍后重试", 503)

    items = []
    for row in rows[:10]:
        items.append({
            "name": row.get("name", ""),
            "status": row.get("status", ""),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        })

    note = "无流水线数据" if not items else None
    return json_ok({
        "pipelines": items,
        "count": len(items),
        "note": note,
    })


# ── GET /api/v1/dashboard-v2/device-status ────────────────────────────

def _device_status(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard-v2/device-status — 设备状态汇总（device.db）。"""
    summary, note = _load_device_summary()
    return json_ok({
        "summary": summary,
        "total": sum(summary.values()),
        "note": note,
    })


# ── GET /api/v1/dashboard-v2/tests-summary ────────────────────────────

def _classify_test_layer(stage_name: str) -> Optional[str]:
    """把 ci stage 名归类到三层测试之一（unit/integration/qualification）。"""
    name = (stage_name or "").lower()
    for layer, keywords in _TEST_LAYER_KEYWORDS.items():
        if any(k in name for k in keywords):
            return layer
    return None


def _tests_summary(query: dict) -> tuple[dict, int]:
    """GET /api/v1/dashboard-v2/tests-summary — 三层测试汇总。

    数据源：store.ci_runs.stages（最近 10 次运行的 stage 结果），按 stage 名
    关键词归类到 unit / integration / qualification 三层，统计 pass/fail/skip。
    无数据时返回全 0 统计 + note 字段说明无数据（禁止造演示数据）。
    """
    layers = {
        "unit": {"pass": 0, "fail": 0, "skip": 0},
        "integration": {"pass": 0, "fail": 0, "skip": 0},
        "qualification": {"pass": 0, "fail": 0, "skip": 0},
    }
    try:
        from yuleosh.store import Store
        runs = Store().list_ci(limit=10)
    except Exception as e:
        log.debug("Failed to load ci runs for tests-summary: %s", e)
        return json_ok({"layers": layers, "note": "测试数据加载失败"})

    stage_status_map = {
        "passed": "pass",
        "failed": "fail",
        "error": "fail",
        "skipped": "skip",
    }
    found = False
    for run in runs:
        raw_stages = run.get("stages") or "[]"
        try:
            stages = json.loads(raw_stages) if isinstance(raw_stages, str) else raw_stages
        except (json.JSONDecodeError, TypeError, ValueError):
            stages = []
        if not isinstance(stages, list):
            continue
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            layer = _classify_test_layer(str(stage.get("name", "")))
            status = str(stage.get("status", "")).lower()
            if layer is None or status not in stage_status_map:
                continue
            layers[layer][stage_status_map[status]] += 1
            found = True

    note = None if found else "无测试数据（ci_runs 无三层测试 stage 记录）"
    return json_ok({"layers": layers, "note": note})
