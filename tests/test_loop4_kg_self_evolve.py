#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 4 — KG 置信度自进化 测试 (15+ 测试用例)。

Covers:
  - TEST_RESULT / REVIEW_FINDING 事件处理
  - 正确预测 → 置信度提升
  - 错误预测 → 置信度降低
  - 置信度上限 0.95
  - 置信度下限 0.1
  - 置信度 < 0.3 → re-review ticket
  - KPI 趋势记录
  - Rollback
  - 持久化
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.loop4_kg_self_evolve import (
    Loop4KGSelfEvolveHandler,
    CONFIDENCE_INCREASE,
    CONFIDENCE_DECREASE,
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    REVIEW_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def handler():
    """创建一个干净的 Loop4 handler。"""
    return Loop4KGSelfEvolveHandler(output_dir=".")


@pytest.fixture
def correct_test_event():
    """正确的预测事件。"""
    return LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        source="kg.verifier",
        data={
            "entity_id": "E-001",
            "edge_id": "E-001",
            "prediction_result": "correct",
            "predicted_value": "valid",
            "actual_value": "valid",
        },
    )


@pytest.fixture
def incorrect_test_event():
    """错误的预测事件。"""
    return LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        source="kg.verifier",
        data={
            "entity_id": "E-002",
            "edge_id": "E-002",
            "prediction_result": "incorrect",
            "predicted_value": "valid",
            "actual_value": "invalid",
        },
    )


@pytest.fixture
def temp_handler(tmp_path):
    """使用临时目录的 handler。"""
    return Loop4KGSelfEvolveHandler(output_dir=str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLoop4HandlerBasic:
    """Loop 4 基础功能测试。"""

    # ── 订阅事件 ──────────────────────────────────────────────────────

    def test_subscribed_events(self, handler):
        """订阅 TEST_RESULT 和 REVIEW_FINDING。"""
        events = handler.subscribed_events()
        assert LoopEventType.TEST_RESULT in events
        assert LoopEventType.REVIEW_FINDING in events
        assert len(events) == 2

    def test_can_handle_with_entity_id(self, handler, correct_test_event):
        """包含 entity_id 和 prediction_result 的 TestResult 可通过。"""
        assert handler.can_handle(correct_test_event)

    def test_can_handle_review_finding(self, handler):
        """REVIEW_FINDING 事件可通过。"""
        event = LoopEvent(
            event_type=LoopEventType.REVIEW_FINDING,
            data={"entity_id": "R-001", "prediction_result": "correct"},
        )
        assert handler.can_handle(event)

    def test_can_handle_missing_entity(self, handler):
        """缺少 entity_id 被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"prediction_result": "correct"},
        )
        assert not handler.can_handle(event)

    def test_can_handle_missing_prediction(self, handler):
        """缺少 prediction_result 被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"entity_id": "E-001"},
        )
        assert not handler.can_handle(event)

    # ── 置信度: 正确预测 ──────────────────────────────────────────────

    def test_correct_prediction_increases_confidence(self, handler, correct_test_event):
        """正确预测置信度提升。"""
        handler.inject_entity("E-001", "E-001", 0.5)
        result = handler.handle(correct_test_event)
        assert result.success
        assert result.details["new_confidence"] > 0.5
        assert result.details["adjustment"] == "increased"

    def test_correct_prediction_delta(self, handler, correct_test_event):
        """正确预测置信度增加值正确。"""
        handler.inject_entity("E-001", "E-001", 0.5)
        result = handler.handle(correct_test_event)
        delta = result.details["new_confidence"] - result.details["old_confidence"]
        assert abs(delta - CONFIDENCE_INCREASE) < 0.01

    # ── 置信度: 错误预测 ──────────────────────────────────────────────

    def test_incorrect_prediction_decreases_confidence(self, handler, incorrect_test_event):
        """错误预测置信度降低。"""
        handler.inject_entity("E-002", "E-002", 0.8)
        result = handler.handle(incorrect_test_event)
        assert result.success
        assert result.details["new_confidence"] < 0.8
        assert result.details["adjustment"] == "decreased"

    def test_incorrect_prediction_delta(self, handler, incorrect_test_event):
        """错误预测置信度降低值正确。"""
        handler.inject_entity("E-002", "E-002", 0.8)
        result = handler.handle(incorrect_test_event)
        delta = result.details["old_confidence"] - result.details["new_confidence"]
        assert abs(delta - CONFIDENCE_DECREASE) < 0.01

    # ── 置信度上限 ────────────────────────────────────────────────────

    def test_confidence_cap_at_max(self, handler):
        """置信度不超过上限 0.95。"""
        handler.inject_entity("E-CAP", "E-CAP", 0.94)
        for _ in range(3):  # 多次正确预测
            event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,
                data={"entity_id": "E-CAP", "edge_id": "E-CAP", "prediction_result": "correct"},
            )
            handler.handle(event)

        conf = handler.get_confidence("E-CAP", "E-CAP")
        assert conf <= CONFIDENCE_MAX
        assert conf == pytest.approx(CONFIDENCE_MAX, abs=0.02)

    # ── 置信度下限 ────────────────────────────────────────────────────

    def test_confidence_floor_at_min(self, handler):
        """置信度不低于下限 0.1。"""
        handler.inject_entity("E-FLOOR", "E-FLOOR", 0.15)
        for _ in range(5):  # 多次错误预测
            event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,
                data={"entity_id": "E-FLOOR", "edge_id": "E-FLOOR", "prediction_result": "incorrect"},
            )
            handler.handle(event)

        conf = handler.get_confidence("E-FLOOR", "E-FLOOR")
        assert conf >= CONFIDENCE_MIN
        assert conf == pytest.approx(CONFIDENCE_MIN, abs=0.02)

    # ── Re-review Ticket ────────────────────────────────────────────────

    def test_low_confidence_triggers_review_ticket(self, temp_handler):
        """置信度 < 0.3 时创建 re-review ticket。"""
        temp_handler.inject_entity("E-LOW", "E-LOW", 0.4)
        # 两次错误预测, 0.4 - 0.15 - 0.15 = 0.1 < 0.3
        for _ in range(2):
            event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,
                data={"entity_id": "E-LOW", "edge_id": "E-LOW", "prediction_result": "incorrect"},
            )
            result = temp_handler.handle(event)

        assert len(temp_handler.review_tickets_created) >= 1

    def test_review_ticket_has_content(self, temp_handler):
        """Re-review ticket 包含必要字段。"""
        temp_handler.inject_entity("E-TKT", "E-TKT", 0.4)
        for _ in range(2):
            event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,
                data={"entity_id": "E-TKT", "edge_id": "E-TKT",
                      "prediction_result": "incorrect"},
            )
            temp_handler.handle(event)

        tickets = temp_handler.review_tickets_created
        assert len(tickets) >= 1

        # 检查 ticket 文件
        tickets_dir = os.path.join(str(temp_handler.output_dir), "rereview_tickets")
        import glob
        ticket_files = glob.glob(os.path.join(tickets_dir, f"{tickets[0]}*"))
        assert len(ticket_files) >= 1

        with open(ticket_files[0]) as f:
            ticket = json.load(f)
        assert ticket["type"] == "kg_confidence_review"
        assert "entity_id" in ticket
        assert "recommended_action" in ticket
        assert ticket["priority"] == "P2"

    # ── 置信度上限不触发 review ────────────────────────────────────────

    def test_high_confidence_no_review(self, handler):
        """高置信度不触发 review。"""
        handler.inject_entity("E-HIGH", "E-HIGH", 0.9)
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"entity_id": "E-HIGH", "edge_id": "E-HIGH", "prediction_result": "correct"},
        )
        result = handler.handle(event)
        assert len(handler.review_tickets_created) == 0
        assert result.details["below_review_threshold"] is False

    # ── KPI 趋势 ──────────────────────────────────────────────────────

    def test_kpi_snapshot_recorded(self, handler, correct_test_event):
        """KPI 快照被记录。"""
        handler.handle(correct_test_event)
        assert len(handler.kpi_snapshots) >= 1

    def test_kpi_snapshot_file_written(self, temp_handler, correct_test_event):
        """KPI 快照被写入文件。"""
        temp_handler.handle(correct_test_event)
        snapshots_dir = os.path.join(str(temp_handler.output_dir), "kg_confidence_trend")
        snapshot_file = os.path.join(snapshots_dir, "confidence_snapshots.jsonl")
        assert os.path.exists(snapshot_file)

        with open(snapshot_file) as f:
            line = f.readline().strip()
        snapshot = json.loads(line)
        assert "entity_id" in snapshot
        assert "confidence" in snapshot

    # ── Rollback ──────────────────────────────────────────────────────

    def test_rollback_restores_confidence(self, handler, correct_test_event):
        """回滚恢复前一个置信度。"""
        handler.inject_entity("E-RB", "E-RB", 0.5)
        result_before = handler.handle(correct_test_event)
        new_conf = result_before.details["new_confidence"]

        result = handler.rollback(correct_test_event)
        assert result.success
        restored = handler.get_confidence("E-RB", "E-RB")
        assert restored == pytest.approx(0.5, abs=0.01)

    def test_rollback_no_history(self, handler):
        """没有历史记录时无法回滚。"""
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"entity_id": "E-NO_HISTORY", "prediction_result": "correct"},
        )
        result = handler.rollback(event)
        assert not result.success
        assert "找不到" in result.action_taken

    # ── 置信度变更历史 ────────────────────────────────────────────────

    def test_confidence_history_recorded(self, handler, correct_test_event):
        """置信度变更历史被记录。"""
        handler.handle(correct_test_event)
        assert len(handler.confidence_history) == 1
        record = handler.confidence_history[0]
        assert record["entity_id"] == "E-001"
        assert "old_confidence" in record
        assert "new_confidence" in record
        assert "adjustment" in record

    def test_multiple_events_history(self, handler):
        """多次事件正确累积历史。"""
        for i in range(3):
            event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,
                data={"entity_id": f"E-{i:03d}", "edge_id": f"E-{i:03d}",
                      "prediction_result": "correct"},
            )
            handler.handle(event)

        assert len(handler.confidence_history) == 3

    # ── REVIEW_FINDING 事件 ───────────────────────────────────────────

    def test_review_finding_event(self, handler):
        """REVIEW_FINDING 事件正确调整置信度。"""
        handler.inject_entity("R-001", "R-001", 0.5)
        event = LoopEvent(
            event_type=LoopEventType.REVIEW_FINDING,
            data={"entity_id": "R-001", "edge_id": "R-001", "prediction_result": "correct"},
        )
        result = handler.handle(event)
        assert result.success
        assert result.details["adjustment"] == "increased"

    # ── 被正确事件暴露 ────────────────────────────────────────────────

    def test_default_confidence_is_0_5(self, handler):
        """未设置的实体默认置信度为 0.5。"""
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"entity_id": "E-NEW", "edge_id": "E-NEW", "prediction_result": "correct"},
        )
        result = handler.handle(event)
        assert result.details["old_confidence"] == 0.5

    # ── details 完整度 ─────────────────────────────────────────────────

    def test_handle_details_completeness(self, handler, correct_test_event):
        """处理结果的 details 包含必要字段。"""
        result = handler.handle(correct_test_event)
        assert "entity_id" in result.details
        assert "old_confidence" in result.details
        assert "new_confidence" in result.details
        assert "adjustment" in result.details
        assert "delta" in result.details
        assert "below_review_threshold" in result.details

    # ── 边缘情况下不需要 review ──────────────────────────────────────────

    def test_confidence_above_review_no_ticket(self, handler):
        """置信度高于 0.3 时不需要 ticket。"""
        handler.inject_entity("E-SAFE", "E-SAFE", 0.5)
        event = LoopEvent(
            event_type=LoopEventType.TEST_RESULT,
            data={"entity_id": "E-SAFE", "edge_id": "E-SAFE", "prediction_result": "incorrect"},
        )
        result = handler.handle(event)
        assert result.success
        assert result.details["below_review_threshold"] is False
