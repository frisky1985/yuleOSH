"""Phase7 E2 — SourceValidator (HMAC 签名/验证/白名单) 全覆盖测试。

覆盖 src/yuleosh/loop_engine/event_bus.py L252-381:
  - __init__ / enabled / set_enabled / set_secret
  - add_to_whitelist / remove_from_whitelist / is_whitelisted / whitelist
  - set_auto_whitelist / auto_whitelist_enabled
  - sign / verify / validate_source

策略:
  - HMAC 期望值用真实 hmac 模块独立计算（确定性，无时钟依赖）。
  - _auto_whitelist 是私有"动态白名单"集合，公开 API 无写入入口
    （仅 remove_from_whitelist 会 discard），故直接操作私有属性做白盒分支覆盖。
"""

import hashlib
import hmac

import pytest

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType, SourceValidator

SECRET = "test-secret"


def _expected(event_id: str, source: str, secret: str) -> str:
    """独立计算期望的 HMAC-SHA256 十六进制签名。"""
    msg = f"{event_id}:{source}".encode()
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


@pytest.fixture
def validator() -> SourceValidator:
    return SourceValidator(secret=SECRET, enabled=True)


def _make_event(event_id: str = "evt-1", source: str = "ci.runner",
                signature: str = "") -> LoopEvent:
    return LoopEvent(
        event_type=LoopEventType.CI_FAILURE,
        source=source,
        event_id=event_id,
        signature=signature,
    )


# ─────────────────────────── __init__ ───────────────────────────

def test_init_env_secret_fallback(monkeypatch):
    """secret 为空时回退环境变量 YULEOSH_EVENT_SOURCE_SECRET。"""
    monkeypatch.setenv("YULEOSH_EVENT_SOURCE_SECRET", "env-secret")
    v = SourceValidator()
    assert v.sign("e1", "src") == _expected("e1", "src", "env-secret")


def test_init_explicit_secret_overrides_env(monkeypatch):
    """显式 secret 优先于环境变量（短路，不读 env）。"""
    monkeypatch.setenv("YULEOSH_EVENT_SOURCE_SECRET", "env-secret")
    v = SourceValidator(secret="explicit")
    assert v.sign("e1", "src") == _expected("e1", "src", "explicit")


def test_init_no_secret_and_no_env(monkeypatch):
    """secret 与 env 均缺失 → 空密钥，sign 返回空串。"""
    monkeypatch.delenv("YULEOSH_EVENT_SOURCE_SECRET", raising=False)
    v = SourceValidator()
    assert v.sign("e1", "src") == ""


def test_init_whitelist_list_and_auto_flag():
    v = SourceValidator(secret="s", whitelist=["a", "b"], auto_whitelist=True)
    assert v.is_whitelisted("a")
    assert v.is_whitelisted("b")
    assert v.auto_whitelist_enabled is True
    assert v.whitelist() == ["a", "b"]


# ─────────────── enabled / set_enabled / set_secret ───────────────

def test_enabled_property_and_toggle(validator):
    assert validator.enabled is True
    validator.set_enabled(False)
    assert validator.enabled is False
    validator.set_enabled(True)
    assert validator.enabled is True


def test_set_secret_rotates_signature(validator):
    old_sig = validator.sign("evt-1", "src")
    validator.set_secret("rotated")
    new_sig = validator.sign("evt-1", "src")
    assert new_sig == _expected("evt-1", "src", "rotated")
    assert old_sig != new_sig


# ─────────────────────────── 白名单 ───────────────────────────

def test_add_and_remove_whitelist(validator):
    validator.add_to_whitelist("ci.runner")
    assert validator.is_whitelisted("ci.runner")
    assert validator.whitelist() == ["ci.runner"]
    validator.remove_from_whitelist("ci.runner")
    assert not validator.is_whitelisted("ci.runner")
    assert validator.whitelist() == []


def test_remove_whitelist_absent_source_is_noop(validator):
    validator.remove_from_whitelist("never-added")
    assert validator.whitelist() == []


def test_remove_whitelist_clears_dynamic_auto_whitelist(validator):
    validator._auto_whitelist.add("dyn.src")
    assert validator.is_whitelisted("dyn.src")
    validator.remove_from_whitelist("dyn.src")
    assert not validator.is_whitelisted("dyn.src")
    assert validator.whitelist() == []


def test_whitelist_returns_sorted_union(validator):
    """whitelist() 返回静态+动态白名单的排序合并。"""
    validator.add_to_whitelist("b.src")
    validator.add_to_whitelist("a.src")
    validator._auto_whitelist.add("z.src")  # 白盒: 动态白名单无公开写入 API
    assert validator.whitelist() == ["a.src", "b.src", "z.src"]


def test_is_whitelisted_via_dynamic_auto_whitelist(validator):
    validator._auto_whitelist.add("dyn.src")
    assert validator.is_whitelisted("dyn.src")
    assert not validator.is_whitelisted("other.src")


# ─────────────────────── auto_whitelist 开关 ───────────────────────

def test_set_auto_whitelist_toggle(validator):
    assert validator.auto_whitelist_enabled is False
    validator.set_auto_whitelist(True)
    assert validator.auto_whitelist_enabled is True
    validator.set_auto_whitelist(False)
    assert validator.auto_whitelist_enabled is False


# ───────────────────────────── sign ─────────────────────────────

def test_sign_matches_independent_hmac_and_is_deterministic(validator):
    sig = validator.sign("evt-1", "ci.runner")
    assert sig == _expected("evt-1", "ci.runner", SECRET)
    assert sig == validator.sign("evt-1", "ci.runner")
    assert len(sig) == 64  # sha256 hex 长度


def test_sign_empty_secret_returns_empty_string(validator):
    validator.set_secret("")
    assert validator.sign("evt-1", "src") == ""


def test_sign_distinguishes_inputs(validator):
    assert validator.sign("evt-1", "src-a") != validator.sign("evt-1", "src-b")
    assert validator.sign("evt-1", "src") != validator.sign("evt-2", "src")


# ───────────────────────────── verify ─────────────────────────────

def test_verify_valid_signature(validator):
    sig = validator.sign("evt-1", "ci.runner")
    ok, reason = validator.verify("evt-1", "ci.runner", sig)
    assert ok is True
    assert reason == "hmac signature valid"


def test_verify_tampered_signature(validator):
    sig = validator.sign("evt-1", "ci.runner")
    tampered = ("0" if sig[0] != "0" else "1") + sig[1:]
    ok, reason = validator.verify("evt-1", "ci.runner", tampered)
    assert ok is False
    assert reason == "hmac signature mismatch"


def test_verify_wrong_event_id(validator):
    sig = validator.sign("evt-1", "ci.runner")
    ok, reason = validator.verify("evt-2", "ci.runner", sig)
    assert ok is False
    assert reason == "hmac signature mismatch"


def test_verify_secret_rotated_after_sign(validator):
    sig = validator.sign("evt-1", "ci.runner")
    validator.set_secret("rotated-secret")
    ok, reason = validator.verify("evt-1", "ci.runner", sig)
    assert ok is False
    assert reason == "hmac signature mismatch"


def test_verify_when_disabled_accepts_anything(validator):
    validator.set_enabled(False)
    ok, reason = validator.verify("evt-1", "ci.runner", "garbage")
    assert ok is True
    assert reason == "validation disabled"


def test_verify_whitelisted_source_bypasses_hmac(validator):
    validator.add_to_whitelist("trusted.src")
    ok, reason = validator.verify("evt-1", "trusted.src", "not-a-signature")
    assert ok is True
    assert reason == "source whitelisted"


def test_verify_dynamic_auto_whitelisted_source(validator):
    validator._auto_whitelist.add("dyn.src")
    ok, reason = validator.verify("evt-1", "dyn.src", "nonsense")
    assert ok is True
    assert reason == "source whitelisted"


def test_verify_auto_whitelist_trusts_all_sources(validator):
    """auto_whitelist 开启且无显式白名单 → 信任所有来源。"""
    validator.set_auto_whitelist(True)
    ok, reason = validator.verify("evt-1", "any.src", "whatever")
    assert ok is True
    assert reason == "auto whitelisted (all sources trusted)"


def test_verify_auto_whitelist_with_explicit_whitelist_uses_hmac(validator):
    """auto_whitelist 开启但存在显式白名单 → 回退 HMAC 校验。"""
    validator.set_auto_whitelist(True)
    validator.add_to_whitelist("trusted.src")
    ok, reason = validator.verify("evt-1", "other.src", "bad")
    assert ok is False
    assert reason == "hmac signature mismatch"


def test_verify_no_secret_not_whitelisted(validator):
    validator.set_secret("")
    ok, reason = validator.verify("evt-1", "src", "sig")
    assert ok is False
    assert reason == "no signing secret configured and auto_whitelist disabled"


# ───────────────────────── validate_source ─────────────────────────

def test_validate_source_with_valid_signature(validator):
    sig = validator.sign("evt-1", "ci.runner")
    ok, reason = validator.validate_source(_make_event(signature=sig))
    assert ok is True
    assert reason == "hmac signature valid"


def test_validate_source_rejects_forged_signature(validator):
    ok, reason = validator.validate_source(
        _make_event(signature="forged-signature")
    )
    assert ok is False
    assert reason == "hmac signature mismatch"


def test_validate_source_whitelisted_event(validator):
    validator.add_to_whitelist("ci.runner")
    ok, reason = validator.validate_source(_make_event())
    assert ok is True
    assert reason == "source whitelisted"


def test_validate_source_auto_whitelisted_event(validator):
    validator.set_auto_whitelist(True)
    ok, reason = validator.validate_source(
        _make_event(source="auto.src", signature="")
    )
    assert ok is True
    assert reason == "auto whitelisted (all sources trusted)"


def test_validate_source_when_disabled(validator):
    validator.set_enabled(False)
    ok, reason = validator.validate_source(_make_event())
    assert ok is True
    assert reason == "validation disabled"
