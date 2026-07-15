# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH CORS configuration — validate Origin against allowed origins.

Environment variables:
  YULEOSH_ENV                  = "development" | "production" (default: production)
  YULEOSH_CORS_ALLOWED_ORIGINS = comma-separated list of allowed origins

In development mode, Access-Control-Allow-Origin: * is used.
In production mode, the request Origin header is validated against the
allowed origins list (which always includes localhost:18789 for the
desktop client).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("yuleosh.api.cors")

# Always-permitted origins (desktop client etc.)
_ALWAYS_ALLOWED = frozenset({
    "http://localhost:18789",
    "http://127.0.0.1:18789",
})


def is_development() -> bool:
    """Return True if running in development mode."""
    return os.environ.get("YULEOSH_ENV", "").lower() == "development"


def get_allowed_origins() -> set:
    """Return the full set of allowed origins.

    Combines always-permitted origins with those from the configurable
    YULEOSH_CORS_ALLOWED_ORIGINS environment variable.
    """
    origins = set(_ALWAYS_ALLOWED)
    env_origins = os.environ.get("YULEOSH_CORS_ALLOWED_ORIGINS", "")
    if env_origins.strip():
        for origin in env_origins.split(","):
            origin = origin.strip()
            if origin:
                origins.add(origin)
    return origins


def get_cors_origin(request_origin: Optional[str] = None) -> str:
    """Return the value for Access-Control-Allow-Origin header.

    In development mode, returns '*' (allow all origins).
    In production mode, validates the request Origin against the allowed
    origins list. If the Origin is allowed, echoes it back. Otherwise
    returns 'null' (disallowed).
    """
    if is_development():
        return "*"

    if not request_origin:
        # No Origin header — return the first allowed origin as a safe default
        allowed = get_allowed_origins()
        if allowed:
            return next(iter(allowed))
        return "null"

    allowed = get_allowed_origins()
    if request_origin in allowed:
        return request_origin

    logger.warning("CORS: blocked origin %s (allowed: %s)", request_origin, allowed)
    return "null"


# Convenience: common origins used by the project
def origin_is_allowed(request_origin: Optional[str] = None) -> bool:
    """Check if the given Origin is allowed (production mode always True)."""
    if is_development():
        return True
    if not request_origin:
        return False
    return request_origin in get_allowed_origins()
