# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.8.0 Track2 — A1 认证合一验收测试（acceptance-matrix T-A1-*）。

覆盖:
  - T-A1-01 secret 单一来源
  - T-A1-02 middleware 统一 verify（get_session_user 被调用）
  - T-A1-03/04 双链互认（v1 token ↔ 前端链 token）
  - T-A1-05/06 register/login 响应契约
  - T-A1-07/14 负例：无效 token / 无 token → 401
  - T-A1-08-neg 限流合并共享计数
  - T-A1-09-neg 无随机 secret 兜底（grep）
  - T-A1-10 fail-fast
  - T-A1-11 前端登录链 E2E
  - T-A1-12/13 API key / session cookie 保留
  - T-A1-15-neg 重复实现消失（grep）
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import jwt as pyjwt
import pytest

from yuleosh.store import Store


def _make_user_and_session(store: Store, org_id: int = 1,
                           email: str | None = None, role: str = "admin"):
    """Seed a user + live session row; return (token, user_id)."""
    from yuleosh.store import _session_token_hash
    from datetime import datetime, timedelta
    from yuleosh.ui.auth_extended import _generate_token
    import uuid as _uuid
    # Collision-free id AND email: users has UNIQUE(org_id, email), so a
    # reused email would make INSERT OR IGNORE skip the user row while the
    # session still references the new (non-existent) uid.
    uid = int(_uuid.uuid4().int % 1_000_000_000) + 100_000_000
    email = email or f"a1-{uid}@test.com"
    store.conn.execute(
        "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (uid, org_id, email, role, datetime.now().isoformat()),
    )
    token = _generate_token(user_id=uid, org_id=org_id, email=email)
    store.conn.execute(
        "INSERT OR IGNORE INTO user_sessions (user_id, token, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (uid, _session_token_hash(token), datetime.now().isoformat(),
         (datetime.now() + timedelta(hours=72)).isoformat()),
    )
    store.conn.commit()
    return token, uid


class TestA1SecretSingleSource:
    """T-A1-01 — secret 单一来源."""

    def test_secret_same_value(self):
        import yuleosh.api.auth as api_auth
        import yuleosh.ui.auth_extended as ae
        assert api_auth._JWT_SECRET == ae.JWT_SECRET
        # api/auth.py must not re-read env (single source).
        assert api_auth._JWT_SECRET is ae.JWT_SECRET or \
            api_auth._JWT_SECRET == ae.JWT_SECRET

    def test_auth_extended_is_only_env_reader(self):
        """SHALL-A1.1: api/auth.py 无第二份 env 解读."""
        repo = Path(__file__).resolve().parent.parent
        text = (repo / "src/yuleosh/api/auth.py").read_text(encoding="utf-8")
        assert 'os.environ.get("YULEOSH_JWT_SECRET")' not in text
        assert "from yuleosh.ui.auth_extended import" in text


class TestA1MiddlewareUnifiedVerify:
    """T-A1-02 — middleware 调用统一 verify."""

    def test_require_auth_calls_verify_token(self):
        from yuleosh.api.middleware import require_auth
        store = Store()
        token, uid = _make_user_and_session(store)

        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}

        from yuleosh.ui.auth_extended import verify_token as _real_verify
        with mock.patch("yuleosh.api.middleware.verify_token",
                        wraps=_real_verify) as vt:
            @require_auth
            def _h(**kwargs):
                return {"ok": True}, 200

            result, code = _h(method="GET", path_tail="", body={}, query={},
                              handler=handler)
            assert code == 200
            vt.assert_called_once()

    def test_middleware_self_decode_not_used(self):
        """SHALL-A1.2: middleware 自研解码不执行（薄委托）."""
        from yuleosh.api.middleware import _decode_token
        with mock.patch("yuleosh.ui.auth_extended._decode_token",
                        return_value={"sub": "1"}) as d:
            assert _decode_token("whatever") == {"sub": "1"}
            d.assert_called_once()


class TestA1DualChain:
    """T-A1-03/04 — v1 token ↔ 前端链 token 互认."""

    def test_v1_token_ui_session(self):
        """/api/v1/auth/login 签发的 token 可在 GET /api/auth/session 解析."""
        from yuleosh.api.auth import handle_auth
        from yuleosh.ui.auth_extended import handle_session_info

        email = f"a1-v1-{int(time.time())}@test.com"
        body = {"email": email, "password": "TestPass123!",
                "organization_name": f"A1Org{int(time.time())}"}
        data, status = handle_auth("POST", "register", body, {})
        assert status == 200
        token = data["data"]["token"]
        # Cross-chain: session endpoint resolves the same user.
        info, s = handle_session_info(token)
        assert s == 200
        assert info["email"] == email

    def test_ui_token_v1_me(self):
        """前端 signin 签发的 token 可在 GET /api/v1/auth/me 解析."""
        from yuleosh.ui.auth_extended import handle_signin
        from yuleosh.api.auth import handle_auth

        email = f"a1-ui-{int(time.time())}@test.com"
        body = {"email": email, "password": "TestPass123!",
                "organization_name": f"A1UiOrg{int(time.time())}"}
        data, status = handle_auth("POST", "register", body, {})
        assert status == 200
        # Sign in via the frontend flow with the same credentials.
        resp, s = handle_signin({"email": email, "password": "TestPass123!"})
        assert s == 200 and "token" in resp
        token = resp["token"]

        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        me, ms = handle_auth("GET", "me", {}, {}, handler=handler)
        assert ms == 200
        assert me["data"]["user"]["email"] == email


class TestA1Contract:
    """T-A1-05/06 — register/login 响应契约."""

    def test_register_contract(self):
        from yuleosh.api.auth import handle_auth
        email = f"a1-reg-{int(time.time())}@test.com"
        data, status = handle_auth("POST", "register", {
            "email": email, "password": "TestPass123!",
            "organization_name": f"RegOrg{int(time.time())}",
        }, {})
        assert status == 200
        d = data["data"]
        assert "token" in d
        assert set(d["user"].keys()) == {"id", "email", "role", "org"}
        assert set(d["user"]["org"].keys()) == {"id", "name", "slug"}
        assert d["user"]["email"] == email

    def test_login_contract(self):
        from yuleosh.api.auth import handle_auth
        email = f"a1-login-{int(time.time())}@test.com"
        body = {"email": email, "password": "TestPass123!",
                "organization_name": f"LoginOrg{int(time.time())}"}
        handle_auth("POST", "register", body, {})
        data, status = handle_auth("POST", "login",
                                   {"email": email, "password": "TestPass123!"}, {})
        assert status == 200
        d = data["data"]
        assert "token" in d
        assert set(d["user"].keys()) == {"id", "email", "role", "org"}

    def test_duplicate_register_409(self):
        from yuleosh.api.auth import handle_auth
        email = f"a1-dup-{int(time.time())}@test.com"
        body = {"email": email, "password": "TestPass123!",
                "organization_name": f"DupOrg{int(time.time())}"}
        r1, s1 = handle_auth("POST", "register", body, {})
        assert s1 == 200
        r2, s2 = handle_auth("POST", "register", body, {})
        assert s2 == 409


class TestA1Negative:
    """T-A1-07 / T-A1-14 — 负例."""

    def test_invalid_token_both_ends(self):
        from yuleosh.api.middleware import require_auth
        from yuleosh.api.auth import handle_auth

        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer forged.token.value"}

        @require_auth
        def _h(**kwargs):
            return {"ok": True}, 200

        _, code = _h(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert code == 401

        me, ms = handle_auth("GET", "me", {}, {}, handler=handler)
        assert ms == 401

    def test_no_token_401(self):
        from yuleosh.api.middleware import require_auth
        handler = mock.MagicMock()
        handler.headers = {}

        @require_auth
        def _h(**kwargs):
            return {"ok": True}, 200

        result, code = _h(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert code == 401
        assert result["error"] == "Authorization header with Bearer token required"


class TestA1RateLimitMerged:
    """T-A1-08-neg — 限流合并后共享计数."""

    def test_shared_budget_across_endpoints(self):
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT, _check_rate_limit
        from yuleosh.api.auth import _check_and_record_failed_attempt
        email = f"a1-rl-{int(time.time())}@test.com"
        _SIGNIN_RATE_LIMIT.clear()
        try:
            # 10 次失败（模拟 /api/v1/auth/login 失败路径）
            for _ in range(10):
                _check_and_record_failed_attempt(email)
            # 再走前端 signin 路径 → 共享预算被阻断
            assert _check_rate_limit(email) is True
        finally:
            _SIGNIN_RATE_LIMIT.clear()


class TestA1NoRandomFallback:
    """T-A1-09-neg / T-A1-10 — grep + fail-fast."""

    def test_no_token_urlsafe_in_src(self):
        repo = Path(__file__).resolve().parent.parent
        hits = []
        for p in (repo / "src/yuleosh").rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "token_urlsafe(32)" in line:
                    hits.append(f"{p.relative_to(repo)}:{i}")
        assert hits == [], f"token_urlsafe(32) 残留: {hits}"

    def test_fail_fast_without_env(self):
        repo = Path(__file__).resolve().parent.parent
        env = {k: v for k, v in os.environ.items() if k != "YULEOSH_JWT_SECRET"}
        r = subprocess.run(
            [sys.executable, "-c",
             "import yuleosh.ui.auth_extended; import yuleosh.api.auth"],
            env=env, capture_output=True, text=True, timeout=60, cwd=str(repo),
        )
        assert r.returncode != 0
        assert "YULEOSH_JWT_SECRET" in r.stderr


class TestA1ApiKeyAndCookieKept:
    """T-A1-12/13 — 独立机制保留."""

    def test_api_key_path_kept(self):
        from yuleosh.ui.auth import is_authenticated
        # X-API-Key 合法（API_KEY 从 env 读取；未设置时 AUTH_ENABLED=False）
        assert callable(is_authenticated)

    def test_cookie_mechanism_kept(self):
        from yuleosh.ui.auth import (
            create_session, validate_session, _generate_session_token,
        )
        token = _generate_session_token()
        token2, cookie = create_session()
        assert validate_session(cookie) is True
        assert token and token2


class TestA1DeadCodeGone:
    """T-A1-15-neg — api/auth.py 重复实现消失."""

    def test_no_duplicate_defs(self):
        repo = Path(__file__).resolve().parent.parent
        text = (repo / "src/yuleosh/api/auth.py").read_text(encoding="utf-8")
        for name in ("def _generate_token", "def _hash_password",
                     "def _check_rate_limit"):
            assert name not in text, f"{name} 仍在 api/auth.py"
        assert "_SIGNIN_RATE_LIMIT" not in text or \
            "from yuleosh.ui.auth_extended import" in text


class TestA1FrontendChain:
    """T-A1-11 — 前端登录链 E2E（signin → org → session → project → stats）."""

    def test_full_chain(self):
        from yuleosh.ui.auth_extended import (
            handle_signin, handle_org_create, handle_session_info,
            handle_project_list,
        )
        from yuleosh.api.middleware import require_auth

        email = f"a1-chain-{int(time.time())}@test.com"
        resp, s = handle_signin({"email": email, "password": "TestPass123!"})
        assert s == 200
        token = resp["token"]

        org_resp, os_ = handle_org_create({
            "org_name": f"ChainOrg{int(time.time())}",
            "org_slug": f"chainorg{int(time.time())}",
            "project_name": "P1", "project_slug": "p1",
            "email": email, "password": "TestPass123!",
        }, token)
        assert os_ == 200
        token = org_resp["token"]

        info, si = handle_session_info(token)
        assert si == 200 and info["user_id"] is not None
        assert info["org_slug"]

        projects, pl = handle_project_list(token)
        assert pl == 200
        assert any(p["slug"] == "p1" for p in projects["projects"])

        # dashboard 数据端点（@require_auth）
        store = Store()
        from yuleosh.ui.auth_extended import _generate_token
        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}

        @require_auth
        def _h(**kwargs):
            return {"ok": True, "cu": kwargs["current_user"]}, 200

        result, code = _h(method="GET", path_tail="overview", body={}, query={},
                          handler=handler)
        assert code == 200
        assert result["cu"]["user_id"] == info["user_id"]
