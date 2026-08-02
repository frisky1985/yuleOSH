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

from yuleosh.ui.routes.helpers import (
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
    path = parsed.path

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
    # ── Loop Engineering API routes ──
    elif path == "/api/loops/summary":
        from yuleosh.api.loops import get_all_loops_data
        handler._json_response(get_all_loops_data())
    # ── Tenant API routes (SAAS-1) ──
    elif path.startswith("/api/v1/tenant/"):
        from yuleosh.ui.routes.tenant_routes import (
            handle_tenant_info, handle_tenant_update, handle_tenant_projects, handle_usage_check,
        )
        parts = path.split("/")
        # /api/v1/tenant/{slug}
        if len(parts) == 5:
            slug = parts[4]
            handle_tenant_info(handler, slug)
        # /api/v1/tenant/{slug}/projects
        elif len(parts) == 6 and parts[5] == "projects":
            slug = parts[4]
            handle_tenant_projects(handler, slug)
        # /api/v1/tenant/{slug}/usage
        elif len(parts) == 6 and parts[5] == "usage":
            slug = parts[4]
            handle_usage_check(handler, slug)
        else:
            handler._serve_page("404.html", {})
        return
    elif path == "/api/v1/tenants":
        from yuleosh.ui.routes.tenant_routes import handle_tenant_list
        handle_tenant_list(handler)
        return
    # ── Kanban / Project routes (SAAS-3) ──
    elif path == "/kanban":
        # Serve the kanban page from ui/pages/
        ui_dir = Path(__file__).resolve().parent.parent
        kanban_path = ui_dir / "pages" / "kanban.html"
        if kanban_path.exists():
            handler._serve_file(kanban_path, "text/html; charset=utf-8")
        else:
            handler._serve_static("/404.html")
        return
    elif path.startswith("/api/v1/projects/"):
        from yuleosh.ui.routes.project_routes import handle_get_project
        handle_get_project(handler, path)
        return
    # ── Audit routes (SAAS-4) ──
    elif path == "/audit-dashboard":
        ui_dir = Path(__file__).resolve().parent.parent
        audit_path = ui_dir / "pages" / "audit-dashboard.html"
        if audit_path.exists():
            handler._serve_file(audit_path, "text/html; charset=utf-8")
        else:
            handler._serve_static("/404.html")
        return
    elif path == "/api/v1/audit":
        from yuleosh.ui.routes.audit_routes import handle_get_audit_logs
        handle_get_audit_logs(handler)
        return
    # ── Billing routes (SAAS-5) ──
    elif path == "/billing":
        ui_dir = Path(__file__).resolve().parent.parent
        billing_path = ui_dir / "pages" / "billing.html"
        if billing_path.exists():
            handler._serve_file(billing_path, "text/html; charset=utf-8")
        else:
            handler._serve_static("/404.html")
        return
    elif path == "/api/v1/billing/usage":
        from yuleosh.ui.routes.billing_routes import handle_get_usage
        handle_get_usage(handler)
        return
    elif path == "/api/v1/billing/plan":
        from yuleosh.ui.routes.billing_routes import handle_get_plan
        handle_get_plan(handler)
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
    if path == "/api/org/create":
        handler._handle_api("org_create")
        return
    if path == "/api/project/create":
        handler._handle_api("project_create")
        return
    if path == "/api/auth/logout":
        handler._handle_api("logout")
        return

    # ── Tenant project create (SAAS-1) ──
    if path.startswith("/api/v1/tenant/") and path.endswith("/projects"):
        from yuleosh.ui.routes.tenant_routes import handle_tenant_project_create
        parts = path.split("/")
        if len(parts) == 6:
            slug = parts[4]
            handle_tenant_project_create(handler, slug)
            return

    # ── Project kanban operations (SAAS-3) ──
    if path == "/api/v1/projects":
        from yuleosh.ui.routes.project_routes import handle_create_project
        handle_create_project(handler)
        return
    if path.startswith("/api/v1/projects/"):
        from yuleosh.ui.routes.project_routes import handle_update_project
        handle_update_project(handler, path)
        return

    # ── Audit log event creation (SAAS-4) ──
    if path == "/api/v1/audit":
        from yuleosh.ui.routes.audit_routes import handle_post_audit_event
        handle_post_audit_event(handler)
        return

    # ── Billing (SAAS-5) ──
    if path == "/api/v1/billing/upgrade":
        from yuleosh.ui.routes.billing_routes import handle_upgrade_plan
        handle_upgrade_plan(handler)
        return

    # Pipeline trigger endpoint
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
