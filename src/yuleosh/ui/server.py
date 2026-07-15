#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""OSH Dashboard Server — lightweight HTTP server for the Web UI.

Includes multi-tenant auth (organizations, projects, users) alongside
the original API-key based auth and all original dashboard routes.
"""
import gzip
import http.server
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

# Ensure project root is importable
# NOTE (CQ-P2-02): Using sys.path.insert as a dev convenience. For production,
# install the package with `pip install -e .` or `pip install .` and remove
# this block along with the second sys.path.insert below.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from yuleosh.store import Store

# Route modules — extracted from the monolithic handler
from yuleosh.ui.routes.helpers import (
    _add_cors_header,
    _compute_etag,
    _format_http_datetime,
    _parse_http_datetime,
    _send_security_headers,
)
from yuleosh.ui.routes.api_routes import (
    handle_status,
    handle_health,
    list_evidence,
    list_reviews,
    list_ci_results,
)

# NOTE (CQ-P2-02): Duplicate path insert — remove both when pip-installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from yuleosh.ui.auth import (
        AUTH_ENABLED,
        API_KEY,
        is_authenticated,
        create_session as legacy_create_session,
        get_login_page as legacy_login_page,
        cleanup_sessions,
    )
except ImportError:
    AUTH_ENABLED = False
    API_KEY = None
    def is_authenticated(session_id): return True
    def create_session(api_key): return None
    def get_login_page(): return "<html><body><h1>Auth Not Configured</h1></body></html>"
    def cleanup_sessions(): pass

# Multi-tenant auth extension
try:
    from yuleosh.ui.auth_extended import (
        handle_signin,
        handle_org_create,
        handle_session_info,
        handle_logout,
        handle_project_list,
        handle_project_create,
        handle_org_info,
    )
    TENANT_AUTH = True
except ImportError as e:
    TENANT_AUTH = False
    print(f"[OSH] Tenant auth not available: {e}", file=sys.stderr)

# API v1 router
try:
    from yuleosh.api.router import dispatch as api_v1_dispatch
except ImportError:
    def api_v1_dispatch(handler, path):
        handler.send_response(501)
        handler.send_header("Content-Type", "application/json")
        _add_cors_header(handler)
        _send_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(json.dumps({"ok": False, "error": "API layer not available"}).encode())

# Rate limiter
try:
    from yuleosh.api.ratelimit import check_rate_limit
except ImportError:
    def check_rate_limit(ip): return True, 0

# Audit logging
try:
    from yuleosh.api.audit import log_request as _audit_log
except ImportError:
    def _audit_log(method, path, status, ip, duration): pass


OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_DIR = Path(__file__).parent
PAGES_DIR = UI_DIR / "pages"
PORT = int(os.environ.get("OSH_PORT", "8080"))


class OSHHandler(http.server.BaseHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        self._request_start_time = 0.0
        self._response_status = 200
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Override send_response to capture status code for audit logging
    # ------------------------------------------------------------------

    def send_response(self, code, message=None):
        self._response_status = code
        super().send_response(code, message)

    # ------------------------------------------------------------------
    # Security headers helper
    # ------------------------------------------------------------------

    def _add_security_headers(self):
        _send_security_headers(self)

    # ------------------------------------------------------------------
    # Client IP helper
    # ------------------------------------------------------------------

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    # ------------------------------------------------------------------
    # Routing — GET
    # ------------------------------------------------------------------

    def do_GET(self):
        self._request_start_time = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Rate limiting
        allowed, retry_after = check_rate_limit(self._get_client_ip())
        if not allowed:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", str(retry_after))
            self._add_security_headers()
            _add_cors_header(self)
            self.send_header("X-RateLimit-Remaining", "0")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
            }).encode())
            self._log_audit()
            return

        # ── Public / no-auth-required endpoints ────────────────────────────
        if path == "/api/health":
            self._json_response(handle_health(self))
            self._log_audit()
            return
        if path == "/welcome":
            self._serve_page("welcome.html", {})
            self._log_audit()
            return
        if path == "/login":
            self._serve_page("login.html", {"msg": ""})
            self._log_audit()
            return
        if path == "/register":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            self._log_audit()
            return
        if path == "/org/setup":
            self._serve_page("org-setup.html", {})
            self._log_audit()
            return
        if path == "/project/select":
            self._serve_page("project-select.html", {})
            self._log_audit()
            return

        # ── Unified auth check for all protected routes (S-P1-01) ────────
        if not self._unified_auth_check():
            self._log_audit()
            return

        # ── Protected API routes ──────────────────────────────────────────
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            self._log_audit()
            return
        if path == "/api/auth/session":
            self._handle_api("session")
            self._log_audit()
            return
        if path == "/api/auth/logout":
            self._handle_api("logout")
            self._log_audit()
            return
        if path == "/api/project/list":
            self._handle_api("project_list")
            self._log_audit()
            return
        if path == "/api/org/info":
            self._handle_api("org_info")
            self._log_audit()
            return

        if path == "/" or path == "/index.html":
            # Check if first-time user — redirect to welcome wizard
            try:
                store = Store()
                cur = store.conn.execute("SELECT value FROM _meta WHERE key='wizard_completed'")
                row = cur.fetchone()
                if row and row["value"] == "1":
                    self._serve_file(UI_DIR / "marketing" / "index.html", "text/html; charset=utf-8")
                else:
                    self.send_response(302)
                    self._add_security_headers()
                    self.send_header("Location", "/welcome")
                    self.end_headers()
            except Exception as e:
                logging.warning("Signin redirect fallback: %s", e)
                self._serve_file(UI_DIR / "marketing" / "index.html", "text/html; charset=utf-8")
        elif path == "/pricing":
            self._serve_file(UI_DIR / "marketing" / "pricing.html", "text/html; charset=utf-8")
        elif path == "/en" or path == "/en/index.html":
            self._serve_file(UI_DIR / "marketing" / "en" / "index.html", "text/html; charset=utf-8")
        elif path == "/en/pricing":
            self._serve_file(UI_DIR / "marketing" / "en" / "pricing.html", "text/html; charset=utf-8")
        elif path == "/dashboard":
            self._serve_file(UI_DIR / "pages" / "dashboard-v5.html", "text/html; charset=utf-8")
        elif path == "/apikeys":
            self._serve_page("apikeys.html", {})
        elif path == "/api/status":
            self._json_response(handle_status(self))
        elif path == "/api/evidence":
            self._json_response(list_evidence(self))
        elif path == "/api/reviews":
            self._json_response(list_reviews(self))
        elif path == "/api/ci":
            self._json_response(list_ci_results(self))
        elif path == "/api/health":
            self._json_response(handle_health(self))
        elif path == "/health":
            self._serve_page("health.html", {})
        elif path == "/welcome":
            self._serve_page("welcome.html", {})
        elif path == "/onboarding":
            self._serve_page("onboarding.html", {})
        elif path == "/pipeline-flow":
            self._serve_file(UI_DIR / "pages" / "pipeline-flow.html", "text/html; charset=utf-8")
        elif path == "/demo":
            self._serve_page("demo.html", {})
        else:
            self._serve_page("404.html", {})
        self._log_audit()

    def do_POST(self):
        self._request_start_time = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Rate limiting
        allowed, retry_after = check_rate_limit(self._get_client_ip())
        if not allowed:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", str(retry_after))
            self._add_security_headers()
            _add_cors_header(self)
            self.send_header("X-RateLimit-Remaining", "0")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
            }).encode())
            self._log_audit()
            return

        # ── Public POST endpoints (no auth required) ────────────────────
        if path == "/_auth/login":
            self._handle_login()
            self._log_audit()
            return
        if path == "/api/auth/signin":
            self._handle_api("signin")
            self._log_audit()
            return

        # ── Unified auth check for all protected routes (S-P1-01) ────────
        if not self._unified_auth_check():
            self._log_audit()
            return

        # ── Protected POST endpoints ─────────────────────────────────────
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            self._log_audit()
            return
        if path == "/api/org/create":
            self._handle_api("org_create")
            self._log_audit()
            return
        if path == "/api/project/create":
            self._handle_api("project_create")
            self._log_audit()
            return
        if path == "/api/auth/logout":
            self._handle_api("logout")
            self._log_audit()
            return

        self._serve_page("404.html", {})
        self._log_audit()

    def do_DELETE(self):
        self._request_start_time = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            self._log_audit()
            return
        self._serve_page("404.html", {})
        self._log_audit()

    def do_OPTIONS(self):
        self.send_response(204)
        _add_cors_header(self)
        self._add_security_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.end_headers()

    # ------------------------------------------------------------------
    # Audit logging helper
    # ------------------------------------------------------------------

    def _log_audit(self):
        """Log the current request to the audit log."""
        duration_ms = (time.time() - self._request_start_time) * 1000
        path = urllib.parse.urlparse(self.path).path
        _audit_log(
            method=self.command,
            path=path,
            status_code=self._response_status,
            ip=self._get_client_ip(),
            duration_ms=round(duration_ms, 2),
        )

    # ------------------------------------------------------------------
    # Unified auth check (S-P1-01 / AR-P1-01)
    # ------------------------------------------------------------------

    def _unified_auth_check(self) -> bool:
        """Check auth via a single pipeline: legacy first, then tenant.

        This replaces the separate _check_auth calls for individual routes
        and ensures every protected route goes through the same pipeline.
        Returns True if allowed, False if denied (response sent).
        """
        # 1. Try legacy auth (API key + session cookie)
        if AUTH_ENABLED:
            headers = {}
            for k, v in self.headers.items():
                headers[k.lower()] = v
            if is_authenticated(headers):
                return True

            # Legacy auth is enabled but not authenticated — deny
            path = urllib.parse.urlparse(self.path).path
            if path.startswith("/api/"):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self._add_security_headers()
                _add_cors_header(self)
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "X-API-Key header required"}).encode())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._add_security_headers()
                self.end_headers()
                self.wfile.write(legacy_login_page().encode("utf-8"))
            return False

        return True

    # ------------------------------------------------------------------
    # API handler for tenant auth (for backward compatibility)
    # ------------------------------------------------------------------

    def _handle_api(self, action: str):
        """Dispatch to tenant auth or org/project handlers."""
        if not TENANT_AUTH:
            self._json_response({"error": "tenant auth not available"}, 501)
            return

        body = self._read_body()
        token = self._get_bearer_token()

        try:
            if action == "signin":
                result, status = handle_signin(body)
                self._json_response(result, status)
            elif action == "session":
                result, status = handle_session_info(token)
                self._json_response(result, status)
            elif action == "org_create":
                result, status = handle_org_create(body, token)
                self._json_response(result, status)
            elif action == "org_info":
                result, status = handle_org_info(token)
                self._json_response(result, status)
            elif action == "project_list":
                result, status = handle_project_list(token)
                self._json_response(result, status)
            elif action == "project_create":
                result, status = handle_project_create(body, token)
                self._json_response(result, status)
            elif action == "logout":
                result, status = handle_logout(token)
                self._json_response(result, status)
            else:
                self._json_response({"error": "unknown action"}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _read_body(self) -> dict:
        """Read and parse JSON request body."""
        from yuleosh.ui.routes.auth_routes import _read_body as _rb
        return _rb(self)

    def _get_bearer_token(self) -> Optional[str]:
        """Extract bearer token from Authorization header."""
        from yuleosh.ui.routes.auth_routes import _get_bearer_token as _gbt
        return _gbt(self)

    # ------------------------------------------------------------------
    # Legacy Auth
    # ------------------------------------------------------------------

    def _check_auth(self) -> bool:
        """Check authentication. Returns True if allowed, False if denied (response sent)."""
        if not AUTH_ENABLED:
            return True

        # Gather headers into a dict
        headers = {}
        for k, v in self.headers.items():
            headers[k.lower()] = v

        if is_authenticated(headers):
            return True

        # Not authenticated — check if it's an API call or browser request
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self._add_security_headers()
            _add_cors_header(self)
            self.end_headers()
            # Use standard {ok, error} format (CP-P1-02)
            self.wfile.write(json.dumps({"ok": False, "error": "X-API-Key header required"}).encode())
            return False
        else:
            # Serve login page for browser requests
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._add_security_headers()
            self.end_headers()
            self.wfile.write(legacy_login_page().encode("utf-8"))
            return False

    def _handle_login(self):
        """Handle POST /_auth/login — validate API key and set session cookie."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        params = urllib.parse.parse_qs(body)
        api_key_input = params.get("api_key", [""])[0]

        if not api_key_input:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._add_security_headers()
            self.end_headers()
            self.wfile.write(legacy_login_page("API key is required").encode("utf-8"))
            return

        import hmac
        if hmac.compare_digest(api_key_input, API_KEY):
            # Success — set session cookie and redirect to dashboard
            _, cookie_val = legacy_create_session()
            self.send_response(302)
            self.send_header("Set-Cookie",
                f"osh_session={cookie_val}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400")
            self._add_security_headers()
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._add_security_headers()
            self.end_headers()
            self.wfile.write(legacy_login_page("Invalid API key").encode("utf-8"))

    # ------------------------------------------------------------------
    # Endpoints — page/file serving
    # ------------------------------------------------------------------

    def _serve_page(self, name: str, context: dict):
        """Serve an HTML page from the pages/ directory, with simple template substitution."""
        filepath = PAGES_DIR / name
        if not filepath.exists():
            # Fallback: serve static 404 page
            fallback = PAGES_DIR / "404.html"
            if fallback.exists():
                content = fallback.read_text(encoding="utf-8")
                body = content.encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._add_security_headers()
                _add_cors_header(self)
                self.end_headers()
                self.wfile.write(body)
                return
            self._json_response({"error": "page not found"}, 404)
            return

        content = filepath.read_text(encoding="utf-8")
        # Simple {key} substitution for context variables
        for key, value in context.items():
            content = content.replace("{" + key + "}", str(value))

        body = content.encode("utf-8")
        etag = _compute_etag(body)
        last_mod = filepath.stat().st_mtime
        inm = self.headers.get("If-None-Match")
        ims = self.headers.get("If-Modified-Since")
        if inm == etag or (ims and abs(last_mod - _parse_http_datetime(ims)) < 2):
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", _format_http_datetime(last_mod))
            self._add_security_headers()
            _add_cors_header(self)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", _format_http_datetime(last_mod))
        self._add_security_headers()
        _add_cors_header(self)
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath: Path, mime: str):
        """Serve a static file with caching and security headers."""
        if filepath.exists():
            data = filepath.read_bytes()
            etag = _compute_etag(data)
            last_mod = filepath.stat().st_mtime
            inm = self.headers.get("If-None-Match")
            ims = self.headers.get("If-Modified-Since")
            if inm == etag or (ims and abs(last_mod - _parse_http_datetime(ims)) < 2):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", _format_http_datetime(last_mod))
                self._add_security_headers()
                _add_cors_header(self)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", _format_http_datetime(last_mod))
            self._add_security_headers()
            _add_cors_header(self)
            self.end_headers()
            self.wfile.write(data)
        else:
            # Serve custom 404 page for missing static files
            fallback = PAGES_DIR / "404.html"
            if fallback.exists():
                content = fallback.read_text(encoding="utf-8")
                body = content.encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._add_security_headers()
                _add_cors_header(self)
                self.end_headers()
                self.wfile.write(body)
                return
            self._json_response({"error": "file not found"}, 404)

    def _json_response(self, data, status: int = 200):
        # Serve custom 500 page for browser requests
        if status == 500 and 'text/html' in self.headers.get('Accept', ''):
            fallback = PAGES_DIR / "500.html"
            if fallback.exists():
                content = fallback.read_text(encoding="utf-8")
                body = content.encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._add_security_headers()
                _add_cors_header(self)
                self.end_headers()
                self.wfile.write(body)
                return
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        accept_encoding = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_encoding and len(body) > 512:
            body_gz = gzip.compress(body)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Encoding", "gzip")
            self._add_security_headers()
            _add_cors_header(self)
            self.send_header("Content-Length", str(len(body_gz)))
            self.end_headers()
            self.wfile.write(body_gz)
        else:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self._add_security_headers()
            _add_cors_header(self)
            self.end_headers()
            self.wfile.write(body)

    def _get_status(self) -> dict:
        return handle_status(self)

    def _get_health(self) -> dict:
        return handle_health(self)

    def _list_evidence(self) -> dict:
        ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
        files = []
        if ev_dir.exists():
            for f in sorted(ev_dir.iterdir()):
                if f.is_file() and f.name != "compliance-pack.zip":
                    files.append({
                        "name": f.name,
                        "size": f"{f.stat().st_size} B",
                        "mtime": f.stat().st_mtime,
                    })
            zip_file = ev_dir / "compliance-pack.zip"
            if zip_file.exists():
                files.append({
                    "name": "compliance-pack.zip 🎯",
                    "size": f"{zip_file.stat().st_size} B",
                    "mtime": zip_file.stat().st_mtime,
                })
        return {"files": files, "count": len(files)}

    def _get_reviews(self) -> dict:
        rev_dir = Path(OSH_HOME) / ".osh" / "reviews"
        sessions = []
        if rev_dir.exists():
            for d in sorted(rev_dir.iterdir()):
                if d.is_dir():
                    sess_file = d / "review-session.json"
                    if sess_file.exists():
                        data = json.loads(sess_file.read_text())
                        sessions.append(data)
        return {"sessions": sessions, "count": len(sessions)}

    def _get_ci_results(self) -> dict:
        ci_dir = Path(OSH_HOME) / ".osh" / "ci"
        results = []
        if ci_dir.exists():
            for f in sorted(ci_dir.glob("layer*.json")):
                data = json.loads(f.read_text())
                results.append(data)
        return {"results": results, "count": len(results)}

    def log_message(self, format, *args):
        sys.stderr.write(f"[OSH UI] {args[0]}\n")


def main(port: int | None = None):
    """Start the OSH Dashboard server.

    Args:
        port: Optional port override (overrides OSH_PORT env / default 8080).
    """
    cleanup_sessions()

    actual_port = port if port is not None else PORT
    server = http.server.HTTPServer(("0.0.0.0", actual_port), OSHHandler)

    if AUTH_ENABLED:
        print(f"🔐 Legacy auth enabled (YULEOSH_API_KEY set)")
    if TENANT_AUTH:
        print(f"🏢 Multi-tenant auth enabled")
    if not AUTH_ENABLED and not TENANT_AUTH:
        print(f"⚠️  Auth disabled — set YULEOSH_API_KEY or install auth_extended.py")

    # Build API route listing from router ROUTES + _LAZY_HANDLERS
    api_routes = []
    try:
        from yuleosh.api.router import ROUTES as api_routes_dict
        from yuleosh.api.router import _LAZY_HANDLERS as lazy_dict
        all_handlers = dict(api_routes_dict)
        all_handlers.update({k: "__lazy__" for k in lazy_dict if k not in all_handlers})
        for name in sorted(all_handlers.keys()):
            doc = f"/api/v1/{name} (lazy-loaded)"
            api_routes.append((f"/api/v1/{name}", doc))
    except Exception as e:
        logging.warning("API route listing failed: %s", e)
        api_routes = [
            ("/api/v1/health", "System health status"),
            ("/api/v1/wizard", "Wizard setup API"),
            ("/api/v1/spec", "Spec validate & diff"),
            ("/api/v1/pipeline", "Run & list pipelines"),
            ("/api/v1/ci", "Run & list CI layers"),
            ("/api/v1/review", "Auto & task review"),
            ("/api/v1/evidence", "Generate & list evidence"),
            ("/api/v1/project", "Project CRUD"),
            ("/api/v1/stats", "Project statistics & trends"),
            ("/api/v1/notify", "Notification config"),
            ("/api/v1/apikeys", "Manage API keys"),
            ("/api/v1/webhooks", "Webhook management"),
            ("/api/v1/audit", "Audit log (admin)"),
        ]

    print(f"""
🚀 yuleOSH Dashboard
   ────────────────────────────────────
   Dashboard:   http://localhost:{actual_port}/
   API v1:      http://localhost:{actual_port}/api/v1/

   API Endpoints:""")
    for route, desc in api_routes:
        print(f"     {route:35s} — {desc}")
    print(f"   Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
