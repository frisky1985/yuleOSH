# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

    body = read_body(handler)
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
        return _respond(handler, *json_error(f"Unknown resource: {resource}", 404))

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
