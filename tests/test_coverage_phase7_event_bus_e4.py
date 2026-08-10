"""Phase 7 E4 — DeadLetterQueue + AuditLog 全分支覆盖率测试。

目标: src/yuleosh/loop_engine/event_bus.py L517-712 (DeadLetterQueue)
      与 L719-911 (AuditLog) 全行覆盖。

时间处理: event_bus 模块内的 ``datetime`` 通过 autouse fixture 冻结为
固定时刻 (2026-06-01T12:00:00+00:00)，所有断言完全确定化 —— 无真实时间依赖。
无 subprocess/网络/multiprocessing。
"""

import json
import logging
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from yuleosh.loop_engine.event_bus import (
    AuditLog,
    DeadLetterQueue,
    LoopEvent,
    LoopEventType,
)

# event_bus.py 内为 `from datetime import datetime, timezone`，
# patch 模块属性即可拦截 datetime.now() / datetime.fromisoformat()。
_DATETIME_PATH = "yuleosh.loop_engine.event_bus.datetime"

_FROZEN_NOW = "2026-06-01T12:00:00+00:00"


class _FrozenDatetime:
    """固定墙钟：datetime.now() 恒返回 2026-06-01T12:00:00+00:00。"""

    _NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls._NOW

    @classmethod
    def fromisoformat(cls, s):
        return datetime.fromisoformat(s)


@pytest.fixture(autouse=True)
def _freeze_event_bus_clock():
    """冻结 event_bus 内的 datetime —— 全部测试时间确定化。"""
    with patch(_DATETIME_PATH, _FrozenDatetime):
        yield


class _FakeStore:
    """记录 insert 调用；fail=True 时抛异常以覆盖日志分支。"""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def insert(self, table, entry):
        self.calls.append((table, entry))
        if self.fail:
            raise RuntimeError("store boom")


def _make_event(event_type=LoopEventType.CI_FAILURE, **kw):
    """构造带完整审计字段的 LoopEvent。"""
    defaults = {
        "source": "ci.runner",
        "data": {"test": "brake"},
        "priority": 5,
        "event_id": "evt-001",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "retry_count": 2,
        "source_fingerprint": "fp",
        "signature": "sig",
        "handler_results": [{"handler": "hA", "status": "ok"}],
        "rollback_status": "none",
    }
    defaults.update(kw)
    return LoopEvent(event_type=event_type, **defaults)


# ═══════════════════════════════════════════════════════════════════════
# DeadLetterQueue — __init__ / 属性
# ═══════════════════════════════════════════════════════════════════════


def test_dlq_init_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    dlq = DeadLetterQueue()
    assert dlq.max_retries == 3
    assert dlq.backoff_factor == 2.0
    assert dlq.max_queue == 5000
    assert dlq.persist_path == str(
        tmp_path / ".yuleosh" / "loop" / "dead_letter_queue.json"
    )
    assert dlq.count() == 0
    assert dlq.stats()["persist_exists"] is False


def test_dlq_init_custom_values():
    dlq = DeadLetterQueue(
        max_retries=1, backoff_factor=0.5, max_queue=2, persist_path=""
    )
    assert dlq.max_retries == 1
    assert dlq.backoff_factor == 0.5
    assert dlq.max_queue == 2
    assert dlq.persist_path is None


def test_dlq_init_persist_path_disabled_empty_string():
    dlq = DeadLetterQueue(persist_path="")
    assert dlq.persist_path is None
    assert dlq.stats()["persist_path"] is None
    assert dlq.stats()["persist_exists"] is False


def test_dlq_init_loads_existing_disk_file(tmp_path):
    p = tmp_path / "dlq.json"
    p.write_text(json.dumps([{"event_id": "a"}, {"event_id": "b"}]))
    dlq = DeadLetterQueue(persist_path=str(p))
    assert dlq.count() == 2
    assert [e["event_id"] for e in dlq.list()] == ["a", "b"]


def test_dlq_init_loads_non_list_ignored(tmp_path):
    p = tmp_path / "dlq.json"
    p.write_text(json.dumps({"event_id": "a"}))
    dlq = DeadLetterQueue(persist_path=str(p))
    assert dlq.count() == 0


def test_dlq_init_loads_corrupt_file_warns(tmp_path, caplog):
    p = tmp_path / "dlq.json"
    p.write_text("{not-json")
    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        dlq = DeadLetterQueue(persist_path=str(p))
    assert "load from disk error" in caplog.text
    assert dlq.count() == 0


def test_dlq_load_from_disk_no_path():
    dlq = DeadLetterQueue(persist_path="")
    dlq._load_from_disk()  # persist_path 为 None → 直接短路，无副作用
    assert dlq.count() == 0


def test_dlq_persist_path_property(tmp_path):
    p = tmp_path / "dlq.json"
    dlq = DeadLetterQueue(persist_path=str(p))
    assert dlq.persist_path == str(p)


# ═══════════════════════════════════════════════════════════════════════
# DeadLetterQueue — enqueue / list / count / clear
# ═══════════════════════════════════════════════════════════════════════


def test_dlq_enqueue_basic():
    dlq = DeadLetterQueue(persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    assert dlq.count() == 1
    e = dlq.list()[0]
    assert e["event_id"] == "evt-001"
    assert e["event_type"] == "ci.failure"
    assert e["source"] == "ci.runner"
    assert e["data"] == {"test": "brake"}
    assert e["priority"] == 5
    assert e["dedup_key"]
    assert e["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert e["failed_at"] == _FROZEN_NOW
    assert e["failure_reason"] == "boom"
    assert e["retry_count"] == 0
    assert e["max_retries"] == 3


def test_dlq_enqueue_truncates_when_over_max():
    dlq = DeadLetterQueue(max_queue=2, persist_path="")
    for i in range(3):
        dlq.enqueue(_make_event(event_id=f"e-{i}"), reason="boom")
    assert dlq.count() == 2
    assert [e["event_id"] for e in dlq.list()] == ["e-1", "e-2"]


def test_dlq_enqueue_persists_to_disk(tmp_path):
    p = tmp_path / "sub" / "dlq.json"
    dlq = DeadLetterQueue(persist_path=str(p))
    dlq.enqueue(_make_event(), reason="boom")
    assert p.exists()
    data = json.loads(p.read_text())
    assert len(data) == 1
    assert data[0]["event_id"] == "evt-001"


def test_dlq_enqueue_store_insert_called():
    store = _FakeStore()
    dlq = DeadLetterQueue(store=store, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    assert len(store.calls) == 1
    table, entry = store.calls[0]
    assert table == "dead_letter_events"
    assert entry["event_id"] == "evt-001"
    assert entry["retry_count"] == 0
    assert entry["max_retries"] == 3
    assert entry["failure_reason"] == "boom"


def test_dlq_enqueue_store_insert_raises(caplog):
    store = _FakeStore(fail=True)
    dlq = DeadLetterQueue(store=store, persist_path="")
    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        dlq.enqueue(_make_event(), reason="boom")
    assert "persist error" in caplog.text
    assert dlq.count() == 1


def test_dlq_enqueue_disabled_no_persist():
    dlq = DeadLetterQueue(persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    assert dlq.count() == 1
    assert dlq.stats()["persist_exists"] is False


def test_dlq_list_limit():
    dlq = DeadLetterQueue(persist_path="")
    for i in range(5):
        dlq.enqueue(_make_event(event_id=f"e-{i}"), reason="boom")
    assert len(dlq.list()) == 5
    assert len(dlq.list(limit=2)) == 2
    assert [e["event_id"] for e in dlq.list(limit=2)] == ["e-3", "e-4"]


def test_dlq_list_negative_limit():
    dlq = DeadLetterQueue(persist_path="")
    for i in range(5):
        dlq.enqueue(_make_event(event_id=f"e-{i}"), reason="boom")
    # limit=-1 → _queue[-(-1):] == _queue[1:] → 4 条
    assert len(dlq.list(limit=-1)) == 4
    assert dlq.list(limit=-1)[0]["event_id"] == "e-1"


def test_dlq_count():
    dlq = DeadLetterQueue(persist_path="")
    assert dlq.count() == 0
    dlq.enqueue(_make_event(), reason="boom")
    assert dlq.count() == 1


def test_dlq_clear_returns_count():
    dlq = DeadLetterQueue(persist_path="")
    dlq.enqueue(_make_event(event_id="a"), reason="boom")
    dlq.enqueue(_make_event(event_id="b"), reason="boom")
    assert dlq.clear() == 2
    assert dlq.count() == 0


def test_dlq_clear_empty():
    dlq = DeadLetterQueue(persist_path="")
    assert dlq.clear() == 0


# ═══════════════════════════════════════════════════════════════════════
# DeadLetterQueue — retry_all (成功/失败/部分成功/backoff 计数/耗尽)
# ═══════════════════════════════════════════════════════════════════════


def test_dlq_retry_all_empty():
    dlq = DeadLetterQueue(persist_path="")
    assert dlq.retry_all() == (0, 0)


def test_dlq_retry_all_no_callback_survives():
    dlq = DeadLetterQueue(max_retries=3, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    assert dlq.retry_all() == (0, 1)
    assert dlq.count() == 1
    assert dlq.list()[0]["retry_count"] == 1


def test_dlq_retry_all_exhausts_after_max_retries():
    dlq = DeadLetterQueue(max_retries=3, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    for _ in range(2):
        assert dlq.retry_all() == (0, 1)
        assert dlq.count() == 1
    assert dlq.retry_all() == (0, 1)
    assert dlq.count() == 0


def test_dlq_retry_all_exhausted_single_call(caplog):
    dlq = DeadLetterQueue(max_retries=1, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        assert dlq.retry_all() == (0, 1)
    assert dlq.count() == 0
    assert "retry exhausted" in caplog.text


def test_dlq_retry_all_callback_success():
    dlq = DeadLetterQueue(max_retries=3, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")
    calls = []

    def cb(entry):
        calls.append(entry["event_id"])

    assert dlq.retry_all(cb) == (1, 0)
    assert dlq.count() == 0
    assert calls == ["evt-001"]


def test_dlq_retry_all_callback_raises_survives(caplog):
    dlq = DeadLetterQueue(max_retries=3, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")

    def cb(entry):
        raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        assert dlq.retry_all(cb) == (0, 1)
    assert dlq.count() == 1
    assert dlq.list()[0]["retry_count"] == 1
    assert "retry failed" in caplog.text


def test_dlq_retry_all_callback_raises_exhausted(caplog):
    dlq = DeadLetterQueue(max_retries=1, persist_path="")
    dlq.enqueue(_make_event(), reason="boom")

    def cb(entry):
        raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        assert dlq.retry_all(cb) == (0, 1)
    assert dlq.count() == 0
    assert "retry failed" in caplog.text
    assert "retry exhausted" in caplog.text


def test_dlq_retry_all_mixed():
    dlq = DeadLetterQueue(max_retries=3, persist_path="")
    dlq.enqueue(_make_event(event_id="ok"), reason="boom")
    dlq.enqueue(_make_event(event_id="fail"), reason="boom")
    dlq.enqueue(_make_event(event_id="survive"), reason="boom")

    def cb(entry):
        if entry["event_id"] == "ok":
            return
        raise RuntimeError("boom")

    assert dlq.retry_all(cb) == (1, 2)
    assert dlq.count() == 2
    assert [e["event_id"] for e in dlq.list()] == ["fail", "survive"]
    assert all(e["retry_count"] == 1 for e in dlq.list())


def test_dlq_retry_all_persists_survivors(tmp_path):
    p = tmp_path / "dlq.json"
    dlq = DeadLetterQueue(max_retries=3, persist_path=str(p))
    dlq.enqueue(_make_event(), reason="boom")
    assert dlq.retry_all() == (0, 1)
    data = json.loads(p.read_text())
    assert len(data) == 1
    assert data[0]["retry_count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# DeadLetterQueue — 落盘异常 / stats
# ═══════════════════════════════════════════════════════════════════════


def test_dlq_persist_to_disk_error(tmp_path, caplog):
    bad_path = tmp_path / "not_a_file"
    bad_path.mkdir()  # 目录当作文件写 → IsADirectoryError → 日志分支
    dlq = DeadLetterQueue(persist_path=str(bad_path))
    with caplog.at_level(logging.WARNING, logger="yuleosh.loop_engine.event_bus"):
        dlq.enqueue(_make_event(), reason="boom")
    assert "persist to disk error" in caplog.text
    assert dlq.count() == 1


def test_dlq_stats(tmp_path):
    p = tmp_path / "dlq.json"
    dlq = DeadLetterQueue(
        max_retries=2, backoff_factor=3.5, store=_FakeStore(), persist_path=str(p)
    )
    dlq.enqueue(_make_event(), reason="boom")
    st = dlq.stats()
    assert st["count"] == 1
    assert st["max_retries"] == 2
    assert st["backoff_factor"] == 3.5
    assert st["store_configured"] is True
    assert st["persist_path"] == str(p)
    assert st["persist_exists"] is True


def test_dlq_stats_no_store_no_file():
    dlq = DeadLetterQueue(persist_path="")
    st = dlq.stats()
    assert st["count"] == 0
    assert st["store_configured"] is False
    assert st["persist_path"] is None
    assert st["persist_exists"] is False


# ═══════════════════════════════════════════════════════════════════════
# AuditLog — __init__ / record
# ═══════════════════════════════════════════════════════════════════════


def test_audit_init():
    al = AuditLog()
    assert al._store is None
    assert al._max_entries == 5000
    assert al._entries == []
    al2 = AuditLog(store=_FakeStore(), max_entries=7)
    assert al2._max_entries == 7


def test_audit_record_basic():
    al = AuditLog()
    al.record(_make_event())
    entries = al.list()
    assert len(entries) == 1
    e = entries[0]
    assert e["event_id"] == "evt-001"
    assert e["event_type"] == "ci.failure"
    assert e["action"] == "completed"
    assert e["source"] == "ci.runner"
    assert e["source_fingerprint"] == "fp"
    assert e["signature"] == "sig"
    assert e["priority"] == 5
    assert e["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert e["retry_count"] == 2
    assert e["handler_results"] == [{"handler": "hA", "status": "ok"}]
    assert e["rollback_status"] == "none"
    assert e["data_summary"] == '{"test": "brake"}'
    assert e["duration_ms"] > 0
    assert e["recorded_at"] == _FROZEN_NOW


def test_audit_record_explicit_handler_results_and_rollback():
    al = AuditLog()
    al.record(
        _make_event(),
        handler_results=[{"handler": "hB", "status": "ok"}],
        rollback_status="rolled-back",
    )
    e = al.list()[0]
    assert e["handler_results"] == [{"handler": "hB", "status": "ok"}]
    assert e["rollback_status"] == "rolled-back"


def test_audit_record_falsy_args_use_event_fields():
    al = AuditLog()
    ev = _make_event(handler_results=[{"handler": "hA"}], rollback_status="ev-rollback")
    al.record(ev, handler_results=[], rollback_status="")
    e = al.list()[0]
    assert e["handler_results"] == [{"handler": "hA"}]
    assert e["rollback_status"] == "ev-rollback"


def test_audit_record_future_timestamp_zero_duration():
    al = AuditLog()
    al.record(_make_event(timestamp="2099-01-01T00:00:00+00:00"))
    assert al.list()[0]["duration_ms"] == 0.0


def test_audit_record_invalid_timestamp_zero_duration():
    al = AuditLog()
    al.record(_make_event(timestamp="not-a-timestamp"))
    assert al.list()[0]["duration_ms"] == 0.0


def test_audit_record_overflow_truncates():
    al = AuditLog(max_entries=2)
    al.record(_make_event(event_id="a"))
    al.record(_make_event(event_id="b"))
    al.record(_make_event(event_id="c"))
    assert [e["event_id"] for e in al.list()] == ["b", "c"]


def test_audit_record_data_summary_truncated():
    al = AuditLog()
    al.record(_make_event(data={"big": "x" * 600}))
    assert len(al.list()[0]["data_summary"]) == 500


# ═══════════════════════════════════════════════════════════════════════
# AuditLog — list 过滤分支
# ═══════════════════════════════════════════════════════════════════════


def test_audit_list_no_filters():
    al = AuditLog()
    for i in range(3):
        al.record(_make_event(event_id=f"e-{i}"))
    assert len(al.list()) == 3
    assert len(al.list(limit=2)) == 2


def test_audit_list_event_type_filter():
    al = AuditLog()
    al.record(_make_event(event_id="a"))
    al.record(_make_event(event_id="b", event_type=LoopEventType.REVIEW_FINDING))
    assert [e["event_id"] for e in al.list(event_type="ci.failure")] == ["a"]
    assert al.list(event_type="kpi.breach") == []


def test_audit_list_since_until_filter():
    al = AuditLog()
    al.record(_make_event(event_id="jan", timestamp="2026-01-01T00:00:00+00:00"))
    al.record(_make_event(event_id="feb", timestamp="2026-02-01T00:00:00+00:00"))
    al.record(_make_event(event_id="mar", timestamp="2026-03-01T00:00:00+00:00"))
    since = "2026-02-01T00:00:00+00:00"
    until = "2026-02-01T00:00:00+00:00"
    assert [e["event_id"] for e in al.list(since=since)] == ["feb", "mar"]
    assert [e["event_id"] for e in al.list(until=until)] == ["jan", "feb"]
    assert [e["event_id"] for e in al.list(since=since, until=until)] == ["feb"]


def test_audit_list_handler_top_handler_match():
    al = AuditLog()
    al.record_action("config_changed", handler_id="h1")
    al.record_action("config_changed", handler_id="h2")
    assert [e["handler_id"] for e in al.list(handler="h1")] == ["h1"]


def test_audit_list_handler_inner_results_match():
    al = AuditLog()
    al.record(_make_event(event_id="a", handler_results=[{"handler": "hA"}]))
    al.record(_make_event(event_id="b", handler_results=[{"handler": "hB"}]))
    assert [e["event_id"] for e in al.list(handler="hA")] == ["a"]


def test_audit_list_handler_no_match():
    al = AuditLog()
    al.record(_make_event(event_id="a", handler_results=[{"handler": "hA"}]))
    al.record_action("rollback", handler_id="h1")
    assert al.list(handler="zzz") == []


def test_audit_list_handler_empty_results():
    al = AuditLog()
    al.record(_make_event(event_id="a", handler_results=[]))
    assert al.list(handler="hA") == []


def test_audit_list_limit_zero_and_negative():
    al = AuditLog()
    for i in range(3):
        al.record(_make_event(event_id=f"e-{i}"))
    assert len(al.list(limit=0)) == 3  # result[-0:] == 全量
    assert len(al.list(limit=-1)) == 3  # limit < 0 → 不截断


# ═══════════════════════════════════════════════════════════════════════
# AuditLog — query / clear / stats
# ═══════════════════════════════════════════════════════════════════════


def test_audit_query_found_and_not_found():
    al = AuditLog()
    al.record(_make_event(event_id="abc"))
    al.record(_make_event(event_id="xyz"))
    found = al.query("abc")
    assert found is not None
    assert found["event_id"] == "abc"
    assert al.query("nope") is None


def test_audit_query_returns_most_recent_duplicate():
    al = AuditLog()
    al.record(_make_event(event_id="dup", data={"n": 1}))
    al.record(_make_event(event_id="dup", data={"n": 2}))
    found = al.query("dup")
    assert found is not None
    assert found["data_summary"] == '{"n": 2}'


def test_audit_clear():
    al = AuditLog()
    al.record(_make_event())
    al.record(_make_event(event_id="x"))
    al.clear()
    assert al.stats()["total_records"] == 0


def test_audit_stats():
    al = AuditLog(store=_FakeStore(), max_entries=10)
    al.record(_make_event())
    assert al.stats() == {
        "total_records": 1,
        "max_entries": 10,
        "store_configured": True,
    }
    al2 = AuditLog()
    assert al2.stats()["store_configured"] is False
    assert al2.stats()["max_entries"] == 5000


# ═══════════════════════════════════════════════════════════════════════
# AuditLog — record_action / _compute_duration_ms / by_type
# ═══════════════════════════════════════════════════════════════════════


def test_audit_record_action_defaults():
    al = AuditLog()
    al.record_action("config_changed")
    e = al.list()[0]
    assert e["event_type"] == "manual"
    assert e["action"] == "config_changed"
    assert e["source"] == "system"
    assert e["handler_id"] == "system"
    assert e["timestamp"] == _FROZEN_NOW
    assert e["recorded_at"] == _FROZEN_NOW
    assert e["duration_ms"] == 0.0
    assert e["result"] == "success"
    assert e["handler_results"] == [{"handler": "system", "status": "success"}]
    assert e["rollback_status"] == ""
    assert e["data_summary"] == "{}"
    assert e["event_id"]
    assert "journal_id" not in e
    assert "restored_entities" not in e


def test_audit_record_action_full():
    al = AuditLog()
    al.record_action(
        "rollback",
        actor="admin",
        handler_id="h9",
        result="failure",
        details={"k": "v"},
        duration_ms=12.5,
        journal_id="j1",
        restored_entities=["e1", "e2"],
    )
    e = al.list()[0]
    assert e["source"] == "admin"
    assert e["handler_id"] == "h9"
    assert e["result"] == "failure"
    assert e["duration_ms"] == 12.5
    assert e["journal_id"] == "j1"
    assert e["restored_entities"] == ["e1", "e2"]
    assert e["data_summary"] == '{"k": "v"}'
    assert e["handler_results"] == [{"handler": "h9", "status": "failure"}]


def test_audit_record_action_overflow():
    al = AuditLog(max_entries=2)
    al.record_action("a")
    al.record_action("b")
    al.record_action("c")
    assert [e["action"] for e in al.list()] == ["b", "c"]


def test_compute_duration_ms_positive():
    al = AuditLog()
    assert (
        al._compute_duration_ms(
            "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00"
        )
        == 1000.0
    )


def test_compute_duration_ms_negative_clamped():
    al = AuditLog()
    assert (
        al._compute_duration_ms(
            "2026-01-01T00:00:01+00:00", "2026-01-01T00:00:00+00:00"
        )
        == 0.0
    )


def test_compute_duration_ms_invalid():
    al = AuditLog()
    assert al._compute_duration_ms("garbage", "2026-01-01T00:00:00+00:00") == 0.0
    # naive 与 aware 相减抛 TypeError → except 分支
    assert al._compute_duration_ms("2026-01-01T00:00:00", "2026-01-01T00:00:01+00:00") == 0.0


def test_by_type_aggregation():
    al = AuditLog()
    assert al.by_type() == {}
    al.record(_make_event(event_id="a"))
    al.record(_make_event(event_id="b", event_type=LoopEventType.REVIEW_FINDING))
    al.record(_make_event(event_id="c"))
    assert al.by_type() == {"ci.failure": 2, "review.finding": 1}
