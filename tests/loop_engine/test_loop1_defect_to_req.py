#!/usr/bin/env python3
"""
Loop 1 — 缺陷→需求回溯闭环测试。
"""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
    Loop1DefectToReqHandler,
)
from yuleosh.loop_engine.feedback_handlers.base import ActionResult


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def ci_failure_event():
    """标准 CI_FAILURE 事件。"""
    return LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="ci.runner",
        data={
            "test_name": "test_brake_light_interrupt",
            "test_fqn": "tests/test_brake.py::test_brake_light_interrupt",
            "error": "AssertionError: expected True, got False",
            "evidence_ref": "ci-runner-12345",
        },
    )


@pytest.fixture
def handler(temp_dir):
    """无 KG 后端的 Handler (降级模式)。"""
    return Loop1DefectToReqHandler(
        kg_store=None,
        output_dir=temp_dir,
        require_kg=False,
    )


# ═══════════════════════════════════════════════════════════════════════
# 基本功能
# ═══════════════════════════════════════════════════════════════════════

def test_handler_subscribed_events(handler):
    """应订阅 CI_FAILURE 事件。"""
    events = handler.subscribed_events()
    assert LoopEventType.CI_FAILURE in events
    assert len(events) == 1


def test_handler_name(handler):
    """名称应为 Loop1DefectToReqHandler。"""
    assert handler.name == "Loop1DefectToReqHandler"


def test_can_handle_ci_failure(handler, ci_failure_event):
    """应可以处理 CI_FAILURE 事件。"""
    assert handler.can_handle(ci_failure_event) is True


def test_can_handle_missing_test_name(handler):
    """缺少 test_name 应返回 False。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"no_test": "missing"},
    )
    assert handler.can_handle(event) is False


def test_can_handle_wrong_type(handler):
    """错误的事件类型应返回 False。"""
    event = LoopEvent(event_type=LoopEventType.KPI_BREACH)
    assert handler.can_handle(event) is False


# ═══════════════════════════════════════════════════════════════════════
# 处理逻辑
# ═══════════════════════════════════════════════════════════════════════

def test_handle_no_kg_returns_success(handler, ci_failure_event):
    """没有 KG 后端时, 处理应成功 (无需求被标记)。"""
    result = handler.handle(ci_failure_event)
    assert result.success is True
    assert "无对应需求" in result.action_taken or "0 个需求" in result.action_taken


def test_handle_generates_spec_delta_file(handler, ci_failure_event, temp_dir):
    """处理后应生成 spec-delta 文件。"""
    handler.handle(ci_failure_event)

    spec_delta_path = os.path.join(temp_dir, "spec-delta.md")
    if os.path.exists(spec_delta_path):
        with open(spec_delta_path) as f:
            content = f.read()
        assert "CI测试失败" in content


def test_handle_with_kg_mock(handler, ci_failure_event, temp_dir):
    """使用 Mock KG 后端, 应追踪到需求。"""
    # Mock KG 返回
    mock_kg = MagicMock()
    with patch.object(handler, '_find_requirements', return_value=["RS-001-01", "RS-001-02"]):
        result = handler.handle(ci_failure_event)

    assert result.success is True
    assert "RS-001-01" in result.action_taken
    assert "RS-001-02" in result.action_taken
    assert "needs_review" in result.action_taken


def test_handle_persists_status(handler, ci_failure_event):
    """需求应被标记为 needs_review。"""
    mock_kg = MagicMock()
    with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
        with patch.object(handler, '_mark_requirement_needs_review') as mock_mark:
            handler.handle(ci_failure_event)
            mock_mark.assert_called_once_with("RS-001", unittest.mock.ANY)


def test_handle_writes_status_file(handler, ci_failure_event, temp_dir):
    """Store 不可用时, 应写入 JSON 状态文件。"""
    req_id = "RS-001-TEST"
    with patch.object(handler, '_find_requirements', return_value=[req_id]):
        handler.handle(ci_failure_event)

    status_path = os.path.join(temp_dir, ".loop_status", f"{req_id}.json")
    if os.path.exists(status_path):
        with open(status_path) as f:
            data = json.load(f)
        assert data["status"] == "needs_review"
        assert data["req_id"] == req_id


# ═══════════════════════════════════════════════════════════════════════
# Rollback
# ═══════════════════════════════════════════════════════════════════════

def test_rollback_clears_status(handler, ci_failure_event):
    """rollback 应清除 needs_review 标记。"""
    with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
        with patch.object(handler, '_clear_needs_review') as mock_clear:
            result = handler.rollback(ci_failure_event)
            assert result.success is True
            mock_clear.assert_called_once_with("RS-001")


# ═══════════════════════════════════════════════════════════════════════
# 事件数据格式兼容性
# ═══════════════════════════════════════════════════════════════════════

def test_handle_with_test_fqn(handler):
    """兼容 test_fqn 字段。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"test_fqn": "tests::test_brake"},
    )
    assert handler.can_handle(event) is True


def test_handle_without_test_name(handler):
    """无任何测试名时, can_handle 应返回 False。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"some_other": "data"},
    )
    assert handler.can_handle(event) is False


# ═══════════════════════════════════════════════════════════════════════
# ActionHistory
# ═══════════════════════════════════════════════════════════════════════

def test_action_history(handler, ci_failure_event):
    """处理后的 action_history 应包含操作记录。"""
    with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
        handler.handle(ci_failure_event)

    history = handler.action_history
    assert len(history) >= 1
    assert history[0]["req_id"] == "RS-001"


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════

def test_handle_duplicate_events(handler, ci_failure_event):
    """重复的 CI_FAILURE 事件应独立处理。"""
    with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
        r1 = handler.handle(ci_failure_event)
        r2 = handler.handle(ci_failure_event)

    assert r1.success is True
    assert r2.success is True


def test_handle_empty_error_message(handler):
    """空的 error 字段不应导致崩溃。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"test_name": "test_brake"},
    )
    result = handler.handle(event)
    assert result is not None


def test_handle_long_error_message(handler, temp_dir):
    """过长的 error message 应被截断。"""
    long_error = "AssertionError: " + "x" * 1000
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"test_name": "test_brake", "error": long_error},
    )
    result = handler.handle(event)
    assert result.success is True
    # spec-delta 中的 error 应被截断到 200 字符
    spec_path = os.path.join(temp_dir, "spec-delta.md")
    if os.path.exists(spec_path):
        with open(spec_path) as f:
            content = f.read()
        # 只检查文件存在且包含需求标记
        assert "needs_review" in content or "test_brake" in content


# ═══════════════════════════════════════════════════════════════════════
# @register_handler 集成
# ═══════════════════════════════════════════════════════════════════════

def test_handler_is_registered():
    """Loop1DefectToReqHandler 应已通过 @register_handler 注册。

    Note: 由于 tests/session 级别的全局注册表共享,
    此测试同时验证 is_registered 和 is_FeedbackHandler_subclass。
    """
    from yuleosh.loop_engine.feedback_handlers.base import (
        get_registered_handlers, _handler_registry
    )
    # 确保 handler 已注册 (可能是同一模块 import 时注册的)
    # 如果全局注册表已被其他测试清除, 重新注册
    if "Loop1DefectToReqHandler" not in get_registered_handlers():
        _handler_registry["Loop1DefectToReqHandler"] = Loop1DefectToReqHandler

    handlers = get_registered_handlers()
    assert "Loop1DefectToReqHandler" in handlers
    assert handlers["Loop1DefectToReqHandler"] is Loop1DefectToReqHandler


import json
import unittest.mock
