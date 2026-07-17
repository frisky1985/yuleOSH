#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 3 — KPI→RCA→改进闭环 测试 (20+ 测试用例)。

Covers:
  - KPI_BREACH 事件处理
  - RCA 分析链路
  - 改进工单生成
  - insufficient_data 处理
  - no_breach 跳过
  - 配置热重载
  - rollback
  - KPI 趋势记录
  - 事件历史
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.loop3_kpi_to_improve import (
    Loop3KPIToImproveHandler,
)
from yuleosh.loop_engine.rca_engine import RCAEngine, RCAReport


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def handler():
    """创建一个干净的 Loop3 handler。"""
    h = Loop3KPIToImproveHandler(output_dir=".")
    return h


@pytest.fixture
def kpi_breach_event():
    """标准 KPI_BREACH 事件 (coverage 下降)。"""
    return LoopEvent(
        event_type=LoopEventType.KPI_BREACH,
        source="ci.kpi_monitor",
        data={
            "metric": "coverage_percent",
            "value": 45.0,
            "threshold": 60.0,
            "data_points_count": 10,
        },
    )


@pytest.fixture
def kpi_no_breach_event():
    """KPI 未超阈值事件。"""
    return LoopEvent(
        event_type=LoopEventType.KPI_BREACH,
        source="ci.kpi_monitor",
        data={
            "metric": "coverage_percent",
            "value": 75.0,
            "threshold": 60.0,
            "data_points_count": 10,
        },
    )


@pytest.fixture
def kpi_insufficient_data_event():
    """数据点不足的 KPI 事件。"""
    return LoopEvent(
        event_type=LoopEventType.KPI_BREACH,
        source="ci.kpi_monitor",
        data={
            "metric": "coverage_percent",
            "value": 45.0,
            "threshold": 60.0,
            "data_points_count": 1,
        },
    )


@pytest.fixture
def temp_handler(tmp_path):
    """使用临时目录的 handler。"""
    return Loop3KPIToImproveHandler(output_dir=str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLoop3HandlerBasic:
    """Loop 3 基础功能测试。"""

    # ── 订阅事件 ──────────────────────────────────────────────────────

    def test_subscribed_events(self, handler):
        """只订阅 KPI_BREACH。"""
        events = handler.subscribed_events()
        assert LoopEventType.KPI_BREACH in events
        assert len(events) == 1

    def test_can_handle_kpi_breach(self, handler, kpi_breach_event):
        """KPI_BREACH 且包含 metric 可通过过滤。"""
        assert handler.can_handle(kpi_breach_event)

    def test_can_handle_reject_other_events(self, handler):
        """非 KPI_BREACH 事件被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            data={"test_name": "test_foo"},
        )
        assert not handler.can_handle(event)

    def test_can_handle_missing_metric(self, handler):
        """缺少 metric 的 KPI_BREACH 被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"value": 100},
        )
        assert not handler.can_handle(event)

    # ── 处理 KPI_BREACH ───────────────────────────────────────────────

    def test_handle_breach_generates_rca(self, handler, kpi_breach_event):
        """KPI 超阈值触发 RCA 分析。"""
        result = handler.handle(kpi_breach_event)
        assert result.success
        assert "RCA" in result.action_taken or "工单" in result.action_taken

    def test_handle_breach_creates_ticket(self, temp_handler, kpi_breach_event):
        """KPI 超阈值创建改进工单文件。"""
        result = temp_handler.handle(kpi_breach_event)
        assert result.success
        assert result.evidence_ref is not None
        assert "yaml" in result.evidence_ref.lower() or "improvement_tickets" in result.evidence_ref

    def test_handle_no_breach_skips(self, handler, kpi_no_breach_event):
        """KPI 未超阈值时不执行 RCA。"""
        result = handler.handle(kpi_no_breach_event)
        assert result.success
        assert "未超过阈值" in result.action_taken

    def test_handle_insufficient_data_skips(self, handler, kpi_insufficient_data_event):
        """数据点不足时不执行 RCA。"""
        result = handler.handle(kpi_insufficient_data_event)
        assert not result.success
        assert "数据点不足" in result.action_taken

    # ── 多种指标 ──────────────────────────────────────────────────────

    def test_misra_violations_breach(self, handler):
        """MISRA 违规数上升触发 RCA。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            source="ci.kpi_monitor",
            data={"metric": "misra_violations", "value": 150, "threshold": 100, "data_points_count": 5},
        )
        result = handler.handle(event)
        assert result.success

    def test_defect_escape_rate_breach(self, handler):
        """缺陷逃逸率上升触发 RCA。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "defect_escape_rate", "value": 8.0, "threshold": 5.0, "data_points_count": 5},
        )
        result = handler.handle(event)
        assert result.success

    def test_build_failure_rate_breach(self, handler):
        """构建失败率上升触发 RCA。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "build_failure_rate", "value": 20.0, "threshold": 10.0, "data_points_count": 5},
        )
        result = handler.handle(event)
        assert result.success

    # ── KPI 趋势 ──────────────────────────────────────────────────────

    def test_kpi_trend_recorded(self, handler, kpi_breach_event):
        """KPI 值被记录到趋势中。"""
        handler.handle(kpi_breach_event)
        trend = handler.get_kpi_trend("coverage_percent")
        assert len(trend) == 1
        assert trend[0] == 45.0

    def test_kpi_trend_multiple_events(self, handler):
        """多次记录时趋势增长。"""
        for i in range(3):
            event = LoopEvent(
                event_type=LoopEventType.KPI_BREACH,
                data={"metric": "misra_violations", "value": float(100 + i * 10),
                      "threshold": 100.0, "data_points_count": 5},
            )
            handler.handle(event)

        trend = handler.get_kpi_trend("misra_violations")
        assert len(trend) == 3

    # ── Rollback ──────────────────────────────────────────────────────

    def test_rollback_removes_trend(self, handler, kpi_breach_event):
        """回滚移除最近的趋势记录。"""
        handler.handle(kpi_breach_event)
        assert len(handler.get_kpi_trend("coverage_percent")) == 1

        result = handler.rollback(kpi_breach_event)
        assert result.success
        assert len(handler.get_kpi_trend("coverage_percent")) == 0

    def test_rollback_empty(self, handler):
        """没有记录时回滚仍返回 success。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "unknown_metric"},
        )
        result = handler.rollback(event)
        assert result.success

    # ── 配置热重载 ─────────────────────────────────────────────────────

    def test_apply_threshold_config(self, handler):
        """自定义阈值配置立即生效。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "misra_violations", "value": 80, "data_points_count": 5},
        )
        # 默认阈值 100, 80 < 100 不超
        result_before = handler.handle(event)
        assert "未超过阈值" in result_before.action_taken

        # 更改阈值到 50, 80 > 50 超
        handler.apply_config({"thresholds": {"misra_violations": 50}})
        result_after = handler.handle(event)
        assert result_after.success
        assert "RCA" in result_after.action_taken or "工单" in result_after.action_taken

    def test_apply_min_data_points(self, handler):
        """最小数据点数配置生效。

        handler 的 min_data_points=1 通过检查, 但 RCA 引擎内部需要 ≥ 3。
        这里使用 3 个数据点来绕过 RCA 引擎的检查。
        """
        handler.apply_config({"min_data_points": 3})
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "coverage_percent", "value": 45, "threshold": 60, "data_points_count": 3},
        )
        result = handler.handle(event)
        assert result.success

    # ── 事件历史 ──────────────────────────────────────────────────────

    def test_event_history_recorded(self, handler):
        """事件历史被记录。"""
        handler.handle(LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "coverage_percent", "value": 40, "threshold": 60, "data_points_count": 5},
        ))
        assert len(handler.event_history) == 1
        assert handler.event_history[0]["metric"] == "coverage_percent"

    # ── 工单列表 ──────────────────────────────────────────────────────

    def test_tickets_created_tracked(self, temp_handler, kpi_breach_event):
        """创建的工单 ID 被跟踪。"""
        temp_handler.handle(kpi_breach_event)
        assert len(temp_handler.tickets_created) == 1
        assert temp_handler.tickets_created[0].startswith("IMP-")

    # ── KPI 趋势持久化 ───────────────────────────────────────────────────

    def test_kpi_trend_persisted(self, temp_handler, kpi_breach_event):
        """KPI 趋势被持久化到文件。"""
        temp_handler.handle(kpi_breach_event)
        trend_dir = os.path.join(str(temp_handler.output_dir), "kpi_trends")
        trend_file = os.path.join(trend_dir, "coverage_percent_trend.json")
        assert os.path.exists(trend_file)

        with open(trend_file) as f:
            data = json.load(f)
        assert data["metric"] == "coverage_percent"
        assert 45.0 in data["values"]

    def test_multiple_metrics_trends(self, temp_handler):
        """多个指标各自维护独立趋势。"""
        metrics_thresholds = [
            ("coverage_percent", 45.0, 60.0),   # coverage: 45 < 60 → breach
            ("misra_violations", 150.0, 100.0),  # misra: 150 > 100 → breach
        ]
        for metric, value, threshold in metrics_thresholds:
            event = LoopEvent(
                event_type=LoopEventType.KPI_BREACH,
                data={"metric": metric, "value": value, "threshold": threshold,
                      "data_points_count": 5},
            )
            temp_handler.handle(event)

        for metric, _, _ in metrics_thresholds:
            trend_file = os.path.join(str(temp_handler.output_dir), "kpi_trends", f"{metric}_trend.json")
            assert os.path.exists(trend_file), f"Trend file for {metric} not found"
            with open(trend_file) as f:
                data = json.load(f)
            assert len(data["values"]) >= 1

    # ── details 完整度 ─────────────────────────────────────────────────

    def test_handle_details_completeness(self, handler, kpi_breach_event):
        """处理结果的 details 包含必要字段。"""
        result = handler.handle(kpi_breach_event)
        assert "metric" in result.details
        assert "severity" in result.details
        assert "priority" in result.details
        assert "root_cause" in result.details

    def test_details_without_breach(self, handler, kpi_no_breach_event):
        """未超阈值时 details 包含 reason。"""
        result = handler.handle(kpi_no_breach_event)
        assert "reason" in result.details

    # ── 边缘情况 ──────────────────────────────────────────────────────

    def test_unknown_metric(self, handler):
        """未知指标仍能正常处理。"""
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            data={"metric": "unknown_metric", "value": 999, "threshold": 100, "data_points_count": 5},
        )
        result = handler.handle(event)
        assert result.success
