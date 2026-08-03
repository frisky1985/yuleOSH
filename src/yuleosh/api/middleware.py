# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH REST API — Middleware: JWT auth requirement for handler injection.

Provides `require_auth` decorator to protect API endpoints behind JWT bearer
token validation, injecting current user info into the handler's kwargs.
"""

import functools
import logging
from typing import Optional

import jwt

from . import json_error
from yuleosh.ui.auth_extended import (
    JWT_SECRET as _JWT_SECRET,          # A1: unified source (SHALL-A1.1)
    JWT_ALGORITHM as _JWT_ALGORITHM,    # A1: unified source
    verify_token,                        # A1: unified verify (SHALL-A1.2)
)

logger = logging.getLogger("yuleosh.api.middleware")


# JWT secret — single source of truth (v3.8.0 A1): the value comes from
# ui/auth_extended.py.JWT_SECRET, never re-read from the environment here.
# ``_decode_token`` below is a THIN DELEGATION to the unified decoder —
# middleware must not implement JWT verification itself (SHALL-A1.2).
_JWT_ALGORITHM = "HS256"


def _decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None.

    A1 (v3.8.0): thin delegation to the unified decoder in
    ``ui/auth_extended.py`` — kept as a named wrapper so existing callers
    (and tests) keep a stable import surface, but the implementation is
    single-sourced.
    """
    from yuleosh.ui.auth_extended import _decode_token as _unified_decode
    return _unified_decode(token)


def _extract_token(headers) -> Optional[str]:
    """Extract Bearer token from request headers."""
    if callable(getattr(headers, "get", None)):
        auth = headers.get("Authorization", "")
    elif isinstance(headers, dict):
        auth = headers.get("Authorization", "")
    else:
        return None

    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(handler):
    """Decorator: enforces JWT auth on a route handler.

    Usage:
        @require_auth
        def handle_something(method, path_tail, body, query, **kwargs):
            # kwargs will include:
            #   current_user: dict with user_id, org_id, email, role
            pass

    On auth failure, the decorator short-circuits with a 401 JSON error.
    """
    @functools.wraps(handler)
    def wrapper(method: str, path_tail: str, body: dict, query: dict,
                **kwargs):
        # Extract headers from the handler object
        http_handler = kwargs.get("handler")
        if http_handler is None:
            # Fail closed (P0): never fabricate an authenticated user when no
            # HTTP handler context is available.  The only sanctioned bypass
            # is an explicit current_user kwarg, which is unreachable from
            # HTTP (router.dispatch only ever passes handler=).
            injected_user = kwargs.get("current_user")
            if injected_user is not None:
                return handler(method=method, path_tail=path_tail, body=body,
                               query=query, **kwargs)
            return json_error(
                "Authorization header with Bearer token required", 401)

        token = _extract_token(getattr(http_handler, "headers", {}))
        if not token:
            return json_error("Authorization header with Bearer token required", 401)

        # ── A1 (v3.8.0): unified verify — same function as the ui side ──
        #   (ui/auth_extended.verify_token).  Accepts BOTH payload formats
        #   (sub/org from the frontend chain, user_id/org_id from the v1
        #   API) and performs decode + session check + user check in ONE
        #   place.  The middleware no longer re-implements JWT verification
        #   (SHALL-A1.2); verdicts match v3.7.0 exactly.
        user = verify_token(token)
        if not user:
            return json_error("Invalid or expired token", 401)

        # Inject current user into kwargs
        kwargs["current_user"] = {
            "user_id": user["user_id"],
            "org_id": user["org_id"],
            "email": user.get("email", ""),
            "role": user.get("role", "member"),
        }

        return handler(method=method, path_tail=path_tail, body=body,
                       query=query, **kwargs)

    return wrapper
