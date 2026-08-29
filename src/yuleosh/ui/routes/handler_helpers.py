# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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

from yuleosh.ui.routes.http_response import (
    _add_cors_header,
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
        _add_cors_header(handler)
        handler.send_header("X-RateLimit-Remaining", "0")
        handler.end_headers()
        handler.wfile.write(json.dumps({
            "ok": False,
            "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
        }).encode())
        return False
    return True


# ------------------------------------------------------------------
# Auth denial
# ------------------------------------------------------------------

def _send_auth_denied(handler) -> None:
    """Respond to an unauthenticated request (SEC-C3 fail-closed).

    Legacy /api/* paths get a 401 JSON payload; browser page requests get
    the tenant login page (same UX as /login).
    """
    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path
    if path.startswith("/api/"):
        handler._json_response({
            "ok": False,
            "error": "unauthorized",
            "message": "Authentication required",
        }, 401)
    else:
        handler._serve_page("login.html", {"msg": ""})


# ------------------------------------------------------------------
# Dispatch: GET, POST, DELETE, OPTIONS
# ------------------------------------------------------------------

def handle_get(handler) -> None:
    """Route and serve all GET requests (non-API-v1 routes)."""
    from yuleosh.ui import server as _s
    parsed = urllib.parse.urlparse(handler.path)
    # Normalize trailing slash so /dashboard/ resolves the same as /dashboard
    # (P0: pages were 404'ing on the canonical trailing-slash form).
    path = parsed.path.rstrip("/") or "/"

    # ── API v1 router (single source of truth for /api/v1/*) ──
    if path.startswith("/api/v1/"):
        if _s.api_v1_dispatch(handler, path):
            return

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
        _send_auth_denied(handler)
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
    elif path == "/pipeline-board":
        handler._serve_file(UI_DIR / "pages" / "pipeline-board.html", "text/html; charset=utf-8")
    elif path == "/demo":
        handler._serve_page("demo.html", {})
    elif path.startswith("/api/v1/pipeline/status/"):
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        result = handle_pipeline_status(handler, path)
        if isinstance(result, tuple):
            data, status = result
            handler._json_response(data, status)
        else:
            handler._json_response(result)
    elif path == "/api/v1/pipeline/runs":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs
        handler._json_response(handle_pipeline_runs(handler))
    elif path == "/api/v1/pipeline/stats":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats
        handler._json_response(handle_pipeline_stats(handler))
    elif path == "/api/v1/pipeline/yuleasr-status":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        handler._json_response(handle_yuleasr_status(handler))
    elif path == "/api/v1/pipeline/validate":
        from yuleosh.pipeline.config_validator import validate_pipeline_config
        result = validate_pipeline_config(project_dir=os.environ.get("OSH_HOME", ""))
        handler._json_response({"ok": True, **result})
    elif path == "/api/v1/pipeline/checkpoint":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint
        handler._json_response(handle_pipeline_checkpoint(handler, path))
    # ── Loop Engineering API routes ──
    elif path == "/api/loops/summary":
        from yuleosh.api.loops import get_all_loops_data
        handler._json_response(get_all_loops_data())
    # ── Kanban page (SAAS-3) ──
    elif path == "/kanban":
        # Serve the kanban page from ui/pages/
        ui_dir = Path(__file__).resolve().parent.parent
        kanban_path = ui_dir / "pages" / "kanban.html"
        if kanban_path.exists():
            handler._serve_file(kanban_path, "text/html; charset=utf-8")
        else:
            handler._serve_static("/404.html")
        return
    elif path.startswith("/api/loops/"):
        from yuleosh.api.loops import get_loop_data
        parts = path.split("/")
        if len(parts) >= 4 and parts[-1] == "data":
            try:
                loop_id = int(parts[3])
            except (ValueError, IndexError):
                loop_id = None
            handler._json_response(get_loop_data(loop_id))
        else:
            handler._serve_page("404.html", {})
    else:
        handler._serve_page("404.html", {})


def handle_post(handler) -> None:
    """Route and serve all POST requests (non-API-v1 routes)."""
    parsed = urllib.parse.urlparse(handler.path)
    path = parsed.path

    # ── API v1 router (single source of truth for /api/v1/*) ──
    if path.startswith("/api/v1/"):
        from yuleosh.ui import server as _s
        if _s.api_v1_dispatch(handler, path):
            return

    if path == "/_auth/login":
        handler._handle_login()
        return

    if path == "/api/auth/signin":
        handler._handle_api("signin")
        return
    if path == "/api/auth/refresh":
        handler._handle_api("refresh")
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

    # ── Pipeline trigger endpoint ──
    if path == "/api/v1/pipeline/trigger":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length) if content_length else b"{}"
        result = handle_pipeline_trigger(handler, body)
        handler._json_response(result)
        return

    # yuleASR pipeline notification endpoint
    if path == "/api/v1/pipeline/yuleasr-notify":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length) if content_length else b"{}"
        result = handle_yuleasr_notify(handler, body)
        handler._json_response(result)
        return

    if not handler._check_auth():
        _send_auth_denied(handler)
        return

    handler._serve_page("404.html", {})


def handle_delete(handler) -> None:
    """Route and serve all DELETE requests (non-API-v1 routes)."""
    handler._serve_page("404.html", {})


def handle_options(handler) -> None:
    """Serve OPTIONS preflight response.

    P1-11 (S-P1-09): the preflight used to hardcode
    ``Access-Control-Allow-Origin: *``, bypassing the cors.py whitelist.
    ``_add_cors_header`` now enforces the same origin policy as normal
    responses (development: *; production: validated Origin echo).
    """
    handler.send_response(204)
    _add_cors_header(handler)
    _send_security_headers(handler)
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
    handler.end_headers()


# ------------------------------------------------------------------
# Audit logging
# ------------------------------------------------------------------

# A2 (v3.8.0): audit unified — the in-memory ring was write-only dead
# code (裁决 B2: delete).  Legacy UI requests and /api/v1/* requests now
# share the SQLite audit_log table via api.audit.log_request (裁决 B3:
# only /api/-prefixed request paths are persisted; page assets are not).

def log_audit(handler) -> None:
    """Persist the current request to the audit_log table.

    B3 (v3.8.0): only ``/api/``-prefixed request paths enter the table
    (page/static asset requests do not, to keep the table bounded).
    ``/api/v1/*`` requests are already persisted by the router's
    ``_do_audit_log`` — this path covers the legacy ``/api/*`` routes
    (e.g. /api/evidence, /api/auth/signin) via the SAME write path
    (SHALL-A2.1: one persistent write path).
    """
    try:
        path = urllib.parse.urlparse(handler.path).path
        if not path.startswith("/api/"):
            return  # B3: page/static requests are not audited
        if path.startswith("/api/v1/"):
            return  # already persisted by router._do_audit_log
        from yuleosh.api.audit import log_request as _db_log
        duration_ms = (time.time() - handler._request_start_time) * 1000
        _db_log(
            method=handler.command,
            path=path,
            status_code=getattr(handler, "_response_status", 200),
            ip=handler._get_client_ip(),
            duration_ms=round(duration_ms, 2),
        )
    except Exception as e:
        logging.getLogger("yuleosh.audit").warning(
            "Audit log write failed: %s", e)

