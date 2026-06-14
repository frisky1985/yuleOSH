# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH REST API — Auth endpoints (register, login, me, logout).

Mounted at /api/v1/auth/ in the REST API router.

Uses bcrypt for password hashing and PyJWT (HS256) for session tokens.
JWT secret from YULEOSH_JWT_SECRET env var (auto-generated fallback).
"""

import logging
import os
import re
import secrets
import time
from typing import Optional

import bcrypt
import jwt

from yuleosh.store import Store
from . import json_ok, json_error

logger = logging.getLogger("yuleosh.api.auth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
TOKEN_TTL_HOURS = 24

# JWT secret from env var, with a random fallback for dev
_JWT_SECRET = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
_JWT_ALGORITHM = "HS256"

# In-memory rate limit tracking: email -> (attempts, window_start)
_SIGNIN_RATE_LIMIT: dict[str, tuple[int, int]] = {}
_MAX_SIGNIN_ATTEMPTS = 10
_RATE_WINDOW_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    return re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt (12 salt rounds)."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _generate_token(user_id: int, org_id: int, email: str) -> str:
    """Generate a signed JWT token with user claims and expiration."""
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "email": email,
        "iat": now,
        "exp": now + TOKEN_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT invalid: %s", e)
        return None


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


def _check_rate_limit(email: str) -> bool:
    """Check signin rate limit. Returns True if blocked."""
    now = int(time.time())
    entry = _SIGNIN_RATE_LIMIT.get(email)
    if entry:
        attempts, window_start = entry
        if now - window_start > _RATE_WINDOW_SECONDS:
            _SIGNIN_RATE_LIMIT[email] = (1, now)
            return False
        if attempts >= _MAX_SIGNIN_ATTEMPTS:
            return True
        _SIGNIN_RATE_LIMIT[email] = (attempts + 1, window_start)
    else:
        _SIGNIN_RATE_LIMIT[email] = (1, now)
    return False


def _user_response(user: dict, org: dict) -> dict:
    """Build the user info response dict, stripping sensitive fields."""
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

    Returns the user dict on success, None on failure.
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
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    org_name = (body.get("organization_name") or "").strip()

    # ── Validation ──────────────────────────────────────────────────────
    if not email or not EMAIL_RE.match(email):
        return json_error("Valid email is required", 400)
    if not password or len(password) < 8:
        return json_error("Password must be at least 8 characters", 400)
    if not org_name:
        return json_error("organization_name is required", 400)

    store = Store()
    org_slug = _slugify(org_name)

    # Create org if it doesn't exist; otherwise check for email conflict
    org = store.get_organization(org_slug)
    if org:
        # Org exists — check if email already registered
        existing = store.get_user(org["id"], email)
        if existing:
            return json_error("Email already registered in this organization", 409)
    else:
        org = store.create_organization(org_name, org_slug)

    # Create user with admin role (first user in org)
    password_hash = _hash_password(password)
    user = store.create_user(org["id"], email, "admin", password_hash)

    # Generate JWT and create session
    token = _generate_token(user["id"], org["id"], email)
    store.create_session(user["id"], token, TOKEN_TTL_HOURS)

    return json_ok({
        "token": token,
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

    # Rate limit check
    if _check_rate_limit(email):
        retry_after = _RATE_WINDOW_SECONDS // 60
        return json_error(
            f"Too many attempts. Try again in {retry_after} minutes.", 429
        )

    store = Store()

    # Search for user across all orgs
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

    payload = _decode_token(token)
    if not payload:
        return json_error("Invalid or expired token", 401)

    store = Store()

    user_id = payload.get("user_id")
    org_id = payload.get("org_id")

    # Verify the session still exists in the DB (not logged out or expired)
    session = store.get_session(token)
    if not session:
        return json_error("Invalid or expired token", 401)

    user = store.get_user_by_id(user_id)
    if not user:
        return json_error("User not found", 401)

    org = store.get_organization_by_id(org_id or user.get("org_id", 0))
    if not org:
        return json_error("Organization not found", 401)

    return json_ok({
        "user": _user_response(user, org),
    })


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------

def _handle_logout(handler=None) -> tuple:
    """Logout — invalidate the session token.

    Header: Authorization: Bearer <token>
    Returns: {ok: true}
    """
    if handler:
        token = _extract_token(handler.headers)
        if token:
            try:
                store = Store()
                store.delete_session(token)
            except Exception as e:
                logger.warning("Failed to delete session on logout: %s", e)

    return json_ok({"message": "Logged out successfully"})
