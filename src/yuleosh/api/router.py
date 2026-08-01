# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH REST API v1 router — dispatches requests to handler modules.

Mounted at /api/v1/ in the main server.
"""

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler

from . import json_ok, json_error, read_body, BadRequest
from .cors import get_cors_origin

# Core modules (always loaded)
from .health import handle_health
from .kb import handle_kb
from .spec import handle_spec
from .pipeline import handle_pipeline
from .ci import handle_ci
from .review import handle_review
from .evidence import handle_evidence
from .project import handle_project
from .stats import handle_stats
from .notify import handle_notify
from .apikeys import handle_apikeys
from .wizard import handle_wizard
from .audit import handle_audit
from .auth import handle_auth

# Lazy-loaded modules (AR-P2-01): only imported when their route is hit
# These are loaded lazily to avoid importing optional/seldom-used modules.
_LAZY_HANDLERS = {
    "webhooks": ("yuleosh.api.webhooks", "handle_webhooks"),
    "demo": ("yuleosh.api.demo", "handle_demo"),
    "preview": ("yuleosh.api.preview", "handle_preview"),
    "subscription": ("yuleosh.api.subscription", "handle_subscription"),
    "dashboard": ("yuleosh.api.dashboard", "handle_dashboard"),
}

logger = logging.getLogger("yuleosh.api.router")


# ─────────────────────────────────────────────────────────────────────
# P0-B: legacy UI route handlers
#
# Before the modular router wiring (af1245a), the following /api/v1/*
# endpoints were served by yuleosh/ui/routes/handler_helpers.py (and the
# route modules tenant_routes/billing_routes/project_routes/audit_routes).
# The wiring shadowed them into 404 dead code.  They are restored here by
# delegating to the same legacy handler modules, which perform their own
# session-token auth and write their own JSON response.
#
# Legacy handler convention: fn(handler, ...) → writes response directly
# via handler.send_response(...), returns None.  Hence _dispatch_legacy
# returns True once a legacy module took the request; the router must NOT
# read the body first (legacy handlers read rfile themselves).
# ─────────────────────────────────────────────────────────────────────

def _dispatch_legacy(handler: BaseHTTPRequestHandler, path: str, method: str) -> bool:
    """Route /api/v1/* paths to pre-modular-router legacy handlers.

    Returns True if a legacy handler wrote the response, False if the path
    is not a legacy route (caller should 404).
    """
    clean = path.rstrip("/")
    try:
        # ── Tenant (SAAS-1) ────────────────────────────────────────────
        if clean.startswith("/api/v1/tenant/"):
            from yuleosh.ui.routes.tenant_routes import (
                handle_tenant_info,
                handle_tenant_projects,
                handle_usage_check,
                handle_tenant_project_create,
            )
            parts = clean.split("/")
            # /api/v1/tenant/{slug}
            if len(parts) == 5:
                slug = parts[4]
                if method == "GET":
                    handle_tenant_info(handler, slug)
                    return True
                return False
            # /api/v1/tenant/{slug}/projects | /usage
            if len(parts) == 6:
                slug = parts[4]
                sub = parts[5]
                if method == "GET":
                    if sub == "projects":
                        handle_tenant_projects(handler, slug)
                        return True
                    if sub == "usage":
                        handle_usage_check(handler, slug)
                        return True
                if method == "POST" and sub == "projects":
                    handle_tenant_project_create(handler, slug)
                    return True
            return False

        # ── Tenants list (SAAS-1) ──────────────────────────────────────
        if clean == "/api/v1/tenants":
            if method != "GET":
                return False
            from yuleosh.ui.routes.tenant_routes import handle_tenant_list
            handle_tenant_list(handler)
            return True

        # ── Billing (SAAS-5) ───────────────────────────────────────────
        if clean.startswith("/api/v1/billing/"):
            from yuleosh.ui.routes.billing_routes import (
                handle_get_usage,
                handle_get_plan,
                handle_upgrade_plan,
            )
            sub = clean.split("/")[-1]
            if method == "GET" and sub == "usage":
                handle_get_usage(handler)
                return True
            if method == "GET" and sub == "plan":
                handle_get_plan(handler)
                return True
            if method == "POST" and sub == "upgrade":
                handle_upgrade_plan(handler)
                return True
            return False

        # ── Projects (SAAS-3, plural) ──────────────────────────────────
        if clean.startswith("/api/v1/projects"):
            from yuleosh.ui.routes.project_routes import (
                handle_get_project,
                handle_create_project,
                handle_update_project,
            )
            if method == "GET" and clean != "/api/v1/projects":
                handle_get_project(handler, clean)
                return True
            if method == "POST" and clean == "/api/v1/projects":
                handle_create_project(handler)
                return True
            if method == "POST" and clean != "/api/v1/projects":
                handle_update_project(handler, clean)
                return True
            return False

        # ── Audit (SAAS-4, legacy UI audit events) ─────────────────────
        if clean == "/api/v1/audit":
            from yuleosh.ui.routes.audit_routes import (
                handle_get_audit_logs,
                handle_post_audit_event,
            )
            if method == "GET":
                handle_get_audit_logs(handler)
                return True
            if method == "POST":
                handle_post_audit_event(handler)
                return True
            return False
    except Exception as e:  # pragma: no cover - defensive
        logger.error(
            "Legacy API dispatch failed [path=%s] [method=%s]: %s",
            path, method, e, exc_info=True,
        )
        try:
            _respond(handler, *json_error("Internal server error", 500))
        except Exception:
            pass
        return True
    return False


# Resource routing map: resource_name -> handler function
# Core modules are loaded eagerly; optional modules are lazy-loaded.
# See AR-P2-01: prevents unnecessary imports for /api/v1/ routes not used.
ROUTES: dict[str, object] = {
    "health": handle_health,
    "wizard": handle_wizard,
    "spec": handle_spec,
    "pipeline": handle_pipeline,
    "ci": handle_ci,
    "review": handle_review,
    "evidence": handle_evidence,
    "project": handle_project,
    "stats": handle_stats,
    "notify": handle_notify,
    "apikeys": handle_apikeys,
    "audit": handle_audit,
    "auth": handle_auth,
    "kb": handle_kb,
}


def dispatch(handler: BaseHTTPRequestHandler, path: str):
    """Dispatch an API request to the appropriate handler.

    path is the full URL path (e.g. /api/v1/pipeline/status)
    """
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    # Strip /api/v1 prefix
    prefix = "/api/v1"
    if not clean_path.startswith(prefix):
        return _respond(handler, *json_error("Not an API route", 404))

    remainder = clean_path[len(prefix):].strip("/")
    query = parse_qs(parsed.query)

    # Parse resource from the remainder
    parts = remainder.split("/", 1)
    resource = parts[0] if parts else ""
    path_tail = parts[1] if len(parts) > 1 else ""

    # Parse resource from the remainder
    parts = remainder.split("/", 1)
    resource = parts[0] if parts else ""
    path_tail = parts[1] if len(parts) > 1 else ""

    method = handler.command

    # Find the handler (AR-P2-01: resolve lazy-loaded modules on first request)
    handler_fn = ROUTES.get(resource)
    if handler_fn is None:
        # Try lazy-loaded modules
        lazy_entry = _LAZY_HANDLERS.get(resource)
        if lazy_entry:
            try:
                module_name, func_name = lazy_entry
                import importlib
                mod = importlib.import_module(module_name)
                handler_fn = getattr(mod, func_name)
                ROUTES[resource] = handler_fn
            except (ImportError, AttributeError):
                pass
    if handler_fn is None:
        # ── P0-B: legacy UI route handlers (pre-modular-router endpoints) ──
        # tenant/billing/projects/tenants lived in handler_helpers before the
        # router wiring and were shadowed into 404 dead code.  Restore them by
        # delegating to the legacy handler modules, which perform their own
        # auth (session token) and write their own JSON response.
        # NOTE: body is deliberately NOT read here — legacy handlers read
        # rfile themselves (their _read_body reads from the socket).
        if _dispatch_legacy(handler, clean_path, method):
            return
        return _respond(handler, *json_error(f"Unknown resource: {resource}", 404))

    body = None
    # P1-5 (W-08): read_body can raise BadRequest (invalid/oversized
    # Content-Length) — respond 400 instead of letting it bubble into a 500.
    try:
        body = read_body(handler)
    except BadRequest as e:
        _respond(handler, *json_error(str(e), 400))
        return

    # ── Audit log helper ─────────────────────────────────────────────
    def _do_audit_log(status_code: int):
        import time
        try:
            from yuleosh.api.audit import log_request as _audit_log
            duration_ms = (time.time() - handler._request_start_time) * 1000 \
                if hasattr(handler, '_request_start_time') else 0.0
            _audit_log(
                method=method,
                path=path,
                status_code=status_code,
                ip=handler.client_address[0],
                duration_ms=round(duration_ms, 2),
            )
        except Exception:
            pass

    try:
        result = handler_fn(method=method, path_tail=path_tail, body=body,
                            query=query, handler=handler)
        # If handler returned None, it already sent the response (e.g. binary download)
        if result is None:
            _do_audit_log(200)
            return
        response_status = result[1] if isinstance(result, tuple) else 200
        _respond(handler, *result)
        _do_audit_log(response_status)
    except BadRequest as e:
        _respond(handler, *json_error(str(e), 400))
        _do_audit_log(400)
    except Exception as e:
        # P0-03: Log full traceback with structured logging; return generic error
        logger.error(
            "Unhandled exception in API dispatch [module=%s] [method=%s] [path=%s]: %s: %s",
            resource, method, path, type(e).__name__, e,
            exc_info=True
        )
        _respond(handler, *json_error("Internal server error", 500))
        _do_audit_log(500)


def _respond(handler: BaseHTTPRequestHandler, data: dict, status: int = 200):
    """Send a JSON response with security headers and CORS.

    CORS behavior (P0-01):
    - Development mode (YULEOSH_ENV=development): Access-Control-Allow-Origin: *
    - Production mode: validates Origin against allowed origins list.
      localhost:18789 (desktop client) is always permitted.
    """
    # Determine CORS origin based on request Origin header
    request_origin = handler.headers.get("Origin")
    cors_origin = get_cors_origin(request_origin)

    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", cors_origin)
    if cors_origin != "*":
        handler.send_header("Vary", "Origin")
    handler.send_header("Content-Security-Policy", "default-src 'self'")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
