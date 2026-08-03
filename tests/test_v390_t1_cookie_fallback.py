# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""v3.9.0 Track3 — T1 cookie 回退读取验收测试（P2：middleware / auth_routes / is_authenticated）。

覆盖 acceptance-matrix：
  - T-T1-04 cookie 读 session（无 Authorization 头）
  - T-T1-05 cookie 访问 require_auth 的 /api/v1/* 端点
  - T-T1-06-neg 伪造 cookie → 401（fail-closed）
  - T-T1-07 Bearer 与 cookie 等价（同一 token 双通道判定一致）
  - T-T1-18-neg 两 cookie 不混用（osh_session 与 yuleosh_at 独立判定）
  - Authorization 存在但非 Bearer → fail-closed（不回退 cookie）
"""

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from unittest import mock

import pytest


def _make_mock_handler(headers=None, path="/", method="GET", body=b""):
    handler = mock.MagicMock(spec=BaseHTTPRequestHandler)
    class MockHeaders(dict):
        def items(self):
            return super().items()
    handler.headers = MockHeaders(headers or {})
    handler.path = path
    handler.command = method
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()
    return handler


def _seed_access_session():
    """Create a user + access token pair in the default store; return token."""
    from yuleosh.store import Store
    from yuleosh.ui.auth_extended import _issue_token_pair
    Store.reset()
    store = Store()
    uid = uuid.uuid4().hex[:10]
    org = store.create_organization("Fallback", f"fb-{uid}")
    user = store.create_user(org["id"], f"fb-{uid}@t.com")
    access, _refresh = _issue_token_pair(store, user["id"], org["id"], user["email"])
    return access


class TestMiddlewareCookieFallback:
    """T-T1-05 — require_auth 凭 access cookie 放行."""

    def _call_require_auth(self, headers):
        from yuleosh.api.middleware import require_auth
        handler = mock.MagicMock()
        handler.headers = headers

        @require_auth
        def _h(**kwargs):
            return {"ok": True, "cu": kwargs["current_user"]}, 200

        return _h(method="GET", path_tail="overview", body={}, query={},
                  handler=handler)

    def test_valid_access_cookie_allows(self):
        token = _seed_access_session()
        result, code = self._call_require_auth({"Cookie": f"yuleosh_at={token}"})
        assert code == 200
        assert result["cu"]["email"].startswith("fb-")

    def test_valid_access_cookie_lowercase_key(self):
        token = _seed_access_session()
        result, code = self._call_require_auth({"cookie": f"yuleosh_at={token}"})
        assert code == 200

    def test_cookie_among_other_cookies(self):
        token = _seed_access_session()
        result, code = self._call_require_auth({
            "Cookie": f"theme=dark; yuleosh_at={token}; osh_session=legacy"})
        assert code == 200

    def test_bearer_still_works(self):
        token = _seed_access_session()
        result, code = self._call_require_auth({"Authorization": f"Bearer {token}"})
        assert code == 200

    def test_forged_cookie_401(self):
        """T-T1-06-neg — 伪造 access cookie → 401（与 Bearer 伪造一致）."""
        result, code = self._call_require_auth(
            {"Cookie": "yuleosh_at=forged.token.value"})
        assert code == 401

    def test_no_credentials_401(self):
        result, code = self._call_require_auth({})
        assert code == 401

    def test_authorization_present_not_bearer_fails_closed(self):
        """Authorization 存在但非 Bearer → 即使 cookie 有效也 401（不回退）."""
        token = _seed_access_session()
        result, code = self._call_require_auth({
            "Authorization": "Basic abc",
            "Cookie": f"yuleosh_at={token}",
        })
        assert code == 401

    def test_osh_session_not_usable_as_access(self):
        """T-T1-18-neg — legacy osh_session cookie 不能冒充租户 access."""
        result, code = self._call_require_auth(
            {"Cookie": "osh_session=valid-looking-hmac-value"})
        assert code == 401


class TestAuthRoutesCookieFallback:
    """T-T1-04 — /api/auth/session 凭 access cookie 返回 200."""

    def test_session_via_cookie(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        token = _seed_access_session()
        handler = _make_mock_handler(
            headers={"Content-Length": "0", "Cookie": f"yuleosh_at={token}"},
            method="GET")
        with mock.patch("yuleosh.ui.auth_extended.handle_session_info") as m:
            m.return_value = ({"user_id": 1, "org_id": 1, "email": "a@t.com"}, 200)
            handle_api_action(handler, "session")
            # 无 Authorization → cookie 回退读取
            assert m.call_args[0][0] == token

    def test_session_forged_cookie_401(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        handler = _make_mock_handler(
            headers={"Content-Length": "0",
                     "Cookie": "yuleosh_at=forged.jwt.value"},
            method="GET")
        with mock.patch("yuleosh.ui.auth_extended.handle_session_info") as m:
            m.return_value = ({"error": "Invalid or expired session"}, 401)
            handle_api_action(handler, "session")
        assert m.call_args[0][0] == "forged.jwt.value"

    def test_bearer_preferred_over_cookie(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        handler = _make_mock_handler(
            headers={"Content-Length": "0",
                     "Authorization": "Bearer bearer-token",
                     "Cookie": "yuleosh_at=cookie-token"},
            method="GET")
        with mock.patch("yuleosh.ui.auth_extended.handle_session_info") as m:
            m.return_value = ({"ok": True}, 200)
            handle_api_action(handler, "session")
        assert m.call_args[0][0] == "bearer-token"


class TestIsAuthenticatedCookieBranch:
    """T-T1-07/18 — is_authenticated 委托链追加租户 cookie 判定."""

    def _call(self, headers):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            return is_authenticated(headers)

    def test_valid_access_cookie_authenticates(self):
        token = _seed_access_session()
        assert self._call({"cookie": f"yuleosh_at={token}"}) is True

    def test_garbage_cookie_denied(self):
        assert self._call({"cookie": "yuleosh_at=garbage"}) is False

    def test_refresh_cookie_never_authenticates(self):
        from yuleosh.store import Store
        from yuleosh.ui.auth_extended import _issue_token_pair
        Store.reset()
        store = Store()
        uid = uuid.uuid4().hex[:10]
        org = store.create_organization("Rt", f"rt-{uid}")
        user = store.create_user(org["id"], f"rt-{uid}@t.com")
        _access, refresh = _issue_token_pair(store, user["id"], org["id"],
                                             user["email"])
        # refresh cookie 无效（get_session_user 拒绝 purpose=refresh）
        assert self._call({"cookie": f"yuleosh_rt={refresh}"}) is False

    def test_legacy_osh_session_still_works(self):
        """T-T1-18-neg — legacy 机制独立保留（create_session/validate_session）. """
        from yuleosh.ui.auth import create_session, validate_session
        from yuleosh.ui.auth_cookies import read_cookie_value
        _, cookie_val = create_session()
        assert validate_session(cookie_val) is True
        # legacy 请求经 osh_session 分支放行（独立机制不回退）
        assert self._call({"cookie": f"osh_session={cookie_val}"}) is True
        # 但 osh_session 值绝不进入租户 cookie 读取（两 cookie 不混用）
        assert read_cookie_value({"cookie": f"osh_session={cookie_val}"},
                                 "yuleosh_at") is None
        # middleware 侧：osh_session 不能冒充 yuleosh_at（见 TestMiddleware）

    def test_x_api_key_still_works(self):
        with mock.patch("yuleosh.ui.auth.API_KEY", "secret-key", create=True):
            assert self._call({"x-api-key": "secret-key"}) is True


class TestReadCookieValue:
    """auth_cookies.read_cookie_value 单元测试."""

    def test_dict_upper_and_lower(self):
        from yuleosh.ui.auth_cookies import read_cookie_value
        assert read_cookie_value({"Cookie": "yuleosh_at=abc"}, "yuleosh_at") == "abc"
        assert read_cookie_value({"cookie": "yuleosh_at=abc"}, "yuleosh_at") == "abc"

    def test_missing(self):
        from yuleosh.ui.auth_cookies import read_cookie_value
        assert read_cookie_value({"Cookie": "other=1"}, "yuleosh_at") is None
        assert read_cookie_value({}, "yuleosh_at") is None
        assert read_cookie_value(None, "yuleosh_at") is None

    def test_malformed(self):
        from yuleosh.ui.auth_cookies import read_cookie_value
        assert read_cookie_value({"Cookie": "not a valid cookie ;;;"}, "yuleosh_at") is None

    def test_message_style_headers(self):
        """真实 BaseHTTPRequestHandler.headers 是 email.message.Message."""
        from email.message import Message
        from yuleosh.ui.auth_cookies import read_cookie_value
        msg = Message()
        msg["Cookie"] = "yuleosh_at=msg-token"
        assert read_cookie_value(msg, "yuleosh_at") == "msg-token"
        assert read_cookie_value(msg, "yuleosh_rt") is None
