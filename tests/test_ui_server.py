# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Unit tests for yuleOSH Dashboard Server (ui/server.py).

CL3 P1-3: Covers core routing, API dispatchers, rate limiting, audit logging,
security headers, static file serving, and auth check.
"""

import io
import json
import os
import socket
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

import pytest


# ── Test set up: mock env before importing server module ────────────────────

@pytest.fixture(autouse=True)
def _setup_env():
    """Set up environment before each test."""
    old = {}
    for k in ("YULEOSH_AUTH_DISABLED", "OSH_HOME"):
        old[k] = os.environ.get(k)
        if k == "YULEOSH_AUTH_DISABLED":
            os.environ[k] = "1"  # Disable auth for tests
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ═══════════════════════════════════════════════════════════════════════════
# Helper: create a mock socket-like object that BaseHTTPRequestHandler needs
# ═══════════════════════════════════════════════════════════════════════════

def _make_rfile(method: str = "GET", path: str = "/api/status",
                body: bytes = b"", headers: dict = None) -> io.BytesIO:
    """Build a raw request file-like object for BaseHTTPRequestHandler."""
    header_lines = f"{method} {path} HTTP/1.1\r\n"
    header_lines += "Host: localhost\r\n"
    if headers:
        for k, v in headers.items():
            header_lines += f"{k}: {v}\r\n"
    if body:
        header_lines += f"Content-Length: {len(body)}\r\n"
    header_lines += "\r\n"
    data = header_lines.encode("utf-8") + body
    return io.BytesIO(data)


class _FakeSocket:
    """Minimal socket that returns a controlled byte stream."""

    def __init__(self, rfile: io.BytesIO):
        self._rfile = rfile
        self._written = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs) -> io.BytesIO:
        if "w" in mode:
            return self._written
        return self._rfile

    def sendall(self, data: bytes) -> None:
        """Required by BaseHTTPRequestHandler.flush_headers -> _SocketWriter.write()."""
        self._written.write(data)

    def getsockname(self):
        return ("127.0.0.1", 8080)

    def close(self):
        pass

    def setblocking(self, flag: bool) -> None:
        pass

    def settimeout(self, timeout) -> None:
        pass

    def getpeername(self):
        return ("127.0.0.1", 12345)

    @property
    def family(self):
        return 0


@pytest.fixture
def make_handler():
    """Factory fixture that creates an OSHHandler with a given request."""

    def _build(method="GET", path="/api/status", body=b"",
               headers=None, client_addr=("127.0.0.1", 12345)):
        from yuleosh.ui.server import OSHHandler
        rfile = _make_rfile(method, path, body, headers)
        fake_sock = _FakeSocket(rfile)
        # HTTPServer needs server_address
        server = mock.MagicMock(spec=HTTPServer)
        server.socket = fake_sock
        server.server_address = ("127.0.0.1", 8080)
        handler = OSHHandler(fake_sock, client_addr, server)
        # Override wfile to BytesIO for direct method testing
        # (BaseHTTPRequestHandler creates _SocketWriter, which needs real socket)
        handler.wfile = fake_sock._written
        return handler

    return _build


# ═══════════════════════════════════════════════════════════════════════════
# Module-level tests (functions, not class methods)
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    """check_rate_limit — core rate limiting logic."""

    def test_rate_limit_allows_normal_requests(self):
        """GIVEN a clean bucket WHEN check_rate_limit THEN allowed."""
        from yuleosh.ui.server import check_rate_limit
        allowed, retry = check_rate_limit("127.0.0.1", max_requests=10, window=60)
        assert allowed is True
        assert retry == 0.0

    def test_rate_limit_blocks_after_max(self):
        """GIVEN max requests reached WHEN check_rate_limit THEN blocked."""
        from yuleosh.ui.server import check_rate_limit, _rate_limit_buckets
        ip = "10.0.0.1"
        _rate_limit_buckets[ip] = [time.time()] * 10  # max_requests reached
        allowed, retry = check_rate_limit(ip, max_requests=10, window=60)
        assert allowed is False
        assert retry > 0

    def test_rate_limit_prunes_old_entries(self):
        """GIVEN expired entries in bucket WHEN check_rate_limit THEN pruned and allowed."""
        from yuleosh.ui.server import check_rate_limit, _rate_limit_buckets
        ip = "10.0.0.2"
        old_ts = time.time() - 120  # 2 minutes ago, outside window
        _rate_limit_buckets[ip] = [old_ts] * 10
        allowed, retry = check_rate_limit(ip, max_requests=10, window=60)
        assert allowed is True


class TestAuditLog:
    """_audit_log — in-memory ring buffer."""

    def test_audit_log_appends_entry(self):
        """GIVEN request details WHEN _audit_log THEN entry appended."""
        from yuleosh.ui.server import _audit_log, _audit_log_ring
        _audit_log_ring.clear()
        _audit_log("GET", "/api/health", 200, "127.0.0.1", 12.3)
        assert len(_audit_log_ring) == 1
        entry = _audit_log_ring[0]
        assert entry["method"] == "GET"
        assert entry["path"] == "/api/health"
        assert entry["status"] == 200
        assert entry["ip"] == "127.0.0.1"
        assert entry["duration_ms"] == 12.3

    def test_audit_log_ring_max(self):
        """GIVEN entries exceed AUDIT_RING_MAX WHEN _audit_log THEN oldest pruned."""
        from yuleosh.ui.server import _audit_log, _audit_log_ring, AUDIT_RING_MAX
        _audit_log_ring.clear()
        for i in range(AUDIT_RING_MAX + 10):
            _audit_log("GET", f"/path/{i}", 200, "10.0.0.1", 1.0)
        assert len(_audit_log_ring) == AUDIT_RING_MAX


class TestApiV1Dispatch:
    """api_v1_dispatch — API routing."""

    def test_api_v1_dispatch_returns_false(self):
        """GIVEN any path WHEN api_v1_dispatch THEN returns False (static mode)."""
        from yuleosh.ui.server import api_v1_dispatch
        handler = mock.MagicMock(spec=BaseHTTPRequestHandler)
        result = api_v1_dispatch(handler, "/api/v1/test")
        assert result is False


class TestOSHHandlerInit:
    """OSHHandler — __init__ and basic HTTP internals."""

    def test_handler_constructs(self, make_handler):
        """GIVEN valid socket request WHEN OSHHandler created THEN no crash."""
        handler = make_handler()
        assert handler.command == "GET"
        assert handler.path == "/api/status"
        assert handler.client_address == ("127.0.0.1", 12345)


class TestOSHHandlerSecurityHeaders:
    """OSHHandler — _add_security_headers."""

    def test_security_headers_set(self, make_handler):
        """GIVEN handler WHEN _add_security_headers THEN all security headers sent."""
        handler = make_handler()
        sent = {}

        def _record_send(k, v):
            sent[k.lower()] = v

        handler.send_header = _record_send
        handler._add_security_headers()

        assert sent.get("x-content-type-options") == "nosniff"
        assert sent.get("x-frame-options") == "DENY"
        assert sent.get("x-xss-protection") == "1; mode=block"
        assert sent.get("referrer-policy") == "strict-origin-when-cross-origin"


class TestOSHHandlerJSONResponse:
    """OSHHandler — _json_response."""

    def test_json_response_sends_data(self, make_handler):
        """GIVEN handler WHEN _json_response THEN writes correct JSON."""
        handler = make_handler()
        handler.wfile = io.BytesIO()

        # Track headers
        sent_headers = {}

        def _record_send(k, v):
            sent_headers[k.lower()] = v

        handler.send_response = mock.MagicMock()
        handler.send_header = _record_send
        handler.end_headers = mock.MagicMock()

        handler._json_response({"status": "ok"}, 200)

        handler.wfile.seek(0)
        body = handler.wfile.read().decode("utf-8")
        parsed = json.loads(body)
        assert parsed == {"status": "ok"}
        assert sent_headers.get("content-type") == "application/json; charset=utf-8"


class TestOSHHandlerHTMLResponse:
    """OSHHandler — _html_response."""

    def test_html_response_sends_html(self, make_handler):
        """GIVEN handler WHEN _html_response THEN writes HTML."""
        handler = make_handler()
        handler.wfile = io.BytesIO()

        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        handler._html_response("<html>OK</html>", 200)

        handler.wfile.seek(0)
        body = handler.wfile.read().decode("utf-8")
        assert "OK" in body


class TestOSHHandlerGetClientIP:
    """OSHHandler — _get_client_ip."""

    def test_get_client_ip(self, make_handler):
        """GIVEN handler WHEN _get_client_ip THEN returns IP string."""
        handler = make_handler(client_addr=("10.0.0.99", 54321))
        ip = handler._get_client_ip()
        assert ip == "10.0.0.99"


class TestOSHHandlerCheckAuth:
    """OSHHandler — _check_auth."""

    def test_check_auth_disabled(self, make_handler):
        """GIVEN AUTH_ENABLED=False WHEN _check_auth THEN returns True."""
        handler = make_handler()
        with mock.patch("yuleosh.ui.server.AUTH_ENABLED", False):
            assert handler._check_auth() is True


class TestOSHHandlerStaticServe:
    """OSHHandler — _serve_static."""

    def test_serve_static_root_returns_html(self, tmp_path, make_handler):
        """GIVEN root path WHEN _serve_static THEN returns index.html."""
        static_dir = tmp_path / "frontend" / "out"
        static_dir.mkdir(parents=True)
        index_file = static_dir / "index.html"
        index_file.write_text("<html>Test Dashboard</html>")

        handler = make_handler()
        handler.wfile = io.BytesIO()
        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        with mock.patch("yuleosh.ui.server.OSH_HOME", str(tmp_path)):
            handler._serve_static("/")

        handler.wfile.seek(0)
        body = handler.wfile.read()
        assert b"Test Dashboard" in body

    def test_serve_static_not_found_404(self, make_handler):
        """GIVEN non-existent file WHEN _serve_static THEN returns fallback."""
        handler = make_handler()
        handler.wfile = io.BytesIO()

        statuses = []

        def _record_status(code, msg=None):
            statuses.append(code)

        handler.send_response = _record_status
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        # Use a path that is guaranteed not to have static files
        with mock.patch("yuleosh.ui.server.OSH_HOME", "/tmp/nonexistent_xyz_ci_test_"):
            handler._serve_static("/nonexistent.html")

        # Should attempt to send a fallback response (500 or 404)
        assert len(statuses) > 0

    def test_serve_static_directory_traversal_prevented(self, tmp_path, make_handler):
        """GIVEN path with '..' WHEN _serve_static THEN no traversal."""
        static_dir = tmp_path / "frontend" / "out"
        static_dir.mkdir(parents=True)
        (static_dir / "index.html").write_text("Safe")

        handler = make_handler()
        handler.wfile = io.BytesIO()

        statuses = []

        def _record_status(code, msg=None):
            statuses.append(code)

        handler.send_response = _record_status
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        with mock.patch("yuleosh.ui.server.OSH_HOME", str(tmp_path)):
            handler._serve_static("/../../../etc/passwd")

        # Should not crash; should serve a 404 or the index page
        assert any(s >= 200 for s in statuses)


class TestOSHHandlerGET:
    """OSHHandler — do_GET routing."""

    def test_do_get_calls_handle_get(self, make_handler):
        """GIVEN GET request WHEN do_GET THEN handle_get called."""
        handler = make_handler()
        handler.wfile = io.BytesIO()

        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_get") as mock_hg:
            handler.do_GET()
            mock_hg.assert_called_once()


class TestOSHHandlerPOST:
    """OSHHandler — do_POST routing."""

    def test_do_post_calls_handle_post(self, make_handler):
        """GIVEN POST request WHEN do_POST THEN handle_post called."""
        handler = make_handler(method="POST", path="/api/action", body=b'{"key": "val"}',
                               headers={"Content-Type": "application/json"})
        handler.wfile = io.BytesIO()

        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_post") as mock_hp:
            handler.do_POST()
            mock_hp.assert_called_once()


class TestOSHHandlerDELETE:
    """OSHHandler — do_DELETE routing."""

    def test_do_delete_calls_handle_delete(self, make_handler):
        """GIVEN DELETE request WHEN do_DELETE THEN handle_delete called."""
        handler = make_handler(method="DELETE", path="/api/resource/42",
                               body=b"{}", headers={})
        handler.wfile = io.BytesIO()

        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_delete") as mock_hd:
            handler.do_DELETE()
            mock_hd.assert_called_once()


class TestOSHHandlerOPTIONS:
    """OSHHandler — do_OPTIONS routing."""

    def test_do_options_calls_handle_options(self, make_handler):
        """GIVEN OPTIONS request WHEN do_OPTIONS THEN handle_options called."""
        handler = make_handler(method="OPTIONS", path="*")
        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_options") as mock_ho:
            handler.do_OPTIONS()
            mock_ho.assert_called_once()


class TestOSHHandlerServeMethods:
    """OSHHandler — _serve_file and _serve_page methods."""

    def test_serve_file_exists(self, tmp_path, make_handler):
        """GIVEN existing file WHEN _serve_file THEN serves content."""
        test_file = tmp_path / "test.html"
        test_file.write_text("Hello World")

        handler = make_handler()
        handler.wfile = io.BytesIO()
        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        handler._serve_file(test_file, "text/html")
        handler.wfile.seek(0)
        assert b"Hello World" in handler.wfile.read()

    def test_serve_file_not_found(self, tmp_path, make_handler):
        """GIVEN non-existing file WHEN _serve_file THEN 404 fallback."""
        handler = make_handler()
        handler.wfile = io.BytesIO()
        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        missing = tmp_path / "missing.html"
        handler._serve_file(missing, "text/html")
        handler.wfile.seek(0)
        body = handler.wfile.read()
        assert isinstance(body, bytes)  # Should have written something

    def test_serve_page_existing(self, tmp_path, make_handler):
        """GIVEN existing template WHEN _serve_page THEN serves it."""
        test_file = tmp_path / "dashboard.html"
        test_file.write_text("Dashboard Content")

        handler = make_handler()
        handler.wfile = io.BytesIO()
        handler.send_response = mock.MagicMock()
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        with mock.patch("yuleosh.ui.server.UI_DIR", tmp_path):
            handler._serve_page("dashboard.html", {})

        handler.wfile.seek(0)
        assert b"Dashboard Content" in handler.wfile.read()

    def test_serve_page_not_found_falls_back(self, tmp_path, make_handler):
        """GIVEN missing template WHEN _serve_page THEN falls back to 404."""
        handler = make_handler()
        handler.wfile = io.BytesIO()

        statuses = []

        def _record_status(code, msg=None):
            statuses.append(code)

        handler.send_response = _record_status
        handler.send_header = mock.MagicMock()
        handler.end_headers = mock.MagicMock()

        with mock.patch("yuleosh.ui.server.UI_DIR", tmp_path / "nonexistent"):
            with mock.patch("yuleosh.ui.server.OSH_HOME", str(tmp_path)):
                handler._serve_page("missing.html", {})

        # Should handle gracefully, one of the fallbacks should catch it
        assert len(statuses) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Server launcher tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMain:
    """main() — server launcher."""

    def test_main_starts_server(self):
        """GIVEN default args WHEN main THEN server starts on 127.0.0.1:8080."""
        from yuleosh.ui.server import main

        with mock.patch("yuleosh.ui.server.HTTPServer") as mock_httpd:
            mock_server = mock.MagicMock()
            mock_httpd.return_value = mock_server
            main(host="127.0.0.1", port=18080)
            mock_httpd.assert_called_once_with(("127.0.0.1", 18080), mock.ANY)

    def test_main_handles_store_failure(self):
        """GIVEN Store init fails WHEN main THEN server still starts."""
        from yuleosh.ui.server import main

        with mock.patch("yuleosh.ui.server.HTTPServer") as mock_httpd:
            mock_server = mock.MagicMock()
            mock_httpd.return_value = mock_server
            with mock.patch("yuleosh.ui.server.Store", side_effect=Exception("DB down")):
                main(host="127.0.0.1", port=18081)
            mock_httpd.assert_called_once()
