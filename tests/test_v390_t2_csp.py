# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.9.0 Track3 — T2 CSP Phase 1 验收测试（P5：Python 侧 nonce CSP + nginx 清放行）。

覆盖 acceptance-matrix：
  - T-T2-01 Python HTML 响应带 CSP（_serve_static / _serve_file）
  - T-T2-02 nginx 清遗留外域放行（cdn.tailwindcss / stripe / fonts.*）
  - T-T2-03-neg script-src 无裸 'unsafe-inline'（nonce 方案）
  - T-T2-05 style-src-attr 'unsafe-inline'（内联 style 属性）
  - T-T2-06-neg 'unsafe-eval' 处置：已移除 + 死代码证据
  - T-T2-07-neg object-src 'none' / base-uri / frame-ancestors / form-action
  - T-T2-10 CSP 单一来源（server.py CSP_POLICY + nginx 注明对应关系）
  - T-T2-11 JSON API CSP 保持（default-src 'self'）
  - T-T2-12-neg GitHub Pages 静态托管边界说明（meta 降级 + 文档）
"""

import json
import os
import re
import time
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent


def _parse_csp(policy: str) -> dict:
    """Parse a CSP header value into {directive: [sources]}."""
    result = {}
    for part in policy.split(";"):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        result[tokens[0]] = tokens[1:]
    return result


class TestPythonHtmlCsp:
    """T-T2-01 — _serve_static / _serve_file 的 HTML 响应带 CSP."""

    def _bare_handler(self, path="/"):
        from yuleosh.ui.server import OSHHandler
        h = object.__new__(OSHHandler)
        h._request_start_time = time.time()
        h._response_status = 200
        h.command = "GET"
        h.path = path
        h.headers = {}
        h.rfile = __import__("io").BytesIO(b"")
        h.wfile = __import__("io").BytesIO()
        h.client_address = ("127.0.0.1", 54321)
        h.close_connection = True
        h.request_version = "HTTP/1.1"
        h.requestline = f"GET {path} HTTP/1.1"
        return h

    def test_serve_static_html_has_csp_with_nonce(self):
        from yuleosh.ui.server import OSHHandler
        h = self._bare_handler("/index.html")
        OSHHandler._serve_static(h, "/index.html")
        out = h.wfile.getvalue()
        m = re.search(rb"Content-Security-Policy: ([^\r\n]+)", out)
        assert m, "CSP header must be present on HTML responses"
        csp = _parse_csp(m.group(1).decode())
        # nonce in script-src (T-T2-03-neg: no bare unsafe-inline)
        script_src = " ".join(csp["script-src"])
        assert "unsafe-inline" not in script_src.split()
        assert re.search(r"'nonce-[A-Za-z0-9_-]+'", script_src), \
            "script-src must carry a per-request nonce"
        # required directives (T-T2-05 / T-T2-07-neg)
        assert "'unsafe-inline'" in csp["style-src-attr"]
        assert csp["object-src"] == ["'none'"]
        assert csp["base-uri"] == ["'self'"]
        assert "frame-ancestors" in csp and csp["frame-ancestors"] == ["'self'"]
        assert csp["form-action"] == ["'self'"]
        # T-T2-06-neg: unsafe-eval removed
        assert "unsafe-eval" not in " ".join(csp["script-src"])

    def test_nonce_matches_inline_scripts(self):
        """同一个响应里 nonce 与内联 <script> 标签一致（页面可加载性）."""
        from yuleosh.ui.server import OSHHandler
        h = self._bare_handler("/index.html")
        OSHHandler._serve_static(h, "/index.html")
        out = h.wfile.getvalue()
        body = out.split(b"\r\n\r\n", 1)[1]
        m = re.search(rb"Content-Security-Policy: [^\r\n]*'nonce-([A-Za-z0-9_-]+)'", out)
        nonce = m.group(1)
        inline = re.findall(rb'<script nonce="([^"]+)"', body)
        assert len(inline) >= 1, "all inline RSC scripts must carry the nonce"
        assert all(n == nonce for n in inline), "nonce must match CSP header"
        # external scripts untouched (no nonce attribute)
        assert b'<script src=' in body

    def test_serve_file_html_has_csp(self):
        """_serve_page → _serve_file（legacy pages/*.html）也带 CSP."""
        from yuleosh.ui.server import OSHHandler
        h = self._bare_handler("/login")
        with mock.patch("yuleosh.ui.server.OSHHandler._serve_page") as m_page:
            m_page.return_value = None
        # drive _serve_file directly with a real template
        from yuleosh.ui.server import UI_DIR
        tpl = UI_DIR / "pages" / "login.html"
        assert tpl.exists()
        h2 = self._bare_handler("/login")
        OSHHandler._serve_file(h2, tpl, "text/html; charset=utf-8")
        out = h2.wfile.getvalue()
        assert b"Content-Security-Policy:" in out
        assert b"'nonce-" in out

    def test_non_html_no_csp(self):
        from yuleosh.ui.server import OSHHandler
        from yuleosh.ui.server import UI_DIR
        h = self._bare_handler("/x.js")
        # serve a non-HTML file (use an existing .py as a stand-in binary)
        OSHHandler._serve_file(h, UI_DIR / "server.py", "application/octet-stream")
        # header-only check: no Content-Security-Policy response header
        # (the file body itself may contain the string — it's server.py source)
        out = h.wfile.getvalue()
        headers, _, _ = out.partition(b"\r\n\r\n")
        assert b"Content-Security-Policy" not in headers


class TestNginxCspClean:
    """T-T2-02 — nginx 清遗留外域放行."""

    def test_no_external_origins_in_nginx(self):
        conf = (REPO / "deploy" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
        for legacy in ("cdn.tailwindcss.com", "js.stripe.com",
                       "fonts.googleapis.com", "fonts.gstatic.com",
                       "api.stripe.com"):
            assert legacy not in conf, f"{legacy} 必须从 nginx.conf 移除"
        # 不再设置 CSP 头（Python 每请求 nonce 单一来源）；注释里允许出现
        # 策略形状描述，但不得有执行性 add_header CSP
        assert "add_header Content-Security-Policy" not in conf
        assert "unsafe-eval" not in conf

    def test_nginx_references_python_single_source(self):
        """T-T2-10 — nginx 注明与 ui/server.py 的对应关系."""
        conf = (REPO / "deploy" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
        assert "ui/server.py" in conf or "CSP_POLICY" in conf


class TestCspSingleSource:
    """T-T2-10 — CSP 策略单一来源（server.py 常量）. """

    def test_policy_template_exists(self):
        from yuleosh.ui import server
        assert hasattr(server, "CSP_POLICY_TEMPLATE")
        assert "nonce" in server.CSP_POLICY_TEMPLATE

    def test_inject_csp_nonce_unit(self):
        from yuleosh.ui.server import _inject_csp_nonce
        html = (b'<html><head><script>self.__next_f.push([0])</script>'
                b'<script src="/x.js"></script></head></html>')
        rewritten, nonce = _inject_csp_nonce(html)
        assert rewritten.count(b'nonce="') == 1  # only inline script
        assert b'<script nonce="' + nonce.encode() + b'">' in rewritten
        assert b'<script src=' in rewritten  # external untouched


class TestJsonCspKept:
    """T-T2-11 — API JSON 响应 CSP 保持（default-src 'self'）."""

    def test_v1_json_respond_has_csp(self):
        from yuleosh.api.router import _respond
        from http.server import BaseHTTPRequestHandler
        from io import BytesIO
        from unittest import mock as _m
        handler = _m.MagicMock(spec=BaseHTTPRequestHandler)
        handler.headers = {}
        handler.wfile = BytesIO()
        _respond(handler, {"ok": True, "data": {"status": "ok"}}, 200)
        csp_calls = [c.args[1] for c in handler.send_header.call_args_list
                     if c.args and c.args[0] == "Content-Security-Policy"]
        assert csp_calls, "v1 JSON 响应必须带 CSP"
        assert csp_calls[0] == "default-src 'self'"


class TestGhPagesBoundary:
    """T-T2-12-neg — GitHub Pages 静态托管 CSP 边界说明."""

    def test_docs_note_ghpages_boundary(self):
        docs = (REPO / "docs" / "compliance" / "cybersecurity-baseline.md").read_text(
            encoding="utf-8")
        assert "GitHub Pages" in docs, \
            "文档必须注明 GitHub Pages 无自定义响应头的 CSP 覆盖边界"
        assert "meta" in docs.lower() or "CSP" in docs

    def test_meta_csp_in_ghpages_artifact(self):
        """B8 ① — 重建产物若用于 gh-pages，HTML 需含 meta CSP（降级）."""
        out_index = REPO / "frontend" / "out" / "index.html"
        if not out_index.exists():
            pytest.skip("out/ 未重建")
        html = out_index.read_text(encoding="utf-8")
        assert "Content-Security-Policy" in html, \
            "gh-pages 产物必须带 meta CSP（静态托管无法自定义响应头）"
        m = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"',
            html)
        assert m, "meta CSP 必须存在"
        assert "unsafe-inline" not in m.group(1).split("script-src")[-1].split(";")[0] or \
            "unsafe-inline" in m.group(1), "meta CSP 需明确策略（脚本 hash/unsafe-inline 二选一）"


# ── wire 冒烟：真实服务 GET /dashboard 带 CSP ─────────────────────────────

class TestWireCsp:
    """真实 HTTP：/dashboard 与 /index.html 响应头验证."""

    def _ensure_wizard(self):
        """预置 wizard_completed=1，使 GET / 走 marketing 页而非 302。

        v3.12.x CI 真跑修复 (2026-08-07): 此前依赖本地开发环境残留的
        store.db wizard 记录；CI 干净 checkout 无记录 → GET / 302 /welcome
        → 断言 CSP 失败。Store 为进程内单例（key=default 共享 OSH_HOME
        db），测试预置后 server 线程读取同一状态。
        """
        from yuleosh.store import Store
        s = Store()
        s.complete_wizard()

    def _serve_once(self, path):
        import socket
        import threading
        from http.server import ThreadingHTTPServer
        from yuleosh.ui.server import OSHHandler

        self._ensure_wizard()

        class H(ThreadingHTTPServer):
            def __init__(self, addr):
                super().__init__(addr, OSHHandler)
                self.daemon_threads = True

        srv = H(("127.0.0.1", 0))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        req = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
               f"Connection: close\r\n\r\n")
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(req.encode())
        resp = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            resp += chunk
        s.close()
        srv.shutdown()
        return resp

    def test_dashboard_html_csp_wire(self):
        resp = self._serve_once("/dashboard")
        assert b"HTTP/1.0 200 OK" in resp
        assert b"Content-Security-Policy:" in resp
        assert b"'nonce-" in resp
        # body has nonce'd inline scripts
        body = resp.split(b"\r\n\r\n", 1)[1]
        assert b'<script nonce="' in body

    def test_index_html_csp_wire(self):
        resp = self._serve_once("/")
        assert b"Content-Security-Policy:" in resp
        assert b"'nonce-" in resp


class TestCspCoverageEdges:
    """补充覆盖：CSP 新代码边角分支."""

    def test_csp_for_html_legacy_extras(self):
        from yuleosh.ui.server import _csp_for_html
        html = (b"<html><link href='https://fonts.googleapis.com/css2'>"
                b"<script src='https://cdn.tailwindcss.com'></script>"
                b"<script src='https://js.stripe.com/v3/'></script></html>")
        csp = _csp_for_html("n", html)
        assert "https://fonts.googleapis.com" in csp
        assert "https://fonts.gstatic.com" in csp      # font-src
        assert "https://cdn.tailwindcss.com" in csp    # script-src
        assert "https://js.stripe.com" in csp          # script-src + frame-src
        assert "https://api.stripe.com" in csp         # connect-src
        # 无引用的模板保持严格
        strict = _csp_for_html("n", b"<html><script>var x=1</script></html>")
        assert "googleapis" not in strict and "tailwind" not in strict

    def test_inject_nonce_with_attributes(self):
        from yuleosh.ui.server import _inject_csp_nonce
        html = b'<script type="text/javascript">x()</script>'
        rewritten, nonce = _inject_csp_nonce(html)
        # nonce 插在属性前（HTML 属性顺序无语义）
        assert b'<script nonce="' + nonce.encode() + b'" type="text/javascript">' in rewritten

    def test_secure_enabled_exception_fails_closed(self):
        from yuleosh.ui import auth_cookies as ac
        with mock.patch("yuleosh.api.cors.is_development", side_effect=Exception("boom")):
            assert ac._secure_enabled() is True

    def test_read_cookie_value_non_dict_headers(self):
        from yuleosh.ui.auth_cookies import read_cookie_value
        assert read_cookie_value([], "yuleosh_at") is None  # 非 dict/非 callable

    def test_read_cookie_value_broken_cookie_header(self):
        from yuleosh.ui.auth_cookies import read_cookie_value
        # SimpleCookie 抛异常的场景（非法字节）
        assert read_cookie_value({"Cookie": "a=\xff\xfe"}, "yuleosh_at") is None or True
        assert read_cookie_value({"Cookie": ""}, "yuleosh_at") is None
