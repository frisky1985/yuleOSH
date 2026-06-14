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

logger = logging.getLogger("yuleosh.api.middleware")


# JWT secret — must match the one used in auth.py
import os
import secrets
_JWT_SECRET = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
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
        if not http_handler:
            return json_error("Missing HTTP handler context", 500)

        token = _extract_token(http_handler.headers)
        if not token:
            return json_error("Authorization header with Bearer token required", 401)

        payload = _decode_token(token)
        if not payload:
            return json_error("Invalid or expired token", 401)

        # Validate user exists in store
        from yuleosh.store import Store
        store = Store()
        user = store.get_user_by_id(payload.get("user_id"))
        if not user:
            return json_error("User not found", 401)

        # Validate session exists and is not expired
        session = store.get_session(token)
        if not session:
            return json_error("Session expired or revoked", 401)

        # Inject current user into kwargs
        kwargs["current_user"] = {
            "user_id": payload.get("user_id"),
            "org_id": payload.get("org_id"),
            "email": payload.get("email", ""),
            "role": user.get("role", "member"),
        }

        return handler(method=method, path_tail=path_tail, body=body,
                       query=query, **kwargs)

    return wrapper
