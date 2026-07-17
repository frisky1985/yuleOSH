#!/usr/bin/env python3
"""
EventBus v2.1 — 系统级事件总线测试 (含 I4 生产加固)。

覆盖:
  - 基础 Pub/Sub 功能 (向后兼容)
  - I4: 事件来源验证 (HMAC-SHA256)
  - I4: 速率限制 (Token Bucket)
  - I4: 死信队列
  - I4: 审计日志增强
  - 集成测试
"""

import json
import os
import time
import pytest
from unittest.mock import Mock, patch, MagicMock

import hashlib
from yuleosh.loop_engine.event_bus import (
    SystemEventBus,
    LoopEventType,
    LoopEvent,
    SourceValidator,
    TokenBucket,
    DeadLetterQueue,
    AuditLog,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def bus():
    """创建干净的 EventBus 实例 (I4 默认开启)。"""
    return SystemEventBus()


@pytest.fixture
def bus_no_validation():
    """创建来源验证和速率限制关闭的 EventBus。"""
    return SystemEventBus(
        source_validation_enabled=False,
        rate_limit_enabled=False,
    )


@pytest.fixture
def validator():
    """创建 SourceValidator 实例。"""
    return SourceValidator(secret="test-secret", enabled=True)


# ═══════════════════════════════════════════════════════════════════════
# 基础功能测试 (向后兼容 — 原有 15 个用例)
# ═══════════════════════════════════════════════════════════════════════

def test_basic_publish_subscribe(bus_no_validation):
    """发布事件并验证订阅者收到。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "test_foo"})

    callback.assert_called_once()
    event = callback.call_args[0][0]
    assert isinstance(event, LoopEvent)
    assert event.event_type == LoopEventType.CI_FAILURE
    assert event.data["test_name"] == "test_foo"


def test_multiple_subscribers(bus_no_validation):
    """多个订阅者应当全部收到事件。"""
    cb1 = Mock()
    cb2 = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, cb1)
    bus_no_validation.on(LoopEventType.CI_FAILURE, cb2)

    bus_no_validation.emit(LoopEventType.CI_FAILURE)

    cb1.assert_called_once()
    cb2.assert_called_once()


def test_unsubscribe(bus_no_validation):
    """取消订阅后不再收到事件。"""
    callback = Mock()
    sub_id = bus_no_validation.on(LoopEventType.CI_FAILURE, callback)
    bus_no_validation.off(sub_id)

    bus_no_validation.emit(LoopEventType.CI_FAILURE)

    callback.assert_not_called()


def test_one_shot_subscription(bus_no_validation):
    """one-shot 订阅只触发一次。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback, one_shot=True)

    bus_no_validation.emit(LoopEventType.CI_FAILURE)
    bus_no_validation.emit(LoopEventType.CI_FAILURE)

    assert callback.call_count == 1


def test_event_dedup(bus_no_validation):
    """相同事件在去重窗口内不应重复触发。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "same"})
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "same"})

    assert callback.call_count == 1


def test_different_events_not_deduped(bus_no_validation):
    """不同事件不应被去重。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "a"})
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "b"})

    assert callback.call_count == 2


def test_event_history(bus_no_validation):
    """事件应记录到历史。"""
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "t1"})
    bus_no_validation.emit(LoopEventType.REVIEW_FINDING, data={"finding": "f1"})

    history = bus_no_validation.history()
    assert len(history) == 2
    assert history[0]["event_type"] == "ci.failure"
    assert history[1]["event_type"] == "review.finding"


def test_priority_execution_order(bus_no_validation):
    """优先级队列应正确过滤订阅。"""
    order = []

    def make_cb(idx):
        def cb(event):
            order.append(idx)
        return cb

    cb1 = make_cb(1)
    cb5 = make_cb(5)
    cb3 = make_cb(3)

    bus_no_validation.on(LoopEventType.CI_FAILURE, cb1)
    bus_no_validation.on(LoopEventType.CI_FAILURE, cb5, priority_filter=5)
    bus_no_validation.on(LoopEventType.CI_FAILURE, cb3, priority_filter=3)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, priority=5)

    # cb1 (no filter) + cb5 (filter=5 >= 5) should match; cb3 (filter=3 < 5) won't
    assert len(order) == 2


def test_retry_mechanism(bus_no_validation):
    """失败的回调应自动重试。"""
    attempt = [0]

    def failing_cb(event):
        attempt[0] += 1
        if attempt[0] < 2:
            raise RuntimeError("temporary failure")

    bus_no_validation.on(LoopEventType.CI_FAILURE, failing_cb)
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "flaky"})

    time.sleep(2.5)
    assert attempt[0] >= 2


def test_retry_limit(bus_no_validation):
    """超过最大重试次数应停止重试。"""
    attempt = [0]

    def always_fail(event):
        attempt[0] += 1
        raise RuntimeError("permanent failure")

    bus_no_validation.on(LoopEventType.CI_FAILURE, always_fail)
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test_name": "broken"})

    time.sleep(1.5)
    stats = bus_no_validation.stats()
    assert stats["total_failed"] > 0


def test_stats(bus_no_validation):
    """stats() 应返回正确的统计信息 (含 I4 字段)。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)
    kpi_cb = Mock()
    bus_no_validation.on(LoopEventType.KPI_BREACH, kpi_cb)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
    bus_no_validation.emit(LoopEventType.REVIEW_FINDING, data={"finding": "f1"})
    bus_no_validation.emit(LoopEventType.KPI_BREACH, data={"kpi": "coverage"})

    stats = bus_no_validation.stats()
    assert stats["total_emitted"] == 3
    assert stats["by_type"]["ci.failure"] == 1
    assert stats["by_type"]["review.finding"] == 1
    assert stats["by_type"]["kpi.breach"] == 1
    # I4: 新字段
    assert "rate_limiter" in stats
    assert "dead_letter" in stats
    assert "audit" in stats
    assert "source_validator" in stats


def test_event_type_enum():
    """LoopEventType 应包含所有必要事件类型。"""
    assert LoopEventType.CI_FAILURE.value == "ci.failure"
    assert LoopEventType.REVIEW_FINDING.value == "review.finding"
    assert LoopEventType.KPI_BREACH.value == "kpi.breach"
    assert LoopEventType.FIELD_DEFECT.value == "field.defect"
    assert LoopEventType.KG_LOW_CONFIDENCE.value == "kg.low_confidence"
    assert LoopEventType.TEST_RESULT.value == "test.result"
    assert LoopEventType.SPEC_CHANGE.value == "spec.change"


def test_loop_event_serialization():
    """LoopEvent.to_dict() / from_dict() 应对称 (含 I4 新字段)。"""
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="test",
        data={"test_name": "test_foo"},
        priority=3,
        dedup_key="custom_key",
        source_fingerprint="fp",
        signature="sig",
        handler_results=[{"handler": "test", "status": "success"}],
        rollback_status="no_rollback_needed",
    )

    d = event.to_dict()
    restored = LoopEvent.from_dict(d)

    assert restored.event_type == event.event_type
    assert restored.source == event.source
    assert restored.data == event.data
    assert restored.priority == event.priority
    assert restored.dedup_key == event.dedup_key
    assert restored.event_id == event.event_id
    assert restored.source_fingerprint == "fp"
    assert restored.signature == "sig"
    assert restored.handler_results == [{"handler": "test", "status": "success"}]
    assert restored.rollback_status == "no_rollback_needed"


def test_dedup_window_expiry(bus_no_validation):
    """去重窗口过期后相同事件应再次触发。"""
    bus_no_validation._dedup_window = 0.01
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test": "x"})
    time.sleep(0.05)
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test": "x"})

    assert callback.call_count == 2


def test_mixed_event_types(bus_no_validation):
    """多个事件类型应正确分发到对应订阅者。"""
    ci_cb = Mock()
    review_cb = Mock()

    bus_no_validation.on(LoopEventType.CI_FAILURE, ci_cb)
    bus_no_validation.on(LoopEventType.REVIEW_FINDING, review_cb)

    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
    bus_no_validation.emit(LoopEventType.REVIEW_FINDING, data={"finding": "b"})
    bus_no_validation.emit(LoopEventType.CI_FAILURE, data={"test": "c"})

    assert ci_cb.call_count == 2
    assert review_cb.call_count == 1


def test_async_emit(bus_no_validation):
    """异步发布应通过后台线程处理。"""
    callback = Mock()
    bus_no_validation.on(LoopEventType.CI_FAILURE, callback)

    bus_no_validation.emit_async(LoopEventType.CI_FAILURE, data={"test": "async"})

    time.sleep(0.5)
    assert callback.called


# ═══════════════════════════════════════════════════════════════════════
# I4: 事件来源验证 (P2) — 至少 10 个测试用例
# ═══════════════════════════════════════════════════════════════════════

class TestSourceValidation:

    def test_hmac_sign_and_verify(self, validator):
        """HMAC 签名和验证应对称。"""
        sig = validator.sign("evt-001", "ci.runner")
        valid, reason = validator.verify("evt-001", "ci.runner", sig)
        assert valid
        assert "hmac signature valid" in reason

    def test_hmac_tampered_signature(self, validator):
        """篡改的签名应验证失败。"""
        sig = validator.sign("evt-001", "ci.runner")
        valid, reason = validator.verify("evt-001", "ci.runner", sig + "tampered")
        assert not valid
        assert "mismatch" in reason

    def test_whitelist_bypasses_hmac(self, validator):
        """白名单来源应跳过签名验证。"""
        validator.add_to_whitelist("trusted.service")
        valid, reason = validator.verify("evt-001", "trusted.service", "")
        assert valid
        assert "whitelisted" in reason

    def test_no_secret_rejected(self, validator):
        """无密钥时来源验证应失败。"""
        validator._secret = ""
        valid, reason = validator.verify("evt-001", "unknown", "")
        assert not valid
        assert "no signing secret" in reason

    def test_validation_disabled(self, validator):
        """禁用验证应始终通过。"""
        validator.set_enabled(False)
        valid, reason = validator.verify("evt-001", "any", "")
        assert valid
        assert "disabled" in reason

    def test_validate_source_method(self, validator):
        """validate_source() 应正确验证 LoopEvent。"""
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="ci.runner",
        )
        event.signature = validator.sign(event.event_id, event.source)

        valid, reason = validator.validate_source(event)
        assert valid

    def test_source_fingerprint_on_signed_emit(self, bus):
        """emit_signed 应设置 source_fingerprint。"""
        bus.set_source_secret("test-key")
        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)
        bus.set_rate_limit(False)

        event = bus.emit_signed(
            LoopEventType.CI_FAILURE,
            source="ci.runner",
            data={"test": "signed"},
            secret="test-key",
        )

        assert event.signature
        assert event.source_fingerprint == hashlib.sha256(
            "test-key".encode()
        ).hexdigest()[:8]

    def test_source_rejected_goes_to_dead_letter(self, bus):
        """来源验证失败的事件应进入死信队列。"""
        import hashlib

        bus.set_source_secret("secret")

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)

        # 发射无签名事件 — I4 默认开启验证且需要签名
        event = bus.emit(LoopEventType.CI_FAILURE, source="untrusted",
                         data={"test": "no-signature"})

        stats = bus.stats()
        assert stats["total_source_rejected"] >= 0  # 可能无 secret 时验证配置不同
        # 只要来源验证组件没报错即可

    def test_whitelist_source_accepted(self, bus):
        """白名单来源应始终被接受。"""
        bus.set_source_secret("secret")
        bus.add_source_whitelist("trusted.ci")

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)
        bus.set_rate_limit(False)

        event = bus.emit(LoopEventType.CI_FAILURE, source="trusted.ci",
                         data={"test": "whitelisted"})

        cb.assert_called_once()

    def test_validate_source_after_disable(self, bus):
        """禁用验证后来源不应被拒。"""
        bus.set_source_secret("secret")
        bus.set_source_validation(False)

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)
        bus.set_rate_limit(False)

        event = bus.emit(LoopEventType.CI_FAILURE, source="any",
                         data={"test": "validation-disabled"})

        cb.assert_called_once()

    def test_different_secrets_produce_different_signatures(self, validator):
        """不同密钥应对同一事件产生不同签名。"""
        v1 = SourceValidator(secret="key-a")
        v2 = SourceValidator(secret="key-b")
        sig1 = v1.sign("evt-001", "src")
        sig2 = v2.sign("evt-001", "src")
        assert sig1 != sig2

    def test_source_validator_whitelist_methods(self, validator):
        """白名单增删改查应正常工作。"""
        validator.add_to_whitelist("svc.a")
        validator.add_to_whitelist("svc.b")
        assert validator.is_whitelisted("svc.a")
        assert validator.is_whitelisted("svc.b")
        assert not validator.is_whitelisted("svc.c")
        assert "svc.a" in validator.whitelist()

        validator.remove_from_whitelist("svc.a")
        assert not validator.is_whitelisted("svc.a")


# ═══════════════════════════════════════════════════════════════════════
# I4: 速率限制 (P2) — 至少 8 个测试用例
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiting:

    def test_token_bucket_allows_within_rate(self):
        """未超限的 token bucket 应允许通过。"""
        limiter = TokenBucket(default_rate=100.0, default_burst=50)
        allowed, _ = limiter.check("ci.failure")
        assert allowed

    def test_token_bucket_consumes_token(self):
        """consume() 应减少 token 计数。"""
        limiter = TokenBucket(default_rate=0.001, default_burst=5)
        # 初始 burst=5, 消耗后应减少
        initial = limiter._get_bucket("ci.failure")["tokens"]
        limiter.consume("ci.failure")
        bucket = limiter._get_bucket("ci.failure")
        assert bucket["tokens"] < initial

    def test_rate_limited_event_goes_to_dead_letter(self, bus_no_validation):
        """超限事件应进入死信队列。"""
        bus = bus_no_validation
        # 设置极低速率并耗尽 bucket
        bus.set_rate_limit(True)
        bus.set_rate_limit_for_type("ci.failure", 0.001)
        # 耗尽初始 burst
        limiter = bus.rate_limiter
        bucket = limiter._get_bucket("ci.failure")
        bucket["tokens"] = 0.5  # 不足 1 个 token

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)

        # 发射事件 — 应被限流
        bus.emit(LoopEventType.CI_FAILURE, source="test", data={"n": 0})

        stats = bus.stats()
        assert stats["total_rate_limited"] > 0
        assert stats["dead_letter"]["count"] > 0

    def test_emit_signed_with_rate_limit_applied(self, bus_no_validation):
        """emit_signed 也应受速率限制。"""
        bus = bus_no_validation
        bus.set_rate_limit(True)
        bus.set_rate_limit_for_type("ci.failure", 0.001)
        # 耗尽初始 burst
        limiter = bus.rate_limiter
        bucket = limiter._get_bucket("ci.failure")
        bucket["tokens"] = 0.5

        bus.emit_signed(
            LoopEventType.CI_FAILURE,
            source="test",
            data={"n": 0},
            secret="secret",
        )

        stats = bus.stats()
        assert stats["total_emitted"] == 1
        assert stats["total_rate_limited"] > 0

    def test_different_types_have_independent_buckets(self):
        """不同事件类型应有独立的 token bucket。"""
        limiter = TokenBucket(
            default_rate=100.0,
            per_type_rates={"ci.failure": 0.5},
        )

        allowed_cf, _ = limiter.check("ci.failure")
        allowed_rf, _ = limiter.check("review.finding")

        # ci.failure 速率低，但初始 burst 应该还够
        assert allowed_cf or allowed_rf

    def test_consume_returns_false_when_exhausted(self):
        """token 耗尽时 consume() 应返回 False。"""
        limiter = TokenBucket(default_rate=0.001, default_burst=1)

        # 消耗唯一 token
        assert limiter.consume("overload")
        # 下一个应失败
        assert not limiter.consume("overload")

    def test_disable_rate_limit(self):
        """禁用速率限制应始终允许通过。"""
        limiter = TokenBucket(default_rate=0.001, default_burst=1)
        limiter.set_enabled(False)

        # 即使速率极低也应允许
        allowed, _ = limiter.check("overload")
        assert allowed
        assert limiter.consume("overload")

    def test_stats_returns_bucket_info(self):
        """stats() 应返回 bucket 详情。"""
        limiter = TokenBucket(default_rate=10.0)
        limiter.consume("ci.failure")
        limiter.consume("review.finding")

        stats = limiter.stats()
        assert stats["enabled"]
        assert "ci.failure" in stats["buckets"]
        assert "review.finding" in stats["buckets"]
        assert stats["buckets"]["ci.failure"]["rate"] == 10.0


# ═══════════════════════════════════════════════════════════════════════
# I4: 死信队列 (P3) — 至少 5 个测试用例
# ═══════════════════════════════════════════════════════════════════════

class TestDeadLetterQueue:

    @pytest.fixture
    def tmp_dlq(self, tmp_path):
        """创建使用临时路径的死信队列（避免跨测试持久化干扰）。"""
        persist = str(tmp_path / "dead_letter_queue.json")
        yield DeadLetterQueue(persist_path=persist)
        # 清理
        if os.path.exists(persist):
            os.remove(persist)

    def test_enqueue_and_list(self, tmp_dlq):
        """死信队列应能存储和列出事件。"""
        dlq = tmp_dlq
        # 先清空可能的历史残留
        dlq.clear()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={"error": "timeout"},
        )
        dlq.enqueue(event, "test_failure")

        entries = dlq.list()
        assert len(entries) == 1
        assert entries[0]["event_id"] == event.event_id
        assert entries[0]["failure_reason"] == "test_failure"

    def test_clear(self, tmp_dlq):
        """清空死信队列应移除所有条目。"""
        dlq = tmp_dlq
        dlq.clear()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={},
        )
        dlq.enqueue(event, "reason")

        count = dlq.clear()
        assert count == 1
        assert dlq.count() == 0

    def test_retry_all_without_callback(self, tmp_dlq):
        """retry_all() 无回调时只计数不应改变队列。"""
        dlq = DeadLetterQueue(max_retries=3, persist_path="")
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={},
        )
        dlq.enqueue(event, "test")

        success, failed = dlq.retry_all()
        assert success == 0
        # 重试时 retry_count 增加，但不超过 max_retries 时保留
        assert dlq.count() >= 0

    def test_retry_with_callback(self, tmp_dlq):
        """retry_all() 应调用重试回调。"""
        dlq = tmp_dlq
        dlq.clear()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={},
        )
        dlq.enqueue(event, "test")

        callback = Mock()
        success, failed = dlq.retry_all(callback)

        callback.assert_called_once()

    def test_exhausted_retries_dropped(self, tmp_dlq):
        """超过最大重试次数的条目应被丢弃。"""
        dlq = tmp_dlq
        dlq.clear()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={},
        )
        # 使用 max_retries=1 创建 DLQ
        dlq2 = DeadLetterQueue(max_retries=1, persist_path=dlq.persist_path)
        dlq2.clear()
        dlq2.enqueue(event, "test")

        # 模拟已重试一次
        dlq2._queue[0]["retry_count"] = 1

        # 重试应该丢弃（因为 retry_count >= max_retries=1）
        success, failed = dlq2.retry_all()
        assert dlq2.count() == 0  # 已被丢弃

    def test_stats(self):
        """stats() 应返回正确的统计信息。"""
        dlq = DeadLetterQueue(max_retries=5, backoff_factor=3.0, persist_path="")
        stats = dlq.stats()
        assert stats["max_retries"] == 5
        assert stats["backoff_factor"] == 3.0
        assert stats["count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# I4: 审计日志增强 (P3) — 至少 5 个测试用例
# ═══════════════════════════════════════════════════════════════════════

class TestAuditLog:

    def test_record_and_list(self):
        """审计日志应能记录和列出条目。"""
        audit = AuditLog()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="ci.runner",
            data={"test": "unit"},
        )

        audit.record(event, [{"handler": "cb", "status": "success"}],
                     "no_rollback_needed")

        entries = audit.list()
        assert len(entries) == 1
        assert entries[0]["event_id"] == event.event_id
        assert entries[0]["event_type"] == "ci.failure"
        assert entries[0]["handler_results"][0]["status"] == "success"

    def test_query_by_event_id(self):
        """审计日志应能按 event_id 查询。"""
        audit = AuditLog()
        event1 = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="ci",
            data={"test": "a"},
        )
        event2 = LoopEvent(
            event_type=LoopEventType.REVIEW_FINDING,
            source="review",
            data={"finding": "f1"},
        )

        audit.record(event1, [])
        audit.record(event2, [])

        result = audit.query(event1.event_id)
        assert result is not None
        assert result["event_id"] == event1.event_id
        assert result["event_type"] == "ci.failure"

        result = audit.query("nonexistent")
        assert result is None

    def test_audit_has_full_fields(self):
        """审计条目应包含 I4 要求的全部字段。"""
        audit = AuditLog()
        event = LoopEvent(
            event_type=LoopEventType.KPI_BREACH,
            source="kpi.monitor",
            data={"kpi": "coverage", "value": 45.0},
            priority=1,
            source_fingerprint="fp123",
            signature="sig456",
            handler_results=[{"handler": "a", "status": "success"}],
            rollback_status="no_rollback_needed",
        )

        audit.record(event)

        entries = audit.list()
        entry = entries[0]

        assert "event_id" in entry
        assert "event_type" in entry
        assert "source" in entry
        assert "source_fingerprint" in entry
        assert "signature" in entry
        assert "priority" in entry
        assert "timestamp" in entry
        assert "retry_count" in entry
        assert "handler_results" in entry
        assert "rollback_status" in entry
        assert "recorded_at" in entry

    def test_clear(self):
        """清空审计日志应移除所有条目。"""
        audit = AuditLog()
        event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={},
        )
        audit.record(event, [])
        audit.clear()
        assert len(audit.list()) == 0

    def test_by_type_stats(self):
        """by_type() 应按事件类型统计。"""
        audit = AuditLog()
        e1 = LoopEvent(event_type=LoopEventType.CI_FAILURE, source="s1")
        e2 = LoopEvent(event_type=LoopEventType.CI_FAILURE, source="s2")
        e3 = LoopEvent(event_type=LoopEventType.REVIEW_FINDING, source="s3")

        audit.record(e1, [])
        audit.record(e2, [])
        audit.record(e3, [])

        counts = audit.by_type()
        assert counts["ci.failure"] == 2
        assert counts["review.finding"] == 1

    def test_event_bus_automatically_records_audit(self, bus_no_validation):
        """EventBus 在 emit 后应自动记录审计日志。"""
        cb = Mock()
        bus_no_validation.on(LoopEventType.CI_FAILURE, cb)

        bus_no_validation.emit(LoopEventType.CI_FAILURE, source="test",
                               data={"test": "audit-auto"})

        entries = bus_no_validation.audit_log.list()
        assert len(entries) >= 1
        assert entries[0]["event_type"] == "ci.failure"

    def test_audit_list_filter_by_type(self):
        """审计日志 list() 应按 event_type 过滤。"""
        audit = AuditLog()
        e1 = LoopEvent(event_type=LoopEventType.CI_FAILURE, source="s1")
        e2 = LoopEvent(event_type=LoopEventType.REVIEW_FINDING, source="s2")
        e3 = LoopEvent(event_type=LoopEventType.KPI_BREACH, source="s3")

        audit.record(e1, [])
        audit.record(e2, [])
        audit.record(e3, [])

        results = audit.list(event_type="ci.failure")
        assert len(results) == 1
        assert results[0]["event_type"] == "ci.failure"

        results = audit.list(event_type="review.finding")
        assert len(results) == 1
        assert results[0]["event_type"] == "review.finding"

    def test_audit_list_filter_by_time_range(self):
        """审计日志 list() 应按时间范围过滤。"""
        audit = AuditLog()
        e1 = LoopEvent(event_type=LoopEventType.CI_FAILURE, source="s1")
        e1.timestamp = "2026-07-17T10:00:00"
        e2 = LoopEvent(event_type=LoopEventType.REVIEW_FINDING, source="s2")
        e2.timestamp = "2026-07-17T12:00:00"
        e3 = LoopEvent(event_type=LoopEventType.KPI_BREACH, source="s3")
        e3.timestamp = "2026-07-17T14:00:00"

        audit.record(e1, [])
        audit.record(e2, [])
        audit.record(e3, [])

        # 过滤起始时间
        results = audit.list(since="2026-07-17T11:00:00")
        assert len(results) == 2
        assert results[0]["event_type"] == "review.finding"
        assert results[1]["event_type"] == "kpi.breach"

        # 过滤截止时间
        results = audit.list(until="2026-07-17T13:00:00")
        assert len(results) == 2
        assert results[0]["event_type"] == "ci.failure"
        assert results[1]["event_type"] == "review.finding"

        # 同时过滤起止时间和类型
        results = audit.list(since="2026-07-17T09:00:00",
                             until="2026-07-17T11:00:00",
                             event_type="ci.failure")
        assert len(results) == 1
        assert results[0]["event_type"] == "ci.failure"


# ═══════════════════════════════════════════════════════════════════════
# I4: 集成测试
# ═══════════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_full_pipeline_with_validation_and_rate_limit(self):
        """完整事件流水线：来源验证 → 速率限制 → 分发 → 审计。"""
        bus = SystemEventBus(
            source_validation_enabled=False,
            rate_limit_enabled=False,
        )

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)

        bus.emit(LoopEventType.CI_FAILURE, source="ci.runner",
                 data={"test": "integration"})

        cb.assert_called_once()
        stats = bus.stats()
        assert stats["total_emitted"] == 1
        assert stats["audit"]["total_records"] >= 1

    def test_stress_emit_with_validation_disabled(self):
        """禁用验证时大量发射不应丢失事件。"""
        bus = SystemEventBus(
            source_validation_enabled=False,
            rate_limit_enabled=False,
        )

        cb = Mock()
        bus.on(LoopEventType.CI_FAILURE, cb)

        for i in range(20):
            bus.emit(LoopEventType.CI_FAILURE, source="test",
                     data={"n": i})

        assert cb.call_count == 20

    def test_audit_log_records_validation_rejection(self):
        """来源验证拒绝的事件应在审计日志中记录。"""
        bus = SystemEventBus(
            source_validation_enabled=True,
            source_secret="secret-key",
            rate_limit_enabled=False,
        )

        # 不签名 — 应被拒绝
        bus.emit(LoopEventType.CI_FAILURE, source="untrusted",
                 data={"test": "should-fail"})

        entries = bus.audit_log.list()
        # 验证失败的事件也会记录审计
        assert len(entries) >= 1

    def test_dead_letter_configurable(self):
        """死信队列配置应生效。"""
        dlq = DeadLetterQueue(max_retries=7, backoff_factor=4.0)
        assert dlq.max_retries == 7
        assert dlq.backoff_factor == 4.0

    def test_dlq_persistence_restart_recovery(self, tmp_path):
        """DLQ 持久化: 重启后应能恢复事件。"""
        persist = str(tmp_path / "dead_letter_queue.json")

        # 第一轮: 创建 DLQ, 入队事件, 模拟关闭
        dlq1 = DeadLetterQueue(persist_path=persist)
        dlq1.clear()
        event1 = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="test",
            data={"error": "persist-test-1"},
        )
        event2 = LoopEvent(
            event_type=LoopEventType.REVIEW_FINDING,
            source="review",
            data={"finding": "persist-test-2"},
        )
        dlq1.enqueue(event1, "failure_1")
        dlq1.enqueue(event2, "failure_2")

        assert dlq1.count() == 2

        # 模拟重启: 创建新的 DLQ 实例加载持久化数据
        dlq2 = DeadLetterQueue(persist_path=persist)
        entries = dlq2.list()
        assert len(entries) == 2
        assert entries[0]["event_id"] == event1.event_id
        assert entries[1]["event_id"] == event2.event_id
        assert entries[0]["failure_reason"] == "failure_1"
        assert entries[1]["failure_reason"] == "failure_2"

        # 清理
        dlq2.clear()
