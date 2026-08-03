# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.8.0 Track2 — A3 路由去 legacy 双轨验收测试（acceptance-matrix T-A3-*）。

覆盖:
  - T-A3-01..12 tenant/billing/projects/audit 新式路由响应契约
  - T-A3-13-neg 未知资源 404
  - T-A3-14-neg _dispatch_legacy 删除
  - T-A3-15-neg handler_helpers 死分支删除
  - T-A3-16-neg body 超限 400
  - T-A3-17 鉴权等价
"""

import json
from pathlib import Path
from unittest import mock

import pytest


def _make_handler(headers=None, method="GET", path="/api/v1/health",
                  body=None):
    """Build a mock handler with router plumbing."""
    from http.server import BaseHTTPRequestHandler
    h = mock.MagicMock(spec=BaseHTTPRequestHandler)
    h.command = method
    h.path = path
    h.client_address = ("127.0.0.1", 12345)
    h._request_start_time = 0.0
    data = json.dumps(body).encode() if body is not None else b""

    class _Headers(dict):
        def get(self, k, d=""):
            if k == "Content-Length":
                return str(len(data))
            return dict.get(self, k, d)

    h.headers = _Headers(headers or {})
    h.rfile = __import__("io").BytesIO(data)
    h.wfile = __import__("io").BytesIO()
    return h


def _call_dispatch(path: str, method: str = "GET", headers=None, body=None):
    from yuleosh.api.router import dispatch
    h = _make_handler(headers=headers, method=method, path=path, body=body)
    dispatch(h, path)
    payload = json.loads(h.wfile.getvalue().decode() or "{}")
    status = h.send_response.call_args[0][0] if h.send_response.called else 200
    return payload, status


def _seed_user(role: str = "admin", org_slug: str = "test-org"):
    """Seed a user + session; return (token, user_id)."""
    from yuleosh.store import Store, _session_token_hash
    from datetime import datetime, timedelta
    from yuleosh.ui.auth_extended import _generate_token
    import uuid as _uuid
    store = Store()
    uid = int(_uuid.uuid4().int % 1_000_000_000) + 300_000_000
    email = f"a3-{uid}@test.com"
    store.conn.execute(
        "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (uid, 1, email, role, datetime.now().isoformat()),
    )
    token = _generate_token(user_id=uid, org_id=1, email=email)
    store.conn.execute(
        "INSERT OR IGNORE INTO user_sessions (user_id, token, created_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (uid, _session_token_hash(token), datetime.now().isoformat(),
         (datetime.now() + timedelta(hours=72)).isoformat()),
    )
    store.conn.commit()
    return token, uid


def _authed_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


class TestA3RoutesMigrated:
    """T-A3-01..12 — 迁移后的路由仍可达且契约一致."""

    @pytest.mark.parametrize("path", [
        "/api/v1/tenant/acme",
        "/api/v1/tenant/acme/projects",
        "/api/v1/tenant/acme/usage",
        "/api/v1/tenants",
        "/api/v1/billing/usage",
        "/api/v1/billing/plan",
        "/api/v1/projects/xyz",
        "/api/v1/audit",
    ])
    def test_routes_not_404_unauthenticated(self, path):
        """无凭据访问迁移路由 → 401（不再 404，不再走 legacy 404 页）."""
        payload, status = _call_dispatch(path, "GET")
        assert status == 401, f"{path}: {status} {payload}"

    def test_unknown_resource_404(self):
        """T-A3-13-neg: 未知资源 → 404 Unknown resource."""
        payload, status = _call_dispatch("/api/v1/definitely-unknown")
        assert status == 404
        assert "Unknown resource" in payload["error"]

    def test_audit_served_by_handle_audit(self):
        """T-A3-12: /api/v1/audit 仅由 handle_audit 服务（POST 405）."""
        token, _ = _seed_user("admin")
        payload, status = _call_dispatch(
            "/api/v1/audit", "POST", _authed_headers(token), {})
        assert status == 405


class TestA3NoLegacyDispatch:
    """T-A3-14/15-neg — 架构债消失证据."""

    def test_dispatch_legacy_gone(self):
        src_root = Path(__file__).resolve().parent.parent / "src"
        hits = []
        for p in src_root.rglob("*.py"):
            for i, line in enumerate(
                    p.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s.startswith("def _dispatch_legacy") or \
                        "_dispatch_legacy(" in s:
                    hits.append(f"{p.relative_to(src_root.parent)}:{i}")
        assert hits == [], f"_dispatch_legacy 残留: {hits}"

    def test_handler_helpers_dead_branches_gone(self):
        p = Path(__file__).resolve().parent.parent / \
            "src/yuleosh/ui/routes/handler_helpers.py"
        text = p.read_text(encoding="utf-8")
        for dead in ('path.startswith("/api/v1/tenant/")',
                     'path == "/api/v1/tenants"',
                     'path.startswith("/api/v1/projects/")',
                     'path == "/api/v1/audit"',
                     'path == "/api/v1/billing/usage"',
                     'path == "/api/v1/billing/plan"',
                     'path == "/api/v1/billing/upgrade"'):
            assert dead not in text, f"死分支残留: {dead}"


class TestA3BodyAndAuth:
    """T-A3-16/17 — body 统一读取 + 鉴权等价."""

    def test_oversize_body_400(self):
        """T-A3-16-neg: billing/upgrade 超 10MB body → 400 不 500."""
        from yuleosh.api.router import dispatch
        h = _make_handler(
            headers={"Authorization": "Bearer x",
                     "Content-Type": "application/json"},
            method="POST", path="/api/v1/billing/upgrade",
            body=None,
        )
        # Simulate an oversized Content-Length (router read_body clamps).
        class _Big(dict):
            def get(self, k, d=""):
                if k == "Content-Length":
                    return str(11 * 1024 * 1024)
                return dict.get(self, k, d)
        h.headers = _Big({"Authorization": "Bearer x",
                          "Content-Type": "application/json"})
        dispatch(h, "/api/v1/billing/upgrade")
        status = h.send_response.call_args[0][0] if h.send_response.called else 200
        assert status == 400

    def test_auth_equiv_require_auth(self):
        """T-A3-17: 同一 token 经新式 require_auth 判定与旧式一致.

        迁移后的 tenant 路由使用统一 get_session_user（与 A1 统一 verify
        同源）；同一合法 token 不再被一边接受一边拒绝。
        """
        token, uid = _seed_user("admin")
        from yuleosh.ui.auth_extended import get_session_user
        from yuleosh.api.middleware import require_auth

        # 旧式语义：get_session_user 直接解析
        u = get_session_user(token)
        assert u is not None and u["user_id"] == uid

        # 新式语义：require_auth（统一 verify）同样放行
        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}

        @require_auth
        def _h(**kwargs):
            return {"ok": True, "cu": kwargs["current_user"]}, 200

        result, code = _h(method="GET", path_tail="", body={}, query={},
                          handler=handler)
        assert code == 200
        assert result["cu"]["user_id"] == uid
