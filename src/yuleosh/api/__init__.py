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


def json_ok(data: Any = None) -> tuple[dict, int]:
    """Return a success JSON response."""
    return {"ok": True, "data": data}, 200


def json_error(msg: str, status: int = 400) -> tuple[dict, int]:
    """Return an error JSON response."""
    return {"ok": False, "error": msg}, status


def read_body(handler) -> dict:
    """Read and parse the request body based on Content-Type header.

    - application/json → JSON decode (fails with 400 on invalid input)
    - application/x-www-form-urlencoded → query-string decode
    - other / no content-type → try JSON, fall back to query-string

    Returns a dict on success, raises BadRequest on parse failure.
    """
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length).decode("utf-8")

    content_type = (handler.headers.get("Content-Type", "") or "").lower().split(";")[0].strip()

    if content_type == "application/json":
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BadRequest(f"Invalid JSON body: {e}")
    elif content_type == "application/x-www-form-urlencoded":
        parsed = parse_qs(raw)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    else:
        # Unknown or no Content-Type: try JSON first, then query-string
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = parse_qs(raw)
            if parsed:
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            raise BadRequest("Unable to parse request body. Use application/json or application/x-www-form-urlencoded.")


def get_store():
    """Get the shared Store instance."""
    from yuleosh.store import Store
    return Store()
