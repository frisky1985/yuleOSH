# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Dashboard — OSHHandler dispatch helpers.

Route dispatch functions (handle_get, handle_post, handle_delete,
handle_options) extracted from the OSHHandler class to reduce server.py
below 500 lines.

IMPORTANT: These functions reference yuleosh.ui.server module-level
variables (Store, api_v1_dispatch, AUTH_ENABLED, etc.) lazily via
`from yuleosh.ui import server` so that unit test patches on
yuleosh.ui.server.* affect dispatch behavior correctly.
"""

import json
import logging
import os
import time
import urllib.parse
from pathlib import Path

from yuleosh.ui.routes.helpers import (
    _compute_etag,
    _format_http_datetime,
    _parse_http_datetime,
    _send_security_headers,
)


# ------------------------------------------------------------------
# Rate limiting
# ------------------------------------------------------------------

def rate_limit_check(handler) -> bool:
    """Check rate limiting. Sends 429 if denied, returns False.
    
    References yuleosh.ui.server.check_rate_limit for test-patch compat.
    """
    from yuleosh.ui import server as _s
    allowed, retry_after = _s.check_rate_limit(handler._get_client_ip())
    if not allowed:
        handler.send_response(429)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Retry-After", str(retry_after))
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("X-RateLimit-Remaining", "0")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "ok": False,
            "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
        }).encode())
        return False
    return True


# ------------------------------------------------------------------
# Dispatch: GET, POST, DELETE, OPTIONS
# ------------------------------------------------------------------

def handle_get(handler) -> None:
    """Route and serve all GET requests (non-API-v1 routes)."""
    from yuleosh.ui import server as _s
    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path

    # Healthcheck — always accessible
    if path == "/api/health":
        handler._json_response(handler._get_health())
        return

    # Health dashboard page
    if path == "/health":
        handler._serve_page("health.html", {})
        return

    # Tenant auth endpoints
    if path == "/api/auth/session":
        handler._handle_api("session")
        return
    if path == "/api/auth/logout":
        handler._handle_api("logout")
        return
    if path == "/api/project/list":
        handler._handle_api("project_list")
        return
    if path == "/api/org/info":
        handler._handle_api("org_info")
        return

    # Welcome/wizard page (no auth required)
    if path == "/welcome":
        handler._serve_page("welcome.html", {})
        return

    # Tenant auth pages (no legacy auth required)
    if path == "/login":
        handler._serve_page("login.html", {"msg": ""})
        return
    if path == "/register":
        handler.send_response(302)
        handler.send_header("Location", "/login")
        handler.end_headers()
        return
    if path == "/org/setup":
        handler._serve_page("org-setup.html", {})
        return
    if path == "/project/select":
        handler._serve_page("project-select.html", {})
        return

    # Legacy auth check for all other routes
    if not handler._check_auth():
        return

    UI_DIR = Path(__file__).resolve().parent.parent

    if path in ("/", "/index.html"):
        try:
            store = _s.Store()
            cur = store.conn.execute("SELECT value FROM _meta WHERE key='wizard_completed'")
            row = cur.fetchone()
            if row and row["value"] == "1":
                handler._serve_file(UI_DIR / "marketing" / "index.html", "text/html; charset=utf-8")
            else:
                handler.send_response(302)
                _send_security_headers(handler)
                handler.send_header("Location", "/welcome")
                handler.end_headers()
        except Exception as e:
            logging.warning("Signin redirect fallback: %s", e)
            handler._serve_file(UI_DIR / "marketing" / "index.html", "text/html; charset=utf-8")
    elif path == "/pricing":
        handler._serve_file(UI_DIR / "marketing" / "pricing.html", "text/html; charset=utf-8")
    elif path in ("/en", "/en/index.html"):
        handler._serve_file(UI_DIR / "marketing" / "en" / "index.html", "text/html; charset=utf-8")
    elif path == "/en/pricing":
        handler._serve_file(UI_DIR / "marketing" / "en" / "pricing.html", "text/html; charset=utf-8")
    elif path == "/dashboard":
        handler._serve_file(UI_DIR / "pages" / "dashboard-v5.html", "text/html; charset=utf-8")
    elif path == "/apikeys":
        handler._serve_page("apikeys.html", {})
    elif path == "/api/status":
        handler._json_response(handler._get_status())
    elif path == "/api/evidence":
        handler._json_response(handler._list_evidence())
    elif path == "/api/reviews":
        handler._json_response(handler._get_reviews())
    elif path == "/api/ci":
        handler._json_response(handler._get_ci_results())
    elif path == "/onboarding":
        handler._serve_page("onboarding.html", {})
    elif path == "/pipeline-flow":
        handler._serve_file(UI_DIR / "pages" / "pipeline-flow.html", "text/html; charset=utf-8")
    elif path == "/demo":
        handler._serve_page("demo.html", {})
    else:
        handler._serve_page("404.html", {})


def handle_post(handler) -> None:
    """Route and serve all POST requests (non-API-v1 routes)."""
    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path

    if path == "/_auth/login":
        handler._handle_login()
        return

    if path == "/api/auth/signin":
        handler._handle_api("signin")
        return
    if path == "/api/org/create":
        handler._handle_api("org_create")
        return
    if path == "/api/project/create":
        handler._handle_api("project_create")
        return
    if path == "/api/auth/logout":
        handler._handle_api("logout")
        return

    if not handler._check_auth():
        return

    handler._serve_page("404.html", {})


def handle_delete(handler) -> None:
    """Route and serve all DELETE requests (non-API-v1 routes)."""
    handler._serve_page("404.html", {})


def handle_options(handler) -> None:
    """Serve OPTIONS preflight response."""
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", "*")
    _send_security_headers(handler)
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
    handler.end_headers()


# ------------------------------------------------------------------
# Audit logging
# ------------------------------------------------------------------

def log_audit(handler) -> None:
    """Log the current request to the audit log via handler state."""
    from yuleosh.ui import server as _s
    duration_ms = (time.time() - handler._request_start_time) * 1000
    path = urllib.parse.urlparse(handler.path).path
    _s._audit_log(
        method=handler.command,
        path=path,
        status_code=getattr(handler, "_response_status", 200),
        ip=handler._get_client_ip(),
        duration_ms=round(duration_ms, 2),
    )
