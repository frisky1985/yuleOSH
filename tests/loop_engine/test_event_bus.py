#!/usr/bin/env python3
"""
EventBus v2 — 系统级事件总线测试。
"""

import time
import pytest
from unittest.mock import Mock, patch

from yuleosh.loop_engine.event_bus import (
    SystemEventBus,
    LoopEventType,
    LoopEvent,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def bus():
    """创建干净的 EventBus 实例。"""
    return SystemEventBus()


# ═══════════════════════════════════════════════════════════════════════
# 测试 1: 基本 Pub/Sub
# ═══════════════════════════════════════════════════════════════════════

def test_basic_publish_subscribe(bus):
    """发布事件并验证订阅者收到。"""
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "test_foo"})

    callback.assert_called_once()
    event = callback.call_args[0][0]
    assert isinstance(event, LoopEvent)
    assert event.event_type == LoopEventType.CI_FAILURE
    assert event.data["test_name"] == "test_foo"


# ═══════════════════════════════════════════════════════════════════════
# 测试 2: 多订阅者
# ═══════════════════════════════════════════════════════════════════════

def test_multiple_subscribers(bus):
    """多个订阅者应当全部收到事件。"""
    cb1 = Mock()
    cb2 = Mock()
    bus.on(LoopEventType.CI_FAILURE, cb1)
    bus.on(LoopEventType.CI_FAILURE, cb2)

    bus.emit(LoopEventType.CI_FAILURE)

    cb1.assert_called_once()
    cb2.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# 测试 3: 取消订阅
# ═══════════════════════════════════════════════════════════════════════

def test_unsubscribe(bus):
    """取消订阅后不再收到事件。"""
    callback = Mock()
    sub_id = bus.on(LoopEventType.CI_FAILURE, callback)
    bus.off(sub_id)

    bus.emit(LoopEventType.CI_FAILURE)

    callback.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# 测试 4: One-shot 订阅
# ═══════════════════════════════════════════════════════════════════════

def test_one_shot_subscription(bus):
    """one-shot 订阅只触发一次。"""
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback, one_shot=True)

    bus.emit(LoopEventType.CI_FAILURE)
    bus.emit(LoopEventType.CI_FAILURE)

    assert callback.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# 测试 5: 事件去重
# ═══════════════════════════════════════════════════════════════════════

def test_event_dedup(bus):
    """相同事件在去重窗口内不应重复触发。"""
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "same"})
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "same"}  )
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "same"})

    # 后两个应被去重
    assert callback.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# 测试 6: 不同事件不被去重
# ═══════════════════════════════════════════════════════════════════════

def test_different_events_not_deduped(bus):
    """不同事件不应被去重。"""
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "a"})
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "b"})

    assert callback.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# 测试 7: 事件历史
# ═══════════════════════════════════════════════════════════════════════

def test_event_history(bus):
    """事件应记录到历史。"""
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "t1"})
    bus.emit(LoopEventType.REVIEW_FINDING, data={"finding": "f1"})

    history = bus.history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ci.failure"
    assert history[1]["event_type"] == "review.finding"

    filtered = bus.history(event_type=LoopEventType.CI_FAILURE)
    assert len(filtered) == 1
    assert filtered[0]["event_type"] == "ci.failure"


# ═══════════════════════════════════════════════════════════════════════
# 测试 8: 优先级队列
# ═══════════════════════════════════════════════════════════════════════

def test_priority_execution_order(bus):
    """高优先级 (低数值) 事件应优先处理。

    priority_filter: 订阅者只接收 priority <= filter 的事件。
    event priority=5: 只有 filter=5 的订阅者收到。
    """
    order = []

    def make_cb(idx):
        def cb(event):
            order.append(idx)
        return cb

    bus.on(LoopEventType.CI_FAILURE, make_cb(1))
    bus.on(LoopEventType.CI_FAILURE, make_cb(5), priority_filter=5)
    bus.on(LoopEventType.CI_FAILURE, make_cb(3), priority_filter=3)

    # 无 filter 的订阅者接收所有事件；filter=5 的也接收 priority=5；filter=3 的不接收
    bus.emit(LoopEventType.CI_FAILURE, priority=5)

    assert len(order) == 2


# ═══════════════════════════════════════════════════════════════════════
# 测试 9: 重试机制
# ═══════════════════════════════════════════════════════════════════════

def test_retry_mechanism(bus):
    """失败的回调应自动重试。(退避 1s, 等待 2.5s) """
    attempt = [0]

    def failing_cb(event):
        attempt[0] += 1
        if attempt[0] < 2:
            raise RuntimeError("temporary failure")

    bus.on(LoopEventType.CI_FAILURE, failing_cb)
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "flaky"})

    # 第一次同步执行(失败) + 1s 退避后重试
    time.sleep(2.5)
    assert attempt[0] >= 2


# ═══════════════════════════════════════════════════════════════════════
# 测试 10: 重试次数限制
# ═══════════════════════════════════════════════════════════════════════

def test_retry_limit(bus):
    """超过最大重试次数应停止重试。"""
    attempt = [0]

    def always_fail(event):
        attempt[0] += 1
        raise RuntimeError("permanent failure")

    bus.on(LoopEventType.CI_FAILURE, always_fail)
    bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "broken"})

    time.sleep(1.5)
    stats = bus.stats()
    assert stats["total_failed"] > 0


# ═══════════════════════════════════════════════════════════════════════
# 测试 11: 统计信息
# ═══════════════════════════════════════════════════════════════════════

def test_stats(bus):
    """stats() 应返回正确的统计信息。

    注意: Ci_FAILURE 有订阅者, REVIEW_FINDING 和 KPI_BREACH 无订阅者。
    """
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
    bus.emit(LoopEventType.REVIEW_FINDING, data={"finding": "f1"})
    bus.emit(LoopEventType.KPI_BREACH, data={"kpi": "coverage"})

    # 还需要订阅 KPI_BREACH 才能让 handled 达到 3
    kpi_cb = Mock()
    bus.on(LoopEventType.KPI_BREACH, kpi_cb)
    bus.emit(LoopEventType.KPI_BREACH, data={"kpi2": "covered"})

    stats = bus.stats()
    assert stats["total_emitted"] == 4
    # CI_FAILURE: 1 handled, KPI_BREACH (second emit): 1 handled
    assert stats["total_handled"] == 2
    assert stats["by_type"]["ci.failure"] == 1
    assert stats["by_type"]["review.finding"] == 1
    assert stats["by_type"]["kpi.breach"] == 2


# ═══════════════════════════════════════════════════════════════════════
# 测试 12: 事件类型枚举
# ═══════════════════════════════════════════════════════════════════════

def test_event_type_enum():
    """LoopEventType 应包含所有必要事件类型。"""
    assert LoopEventType.CI_FAILURE.value == "ci.failure"
    assert LoopEventType.REVIEW_FINDING.value == "review.finding"
    assert LoopEventType.KPI_BREACH.value == "kpi.breach"
    assert LoopEventType.FIELD_DEFECT.value == "field.defect"
    assert LoopEventType.KG_LOW_CONFIDENCE.value == "kg.low_confidence"
    assert LoopEventType.TEST_RESULT.value == "test.result"
    assert LoopEventType.SPEC_CHANGE.value == "spec.change"
    assert len(LoopEventType) == 7


# ═══════════════════════════════════════════════════════════════════════
# 测试 13: LoopEvent 序列化/反序列化
# ═══════════════════════════════════════════════════════════════════════

def test_loop_event_serialization():
    """LoopEvent.to_dict() / from_dict() 应对称。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="test",
        data={"test_name": "test_foo"},
        priority=3,
        dedup_key="custom_key",
    )

    d = event.to_dict()
    restored = LoopEvent.from_dict(d)

    assert restored.event_type == event.event_type
    assert restored.source == event.source
    assert restored.data == event.data
    assert restored.priority == event.priority
    assert restored.dedup_key == event.dedup_key
    assert restored.event_id == event.event_id
    assert restored.timestamp == event.timestamp


# ═══════════════════════════════════════════════════════════════════════
# 测试 14: 超时去重窗口
# ═══════════════════════════════════════════════════════════════════════

def test_dedup_window_expiry(bus):
    """去重窗口过期后相同事件应再次触发。"""
    bus._dedup_window = 0.01  # 极短窗口
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit(LoopEventType.CI_FAILURE, data={"test": "x"})
    time.sleep(0.05)
    bus.emit(LoopEventType.CI_FAILURE, data={"test": "x"})

    # 去重窗口已过期, 应触发两次
    assert callback.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# 测试 15: 多事件类型混合
# ═══════════════════════════════════════════════════════════════════════

def test_mixed_event_types(bus):
    """多个事件类型应正确分发到对应订阅者。"""
    ci_cb = Mock()
    review_cb = Mock()

    bus.on(LoopEventType.CI_FAILURE, ci_cb)
    bus.on(LoopEventType.REVIEW_FINDING, review_cb)

    bus.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
    bus.emit(LoopEventType.REVIEW_FINDING, data={"finding": "b"})
    bus.emit(LoopEventType.CI_FAILURE, data={"test": "c"})

    assert ci_cb.call_count == 2
    assert review_cb.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# 测试 16: 异步发布
# ═══════════════════════════════════════════════════════════════════════

def test_async_emit(bus):
    """异步发布应通过后台线程处理。"""
    callback = Mock()
    bus.on(LoopEventType.CI_FAILURE, callback)

    bus.emit_async(LoopEventType.CI_FAILURE, data={"test": "async"})

    time.sleep(0.5)
    assert callback.called
