#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Dashboard Server — OSHHandler HTTP server.

Serves the yuleOSH web dashboard with API routes, auth, static files,
and project management.  Routes are extracted to yuleosh/ui/routes/*.
"""

import json
import logging
import os
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from yuleosh.store import Store

# ── Configuration ──────────────────────────────────────────────────────────

AUTH_ENABLED = os.environ.get("YULEOSH_AUTH_DISABLED", "").lower() not in (
    "true", "1", "yes"
)
OSH_HOME = os.environ.get(
    "OSH_HOME",
    str(Path(os.environ.get("HOME", ".")) / ".openclaw" / "workspace" / "tasks" / "yuleOSH"),
)

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


# ── Audit log (in-memory ring) ─────────────────────────────────────────────

_audit_log_ring: list[dict] = []
AUDIT_RING_MAX = 5000


def _audit_log(method: str, path: str, status_code: int,
               ip: str, duration_ms: float) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "method": method,
        "path": path,
        "status": status_code,
        "ip": ip,
        "duration_ms": duration_ms,
    }
    _audit_log_ring.append(entry)
    if len(_audit_log_ring) > AUDIT_RING_MAX:
        _audit_log_ring.pop(0)


# ── API v1 dispatch ────────────────────────────────────────────────────────

def api_v1_dispatch(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Dispatch /api/v1/* requests.  Returns True if handled."""
    return False  # Not implemented in static-only mode


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

    def _json_response(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        self.send_header("Content-Length", str(len(data)))
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _check_auth(self) -> bool:
        """If AUTH_ENABLED, check session.  Returns True if OK."""
        if not AUTH_ENABLED:
            return True
        # Simplified: checks for X-API-Key header
        api_key = self.headers.get("X-API-Key", "")
        if api_key:
            return True
        return True  # Allow for now; proper auth uses auth_routes

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
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        result = handle_api_action(self, action, body)
        self._json_response(result)

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
            logging.error("GET %s: %s", self.path, e)
            self._serve_static("/")
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_POST(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_post, log_audit
        self._request_start_time = time.time()
        try:
            handle_post(self)
        except Exception as e:
            logging.error("POST %s: %s", self.path, e)
            self._json_response({"error": str(e)}, 500)
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_DELETE(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_delete, log_audit
        self._request_start_time = time.time()
        try:
            handle_delete(self)
        except Exception as e:
            logging.error("DELETE %s: %s", self.path, e)
            self._json_response({"error": str(e)}, 500)
        finally:
            self._response_status = getattr(self, "_response_status", 200)
            log_audit(self)

    def do_OPTIONS(self) -> None:
        from yuleosh.ui.routes.handler_helpers import handle_options
        handle_options(self)

    # ── Serve file/page (called by routes) ────────────────────────────────

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        """Serve a file by its absolute path."""
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
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
        logging.info("%s - %s", self.client_address[0], format % args)


# ── Server launcher ────────────────────────────────────────────────────────

def main(host: str = "127.0.0.1", port: int = 8080):
    """Start the yuleOSH Dashboard Server."""
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
