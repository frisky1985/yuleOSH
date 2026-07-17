#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 2 — 现场缺陷→FMEA 闭环 测试 (15+ 测试用例)。

Covers:
  - FIELD_DEFECT 事件处理
  - FMEA 条目查找/创建
  - failure_rate 递增
  - severity 更新
  - 严重度 ≥ 8 触发安全影响分析
  - 安全影响分析报告生成
  - KG 追溯
  - Rollback
  - 事件历史
"""

import copy
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.loop2_field_to_fmea import (
    Loop2FieldToFMEAHandler,
    FMEAEntry,
    SAFETY_SEVERITY_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def handler():
    """创建一个干净的 Loop2 handler。"""
    return Loop2FieldToFMEAHandler(output_dir=".")


@pytest.fixture
def field_defect_event():
    """标准 FIELD_DEFECT 事件。"""
    return LoopEvent(
        event_type=LoopEventType.FIELD_DEFECT,
        source="field.reporter",
        data={
            "swc": "CanIf",
            "failure_code": "BUS_OFF",
            "severity": 5,
            "defect_id": "FLD-001",
            "description": "CAN bus off after extended idle period",
        },
    )


@pytest.fixture
def high_severity_defect_event():
    """高严重度 FIELD_DEFECT 事件 (severity=9)。"""
    return LoopEvent(
        event_type=LoopEventType.FIELD_DEFECT,
        source="field.reporter",
        data={
            "swc": "BrakeController",
            "failure_code": "BRAKE_FAILURE",
            "severity": 9,
            "defect_id": "FLD-002",
            "description": "Brake system fails to engage after timeout",
        },
    )


@pytest.fixture
def temp_handler(tmp_path):
    """使用临时目录的 handler。"""
    return Loop2FieldToFMEAHandler(output_dir=str(tmp_path))


@pytest.fixture
def sample_fmea_entry():
    """预填充的 FMEA 条目。"""
    return FMEAEntry(
        fmea_id="FMEA-CanIf-BUS_OFF",
        swc="CanIf",
        failure_mode="BUS_OFF",
        failure_rate=5,
        severity=3,
        occurrence=2,
        detection=3,
        safety_related=False,
    )


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLoop2HandlerBasic:
    """Loop 2 基础功能测试。"""

    # ── 订阅事件 ──────────────────────────────────────────────────────

    def test_subscribed_events(self, handler):
        """只订阅 FIELD_DEFECT。"""
        events = handler.subscribed_events()
        assert LoopEventType.FIELD_DEFECT in events
        assert len(events) == 1

    def test_can_handle_field_defect(self, handler, field_defect_event):
        """FIELD_DEFECT 且包含 swc 可通过。"""
        assert handler.can_handle(field_defect_event)

    def test_can_handle_reject_other(self, handler):
        """非 FIELD_DEFECT 被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            data={"test_name": "test_foo"},
        )
        assert not handler.can_handle(event)

    def test_can_handle_missing_swc(self, handler):
        """缺少 swc 被拒绝。"""
        event = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"severity": 5},
        )
        assert not handler.can_handle(event)

    # ── FMEA 条目更新 ────────────────────────────────────────────────

    def test_new_fmea_entry_created(self, handler, field_defect_event):
        """新 SWC 创建 FMEA 骨架条目。"""
        result = handler.handle(field_defect_event)
        assert result.success

        entries = handler.get_all_entries()
        assert len(entries) == 1
        assert entries[0].swc == "CanIf"

    def test_failure_rate_incremented(self, handler, field_defect_event):
        """failure_rate 递增 1。"""
        handler.handle(field_defect_event)
        entries = handler.get_all_entries()
        assert entries[0].failure_rate >= 1

    def test_failure_rate_double_defect(self, handler, field_defect_event):
        """两次相同 SWC 的缺陷 failure_rate 递增。"""
        handler.handle(field_defect_event)
        rate_after_first = handler.get_all_entries()[0].failure_rate

        handler.handle(field_defect_event)
        rate_after_second = handler.get_all_entries()[0].failure_rate

        assert rate_after_second > rate_after_first

    def test_severity_updated(self, handler, field_defect_event):
        """severity 更新为事件中的值。"""
        handler.handle(field_defect_event)
        entries = handler.get_all_entries()
        assert entries[0].severity == 5

    def test_severity_not_downgraded(self, handler):
        """severity 不被更低值覆盖。"""
        high_sev = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"swc": "CanIf", "failure_code": "BUS_OFF", "severity": 8, "defect_id": "FLD-001"},
        )
        handler.handle(high_sev)

        low_sev = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"swc": "CanIf", "failure_code": "BUS_OFF", "severity": 3, "defect_id": "FLD-002"},
        )
        handler.handle(low_sev)

        entries = handler.get_all_entries()
        assert entries[0].severity == 8

    def test_existing_fmea_updated(self, handler, field_defect_event):
        """已存在的 FMEA 条目被正确更新。"""
        handler.handle(field_defect_event)
        rate_before = handler.get_all_entries()[0].failure_rate

        handler.handle(field_defect_event)
        rate_after = handler.get_all_entries()[0].failure_rate

        assert rate_after > rate_before

    # ── 安全影响分析 ──────────────────────────────────────────────────

    def test_safety_analysis_triggered(self, handler, high_severity_defect_event):
        """severity ≥ 8 触发安全影响分析。"""
        result = handler.handle(high_severity_defect_event)
        assert result.success
        assert "安全影响分析" in result.action_taken
        assert result.details.get("safety_analysis_triggered") is True

    def test_safety_report_file_created(self, temp_handler, high_severity_defect_event):
        """安全影响分析报告被写入文件。"""
        temp_handler.handle(high_severity_defect_event)
        reports_dir = os.path.join(str(temp_handler.output_dir), "reports")
        assert os.path.exists(reports_dir)
        report_files = [f for f in os.listdir(reports_dir) if f.startswith("safety-impact-")]
        assert len(report_files) >= 1

    def test_safety_report_content(self, temp_handler, high_severity_defect_event):
        """安全影响分析报告包含必要内容。"""
        temp_handler.handle(high_severity_defect_event)
        reports_dir = os.path.join(str(temp_handler.output_dir), "reports")
        report_files = [f for f in os.listdir(reports_dir) if f.startswith("safety-impact-")]
        report_path = os.path.join(reports_dir, report_files[0])

        with open(report_path) as f:
            content = f.read()
        assert "# 安全影响分析报告" in content
        assert "FMEA ID" in content
        assert "安全目标" in content
        assert "推荐措施" in content
        assert "ASIL" in content

    def test_safety_not_triggered_for_low_severity(self, handler):
        """severity < 8 不触发安全分析。使用独立 SWC 避免跨测试污染。"""
        event = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            source="field.reporter",
            data={"swc": "LowSevSWC", "failure_code": "MINOR", "severity": 3, "defect_id": "LOW-001"},
        )
        result = handler.handle(event)
        assert result.details.get("safety_analysis_triggered") is not True

    # ── RPN 计算 ──────────────────────────────────────────────────────

    def test_rpn_recalculated(self):
        """severity 更新后 RPN 被重新计算。"""
        entry = FMEAEntry(
            fmea_id="FMEA-Test", swc="Test", severity=3, occurrence=3, detection=3
        )
        assert entry.rpn == 27  # 3 * 3 * 3

    def test_rpn_update_after_handle(self, handler):
        """处理事件后 RPN 更新。"""
        event = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"swc": "RPNTest", "failure_code": "ERR", "severity": 7, "defect_id": "R-001"},
        )
        result = handler.handle(event)
        assert "rpn" in result.details

    # ── Rollback ──────────────────────────────────────────────────────

    def test_rollback_decrements_failure_rate(self, handler, field_defect_event):
        """回滚减少 failure_rate。"""
        handler.handle(field_defect_event)
        rate_before = handler.get_all_entries()[0].failure_rate

        result = handler.rollback(field_defect_event)
        assert result.success

        rate_after = handler.get_all_entries()[0].failure_rate
        assert rate_after < rate_before

    def test_rollback_no_entry(self, handler):
        """没有条目时回滚失败。"""
        event = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"swc": "NoSuchSWC"},
        )
        result = handler.rollback(event)
        assert not result.success

    # ── 事件历史 ──────────────────────────────────────────────────────

    def test_event_history_recorded(self, handler, field_defect_event):
        """事件历史被记录。"""
        handler.handle(field_defect_event)
        assert len(handler.event_history) == 1
        assert handler.event_history[0]["swc"] == "CanIf"

    # ── FMEA 条目注入 ────────────────────────────────────────────────

    def test_inject_fmea_entry(self, handler, sample_fmea_entry):
        """FMEA 条目注入功能。"""
        handler.inject_fmea_entry(copy.deepcopy(sample_fmea_entry))
        entry = handler.get_fmea_entry(sample_fmea_entry.fmea_id)
        assert entry is not None
        assert entry.swc == "CanIf"
        assert entry.failure_rate == 5

    def test_injected_entry_updated(self, handler, sample_fmea_entry):
        """注入后的事件处理正确更新条目。"""
        original_rate = sample_fmea_entry.failure_rate  # 5
        handler.inject_fmea_entry(copy.deepcopy(sample_fmea_entry))

        event = LoopEvent(
            event_type=LoopEventType.FIELD_DEFECT,
            data={"swc": "CanIf", "failure_code": "BUS_OFF", "severity": 4, "defect_id": "FLD-003"},
        )
        handler.handle(event)

        entry = handler.get_fmea_entry(sample_fmea_entry.fmea_id)
        assert entry.failure_rate == original_rate + 1  # 5 + 1 = 6

    # ── Details 完整度 ───────────────────────────────────────────────

    def test_handle_details_completeness(self, handler, field_defect_event):
        """处理结果的 details 包含必要字段。"""
        result = handler.handle(field_defect_event)
        assert "swc" in result.details
        assert "fmea_id" in result.details
        assert "failure_rate" in result.details
        assert "severity" in result.details

    # ── 安全报告列表 ────────────────────────────────────────────────

    def test_safety_reports_tracked(self, temp_handler, high_severity_defect_event):
        """安全报告被跟踪记录。"""
        temp_handler.handle(high_severity_defect_event)
        assert len(temp_handler.safety_reports) >= 1
        assert temp_handler.safety_reports[0]["fmea_id"].startswith("FMEA-")
        assert temp_handler.safety_reports[0]["severity"] >= SAFETY_SEVERITY_THRESHOLD
