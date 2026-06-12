# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""API input validation helpers for yuleOSH.

Provides shared validation functions used across API handlers.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


OSH_HOME = os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent)


def validate_spec_path(spec_path: Optional[str]) -> tuple[bool, Optional[str]]:
    """Validate that a spec_path input is safe and refers to an existing file.

    Returns (is_valid, error_message).
    """
    if not spec_path or not spec_path.strip():
        return False, "spec_path is required"

    spec_path = spec_path.strip()

    # No path traversal
    if ".." in spec_path or spec_path.startswith("/"):
        return False, "spec_path must be a relative path without traversal"

    # Must have a valid extension
    allowed_extensions = {".md", ".yaml", ".yml", ".json"}
    ext = os.path.splitext(spec_path)[1].lower()
    if ext not in allowed_extensions:
        return False, f"spec_path must have one of these extensions: {', '.join(sorted(allowed_extensions))}"

    # Resolve relative to OSH_HOME
    full_path = Path(OSH_HOME) / spec_path
    if not full_path.exists():
        return False, f"spec_path file not found: {spec_path}"

    if not full_path.is_file():
        return False, "spec_path must point to a file"

    return True, None


def validate_pagination(query: dict) -> dict:
    """Extract and validate pagination parameters from a query dict.

    Returns a dict with 'limit' and 'offset' keys, defaulting to 50 and 0.
    Caps limit at 200.
    """
    try:
        limit = int(query.get("limit", [50])[0])
    except (ValueError, IndexError, TypeError):
        limit = 50

    try:
        offset = int(query.get("offset", [0])[0])
    except (ValueError, IndexError, TypeError):
        offset = 0

    if limit < 1:
        limit = 50
    if offset < 0:
        offset = 0

    limit = min(limit, 200)

    return {"limit": limit, "offset": offset}


def validate_json_body(body: Any) -> tuple[bool, Optional[str]]:
    """Validate that the request body is a non-empty dict.

    Returns (is_valid, error_message).
    """
    if not isinstance(body, dict):
        return False, "Request body must be a JSON object"

    return True, None
