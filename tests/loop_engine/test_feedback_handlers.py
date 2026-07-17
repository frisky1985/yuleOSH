#!/usr/bin/env python3
"""
FeedbackHandler 基类测试。
"""

import pytest
from unittest.mock import Mock, patch

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
    get_registered_handlers,
    clear_registry,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures & Helpers
# ═══════════════════════════════════════════════════════════════════════

class MockHandler(FeedbackHandler):
    """测试用 handler。"""
    def subscribed_events(self):
        return [LoopEventType.CI_FAILURE]

    def handle(self, event):
        return ActionResult(
            success=True,
            action_taken=f"handled {event.event_type.value}",
            handler_name=self.name,
        )


@pytest.fixture
def handler():
    return MockHandler()


@pytest.fixture
def ci_event():
    return LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="test",
        data={"test_name": "test_foo"},
    )


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════

def test_action_result_defaults():
    """ActionResult 默认值。"""
    r = ActionResult()
    assert r.success is True
    assert r.action_taken == ""
    assert r.evidence_ref is None
    assert r.rollback_possible is False
    assert r.details == {}
    assert r.timestamp != ""


def test_action_result_bool():
    """ActionResult 应作为 bool 可用。"""
    assert bool(ActionResult(success=True)) is True
    assert bool(ActionResult(success=False)) is False


def test_action_result_to_dict():
    """ActionResult.to_dict() 应包含所有字段。"""
    r = ActionResult(
        success=True,
        action_taken="mark needs_review",
        evidence_ref="spec-delta.md",
        rollback_possible=True,
        details={"req_id": "RS-001"},
        handler_name="Loop1DefectToReqHandler",
    )
    d = r.to_dict()
    assert d["success"] is True
    assert d["action_taken"] == "mark needs_review"
    assert d["evidence_ref"] == "spec-delta.md"
    assert d["rollback_possible"] is True
    assert d["details"]["req_id"] == "RS-001"
    assert d["handler_name"] == "Loop1DefectToReqHandler"


def test_handler_subscribed_events(handler):
    """handler 应返回其订阅的事件类型。"""
    events = handler.subscribed_events()
    assert LoopEventType.CI_FAILURE in events


def test_handler_handle(handler, ci_event):
    """handler.handle() 应返回 ActionResult。"""
    result = handler.handle(ci_event)
    assert isinstance(result, ActionResult)
    assert result.success is True
    assert "ci.failure" in result.action_taken


def test_handler_can_handle_match(handler, ci_event):
    """可以处理匹配的事件类型。"""
    assert handler.can_handle(ci_event) is True


def test_handler_can_handle_no_match(handler):
    """不应处理不匹配的事件类型。"""
    event = LoopEvent(event_type=LoopEventType.KPI_BREACH)
    assert handler.can_handle(event) is False


def test_handler_name(handler):
    """handler.name 应返回类名。"""
    assert handler.name == "MockHandler"


def test_handler_rollback_default(handler):
    """默认 rollback 应返回不可回滚。"""
    event = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    result = handler.rollback(event)
    assert result.success is False
    assert result.rollback_possible is False


# ═══════════════════════════════════════════════════════════════════════
# @register_handler
# ═══════════════════════════════════════════════════════════════════════

def test_register_handler():
    """@register_handler 应注册 handler。"""
    from yuleosh.loop_engine.feedback_handlers.base import _handler_registry
    saved = dict(_handler_registry)
    clear_registry()

    try:
        @register_handler
        class TestHandler(FeedbackHandler):
            def subscribed_events(self):
                return [LoopEventType.CI_FAILURE]

            def handle(self, event):
                return ActionResult()

        handlers = get_registered_handlers()
        assert "TestHandler" in handlers
        assert handlers["TestHandler"] is TestHandler
    finally:
        _handler_registry.clear()
        _handler_registry.update(saved)


def test_register_handler_non_subclass():
    """@register_handler 应拒绝非 FeedbackHandler 子类。"""
    with pytest.raises(TypeError):
        register_handler(int)  # type: ignore


def test_get_registered_handlers_copy():
    """get_registered_handlers() 应返回副本。"""
    clear_registry()
    assert len(get_registered_handlers()) == 0


def test_clear_registry():
    """clear_registry() 应清空注册表。"""
    from yuleosh.loop_engine.feedback_handlers.base import _handler_registry
    saved = dict(_handler_registry)
    clear_registry()

    try:
        @register_handler
        class TempHandler(FeedbackHandler):
            def subscribed_events(self):
                return [LoopEventType.CI_FAILURE]
            def handle(self, event):
                return ActionResult()

        assert "TempHandler" in get_registered_handlers()
        clear_registry()
        assert "TempHandler" not in get_registered_handlers()
    finally:
        _handler_registry.clear()
        _handler_registry.update(saved)


def test_register_duplicate():
    """重复注册应覆盖。"""
    from yuleosh.loop_engine.feedback_handlers.base import _handler_registry
    saved = dict(_handler_registry)
    clear_registry()

    try:
        @register_handler
        class SameName(FeedbackHandler):
            def subscribed_events(self):
                return [LoopEventType.CI_FAILURE]
            def handle(self, event):
                return ActionResult()

        @register_handler
        class SameName(FeedbackHandler):
            def subscribed_events(self):
                return [LoopEventType.KPI_BREACH]
            def handle(self, event):
                return ActionResult()

        handlers = get_registered_handlers()
        assert handlers["SameName"].subscribed_events(None) == [LoopEventType.KPI_BREACH]
    finally:
        _handler_registry.clear()
        _handler_registry.update(saved)


# ═══════════════════════════════════════════════════════════════════════
# 抽象方法强制实现
# ═══════════════════════════════════════════════════════════════════════

def test_abstract_class_cannot_instantiate():
    """FeedbackHandler 是抽象类，不可直接实例化。"""
    with pytest.raises(TypeError):
        FeedbackHandler()


def test_missing_subscribed_events_raises():
    """未实现 subscribed_events 的子类实例化时应报错。"""
    with pytest.raises(TypeError):
        type("Incomplete", (FeedbackHandler,), {})()


def test_missing_handle_raises():
    """未实现 handle 的子类实例化时应报错。"""
    with pytest.raises(TypeError):
        type("NoHandle", (FeedbackHandler,), {
            "subscribed_events": lambda self: [LoopEventType.CI_FAILURE],
        })()
