
# @tests src/yuleosh/api/dashboard.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.9.0 Track3 — T1 refresh 续期端点验收测试（P3：POST /api/auth/refresh）。

覆盖 acceptance-matrix：
  - T-T1-10 refresh 续期：新 access 签发（原请求重放由前端 P4 覆盖）
  - T-T1-11-neg refresh 过期/无效 → 401 + 双 cookie 清除（Max-Age=0）
  - T-T1-12-neg refresh 轮换：续期后旧 refresh 失效（SHALL-T1.13）
  - T1.7 兼容：非浏览器客户端可经 Bearer 携带 refresh token 续期
  - 新 access 立即可用于 require_auth / session
"""

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from unittest import mock

import pytest

from yuleosh.store import Store
from yuleosh.ui.auth_extended import _issue_token_pair


def _seed_pair():
    """Seed a user + access/refresh pair; return (store, access, refresh)."""
    Store.reset()
    store = Store()
    uid = uuid.uuid4().hex[:10]
    org = store.create_organization("Refresh", f"rf-{uid}")
    user = store.create_user(org["id"], f"rf-{uid}@t.com")
    access, refresh = _issue_token_pair(store, user["id"], org["id"],
                                        user["email"])
    return store, access, refresh


def _make_mock_handler(headers=None, method="POST", body=b"{}"):
    handler = mock.MagicMock(spec=BaseHTTPRequestHandler)
    class MockHeaders(dict):
        def items(self):
            return super().items()
    handler.headers = MockHeaders(headers or {})
    handler.path = "/api/auth/refresh"
    handler.command = method
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()
    return handler


def _set_cookie_calls(handler):
    return [
        (c.args[0], c.args[1])
        for c in handler.send_header.call_args_list
        if c.args and c.args[0] == "Set-Cookie"
    ]


class TestHandleRefreshUnit:
    """handle_refresh 直接单元测试."""

    def test_valid_refresh_issues_new_pair(self):
        from yuleosh.ui.auth_extended import handle_refresh, _decode_token
        _store, _access, refresh = _seed_pair()
        result, status = handle_refresh(refresh)
        assert status == 200
        assert "token" in result and result.get("refresh_token")
        assert result["token"] != refresh
        assert _decode_token(result["refresh_token"]).get("purpose") == "refresh"

    def test_no_token_401(self):
        from yuleosh.ui.auth_extended import handle_refresh
        result, status = handle_refresh(None)
        assert status == 401
        assert handle_refresh("")[1] == 401

    def test_garbage_token_401(self):
        from yuleosh.ui.auth_extended import handle_refresh
        assert handle_refresh("garbage.token.value")[1] == 401

    def test_access_token_not_accepted(self):
        """access token（无 purpose）不能用于 refresh 端点."""
        from yuleosh.ui.auth_extended import handle_refresh
        _store, access, _refresh = _seed_pair()
        result, status = handle_refresh(access)
        assert status == 401

    def test_rotation_old_refresh_dead(self):
        """T-T1-12-neg — 续期后旧 refresh 立即失效（轮换）."""
        from yuleosh.ui.auth_extended import handle_refresh, verify_token
        store, _access, refresh = _seed_pair()
        result, status = handle_refresh(refresh)
        assert status == 200
        # 旧 refresh 再使用 → 401（session 行已删除）
        assert handle_refresh(refresh)[1] == 401
        # 新 refresh 有效
        assert handle_refresh(result["refresh_token"])[1] == 200

    def test_logged_out_refresh_rejected(self):
        """logout（DB 行删除）后 refresh → 401."""
        from yuleosh.ui.auth_extended import handle_refresh
        from yuleosh.store import _session_token_hash
        store, _access, refresh = _seed_pair()
        store.delete_session(refresh)
        assert handle_refresh(refresh)[1] == 401


class TestRefreshRoute:
    """路由层：Set-Cookie 下发与清除."""

    def test_success_sets_new_cookies(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        _store, _access, refresh = _seed_pair()
        handler = _make_mock_handler(
            headers={"Content-Length": "2", "Cookie": f"yuleosh_rt={refresh}"})
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh",
                        return_value=(
                            {"token": "new-at", "refresh_token": "new-rt"}, 200)):
            handle_api_action(handler, "refresh")
        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        values = {v.split("=")[0] for _, v in cookies}
        assert values == {"yuleosh_at", "yuleosh_rt"}
        # 新 token 进 cookie
        assert any("new-at" in v for _, v in cookies if v.startswith("yuleosh_at="))
        assert any("new-rt" in v for _, v in cookies if v.startswith("yuleosh_rt="))
        # body 无 refresh_token
        assert "new-rt" not in handler.wfile.getvalue().decode()

    def test_failure_clears_cookies(self):
        """T-T1-11-neg — refresh 失效 → 401 + 双 cookie Max-Age=0."""
        from yuleosh.ui.routes.auth_routes import handle_api_action
        handler = _make_mock_handler(
            headers={"Content-Length": "2",
                     "Cookie": "yuleosh_rt=expired.refresh.token"})
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh",
                        return_value=({"error": "Invalid or expired refresh token"}, 401)):
            handle_api_action(handler, "refresh")
        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        for _, v in cookies:
            assert "Max-Age=0" in v
            assert v.split("=")[0].split(";")[0] in ("yuleosh_at", "yuleosh_rt")


class TestRefreshWire:
    """真实 store 流程（不 mock handle_refresh）."""

    def test_full_renewal_cycle(self):
        """refresh 成功 → 新 access 可用于 middleware 与 session."""
        from yuleosh.ui.routes.auth_routes import handle_api_action
        from yuleosh.ui.auth_extended import handle_refresh
        from yuleosh.api.middleware import require_auth

        _store, _access, refresh = _seed_pair()
        result, status = handle_refresh(refresh)
        assert status == 200
        new_access = result["token"]
        new_refresh = result["refresh_token"]

        # 新 access → require_auth（Bearer 路径）
        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {new_access}"}

        @require_auth
        def _h(**kwargs):
            return {"ok": True}, 200

        assert _h(method="GET", path_tail="x", body={}, query={},
                  handler=handler)[1] == 200
        # 新 access → session（cookie 路径）
        h2 = _make_mock_handler(
            headers={"Content-Length": "0", "Cookie": f"yuleosh_at={new_access}"},
            method="GET")
        with mock.patch("yuleosh.ui.auth_extended.handle_session_info") as m:
            m.return_value = ({"user_id": 1, "email": "x"}, 200)
            handle_api_action(h2, "session")
        assert m.call_args[0][0] == new_access

    def test_bearer_refresh_for_api_clients(self):
        """T1.7 — 非浏览器客户端可经 Bearer 携带 refresh token."""
        from yuleosh.ui.routes.auth_routes import handle_api_action
        _store, _access, refresh = _seed_pair()
        handler = _make_mock_handler(
            headers={"Content-Length": "2",
                     "Authorization": f"Bearer {refresh}"})
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh",
                        return_value=({"token": "a", "refresh_token": "r"}, 200)):
            handle_api_action(handler, "refresh")
        # 无 yuleosh_rt cookie → 走 Bearer
        assert len(_set_cookie_calls(handler)) == 2
