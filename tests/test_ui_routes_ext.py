"""
Extended tests for yuleosh.ui.routes — push coverage ≥ 60%.
Covers auth_routes, page_routes, and helpers.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Mock handler factory ──────────────────────────────────────────────

def _make_mock_handler(headers=None, path="/", method="GET", body=b""):
    """Create a minimal mock BaseHTTPRequestHandler."""
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


# =====================================================================
# auth_routes.py
# =====================================================================

class TestAuthRoutes:
    """Cover handle_auth_check and related functions."""

    def test_auth_disabled_allows_all(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_check
        handler = _make_mock_handler()
        # Mock AUTH_ENABLED at the source (yuleosh.ui.auth)
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", False):
            result = handle_auth_check(handler)
            assert result is True

    def test_auth_enabled_authenticated(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_check
        handler = _make_mock_handler(headers={"X-API-Key": "valid"})
        # Need to mock both AUTH_ENABLED and is_authenticated in the source module
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            with mock.patch("yuleosh.ui.auth.is_authenticated", return_value=True):
                result = handle_auth_check(handler)
                assert result is True

    def test_auth_enabled_api_call_denied(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_check
        handler = _make_mock_handler(path="/api/evidence")
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            with mock.patch("yuleosh.ui.auth.is_authenticated", return_value=False):
                result = handle_auth_check(handler)
                assert result is False
                handler.send_response.assert_called_with(401)

    def test_auth_enabled_browser_request(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_check
        handler = _make_mock_handler(path="/dashboard")
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            with mock.patch("yuleosh.ui.auth.is_authenticated", return_value=False):
                with mock.patch("yuleosh.ui.auth.get_login_page",
                                return_value="<html>login</html>", create=True):
                    result = handle_auth_check(handler)
                    assert result is False
                    handler.send_response.assert_called_with(200)

    def test_handle_auth_login_no_key(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_login
        handler = _make_mock_handler(headers={"Content-Length": "0"}, method="POST")
        with mock.patch("yuleosh.ui.auth.API_KEY", "test-key", create=True):
            with mock.patch("yuleosh.ui.auth.get_login_page",
                            return_value="<html>form</html>", create=True):
                handle_auth_login(handler)
                handler.send_response.assert_called_with(200)

    def test_handle_auth_login_invalid_key(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_login
        body = b"api_key=wrong"
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body))}, method="POST", body=body)
        with mock.patch("yuleosh.ui.auth.API_KEY", "real-key", create=True):
            with mock.patch("yuleosh.ui.auth.get_login_page",
                            return_value="<html>form</html>", create=True):
                handle_auth_login(handler)
                handler.send_response.assert_called_with(200)

    def test_handle_auth_login_valid_key(self):
        from yuleosh.ui.routes.auth_routes import handle_auth_login
        body = b"api_key=real-key"
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body))}, method="POST", body=body)
        with mock.patch("yuleosh.ui.auth.API_KEY", "real-key", create=True):
            with mock.patch("yuleosh.ui.auth.create_session",
                            return_value=("session_id", "cookie_val"), create=True):
                handle_auth_login(handler)
                handler.send_response.assert_called_with(302)

    def test_handle_api_action_signin(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        body = json.dumps({}).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body)), "Authorization": "Bearer token"},
            method="POST", body=body)
        with mock.patch("yuleosh.ui.auth_extended.handle_signin",
                        return_value=({"status": "ok"}, 200)):
            handle_api_action(handler, "signin")
            handler.send_response.assert_called_with(200)

    def test_handle_api_action_unknown(self):
        from yuleosh.ui.routes.auth_routes import handle_api_action
        handler = _make_mock_handler(headers={"Content-Length": "0"}, method="POST")
        handle_api_action(handler, "unknown_action")
        handler.send_response.assert_called_with(400)

    def test_read_body_empty(self):
        from yuleosh.ui.routes.auth_routes import _read_body
        handler = _make_mock_handler(headers={"Content-Length": "0"})
        assert _read_body(handler) == {}

    def test_read_body_valid_json(self):
        from yuleosh.ui.routes.auth_routes import _read_body
        body_bytes = json.dumps({"key": "value"}).encode()
        handler = _make_mock_handler(
            headers={"Content-Length": str(len(body_bytes))}, body=body_bytes)
        assert _read_body(handler) == {"key": "value"}

    def test_read_body_invalid_json(self):
        from yuleosh.ui.routes.auth_routes import _read_body
        handler = _make_mock_handler(headers={"Content-Length": "5"}, body=b"not-json")
        assert _read_body(handler) == {}

    def test_get_bearer_token(self):
        from yuleosh.ui.routes.auth_routes import _get_bearer_token
        handler = _make_mock_handler(headers={"Authorization": "Bearer mytoken"})
        assert _get_bearer_token(handler) == "mytoken"

    def test_get_bearer_token_missing(self):
        from yuleosh.ui.routes.auth_routes import _get_bearer_token
        handler = _make_mock_handler(headers={})
        assert _get_bearer_token(handler) is None

    def test_send_json_response(self):
        from yuleosh.ui.routes.auth_routes import _send_json_response
        handler = _make_mock_handler()
        _send_json_response(handler, {"status": "ok"}, 200)
        handler.send_response.assert_called_with(200)

    def test_send_json_response_with_method(self):
        from yuleosh.ui.routes.auth_routes import _send_json_response
        handler = _make_mock_handler()
        handler._json_response = mock.MagicMock()
        _send_json_response(handler, {"status": "ok"}, 200)
        handler._json_response.assert_called_once_with({"status": "ok"}, 200)

    def test_send_json_error(self):
        from yuleosh.ui.routes.auth_routes import _send_json_error
        handler = _make_mock_handler()
        _send_json_error(handler, "error msg", 400)
        handler.send_response.assert_called_with(400)


# =====================================================================
# helpers.py
# =====================================================================

class TestHelpers:
    """Cover route helpers."""

    def test_compute_etag(self):
        from yuleosh.ui.routes.helpers import _compute_etag
        etag = _compute_etag(b"hello world")
        assert etag.startswith('W/"') or etag.startswith('"')

    def test_send_security_headers(self):
        from yuleosh.ui.routes.helpers import _send_security_headers
        handler = _make_mock_handler()
        _send_security_headers(handler)
        assert handler.send_header.call_count > 0

    def test_format_http_datetime(self):
        from yuleosh.ui.routes.helpers import _format_http_datetime
        result = _format_http_datetime(1000000)
        assert isinstance(result, str)

    def test_parse_http_datetime(self):
        from yuleosh.ui.routes.helpers import _parse_http_datetime
        from yuleosh.ui.routes.helpers import _format_http_datetime
        now = 1000000
        formatted = _format_http_datetime(now)
        parsed = _parse_http_datetime(formatted)
        assert abs(parsed - now) < 2

    def test_parse_http_datetime_invalid(self):
        from yuleosh.ui.routes.helpers import _parse_http_datetime
        result = _parse_http_datetime("bad date")
        assert result == 0.0


# =====================================================================
# page_routes.py
# =====================================================================

class TestPageRoutes:
    """Cover page_routes functions."""

    def test_send_html_response(self):
        from yuleosh.ui.routes.page_routes import _send_html_response
        handler = _make_mock_handler()
        _send_html_response(handler, "<html>test</html>", 200)
        handler.send_response.assert_called_with(200)

    def test_send_json_error(self):
        from yuleosh.ui.routes.page_routes import _send_json_error
        handler = _make_mock_handler()
        _send_json_error(handler, "error", 400)
        handler.send_response.assert_called_with(400)

    def test_serve_file_not_found(self, tmp_path):
        from yuleosh.ui.routes.page_routes import serve_file
        handler = _make_mock_handler()
        serve_file(handler, tmp_path / "nonexistent.txt", "text/plain")
        assert handler.send_response.call_count >= 1

    def test_serve_file_found(self, tmp_path):
        from yuleosh.ui.routes.page_routes import serve_file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        handler = _make_mock_handler(headers={})
        serve_file(handler, test_file, "text/plain")
        handler.send_response.assert_called_with(200)
        handler.send_header.assert_any_call("Content-Type", "text/plain")

    def test_serve_file_304(self, tmp_path):
        from yuleosh.ui.routes.page_routes import serve_file
        from yuleosh.ui.routes.helpers import _compute_etag
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")
        data = b"hello"
        etag = _compute_etag(data)
        handler = _make_mock_handler(headers={"If-None-Match": etag})
        serve_file(handler, test_file, "text/plain")
        handler.send_response.assert_called_with(304)
