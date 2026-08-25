"""Phase 7 E6 — CoalescingGroup + CoalescingManager 全分支覆盖率测试。

目标: src/yuleosh/loop_engine/event_bus.py L1117-1277 全行覆盖。
时间依赖全部 mock (yuleosh.loop_engine.event_bus.time.time) —— 无真实时间/网络/subprocess。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

from unittest.mock import patch

from yuleosh.loop_engine.event_bus import (
    CoalescingGroup,
    CoalescingManager,
    LoopEvent,
    LoopEventType,
)

# event_bus.py 内为模块级 `import time`，因此 patch 模块属性即可拦截 time.time()。
_TIME_PATH = "yuleosh.loop_engine.event_bus.time.time"


def make_event(event_type: LoopEventType, data: dict | None = None) -> LoopEvent:
    """构造最小 LoopEvent。"""
    return LoopEvent(event_type=event_type, source="e6.test", data=data)


# ═══════════════════════════════════════════════════════════════════════
# CoalescingGroup
# ═══════════════════════════════════════════════════════════════════════


def test_group_defaults():
    g = CoalescingGroup()
    assert g.group_key == ""
    assert g.event_type is None
    assert g.events == []
    assert g.window_start == 0.0
    assert g.pending is True


def test_group_add_event_appends():
    ev = make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"})
    g = CoalescingGroup(group_key="R1", event_type=LoopEventType.CI_FAILURE)
    g.add_event(ev)
    assert g.events == [ev]


def test_group_to_dict_with_event_type():
    g = CoalescingGroup(
        group_key="G1",
        event_type=LoopEventType.FIELD_DEFECT,
        window_start=42.5,
        pending=False,
    )
    d = g.to_dict()
    assert d == {
        "group_key": "G1",
        "event_type": "field.defect",
        "event_count": 0,
        "window_start": 42.5,
        "pending": False,
    }


def test_group_to_dict_without_event_type():
    # to_dict 的 `self.event_type.value if self.event_type else ""` 空分支
    g = CoalescingGroup(group_key="G2", window_start=1.0)
    d = g.to_dict()
    assert d["event_type"] == ""
    assert d["event_count"] == 0


def test_group_to_dict_event_count():
    g = CoalescingGroup(group_key="G3", event_type=LoopEventType.TEST_RESULT)
    g.add_event(make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"}))
    g.add_event(make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"}))
    assert g.to_dict()["event_count"] == 2


# ═══════════════════════════════════════════════════════════════════════
# CoalescingManager — __init__ / window 管理
# ═══════════════════════════════════════════════════════════════════════


def test_manager_init():
    mgr = CoalescingManager()
    assert mgr._windows == {}
    assert mgr._groups == {}
    assert mgr._lock is not None


def test_set_window_and_get_window():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    assert mgr.get_window(LoopEventType.CI_FAILURE) == 30.0
    # 未设置类型 → 默认 0.0
    assert mgr.get_window(LoopEventType.TEST_RESULT) == 0.0


def test_set_window_overwrites():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    mgr.set_window(LoopEventType.CI_FAILURE, 5.0)
    assert mgr.get_window(LoopEventType.CI_FAILURE) == 5.0


def test_remove_window():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    mgr.remove_window(LoopEventType.CI_FAILURE)
    assert mgr.get_window(LoopEventType.CI_FAILURE) == 0.0
    # 移除不存在的类型不报错
    mgr.remove_window(LoopEventType.FIELD_DEFECT)


# ═══════════════════════════════════════════════════════════════════════
# CoalescingManager — get_group_key
# ═══════════════════════════════════════════════════════════════════════


def test_group_key_ci_failure_req_id():
    mgr = CoalescingManager()
    assert mgr.get_group_key(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"})) == "R1"


def test_group_key_ci_failure_requirement_id_fallback():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.CI_FAILURE, {"requirement_id": "R2"})
    assert mgr.get_group_key(ev) == "R2"


def test_group_key_ci_failure_none():
    mgr = CoalescingManager()
    assert mgr.get_group_key(make_event(LoopEventType.CI_FAILURE, {"x": 1})) is None


def test_group_key_ci_failure_none_data():
    # `event.data or {}` 的 falsy 分支
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.CI_FAILURE, {})
    ev.data = None  # type: ignore[assignment]
    assert mgr.get_group_key(ev) is None


def test_group_key_test_result_entity_id():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"})
    assert mgr.get_group_key(ev) == "E1"


def test_group_key_test_result_edge_id_fallback():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.TEST_RESULT, {"edge_id": "ED1"})
    assert mgr.get_group_key(ev) == "ED1"


def test_group_key_test_result_no_ids():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.TEST_RESULT, {"other": 1})
    assert mgr.get_group_key(ev) is None


def test_group_key_kg_low_confidence_entity_id():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.KG_LOW_CONFIDENCE, {"entity_id": "E2"})
    assert mgr.get_group_key(ev) == "E2"


def test_group_key_kg_low_confidence_edge_id_fallback():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.KG_LOW_CONFIDENCE, {"edge_id": "ED2"})
    assert mgr.get_group_key(ev) == "ED2"


def test_group_key_field_defect_swc():
    mgr = CoalescingManager()
    ev = make_event(LoopEventType.FIELD_DEFECT, {"swc": "SWC-1"})
    assert mgr.get_group_key(ev) == "SWC-1"


def test_group_key_field_defect_missing_swc():
    mgr = CoalescingManager()
    assert mgr.get_group_key(make_event(LoopEventType.FIELD_DEFECT, {})) is None


def test_group_key_other_type_returns_none():
    mgr = CoalescingManager()
    assert mgr.get_group_key(make_event(LoopEventType.SPEC_CHANGE, {"req_id": "R1"})) is None


# ═══════════════════════════════════════════════════════════════════════
# CoalescingManager — add_event
# ═══════════════════════════════════════════════════════════════════════


def test_add_event_no_derived_key_returns_none_true():
    mgr = CoalescingManager()
    # SPEC_CHANGE 无法派生 key → (None, True)，不建组
    key, ready = mgr.add_event(make_event(LoopEventType.SPEC_CHANGE, {"req_id": "R1"}))
    assert key is None
    assert ready is True
    assert mgr._groups == {}


def test_add_event_explicit_key_derives_when_none():
    # group_key=None 时通过 get_group_key 派生 (CI_FAILURE → req_id)
    mgr = CoalescingManager()
    key, _ = mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}))
    assert key == "R1"


def test_add_event_no_window_returns_ready_without_group():
    # 未设置窗口 (0.0) → window <= 0 → 直接 ready，不建组
    mgr = CoalescingManager()
    key, ready = mgr.add_event(
        make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1"
    )
    assert key == "R1"
    assert ready is True
    assert mgr._groups == {}


def test_add_event_zero_window_returns_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 0.0)
    key, ready = mgr.add_event(
        make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1"
    )
    assert (key, ready) == ("R1", True)
    assert mgr._groups == {}


def test_add_event_creates_new_group_not_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        key, ready = mgr.add_event(
            make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1"
        )
    assert key == "R1"
    assert ready is False
    group = mgr._groups["R1"]
    assert group.group_key == "R1"
    assert group.event_type == LoopEventType.CI_FAILURE
    assert group.window_start == 100.0
    assert len(group.events) == 1


def test_add_event_existing_group_appends_and_not_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    with patch(_TIME_PATH, side_effect=[101.0]):
        key, ready = mgr.add_event(
            make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1"
        )
    assert key == "R1"
    assert ready is False
    assert len(mgr._groups["R1"].events) == 2
    assert mgr._groups["R1"].window_start == 100.0  # 复用组不重置窗口


def test_add_event_window_elapsed_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    # t=131 → elapsed=31 >= 30 → ready
    with patch(_TIME_PATH, side_effect=[131.0]):
        key, ready = mgr.add_event(
            make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1"
        )
    assert (key, ready) == ("R1", True)


def test_add_event_window_boundary_elapsed_equal_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.TEST_RESULT, 30.0)
    with patch(_TIME_PATH, side_effect=[200.0, 200.5]):
        mgr.add_event(make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"}), group_key="E1")
    # t=230 → elapsed=30 == window → ready (>= 边界)
    with patch(_TIME_PATH, side_effect=[230.0]):
        key, ready = mgr.add_event(
            make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"}), group_key="E1"
        )
    assert (key, ready) == ("E1", True)


# ═══════════════════════════════════════════════════════════════════════
# CoalescingManager — flush / flush_by_event_type / cancel / clear / 查询
# ═══════════════════════════════════════════════════════════════════════


def test_flush_existing_group():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    group = mgr.flush("R1")
    assert group is not None
    assert group.group_key == "R1"
    assert mgr._groups == {}


def test_flush_missing_group_returns_none():
    mgr = CoalescingManager()
    assert mgr.flush("nope") is None


def test_flush_by_event_type_filters_removes_ready():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    mgr.set_window(LoopEventType.TEST_RESULT, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.TEST_RESULT, {"entity_id": "E1"}), group_key="E1")
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R3"}), group_key="R3")
    # t=131: 两个 CI 组过期 → 返回并删除；TEST_RESULT 组因类型不匹配被跳过
    with patch(_TIME_PATH, side_effect=[131.0, 131.0]):
        ready = mgr.flush_by_event_type(LoopEventType.CI_FAILURE)
    assert {g.group_key for g in ready} == {"R1", "R3"}
    assert set(mgr._groups.keys()) == {"E1"}


def test_flush_by_event_type_not_ready_keeps_group():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    # t=110 → elapsed=10 < 30 → 不 ready
    with patch(_TIME_PATH, side_effect=[110.0]):
        ready = mgr.flush_by_event_type(LoopEventType.CI_FAILURE)
    assert ready == []
    assert "R1" in mgr._groups


def test_flush_by_event_type_zero_window_flushes_all():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    # 窗口改为 0 → elapsed >= 0 恒成立 → 立即 flush
    mgr.set_window(LoopEventType.CI_FAILURE, 0.0)
    with patch(_TIME_PATH, return_value=200.0):
        ready = mgr.flush_by_event_type(LoopEventType.CI_FAILURE)
    assert [g.group_key for g in ready] == ["R1"]
    assert mgr._groups == {}


def test_flush_by_event_type_empty_when_none_match():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    with patch(_TIME_PATH, return_value=500.0):
        ready = mgr.flush_by_event_type(LoopEventType.FIELD_DEFECT)
    assert ready == []
    assert "R1" in mgr._groups


def test_cancel_group():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    mgr.cancel_group("R1")
    assert mgr._groups == {}
    # 取消不存在的组不报错
    mgr.cancel_group("ghost")


def test_clear():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R2"}), group_key="R2")
    assert len(mgr._groups) == 2
    mgr.clear()
    assert mgr._groups == {}


def test_active_groups():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    groups = mgr.active_groups()
    assert set(groups.keys()) == {"R1"}
    assert groups["R1"]["group_key"] == "R1"
    assert groups["R1"]["event_type"] == "ci.failure"
    assert groups["R1"]["pending"] is True
    assert groups["R1"]["window_start"] == 100.0
    assert groups["R1"]["event_count"] == 1


def test_stats():
    mgr = CoalescingManager()
    mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
    mgr.set_window(LoopEventType.FIELD_DEFECT, 60.0)
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        mgr.add_event(make_event(LoopEventType.CI_FAILURE, {"req_id": "R1"}), group_key="R1")
    stats = mgr.stats()
    assert stats["active_groups"] == 1
    assert stats["windows"] == {"ci.failure": 30.0, "field.defect": 60.0}
    assert set(stats["groups"].keys()) == {"R1"}


def test_stats_empty():
    mgr = CoalescingManager()
    stats = mgr.stats()
    assert stats["active_groups"] == 0
    assert stats["windows"] == {}
    assert stats["groups"] == {}
