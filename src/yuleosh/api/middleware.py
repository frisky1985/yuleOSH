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
from yuleosh.ui.auth_extended import JWT_SECRET as _JWT_SECRET  # A1: unified source (SHALL-A1.1)

logger = logging.getLogger("yuleosh.api.middleware")


# JWT secret — single source of truth (v3.8.0 A1): the value comes from
# ui/auth_extended.py.JWT_SECRET, never re-read from the environment here.
_JWT_ALGORITHM = "HS256"


def _decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired in middleware")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT invalid in middleware: %s", e)
        return None


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

        payload = _decode_token(token)
        if not payload:
            return json_error("Invalid or expired token", 401)

        # ── Token contract (P0-A): accept BOTH payload formats ──────────
        #   format A (router/middleware native): {"user_id": ..., "org_id": ...}
        #   format B (frontend ui/auth_extended): {"sub": "<user_id>", "org": ...}
        # The frontend login chain (signin → org/create) signs `sub`/`org`;
        # the middleware must not 401 those tokens (dashboard/KB v1 APIs).
        user_id = payload.get("user_id")
        if user_id is None:
            user_id = payload.get("sub")
        org_id = payload.get("org_id")
        if org_id is None:
            org_id = payload.get("org")

        # auth_extended signs sub as str(user_id) — normalize to int for the store.
        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            pass
        try:
            org_id = int(org_id) if org_id is not None else None
        except (TypeError, ValueError):
            pass

        # Validate user exists in store
        from yuleosh.store import Store
        store = Store()
        user = store.get_user_by_id(user_id)
        if not user:
            return json_error("User not found", 401)

        # Validate session exists and is not expired
        session = store.get_session(token)
        if not session:
            return json_error("Session expired or revoked", 401)

        # Inject current user into kwargs
        kwargs["current_user"] = {
            "user_id": user_id,
            "org_id": org_id,
            "email": payload.get("email", ""),
            "role": user.get("role", "member"),
        }

        return handler(method=method, path_tail=path_tail, body=body,
                       query=query, **kwargs)

    return wrapper
