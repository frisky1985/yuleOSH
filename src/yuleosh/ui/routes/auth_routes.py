"""
yuleOSH Dashboard — Auth route handlers.

Extracts authentication and tenant-auth dispatch logic from the
monolithic OSHHandler into standalone helper functions.
"""

import hmac
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Optional

from yuleosh.ui.routes.helpers import _send_security_headers


def handle_auth_check(handler: BaseHTTPRequestHandler) -> bool:
    """Check authentication. Returns True if allowed, False if denied (response sent)."""
    # These are imported lazily to avoid circular imports at module level
    from yuleosh.ui.auth import AUTH_ENABLED, is_authenticated, get_login_page as _get_login_page

    if not AUTH_ENABLED:
        return True

    # Gather headers into a dict
    headers = {}
    for k, v in handler.headers.items():
        headers[k.lower()] = v

    if is_authenticated(headers):
        return True

    # Not authenticated — check if it's an API call or browser request
    path = urllib.parse.urlparse(handler.path).path
    if path.startswith("/api/"):
        handler.send_response(401)
        handler.send_header("Content-Type", "application/json")
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "error": "unauthorized",
            "message": "X-API-Key header required"
        }).encode())
        return False
    else:
        # Serve login page for browser requests
        _get_login_page = __import__("yuleosh.ui.auth", fromlist=["get_login_page"]).get_login_page
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        _send_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(_get_login_page().encode("utf-8"))
        return False


def handle_auth_login(handler: BaseHTTPRequestHandler):
    """Handle POST /_auth/login — validate API key and set session cookie."""
    from yuleosh.ui.auth import API_KEY, create_session, get_login_page as _get_login_page

    content_length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(content_length).decode("utf-8")
    params = urllib.parse.parse_qs(body)
    api_key_input = params.get("api_key", [""])[0]

    if not api_key_input:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        _send_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(_get_login_page("API key is required").encode("utf-8"))
        return

    if hmac.compare_digest(api_key_input, API_KEY):
        # Success — set session cookie and redirect to dashboard
        _, cookie_val = create_session()
        handler.send_response(302)
        handler.send_header("Set-Cookie",
            f"osh_session={cookie_val}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400")
        _send_security_headers(handler)
        handler.send_header("Location", "/")
        handler.end_headers()
    else:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        _send_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(_get_login_page("Invalid API key").encode("utf-8"))


def handle_api_action(handler: BaseHTTPRequestHandler, action: str):
    """Dispatch to tenant auth or org/project handlers."""
    try:
        from yuleosh.ui.auth_extended import (
            handle_signin, handle_session_info, handle_org_create,
            handle_org_info, handle_project_list, handle_project_create,
            handle_logout,
        )
    except ImportError:
        _send_json_error(handler, "tenant auth not available", 501)
        return

    body = _read_body(handler)
    token = _get_bearer_token(handler)

    try:
        if action == "signin":
            result, status = handle_signin(body)
            _send_json_response(handler, result, status)
        elif action == "session":
            result, status = handle_session_info(token)
            _send_json_response(handler, result, status)
        elif action == "org_create":
            result, status = handle_org_create(body, token)
            _send_json_response(handler, result, status)
        elif action == "org_info":
            result, status = handle_org_info(token)
            _send_json_response(handler, result, status)
        elif action == "project_list":
            result, status = handle_project_list(token)
            _send_json_response(handler, result, status)
        elif action == "project_create":
            result, status = handle_project_create(body, token)
            _send_json_response(handler, result, status)
        elif action == "logout":
            result, status = handle_logout(token)
            _send_json_response(handler, result, status)
        else:
            _send_json_error(handler, "unknown action", 400)
    except Exception as e:
        _send_json_error(handler, str(e), 500)


# ── Internal helpers ────────────────────────────────────────────────


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse JSON request body."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    try:
        body = handler.rfile.read(content_length).decode("utf-8")
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _get_bearer_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    """Extract bearer token from Authorization header."""
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _send_json_response(handler: BaseHTTPRequestHandler, data, status: int = 200):
    """Send a JSON response via handler's standard mechanism."""
    # Delegate to handler's json_response if available, otherwise inline
    if hasattr(handler, "_json_response"):
        handler._json_response(data, status)
    else:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(body)


def _send_json_error(handler: BaseHTTPRequestHandler, message: str, status: int = 400):
    """Send an error JSON response."""
    _send_json_response(handler, {"error": message}, status)
