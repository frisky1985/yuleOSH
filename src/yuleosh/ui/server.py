#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard Server — OSHHandler HTTP server.

Serves the yuleOSH web dashboard with API routes, auth, static files,
and project management.  Routes are extracted to yuleosh/ui/routes/*.

TD-004 split (pure relocation): the HTTP security domain (rate limiting,
CSP, security headers) moved to yuleosh/ui/http_security.py, static &
page serving to yuleosh/ui/static_serving.py, API dispatch to
yuleosh/ui/api_dispatch.py and the server launcher to
yuleosh/ui/http_app.py.  This module keeps the OSHHandler orchestration
class and re-exports every public symbol so imports and test patches
keep working.

## Configuration

Environment variables:
  YULEOSH_AUTH_DISABLED=true|1|yes  — Disable authentication (default: enabled)
  OSH_HOME=<path>                   — Override project home directory

## API Endpoints

### Static files
  GET /, /index.html, /* — Serve frontend/out/ static files

### Pages
  GET /dashboard     — Dashboard landing page (dashboard-v5.html)
  GET /health        — Health check endpoint
  GET /status        — System status endpoint
  GET /login         — Login page

### API v0 (legacy)
  GET  /api/reviews        — List review sessions
  GET  /api/ci-results     — List CI layer results
  GET  /api/evidence       — List evidence artifacts
  POST /api/action         — Execute API action

### Auth
  POST /_auth/login  — Validate API key, set session cookie

## Rate Limiting
  - 60 requests per 60s window per client IP
  - Returns 429 with Retry-After header when exceeded

## Security Headers
  All responses include:
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - X-XSS-Protection: 1; mode=block
  - Referrer-Policy: strict-origin-when-cross-origin

## Routes
  HTTP method handlers (do_GET, do_POST, do_DELETE) delegate to:
    yuleosh.ui.routes.handler_helpers.handle_get
    yuleosh.ui.routes.handler_helpers.handle_post
    yuleosh.ui.routes.handler_helpers.handle_delete
"""

import json
import logging
import os
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer  # noqa: F401 — test-patch seam (mock.patch("yuleosh.ui.server.HTTPServer"))
from pathlib import Path
from typing import Optional

from yuleosh.store import Store  # noqa: F401 — test-patch seam (mock.patch("yuleosh.ui.server.Store"))

# ── Configuration ──────────────────────────────────────────────────────────

# M-3 (v3.6.1 P2-①): single source of truth for AUTH_ENABLED — the
# environment-variable interpretation lives only in yuleosh/ui/auth.py.
# server.py must NOT re-derive it (a second copy drifted in v3.6.x).
from yuleosh.ui.auth import AUTH_ENABLED

# Public paths that never require auth (SEC-C3 whitelist):
#   - health/status + health dashboard page
#   - login / registration / tenant onboarding pages (the tenant flow
#     keeps its token in localStorage — no cookie — so these pages must
#     be reachable without credentials)
#   - tenant auth endpoints (self-authenticating via Bearer JWT)
#   - frontend app pages (static HTML shells; all DATA comes from the
#     gated /api/* endpoints)
_PUBLIC_PATHS = frozenset({
    "/api/health", "/api/status", "/health",
    "/login", "/register", "/welcome", "/org/setup", "/project/select",
    "/api/auth/signin", "/api/auth/session", "/api/auth/logout",
    "/api/auth/refresh",
    "/api/org/create", "/api/org/info",
    "/api/project/create", "/api/project/list",
    "/", "/index.html", "/dashboard", "/kanban", "/audit-dashboard",
    "/billing", "/pipeline-flow", "/apikeys", "/onboarding", "/demo",
    "/pricing", "/en", "/en/index.html", "/en/pricing",
})
_PUBLIC_PREFIXES = ("/static/", "/assets/", "/_next/")

# Repo root inferred from this file (src/yuleosh/ui/server.py -> repo root).
# v3.12.x CI 真跑修复 (2026-08-07): the old default pointed at a hard-coded
# dev-machine path (~/.openclaw/workspace/tasks/yuleOSH), which does not exist
# on CI runners -> _serve_static returned 500 "Static files not found" and 4
# tests failed in CI. Inferring from __file__ works everywhere (local repo,
# CI checkout, installed package).
_REPO_ROOT = Path(__file__).resolve().parents[3]

OSH_HOME = os.environ.get(
    "OSH_HOME",
    str(_REPO_ROOT),
)

# ── TD-004: 职责域模块（纯搬移）────────────────────────────────────────
#   限流 + CSP + 安全响应头 → yuleosh/ui/http_security.py
#   兼容 re-export：tests/test_ui_server.py、tests/test_v391_p2_fixes.py、
#   tests/test_v390_t2_csp.py、tests/test_coverage_phase3_lowcov.py、
#   src/yuleosh/ui/routes/auth_routes.py 通过 server.<sym> 访问/打 patch。
from yuleosh.ui.http_security import (
    CSP_POLICY_TEMPLATE,  # noqa: F401 — 兼容 re-export (test_v390_t2_csp)
    RATE_LIMIT_MAX,  # noqa: F401 — 兼容 re-export (test_v391_p2_fixes)
    _add_security_headers,
    _csp_for_html,  # noqa: F401 — 兼容 re-export (test_v390_t2_csp)
    _inject_csp_nonce,  # noqa: F401 — 兼容 re-export (test_v390_t2_csp)
    _rate_limit_buckets,  # noqa: F401 — 兼容 re-export (test_ui_server/test_v391)
    check_rate_limit,  # noqa: F401 — 兼容 re-export (auth_routes/phase3 tests)
)

#   静态资源/页面文件服务 → yuleosh/ui/static_serving.py（方法体挂回 OSHHandler）
from yuleosh.ui.static_serving import (
    _is_immutable_asset as _is_immutable_asset_fn,
    _serve_file,
    _serve_page,
    _serve_static,
)

#   API v1 网关 + legacy API 委托 → yuleosh/ui/api_dispatch.py（方法体挂回 OSHHandler）
from yuleosh.ui.api_dispatch import (
    _get_ci_results,
    _get_health,
    _get_reviews,
    _get_status,
    _handle_api,
    _handle_login,
    _list_evidence,
    api_v1_dispatch,  # noqa: F401 — 兼容 re-export (test_coverage_phase3_lowcov mock.patch)
)

#   HTTP 服务启动编排 → yuleosh/ui/http_app.py
from yuleosh.ui.http_app import main

# ── OSHHandler ─────────────────────────────────────────────────────────────

UI_DIR = Path(__file__).resolve().parent


class OSHHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the yuleOSH dashboard."""

    def __init__(self, *args, **kwargs):
        self._request_start_time = time.time()
        self._response_status = 200
        super().__init__(*args, **kwargs)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    def _json_response(self, data: dict, status: int = 200,
                       extra_headers: Optional[list] = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # T1 (v3.9.0): extra headers before end_headers — used by the
        # tenant auth flow to emit Set-Cookie (access/refresh pair).
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(body)

    # TD-004: 方法体已搬移至职责域模块（纯搬移，挂回本类保持
    # ``mock.patch("yuleosh.ui.server.OSHHandler.*")`` 语义不变）
    _add_security_headers = _add_security_headers
    _serve_static = _serve_static
    _is_immutable_asset = staticmethod(_is_immutable_asset_fn)
    _serve_file = _serve_file
    _serve_page = _serve_page

    def _check_auth(self) -> bool:
        """If AUTH_ENABLED, check session/API key.  Returns True if OK.

        P1-3 (W-06): previously returned True unconditionally, leaving every
        legacy (non-/api/v1/) endpoint unauthenticated.  Now delegates to the
        real implementation (ui.auth.is_authenticated — API key compare_digest
        + signed session cookie + tenant JWT bearer).

        SEC-C3: AUTH_ENABLED is fail-closed by default (only
        YULEOSH_AUTH_DISABLED=1 turns it off).  A whitelist of public
        paths (health/status, login & tenant onboarding pages, tenant auth
        endpoints, static assets) is served without credentials; every
        other path — including the legacy /api/* data endpoints — requires
        a valid API key, session cookie or tenant JWT.
        """
        if not AUTH_ENABLED:
            return True
        # M-4 (v3.6.1 P2-②): strip the query string before whitelist matching
        # so ``/api/health?source=monitor&v=2`` is public like ``/api/health``.
        # Security boundary: the query is ONLY used to relax matching for
        # already-public paths — a non-public path with any query still
        # requires credentials (no query-based bypass).
        path_only = urllib.parse.urlsplit(self.path).path
        if path_only in _PUBLIC_PATHS or path_only.startswith(_PUBLIC_PREFIXES):
            return True
        from yuleosh.ui.auth import is_authenticated
        return is_authenticated(self.headers)

    # TD-004: legacy API 委托已搬移至 yuleosh/ui/api_dispatch.py
    _get_health = _get_health
    _get_status = _get_status
    _list_evidence = _list_evidence
    _get_reviews = _get_reviews
    _get_ci_results = _get_ci_results
    _handle_api = _handle_api
    _handle_login = _handle_login

    # ── HTTP method handlers ──────────────────────────────────────────────

    def do_GET(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_get, log_audit
        self._request_start_time = time.time()
        try:
            handle_get(self)
        except Exception as e:
            # W-1 (COR-C2 / Fix 4): never silently degrade an exception to a
            # 200 landing page — that hid real failures from monitoring (and
            # mismatched do_POST/do_DELETE, which already answer JSON 500).
            # API paths get a machine-readable JSON 500; page paths get a
            # plain 500 error page; full traceback goes to the logs.
            logging.error("GET %s: %s", self.path, e, exc_info=True)
            if self.path.startswith("/api/"):
                self._json_response({"error": "Internal server error"}, 500)
            else:
                body = b"<h1>500 Internal Server Error</h1>"
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._add_security_headers()
                self.end_headers()
                self.wfile.write(body)
            # W-1: audit must record the failure, not a phantom 200.
            self._response_status = 500
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_POST(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_post, log_audit
        self._request_start_time = time.time()
        try:
            handle_post(self)
        except Exception as e:
            # P1-7 (S-P1-05): never echo internal exception details to the
            # client — log full detail server-side, return a generic message.
            logging.error("POST %s: %s", self.path, e, exc_info=True)
            self._json_response({"error": "Internal server error"}, 500)
            # F3 (v3.8.0): audit must record the failure as 500, not the
            # finally-fallback 200 (aligned with do_GET's W-1 fix).
            self._response_status = 500
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_DELETE(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_delete, log_audit
        self._request_start_time = time.time()
        try:
            handle_delete(self)
        except Exception as e:
            # P1-7 (S-P1-05): generic message to client, details to logs.
            logging.error("DELETE %s: %s", self.path, e, exc_info=True)
            self._json_response({"error": "Internal server error"}, 500)
            # F3 (v3.8.0): audit must record the failure as 500, not 200.
            self._response_status = 500
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_OPTIONS(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_options
        handle_options(self)

    def log_message(self, format, *args):
        """Override default stderr logging with module-level logger."""
        try:
            msg = format % args if args else format
        except (TypeError, ValueError):
            msg = format
        logging.info("%s - %s", self.client_address[0], msg)


if __name__ == "__main__":
    main()
