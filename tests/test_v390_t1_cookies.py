# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""v3.9.0 Track3 — T1 双 cookie 下发验收测试（P1：签发时下发 access/refresh + logout 清除）。

覆盖 acceptance-matrix：
  - T-T1-01 signin 下发双 cookie（yuleosh_at + yuleosh_rt，HttpOnly; SameSite=Lax; Path=/）
  - T-T1-02 org/create 下发双 cookie
  - T-T1-03 v1 register 下发双 cookie（router._respond 通道）
  - T-T1-13 logout 清除双 cookie（Max-Age=0）
  - T-T1-22 httpOnly 属性断言
  - T-T1-15 access 短期化（ACCESS_TTL_HOURS=0.5h / refresh 7d）
  - refresh 不可当 Bearer 用（verify_token / get_session_user 拒绝 purpose=refresh）
  - JSON body 契约保持（refresh_token 不下发到 wire）
  - 回归：_handle_api 单响应修复（不再双响应拼接）
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_mock_handler(headers=None, path="/", method="GET", body=b""):
    """Minimal mock BaseHTTPRequestHandler (mirrors test_ui_routes_ext)."""
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


def _set_cookie_calls(handler):
    """Extract (name, value) pairs from send_header calls named Set-Cookie."""
    return [
        (c.args[0], c.args[1])
        for c in handler.send_header.call_args_list
        if c.args and c.args[0] == "Set-Cookie"
    ]


def _parse_set_cookie(value: str) -> dict:
    """Parse a single Set-Cookie header value into attrs."""
    parts = value.split("; ")
    first = parts[0].split("=", 1)
    attrs = {"name": first[0], "value": first[1] if len(first) > 1 else ""}
    for p in parts[1:]:
        if p in ("HttpOnly", "Secure"):
            attrs[p.lower()] = True
        elif p.startswith("Max-Age="):
            attrs["max_age"] = int(p.split("=", 1)[1])
        elif p.startswith("SameSite="):
            attrs["samesite"] = p.split("=", 1)[1]
        elif p.startswith("Path="):
            attrs["path"] = p.split("=", 1)[1]
    return attrs


# ── T1.1 双 cookie 下发 ──────────────────────────────────────────────────

class TestSigninSetsCookies:
    """T-T1-01 — signin 成功下发 access + refresh 双 httpOnly cookie."""

    def test_signin_issues_dual_cookies(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        body = json.dumps({"email": "alice@t.com", "password": "Secret1!"}).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body)), "Content-Type": "application/json"},
            method="POST", body=body)
        result = {"token": "at.jwt.value", "refresh_token": "rt.jwt.value",
                  "redirect": "/project/select", "user_id": 1, "org_id": 1}
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=(result, 200)):
            handle_api_action(handler, "signin")

        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        names = {_parse_set_cookie(v)["name"] for _, v in cookies}
        assert names == {"yuleosh_at", "yuleosh_rt"}
        # HttpOnly + SameSite=Lax + Path=/ on BOTH cookies (T-T1-22)
        for _, v in cookies:
            attrs = _parse_set_cookie(v)
            assert attrs["httponly"] is True
            assert attrs["samesite"] == "Lax"
            assert attrs["path"] == "/"
            assert attrs["max_age"] > 0

    def test_signin_body_keeps_refresh_token_off_the_wire(self):
        """T-T1-01 neg：refresh_token 只在 cookie，不进 JSON body."""
        from yuleosh.ui.routes.auth_routes import handle_api_action
        body = json.dumps({"email": "bob@t.com", "password": "Secret1!"}).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body))}, method="POST", body=body)
        result = {"token": "at", "refresh_token": "rt", "user_id": 1, "org_id": 1}
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=(result, 200)):
            handle_api_action(handler, "signin")
        written = handler.wfile.getvalue().decode()
        assert "rt" not in written
        assert '"token": "at"' in written or "at" in written

    def test_signin_failure_no_cookies(self):
        """负例：登录失败（401）不得下发 cookie."""
        from yuleosh.ui.routes.auth_routes import handle_api_action
        body = json.dumps({"email": "x@t.com", "password": "bad"}).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body))}, method="POST", body=body)
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=({"error": "Invalid email or password"}, 401)):
            handle_api_action(handler, "signin")
        assert _set_cookie_calls(handler) == []


class TestOrgCreateSetsCookies:
    """T-T1-02 — org/create 成功下发双 cookie."""

    def test_org_create_issues_dual_cookies(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        body = json.dumps({
            "org_name": "Acme", "org_slug": "acme", "project_name": "P",
            "project_slug": "p", "email": "a@t.com", "password": "Secret1!",
        }).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body)),
                     "Authorization": "Bearer org-setup-token"},
            method="POST", body=body)
        result = {"token": "at2", "refresh_token": "rt2", "org_id": 9,
                  "org_slug": "acme", "redirect": "/project/select"}
        with mock.patch("yuleosh.ui.auth_extended.handle_org_create",
                        return_value=(result, 200)):
            handle_api_action(handler, "org_create")

        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        assert {_parse_set_cookie(v)["name"] for _, v in cookies} == {
            "yuleosh_at", "yuleosh_rt"}


class TestV1RegisterSetsCookies:
    """T-T1-03 — v1 register 经 router._respond 下发双 cookie."""

    def _call_respond(self, data, status=200):
        handler = _make_mock_handler(headers={})
        from yuleosh.api.router import _respond
        _respond(handler, data, status)
        return handler

    def test_register_emits_cookies_and_strips_marker(self):
        payload = {
            "ok": True,
            "data": {"token": "v1-at", "user": {"id": 1, "email": "a@t.com"}},
            "_auth_refresh_token": "v1-rt",
        }
        handler = self._call_respond(payload)
        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        names = {_parse_set_cookie(v)["name"] for _, v in cookies}
        assert names == {"yuleosh_at", "yuleosh_rt"}
        # marker stripped — never serialized
        assert handler.wfile.getvalue().decode() == json.dumps(
            {"ok": True, "data": {"token": "v1-at", "user": {"id": 1, "email": "a@t.com"}}},
            indent=2, ensure_ascii=False)

    def test_non_auth_response_no_cookies(self):
        handler = self._call_respond({"ok": True, "data": {"status": "ok"}})
        assert _set_cookie_calls(handler) == []


class TestLogoutClearsCookies:
    """T-T1-13 — logout 清除双 cookie（Max-Age=0）."""

    def test_logout_sends_clear_cookies(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        handler = _make_mock_handler(
            headers={"Content-Length": "2"}, method="POST", body=b"{}")
        with mock.patch("yuleosh.ui.auth_extended.handle_logout",
                        return_value=({"status": "ok"}, 200)):
            handle_api_action(handler, "logout")

        cookies = _set_cookie_calls(handler)
        assert len(cookies) == 2
        for _, v in cookies:
            attrs = _parse_set_cookie(v)
            assert attrs["name"] in ("yuleosh_at", "yuleosh_rt")
            assert attrs["value"] == ""
            assert attrs["max_age"] == 0


# ── T1.2 TTL 与 token 语义 ───────────────────────────────────────────────

class TestTokenPairSemantics:
    """T-T1-15 + refresh 不可当 Bearer（verify/get_session_user 拒绝）."""

    def _seed_user_and_pair(self):
        from yuleosh.store import Store
        from yuleosh.ui.auth_extended import _issue_token_pair
        import uuid as _uuid
        Store.reset()
        store = Store()
        uid = _uuid.uuid4().hex[:10]
        org = store.create_organization("Pair", f"pair-{uid}")
        user = store.create_user(org["id"], f"pair-{uid}@t.com")
        access, refresh = _issue_token_pair(store, user["id"], org["id"], user["email"])
        return store, access, refresh

    def test_pair_ttls(self):
        from yuleosh.ui.auth_extended import _decode_token
        _, access, refresh = self._seed_user_and_pair()
        p_a = _decode_token(access)
        p_r = _decode_token(refresh)
        # access ≈ 30min, refresh ≈ 7d (T-T1-15)
        assert abs((p_a["exp"] - p_a["iat"]) - 1800) < 60
        assert abs((p_r["exp"] - p_r["iat"]) - 168 * 3600) < 60
        assert p_r.get("purpose") == "refresh"
        assert p_a.get("purpose") is None

    def test_refresh_never_authenticates(self):
        from yuleosh.ui.auth_extended import verify_token, get_session_user
        _, access, refresh = self._seed_user_and_pair()
        # access works on both verify paths
        assert verify_token(access) is not None
        assert get_session_user(access) is not None
        # refresh is rejected everywhere (SHALL-T1.4/T1.5, T-T1-07 neg)
        assert verify_token(refresh) is None
        assert get_session_user(refresh) is None

    def test_default_generate_token_ttl_unchanged(self):
        """既有契约：_generate_token() 默认仍 72h（test_jwt_auth 依赖）."""
        from yuleosh.ui.auth_extended import _generate_token, _decode_token
        p = _decode_token(_generate_token(user_id=1))
        assert abs((p["exp"] - p["iat"]) - 72 * 3600) < 60


class TestCookiePolicyModule:
    """auth_cookies 单一来源（T-T1-22 / T-T2-10 同源思路）."""

    def test_cookie_names_and_ttl_constants(self):
        from yuleosh.ui import auth_cookies as ac
        assert ac.ACCESS_COOKIE_NAME == "yuleosh_at"
        assert ac.REFRESH_COOKIE_NAME == "yuleosh_rt"
        assert ac.ACCESS_TTL_HOURS <= 72          # 显著短于 legacy 72h
        assert ac.ACCESS_TTL_HOURS <= 0.5         # 建议 ≤30min
        assert ac.REFRESH_TTL_HOURS >= ac.ACCESS_TTL_HOURS
        # 不与 legacy osh_session 冲突（T1.8）
        assert "osh_session" not in (ac.ACCESS_COOKIE_NAME, ac.REFRESH_COOKIE_NAME)

    def test_make_auth_cookie_attrs(self):
        from yuleosh.ui.auth_cookies import make_auth_cookie
        with mock.patch("yuleosh.ui.auth_cookies._secure_enabled", return_value=False):
            v = make_auth_cookie("yuleosh_at", "tok", 1800)
        attrs = _parse_set_cookie(v)
        assert attrs["name"] == "yuleosh_at"
        assert attrs["value"] == "tok"
        assert attrs["httponly"] is True
        assert attrs["samesite"] == "Lax"
        assert attrs["path"] == "/"
        assert attrs["max_age"] == 1800

    def test_clear_cookie_headers_max_age_zero(self):
        from yuleosh.ui.auth_cookies import clear_cookie_headers
        with mock.patch("yuleosh.ui.auth_cookies._secure_enabled", return_value=False):
            headers = clear_cookie_headers()
        assert len(headers) == 2
        for v in headers:
            assert _parse_set_cookie(v)["max_age"] == 0


# ── 回归：_handle_api 单响应修复 ─────────────────────────────────────────

class TestHandleApiSingleResponse:
    """回归：_handle_api 不再二次 _json_response（wire 双响应修复）."""

    def _bare_handler(self):
        from yuleosh.ui.server import OSHHandler
        h = object.__new__(OSHHandler)
        h._request_start_time = time.time()
        h._response_status = 200
        h.command = "POST"
        h.path = "/api/auth/signin"
        h.headers = {"Content-Length": "2"}
        h.rfile = BytesIO(b"{}")
        h.wfile = BytesIO()
        h.client_address = ("127.0.0.1", 54321)
        h.close_connection = True
        h.request_version = "HTTP/1.1"
        h.requestline = "POST /api/auth/signin HTTP/1.1"
        return h

    def test_handle_api_sends_single_response(self):
        from yuleosh.ui.server import OSHHandler
        h = self._bare_handler()
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=({"status": "ok"}, 200)):
            OSHHandler._handle_api(h, "signin")
        out = h.wfile.getvalue()
        assert out.count(b"HTTP/1.0") == 1, "must be exactly one HTTP response"
        assert out.count(b"null") == 0

    def test_handle_api_signin_emits_set_cookie_on_wire(self):
        """真实 handler：signin 成功 → 响应含 2 个 Set-Cookie（wire 级）."""
        from yuleosh.ui.server import OSHHandler
        from yuleosh.ui.auth_extended import _create_login_response
        h = self._bare_handler()
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=({"token": "w-at", "refresh_token": "w-rt",
                                       "redirect": "/x"}, 200)):
            OSHHandler._handle_api(h, "signin")
        out = h.wfile.getvalue()
        assert out.count(b"Set-Cookie: yuleosh_at=") == 1
        assert out.count(b"Set-Cookie: yuleosh_rt=") == 1
        assert out.count(b"HTTP/1.0") == 1


# ── 集成：真实登录链 signin→org/create wire 冒烟 ─────────────────────────

class TestSigninOrgCreateWire:
    """端到端（逻辑级）signin(needs_org) → org/create 双 cookie."""

    def test_chain_signin_orgcreate(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        from yuleosh.ui.auth_cookies import ACCESS_COOKIE_NAME
        # signin（新用户 → needs_org：org_setup token 进 yuleosh_at cookie，
        # 使后续 org/create 纯 cookie 可用 — T-T1-19）
        email = f"chain.{int(time.time())}@t.com"
        body = json.dumps({"email": email, "password": "TestPass123!"}).encode()
        h1 = _make_mock_handler(headers={"Content-Length": str(len(body))},
                                method="POST", body=body)
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=({"token": "setup-jwt", "redirect": "/org/setup",
                                       "needs_org": True}, 200)):
            handle_api_action(h1, "signin")
        cookies = _set_cookie_calls(h1)
        assert len(cookies) == 1  # 仅 access 槽位放 org_setup token（无 user 会话）
        attrs = _parse_set_cookie(cookies[0][1])
        assert attrs["name"] == ACCESS_COOKIE_NAME
        assert attrs["value"] == "setup-jwt"
        assert attrs["httponly"] is True
        assert attrs["max_age"] == 1800

        # org/create（真实 store 流程 → 双 cookie）
        from yuleosh.store import Store
        Store.reset()
        body2 = json.dumps({
            "org_name": "ChainOrg", "org_slug": f"chainorg{int(time.time())}",
            "project_name": "P", "project_slug": "p", "email": email,
            "password": "TestPass123!",
        }).encode()
        h2 = _make_mock_handler(
            headers={"Content-Length": str(len(body2)),
                     "Cookie": f"{ACCESS_COOKIE_NAME}=setup-jwt"},
            method="POST", body=body2)
        # 真实 handle_org_create：org_setup token 需与 email 匹配 —— 用真实实现
        from yuleosh.ui.auth_extended import handle_org_create, _generate_token
        setup = _generate_token(email=email, purpose="org_setup")
        result, status = handle_org_create(json.loads(body2), setup)
        assert status == 200
        assert "token" in result and result.get("refresh_token")
        with mock.patch("yuleosh.ui.auth_extended.handle_org_create",
                        return_value=(result, 200)):
            handle_api_action(h2, "org_create")
        cookies = _set_cookie_calls(h2)
        assert len(cookies) == 2
        assert {_parse_set_cookie(v)["name"] for _, v in cookies} == {
            "yuleosh_at", "yuleosh_rt"}
        # body 无 refresh_token（cookie-only）
        assert "refresh_token" not in h2.wfile.getvalue().decode()
