#!/usr/bin/env python3
"""OSH Dashboard Server — lightweight HTTP server for the Web UI.

Includes multi-tenant auth (organizations, projects, users) alongside
the original API-key based auth and all original dashboard routes.
"""
import http.server
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

from src.store import Store

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
        handler.end_headers()
        handler.wfile.write(json.dumps({"ok": False, "error": "API layer not available"}).encode())

OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_DIR = Path(__file__).parent
PAGES_DIR = UI_DIR / "pages"
PORT = int(os.environ.get("OSH_PORT", "8080"))


class OSHHandler(http.server.BaseHTTPRequestHandler):

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API v1 routes — dispatch to modular handlers
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            return

        # Healthcheck — always accessible
        if path == "/api/health":
            self._json_response(self._get_health())
            return

        # Health dashboard page
        if path == "/health":
            self._serve_page("health.html", {})
            return

        # Tenant auth endpoints
        if path == "/api/auth/session":
            self._handle_api("session")
            return
        if path == "/api/auth/logout":
            self._handle_api("logout")
            return
        if path == "/api/project/list":
            self._handle_api("project_list")
            return
        if path == "/api/org/info":
            self._handle_api("org_info")
            return

        # Welcome/wizard page (no auth required)
        if path == "/welcome":
            self._serve_page("welcome.html", {})
            return

        # Tenant auth pages (no legacy auth required)
        if path == "/login":
            self._serve_page("login.html", {"msg": ""})
            return
        if path == "/org/setup":
            self._serve_page("org-setup.html", {})
            return
        if path == "/project/select":
            self._serve_page("project-select.html", {})
            return

        # Legacy auth check for all other routes
        if not self._check_auth():
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
                    self.send_header("Location", "/welcome")
                    self.end_headers()
            except Exception:
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
        elif path.startswith("/exec"):
            self._handle_exec(parsed.query)
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API v1 routes — dispatch to modular handlers
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            return

        # Legacy login endpoint — always accessible
        if path == "/_auth/login":
            self._handle_login()
            return

        # Tenant auth endpoints — always accessible
        if path == "/api/auth/signin":
            self._handle_api("signin")
            return
        if path == "/api/org/create":
            self._handle_api("org_create")
            return
        if path == "/api/project/create":
            self._handle_api("project_create")
            return
        if path == "/api/auth/logout":
            self._handle_api("logout")
            return

        # Legacy auth check
        if not self._check_auth():
            return

        self._json_response({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/v1/"):
            api_v1_dispatch(self, path)
            return
        self._json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.end_headers()

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
        if path.startswith("/api/") or path.startswith("/exec"):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unauthorized", "message": "X-API-Key header required"}).encode())
            return False
        else:
            # Serve login page for browser requests
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(legacy_login_page("Invalid API key").encode("utf-8"))

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def _serve_page(self, name: str, context: dict):
        """Serve an HTML page from the pages/ directory, with simple template substitution."""
        filepath = PAGES_DIR / name
        if not filepath.exists():
            self._json_response({"error": "page not found"}, 404)
            return

        content = filepath.read_text(encoding="utf-8")
        # Simple {key} substitution for context variables
        for key, value in context.items():
            content = content.replace("{" + key + "}", str(value))

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _serve_file(self, filepath: Path, mime: str):
        if filepath.exists():
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json_response({"error": "file not found"}, 404)

    def _json_response(self, data, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())

    def _handle_exec(self, query: str):
        params = urllib.parse.parse_qs(query)
        cmd = params.get("cmd", [""])[0]

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=60,
                cwd=OSH_HOME,
            )
            output = result.stdout or result.stderr
            self._json_response({
                "status": "ok",
                "exit_code": result.returncode,
                "output": output[:2000],
            })
        except subprocess.TimeoutExpired:
            self._json_response({"status": "error", "output": "Command timed out"}, 500)
        except Exception as e:
            self._json_response({"status": "error", "output": str(e)}, 500)

    def _get_status(self) -> dict:
        return {
            "status": "running",
            "osh_home": OSH_HOME,
            "version": "0.1.0",
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }

    def _get_health(self) -> dict:
        return {
            "status": "ok",
            "version": "0.1.0",
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

    print(f"🌐 OSH Dashboard: http://localhost:{PORT}")
    print(f"   OSH_HOME: {OSH_HOME}")
    print(f"   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
