#!/usr/bin/env python3
"""OSH Dashboard Server — lightweight HTTP server for the Web UI.

Includes multi-tenant auth (organizations, projects, users) alongside
the original API-key based auth and all original dashboard routes.
"""
import gzip
import hashlib
import http.server
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.store import Store


# ------------------------------------------------------------------
# Caching & compression helpers
# ------------------------------------------------------------------


def _compute_etag(content: bytes) -> str:
    """Return a weak ETag for the given content."""
    return f'W/"{hashlib.md5(content).hexdigest()}"'


def _format_http_datetime(timestamp: float) -> str:
    """Format a Unix timestamp as an HTTP-date string (RFC 7231)."""
    import datetime as dt
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _parse_http_datetime(date_str: str) -> float:
    """Parse an HTTP-date string back to a Unix timestamp."""
    import datetime as dt
    for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            parsed = dt.datetime.strptime(date_str.strip(), fmt)
            return parsed.replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    return 0.0


def _send_gzipped_json(handler, data: dict, status: int = 200):
    """Send a JSON response with gzip compression and CORS headers."""
    body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    accept_encoding = handler.headers.get("Accept-Encoding", "")
    if "gzip" in accept_encoding and len(body) > 512:
        body_gz = gzip.compress(body)
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Encoding", "gzip")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Content-Length", str(len(body_gz)))
        handler.end_headers()
        handler.wfile.write(body_gz)
    else:
        handler._json_response(data, status)

# Add parent dir to path for auth import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from src.ui.auth import (
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
    from src.ui.auth_extended import (
        get_session_user,
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
    from src.api.router import dispatch as api_v1_dispatch
except ImportError:
    def api_v1_dispatch(handler, path):
        handler.send_response(501)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Access-Control-Allow-Origin", "*")
        _send_security_headers(handler)
        handler.end_headers()
        handler.wfile.write(json.dumps({"ok": False, "error": "API layer not available"}).encode())

# Rate limiter
try:
    from src.api.ratelimit import check_rate_limit, get_remaining
except ImportError:
    def check_rate_limit(ip): return True, 0
    def get_remaining(ip): return 0

# Audit logging
try:
    from src.api.audit import log_request as _audit_log
except ImportError:
    def _audit_log(method, path, status, ip, duration): pass


def _send_security_headers(handler):
    """Send security headers on the given handler."""
    handler.send_header("Content-Security-Policy", "default-src 'self'")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Strict-Transport-Security", "max-age=31536000")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

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
        self.send_header("Content-Security-Policy", "default-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    # ------------------------------------------------------------------
    # Client IP helper
    # ------------------------------------------------------------------

    def _get_client_ip(self) -> str:
        return self.client_address[0]

    # ------------------------------------------------------------------
    # Routing
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-RateLimit-Remaining", "0")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
            }).encode())
            self._log_audit()
            return

        # API v1 routes — dispatch to modular handlers
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            self._log_audit()
            return

        # Healthcheck — always accessible
        if path == "/api/health":
            self._json_response(self._get_health())
            self._log_audit()
            return

        # Health dashboard page
        if path == "/health":
            self._serve_page("health.html", {})
            self._log_audit()
            return

        # Tenant auth endpoints
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

        # Welcome/wizard page (no auth required)
        if path == "/welcome":
            self._serve_page("welcome.html", {})
            self._log_audit()
            return

        # Tenant auth pages (no legacy auth required)
        if path == "/login":
            self._serve_page("login.html", {"msg": ""})
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

        # Legacy auth check for all other routes
        if not self._check_auth():
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
            self._serve_file(UI_DIR / "dashboard.html", "text/html")
        elif path == "/apikeys":
            self._serve_page("apikeys.html", {})
        elif path == "/api/status":
            self._json_response(self._get_status())
        elif path == "/api/evidence":
            self._json_response(self._list_evidence())
        elif path == "/api/reviews":
            self._json_response(self._get_reviews())
        elif path == "/api/ci":
            self._json_response(self._get_ci_results())
        elif path == "/api/health":
            self._json_response(self._get_health())
        elif path == "/health":
            self._serve_page("health.html", {})
        elif path == "/welcome":
            self._serve_page("welcome.html", {})
        elif path == "/onboarding":
            self._serve_page("onboarding.html", {})
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-RateLimit-Remaining", "0")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": False,
                "error": f"Rate limit exceeded. Retry after {retry_after} seconds."
            }).encode())
            self._log_audit()
            return

        # API v1 routes — dispatch to modular handlers
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            self._log_audit()
            return

        # Legacy login endpoint — always accessible
        if path == "/_auth/login":
            self._handle_login()
            self._log_audit()
            return

        # Tenant auth endpoints — always accessible
        if path == "/api/auth/signin":
            self._handle_api("signin")
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

        # Legacy auth check
        if not self._check_auth():
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
        self.send_header("Access-Control-Allow-Origin", "*")
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
    # API handler for tenant auth
    # ------------------------------------------------------------------

    def _handle_api(self, action: str):
        """Dispatch to tenant auth or org/project handlers."""
        if not TENANT_AUTH:
            self._json_response({"error": "tenant auth not available"}, 501)
            return

        body = self._read_body()

        # Extract bearer token from Authorization header
        token = self._get_bearer_token()

        try:
            if action == "signin":
                result, status = handle_signin(body)
                # If signin returns a token (needs_org flow), pass it back
                self._json_response(result, status)
                return

            elif action == "session":
                result, status = handle_session_info(token)
                self._json_response(result, status)
                return

            elif action == "org_create":
                # The body might have email from a magic-token flow
                result, status = handle_org_create(body, token)
                self._json_response(result, status)
                return

            elif action == "org_info":
                result, status = handle_org_info(token)
                self._json_response(result, status)
                return

            elif action == "project_list":
                result, status = handle_project_list(token)
                self._json_response(result, status)
                return

            elif action == "project_create":
                result, status = handle_project_create(body, token)
                self._json_response(result, status)
                return

            elif action == "logout":
                result, status = handle_logout(token)
                self._json_response(result, status)
                return

            else:
                self._json_response({"error": "unknown action"}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _read_body(self) -> dict:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _get_bearer_token(self) -> Optional[str]:
        """Extract bearer token from Authorization header."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized", "message": "X-API-Key header required"}).encode())
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
    # Endpoints
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
                self.send_header("Access-Control-Allow-Origin", "*")
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", _format_http_datetime(last_mod))
        self._add_security_headers()
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath: Path, mime: str):
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
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", _format_http_datetime(last_mod))
            self._add_security_headers()
            self.send_header("Access-Control-Allow-Origin", "*")
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
                self.send_header("Access-Control-Allow-Origin", "*")
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
                self.send_header("Access-Control-Allow-Origin", "*")
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body_gz)))
            self.end_headers()
            self.wfile.write(body_gz)
        else:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self._add_security_headers()
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    def _get_status(self) -> dict:
        return {
            "status": "running",
            "osh_home": OSH_HOME,
            "version": "1.0.0",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }

    def _get_health(self) -> dict:
        return {
            "status": "ok",
            "version": "1.0.0",
            "uptime_seconds": None,
            "auth_enabled": AUTH_ENABLED,
            "tenant_auth": TENANT_AUTH,
            "osh_home": OSH_HOME,
        }

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


def main():
    cleanup_sessions()

    server = http.server.HTTPServer(("0.0.0.0", PORT), OSHHandler)

    if AUTH_ENABLED:
        print(f"🔐 Legacy auth enabled (YULEOSH_API_KEY set)")
    if TENANT_AUTH:
        print(f"🏢 Multi-tenant auth enabled")
    if not AUTH_ENABLED and not TENANT_AUTH:
        print(f"⚠️  Auth disabled — set YULEOSH_API_KEY or install auth_extended.py")

    # Build API route listing from router ROUTES dict
    api_routes = []
    try:
        from src.api.router import ROUTES as api_routes_dict
        for name, handler in sorted(api_routes_dict.items()):
            doc = (handler.__doc__ or "").strip()
            # Shorten verbose docstrings for clean display
            if doc.startswith("Route to") or doc.startswith("Handle") or doc == "":
                doc = f"/api/v1/{name}"
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
   Dashboard:   http://localhost:{PORT}/
   API v1:      http://localhost:{PORT}/api/v1/

   API Endpoints:""")
    for route, desc in api_routes:
        print(f"     {route:35s} — {desc}")
    print(f"   Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()



    # ── v0.9.0: Async pipeline + usage handlers ─────────────────────────────

    def _handle_pipeline_status(self, path: str):
        """GET /api/v1/pipeline/status/{job_id}"""
        job_id = path.rsplit("/", 1)[-1]
        try:
            from pipeline.async_runner import get_job_status
            status = get_job_status(job_id)
            if status:
                self._json_response(status)
            else:
                self._json_response({"error": "Job not found"}, 404)
        except Exception:
            self._json_response({"error": "Pipeline status unavailable"}, 500)

    def _handle_usage(self):
        """GET /api/v1/usage — current org usage summary"""
        token = self._get_bearer_token()
        if not token:
            self._json_response({"error": "Unauthorized"}, 401)
            return
        try:
            from src.ui.auth_extended import get_session_user
            user = get_session_user(token)
            if not user:
                self._json_response({"error": "Invalid session"}, 401)
                return
            store = Store()
            from usage.metering import get_usage_summary
            summary = get_usage_summary(store, user["org_id"])
            self._json_response(summary)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json_response({"error": str(e)}, 500)


if __name__ == "__main__":
    main()
