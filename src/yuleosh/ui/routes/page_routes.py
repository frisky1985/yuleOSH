"""
yuleOSH Dashboard — Page serving route handlers.

Extracts page-serving logic from the monolithic OSHHandler into
standalone helper functions.
"""

import json
import gzip
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler

from yuleosh.ui.routes.helpers import (
    _compute_etag,
    _format_http_datetime,
    _parse_http_datetime,
    _add_cors_header,
    _send_security_headers,
)


def serve_page(handler: BaseHTTPRequestHandler, name: str, context: dict):
    """Serve an HTML page from the pages/ directory, with simple template substitution."""
    PAGES_DIR = Path(handler.__class__.__module__.replace(".", "/")).parent / "pages"
    # Resolve PAGES_DIR correctly from ui/server.py context
    import sys
    from pathlib import Path as _Path
    ui_dir = _Path(__file__).resolve().parent.parent
    pages_dir = ui_dir / "pages"

    filepath = pages_dir / name
    if not filepath.exists():
        # Fallback: serve static 404 page
        fallback = pages_dir / "404.html"
        if fallback.exists():
            content = fallback.read_text(encoding="utf-8")
            _send_html_response(handler, content, 404)
            return
        _send_json_error(handler, "page not found", 404)
        return

    content = filepath.read_text(encoding="utf-8")
    # Simple {key} substitution for context variables
    for key, value in context.items():
        content = content.replace("{" + key + "}", str(value))

    body = content.encode("utf-8")
    etag = _compute_etag(body)
    last_mod = filepath.stat().st_mtime
    inm = handler.headers.get("If-None-Match")
    ims = handler.headers.get("If-Modified-Since")
    if inm == etag or (ims and abs(last_mod - _parse_http_datetime(ims)) < 2):
        handler.send_response(304)
        handler.send_header("ETag", etag)
        handler.send_header("Last-Modified", _format_http_datetime(last_mod))
        _send_security_headers(handler)
        _add_cors_header(handler)
        handler.end_headers()
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("ETag", etag)
    handler.send_header("Last-Modified", _format_http_datetime(last_mod))
    _send_security_headers(handler)
    _add_cors_header(handler)
    handler.end_headers()
    handler.wfile.write(body)


def serve_file(handler: BaseHTTPRequestHandler, filepath: Path, mime: str):
    """Serve a static file with caching and security headers."""
    from yuleosh.ui.routes.helpers import _compute_etag, _format_http_datetime, _parse_http_datetime, _send_security_headers

    if filepath.exists():
        data = filepath.read_bytes()
        etag = _compute_etag(data)
        last_mod = filepath.stat().st_mtime
        inm = handler.headers.get("If-None-Match")
        ims = handler.headers.get("If-Modified-Since")
        if inm == etag or (ims and abs(last_mod - _parse_http_datetime(ims)) < 2):
            handler.send_response(304)
            handler.send_header("ETag", etag)
            handler.send_header("Last-Modified", _format_http_datetime(last_mod))
            _send_security_headers(handler)
            _add_cors_header(handler)
            handler.end_headers()
            return
        handler.send_response(200)
        handler.send_header("Content-Type", mime)
        handler.send_header("ETag", etag)
        handler.send_header("Last-Modified", _format_http_datetime(last_mod))
        _send_security_headers(handler)
        _add_cors_header(handler)
        handler.end_headers()
        handler.wfile.write(data)
    else:
        # Serve custom 404 page for missing static files
        from pathlib import Path as _P
        pages_dir = _P(__file__).resolve().parent.parent / "pages"
        fallback = pages_dir / "404.html"
        if fallback.exists():
            content = fallback.read_text(encoding="utf-8")
            _send_html_response(handler, content, 404)
            return
        _send_json_error(handler, "file not found", 404)


# ── Internal helpers ────────────────────────────────────────────────


def _send_html_response(handler: BaseHTTPRequestHandler, content: str, status: int = 200):
    """Send an HTML response."""
    body = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    _send_security_headers(handler)
    _add_cors_header(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _send_json_error(handler: BaseHTTPRequestHandler, message: str, status: int = 400):
    """Send an error JSON response."""
    body = json.dumps({"error": message}).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    _send_security_headers(handler)
    _add_cors_header(handler)
    handler.end_headers()
    handler.wfile.write(body)
