# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH REST API — Auth endpoints (register, login, me, logout).

Mounted at /api/v1/auth/ in the REST API router.

A1 (v3.8.0 认证合一): this module is a thin CONTRACT ADAPTER over the
unified auth implementation in ``ui/auth_extended.py``.

- JWT secret / bcrypt / token signing+decoding / rate limiting all have
  ONE implementation in auth_extended (SHALL-A1.1/1.3/1.5/1.6).  This
  module only imports them (adapter-layer references — T-A1-15).
- ``handle_auth`` keeps the v1 response contract
  ({token, user:{id,email,role,org:{id,name,slug}}}) while the heavy
  lifting (credential verify, session creation, rate-limit budget) is
  delegated to auth_extended (SHALL-A1.4).  The shared rate-limit table
  means /api/v1/auth/login and /api/auth/signin share one budget
  (SHALL-A1.6, T-A1-08).
"""

import logging
import re
from typing import Optional

from yuleosh.store import Store
from yuleosh.ui.auth_extended import (  # A1: unified implementations
    EMAIL_RE,
    JWT_ALGORITHM as _JWT_ALGORITHM,
    JWT_SECRET as _JWT_SECRET,
    _SIGNIN_RATE_LIMIT,
    _MAX_SIGNIN_ATTEMPTS,
    _RATE_WINDOW_SECONDS,
    _check_and_record_failed_attempt,
    _check_rate_limit,
    _decode_token,
    _generate_token,
    _hash_password,
    _slugify,
    _verify_password,
    get_session_user,
    handle_logout as _auth_extended_logout,
    register as _auth_extended_register,
)
from . import json_ok, json_error

logger = logging.getLogger("yuleosh.api.auth")

# v1 register/login session TTL (24h) — kept for the v1 contract; the
# unified auth_extended flow uses its own SESSION_TTL_HOURS for the JWT
# expiry claim.  Both share the same store.session row expiry semantics.
TOKEN_TTL_HOURS = 24

# In-memory rate limit tracking — shared table with the ui signin flow
# (SHALL-A1.6): email -> (failed_attempts, window_start).  Defined in
# auth_extended; re-exported here for adapter/test compatibility.


# ---------------------------------------------------------------------------
# Internal helpers (adapter layer)
# ---------------------------------------------------------------------------

# NOTE (A1): _slugify / _hash_password / _verify_password / _generate_token /
# _decode_token / _check_rate_limit / _SIGNIN_RATE_LIMIT / _MAX_SIGNIN_ATTEMPTS /
# _RATE_WINDOW_SECONDS / EMAIL_RE are IMPORTED from ui/auth_extended above —
# they are the unified single implementations (T-A1-15: adapter-layer
# references only, zero `def` of duplicated crypto in this module).

def _extract_token(headers: dict) -> Optional[str]:
    """Extract Bearer token from request headers.

    Accepts both dict-like and object attribute access for headers.
    """
    # Headers may be accessed as dict or via .get()
    if callable(getattr(headers, "get", None)):
        auth = headers.get("Authorization", "")
    elif isinstance(headers, dict):
        auth = headers.get("Authorization", "")
    else:
        auth = str(headers) if headers else ""

    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _user_response(user: dict, org: dict) -> dict:
    """Build the v1 user info response dict, stripping sensitive fields."""
    return {
        "id": user["id"],
        "email": user.get("email", ""),
        "role": user.get("role", "member"),
        "org": {
            "id": org["id"],
            "name": org.get("name", ""),
            "slug": org.get("slug", ""),
        },
    }


def _login_user(email: str, password: str, store: Store) -> Optional[dict]:
    """Attempt to authenticate a user across all orgs.

    Uses the unified password verifier (A1). Returns the user dict on
    success, None on failure.
    """
    orgs = store.list_organizations()
    for org in orgs:
        user = store.get_user(org["id"], email)
        if user:
            pw_hash = user.get("password_hash")
            if pw_hash:
                if not _verify_password(password, pw_hash):
                    return None
                return user
            else:
                # User exists but has no password set (e.g. invite-only) —
                # treat as auth failure unless we allow pass-through.
                return None
    return None


# ---------------------------------------------------------------------------
# Auth handler
# ---------------------------------------------------------------------------

def handle_auth(method: str, path_tail: str, body: dict, query: dict,
                **kwargs) -> tuple:
    """Auth REST API handler — register, login, me, logout.

    Routes:
        POST /api/v1/auth/register — Register a new user
        POST /api/v1/auth/login    — Login with email + password
        GET  /api/v1/auth/me       — Get current user from JWT
        POST /api/v1/auth/logout   — Invalidate current session/JWT
    """
    if method == "POST" and path_tail == "register":
        return _handle_register(body)
    elif method == "POST" and path_tail == "login":
        return _handle_login(body)
    elif method == "GET" and path_tail == "me":
        return _handle_me(kwargs.get("handler"))
    elif method == "POST" and path_tail == "logout":
        return _handle_logout(kwargs.get("handler"))
    else:
        return json_error(f"Unknown auth endpoint: {method} /{path_tail}", 404)


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register
# ---------------------------------------------------------------------------

def _handle_register(body: dict) -> tuple:
    """Register a new user with email, password, and organization name.

    Body: {email, password, organization_name}
    Returns: {token, user: {id, email, role, org}}
    """
    # A1: delegate to the unified register (org+user+token) and convert
    # the response to the v1 contract.
    resp, status = _auth_extended_register(body)
    if status != 200:
        return json_error(resp.get("error", "Registration failed"), status)

    store = Store()
    user = store.get_user_by_id(resp["user_id"])
    org = store.get_organization_by_id(resp["org_id"])
    return json_ok({
        "token": resp["token"],
        "user": _user_response(user, org),
    })


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

def _handle_login(body: dict) -> tuple:
    """Login with email and password.

    Body: {email, password}
    Returns: {token, user: {id, email, role, org}}
    """
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not email or not EMAIL_RE.match(email):
        return json_error("Valid email is required", 400)
    if not password:
        return json_error("Password is required", 400)

    # Shared rate-limit budget with /api/auth/signin (SHALL-A1.6).
    if _check_rate_limit(email):
        retry_after = _RATE_WINDOW_SECONDS // 60
        return json_error(
            f"Too many attempts. Try again in {retry_after} minutes.", 429
        )

    store = Store()

    # Search for user across all orgs (same semantics as handle_signin).
    orgs = store.list_organizations()
    authenticated_user = None
    authenticated_org = None

    for org in orgs:
        user = store.get_user(org["id"], email)
        if user:
            pw_hash = user.get("password_hash")
            if pw_hash and _verify_password(password, pw_hash):
                authenticated_user = user
                authenticated_org = org
                break

    if not authenticated_user or not authenticated_org:
        _check_and_record_failed_attempt(email)
        return json_error("Invalid email or password", 401)

    # Generate JWT and create session
    token = _generate_token(
        authenticated_user["id"],
        authenticated_org["id"],
        authenticated_user["email"],
    )
    store.create_session(authenticated_user["id"], token, TOKEN_TTL_HOURS)

    return json_ok({
        "token": token,
        "user": _user_response(authenticated_user, authenticated_org),
    })


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------

def _handle_me(handler=None) -> tuple:
    """Get current user info from JWT in Authorization header.

    Header: Authorization: Bearer <token>
    Returns: {user: {id, email, role, org}}
    """
    if handler is None:
        return json_error("Unauthorized", 401)

    token = _extract_token(handler.headers)
    if not token:
        return json_error("Authorization header with Bearer token required", 401)

    # A1: unified session resolve (same verify as the ui side).
    info = get_session_user(token)
    if not info:
        return json_error("Invalid or expired token", 401)

    return json_ok({
        "user": {
            "id": info["user_id"],
            "email": info["email"],
            "role": info["role"],
            "org": {
                "id": info["org_id"],
                "name": info["org_name"],
                "slug": info["org_slug"],
            },
        },
    })


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------

def _handle_logout(handler=None) -> tuple:
    """Logout — invalidate the session token.

    Header: Authorization: Bearer <token>
    Returns: {message: "Logged out successfully"}
    """
    if handler:
        token = _extract_token(handler.headers)
        if token:
            try:
                _auth_extended_logout(token)
            except Exception as e:
                logger.warning("Failed to delete session on logout: %s", e)

    return json_ok({"message": "Logged out successfully"})
