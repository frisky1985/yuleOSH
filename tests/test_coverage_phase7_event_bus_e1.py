"""Phase 7 coverage boost — event_bus.py E1 目标组。

Target (src/yuleosh/loop_engine/event_bus.py):
  - _get_chain_classes (L68-75)
  - LoopEventType       (L82-136, 枚举)
  - LoopEvent           (L144-224: __post_init__/to_dict/from_dict/__repr__)
  - Subscription        (L232-245)

策略:
  - 数据模型类直接实例化，覆盖各字段默认值 / 显式值 / 序列化往返；
  - from_dict 覆盖缺键默认值、多余键忽略、非法 event_type 抛 ValueError；
  - _get_chain_classes 首调走真实 import（chain.py 无副作用），
    二次调用验证缓存分支（patch sys.modules 证明不再 import）；
  - 无网络 / 时间依赖（时间戳断言只验格式与存在性），无 multiprocessing。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

import sys
import uuid
from datetime import UTC, datetime
from unittest import mock

import pytest

from yuleosh.loop_engine import event_bus
from yuleosh.loop_engine.chain import ChainConfig, ChainContext
from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType, Subscription

# ═══════════════════════════════════════════════════════════════════════
# _get_chain_classes (L68-75)
# ═══════════════════════════════════════════════════════════════════════


def _reset_chain_globals():
    event_bus._ChainConfig = None
    event_bus._ChainContext = None


def test_get_chain_classes_first_call_imports_real_classes():
    """首次调用（全局为 None）→ 真实 import chain.ChainConfig/ChainContext。"""
    _reset_chain_globals()
    try:
        cfg, ctx = event_bus._get_chain_classes()
        assert cfg is ChainConfig
        assert ctx is ChainContext
        # 全局缓存已写入
        assert event_bus._ChainConfig is ChainConfig
        assert event_bus._ChainContext is ChainContext
    finally:
        _reset_chain_globals()


def test_get_chain_classes_cached_skips_import():
    """全局已缓存 → 直接返回缓存，不再执行 import。"""
    sentinel_cfg = object()
    sentinel_ctx = object()
    event_bus._ChainConfig = sentinel_cfg
    event_bus._ChainContext = sentinel_ctx
    # 从 sys.modules 移除 chain 并阻止再次导入：若走 import 分支会抛错。
    saved = sys.modules.pop("yuleosh.loop_engine.chain", None)
    try:
        cfg, ctx = event_bus._get_chain_classes()
        assert cfg is sentinel_cfg
        assert ctx is sentinel_ctx
        assert "yuleosh.loop_engine.chain" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["yuleosh.loop_engine.chain"] = saved
        event_bus._ChainConfig = None
        event_bus._ChainContext = None


def test_get_chain_classes_memoized_returns_same_objects():
    """连续调用返回同一对象（幂等）。"""
    _reset_chain_globals()
    try:
        first = event_bus._get_chain_classes()
        second = event_bus._get_chain_classes()
        assert first == second
        assert first[0] is second[0]
        assert first[1] is second[1]
    finally:
        _reset_chain_globals()


# ═══════════════════════════════════════════════════════════════════════
# LoopEventType (L82-136)
# ═══════════════════════════════════════════════════════════════════════

EXPECTED_MEMBERS = {
    "CI_FAILURE": "ci.failure",
    "REVIEW_FINDING": "review.finding",
    "KPI_BREACH": "kpi.breach",
    "FIELD_DEFECT": "field.defect",
    "KG_LOW_CONFIDENCE": "kg.low_confidence",
    "TEST_RESULT": "test.result",
    "SPEC_CHANGE": "spec.change",
    "LOOP1_DONE": "loop1.done",
    "LOOP2_DONE": "loop2.done",
    "LOOP3_DONE": "loop3.done",
    "LOOP4_CONFIDENCE_UP": "loop4.confidence_up",
    "LESSON_CREATE": "lesson_create",
    "MEMORY_REMEMBER": "memory_remember",
    "KB_ARTICLE_CREATED": "kb_article_created",
    "SKILL_CREATED": "skill_created",
    "KG_EDGE_MERGED": "kg_edge_merged",
}


def test_loop_event_type_members_and_values():
    """全部 16 个成员及值。"""
    assert {m.name: m.value for m in LoopEventType} == EXPECTED_MEMBERS


def test_loop_event_type_is_str_enum():
    """str mixin：成员可当字符串比较/使用。"""
    assert isinstance(LoopEventType.CI_FAILURE, str)
    assert LoopEventType.CI_FAILURE == "ci.failure"
    assert LoopEventType.LESSON_CREATE == "lesson_create"


def test_loop_event_type_lookup_by_value():
    """按值反查成员。"""
    assert LoopEventType("ci.failure") is LoopEventType.CI_FAILURE
    assert LoopEventType("kg_edge_merged") is LoopEventType.KG_EDGE_MERGED
    assert LoopEventType("loop4.confidence_up") is LoopEventType.LOOP4_CONFIDENCE_UP


def test_loop_event_type_invalid_value_raises_value_error():
    """非法值 → ValueError。"""
    with pytest.raises(ValueError):
        LoopEventType("no.such.event")


def test_loop_event_type_iteration_and_str():
    """迭代顺序与 str() 表现（str mixin 枚举的默认 repr 风格）。"""
    names = [m.name for m in LoopEventType]
    assert names[0] == "CI_FAILURE"
    assert names[-1] == "KG_EDGE_MERGED"
    assert "LoopEventType.CI_FAILURE" in str(LoopEventType.CI_FAILURE)


# ═══════════════════════════════════════════════════════════════════════
# LoopEvent (L144-224)
# ═══════════════════════════════════════════════════════════════════════


def _iso_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def test_loop_event_defaults_post_init():
    """默认字段：event_id/timestamp/dedup_key 自动生成。"""
    ev = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    assert isinstance(ev.event_id, str)
    assert len(ev.event_id) > 0
    assert ev.source == "system"
    assert ev.data == {}
    assert ev.priority == 5
    assert ev.retry_count == 0
    assert ev.max_retries == 3
    assert ev.source_fingerprint == ""
    assert ev.signature == ""
    assert ev.handler_results == []
    assert ev.rollback_status == ""
    # timestamp 为 ISO 格式
    datetime.fromisoformat(ev.timestamp)
    # dedup_key 自动生成且为 16 位 hex
    assert isinstance(ev.dedup_key, str)
    assert len(ev.dedup_key) == 16
    int(ev.dedup_key, 16)


def test_loop_event_auto_ids_unique():
    """event_id 唯一；同载荷 dedup_key 相同（去重语义）。"""
    a = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    b = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    assert a.event_id != b.event_id
    # 去重键由类型+数据决定，相同载荷 → 相同 key（正是去重用途）
    assert a.dedup_key == b.dedup_key


def test_loop_event_dedup_key_deterministic_and_data_sensitive():
    """同类型同数据 → 相同 dedup_key；数据不同 → 不同。"""
    e1 = LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        data={"name": "x", "ok": True},
    )
    e2 = LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        data={"name": "x", "ok": True},
    )
    e3 = LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        data={"name": "x", "ok": False},
    )
    assert e1.dedup_key == e2.dedup_key
    assert e1.dedup_key != e3.dedup_key
    # 键顺序无关（json sort_keys=True）
    e4 = LoopEvent(
        event_type=LoopEventType.TEST_RESULT,
        data={"ok": True, "name": "x"},
    )
    assert e1.dedup_key == e4.dedup_key


def test_loop_event_explicit_fields_kept():
    """显式传入的字段不被 __post_init__ 覆盖。"""
    fixed_id = str(uuid.uuid4())
    fixed_ts = _iso_timestamp()
    ev = LoopEvent(
        event_type=LoopEventType.REVIEW_FINDING,
        source="review.bot",
        data={"file": "a.py"},
        priority=1,
        dedup_key="my-key",
        event_id=fixed_id,
        timestamp=fixed_ts,
        retry_count=2,
        max_retries=5,
        source_fingerprint="fp",
        signature="sig",
        handler_results=[{"ok": True}],
        rollback_status="rolled-back",
    )
    assert ev.event_id == fixed_id
    assert ev.timestamp == fixed_ts
    assert ev.dedup_key == "my-key"
    assert ev.source == "review.bot"
    assert ev.data == {"file": "a.py"}
    assert ev.priority == 1
    assert ev.retry_count == 2
    assert ev.max_retries == 5
    assert ev.source_fingerprint == "fp"
    assert ev.signature == "sig"
    assert ev.handler_results == [{"ok": True}]
    assert ev.rollback_status == "rolled-back"


def test_loop_event_to_dict_full():
    """to_dict 序列化全部字段，event_type 转成 .value。"""
    fixed_id = str(uuid.uuid4())
    fixed_ts = _iso_timestamp()
    ev = LoopEvent(
        event_type=LoopEventType.KPI_BREACH,
        source="kpi.monitor",
        data={"metric": "cpu"},
        priority=0,
        dedup_key="dk",
        event_id=fixed_id,
        timestamp=fixed_ts,
        retry_count=1,
        max_retries=4,
        source_fingerprint="fp",
        signature="sig",
        handler_results=[{"h": 1}],
        rollback_status="none",
    )
    assert ev.to_dict() == {
        "event_id": fixed_id,
        "event_type": "kpi.breach",
        "source": "kpi.monitor",
        "data": {"metric": "cpu"},
        "priority": 0,
        "dedup_key": "dk",
        "timestamp": fixed_ts,
        "retry_count": 1,
        "max_retries": 4,
        "source_fingerprint": "fp",
        "signature": "sig",
        "handler_results": [{"h": 1}],
        "rollback_status": "none",
    }


def test_loop_event_from_dict_roundtrip():
    """to_dict → from_dict 往返等价（含显式值全部保留）。"""
    fixed_id = str(uuid.uuid4())
    fixed_ts = _iso_timestamp()
    ev = LoopEvent(
        event_type=LoopEventType.SPEC_CHANGE,
        source="spec.watch",
        data={"doc": "d1"},
        priority=2,
        dedup_key="dk-rt",
        event_id=fixed_id,
        timestamp=fixed_ts,
        retry_count=3,
        max_retries=7,
        source_fingerprint="fp",
        signature="sig",
        handler_results=[{"a": 1}],
        rollback_status="ok",
    )
    restored = LoopEvent.from_dict(ev.to_dict())
    assert restored == ev
    assert restored.to_dict() == ev.to_dict()


def test_loop_event_from_dict_minimal_uses_defaults():
    """缺键 → 默认值（source/data/priority/retry/max_retries 等）。"""
    ev = LoopEvent.from_dict({"event_type": "field.defect"})
    assert ev.event_type is LoopEventType.FIELD_DEFECT
    assert ev.source == "system"
    assert ev.data == {}
    assert ev.priority == 5
    assert ev.retry_count == 0
    assert ev.max_retries == 3
    assert ev.source_fingerprint == ""
    assert ev.signature == ""
    assert ev.handler_results == []
    assert ev.rollback_status == ""
    # 缺 event_id/timestamp/dedup_key → __post_init__ 自动补
    assert ev.event_id != ""
    assert ev.timestamp != ""
    assert ev.dedup_key is not None


def test_loop_event_from_dict_partial_keys():
    """部分键提供 → 仅覆盖提供的键。"""
    fixed_id = str(uuid.uuid4())
    ev = LoopEvent.from_dict(
        {
            "event_type": "test.result",
            "source": "ci",
            "priority": 9,
            "event_id": fixed_id,
            "dedup_key": "keep-me",
        }
    )
    assert ev.source == "ci"
    assert ev.priority == 9
    assert ev.event_id == fixed_id
    assert ev.dedup_key == "keep-me"
    assert ev.data == {}
    assert ev.max_retries == 3


def test_loop_event_from_dict_ignores_extra_keys():
    """多余键被忽略，不影响结果。"""
    d = {
        "event_type": "memory_remember",
        "source": "mem",
        "extra_unknown": 123,
        "nested": {"x": 1},
    }
    ev = LoopEvent.from_dict(d)
    assert ev.event_type is LoopEventType.MEMORY_REMEMBER
    assert ev.source == "mem"
    assert not hasattr(ev, "extra_unknown")


def test_loop_event_from_dict_invalid_type_raises():
    """非法 event_type 值 → ValueError。"""
    with pytest.raises(ValueError):
        LoopEvent.from_dict({"event_type": "bogus.type"})


def test_loop_event_repr_format():
    """__repr__ 包含类型值 / id 前 8 位 / priority / retry。"""
    ev = LoopEvent(
        event_type=LoopEventType.LOOP2_DONE,
        event_id="1234567890abcdef",
        priority=3,
        retry_count=2,
    )
    assert repr(ev) == "<LoopEvent loop2.done id=12345678 prio=3 retry=2>"


# ═══════════════════════════════════════════════════════════════════════
# Subscription (L232-245)
# ═══════════════════════════════════════════════════════════════════════


def _handler(ev):
    return "handled"


def test_subscription_defaults_post_init():
    """传 id=""（必填字段）→ __post_init__ 自动生成；过滤字段取默认。"""
    sub = Subscription(id="", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    assert isinstance(sub.id, str)
    assert len(sub.id) > 0
    assert sub.event_type is LoopEventType.CI_FAILURE
    assert sub.callback is _handler
    assert sub.priority_filter is None
    assert sub.one_shot is False
    datetime.fromisoformat(sub.created_at)


def test_subscription_explicit_fields_kept():
    """显式 id/created_at/priority_filter/one_shot 保留。"""
    fixed_id = str(uuid.uuid4())
    fixed_ts = _iso_timestamp()
    sub = Subscription(
        id=fixed_id,
        event_type=LoopEventType.KG_LOW_CONFIDENCE,
        callback=_handler,
        priority_filter=2,
        one_shot=True,
        created_at=fixed_ts,
    )
    assert sub.id == fixed_id
    assert sub.created_at == fixed_ts
    assert sub.priority_filter == 2
    assert sub.one_shot is True
    assert sub.event_type is LoopEventType.KG_LOW_CONFIDENCE


def test_subscription_ids_unique():
    """两个缺省 id 的订阅 id 唯一。"""
    a = Subscription(id="", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    b = Subscription(id="", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    assert a.id != b.id


def test_subscription_callback_invokable():
    """callback 字段可调用（数据类仅存储，不做过滤逻辑）。"""
    sub = Subscription(id="sub-1", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    ev = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    assert sub.callback(ev) == "handled"


def test_subscription_repr_fields_accessible():
    """dataclass 生成字段访问与相等性。"""
    sub1 = Subscription(id="", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    sub2 = Subscription(
        id=sub1.id,
        event_type=sub1.event_type,
        callback=sub1.callback,
        priority_filter=sub1.priority_filter,
        one_shot=sub1.one_shot,
        created_at=sub1.created_at,
    )
    assert sub1 == sub2
    assert "Subscription" in repr(sub1)


# ═══════════════════════════════════════════════════════════════════════
# mock 辅助验证（无真实时间依赖）
# ═══════════════════════════════════════════════════════════════════════


def test_loop_event_post_init_uses_uuid4():
    """event_id 自动生成路径确由 uuid.uuid4() 提供。"""
    fake_uuid = "00000000-0000-4000-8000-000000000001"
    with mock.patch.object(event_bus.uuid, "uuid4", return_value=uuid.UUID(fake_uuid)):
        ev = LoopEvent(event_type=LoopEventType.CI_FAILURE)
    assert ev.event_id == fake_uuid


def test_subscription_post_init_uses_uuid4():
    """Subscription.id 自动生成路径确由 uuid.uuid4() 提供。"""
    fake_uuid = "00000000-0000-4000-8000-000000000002"
    with mock.patch.object(event_bus.uuid, "uuid4", return_value=uuid.UUID(fake_uuid)):
        sub = Subscription(id="", event_type=LoopEventType.CI_FAILURE, callback=_handler)
    assert sub.id == fake_uuid
