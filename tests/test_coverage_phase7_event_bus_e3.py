"""Phase 7 E3 — TokenBucket 令牌桶限流 全分支覆盖率测试。

目标: src/yuleosh/loop_engine/event_bus.py L388-510 (class TokenBucket) 全行覆盖。
时间依赖全部 mock (yuleosh.loop_engine.event_bus.time.time) —— 无真实时间/网络/subprocess。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

from unittest.mock import patch

import pytest

from yuleosh.loop_engine.event_bus import TokenBucket

# event_bus.py 内为模块级 `import time`，因此 patch 模块属性即可拦截 time.time()。
_TIME_PATH = "yuleosh.loop_engine.event_bus.time.time"


class FakeTime:
    """可手动推进的可变时钟，用于模拟 refill 时间流逝。"""

    def __init__(self, start: float):
        self.now = start

    def __call__(self) -> float:
        return self.now


# ── __init__ ────────────────────────────────────────────────────────────


def test_init_defaults():
    tb = TokenBucket()
    assert tb._default_rate == 50.0
    assert tb._default_burst == 100
    assert tb._per_type_rates == {}
    assert tb._buckets == {}
    assert tb._enabled is True


def test_init_with_per_type_rates():
    tb = TokenBucket(default_rate=1.0, default_burst=7, per_type_rates={"ci": 3.0})
    assert tb._default_rate == 1.0
    assert tb._default_burst == 7
    assert tb._per_type_rates == {"ci": 3.0}


def test_init_empty_per_type_rates_falsy():
    # `dict(per_type_rates or {})` 的 falsy 分支
    tb = TokenBucket(per_type_rates={})
    assert tb._per_type_rates == {}
    tb2 = TokenBucket(per_type_rates=None)
    assert tb2._per_type_rates == {}


# ── enabled / set_enabled ───────────────────────────────────────────────


def test_enabled_property_and_set_enabled():
    tb = TokenBucket()
    assert tb.enabled is True
    tb.set_enabled(False)
    assert tb.enabled is False
    tb.set_enabled(True)
    assert tb.enabled is True


# ── set_rate ────────────────────────────────────────────────────────────


def test_set_rate_updates_per_type_rates():
    tb = TokenBucket()
    tb.set_rate("ci.failure", 2.5)
    assert tb._per_type_rates == {"ci.failure": 2.5}
    tb.set_rate("ci.failure", 0.0)
    assert tb._per_type_rates == {"ci.failure": 0.0}


# ── _get_bucket ─────────────────────────────────────────────────────────


def test_get_bucket_creates_new():
    with patch(_TIME_PATH, return_value=123.0) as m:
        tb = TokenBucket(default_rate=10.0, default_burst=100)
        b = tb._get_bucket("ci")
    assert b["tokens"] == 100.0
    assert b["rate"] == 10.0
    assert b["burst"] == 100
    assert b["last_refill"] == 123.0
    assert b["dropped"] == 0
    assert m.call_count == 1


def test_get_bucket_reuses_existing():
    with patch(_TIME_PATH, return_value=1.0) as m:
        tb = TokenBucket()
        b1 = tb._get_bucket("ci")
        b2 = tb._get_bucket("ci")
    assert b1 is b2
    # 复用分支不再调用 time.time（不重新初始化）
    assert m.call_count == 1


def test_get_bucket_burst_prefers_rate_times_two():
    tb = TokenBucket(default_rate=1.0, default_burst=10, per_type_rates={"fast": 100.0})
    with patch(_TIME_PATH, return_value=0.0):
        fast = tb._get_bucket("fast")
        slow = tb._get_bucket("slow")
    assert fast["rate"] == 100.0
    assert fast["burst"] == 200  # int(max(100*2, 10))
    assert fast["tokens"] == 200.0
    assert slow["rate"] == 1.0
    assert slow["burst"] == 10  # int(max(1*2, 10)) → 默认 burst 更大
    assert slow["tokens"] == 10.0


# ── _refill ─────────────────────────────────────────────────────────────


def test_refill_partial_refill():
    with patch(_TIME_PATH, side_effect=[100.0, 100.5]):
        tb = TokenBucket(default_rate=10.0, default_burst=100)
        b = tb._get_bucket("ci")  # t=100.0, tokens=100.0
        b["tokens"] = 90.0
        tb._refill(b)  # elapsed=0.5 → +5 → 95 (< burst, 部分补充)
    assert b["tokens"] == 95.0
    assert b["last_refill"] == 100.5


def test_refill_caps_at_burst():
    with patch(_TIME_PATH, side_effect=[100.0, 200.0]):
        tb = TokenBucket(default_rate=10.0, default_burst=100)
        b = tb._get_bucket("ci")
        b["tokens"] = 90.0
        tb._refill(b)  # elapsed=100 → +1000 → min 封顶到 burst=100
    assert b["tokens"] == 100.0
    assert b["last_refill"] == 200.0


def test_refill_full_bucket_stays_at_cap():
    with patch(_TIME_PATH, side_effect=[100.0, 150.0]):
        tb = TokenBucket(default_rate=5.0, default_burst=100)
        b = tb._get_bucket("ci")
        tb._refill(b)  # elapsed=50 → +250 → 封顶仍为 100
    assert b["tokens"] == 100.0
    assert b["last_refill"] == 150.0


# ── check ───────────────────────────────────────────────────────────────


def test_check_disabled_short_circuits():
    tb = TokenBucket()
    tb.set_enabled(False)
    assert tb.check("ci") == (True, 0.0)
    assert tb.check("ops") == (True, 0.0)
    # disabled 时不创建任何 bucket
    assert tb._buckets == {}


def test_check_full_bucket_allowed():
    with patch(_TIME_PATH, return_value=50.0):
        tb = TokenBucket()
        assert tb.check("ci") == (True, 0.0)
    assert tb._buckets["ci"]["tokens"] == 100.0


def test_check_insufficient_tokens_returns_wait():
    with patch(_TIME_PATH, side_effect=[0.0, 0.5]):
        tb = TokenBucket(default_rate=1.0, default_burst=100)
        b = tb._get_bucket("ci")  # t=0, tokens=100
        b["tokens"] = 0.0
        b["last_refill"] = 0.0
        allowed, wait = tb.check("ci")  # elapsed=0.5 → tokens=0.5 < 1
    assert allowed is False
    assert wait == pytest.approx(0.5)  # (1-0.5)/1.0


def test_check_zero_rate_uses_floor_rate():
    with patch(_TIME_PATH, side_effect=[0.0, 0.0]):
        tb = TokenBucket(default_rate=0.0, default_burst=5)
        b = tb._get_bucket("ci")
        b["tokens"] = 0.0
        b["last_refill"] = 0.0
        allowed, wait = tb.check("ci")
    assert allowed is False
    # max(rate, 0.001) 兜底 → (1-0)/0.001
    assert wait == pytest.approx(1000.0)


def test_check_allowed_after_partial_refill():
    with patch(_TIME_PATH, side_effect=[0.0, 0.2]):
        tb = TokenBucket(default_rate=10.0, default_burst=100)
        b = tb._get_bucket("ci")
        b["tokens"] = 0.0
        b["last_refill"] = 0.0
        allowed, wait = tb.check("ci")  # elapsed=0.2 → tokens=2.0 ≥ 1
    assert allowed is True
    assert wait == 0.0


def test_check_exactly_one_token_allowed():
    with patch(_TIME_PATH, return_value=0.0):
        tb = TokenBucket()
        b = tb._get_bucket("ci")
        b["tokens"] = 1.0
        assert tb.check("ci") == (True, 0.0)


def test_check_capped_refill_then_allowed():
    with patch(_TIME_PATH, side_effect=[0.0, 100.0]):
        tb = TokenBucket(default_rate=10.0, default_burst=100)
        b = tb._get_bucket("ci")
        b["tokens"] = 50.0
        b["last_refill"] = 0.0
        allowed, _ = tb.check("ci")  # elapsed=100 → 封顶到 100
    assert allowed is True
    assert b["tokens"] == 100.0


# ── consume ─────────────────────────────────────────────────────────────


def test_consume_success_decrements_token():
    with patch(_TIME_PATH, return_value=100.0):
        tb = TokenBucket()
        assert tb.consume("ci") is True
        assert tb._buckets["ci"]["tokens"] == 99.0


def test_consume_floor_at_zero():
    with patch(_TIME_PATH, return_value=100.0):
        tb = TokenBucket(default_rate=10.0, default_burst=1)
        b = tb._get_bucket("ci")
        b["tokens"] = 1.0
        assert tb.consume("ci") is True  # 1.0 ≥ 1.0 → max(0.0, 1.0-1.0)
        assert b["tokens"] == 0.0
        assert b["dropped"] == 0


def test_consume_exhausts_bucket_then_drops():
    with patch(_TIME_PATH, return_value=100.0):
        # rate=1.0 → burst = int(max(2.0, 3)) = 3
        tb = TokenBucket(default_rate=1.0, default_burst=3)
        results = [tb.consume("ci") for _ in range(5)]
    assert results == [True, True, True, False, False]
    b = tb._buckets["ci"]
    assert b["tokens"] == 0.0
    assert b["dropped"] == 2


def test_consume_failure_increments_dropped():
    with patch(_TIME_PATH, return_value=100.0):
        tb = TokenBucket(default_rate=0.0, default_burst=5)
        b = tb._get_bucket("ci")
        b["tokens"] = 0.0
        assert tb.consume("ci") is False
        assert tb.consume("ci") is False
        assert b["dropped"] == 2
        assert b["tokens"] == 0.0


def test_consume_when_disabled():
    with patch(_TIME_PATH, return_value=100.0):
        # rate=1.0 → burst = int(max(2.0, 5)) = 5
        tb = TokenBucket(default_rate=1.0, default_burst=5)
        tb.set_enabled(False)
        # check 短路返回 (True, 0.0)，consume 走 allowed 分支并创建 bucket
        assert tb.consume("ci") is True
        assert tb._buckets["ci"]["tokens"] == 4.0
        assert tb._buckets["ci"]["dropped"] == 0


# ── set_rate 与 bucket 隔离 ─────────────────────────────────────────────


def test_set_rate_affects_only_new_buckets():
    with patch(_TIME_PATH, return_value=0.0):
        tb = TokenBucket(default_rate=10.0, default_burst=50)
        tb._get_bucket("a")  # rate=10.0
        tb.set_rate("a", 100.0)
        tb.set_rate("b", 100.0)
        tb._get_bucket("b")  # rate=100.0, burst=int(max(200, 50))=200
    # 已存在的 bucket 保持创建时的 rate，不随 set_rate 变更
    assert tb._buckets["a"]["rate"] == 10.0
    assert tb._buckets["b"]["rate"] == 100.0
    assert tb._buckets["b"]["burst"] == 200


def test_buckets_isolated_per_event_type():
    with patch(_TIME_PATH, return_value=0.0):
        tb = TokenBucket(default_rate=1.0, default_burst=5)
        assert tb.check("ci") == (True, 0.0)
        assert tb.check("ops") == (True, 0.0)
        b = tb._buckets["ci"]
        b["tokens"] = 0.0
        b["last_refill"] = 0.0
        assert tb.check("ci")[0] is False
        assert tb.check("ops")[0] is True  # ops 桶独立不受影响


# ── stats ───────────────────────────────────────────────────────────────


def test_stats_empty():
    tb = TokenBucket()
    assert tb.stats() == {
        "enabled": True,
        "default_rate": 50.0,
        "default_burst": 100,
        "buckets": {},
    }


def test_stats_shape_rounding_and_no_internal_keys():
    with patch(_TIME_PATH, return_value=0.0):
        tb = TokenBucket(
            default_rate=10.0, default_burst=100, per_type_rates={"ci": 2.0}
        )
        tb._get_bucket("ci")
        tb._get_bucket("other")
        b = tb._buckets["ci"]
        b["tokens"] = 99.126
        b["dropped"] = 3
        s = tb.stats()
    assert s["enabled"] is True
    assert s["default_rate"] == 10.0
    assert s["default_burst"] == 100
    ci = s["buckets"]["ci"]
    assert ci["tokens"] == pytest.approx(99.13)  # round(99.126, 2)
    assert ci["rate"] == 2.0
    assert ci["burst"] == 100
    assert ci["dropped"] == 3
    other = s["buckets"]["other"]
    assert other["rate"] == 10.0
    assert other["burst"] == 100
    assert other["dropped"] == 0
    # stats 不泄漏内部字段 last_refill
    assert "last_refill" not in ci


# ── 时间推进集成流 ───────────────────────────────────────────────────────


def test_time_advance_rate_limiting_flow():
    ft = FakeTime(100.0)
    with patch(_TIME_PATH, ft):
        tb = TokenBucket(default_rate=2.0, default_burst=4)
        for _ in range(4):
            assert tb.consume("ci") is True
        assert tb._buckets["ci"]["tokens"] == 0.0
        assert tb.consume("ci") is False
        assert tb._buckets["ci"]["dropped"] == 1

        ft.now = 101.5  # 1.5s → 补充 3 token → 3.0
        assert tb.check("ci") == (True, 0.0)
        assert tb.consume("ci") is True
        assert tb._buckets["ci"]["tokens"] == pytest.approx(2.0)

        ft.now = 101.5  # elapsed=0 → 不变
        assert tb.check("ci") == (True, 0.0)

        ft.now = 102.0  # 0.5s → +1 → 3.0
        assert tb.consume("ci") is True
        assert tb._buckets["ci"]["tokens"] == pytest.approx(2.0)
