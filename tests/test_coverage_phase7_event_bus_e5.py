"""Phase 7 E5 — _default_persistence_path + EventQueuePersistence 全分支覆盖率测试。

目标: src/yuleosh/loop_engine/event_bus.py L920-1109
  - _default_persistence_path (L920-935): OSH_HOME 优先 / tempfile 隔离回退
  - EventQueuePersistence (L938-1109): 磁盘 JSON 持久化 + 崩溃恢复全分支

策略: pytest tmp_path 真实文件系统 (save_event 落盘、mark_processed 更新
processed ids、recover_unconsumed 模拟崩溃窗口), 无真实时间/网络/subprocess
依赖 (事件 timestamp 全部显式传入)。仅允许新建本测试文件, 零 src/ 改动。
"""

import json
import logging
import os
from unittest.mock import patch

from yuleosh.loop_engine.event_bus import (
    EventQueuePersistence,
    LoopEvent,
    LoopEventType,
    _default_persistence_path,
)

_LOGGER = "yuleosh.loop_engine.event_bus"


def _make_event(event_id: str, timestamp: str, retry_count: int = 0) -> LoopEvent:
    """构造一个字段完全确定的 LoopEvent (无真实时间依赖)。"""
    return LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source="ci.runner",
        data={"n": 1},
        event_id=event_id,
        timestamp=timestamp,
        retry_count=retry_count,
    )


def _pending_ids(tmp_path) -> list:
    return [
        e["event_id"]
        for e in json.loads((tmp_path / "pending_events.json").read_text())
    ]


# ── _default_persistence_path ───────────────────────────────────────────


def test_default_persistence_path_uses_osh_home():
    # OSH_HOME 分支: 显式指定的 home 优先
    with patch.dict(os.environ, {"OSH_HOME": "/tmp/fake-osh"}):
        path = _default_persistence_path()
    assert path == "/tmp/fake-osh/.yuleosh/loop"


def test_default_persistence_path_falls_back_to_tempdir():
    # 回退分支: OSH_HOME 为空 → tempfile 隔离目录 (带 uid)
    with (
        patch.dict(os.environ, {"OSH_HOME": ""}),
        patch("yuleosh.loop_engine.event_bus.os.getuid", return_value=4242),
        patch("tempfile.gettempdir", return_value="/tmp/yuleosh-tmp"),
    ):
        path = _default_persistence_path()
    assert path == "/tmp/yuleosh-tmp/yuleosh-loop-4242"


# ── __init__ / base_path ────────────────────────────────────────────────


def test_init_default_base_path_uses_helper(tmp_path):
    target = str(tmp_path / "default-loop")
    with patch(
        "yuleosh.loop_engine.event_bus._default_persistence_path",
        return_value=target,
    ):
        p = EventQueuePersistence()
    assert p.base_path == target
    assert os.path.isdir(target)


def test_init_explicit_base_path_creates_dir(tmp_path):
    base = tmp_path / "loop-store"
    p = EventQueuePersistence(str(base))
    assert p.base_path == str(base)
    assert base.is_dir()
    assert not (base / "pending_events.json").exists()
    assert not (base / "processed_events.json").exists()


# ── save_event ──────────────────────────────────────────────────────────


def test_save_event_persists_to_disk(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    p.save_event(_make_event("ev-1", "2026-08-10T00:00:00+00:00"))
    assert _pending_ids(tmp_path) == ["ev-1"]
    assert p.pending_count() == 1


def test_save_event_duplicate_skipped(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    ev = _make_event("dup-1", "2026-08-10T00:00:00+00:00")
    p.save_event(ev)
    p.save_event(ev)  # existing_ids 分支 → 直接 return
    assert _pending_ids(tmp_path) == ["dup-1"]


def test_save_event_already_processed_skipped(tmp_path, caplog):
    p = EventQueuePersistence(str(tmp_path))
    p.mark_processed("proc-1")
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        p.save_event(_make_event("proc-1", "2026-08-10T00:00:00+00:00"))
    assert "already processed" in caplog.text
    assert _pending_ids(tmp_path) == []


# ── mark_processed / mark_batch_processed ───────────────────────────────


def test_mark_processed_removes_from_pending_and_saves(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    p.save_event(_make_event("m-1", "2026-08-10T00:00:00+00:00"))
    p.save_event(_make_event("m-2", "2026-08-10T00:00:01+00:00"))
    p.mark_processed("m-1")
    assert p.pending_count() == 1
    assert _pending_ids(tmp_path) == ["m-2"]
    processed = json.loads((tmp_path / "processed_events.json").read_text())
    assert "m-1" in processed


def test_mark_batch_processed_removes_multiple(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    for i in range(3):
        p.save_event(_make_event(f"b-{i}", f"2026-08-10T00:00:0{i}+00:00"))
    p.mark_batch_processed(["b-0", "b-2"])
    assert p.pending_count() == 1
    assert _pending_ids(tmp_path) == ["b-1"]


def test_mark_batch_processed_empty(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    p.save_event(_make_event("b-only", "2026-08-10T00:00:00+00:00"))
    p.mark_batch_processed([])  # 空列表 → 循环零次, ids_set 为空
    assert p.pending_count() == 1
    assert _pending_ids(tmp_path) == ["b-only"]


# ── recover_unconsumed (崩溃恢复) ───────────────────────────────────────


def test_recover_unconsumed_crash_window_sorted_skip_processed(tmp_path):
    # 模拟崩溃窗口: processed_events.json 已落盘但 pending 未清理,
    # 且 pending 文件顺序乱序 → 恢复时必须跳过已处理并按 timestamp 排序。
    ev1 = _make_event("r-1", "2026-08-10T00:00:02+00:00")
    ev2 = _make_event("r-2", "2026-08-10T00:00:01+00:00")
    ev3 = _make_event("r-3", "2026-08-10T00:00:03+00:00", retry_count=5)
    (tmp_path / "processed_events.json").write_text(json.dumps(["r-2"]))
    (tmp_path / "pending_events.json").write_text(
        json.dumps([ev3.to_dict(), ev2.to_dict(), ev1.to_dict()])
    )
    p = EventQueuePersistence(str(tmp_path))
    recovered = p.recover_unconsumed()
    assert [e.event_id for e in recovered] == ["r-1", "r-3"]  # 排序 + 跳过 r-2
    assert all(e.retry_count == 0 for e in recovered)  # retry_count 重置
    # 已处理的 r-2 被从磁盘清除 (remaining 保持遍历顺序, 非排序后顺序)
    assert set(_pending_ids(tmp_path)) == {"r-1", "r-3"}


def test_recover_unconsumed_no_pending(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    assert p.recover_unconsumed() == []


def test_recover_unconsumed_skips_invalid_and_missing_id(tmp_path, caplog):
    (tmp_path / "pending_events.json").write_text(
        json.dumps(
            [
                {"event_id": "bad-1"},  # 缺 event_type → from_dict KeyError
                {  # 无 event_id → eid="" → 正常恢复 (自动生成 id)
                    "event_type": "ci.failure",
                    "timestamp": "2026-08-10T00:00:00+00:00",
                },
                {
                    "event_id": "ok-1",
                    "event_type": "ci.failure",
                    "timestamp": "2026-08-10T00:00:01+00:00",
                },
            ]
        )
    )
    p = EventQueuePersistence(str(tmp_path))
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        recovered = p.recover_unconsumed()
    assert "skip invalid event bad-1" in caplog.text
    assert len(recovered) == 2
    assert recovered[0].timestamp == "2026-08-10T00:00:00+00:00"  # 排序
    assert [e.event_id for e in recovered][1] == "ok-1"
    # 非法条目被丢弃; 无 event_id 的原始 dict 原样保留 (无 event_id 键)
    remaining = json.loads((tmp_path / "pending_events.json").read_text())
    assert [e.get("event_id") for e in remaining] == [None, "ok-1"]


def test_crash_recovery_new_instance(tmp_path):
    p1 = EventQueuePersistence(str(tmp_path))
    p1.save_event(_make_event("cr-1", "2026-08-10T00:00:00+00:00"))
    p1.save_event(_make_event("cr-2", "2026-08-10T00:00:01+00:00"))
    p1.mark_processed("cr-1")
    p2 = EventQueuePersistence(str(tmp_path))  # 模拟进程重启
    assert p2._processed_ids == {"cr-1"}
    recovered = p2.recover_unconsumed()
    assert [e.event_id for e in recovered] == ["cr-2"]


# ── has_pending / pending_count ─────────────────────────────────────────


def test_has_pending_true_false(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    assert p.has_pending() is False  # 空 pending
    p.save_event(_make_event("h-1", "2026-08-10T00:00:00+00:00"))
    assert p.has_pending() is True
    p.mark_processed("h-1")
    assert p.has_pending() is False  # 文件已清空


def test_has_pending_false_all_processed(tmp_path):
    # pending 有条目但全部已处理 → 循环走完 return False
    (tmp_path / "pending_events.json").write_text(
        json.dumps([{"event_id": "x-1", "event_type": "ci.failure"}])
    )
    (tmp_path / "processed_events.json").write_text(json.dumps(["x-1"]))
    p = EventQueuePersistence(str(tmp_path))
    assert p.has_pending() is False


def test_pending_count_mixed(tmp_path):
    (tmp_path / "pending_events.json").write_text(
        json.dumps(
            [
                {"event_id": "c-1", "event_type": "ci.failure"},
                {"event_id": "c-2", "event_type": "ci.failure"},
                {"event_id": "c-3", "event_type": "ci.failure"},
            ]
        )
    )
    (tmp_path / "processed_events.json").write_text(json.dumps(["c-2"]))
    p = EventQueuePersistence(str(tmp_path))
    assert p.pending_count() == 2
    p2 = EventQueuePersistence(str(tmp_path / "empty"))
    assert p2.pending_count() == 0


# ── clear / stats ───────────────────────────────────────────────────────


def test_clear_resets_all(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    p.save_event(_make_event("cl-1", "2026-08-10T00:00:00+00:00"))
    p.mark_processed("cl-1")
    assert p.pending_count() == 0
    p.clear()
    assert p._processed_ids == set()
    assert _pending_ids(tmp_path) == []
    assert json.loads((tmp_path / "processed_events.json").read_text()) == []
    assert p.pending_count() == 0


def test_stats(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    p.save_event(_make_event("s-1", "2026-08-10T00:00:00+00:00"))
    p.save_event(_make_event("s-2", "2026-08-10T00:00:01+00:00"))
    p.mark_processed("s-1")
    st = p.stats()
    assert st["base_path"] == str(tmp_path)
    assert st["pending_count"] == 1
    assert st["unconsumed_count"] == 1
    assert st["processed_ids_count"] == 1


# ── _load_pending ───────────────────────────────────────────────────────


def test_load_pending_corrupted_json(tmp_path, caplog):
    (tmp_path / "pending_events.json").write_text("{not json")
    p = EventQueuePersistence(str(tmp_path))
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert p._load_pending() == []
    assert "load pending error" in caplog.text


def test_load_pending_not_a_list(tmp_path):
    (tmp_path / "pending_events.json").write_text('{"a": 1}')
    p = EventQueuePersistence(str(tmp_path))
    assert p._load_pending() == []


def test_load_pending_missing_file(tmp_path):
    p = EventQueuePersistence(str(tmp_path))
    assert p._load_pending() == []


def test_save_pending_oserror(tmp_path, caplog):
    # pending_events.json 被目录占位 → open 抛 IsADirectoryError (OSError)
    base = tmp_path / "store"
    (base / "pending_events.json").mkdir(parents=True)
    p = EventQueuePersistence(str(base))
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        p.save_event(_make_event("os-1", "2026-08-10T00:00:00+00:00"))
    assert "load pending error" in caplog.text
    assert "save pending error" in caplog.text


# ── _load_processed_ids / _save_processed_ids ───────────────────────────


def test_load_processed_ids_valid(tmp_path):
    (tmp_path / "processed_events.json").write_text(json.dumps(["a", "b"]))
    p = EventQueuePersistence(str(tmp_path))
    assert p._processed_ids == {"a", "b"}


def test_load_processed_ids_corrupted(tmp_path, caplog):
    (tmp_path / "processed_events.json").write_text("[1, 2")
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        p = EventQueuePersistence(str(tmp_path))
    assert p._processed_ids == set()
    assert "load processed ids error" in caplog.text


def test_load_processed_ids_not_a_list(tmp_path):
    (tmp_path / "processed_events.json").write_text('{"x": 1}')
    p = EventQueuePersistence(str(tmp_path))
    assert p._processed_ids == set()


def test_save_processed_ids_oserror(tmp_path, caplog):
    # processed_events.json 被目录占位 → 读写均抛 IsADirectoryError (OSError)
    base = tmp_path / "store2"
    (base / "processed_events.json").mkdir(parents=True)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        p = EventQueuePersistence(str(base))
        assert p._processed_ids == set()
        p.mark_processed("p-1")
    assert "load processed ids error" in caplog.text
    assert "save processed ids error" in caplog.text
