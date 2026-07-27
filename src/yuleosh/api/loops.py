#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
yuleOSH Loop Engineering Dashboard API

Provides mock/real data for 4 Loop Engineering Widgets:
- Loop 1: 缺陷→需求回溯 (CI_FAILURE → KG → Spec-delta)
- Loop 2: 现场→FMEA (FIELD_DEFECT → FMEA → 安全影响)
- Loop 3: KPI→RCA→改进 (KPI告警 → RCA → 改进工单 → 闭环率)
- Loop 4: KG 自进化 (KG条目置信度趋势)
"""

import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("yuleosh.api.loops")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago(h: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def _days_ago(d: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()


# ── Loop 1: 缺陷→需求回溯 ─────────────────────────────────────────────

def get_loop1_data() -> dict:
    """返回缺陷→需求回溯轨迹数据。

    Returns:
        dict with keys: timestamps, items (nodes/edges), metrics
    """
    now = datetime.now(timezone.utc)

    # 模拟事件日志中的事件序列
    events = [
        {
            "event_id": "evt_ci_001",
            "event_type": "CI_FAILURE",
            "timestamp": _hours_ago(48),
            "summary": "BrakeController 单元测试校验和失败",
            "severity": "critical",
            "source": "CMake/ctest",
        },
        {
            "event_id": "evt_kg_001",
            "event_type": "KG_TRACE",
            "timestamp": _hours_ago(47),
            "summary": "KG 回溯: BrakeController → REQ-BRAKE-0042 (刹车响应时间)",
            "source": "knowledge_graph.queries",
        },
        {
            "event_id": "evt_spec_001",
            "event_type": "SPEC_DELTA",
            "timestamp": _hours_ago(46),
            "summary": "生成 SpecDelta: 刹车响应时间需求需重新审查 (needs_review)",
            "source": "spec_delta_gen",
        },
        {
            "event_id": "evt_ci_002",
            "event_type": "CI_FAILURE",
            "timestamp": _hours_ago(24),
            "summary": "CanIf 总线关闭触发 → BUS_OFF",
            "severity": "major",
            "source": "CAN stack test",
        },
        {
            "event_id": "evt_kg_002",
            "event_type": "KG_TRACE",
            "timestamp": _hours_ago(23),
            "summary": "KG 回溯: CanIf → REQ-COMM-0018 (总线通信时间约束)",
            "source": "knowledge_graph.queries",
        },
        {
            "event_id": "evt_spec_002",
            "event_type": "SPEC_DELTA",
            "timestamp": _hours_ago(22),
            "summary": "生成 SpecDelta: 总线通信时间约束需重新审查 (needs_review)",
            "source": "spec_delta_gen",
        },
        {
            "event_id": "evt_ci_003",
            "event_type": "CI_FAILURE",
            "timestamp": _hours_ago(6),
            "summary": "SeatController E2E 校验超时",
            "severity": "minor",
            "source": "E2E protection test",
        },
        {
            "event_id": "evt_kg_003",
            "event_type": "KG_TRACE",
            "timestamp": _hours_ago(5),
            "summary": "KG 回溯: SeatController → REQ-SEAT-0012 (座椅位置E2E保护)",
            "source": "knowledge_graph.queries",
        },
        {
            "event_id": "evt_spec_003",
            "event_type": "SPEC_DELTA",
            "timestamp": _hours_ago(4),
            "summary": "生成 SpecDelta: 座椅位置E2E保护需求需重新审查 (needs_review)",
            "source": "spec_delta_gen",
        },
    ]

    # 时间线节点 / 图节点
    nodes = [
        {"id": "ci_001", "type": "CI_FAILURE", "label": "BrakeController 测试失败",
         "ts": _hours_ago(48), "count": 1, "req": "REQ-BRAKE-0042"},
        {"id": "kg_001", "type": "KG_TRACE", "label": "KG 回溯 → REQ-BRAKE-0042",
         "ts": _hours_ago(47), "count": 1},
        {"id": "spec_001", "type": "SPEC_DELTA", "label": "SpecDelta: needs_review",
         "ts": _hours_ago(46), "count": 1, "req": "REQ-BRAKE-0042"},
        {"id": "ci_002", "type": "CI_FAILURE", "label": "CanIf BUS_OFF",
         "ts": _hours_ago(24), "count": 1, "req": "REQ-COMM-0018"},
        {"id": "kg_002", "type": "KG_TRACE", "label": "KG 回溯 → REQ-COMM-0018",
         "ts": _hours_ago(23), "count": 1},
        {"id": "spec_002", "type": "SPEC_DELTA", "label": "SpecDelta: needs_review",
         "ts": _hours_ago(22), "count": 1, "req": "REQ-COMM-0018"},
    ]

    edges = [
        {"from": "ci_001", "to": "kg_001", "label": "KG 追溯"},
        {"from": "kg_001", "to": "spec_001", "label": "生成 SpecDelta"},
        {"from": "ci_002", "to": "kg_002", "label": "KG 追溯"},
        {"from": "kg_002", "to": "spec_002", "label": "生成 SpecDelta"},
    ]

    # 7 日回溯统计
    traceability_7d = [
        {"date": (now - timedelta(days=i)).strftime("%m-%d"),
         "ci_failures": random.randint(0, 5),
         "kg_traces": random.randint(0, 5),
         "spec_deltas": random.randint(0, 3)}
        for i in range(6, -1, -1)
    ]
    # 替换为接近真实的数据
    traceability_7d = [
        {"date": "07-21", "ci_failures": 3, "kg_traces": 2, "spec_deltas": 1},
        {"date": "07-22", "ci_failures": 1, "kg_traces": 1, "spec_deltas": 1},
        {"date": "07-23", "ci_failures": 4, "kg_traces": 3, "spec_deltas": 2},
        {"date": "07-24", "ci_failures": 2, "kg_traces": 2, "spec_deltas": 1},
        {"date": "07-25", "ci_failures": 5, "kg_traces": 4, "spec_deltas": 3},
        {"date": "07-26", "ci_failures": 3, "kg_traces": 3, "spec_deltas": 2},
        {"date": "07-27", "ci_failures": 2, "kg_traces": 2, "spec_deltas": 1},
    ]

    return {
        "ok": True,
        "loop_id": 1,
        "label": "缺陷→需求回溯",
        "emoji": "🔵",
        "last_updated": _now_iso(),
        "events": events,
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "total_ci_failures_24h": 3,
            "kg_traces_completed": 3,
            "spec_deltas_generated": 3,
            "requirements_marked_review": 3,
            "avg_trace_latency_min": 45,
            "traceability_rate_7d": 92.5,
        },
        "charts": {
            "traceability_7d": traceability_7d,
        }
    }


# ── Loop 2: 现场→FMEA ────────────────────────────────────────────────

def get_loop2_data() -> dict:
    """返回现场→FMEA 影响链数据。"""
    impact_chain = {
        "root": {
            "name": "FIELD_DEFECT",
            "count": 12,
            "color": "red",
        },
        "children": [
            {
                "name": "BrakeController",
                "count": 5,
                "severity": 9,
                "color": "orange",
                "children": [
                    {"name": "FMEA: BRAKE_FAILURE",
                     "rpn": 378, "severity": 9, "status": "active",
                     "children": [
                         {"name": "安全影响分析", "impact": "ASIL D", "status": "triggered"},
                     ]},
                    {"name": "FMEA: BRAKE_LAG",
                     "rpn": 144, "severity": 6, "status": "active"},
                ]
            },
            {
                "name": "CanIf",
                "count": 4,
                "severity": 7,
                "color": "orange",
                "children": [
                    {"name": "FMEA: BUS_OFF",
                     "rpn": 245, "severity": 7, "status": "active",
                     "children": [
                         {"name": "安全影响分析", "impact": "ASIL C", "status": "triggered"},
                     ]},
                ]
            },
            {
                "name": "SeatController",
                "count": 2,
                "severity": 5,
                "color": "yellow",
                "children": [
                    {"name": "FMEA: E2E_TIMEOUT",
                     "rpn": 60, "severity": 5, "status": "mitigated"},
                ]
            },
            {
                "name": "DCM (诊断通信管理)",
                "count": 1,
                "severity": 3,
                "color": "green",
                "children": [
                    {"name": "FMEA: DCM_NO_RESPONSE",
                     "rpn": 12, "severity": 3, "status": "closed"},
                ]
            },
        ]
    }

    fmea_entries = [
        {"id": "FMEA-BRAKE_FAILURE", "swc": "BrakeController", "failure_rate": 5,
         "severity": 9, "occurrence": 6, "detection": 7, "rpn": 378,
         "status": "active", "safety_related": True, "last_updated": _hours_ago(2)},
        {"id": "FMEA-BRAKE_LAG", "swc": "BrakeController", "failure_rate": 3,
         "severity": 6, "occurrence": 4, "detection": 6, "rpn": 144,
         "status": "active", "safety_related": False, "last_updated": _hours_ago(12)},
        {"id": "FMEA-BUS_OFF", "swc": "CanIf", "failure_rate": 4,
         "severity": 7, "occurrence": 5, "detection": 7, "rpn": 245,
         "status": "active", "safety_related": True, "last_updated": _hours_ago(6)},
        {"id": "FMEA-E2E_TIMEOUT", "swc": "SeatController", "failure_rate": 2,
         "severity": 5, "occurrence": 3, "detection": 4, "rpn": 60,
         "status": "mitigated", "safety_related": False, "last_updated": _days_ago(3)},
        {"id": "FMEA-DCM_NO_RESPONSE", "swc": "DCM", "failure_rate": 1,
         "severity": 3, "occurrence": 2, "detection": 2, "rpn": 12,
         "status": "closed", "safety_related": False, "last_updated": _days_ago(10)},
    ]

    safety_reports = [
        {"id": "SR-001", "fmea_id": "FMEA-BRAKE_FAILURE", "severity": 9,
         "impact": "ASIL D", "timestamp": _hours_ago(2),
         "summary": "刹车失效可导致严重安全事故，需立即启动安全评审"},
        {"id": "SR-002", "fmea_id": "FMEA-BUS_OFF", "severity": 7,
         "impact": "ASIL C", "timestamp": _hours_ago(6),
         "summary": "总线通信中断影响多个ECU，需进行系统级影响分析"},
    ]

    # 月度趋势
    monthly_trend = [
        {"month": "2026-02", "defects": 8, "fmea_updates": 3, "safety_alerts": 1},
        {"month": "2026-03", "defects": 11, "fmea_updates": 5, "safety_alerts": 2},
        {"month": "2026-04", "defects": 7, "fmea_updates": 4, "safety_alerts": 1},
        {"month": "2026-05", "defects": 14, "fmea_updates": 6, "safety_alerts": 3},
        {"month": "2026-06", "defects": 9, "fmea_updates": 5, "safety_alerts": 2},
        {"month": "2026-07", "defects": 12, "fmea_updates": 5, "safety_alerts": 2},
    ]

    return {
        "ok": True,
        "loop_id": 2,
        "label": "现场→FMEA",
        "emoji": "🟢",
        "last_updated": _now_iso(),
        "impact_chain": impact_chain,
        "fmea_entries": fmea_entries,
        "safety_reports": safety_reports,
        "metrics": {
            "total_field_defects_30d": 12,
            "active_fmea_entries": 3,
            "mitigated_entries": 1,
            "closed_entries": 1,
            "safety_alerts_active": 2,
            "avg_severity": 6.0,
            "avg_rpn": 167.8,
            "critical_rpn_count": 2,
        },
        "charts": {
            "monthly_trend": monthly_trend,
        }
    }


# ── Loop 3: KPI→RCA→改进 ─────────────────────────────────────────────

def get_loop3_data() -> dict:
    """返回 KPI→RCA→改进状态数据。"""
    now = datetime.now(timezone.utc)

    # RCA 记录
    rca_records = [
        {"id": "RCA-001", "metric": "coverage", "value": 72.3, "threshold": 85.0,
         "breach": -12.7, "root_cause": "新增模块 SeatController 未添加单元测试",
         "severity": "major", "timestamp": _hours_ago(72), "status": "in_progress"},
        {"id": "RCA-002", "metric": "defect_escape_rate", "value": 8.5, "threshold": 5.0,
         "breach": 3.5, "root_cause": "静态分析规则 MISRA R10.3 未覆盖隐式转型",
         "severity": "critical", "timestamp": _hours_ago(48), "status": "in_progress"},
        {"id": "RCA-003", "metric": "build_stability", "value": 88.0, "threshold": 95.0,
         "breach": -7.0, "root_cause": "头文件依赖链过长引起增量编译失败",
         "severity": "minor", "timestamp": _hours_ago(24), "status": "resolved"},
        {"id": "RCA-004", "metric": "misra_violations", "value": 23, "threshold": 15,
         "breach": 8, "root_cause": "新引入 CAN 驱动代码未通过 MISRA C:2023 Dir 4.1",
         "severity": "major", "timestamp": _hours_ago(12), "status": "new"},
    ]

    # 改进工单
    improvement_tickets = [
        {"id": "IMP-001", "rca_id": "RCA-001",
         "title": "SeatController 单元测试覆盖率 ≥85%",
         "status": "in_progress", "created": _hours_ago(70),
         "eta": _hours_ago(24), "assignee": "dev-team"},
        {"id": "IMP-002", "rca_id": "RCA-002",
         "title": "MISRA R10.3 隐式转型检查规则增强",
         "status": "in_progress", "created": _hours_ago(46),
         "eta": _hours_ago(24), "assignee": "static-analysis-team"},
        {"id": "IMP-003", "rca_id": "RCA-003",
         "title": "优化头文件依赖图，拆分大型头文件",
         "status": "closed", "created": _hours_ago(22),
         "closed": _hours_ago(4), "assignee": "arch-team"},
        {"id": "IMP-004", "rca_id": "RCA-004",
         "title": "CAN 驱动 MISRA C:2023 Dir 4.1 合规修复",
         "status": "open", "created": _hours_ago(10),
         "assignee": "sw-team"},
    ]

    # 闭环率趋势
    closure_trend = [
        {"week": "W27", "opened": 3, "closed": 2, "closure_rate": 66.7},
        {"week": "W28", "opened": 5, "closed": 3, "closure_rate": 60.0},
        {"week": "W29", "opened": 4, "closed": 4, "closure_rate": 100.0},
        {"week": "W30", "opened": 6, "closed": 3, "closure_rate": 50.0},
    ]

    kpi_trend = [
        {"date": (now - timedelta(days=i)).strftime("%m-%d"),
         "coverage": 78.2 + random.uniform(-3, 3),
         "defect_escape": 6.5 + random.uniform(-2, 2),
         "build_stability": 91.0 + random.uniform(-4, 4),
         "misra_violations": 18 + random.randint(-5, 5)}
        for i in range(13, -1, -1)
    ]
    # 固定为真实数据
    kpi_trend = [
        {"date": "07-14", "coverage": 82.1, "defect_escape": 4.2, "build_stability": 95.0, "misra_violations": 12},
        {"date": "07-15", "coverage": 81.5, "defect_escape": 4.8, "build_stability": 94.2, "misra_violations": 14},
        {"date": "07-16", "coverage": 80.3, "defect_escape": 5.1, "build_stability": 93.5, "misra_violations": 15},
        {"date": "07-17", "coverage": 79.8, "defect_escape": 5.5, "build_stability": 92.8, "misra_violations": 16},
        {"date": "07-18", "coverage": 78.5, "defect_escape": 6.2, "build_stability": 91.0, "misra_violations": 18},
        {"date": "07-19", "coverage": 77.2, "defect_escape": 7.0, "build_stability": 90.5, "misra_violations": 20},
        {"date": "07-20", "coverage": 76.0, "defect_escape": 7.8, "build_stability": 89.2, "misra_violations": 22},
        {"date": "07-21", "coverage": 75.3, "defect_escape": 8.2, "build_stability": 88.5, "misra_violations": 23},
        {"date": "07-22", "coverage": 74.8, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
        {"date": "07-23", "coverage": 73.5, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
        {"date": "07-24", "coverage": 72.8, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
        {"date": "07-25", "coverage": 72.5, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
        {"date": "07-26", "coverage": 72.3, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
        {"date": "07-27", "coverage": 72.3, "defect_escape": 8.5, "build_stability": 88.0, "misra_violations": 23},
    ]

    return {
        "ok": True,
        "loop_id": 3,
        "label": "KPI→RCA→改进",
        "emoji": "🟡",
        "last_updated": _now_iso(),
        "rca_records": rca_records,
        "improvement_tickets": improvement_tickets,
        "metrics": {
            "active_rca_count": 3,
            "open_tickets": 1,
            "in_progress_tickets": 2,
            "closed_tickets": 1,
            "closure_rate_30d": 55.6,
            "avg_resolution_time_hours": 28.5,
            "current_coverage": 72.3,
            "current_defect_escape": 8.5,
        },
        "charts": {
            "kpi_trend": kpi_trend,
            "closure_trend": closure_trend,
        }
    }


# ── Loop 4: KG 自进化 ────────────────────────────────────────────────

def get_loop4_data() -> dict:
    """返回 KG 置信度分布数据。"""
    # 置信度分布 (直方图桶)
    confidence_buckets = [
        {"range": "0.0-0.2", "count": 3, "pct": 1.5},
        {"range": "0.2-0.4", "count": 12, "pct": 6.0},
        {"range": "0.4-0.6", "count": 45, "pct": 22.5},
        {"range": "0.6-0.8", "count": 78, "pct": 39.0},
        {"range": "0.8-1.0", "count": 62, "pct": 31.0},
    ]

    # 低分条目 (置信度 < 0.3)
    low_confidence_items = [
        {"id": "KG-EDGE-0142", "entity": "BrakeController → REQ-BRAKE-0042",
         "type": "edge", "confidence": 0.21, "reason": "测试结果与预测不符",
         "predicted": "passed", "actual": "failed",
         "last_updated": _hours_ago(12), "needs_review": True},
        {"id": "KG-NODE-0089", "entity": "CanIf",
         "type": "node", "confidence": 0.18, "reason": "知识来源可信度低",
         "source": "auto-extracted",
         "last_updated": _hours_ago(24), "needs_review": True},
        {"id": "KG-EDGE-0091", "entity": "SeatController → REQ-SEAT-0012",
         "type": "edge", "confidence": 0.25, "reason": "E2E 保护边界条件不明确",
         "predicted": "compliant", "actual": "non-compliant",
         "last_updated": _hours_ago(36), "needs_review": True},
        {"id": "KG-NODE-0123", "entity": "DCM_NoResponse_SWC",
         "type": "node", "confidence": 0.29, "reason": "单元测试覆盖率不足",
         "source": "code_scanner",
         "last_updated": _hours_ago(48), "needs_review": True},
        {"id": "KG-EDGE-0078", "entity": "CanIf → REQ-COMM-0018",
         "type": "edge", "confidence": 0.12, "reason": "多次预测失败",
         "predicted": "passed", "actual": "failed",
         "last_updated": _hours_ago(6), "needs_review": True},
    ]

    # 置信度趋势 (14日)
    confidence_trend = [
        {"date": "07-14", "avg_confidence": 0.62, "total_entries": 185, "low_confidence": 8},
        {"date": "07-15", "avg_confidence": 0.63, "total_entries": 187, "low_confidence": 7},
        {"date": "07-16", "avg_confidence": 0.61, "total_entries": 189, "low_confidence": 9},
        {"date": "07-17", "avg_confidence": 0.60, "total_entries": 192, "low_confidence": 10},
        {"date": "07-18", "avg_confidence": 0.59, "total_entries": 194, "low_confidence": 12},
        {"date": "07-19", "avg_confidence": 0.58, "total_entries": 195, "low_confidence": 13},
        {"date": "07-20", "avg_confidence": 0.56, "total_entries": 197, "low_confidence": 15},
        {"date": "07-21", "avg_confidence": 0.55, "total_entries": 198, "low_confidence": 16},
        {"date": "07-22", "avg_confidence": 0.54, "total_entries": 200, "low_confidence": 17},
        {"date": "07-23", "avg_confidence": 0.53, "total_entries": 200, "low_confidence": 18},
        {"date": "07-24", "avg_confidence": 0.53, "total_entries": 200, "low_confidence": 18},
        {"date": "07-25", "avg_confidence": 0.54, "total_entries": 200, "low_confidence": 17},
        {"date": "07-26", "avg_confidence": 0.55, "total_entries": 200, "low_confidence": 16},
        {"date": "07-27", "avg_confidence": 0.56, "total_entries": 200, "low_confidence": 15},
    ]

    return {
        "ok": True,
        "loop_id": 4,
        "label": "KG 自进化",
        "emoji": "🟣",
        "last_updated": _now_iso(),
        "confidence_buckets": confidence_buckets,
        "low_confidence_items": low_confidence_items,
        "metrics": {
            "total_kg_entries": 200,
            "avg_confidence": 0.56,
            "low_confidence_count": 15,
            "high_confidence_count": 62,
            "needs_review_count": 5,
            "re_review_tickets_created": 8,
            "confidence_trend_7d": -0.06,
        },
        "charts": {
            "confidence_trend": confidence_trend,
        }
    }


# ── Dispatcher ────────────────────────────────────────────────────────

LOOP_FUNCS = {
    1: get_loop1_data,
    2: get_loop2_data,
    3: get_loop3_data,
    4: get_loop4_data,
}


def get_loop_data(loop_id: int) -> dict:
    """获取指定 Loop 的数据。"""
    func = LOOP_FUNCS.get(loop_id)
    if func is None:
        return {"ok": False, "error": f"Loop {loop_id} not found"}
    try:
        return func()
    except Exception as e:
        log.error("get_loop_data(%d): %s", loop_id, e)
        return {"ok": False, "error": str(e)}


def get_all_loops_data() -> dict:
    """获取所有 Loop 的摘要数据。"""
    return {
        "ok": True,
        "loop_1": {
            "label": "缺陷→需求回溯", "emoji": "🔵",
            "total_events_24h": 3, "spec_deltas": 3, "traceability_rate": 92.5,
        },
        "loop_2": {
            "label": "现场→FMEA", "emoji": "🟢",
            "field_defects_30d": 12, "active_fmeas": 3, "safety_alerts": 2,
        },
        "loop_3": {
            "label": "KPI→RCA→改进", "emoji": "🟡",
            "active_rca": 3, "open_tickets": 1, "closure_rate": 55.6,
        },
        "loop_4": {
            "label": "KG 自进化", "emoji": "🟣",
            "total_entries": 200, "avg_confidence": 0.56, "needs_review": 5,
        },
    }
