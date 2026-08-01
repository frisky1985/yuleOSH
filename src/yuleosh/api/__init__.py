# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH REST API — modular route handlers.

All endpoints return JSON:
  {"ok": true, "data": {...}}
or on error:
  {"ok": false, "error": "message"}
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

# NOTE (CQ-P2-02): sys.path.insert for dev. In production, use `pip install -e .` and remove.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))


class BadRequest(Exception):
    """Raised when a request body cannot be parsed."""


# Unified request-body cap (P1-5 / W-08): protects against memory-exhaustion
# via a huge declared Content-Length (memory DoS).
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


def json_ok(data: Any = None) -> tuple[dict, int]:
    """Return a success JSON response."""
    return {"ok": True, "data": data}, 200


def json_error(msg: str | dict, status: int = 400) -> tuple[dict, int]:
    """Return an error JSON response (W-07 contract fix).

    Accepts either a plain message string or a structured error dict
    ``{"error": <str>, ...extra fields}``.  The dict form is normalized so
    the ``error`` field is ALWAYS a string (API contract), with extra fields
    moved to a ``details`` object.  Example::

        json_error({"error": "file_too_large", "max_size_mb": 50}, 413)
        # -> {"ok": False, "error": "file_too_large", "details": {"max_size_mb": 50}}
    """
    if isinstance(msg, dict):
        err = msg.get("error", "error")
        details = {k: v for k, v in msg.items() if k != "error"}
        payload = {"ok": False, "error": str(err)}
        if details:
            payload["details"] = details
        return payload, status
    return {"ok": False, "error": msg}, status


def read_body(handler) -> dict:
    """Read and parse the request body based on Content-Type header.

    - application/json → JSON decode (fails with 400 on invalid input)
    - application/x-www-form-urlencoded → query-string decode
    - other / no content-type → try JSON, fall back to query-string

    Security (P1-5 / W-08):
    - Content-Length is clamped to MAX_BODY_BYTES (10 MB) — oversized or
      malformed (non-numeric/negative) headers raise BadRequest (400)
      instead of attempting an unbounded rfile.read() or a 500.

    Returns a dict on success, raises BadRequest on parse failure.
    """
    raw_header = handler.headers.get("Content-Length", "0") or "0"
    try:
        content_length = int(raw_header)
    except (ValueError, TypeError):
        raise BadRequest("Invalid Content-Length header")
    if content_length < 0:
        raise BadRequest("Invalid Content-Length header")
    content_length = min(content_length, MAX_BODY_BYTES)
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length)
    # Stash raw bytes on the handler so signature-verifying handlers
    # (e.g. GitHub webhooks) can verify HMACs against the exact payload.
    try:
        handler._raw_body = raw
    except Exception:
        pass
    raw_text = raw.decode("utf-8", errors="replace")

    content_type = (handler.headers.get("Content-Type", "") or "").lower().split(";")[0].strip()

    if content_type == "application/json":
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BadRequest(f"Invalid JSON body: {e}")
    elif content_type == "application/x-www-form-urlencoded":
        parsed = parse_qs(raw_text)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    else:
        # Unknown or no Content-Type: try JSON first, then query-string
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = parse_qs(raw_text)
            if parsed:
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            raise BadRequest("Unable to parse request body. Use application/json or application/x-www-form-urlencoded.")


def get_store():
    """Get the shared Store instance."""
    from yuleosh.store import Store
    return Store()
