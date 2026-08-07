#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard Server — OSHHandler HTTP server.

Serves the yuleOSH web dashboard with API routes, auth, static files,
and project management.  Routes are extracted to yuleosh/ui/routes/*.

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
import re
import secrets
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler

from yuleosh.store import Store

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

# ── T2 (v3.9.0): CSP — single source for every HTML response ────────────
#   script-src uses a per-request nonce (裁决 B5 ①): _serve_static/
#   _serve_file rewrite inline RSC <script> tags and inject the matching
#   nonce into the policy — no build coupling, per-response randomness.
#   'unsafe-inline' is allowed in style-src / style-src-attr: the static
#   export has 31 inline style= attributes AND the React runtime injects
#   <style> elements dynamically (hash-impossible) — style injection is
#   not an XSS vector, so script-src stays strict while styles keep
#   'unsafe-inline' (verified by browser test T-T2-08).
#   'unsafe-eval' is REMOVED (裁决 B6): the only Function( in the bundle is
#   core-js's global-detection fallback
#   (frontend/out/_next/static/chunks/0cz1d0mv5g_q7.js:
#   ``Function("return this")``) — short-circuited dead code wherever
#   globalThis exists (all modern browsers), so it is never executed.
#   nginx (deploy/nginx/nginx.conf) intentionally does NOT set its own
#   CSP — a static nginx CSP would AND with this per-request nonce policy
#   and block the inline RSC scripts (single source, T-T2-10).
def _format_csp(directives: dict) -> str:
    """Serialize a {directive: [sources]} dict into a CSP header value."""
    return "; ".join(
        f"{k} {' '.join(v)}" for k, v in directives.items()
    ) + ";"


def _base_csp_directives(nonce: str) -> dict:
    """The strict base policy — single source for every HTML response.

    - script-src: per-request nonce ONLY (裁决 B5 ①) — no 'unsafe-inline',
      no 'unsafe-eval' (B6: core-js Function("return this") fallback is
      short-circuited dead code wherever globalThis exists).
    - style-src 'unsafe-inline': static export's inline style= attributes
      AND the React runtime's dynamically injected <style> elements
      (hash-impossible; style injection is not an XSS vector).
    """
    return {
        "default-src": ["'self'"],
        "script-src": ["'self'", f"'nonce-{nonce}'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "style-src-attr": ["'unsafe-inline'"],
        "font-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "connect-src": ["'self'"],
        "frame-src": ["'self'"],  # defensive: nothing uses frames today
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "frame-ancestors": ["'self'"],
        "form-action": ["'self'"],
    }


# ── T2.2 exception (注明用途) ──────────────────────────────────────────────
#   The legacy Python templates (ui/pages/*, ui/marketing/*) genuinely
#   load a few external resources at runtime (verified by byte-scan of
#   each template + Chrome console).  The contract's "产物零引用" premise
#   holds for frontend/out/ (Next.js export) but NOT for these served
#   templates — so the origins they actually reference are appended to
#   the policy, per T2.2's own exception clause ("实际在用，注明用途").
#   The scan is by template bytes, so the allowlist can never drift from
#   the templates themselves.  js.stripe.com is listed here only if a
#   template starts referencing it — none do today.
_LEGACY_EXTERNAL = [
    # (marker_bytes, directive, origin)
    (b"fonts.googleapis.com", "style-src", "https://fonts.googleapis.com"),
    (b"fonts.googleapis.com", "font-src", "https://fonts.gstatic.com"),
    (b"cdn.tailwindcss.com", "script-src", "https://cdn.tailwindcss.com"),
    (b"js.stripe.com", "script-src", "https://js.stripe.com"),
    (b"js.stripe.com", "frame-src", "https://js.stripe.com"),
    (b"js.stripe.com", "connect-src", "https://api.stripe.com"),
]


def _csp_for_html(nonce: str, html: bytes) -> str:
    """Build the CSP for one HTML response.

    Starts from the strict base and appends the external origins the
    template actually references (legacy templates only — frontend/out
    pages reference nothing external, so they stay strict).
    """
    directives = _base_csp_directives(nonce)
    for marker, directive, origin in _LEGACY_EXTERNAL:
        if marker in html and origin not in directives[directive]:
            directives[directive].append(origin)
    return _format_csp(directives)


# Strict-form template (no legacy extras) — kept for tests/comments.
CSP_POLICY_TEMPLATE = _format_csp(_base_csp_directives("{nonce}"))

# Inline <script> without a src attribute (RSC flight data + legacy page
# inline JS).  External scripts are never touched.
_INLINE_SCRIPT_RE = re.compile(rb"<script(?![^>]*\bsrc=)([^>]*)>", re.IGNORECASE)


def _inject_csp_nonce(html: bytes):
    """Rewrite inline <script> tags with a per-request nonce (B5 ①).

    Returns ``(rewritten_html, nonce)``.  The nonce is random per
    response; the caller must pair it with the CSP header built from
    ``CSP_POLICY_TEMPLATE``.
    """
    nonce = secrets.token_urlsafe(16)
    rewritten = _INLINE_SCRIPT_RE.sub(
        lambda m: b'<script nonce="' + nonce.encode() + b'"' + m.group(1) + b">",
        html,
    )
    return rewritten, nonce


# ── Rate limiting ───────────────────────────────────────────────────────────

_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 60          # requests per window
RATE_LIMIT_WINDOW = 60.0     # seconds


def check_rate_limit(client_ip: str, max_requests: int = RATE_LIMIT_MAX,
                      window: float = RATE_LIMIT_WINDOW) -> tuple[bool, float]:
    """Check if client_ip is within rate limits.  Returns (allowed, retry_after)."""
    now = time.time()
    bucket = _rate_limit_buckets[client_ip]
    # Prune old entries
    while bucket and bucket[0] < now - window:
        bucket.pop(0)
    if len(bucket) >= max_requests:
        retry_after = window - (now - bucket[0])
        return False, round(retry_after, 1)
    bucket.append(now)
    return True, 0.0


# ── API v1 dispatch ────────────────────────────────────────────────────────

def api_v1_dispatch(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Dispatch /api/v1/* requests to the modular router.

    Returns True when the router handled the request (response written).
    Returns False only for non-API paths, so callers fall back to
    page/static serving.

    P0-1 guarantee: a /api/v1/* path is NEVER degraded to an HTML page.
    If the router cannot serve it (e.g. missing YULEOSH_JWT_SECRET raises
    at import time, or any other unexpected failure), a JSON 500 error is
    written instead, so API clients always receive machine-readable
    responses.
    """
    if not path.startswith("/api/v1/"):
        return False
    try:
        from yuleosh.api.router import dispatch
        dispatch(handler, path)
    except Exception as e:
        # Fail closed for API paths — never fall through to HTML page
        # serving (the P0-1 symptom: /api/v1/* answered with a 200 HTML
        # landing page).
        try:
            handler._json_response(
                {"ok": False, "error": f"API dispatch failed: {e}"}, 500
            )
        except Exception:
            # No live HTTP plumbing (e.g. bare mock in unit tests) —
            # nothing writable, but still report handled so callers do
            # not serve an HTML page for an API path.
            pass
    return True


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

    def _add_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def _serve_static(self, path: str) -> None:
        """Serve a static file from frontend/out/."""
        OSH_HOME_DIR = Path(os.environ.get("HOME", "."))
        # Look for frontend/out at the repo root
        candidates = [
            # v3.12.x CI 真跑修复: repo-root checkout (CI download-artifact
            # places frontend/out here). This is the canonical location.
            _REPO_ROOT / "frontend" / "out",
            Path(OSH_HOME) / "frontend" / "out",
            OSH_HOME_DIR / ".openclaw" / "workspace" / "tasks" / "yuleOSH" / "frontend" / "out",
        ]
        static_dir = None
        for c in candidates:
            if c.exists():
                static_dir = c
                break

        if not static_dir:
            self._json_response({"error": "Static files not found"}, 500)
            return

        # Resolve file path
        if path == "/" or path == "":
            file_path = static_dir / "index.html"
        else:
            # Strip leading / and sanitize
            rel = path.lstrip("/")
            file_path = static_dir / rel
            # If path is a directory, try index.html
            if file_path.is_dir():
                file_path = file_path / "index.html"

        # Security: prevent directory traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(static_dir.resolve())):
                file_path = static_dir / "404.html"
        except (ValueError, OSError):
            file_path = static_dir / "404.html"

        if not file_path.exists():
            file_path = static_dir / "404.html"
            if not file_path.exists():
                self._json_response({"error": "Not found"}, 404)
                return

        mime_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }
        ext = file_path.suffix.lower()
        content_type = mime_map.get(ext, "application/octet-stream")

        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # T2 (v3.9.0, SHALL-T2.1): HTML responses get the nonce CSP header
        # (inline RSC scripts are rewritten with the matching nonce).  The
        # body length changes after injection — set it after the rewrite.
        if ext == ".html" or file_path.name == "index.html":
            data, nonce = _inject_csp_nonce(data)
            self.send_header("Content-Security-Policy",
                             _csp_for_html(nonce, data))
        self.send_header("Content-Length", str(len(data)))
        # M-2 (SEC-P2): cache-control for static assets.
        #   - content-hashed build artifacts (_next/static/*.js etc.) are
        #     immutable → long-lived public cache;
        #   - HTML documents are NEVER long-cached (updates must be visible);
        #   - non-hashed assets get a short max-age only (no immutable).
        if self._is_immutable_asset(file_path):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        elif ext == ".html" or file_path.name == "index.html":
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _is_immutable_asset(file_path: Path) -> bool:
        """True for content-hashed build artifacts (M-2).

        Conservative rule: the file must live under a build output dir
        (``_next/static`` or ``static``) AND its name must look like
        ``<8+ alnum/-/_>.<ext>`` — the Next.js ``[name].[hash].js`` pattern.
        User-uploaded resources never match (no hash in name, or not under
        a build dir), so they are never marked immutable.
        """
        rel = str(file_path)
        if "/_next/static/" not in rel and "/static/" not in rel:
            return False
        name = file_path.name
        stem = name.rsplit(".", 1)[0] if "." in name else ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", stem or ""):
            return False
        return file_path.suffix.lower() in (".js", ".css", ".woff", ".woff2", ".png", ".svg")

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

    def _get_health(self) -> dict:
        from yuleosh.ui.routes import handle_health
        return handle_health(self)

    def _get_status(self) -> dict:
        from yuleosh.ui.routes import handle_status
        return handle_status(self)

    def _list_evidence(self) -> list:
        from yuleosh.ui.routes import list_evidence
        return list_evidence(self)

    def _get_reviews(self) -> list:
        from yuleosh.ui.routes import list_reviews
        return list_reviews(self)

    def _get_ci_results(self) -> list:
        from yuleosh.ui.routes import list_ci_results
        return list_ci_results(self)

    def _handle_api(self, action: str) -> None:
        from yuleosh.ui.routes import handle_api_action
        # FIX (v3.9.0 P1): handle_api_action already sends the response
        # (via auth_routes._send_json_response → self._json_response).  The
        # previous ``result = ...; self._json_response(result)`` emitted a
        # SECOND HTTP response ("…}HTTP/1.0 200 OK…null") on the same
        # connection — corrupted wire output for every /api/auth/* route.
        handle_api_action(self, action)

    def _handle_login(self) -> None:
        from yuleosh.ui.routes import handle_auth_login
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        result = handle_auth_login(self, body)
        if isinstance(result, dict):
            self._json_response(result)
        else:
            self.send_response(302)
            self.send_header("Location", "/dashboard")
            self.end_headers()

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

    # ── Serve file/page (called by routes) ────────────────────────────────

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        """Serve a file by its absolute path.

        F4 (v3.8.0): HTML documents get ``Cache-Control: no-cache`` (aligned
        with M-2's ``_serve_static`` semantics) so page updates are always
        visible; non-HTML content keeps the default (no long-lived cache).
        """
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            # F4: pages must not be stale-cached (M-2 HTML rule).
            if "html" in content_type or file_path.suffix.lower() in (".html", ".htm"):
                self.send_header("Cache-Control", "no-cache")
                # T2 (v3.9.0, SHALL-T2.1): HTML responses carry the CSP
                # header with a per-request nonce covering the inline RSC
                # scripts (B5 ①).  Content-Length is set once, AFTER the
                # nonce rewrite (body length changes).
                data, nonce = _inject_csp_nonce(data)
                self.send_header("Content-Security-Policy",
                                 _csp_for_html(nonce, data))
            self.send_header("Content-Length", str(len(data)))
            self._add_security_headers()
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._serve_static("/404.html")

    def _serve_page(self, template_name: str, context: dict) -> None:
        """Render a dashboard template page."""
        ui_dir = UI_DIR
        template_path = ui_dir / template_name
        if template_path.exists():
            self._serve_file(template_path, "text/html; charset=utf-8")
            return
        # Fallback to pages/
        pages_path = ui_dir / "pages" / template_name
        if pages_path.exists():
            self._serve_file(pages_path, "text/html; charset=utf-8")
            return
        # Fallback to marketing/
        marketing_path = ui_dir / "marketing" / template_name
        if marketing_path.exists():
            self._serve_file(marketing_path, "text/html; charset=utf-8")
            return
        # Not found
        self._serve_static("/404.html")

    def log_message(self, format, *args):
        """Override default stderr logging with module-level logger."""
        try:
            msg = format % args if args else format
        except (TypeError, ValueError):
            msg = format
        logging.info("%s - %s", self.client_address[0], msg)


# ── Server launcher ────────────────────────────────────────────────────────

def main(host: str = "", port: int = 0):
    """Start the yuleOSH Dashboard Server.

    Host/port resolution order (for Docker/deploy flexibility):
      1. explicit args (if provided)
      2. YULEOSH_HOST / YULEOSH_PORT (or legacy OSH_HOST / OSH_PORT)
      3. defaults 127.0.0.1:8080
    """
    import os as _os
    if not host:
        host = _os.environ.get("YULEOSH_HOST") or _os.environ.get("OSH_HOST") or "127.0.0.1"
    if not port:
        try:
            port = int(_os.environ.get("YULEOSH_PORT") or _os.environ.get("OSH_PORT") or "8080")
        except ValueError:
            port = 8080
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure OSH_HOME exists
    os.makedirs(OSH_HOME, exist_ok=True)
    os.environ.setdefault("OSH_HOME", OSH_HOME)

    # Initialize store
    try:
        store = Store()
        logging.info("Store initialized at %s", store.db_path if hasattr(store, 'db_path') else "memory")
    except Exception as e:
        logging.warning("Store init failed (dashboard will work without it): %s", e)

    server = HTTPServer((host, port), OSHHandler)
    logging.info("yuleOSH Dashboard Server running on http://%s:%d", host, port)
    logging.info("AUTH_ENABLED=%s, OSH_HOME=%s", AUTH_ENABLED, OSH_HOME)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
