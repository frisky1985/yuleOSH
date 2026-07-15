"""
yuleOSH Dashboard Server — Route helper utilities.

Provides caching, compression, security-header, and datetime helpers
used by the OSH HTTP server.
"""

import datetime as dt
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Optional


def _compute_etag(content: bytes) -> str:
    """Return a weak ETag for the given content."""
    return f'W/"{hashlib.md5(content).hexdigest()}"'


def _format_http_datetime(timestamp: float) -> str:
    """Format a Unix timestamp as an HTTP-date string (RFC 7231)."""
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )


def _parse_http_datetime(date_str: str) -> float:
    """Parse an HTTP-date string back to a Unix timestamp."""
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
        _add_cors_header(handler)
        handler.send_header("Content-Length", str(len(body_gz)))
        handler.end_headers()
        handler.wfile.write(body_gz)
    else:
        handler._json_response(data, status)


def _add_cors_header(handler):
    """Set Access-Control-Allow-Origin based on request Origin and env.

    Uses yuleosh.api.cors to determine the correct CORS origin.
    """
    from yuleosh.api.cors import get_cors_origin
    request_origin = handler.headers.get("Origin")
    cors_origin = get_cors_origin(request_origin)
    handler.send_header("Access-Control-Allow-Origin", cors_origin)
    if cors_origin != "*":
        handler.send_header("Vary", "Origin")


def _send_security_headers(handler):
    """Send security headers on the given handler."""
    handler.send_header("Content-Security-Policy", "default-src 'self'")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Strict-Transport-Security", "max-age=31536000")
    handler.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
