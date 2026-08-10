"""Phase 7 coverage boost — event_bus.py E7a 目标组 (SystemEventBus 前半)。

Target (src/yuleosh/loop_engine/event_bus.py, SystemEventBus L1285-2261):
  - __init__                     (L1304-1437)
  - 组件属性                     (L1442-1469)
  - chain_config getter/setter   (L1474-1491) + chain_enabled (L1494-1499)
  - on / off / clear             (L1503-1548)
  - emit                         (L1552-1588)
  - _emit_event                  (L1590-1749, 全链路分支)
  - emit_signed                  (L1751-1793)
  - emit_async                   (L1795-1816)
  - _worker_loop                 (L1818-1830)
  - active_subscriptions         (L2258-2261)

策略:
  - 构造 bus 时统一注入 OSH_HOME=tmp（autouse fixture），死信/持久化磁盘
    写入全部落在 pytest tmp 目录，绝不触碰 repo 或系统 /tmp；
  - 环境变量 YULEOSH_EVENT_SOURCE_SECRET 一律清除，保证来源验证分支确定；
  - emit_async / _worker_loop 线程完全可控：patch threading.Thread 为
    捕获型假线程；_worker_loop 用 mock 的 queue.get 直接驱动函数体；
  - 重试线程 (time.sleep(1)) 通过 patch SystemEventBus._schedule_retry 杜绝；
  - 无网络 / 真实时间依赖 / multiprocessing。
"""

import hashlib
import json
import queue
import threading
import uuid
from typing import ClassVar
from unittest import mock

import pytest

from yuleosh.loop_engine import event_bus
from yuleosh.loop_engine.chain import ChainConfig, default_chain_config
from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType, SystemEventBus

# ═══════════════════════════════════════════════════════════════════════
# 公共 fixture / helper
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """隔离环境：OSH_HOME 指向 tmp，清除来源密钥环境变量。

    防止 DeadLetterQueue / EventQueuePersistence 把磁盘文件写到 repo 根
    （OSH_HOME 未设置时默认相对路径 ./ 或 /tmp），并保证 SourceValidator
    不读取宿主环境的 YULEOSH_EVENT_SOURCE_SECRET。
    """
    monkeypatch.setenv("OSH_HOME", str(tmp_path / "osh-home"))
    monkeypatch.delenv("YULEOSH_EVENT_SOURCE_SECRET", raising=False)


def _make_bus(**kwargs):
    """构造 SystemEventBus，默认关闭来源验证（多数 emit 测试不需要）。"""
    kwargs.setdefault("source_validation_enabled", False)
    return SystemEventBus(**kwargs)


class _FakeThread:
    """捕获 threading.Thread 调用但不真正启动线程（emit_async 可控）。"""

    instances: ClassVar[list] = []

    def __init__(self, target=None, **kwargs):
        self.target = target
        self.kwargs = kwargs
        self.started = False
        _FakeThread.instances.append(self)

    def start(self):
        self.started = True


# ═══════════════════════════════════════════════════════════════════════
# __init__ (L1304-1437)
# ═══════════════════════════════════════════════════════════════════════


def test_init_defaults_and_component_properties():
    """默认构造：内部状态 + 全部 7 个只读组件属性 (L1442-1469)。"""
    bus = _make_bus()
    assert isinstance(bus._lock, type(threading.RLock()))
    assert isinstance(bus._lock_emit, type(threading.Lock()))
    assert bus._dedup_window == 300.0
    assert bus._max_history == 2000
    assert bus._store is None
    assert bus._worker_thread is None
    assert bus._running is False
    assert bus._max_workers == 4
    assert bus._stats["total_emitted"] == 0
    assert bus._dedup_seen == {}
    # 属性 (L1442-1469)
    assert bus.source_validator is bus._source_validator
    assert bus.rate_limiter is bus._rate_limiter
    assert bus.dead_letter is bus._dead_letter
    assert bus.audit_log is bus._audit_log
    assert bus.persistence is bus._persistence
    assert bus.coalescing is bus._coalescing
    assert bus.persistence_enabled is False
    # 子组件类型
    assert isinstance(bus.source_validator, event_bus.SourceValidator)
    assert isinstance(bus.rate_limiter, event_bus.TokenBucket)
    assert isinstance(bus.dead_letter, event_bus.DeadLetterQueue)
    assert isinstance(bus.audit_log, event_bus.AuditLog)
    assert isinstance(bus.persistence, event_bus.EventQueuePersistence)
    assert isinstance(bus.coalescing, event_bus.CoalescingManager)


def test_init_custom_params_wired_to_components():
    """自定义参数正确注入子组件。"""
    store = mock.Mock()
    bus = SystemEventBus(
        dedup_window_seconds=42.0,
        store=store,
        max_workers=8,
        source_validation_enabled=True,
        source_secret="s3cret",
        source_whitelist=["ci.runner", "kg.reporter"],
        source_auto_whitelist=True,
        rate_limit_enabled=False,
        rate_limit_default=7.5,
        rate_limit_default_burst=9,
        rate_limit_per_type={"ci.failure": 1.0},
        dead_letter_max_retries=5,
        dead_letter_backoff=3.0,
        dead_letter_max_queue=77,
        audit_log_max_entries=123,
        persistence_enabled=False,
        persistence_base_path="/tmp/unused-base",
    )
    assert bus._dedup_window == 42.0
    assert bus._max_workers == 8
    assert bus._store is store
    assert bus.source_validator._secret == "s3cret"
    assert bus.source_validator._whitelist == {"ci.runner", "kg.reporter"}
    assert bus.source_validator._auto_whitelist_enabled is True
    assert bus.rate_limiter._enabled is False
    assert bus.rate_limiter._default_rate == 7.5
    assert bus.rate_limiter._default_burst == 9
    assert bus.rate_limiter._per_type_rates == {"ci.failure": 1.0}
    assert bus.dead_letter._max_retries == 5
    assert bus.dead_letter._backoff_factor == 3.0
    assert bus.dead_letter._max_queue == 77
    assert bus.audit_log._max_entries == 123


def test_init_persistence_enabled_no_recovered(tmp_path):
    """persistence_enabled=True 且无待恢复事件 → 不启动 worker。"""
    bus = _make_bus(
        persistence_enabled=True,
        persistence_base_path=str(tmp_path),
    )
    assert bus.persistence_enabled is True
    assert bus.persistence.base_path == str(tmp_path)
    assert bus._stats["total_recovered"] == 0
    assert bus._work_queue.qsize() == 0
    assert bus._running is False
    assert bus._worker_thread is None


def test_init_persistence_enabled_with_recovered(tmp_path):
    """persistence_enabled=True 且存在 pending 事件 → 恢复入队 + 创建 worker 线程。"""
    pending = [{
        "event_type": "ci.failure",
        "source": "recovered.src",
        "data": {"k": 1},
        "priority": 3,
        "dedup_key": "dk-rec-1",
        "event_id": "eid-rec-1",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "retry_count": 2,
        "max_retries": 3,
    }]
    with open(tmp_path / "pending_events.json", "w") as f:
        json.dump(pending, f)

    with mock.patch.object(event_bus.threading, "Thread", _FakeThread):
        bus = _make_bus(
            persistence_enabled=True,
            persistence_base_path=str(tmp_path),
        )
    assert bus._stats["total_recovered"] == 1
    assert bus._work_queue.qsize() == 1
    prio, idx, ev = bus._work_queue.get_nowait()
    assert prio == 3
    assert idx == 0
    assert ev.event_id == "eid-rec-1"
    # 恢复事件 retry_count 被重置为 0 (recover_unconsumed 行为)
    assert ev.retry_count == 0
    # 修复 (2026-08-11): 恢复路径现在会 .start() worker 线程（原漏调，事件入队无人消费）
    assert bus._running is True
    assert isinstance(bus._worker_thread, _FakeThread)
    assert bus._worker_thread.started is True


def test_init_persistence_disabled_uses_given_base_path(tmp_path):
    """persistence 关闭分支 (L1412-1419)：使用传入 base_path。"""
    base = str(tmp_path / "persist-off")
    bus = _make_bus(persistence_enabled=False, persistence_base_path=base)
    assert bus.persistence_enabled is False
    assert bus.persistence.base_path == base


def test_init_coalescing_windows():
    """loop1/loop4 聚合窗口配置 (L1423-1437) + 默认 0 窗口。"""
    bus = _make_bus()
    assert bus.coalescing.get_window(LoopEventType.CI_FAILURE) == 0.0
    assert bus.coalescing.get_window(LoopEventType.TEST_RESULT) == 0.0
    assert bus.coalescing.get_window(LoopEventType.KG_LOW_CONFIDENCE) == 0.0

    bus1 = _make_bus(loop1_coalescing_window=30.0)
    assert bus1.coalescing.get_window(LoopEventType.CI_FAILURE) == 30.0

    bus4 = _make_bus(loop4_coalescing_window=60.0)
    assert bus4.coalescing.get_window(LoopEventType.TEST_RESULT) == 60.0
    assert bus4.coalescing.get_window(LoopEventType.KG_LOW_CONFIDENCE) == 60.0


# ═══════════════════════════════════════════════════════════════════════
# chain_config (L1474-1491) / chain_enabled (L1494-1499)
# ═══════════════════════════════════════════════════════════════════════


def test_chain_config_getter_default_lazy_import():
    """_chain_config 为 None → 延迟导入 default_chain_config 并缓存。"""
    bus = _make_bus()
    assert bus._chain_config is None
    cc = bus.chain_config
    assert cc is default_chain_config
    assert bus._chain_config is default_chain_config
    # 二次访问走缓存
    assert bus.chain_config is default_chain_config


def test_chain_config_setter_and_reset_to_default():
    """setter 设置自定义配置；None 重置后 getter 重新导入默认。"""
    bus = _make_bus()
    custom = ChainConfig(max_depth=2)
    bus.chain_config = custom
    assert bus._chain_config is custom
    assert bus.chain_config is custom

    bus.chain_config = None
    assert bus._chain_config is None
    assert bus.chain_config is default_chain_config


def test_chain_enabled_variants():
    """chain_enabled：None→False；空配置→False；有规则→True。"""
    bus_none = _make_bus()
    assert bus_none.chain_enabled is False

    bus_empty = _make_bus()
    bus_empty.chain_config = ChainConfig()
    assert bus_empty.chain_enabled is False

    bus_rules = _make_bus()
    bus_rules.chain_config = default_chain_config
    assert bus_rules.chain_enabled is True


# ═══════════════════════════════════════════════════════════════════════
# on / off / clear (L1503-1548)
# ═══════════════════════════════════════════════════════════════════════


def test_on_registers_subscription_and_returns_id():
    """on() 注册回调并返回 uuid 订阅 ID。"""
    bus = _make_bus()
    cb = lambda e: None
    sub_id = bus.on(LoopEventType.CI_FAILURE, cb)
    uuid.UUID(sub_id)
    assert len(bus._subscriptions[LoopEventType.CI_FAILURE]) == 1
    sub = bus._subscriptions[LoopEventType.CI_FAILURE][0]
    assert sub.id == sub_id
    assert sub.callback is cb
    assert sub.priority_filter is None
    assert sub.one_shot is False
    assert bus._callbacks[sub_id] is cb
    assert bus.active_subscriptions() == {"ci.failure": 1}


def test_on_non_callable_raises_type_error():
    """callback 不可调用 → TypeError。"""
    bus = _make_bus()
    with pytest.raises(TypeError, match="callback must be callable"):
        bus.on(LoopEventType.CI_FAILURE, "not-a-callable")  # type: ignore[arg-type]


def test_on_priority_filter_and_one_shot():
    """priority_filter / one_shot 参数透传到 Subscription。"""
    bus = _make_bus()
    cb = lambda e: None
    sub_id = bus.on(LoopEventType.TEST_RESULT, cb, priority_filter=3, one_shot=True)
    sub = bus._subscriptions[LoopEventType.TEST_RESULT][0]
    assert sub.id == sub_id
    assert sub.priority_filter == 3
    assert sub.one_shot is True


def test_off_removes_only_matching_subscription():
    """off() 仅移除指定 ID；未知 ID 为 no-op。"""
    bus = _make_bus()
    cb1 = lambda e: None
    cb2 = lambda e: None
    cb3 = lambda e: None
    id1 = bus.on(LoopEventType.CI_FAILURE, cb1)
    id2 = bus.on(LoopEventType.CI_FAILURE, cb2)
    id3 = bus.on(LoopEventType.KPI_BREACH, cb3)

    bus.off(id1)
    assert [s.id for s in bus._subscriptions[LoopEventType.CI_FAILURE]] == [id2]
    assert [s.id for s in bus._subscriptions[LoopEventType.KPI_BREACH]] == [id3]
    assert id1 not in bus._callbacks
    assert id2 in bus._callbacks

    # 未知 ID → 无变化
    bus.off("no-such-id")
    assert [s.id for s in bus._subscriptions[LoopEventType.CI_FAILURE]] == [id2]
    assert bus.active_subscriptions() == {"ci.failure": 1, "kpi.breach": 1}


def test_clear_removes_all_subscriptions():
    """clear() 清空全部订阅与回调。"""
    bus = _make_bus()
    bus.on(LoopEventType.CI_FAILURE, lambda e: None)
    bus.on(LoopEventType.TEST_RESULT, lambda e: None)
    assert bus.active_subscriptions() == {"ci.failure": 1, "test.result": 1}
    bus.clear()
    assert bus._subscriptions == {}
    assert bus._callbacks == {}
    assert bus.active_subscriptions() == {}


# ═══════════════════════════════════════════════════════════════════════
# emit (L1552-1588)
# ═══════════════════════════════════════════════════════════════════════


def test_emit_constructs_event_and_dispatches():
    """emit() 构造 LoopEvent（data=None → {}）并派发给订阅者。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit(LoopEventType.CI_FAILURE, source="ci.runner", priority=2)
    assert isinstance(ev, LoopEvent)
    assert ev.event_type is LoopEventType.CI_FAILURE
    assert ev.source == "ci.runner"
    assert ev.priority == 2
    assert ev.data == {}
    assert ev.dedup_key is not None
    assert len(calls) == 1
    assert calls[0] is ev
    assert bus._stats["total_emitted"] == 1
    assert bus._stats["by_type"]["ci.failure"] == 1
    assert bus._stats["total_handled"] == 1
    assert ev.rollback_status == "no_rollback_needed"
    assert len(bus.history()) == 1


def test_emit_with_data_and_explicit_dedup_key():
    """data 与 dedup_key 透传。"""
    bus = _make_bus()
    ev = bus.emit(
        LoopEventType.CI_FAILURE,
        data={"test_name": "brake", "ok": False},
        dedup_key="my-custom-key",
    )
    assert ev.data == {"test_name": "brake", "ok": False}
    assert ev.dedup_key == "my-custom-key"


# ═══════════════════════════════════════════════════════════════════════
# _emit_event (L1590-1749) — 各分支
# ═══════════════════════════════════════════════════════════════════════


def test_emit_no_matching_subscribers():
    """无匹配订阅 → 早期返回，记录历史，不写审计。"""
    bus = _make_bus()
    ev = bus.emit(LoopEventType.CI_FAILURE, data={"x": 1})
    assert ev is not None
    assert bus._stats["total_emitted"] == 1
    assert bus._stats["total_handled"] == 0
    assert bus.audit_log.stats()["total_records"] == 0
    assert len(bus.history()) == 1
    assert ev.handler_results == []


def test_emit_source_validation_rejected():
    """来源验证失败 → 统计 + 死信 + 审计(rollback=n/a)，订阅者不被调用。"""
    bus = _make_bus(source_validation_enabled=True)
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit(LoopEventType.CI_FAILURE, source="evil.source")
    assert bus._stats["total_source_rejected"] == 1
    assert bus._stats["total_dead_letter"] == 1
    assert bus._stats["total_handled"] == 0
    assert bus.dead_letter.count() == 1
    assert calls == []
    assert ev.handler_results == [{
        "handler": "_validation",
        "status": "rejected",
        "reason": "no signing secret configured and auto_whitelist disabled",
    }]
    assert ev.rollback_status == "n/a"


def test_emit_source_whitelisted_passes():
    """白名单来源绕过 HMAC 直接通过。"""
    bus = _make_bus(
        source_validation_enabled=True,
        source_whitelist=["ci.runner"],
    )
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))
    ev = bus.emit(LoopEventType.CI_FAILURE, source="ci.runner")
    assert len(calls) == 1
    assert bus._stats["total_source_rejected"] == 0
    assert bus._stats["total_handled"] == 1
    assert ev.rollback_status == "no_rollback_needed"


def test_emit_rate_limited():
    """速率限制超限 → 统计 + 死信 + 审计。"""
    bus = _make_bus(
        rate_limit_default=0.0001,
        rate_limit_default_burst=1,
    )
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev1 = bus.emit(LoopEventType.CI_FAILURE, data={"n": 1})
    assert bus._stats["total_handled"] == 1
    assert bus._stats["total_rate_limited"] == 0
    assert ev1.rollback_status == "no_rollback_needed"

    ev2 = bus.emit(LoopEventType.CI_FAILURE, data={"n": 2})
    assert bus._stats["total_rate_limited"] == 1
    assert bus._stats["total_dead_letter"] == 1
    assert bus.dead_letter.count() == 1
    assert len(calls) == 1  # 第二个事件未派发
    assert ev2.handler_results == [{
        "handler": "_rate_limiter",
        "status": "rejected",
        "reason": "rate_limited",
    }]
    assert ev2.rollback_status == "n/a"


def test_emit_dedup_explicit_key():
    """显式 dedup_key 在窗口内重复 → 去重短路。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    bus.emit(LoopEventType.CI_FAILURE, dedup_key="dup-key")
    ev2 = bus.emit(LoopEventType.CI_FAILURE, dedup_key="dup-key")

    assert bus._stats["total_deduped"] == 1
    assert bus._stats["total_handled"] == 1
    assert len(calls) == 1
    assert len(bus.history()) == 1
    assert ev2.dedup_key == "dup-key"


def test_emit_dedup_auto_key_same_data():
    """相同载荷自动生成相同 dedup_key → 第二次去重。"""
    bus = _make_bus()
    data = {"test_name": "brake", "ok": False}
    bus.emit(LoopEventType.CI_FAILURE, data=data)
    bus.emit(LoopEventType.CI_FAILURE, data=data)
    assert bus._stats["total_deduped"] == 1
    assert bus._stats["total_emitted"] == 2
    assert len(bus.history()) == 1


def test_emit_coalesced_captured_in_window():
    """聚合窗口捕获 (group_key 非 None 且未就绪) → 不派发，仅记录历史。"""
    bus = _make_bus(loop1_coalescing_window=3600.0)
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit(LoopEventType.CI_FAILURE, data={"req_id": "RS-001"})
    assert bus._stats["total_handled"] == 0
    assert calls == []
    assert bus._stats["total_coalesced"] == 0
    groups = bus.coalescing.active_groups()
    assert "RS-001" in groups
    assert groups["RS-001"]["pending"] is True
    assert len(bus.history()) == 1
    assert ev.handler_results == []


def test_emit_coalesced_captured_with_persistence(tmp_path):
    """聚合捕获 + persistence 开启 → save_event 持久化 (L1646-1647)。"""
    bus = _make_bus(
        persistence_enabled=True,
        persistence_base_path=str(tmp_path),
        loop1_coalescing_window=3600.0,
    )
    bus.emit(LoopEventType.CI_FAILURE, data={"req_id": "RS-002"})
    assert bus.persistence.pending_count() == 1
    assert bus._stats["total_handled"] == 0
    assert bus.persistence.stats()["processed_ids_count"] == 0


def test_emit_persistence_all_success_marks_processed(tmp_path):
    """persistence + 全部 handler 成功 → mark_processed 移除 pending。"""
    bus = _make_bus(
        persistence_enabled=True,
        persistence_base_path=str(tmp_path),
    )
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit(LoopEventType.CI_FAILURE, data={"a": 1})
    assert len(calls) == 1
    assert bus.persistence.pending_count() == 0
    assert bus.persistence.stats()["processed_ids_count"] == 1
    assert ev.rollback_status == "no_rollback_needed"


def test_emit_persistence_not_all_success_keeps_pending(tmp_path):
    """persistence + handler 失败 → all_success=False → 不 mark_processed。"""
    bus = _make_bus(
        persistence_enabled=True,
        persistence_base_path=str(tmp_path),
    )

    def boom(e):
        raise RuntimeError("handler failed")

    bus.on(LoopEventType.CI_FAILURE, boom)
    with mock.patch.object(SystemEventBus, "_schedule_retry") as sched:
        bus.emit(LoopEventType.CI_FAILURE, data={"a": 2})
        assert sched.call_count == 1

    assert bus.persistence.pending_count() == 1
    assert bus.persistence.stats()["processed_ids_count"] == 0
    assert bus._stats["total_failed"] == 1


def test_emit_store_persist_event_called():
    """配置 store → _persist_event 写入 loop_events 表。"""
    store = mock.Mock()
    bus = _make_bus(store=store)
    bus.emit(LoopEventType.CI_FAILURE, source="ci.runner", data={"x": 1})

    assert store.insert.call_count == 1
    table, payload = store.insert.call_args[0]
    assert table == "loop_events"
    assert payload["event_type"] == "ci.failure"
    assert payload["source"] == "ci.runner"
    assert payload["data"] == '{"x": 1}'
    assert payload["signature"] == ""
    # _persist_event 在 handler 执行前调用 → rollback_status/handler_results 尚未赋值
    assert payload["rollback_status"] == ""
    assert payload["handler_results"] == "[]"


def test_emit_store_persist_error_logged(caplog):
    """store.insert 抛异常 → 记录 warning，不影响派发。"""
    store = mock.Mock()
    store.insert.side_effect = RuntimeError("disk full")
    bus = _make_bus(store=store)
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    with caplog.at_level("WARNING", logger="yuleosh.loop_engine.event_bus"):
        bus.emit(LoopEventType.CI_FAILURE, data={"x": 1})

    assert len(calls) == 1
    assert any("persist error" in r.message for r in caplog.records)


def test_emit_priority_filter_filters_subscribers():
    """priority_filter：事件 priority 高于 filter → 订阅者被过滤。"""
    bus = _make_bus()
    low_calls = []
    high_calls = []
    none_calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: low_calls.append(e), priority_filter=3)
    bus.on(LoopEventType.CI_FAILURE, lambda e: none_calls.append(e), priority_filter=None)
    bus.on(LoopEventType.CI_FAILURE, lambda e: high_calls.append(e), priority_filter=5)

    # priority=5: filter=3 被过滤；filter=None 与 filter=5 匹配 (5<=5)
    bus.emit(LoopEventType.CI_FAILURE, priority=5, data={"n": 1})
    assert low_calls == []
    assert len(none_calls) == 1
    assert len(high_calls) == 1

    # priority=6: filter=5 也被过滤；None filter 始终匹配（注意 data 不同避免去重）
    bus.emit(LoopEventType.CI_FAILURE, priority=6, data={"n": 2})
    assert len(high_calls) == 1
    assert len(none_calls) == 2

    # 全部订阅被 filter 排除 → 无匹配订阅分支
    bus2 = _make_bus()
    bus2.on(LoopEventType.CI_FAILURE, lambda e: None, priority_filter=3)
    ev = bus2.emit(LoopEventType.CI_FAILURE, priority=5, data={"n": 3})
    assert bus2._stats["total_handled"] == 0
    assert ev.handler_results == []
    assert len(bus2.history()) == 1


def test_emit_test_result_wildcard_subscribers():
    """TEST_RESULT 订阅者收到所有类型事件；自身类型不重复派发。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.TEST_RESULT, lambda e: calls.append(e))

    bus.emit(LoopEventType.CI_FAILURE, data={"a": 1})  # wildcard 命中
    bus.emit(LoopEventType.TEST_RESULT, data={"b": 2})  # 双列表命中但去重
    assert len(calls) == 2
    assert bus._stats["total_handled"] == 2


def test_emit_handlers_sorted_by_priority_filter():
    """匹配订阅按 priority_filter 升序执行。"""
    bus = _make_bus()
    order = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: order.append("filter5"), priority_filter=5)
    bus.on(LoopEventType.CI_FAILURE, lambda e: order.append("filter0"), priority_filter=0)

    bus.emit(LoopEventType.CI_FAILURE, priority=0)
    assert order == ["filter0", "filter5"]


def test_emit_handler_exception_retry_branch():
    """handler 抛异常且 retry_count < max_retries → 重试分支。"""
    bus = _make_bus()
    calls = []

    def boom(e):
        calls.append(e)
        raise RuntimeError("boom")

    bus.on(LoopEventType.CI_FAILURE, boom)
    with mock.patch.object(SystemEventBus, "_schedule_retry") as sched:
        ev = bus.emit(LoopEventType.CI_FAILURE, data={"r": 1})

    assert len(calls) == 1
    assert sched.call_count == 1
    assert ev.retry_count == 1
    assert bus._stats["total_failed"] == 1
    assert bus._stats["total_retried"] == 1
    assert ev.handler_results[0]["status"] == "failed"
    assert ev.handler_results[0]["retry"] == 1
    assert ev.rollback_status == "full_rollback"
    assert bus.dead_letter.count() == 0  # 重试分支不入死信


def test_emit_handler_exception_exhausted_branch():
    """handler 抛异常且重试耗尽 (max_retries=0) → exhausted + 死信。"""
    bus = _make_bus()

    def boom(e):
        raise RuntimeError("boom")

    bus.on(LoopEventType.CI_FAILURE, boom)
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="unit.test",
        data={"r": 2},
        max_retries=0,
    )
    with mock.patch.object(SystemEventBus, "_schedule_retry") as sched:
        ev = bus._emit_event(event)

    assert sched.call_count == 0
    assert ev.handler_results[0]["status"] == "exhausted"
    assert "boom" in ev.handler_results[0]["error"]
    assert bus._stats["total_failed"] == 1
    assert bus.dead_letter.count() == 1
    assert bus.dead_letter.list()[0]["failure_reason"].startswith("handler_exhausted:")
    assert ev.rollback_status == "full_rollback"


def test_emit_partial_rollback():
    """部分 handler 失败 → partial_rollback。"""
    bus = _make_bus()

    def ok_handler(e):
        pass

    def boom(e):
        raise RuntimeError("boom")

    bus.on(LoopEventType.CI_FAILURE, ok_handler)
    bus.on(LoopEventType.CI_FAILURE, boom)
    event = LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        data={"r": 3},
        max_retries=0,
    )
    ev = bus._emit_event(event)
    assert ev.rollback_status == "partial_rollback"
    assert bus._stats["total_handled"] == 1
    assert bus._stats["total_failed"] == 1
    assert bus.dead_letter.count() == 1


def test_emit_one_shot_auto_unsubscribe():
    """one_shot 订阅触发一次后自动取消。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e), one_shot=True)

    bus.emit(LoopEventType.CI_FAILURE, data={"o": 1})
    assert len(calls) == 1
    # off() 修复 (2026-08-11): 空订阅列表直接删除事件类型键，不再残留 {"ci.failure": 0}
    assert bus.active_subscriptions() == {}

    bus.emit(LoopEventType.CI_FAILURE, data={"o": 2})
    assert len(calls) == 1
    assert bus._stats["total_handled"] == 1


# ═══════════════════════════════════════════════════════════════════════
# emit_signed (L1751-1793)
# ═══════════════════════════════════════════════════════════════════════


def test_emit_signed_with_explicit_secret():
    """显式 secret → 设置 validator 密钥 + 指纹 = sha256(secret)[:8]，验证通过。"""
    bus = SystemEventBus(source_secret="bus-secret")
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit_signed(
        LoopEventType.CI_FAILURE, source="trusted.src", secret="custom-secret"
    )
    assert bus.source_validator._secret == "custom-secret"
    assert ev.source_fingerprint == hashlib.sha256(b"custom-secret").hexdigest()[:8]
    assert ev.signature != ""
    assert len(calls) == 1
    assert bus._stats["total_source_rejected"] == 0
    assert ev.rollback_status == "no_rollback_needed"


def test_emit_signed_without_secret_uses_bus_secret():
    """无 secret 参数 → 使用 bus 配置密钥，指纹为 "configured"。"""
    bus = SystemEventBus(source_secret="bus-secret")
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))

    ev = bus.emit_signed(LoopEventType.CI_FAILURE, source="trusted.src")
    assert ev.source_fingerprint == "configured"
    assert ev.signature != ""
    assert len(calls) == 1
    assert bus._stats["total_source_rejected"] == 0


def test_emit_signed_no_secret_rejected():
    """无任何密钥 → 空签名 → 来源验证拒绝。"""
    bus = SystemEventBus()  # 验证开启、无密钥（env 已被 fixture 清除）
    ev = bus.emit_signed(LoopEventType.CI_FAILURE, source="somewhere")
    assert ev.source_fingerprint == "configured"
    assert ev.signature == ""
    assert bus._stats["total_source_rejected"] == 1
    assert bus._stats["total_handled"] == 0


# ═══════════════════════════════════════════════════════════════════════
# emit_async (L1795-1816)
# ═══════════════════════════════════════════════════════════════════════


def test_emit_async_starts_worker_thread():
    """_running=False → 创建并启动 worker 线程（假线程，不真跑）。"""
    bus = _make_bus()
    _FakeThread.instances.clear()
    with mock.patch.object(event_bus.threading, "Thread", _FakeThread):
        bus.emit_async(LoopEventType.CI_FAILURE, source="async.src", priority=2)

    assert bus._running is True
    assert bus._work_queue.qsize() == 1
    prio, idx, queued = bus._work_queue.get_nowait()
    assert prio == 2
    assert idx == 0
    assert queued.event_type is LoopEventType.CI_FAILURE
    assert queued.source == "async.src"
    assert len(_FakeThread.instances) == 1
    fake = _FakeThread.instances[0]
    assert fake.target.__self__ is bus
    assert fake.target.__func__ is SystemEventBus._worker_loop
    assert fake.kwargs == {"daemon": True}
    assert fake.started is True


def test_emit_async_running_no_new_thread():
    """_running=True → 不再创建线程，仅入队。"""
    bus = _make_bus()
    bus._running = True
    _FakeThread.instances.clear()
    with mock.patch.object(event_bus.threading, "Thread", _FakeThread):
        bus.emit_async(LoopEventType.CI_FAILURE, data={"q": 1})

    assert bus._work_queue.qsize() == 1
    assert _FakeThread.instances == []


def test_emit_async_same_priority_queues_both():
    """回归 (2026-08-11): 同优先级两条事件不再抛 TypeError。

    源码曾用 ``put((event.priority, 0, event))``——idx 恒为 0，同优先级时
    heapq 比较 LoopEvent 实例（dataclass 无 __lt__）→ TypeError。
    修复: 全局单调计数器 _emit_seq 保证 idx 唯一。两条同优先级事件应都能入队。
    """
    bus = _make_bus()
    with mock.patch.object(event_bus.threading, "Thread", _FakeThread):
        bus.emit_async(LoopEventType.CI_FAILURE, source="a")
        bus.emit_async(LoopEventType.CI_FAILURE, source="b")  # 不再抛异常

    ev1 = bus._work_queue.get_nowait()
    ev2 = bus._work_queue.get_nowait()
    assert ev1[2].source == "a"
    assert ev2[2].source == "b"
    assert ev1[1] != ev2[1]  # 序号唯一


# ═══════════════════════════════════════════════════════════════════════
# _worker_loop (L1818-1830)
# ═══════════════════════════════════════════════════════════════════════


def test_worker_loop_not_running_exits_immediately():
    """_running=False → while 不进入，直接置 False 返回。"""
    bus = _make_bus()
    assert bus._running is False
    bus._worker_loop()
    assert bus._running is False


def test_worker_loop_processes_event_and_handles_empty():
    """worker 处理队列事件；queue.Empty → continue。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))
    ev = LoopEvent(event_type=LoopEventType.CI_FAILURE, data={"w": 1})

    bus._running = True
    real_emit = bus.emit

    def emit_and_stop(*args, **kwargs):
        result = real_emit(*args, **kwargs)
        bus._running = False
        return result

    bus.emit = emit_and_stop
    with mock.patch.object(
        bus._work_queue, "get",
        side_effect=[queue.Empty(), (ev.priority, 0, ev)],
    ):
        bus._worker_loop()

    assert len(calls) == 1
    # worker 通过 emit() 重建事件 → 对象不同但载荷一致
    assert calls[0].event_type is LoopEventType.CI_FAILURE
    assert calls[0].data == {"w": 1}
    assert bus._running is False
    assert bus._stats["total_emitted"] == 1
    assert bus._stats["total_handled"] == 1


def test_worker_loop_generic_exception_logged(caplog):
    """worker 捕获未知异常 → log.exception('worker error') 后继续。"""
    bus = _make_bus()
    calls = []
    bus.on(LoopEventType.CI_FAILURE, lambda e: calls.append(e))
    ev = LoopEvent(event_type=LoopEventType.CI_FAILURE, data={"w": 2})

    bus._running = True
    real_emit = bus.emit

    def emit_and_stop(*args, **kwargs):
        result = real_emit(*args, **kwargs)
        bus._running = False
        return result

    bus.emit = emit_and_stop
    with (
        mock.patch.object(
            bus._work_queue, "get",
            side_effect=[RuntimeError("worker boom"), (ev.priority, 0, ev)],
        ),
        caplog.at_level("ERROR", logger="yuleosh.loop_engine.event_bus"),
    ):
        bus._worker_loop()

    assert any("worker error" in r.message for r in caplog.records)
    assert len(calls) == 1
    assert bus._running is False


# ═══════════════════════════════════════════════════════════════════════
# active_subscriptions (L2258-2261)
# ═══════════════════════════════════════════════════════════════════════


def test_active_subscriptions_counts_by_type():
    """按事件类型返回订阅计数。"""
    bus = _make_bus()
    assert bus.active_subscriptions() == {}
    bus.on(LoopEventType.CI_FAILURE, lambda e: None)
    bus.on(LoopEventType.CI_FAILURE, lambda e: None)
    bus.on(LoopEventType.KPI_BREACH, lambda e: None)
    assert bus.active_subscriptions() == {"ci.failure": 2, "kpi.breach": 1}
