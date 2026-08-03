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

from yuleosh.ui.routes.helpers import _send_security_headers, _add_cors_header


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
        _add_cors_header(handler)
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
            # P1-2: pass the client IP so signin can enforce a per-IP
            # attempt cap (bounds cross-email lockout DoS).
            client_ip = ""
            try:
                client_ip = handler.client_address[0]
            except (AttributeError, IndexError, TypeError):
                pass
            result, status = handle_signin(body, ip=client_ip)
            # T1 (v3.9.0, SHALL-T1.1): successful login issues the
            # access+refresh httpOnly cookie pair (JSON body contract
            # unchanged — refresh_token is cookie-only).
            cookies = _auth_cookie_headers(result)
            _send_json_response(handler, result, status, set_cookies=cookies)
        elif action == "session":
            result, status = handle_session_info(token)
            _send_json_response(handler, result, status)
        elif action == "org_create":
            result, status = handle_org_create(body, token)
            cookies = _auth_cookie_headers(result)
            _send_json_response(handler, result, status, set_cookies=cookies)
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
            # T1 (v3.9.0, SHALL-T1.6): logout also clears both tenant
            # cookies (Max-Age=0) — the browser session is fully gone.
            _send_json_response(handler, result, status,
                                set_cookies=_clear_cookie_headers())
        elif action == "refresh":
            # T1 (v3.9.0, SHALL-T1.5): POST /api/auth/refresh — cookie
            # mode renewal.  The refresh token comes from the yuleosh_rt
            # cookie (or an explicit Bearer for API clients).
            from yuleosh.ui.auth_cookies import (
                REFRESH_COOKIE_NAME, read_cookie_value,
            )
            from yuleosh.ui.auth_extended import handle_refresh
            rt = read_cookie_value(handler.headers, REFRESH_COOKIE_NAME) \
                or token  # Bearer fallback for non-browser clients
            result, status = handle_refresh(rt)
            if status == 200:
                cookies = _auth_cookie_headers(result)
            else:
                # T1.5 neg: refresh failed/expired → clear both cookies.
                cookies = _clear_cookie_headers()
            _send_json_response(handler, result, status, set_cookies=cookies)
        else:
            _send_json_error(handler, "unknown action", 400)
    except Exception as e:
        _send_json_error(handler, str(e), 500)


# ── Internal helpers ────────────────────────────────────────────────


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse the request body (P1-5: unified clamped read_body).

    Delegates to yuleosh.api.read_body which clamps Content-Length to 10 MB
    and converts malformed headers to BadRequest.  Invalid JSON / bad
    Content-Length yield {} — caller validation returns the 4xx.
    """
    from yuleosh.api import read_body, BadRequest
    try:
        return read_body(handler)
    except BadRequest:
        return {}


def _auth_cookie_headers(result: dict) -> list:
    """T1 (v3.9.0): convert a login response's tokens into Set-Cookie values.

    The refresh token never leaves the server in the JSON body (SHALL-T1.1
    body contract preserved); it is delivered exclusively via the httpOnly
    cookie.  Returns [] for non-login responses (no tokens to set).
    """
    if not isinstance(result, dict):
        return []
    access = result.get("token")
    refresh = result.pop("refresh_token", None)
    if not access or not refresh:
        return []
    from yuleosh.ui.auth_cookies import token_cookie_headers
    return token_cookie_headers(access, refresh)


def _clear_cookie_headers() -> list:
    """T1 (v3.9.0): Set-Cookie values that delete both tenant cookies."""
    from yuleosh.ui.auth_cookies import clear_cookie_headers
    return clear_cookie_headers()


def _get_bearer_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    """Extract bearer token from Authorization header, with cookie fallback.

    T1 (v3.9.0, SHALL-T1.4): no Authorization header → read the
    ``yuleosh_at`` access cookie (browser cookie mode).  An Authorization
    header that is present but not Bearer fails closed (no fallback).
    """
    auth = handler.headers.get("Authorization", "")
    if auth:
        if auth.startswith("Bearer "):
            return auth[7:]
        return None
    from yuleosh.ui.auth_cookies import ACCESS_COOKIE_NAME, read_cookie_value
    return read_cookie_value(handler.headers, ACCESS_COOKIE_NAME)


def _send_json_response(handler: BaseHTTPRequestHandler, data, status: int = 200,
                        set_cookies: Optional[list] = None):
    """Send a JSON response via handler's standard mechanism.

    T1 (v3.9.0): ``set_cookies`` is a list of raw Set-Cookie header values
    (from auth_cookies) emitted on the response before end_headers.
    """
    extra = [("Set-Cookie", c) for c in (set_cookies or [])]
    # Delegate to handler's json_response if available, otherwise inline
    if hasattr(handler, "_json_response"):
        # Only pass extra_headers when present — keeps the common call
        # signature stable for existing tests/callers.
        if extra:
            handler._json_response(data, status, extra_headers=extra)
        else:
            handler._json_response(data, status)
    else:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        for name, value in extra:
            handler.send_header(name, value)
        _send_security_headers(handler)
        _add_cors_header(handler)
        handler.end_headers()
        handler.wfile.write(body)


def _send_json_error(handler: BaseHTTPRequestHandler, message: str, status: int = 400):
    """Send an error JSON response."""
    _send_json_response(handler, {"error": message}, status)
