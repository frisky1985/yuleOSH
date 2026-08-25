"""Phase 7 E7b — SystemEventBus 后半全分支覆盖率测试。

目标: src/yuleosh/loop_engine/event_bus.py L1834-2256 全行/全分支覆盖:
  - I5 Loop Chaining (_trigger_chained_events / set_chain_max_depth / clear_chain_context)
  - ACC-005/008 持久化管理 (set_persistence_base_path / set_persistence_enabled / recover_from_crash)
  - ACC-106/406 合并窗口 (set_loop1/loop4_coalescing_window / flush_* / clear / active)
  - I4 source 配置 (set_source_secret / set_source_validation / whitelist 增删 / auto_whitelist)
  - I4 限流 (set_rate_limit / set_rate_limit_for_type)
  - 去重 (_is_duplicate), store 注入 (set_store), _persist_event
  - _record_audit / _compute_rollback_status / _schedule_retry
  - _append_history / history / clear_history / stats

策略:
  - 时间依赖全部 mock: event_bus.py 内是模块级 `import time`,
    因此 patch `yuleosh.loop_engine.event_bus.time.time` / `time.sleep` 即可拦截。
  - 线程用假 Thread 类 (start 不真正启动线程), 需要执行 retry 体时手动调用
    target(), 确定性覆盖 _schedule_retry 全部分支, 无真实 sleep/线程。
  - recover_from_crash 的恢复委托 patch 到 _persistence.recover_unconsumed
    (EventQueuePersistence 本体已由 E5 覆盖, 此处只测 SystemEventBus 侧分支)。
  - 无网络 / 无 subprocess / 无 multiprocessing / 无真实时间依赖。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

from typing import ClassVar
from unittest import mock

import pytest

from yuleosh.loop_engine.chain import ChainConfig, ChainContext
from yuleosh.loop_engine.event_bus import (
    LoopEvent,
    LoopEventType,
    Subscription,
    SystemEventBus,
)

# event_bus.py 内为模块级 `import time`, patch 模块属性即可拦截。
_TIME_PATH = "yuleosh.loop_engine.event_bus.time.time"
_SLEEP_PATH = "yuleosh.loop_engine.event_bus.time.sleep"
_THREAD_PATH = "yuleosh.loop_engine.event_bus.threading.Thread"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


class FakeStore:
    """最小可注入 store: 记录 insert 调用。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def insert(self, table: str, record: dict):
        self.calls.append((table, record))


def _make_fake_thread_cls():
    """假 Thread: start() 不真正启动, 记录实例供手动执行 target。"""

    class FakeThread:
        instances: ClassVar[list["FakeThread"]] = []

        def __init__(self, target=None, daemon=False):
            self.target = target
            self.daemon = daemon
            FakeThread.instances.append(self)

        def start(self):
            pass

    return FakeThread


@pytest.fixture
def bus(tmp_path, monkeypatch):
    """默认总线: 持久化关闭、来源验证/限流关闭, 全部落盘路径隔离到 tmp_path。"""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return SystemEventBus(
        persistence_base_path=str(tmp_path / "loop"),
        source_validation_enabled=False,
        rate_limit_enabled=False,
    )


def _make_persistence_bus(tmp_path, monkeypatch):
    """启用持久化的总线 (用于 recover_from_crash)。"""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return SystemEventBus(
        persistence_enabled=True,
        persistence_base_path=str(tmp_path / "loop"),
        source_validation_enabled=False,
        rate_limit_enabled=False,
    )


def _ev(event_type: LoopEventType, data: dict | None = None, **kw) -> LoopEvent:
    return LoopEvent(event_type=event_type, source="e7b.test", data=data or {}, **kw)


# ═══════════════════════════════════════════════════════════════════════
# I5 Loop Chaining — _trigger_chained_events (L1834-1934)
# ═══════════════════════════════════════════════════════════════════════


def test_chain_all_failed_skips(bus):
    """handler 全部失败 → 直接返回, 不触发任何链式事件。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "failed"}, {"status": "exhausted"}])
    assert bus.history(limit=10) == []


def test_chain_no_config_returns(bus):
    """_chain_config 为 None → 直接返回。"""
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus.history(limit=10) == []


def test_chain_no_targets_returns(bus):
    """配置了规则但当前事件类型无匹配 target → 返回。"""
    cc = ChainConfig()
    cc.add_rule("review.finding", "Loop2FieldToFMEAHandler")
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus.history(limit=10) == []


def test_chain_target_without_event_mapping_skipped(bus):
    """target handler 无事件映射 (绕过 add_rule 校验注入) → warning + continue。"""
    cc = ChainConfig()
    cc._rules["ci.failure"] = ["MysteryHandler"]
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus.history(limit=10) == []


def test_chain_success_propagates_context(bus):
    """成功链路: 创建 ChainContext、透传 root/depth/trigger/target, 清理上下文。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE, {"req_id": "R1"}, priority=3)
    # 第二个 result 无 handler 键 → 覆盖 `if hname:` 空分支
    bus._trigger_chained_events(
        ev, [{"status": "success", "handler": "h1"}, {"status": "success"}]
    )
    assert bus._chain_context is None
    chain_hist = [h for h in bus.history(limit=10) if h["event_type"] == "kpi.breach"]
    assert len(chain_hist) == 1
    data = chain_hist[0]["data"]
    assert data["_chain_root_event_id"] == ev.event_id
    assert data["_chain_depth"] == 1
    assert data["_chain_trigger"] == "ci.failure"
    assert data["_chain_target"] == "Loop3KPIToImproveHandler"
    assert data["req_id"] == "R1"


def test_chain_empty_results_still_chains(bus):
    """handler_results 为空 → all_failed=True 但列表为空, 仍继续链式触发。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [])
    chain_hist = [h for h in bus.history(limit=10) if h["event_type"] == "kpi.breach"]
    assert len(chain_hist) == 1


def test_chain_existing_context_reused(bus):
    """已有 ChainContext → 复用 (不重建), root_event_id 来自既有上下文。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    bus._chain_context = ChainContext(root_event_id="root0", max_depth=5)
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus._chain_context is None
    chain_hist = [h for h in bus.history(limit=10) if h["event_type"] == "kpi.breach"]
    assert chain_hist[-1]["data"]["_chain_root_event_id"] == "root0"


def test_chain_visited_handler_blocked(bus):
    """防循环: 目标 handler 已在 visited_handlers → can_chain False → 跳过。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ctx = ChainContext(root_event_id="root1", max_depth=5)
    ctx.visited_handlers.add("Loop3KPIToImproveHandler")
    bus._chain_context = ctx
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus._chain_context is None
    assert bus.history(limit=10) == []


def test_chain_depth_limit_blocked(bus):
    """防循环: 深度已达上限 → can_chain False → 跳过。"""
    cc = ChainConfig(max_depth=2)
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ctx = ChainContext(root_event_id="root2", max_depth=2)
    ctx.depth = 2
    bus._chain_context = ctx
    ev = _ev(LoopEventType.CI_FAILURE)
    bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus.history(limit=10) == []


def test_chain_emit_exception_caught(bus):
    """链式 _emit_event 抛异常 → 捕获并记 error, 不向上传播。"""
    cc = ChainConfig()
    cc.add_rule("ci.failure", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    ev = _ev(LoopEventType.CI_FAILURE)
    with mock.patch.object(bus, "_emit_event", side_effect=RuntimeError("boom")):
        bus._trigger_chained_events(ev, [{"status": "success"}])
    assert bus._chain_context is None


# ── set_chain_max_depth / clear_chain_context (L1936-1950) ────────────


def test_set_chain_max_depth(bus):
    cc = ChainConfig()
    bus._chain_config = cc
    bus.set_chain_max_depth(3)
    assert bus._chain_config.max_depth == 3


def test_set_chain_max_depth_invalid_raises(bus):
    cc = ChainConfig()
    bus._chain_config = cc
    with pytest.raises(ValueError):
        bus.set_chain_max_depth(0)


def test_clear_chain_context(bus):
    bus._chain_context = ChainContext(root_event_id="x")
    bus.clear_chain_context()
    assert bus._chain_context is None


# ═══════════════════════════════════════════════════════════════════════
# ACC-005/008 持久化管理 (L1954-1994)
# ═══════════════════════════════════════════════════════════════════════


def test_set_persistence_base_path(bus, tmp_path):
    new_path = tmp_path / "new_loop"
    bus.set_persistence_base_path(str(new_path))
    assert bus.persistence.base_path == str(new_path)
    assert new_path.is_dir()  # EventQueuePersistence 构造时创建目录


def test_set_persistence_enabled_toggle(bus):
    assert bus.persistence_enabled is False
    bus.set_persistence_enabled(True)
    assert bus.persistence_enabled is True
    bus.set_persistence_enabled(False)
    assert bus.persistence_enabled is False


def test_recover_from_crash_disabled_returns_zero(bus):
    assert bus.recover_from_crash() == 0


def test_recover_from_crash_empty_recovery(tmp_path, monkeypatch):
    pbus = _make_persistence_bus(tmp_path, monkeypatch)
    fake_thread = _make_fake_thread_cls()
    with mock.patch.object(
        pbus._persistence, "recover_unconsumed", return_value=[]
    ), mock.patch(_THREAD_PATH, fake_thread):
        assert pbus.recover_from_crash() == 0
    assert pbus._work_queue.qsize() == 0
    assert fake_thread.instances == []
    assert pbus._running is False


def test_recover_from_crash_re_enqueues_and_starts_worker(tmp_path, monkeypatch):
    pbus = _make_persistence_bus(tmp_path, monkeypatch)
    fake_thread = _make_fake_thread_cls()
    ev1 = _ev(LoopEventType.CI_FAILURE, {"a": 1})
    ev2 = _ev(LoopEventType.TEST_RESULT, {"b": 2})
    with mock.patch.object(
        pbus._persistence, "recover_unconsumed", return_value=[ev1, ev2]
    ), mock.patch(_THREAD_PATH, fake_thread):
        count = pbus.recover_from_crash()
    assert count == 2
    assert pbus._work_queue.qsize() == 2
    assert pbus._stats["total_recovered"] == 2
    assert pbus._stats["total_emitted"] == 2
    assert pbus._stats["by_type"]["ci.failure"] == 1
    assert pbus._stats["by_type"]["test.result"] == 1
    assert pbus._running is True
    assert len(fake_thread.instances) == 1
    assert fake_thread.instances[0].target == pbus._worker_loop


def test_recover_from_crash_worker_already_running(tmp_path, monkeypatch):
    pbus = _make_persistence_bus(tmp_path, monkeypatch)
    fake_thread = _make_fake_thread_cls()
    pbus._running = True  # 模拟 worker 已启动 → 不再创建线程
    ev = _ev(LoopEventType.CI_FAILURE)
    with mock.patch.object(
        pbus._persistence, "recover_unconsumed", return_value=[ev]
    ), mock.patch(_THREAD_PATH, fake_thread):
        assert pbus.recover_from_crash() == 1
    assert pbus._running is True
    assert fake_thread.instances == []


# ═══════════════════════════════════════════════════════════════════════
# ACC-106/406 合并窗口管理 (L1998-2060)
# ═══════════════════════════════════════════════════════════════════════


def test_set_loop1_coalescing_window_enable_and_disable(bus):
    bus.set_loop1_coalescing_window(30.0)
    assert bus.coalescing.get_window(LoopEventType.CI_FAILURE) == 30.0
    bus.set_loop1_coalescing_window(0.0)  # <=0 → remove_window
    assert bus.coalescing.get_window(LoopEventType.CI_FAILURE) == 0.0


def test_set_loop4_coalescing_window_enable_and_disable(bus):
    bus.set_loop4_coalescing_window(60.0)
    assert bus.coalescing.get_window(LoopEventType.TEST_RESULT) == 60.0
    assert bus.coalescing.get_window(LoopEventType.KG_LOW_CONFIDENCE) == 60.0
    bus.set_loop4_coalescing_window(0.0)
    assert bus.coalescing.get_window(LoopEventType.TEST_RESULT) == 0.0
    assert bus.coalescing.get_window(LoopEventType.KG_LOW_CONFIDENCE) == 0.0


def test_flush_loop1_coalesced_ready(bus):
    bus.set_loop1_coalescing_window(30.0)
    ev = _ev(LoopEventType.CI_FAILURE, {"req_id": "R1"})
    clock = {"t": 1000.0}
    with mock.patch(_TIME_PATH, side_effect=lambda: clock["t"]):
        bus._coalescing.add_event(ev, group_key="R1")  # window_start=1000, elapsed 0
        assert bus.active_coalescing_groups() == {
            "R1": {
                "group_key": "R1",
                "event_type": "ci.failure",
                "event_count": 1,
                "window_start": 1000.0,
                "pending": True,
            }
        }
        clock["t"] = 1031.0  # elapsed 31 >= 30 → ready
        groups = bus.flush_loop1_coalesced()
    assert len(groups) == 1
    assert groups[0].group_key == "R1"
    assert bus._stats["total_coalesced"] == 1
    assert bus.active_coalescing_groups() == {}


def test_flush_loop1_coalesced_not_ready(bus):
    bus.set_loop1_coalescing_window(30.0)
    ev = _ev(LoopEventType.CI_FAILURE, {"req_id": "R1"})
    with mock.patch(_TIME_PATH, return_value=1000.0):
        bus._coalescing.add_event(ev, group_key="R1")
        groups = bus.flush_loop1_coalesced()
    assert groups == []
    assert bus._stats["total_coalesced"] == 1
    assert "R1" in bus.active_coalescing_groups()


def test_flush_loop4_coalesced_ready(bus):
    bus.set_loop4_coalescing_window(60.0)
    ev = _ev(LoopEventType.TEST_RESULT, {"entity_id": "E1"})
    clock = {"t": 2000.0}
    with mock.patch(_TIME_PATH, side_effect=lambda: clock["t"]):
        bus._coalescing.add_event(ev, group_key="E1")
        clock["t"] = 2061.0  # elapsed 61 >= 60 → ready
        groups = bus.flush_loop4_coalesced()
    assert len(groups) == 1
    assert groups[0].group_key == "E1"
    assert bus._stats["total_coalesced"] == 1


def test_clear_coalescing(bus):
    bus.set_loop1_coalescing_window(30.0)
    ev = _ev(LoopEventType.CI_FAILURE, {"req_id": "R1"})
    with mock.patch(_TIME_PATH, return_value=1000.0):
        bus._coalescing.add_event(ev, group_key="R1")
    assert bus.active_coalescing_groups() != {}
    bus.clear_coalescing()
    assert bus.active_coalescing_groups() == {}


# ═══════════════════════════════════════════════════════════════════════
# I4 source 配置 (L2064-2082) / 限流 (L2086-2092)
# ═══════════════════════════════════════════════════════════════════════


def test_source_configuration_setters(bus):
    bus.set_source_secret("s3cr3t")
    assert bus.source_validator._secret == "s3cr3t"
    bus.set_source_validation(False)
    assert bus.source_validator.enabled is False
    bus.set_source_validation(True)
    assert bus.source_validator.enabled is True
    bus.add_source_whitelist("trusted.source")
    assert "trusted.source" in bus.source_validator.whitelist()
    bus.set_source_auto_whitelist(True)
    assert bus.source_validator.auto_whitelist_enabled is True
    bus.remove_source_whitelist("trusted.source")
    assert "trusted.source" not in bus.source_validator.whitelist()


def test_rate_limit_setters(bus):
    bus.set_rate_limit(False)
    assert bus.rate_limiter.enabled is False
    bus.set_rate_limit(True)
    assert bus.rate_limiter.enabled is True
    bus.set_rate_limit_for_type("ci.failure", 7.5)
    assert bus.rate_limiter._per_type_rates["ci.failure"] == 7.5


# ═══════════════════════════════════════════════════════════════════════
# 去重 _is_duplicate (L2096-2109)
# ═══════════════════════════════════════════════════════════════════════


def test_is_duplicate_first_then_repeat(bus):
    ev = _ev(LoopEventType.CI_FAILURE, dedup_key="dup1")
    assert bus._is_duplicate(ev) is False
    assert bus._is_duplicate(ev) is True


def test_is_duplicate_window_expiry_re_records(bus):
    bus._dedup_window = 5.0
    ev = _ev(LoopEventType.CI_FAILURE, dedup_key="dup1")
    with mock.patch(_TIME_PATH, return_value=1000.0):
        assert bus._is_duplicate(ev) is False
    with mock.patch(_TIME_PATH, return_value=1006.0):
        # 已过窗口 (6 >= 5) → 非重复, 重新记录时间戳
        assert bus._is_duplicate(ev) is False
    with mock.patch(_TIME_PATH, return_value=1007.0):
        assert bus._is_duplicate(ev) is True
    assert bus._dedup_seen["dup1"] == 1006.0


def test_is_duplicate_stale_key_cleanup(bus):
    bus._dedup_window = 5.0
    bus._dedup_seen = {"stale1": 100.0, "stale2": 101.0}
    ev = _ev(LoopEventType.CI_FAILURE, dedup_key="fresh")
    with mock.patch(_TIME_PATH, return_value=115.0):
        assert bus._is_duplicate(ev) is False
    # 115 - 100/101 > 2*5 → 两个过期键被清理
    assert bus._dedup_seen == {"fresh": 115.0}


# ═══════════════════════════════════════════════════════════════════════
# Store 注入 / 持久化 / 审计 / 回滚状态 (L2113-2167)
# ═══════════════════════════════════════════════════════════════════════


def test_set_store_rebuilds_children(bus):
    store = FakeStore()
    old_path = bus.dead_letter.persist_path
    old_max_retries = bus.dead_letter.max_retries
    old_backoff = bus.dead_letter.backoff_factor
    old_max_queue = bus.dead_letter.max_queue
    old_max_entries = bus.audit_log.stats()["max_entries"]
    bus.set_store(store)
    assert bus._store is store
    assert bus.dead_letter._store is store
    assert bus.audit_log._store is store
    assert bus.dead_letter.persist_path == old_path
    assert bus.dead_letter.max_retries == old_max_retries
    assert bus.dead_letter.backoff_factor == old_backoff
    assert bus.dead_letter.max_queue == old_max_queue
    assert bus.audit_log.stats()["max_entries"] == old_max_entries


def test_persist_event_writes_full_record(bus):
    store = FakeStore()
    bus._store = store
    ev = _ev(
        LoopEventType.CI_FAILURE,
        {"x": 1},
        dedup_key="k1",
        priority=2,
    )
    ev.source_fingerprint = "fp123"
    ev.signature = "sig456"
    ev.handler_results = [{"handler": "h1", "status": "success"}]
    ev.rollback_status = "no_rollback_needed"
    bus._persist_event(ev)
    assert len(store.calls) == 1
    table, record = store.calls[0]
    assert table == "loop_events"
    assert record["event_id"] == ev.event_id
    assert record["event_type"] == "ci.failure"
    assert record["source"] == "e7b.test"
    assert record["source_fingerprint"] == "fp123"
    assert record["signature"] == "sig456"
    assert record["data"] == '{"x": 1}'
    assert record["priority"] == 2
    assert record["dedup_key"] == "k1"
    assert record["timestamp"] == ev.timestamp
    assert record["retry_count"] == 0
    assert record["max_retries"] == 3
    assert record["handler_results"] == '[{"handler": "h1", "status": "success"}]'
    assert record["rollback_status"] == "no_rollback_needed"


def test_persist_event_store_error_swallowed(bus):
    class BoomStore:
        def insert(self, table, record):
            raise RuntimeError("db down")

    bus._store = BoomStore()
    # 显式 dedup_key 跳过 __post_init__ 的 json.dumps 自动去重键生成,
    # 让不可序列化 data 的 TypeError 落在 _persist_event 的 try 内被吞掉。
    ev = _ev(
        LoopEventType.CI_FAILURE, data={"bad": object()}, dedup_key="k-bad"
    )
    bus._persist_event(ev)  # 不抛异常


def test_record_audit_sets_fields_and_logs(bus):
    ev = _ev(LoopEventType.CI_FAILURE)
    results = [{"handler": "h1", "status": "success"}]
    bus._record_audit(ev, results, "no_rollback_needed")
    assert ev.handler_results == results
    assert ev.rollback_status == "no_rollback_needed"
    entries = bus.audit_log.list()
    assert len(entries) == 1
    assert entries[0]["event_id"] == ev.event_id
    assert entries[0]["rollback_status"] == "no_rollback_needed"


def test_compute_rollback_status_all_variants(bus):
    assert bus._compute_rollback_status([]) == "no_rollback_needed"
    assert bus._compute_rollback_status([{"status": "success"}]) == "no_rollback_needed"
    assert (
        bus._compute_rollback_status(
            [{"status": "success"}, {"status": "failed"}]
        )
        == "partial_rollback"
    )
    assert (
        bus._compute_rollback_status(
            [{"status": "failed"}, {"status": "exhausted"}]
        )
        == "full_rollback"
    )


# ═══════════════════════════════════════════════════════════════════════
# 重试 _schedule_retry (L2171-2196)
# ═══════════════════════════════════════════════════════════════════════


def _run_retry_target(bus, event, callback):
    """调度重试并同步执行 retry 体 (假线程 + 假 sleep)。"""
    sub = Subscription(
        id="sub-retry", event_type=event.event_type, callback=callback
    )
    fake_thread = _make_fake_thread_cls()
    with mock.patch(_THREAD_PATH, fake_thread), mock.patch(_SLEEP_PATH):
        bus._schedule_retry(event, sub)
        assert len(fake_thread.instances) == 1
        fake_thread.instances[-1].target()
    return fake_thread


def test_schedule_retry_success(bus):
    calls = []

    def cb(ev):
        calls.append(ev)

    ev = _ev(LoopEventType.CI_FAILURE)
    _run_retry_target(bus, ev, cb)
    assert calls == [ev]
    assert bus._stats["total_handled"] == 1
    assert bus._stats["total_failed"] == 0


def test_schedule_retry_failure_reschedules(bus):
    def cb(ev):
        raise RuntimeError("boom")

    ev = _ev(LoopEventType.CI_FAILURE, max_retries=3)
    sub = Subscription(
        id="sub-retry", event_type=ev.event_type, callback=cb
    )
    fake_thread = _make_fake_thread_cls()
    with mock.patch(_THREAD_PATH, fake_thread), mock.patch(_SLEEP_PATH):
        bus._schedule_retry(ev, sub)
        # 第一次执行 → 失败 → retry_count 0→1, 重新调度
        fake_thread.instances[-1].target()
        assert ev.retry_count == 1
        assert bus._stats["total_failed"] == 1
        assert bus._stats["total_retried"] == 1
        assert len(fake_thread.instances) == 2
        # 第二次执行 → 仍失败 → retry_count 1→2, 再次调度
        fake_thread.instances[-1].target()
        assert ev.retry_count == 2
        assert bus._stats["total_failed"] == 2
        assert bus._stats["total_retried"] == 2
        assert len(fake_thread.instances) == 3


def test_schedule_retry_exhausted_goes_to_dead_letter(bus):
    def cb(ev):
        raise RuntimeError("boom")

    ev = _ev(LoopEventType.CI_FAILURE, max_retries=3)
    ev.retry_count = 3  # 已耗尽 → 入死信队列
    _run_retry_target(bus, ev, cb)
    assert bus._stats["total_failed"] == 1
    assert bus._stats["total_retried"] == 0
    assert bus.dead_letter.count() == 1
    entry = bus.dead_letter.list()[-1]
    assert "retry_exhausted" in entry["failure_reason"]


# ═══════════════════════════════════════════════════════════════════════
# 历史 (L2200-2221)
# ═══════════════════════════════════════════════════════════════════════


def test_append_history_caps_at_max(bus):
    bus._max_history = 2
    e1 = _ev(LoopEventType.CI_FAILURE)
    e2 = _ev(LoopEventType.TEST_RESULT)
    e3 = _ev(LoopEventType.SPEC_CHANGE)
    bus._append_history(e1)
    bus._append_history(e2)
    bus._append_history(e3)
    hist = bus.history(limit=10)
    assert len(hist) == 2
    assert [h["event_id"] for h in hist] == [e2.event_id, e3.event_id]


def test_history_filter_and_limit(bus):
    for i in range(5):
        bus._append_history(_ev(LoopEventType.CI_FAILURE, {"i": i}))
    for i in range(3):
        bus._append_history(_ev(LoopEventType.TEST_RESULT, {"i": i}))
    assert len(bus.history(limit=100)) == 8
    ci = bus.history(event_type=LoopEventType.CI_FAILURE, limit=100)
    assert len(ci) == 5
    assert all(h["event_type"] == "ci.failure" for h in ci)
    limited = bus.history(limit=3)
    assert len(limited) == 3
    assert limited[0]["event_type"] == "test.result"
    assert set(limited[0].keys()) >= {
        "event_id", "event_type", "data", "dedup_key", "timestamp",
    }


def test_clear_history(bus):
    bus._append_history(_ev(LoopEventType.CI_FAILURE))
    assert len(bus.history(limit=10)) == 1
    bus.clear_history()
    assert bus.history(limit=10) == []


# ═══════════════════════════════════════════════════════════════════════
# 统计 stats (L2225-2256)
# ═══════════════════════════════════════════════════════════════════════


def test_stats_shape_and_chain_disabled(bus):
    s = bus.stats()
    assert s["total_emitted"] == 0
    assert "rate_limiter" in s and s["rate_limiter"]["enabled"] is False
    assert "dead_letter" in s and "audit" in s
    assert s["source_validator"] == {
        "enabled": False,
        "has_secret": False,
        "whitelist": [],
        "auto_whitelist": False,
    }
    assert s["chain"] == {"enabled": False}
    assert "base_path" in s["persistence"]
    assert s["coalescing"]["active_groups"] == 0


def test_stats_chain_with_chain_config(bus):
    cc = ChainConfig()
    cc.add_rule("loop1.done", "Loop3KPIToImproveHandler")
    bus._chain_config = cc
    s = bus.stats()
    assert s["chain"] == {
        "max_depth": 5,
        "active_rules": 1,
        "rules": {"loop1.done": ["Loop3KPIToImproveHandler"]},
    }


def test_stats_chain_with_non_config_object(bus):
    bus._chain_config = {"custom": True}
    assert bus.stats()["chain"] == {"enabled": True}


def test_stats_source_secret_flag(bus):
    bus.set_source_secret("sekrit")
    assert bus.stats()["source_validator"]["has_secret"] is True
    assert bus.stats()["source_validator"]["enabled"] is False


def test_active_subscriptions_counts(bus):
    def cb(ev):
        pass

    bus.on(LoopEventType.CI_FAILURE, cb)
    bus.on(LoopEventType.CI_FAILURE, cb)
    bus.on(LoopEventType.TEST_RESULT, cb)
    assert bus.active_subscriptions() == {
        "ci.failure": 2,
        "test.result": 1,
    }
