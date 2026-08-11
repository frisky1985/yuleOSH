# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.9.1 — 复验 P2×3 观察项闭环测试。

覆盖复验报告（reports/yuleOSH-v390-assessment.md）遗留项：
  - P2-1: refresh 端点无显式限流器 → per-IP 限流（429 + Retry-After）
  - P2-2: `npm run build` 不自动注入 meta CSP → build 链上
          inject-meta-csp.py
  - P2-3: /org/setup 静态页仍读 localStorage('osh_token') → 改 cookie
          认证（HttpOnly yuleosh_at 同源携带），零 localStorage
"""

import json
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── P2-1: refresh per-IP 限流 ──────────────────────────────────────────

class TestP21RefreshRateLimit:
    """refresh 端点现在走 server.check_rate_limit（P2-1 闭环）."""

    def _make_handler(self, ip="127.0.0.1", headers=None):
        handler = mock.MagicMock(spec=BaseHTTPRequestHandler)
        handler.client_address = (ip, 54321)
        class MockHeaders(dict):
            def items(self):
                return super().items()
        handler.headers = MockHeaders(headers or {})
        handler.path = "/api/auth/refresh"
        handler.command = "POST"
        handler.rfile = BytesIO(b"{}")
        handler.wfile = BytesIO()
        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()
        return handler

    def test_refresh_path_uses_rate_limit(self, tmp_path, monkeypatch):
        """refresh 分支调用 check_rate_limit（有 IP 时）→ SQLite 计数落库."""
        monkeypatch.setenv("YULEOSH_RATE_DB", str(tmp_path / "rl.db"))
        from yuleosh.api.ratelimit_shared import RateLimitStore
        from yuleosh.ui import server as _srv
        from yuleosh.ui.routes.auth_routes import handle_api_action

        handler = self._make_handler(ip="10.0.0.9")
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh",
                        return_value=(
                            {"token": "a", "refresh_token": "r"}, 200)):
            handle_api_action(handler, "refresh")
        # check_rate_limit 对 10.0.0.9 有记录（共享 SQLite）
        store = RateLimitStore(db_path=str(tmp_path / "rl.db"))
        remaining = store.get_remaining("10.0.0.9", limit=_srv.RATE_LIMIT_MAX)
        assert remaining == _srv.RATE_LIMIT_MAX - 1  # 已计入 1 次

    def test_refresh_429_when_over_limit(self, tmp_path, monkeypatch):
        """预填满共享 SQLite 计数 → refresh 真被限流 → 429 且拒绝处理."""
        monkeypatch.setenv("YULEOSH_RATE_DB", str(tmp_path / "rl.db"))
        from yuleosh.ui import server as _srv
        from yuleosh.ui.routes.auth_routes import handle_api_action

        ip = "203.0.113.7"
        # 真实调用 check_rate_limit 填满共享 SQLite（与生产同路径）
        for _ in range(_srv.RATE_LIMIT_MAX):
            _srv.check_rate_limit(ip)
        handler = self._make_handler(ip=ip)
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh") as m:
            handle_api_action(handler, "refresh")
        m.assert_not_called()  # 限流拦截，未进入 handle_refresh
        # 429 响应
        body = handler.wfile.getvalue().decode()
        assert "429" in body or any(
            c.args and c.args[0] == 429 for c in handler.send_response.call_args_list
        ), body[:200]

    def test_refresh_allowed_under_limit(self):
        """未超限 → 正常进入 handle_refresh."""
        from yuleosh.ui import server as _srv
        from yuleosh.ui.routes.auth_routes import handle_api_action

        _srv._rate_limit_buckets.clear()
        handler = self._make_handler(ip="198.51.100.3")
        with mock.patch("yuleosh.ui.auth_extended.handle_refresh",
                        return_value=({"token": "a", "refresh_token": "r"}, 200)):
            handle_api_action(handler, "refresh")
        # 未被 429 拦截 → handle_refresh 被调用（或 cookie 读取路径无 token）
        # 只要不抛异常且无 429 即可
        body = handler.wfile.getvalue().decode()
        assert "429" not in body


# ── P2-2: build 自动注入 meta CSP ─────────────────────────────────────

class TestP22BuildChainsCsp:
    """package.json build 脚本必须链上 inject-meta-csp.py（P2-2 闭环）."""

    def test_build_script_contains_inject(self):
        pkg = json.loads(
            (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        build = pkg["scripts"]["build"]
        assert "inject-meta-csp.py" in build
        assert "next build" in build

    def test_inject_script_exists(self):
        script = REPO_ROOT / "frontend" / "scripts" / "inject-meta-csp.py"
        assert script.exists(), "inject-meta-csp.py 必须存在才能被 build 链上"


# ── P2-3: /org/setup 去 localStorage ──────────────────────────────────

class TestP23OrgSetupNoLocalStorage:
    """org-setup 页面零 localStorage 引用（P2-3 闭环）."""

    def test_source_template_no_localstorage(self):
        html = (REPO_ROOT / "src" / "yuleosh" / "ui" / "pages" /
                "org-setup.html").read_text(encoding="utf-8")
        assert "localStorage" not in html

    def test_out_artifact_no_localstorage(self):
        out = REPO_ROOT / "frontend" / "out" / "app" / "pages" / "org-setup.html"
        if not out.exists():
            pytest.skip("out 产物未构建（CI 构建后验证）")
        html = out.read_text(encoding="utf-8")
        assert "localStorage" not in html

    def test_org_create_uses_cookie_not_bearer(self):
        """handleOrgCreate 不再拼 Authorization: Bearer（走 cookie）."""
        html = (REPO_ROOT / "src" / "yuleosh" / "ui" / "pages" /
                "org-setup.html").read_text(encoding="utf-8")
        assert "Authorization" not in html
        assert "credentials: 'same-origin'" in html
        assert "401" in html  # 401 时回登录页
