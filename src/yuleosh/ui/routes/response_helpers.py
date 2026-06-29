# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Dashboard — Response helper functions.

Canonical implementations for JSON, page, and file responses that were
extracted from OSHHandler to keep server.py ≤500 lines. These functions
reference yuleosh.ui.server module variables lazily so that unit test
patches on yuleosh.ui.server.* work correctly.
"""

import gzip
import json
from pathlib import Path

from yuleosh.ui.routes.helpers import (
    _compute_etag,
    _format_http_datetime,
    _parse_http_datetime,
    _send_security_headers,
)


def serve_page(handler, name: str, context: dict) -> None:
    """Serve an HTML page from the pages/ directory."""
    from yuleosh.ui import server as _s
    pages_dir = _s.PAGES_DIR

    filepath = pages_dir / name
    if not filepath.exists():
        fallback = pages_dir / "404.html"
        if fallback.exists():
            _serve_html(handler, fallback.read_text(encoding="utf-8"), 404)
            return
        json_response(handler, {"error": "page not found"}, 404)
        return

    content = filepath.read_text(encoding="utf-8")
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
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("ETag", etag)
    handler.send_header("Last-Modified", _format_http_datetime(last_mod))
    _send_security_headers(handler)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def serve_file(handler, filepath: Path, mime: str) -> None:
    """Serve a static file with caching and security headers."""
    from yuleosh.ui import server as _s
    pages_dir = _s.PAGES_DIR

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
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            return
        handler.send_response(200)
        handler.send_header("Content-Type", mime)
        handler.send_header("ETag", etag)
        handler.send_header("Last-Modified", _format_http_datetime(last_mod))
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(data)
    else:
        fallback = pages_dir / "404.html"
        if fallback.exists():
            _serve_html(handler, fallback.read_text(encoding="utf-8"), 404)
            return
        json_response(handler, {"error": "file not found"}, 404)


def json_response(handler, data, status: int = 200) -> None:
    """Send a JSON response with optional gzip compression."""
    from yuleosh.ui import server as _s
    pages_dir = _s.PAGES_DIR

    accept = handler.headers.get("Accept", "")
    if status == 500 and "text/html" in accept:
        fallback = pages_dir / "500.html"
        if fallback.exists():
            _serve_html(handler, fallback.read_text(encoding="utf-8"), 500)
            return

    body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    accept_encoding = handler.headers.get("Accept-Encoding", "")
    if "gzip" in accept_encoding and len(body) > 512:
        body_gz = gzip.compress(body)
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Encoding", "gzip")
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Content-Length", str(len(body_gz)))
        handler.end_headers()
        handler.wfile.write(body_gz)
    else:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        _send_security_headers(handler)
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(body)


def _serve_html(handler, content: str, status: int = 200) -> None:
    """Send an HTML string as response."""
    body = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    _send_security_headers(handler)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)
