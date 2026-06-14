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
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))


def json_ok(data: Any = None) -> tuple[dict, int]:
    """Return a success JSON response."""
    return {"ok": True, "data": data}, 200


def json_error(msg: str, status: int = 400) -> tuple[dict, int]:
    """Return an error JSON response."""
    return {"ok": False, "error": msg}, status


def read_body(handler) -> dict:
    """Read and parse JSON body from the HTTP request."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length).decode("utf-8")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Try query-string format
        parsed = parse_qs(raw)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}


def get_store():
    """Get the shared Store instance."""
    from yuleosh.store import Store
    return Store()
