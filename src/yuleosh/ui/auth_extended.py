# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Multi-tenant Organization, Project & User Authentication for yuleOSH.

v0.8.0: JWT + bcrypt password auth + rate limiting + security headers.

Provides:
- Password-based signin/signup with bcrypt hashing
- Rate-limited login (10 attempts / 5 min per email)
- Organization creation and membership with invite codes
- Project creation and switching
- Role-based access control (admin vs member)
- Session management with signed JWT bearer tokens
"""

import json
import logging
import os
import re
import secrets
import threading
import time
from typing import Optional

import bcrypt
import jwt  # PyJWT

from yuleosh.store import Store


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SESSION_TTL_HOURS = 72

# ── JWT ──────────────────────────────────────────────────────────────────────
_YULEOSH_JWT_SECRET_ENV = os.environ.get("YULEOSH_JWT_SECRET")
if not _YULEOSH_JWT_SECRET_ENV:
    raise RuntimeError(
        "YULEOSH_JWT_SECRET environment variable is required for multi-tenant auth. "
        "Generate one with: openssl rand -base64 48"
    )
JWT_SECRET = _YULEOSH_JWT_SECRET_ENV
JWT_ALGORITHM = "HS256"

# ── Password strength validation ────────────────────────────────────────────

_MIN_PASSWORD_LENGTH = 8


def _validate_password_strength(password: str) -> list[str]:
    """Validate password strength. Returns list of error messages (empty = valid)."""
    errors: list[str] = []
    if len(password) < _MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one digit")
    return errors


# ── Rate limiting ────────────────────────────────────────────────────────────
# NOTE (S-P2-02): The in-memory rate limiter does NOT work across multiple
# processes or workers. For production deployments with >1 worker, replace
# with a shared store (Redis/Memcached) or database-backed rate limiter.
#
# P1-2 (W-04 / S-P1-06): lockout-DoS hardening.
#   - Per-email limit now counts FAILED attempts only (recorded at the point
#     of verification failure).  Correct-password logins never consume the
#     budget, and enumeration is still foiled because the same unified
#     message is returned for unknown-user / no-password / wrong-password.
#   - A per-IP attempt cap bounds how many distinct accounts a single
#     attacker can lock out (30 attempts / 5 min per IP).

class _ThreadSafeDict:
    """A dict wrapper that serializes all access with a lock.

    W-2 (COR-W2 / SEC-W2 / Fix 5): the signin rate-limit tables were plain
    dicts — the read-modify-write in ``_record_failed_attempt`` /
    ``_check_ip_rate_limit`` raced under concurrent signins (limit bypass)
    and ``_SIGNIN_IP_LIMIT`` grew without bound.  Same semantics as the
    ``_ThreadSafeDict`` in ``yuleosh/api/preview.py`` (mirrored here to keep
    the ui -> api dependency direction clean).

    NOTE: internal read-modify-write helpers use ``._dict`` directly under
    ``._lock`` — the public accessors re-acquire the same non-reentrant lock
    and would deadlock (same pattern as preview.py).
    """
    def __init__(self):
        self._dict: dict = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def clear(self):
        """Remove all entries (test isolation / state reset)."""
        with self._lock:
            self._dict.clear()

    def pop(self, key, default=None):
        with self._lock:
            return self._dict.pop(key, default)

    def __getitem__(self, key):
        with self._lock:
            return self._dict[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._dict[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._dict[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._dict

    def __len__(self):
        with self._lock:
            return len(self._dict)

    def items(self):
        with self._lock:
            return list(self._dict.items())

    def keys(self):
        with self._lock:
            return list(self._dict.keys())


_SIGNIN_RATE_LIMIT = _ThreadSafeDict()  # email -> (failed_attempts, window_start)
_SIGNIN_IP_LIMIT = _ThreadSafeDict()  # ip -> (attempts, window_start)
_MAX_SIGNIN_ATTEMPTS = 10
_RATE_WINDOW_SECONDS = 300  # 5 minutes
_MAX_SIGNIN_IP_ATTEMPTS = 30
_IP_WINDOW_SECONDS = 300  # 5 minutes
_IP_LIMIT_CLEANUP_THRESHOLD = 2000  # W-2: bounded IP-table growth (was unbounded DoS)


def _check_rate_limit(email: str) -> bool:
    """Check whether the email is currently blocked. Returns True if blocked.

    P1-2: pure check — does NOT increment.  Failed attempts are recorded by
    _record_failed_attempt() at the failure site so correct logins never
    lock a user out.

    Process-local only (S-P2-02): does not span workers.
    Stale entries are cleaned up opportunistically.

    W-2: the read is atomic under the container lock (a plain-dict check
    raced with concurrent records and could let a burst past the cap).
    """
    now = int(time.time())
    with _SIGNIN_RATE_LIMIT._lock:
        entry = _SIGNIN_RATE_LIMIT._dict.get(email)
        if entry:
            attempts, window_start = entry
            if now - window_start > _RATE_WINDOW_SECONDS:
                _SIGNIN_RATE_LIMIT._dict.pop(email, None)
                return False
            if attempts >= _MAX_SIGNIN_ATTEMPTS:
                return True
    return False


def _record_failed_attempt(email: str) -> None:
    """Record one FAILED signin attempt for the email (P1-2).

    W-2: the read-modify-write is atomic under the container lock.
    """
    now = int(time.time())
    with _SIGNIN_RATE_LIMIT._lock:
        entry = _SIGNIN_RATE_LIMIT._dict.get(email)
        if entry:
            attempts, window_start = entry
            if now - window_start > _RATE_WINDOW_SECONDS:
                _SIGNIN_RATE_LIMIT._dict[email] = (1, now)
            else:
                _SIGNIN_RATE_LIMIT._dict[email] = (attempts + 1, window_start)
        else:
            _SIGNIN_RATE_LIMIT._dict[email] = (1, now)
            # Opportunistic stale entry cleanup (every ~11th new entry)
            if len(_SIGNIN_RATE_LIMIT._dict) > 1000 and hash(email) % 11 == 0:
                _cleanup_stale_rate_entries()


def _check_and_record_failed_attempt(email: str) -> bool:
    """Atomically check the email budget AND record a failure (W-2).

    MAY-W2.6: the signin failure path uses this combined operation so the
    check+record read-modify-write is one critical section — N concurrent
    wrong-password submissions can never push the failed count past
    ``_MAX_SIGNIN_ATTEMPTS + ε`` (the limit check and the increment cannot
    interleave).  Returns True when the failure was recorded, False when
    the email is already blocked (the attempt is refused without counting).
    """
    now = int(time.time())
    with _SIGNIN_RATE_LIMIT._lock:
        entry = _SIGNIN_RATE_LIMIT._dict.get(email)
        if entry:
            attempts, window_start = entry
            if now - window_start > _RATE_WINDOW_SECONDS:
                _SIGNIN_RATE_LIMIT._dict[email] = (1, now)
                return True
            if attempts >= _MAX_SIGNIN_ATTEMPTS:
                return False
            _SIGNIN_RATE_LIMIT._dict[email] = (attempts + 1, window_start)
            return True
        _SIGNIN_RATE_LIMIT._dict[email] = (1, now)
        if len(_SIGNIN_RATE_LIMIT._dict) > 1000 and hash(email) % 11 == 0:
            _cleanup_stale_rate_entries()
        return True


def _check_ip_rate_limit(ip: str) -> bool:
    """Per-IP signin attempt cap (P1-2). Returns True if blocked.

    Bounds the number of distinct emails a single source can lock out.

    W-2: read-modify-write atomic under lock; the IP table now gets the
    same opportunistic cleanup as the email table (>2000 entries) so it can
    no longer grow without bound.
    """
    if not ip:
        return False
    now = int(time.time())
    with _SIGNIN_IP_LIMIT._lock:
        entry = _SIGNIN_IP_LIMIT._dict.get(ip)
        if entry:
            attempts, window_start = entry
            if now - window_start > _IP_WINDOW_SECONDS:
                _SIGNIN_IP_LIMIT._dict[ip] = (1, now)
                return False
            if attempts >= _MAX_SIGNIN_IP_ATTEMPTS:
                return True
            _SIGNIN_IP_LIMIT._dict[ip] = (attempts + 1, window_start)
        else:
            _SIGNIN_IP_LIMIT._dict[ip] = (1, now)
            # W-2: bounded growth — purge expired IP windows when the table
            # gets large (mirrors the email-table pattern).  Cleanup only
            # touches entries outside the window; live entries are untouched.
            if (len(_SIGNIN_IP_LIMIT._dict) > _IP_LIMIT_CLEANUP_THRESHOLD
                    and hash(ip) % 11 == 0):
                _cleanup_stale_ip_entries()
    return False


def _cleanup_stale_rate_entries():
    """Remove rate-limit entries older than the window.

    W-2: operates on ``._dict`` directly — callers hold the container lock
    (the public accessors would re-acquire the non-reentrant lock).
    """
    cutoff = int(time.time()) - _RATE_WINDOW_SECONDS
    stale = [k for k, (_, ws) in _SIGNIN_RATE_LIMIT._dict.items() if ws < cutoff]
    for k in stale:
        del _SIGNIN_RATE_LIMIT._dict[k]


def _cleanup_stale_ip_entries():
    """Remove IP-limit entries older than the IP window (W-2)."""
    cutoff = int(time.time()) - _IP_WINDOW_SECONDS
    stale = [k for k, (_, ws) in _SIGNIN_IP_LIMIT._dict.items() if ws < cutoff]
    for k in stale:
        del _SIGNIN_IP_LIMIT._dict[k]


# ── Password hashing ─────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Hash password with bcrypt (12 rounds). Returns hashed string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash. Constant-time comparison."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _generate_token(user_id: int = 0, org_id: int = 0, email: str = "",
                    purpose: Optional[str] = None) -> str:
    """Generate a signed JWT with embedded user/org claims and expiration."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "email": email,
        "iat": now,
        "exp": now + SESSION_TTL_HOURS * 3600,
    }
    if purpose:
        payload["purpose"] = purpose
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict | None:
    """Decode and validate JWT. Returns payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        logging.getLogger("auth_extended").warning("JWT decode failed: %s", e)
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))


def verify_token(token: str) -> dict | None:
    """Unified bearer-token verify (A1, SHALL-A1.2).

    Single source of truth for JWT bearer verification used by the
    v1 API middleware (``api.middleware.require_auth``) AND the ui side.
    Verdict semantics are identical to the v3.7.0 middleware path:

      - token signature / expiry invalid  -> None
      - session row missing (logged out / expired) -> None
      - user row missing                -> None

    Returns the current-user dict ``{user_id, org_id, email, role}`` on
    success (the same shape ``require_auth`` injected in v3.7.0), or None.
    """
    if not token:
        return None
    payload = _decode_token(token)
    if payload is None:
        return None

    # ── Token contract (P0-A): accept BOTH payload formats ──────────
    #   format A (router/middleware native): {"user_id": ..., "org_id": ...}
    #   format B (frontend ui/auth_extended): {"sub": "<user_id>", "org": ...}
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

    store = Store()
    user = store.get_user_by_id(user_id)
    if not user:
        return None
    session = store.get_session(token)
    if not session:
        return None
    return {
        "user_id": user_id,
        "org_id": org_id,
        "email": payload.get("email", ""),
        "role": user.get("role", "member"),
    }


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_session_user(token: str) -> dict | None:
    """Resolve a bearer token to a user dict with org info.

    P1-6 (S-P1-02): the JWT signature is verified first (defense in depth —
    only signed tokens can resolve a session), then the session row is
    looked up by its sha256 hash.  Random/forged strings never resolve.
    """
    if not token:
        return None
    if _decode_token(token) is None:
        return None
    store = Store()
    session = store.get_session(token)
    if not session:
        return None
    user = store.get_user_by_id(session["user_id"])
    if not user:
        return None
    org = store.get_organization_by_id(user.get("org_id", 0))
    if not org:
        return None
    return {
        "user_id": user["id"],
        "org_id": org["id"],
        "email": user.get("email", ""),
        "role": user.get("role", "member"),
        "org_name": org.get("name", ""),
        "org_slug": org.get("slug", ""),
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

def handle_signin(body: dict, ip: str = "") -> dict:
    """POST /api/auth/signin — Password-based signin/signup.

    Body: {email, password, [invite_code]}

    Flow:
    1. Rate limit check (per-email failed-attempt budget + per-IP cap)
    2. If user exists with password → verify password → login
    3. If invite_code → join org (signup without password first time)
    4. If email-only (backward compat) → first-time org creation flow

    P1-2 (W-04 / S-P1-06):
    - Users without a password_hash can NEVER log in with email alone
      (fail-closed, matches api/auth.py) — unified error message prevents
      account enumeration.
    - Failed attempts are counted per-email (max 10 / 5 min) AND per-IP
      (max 30 / 5 min) to bound account-lockout DoS.
    """
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    invite_code = (body.get("invite_code") or "").strip().lower()

    if not email or not EMAIL_RE.match(email):
        return {"error": "Valid email is required"}, 400

    # Rate limit (P1-2): per-email lockout check + per-IP attempt cap
    if _check_rate_limit(email):
        return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
    if _check_ip_rate_limit(ip):
        return {"error": f"Too many attempts. Try again in {_IP_WINDOW_SECONDS // 60} minutes."}, 429

    store = Store()

    # Check invite code
    target_org = None
    if invite_code:
        target_org = store.get_organization(invite_code)
        if not target_org:
            return {"error": f"Organization '{invite_code}' not found."}, 404

    if target_org:
        existing_user = store.get_user(target_org["id"], email)
        if existing_user:
            # Fail closed (P0): a user without a password_hash cannot be
            # authenticated by email alone — unified message prevents
            # account enumeration.
            if not existing_user.get("password_hash"):
                if not _check_and_record_failed_attempt(email):
                    return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                return {"error": "Invalid email or password"}, 401
            if not password:
                if not _check_and_record_failed_attempt(email):
                    return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                return {"error": "Invalid email or password"}, 401
            if not _verify_password(password, existing_user["password_hash"]):
                if not _check_and_record_failed_attempt(email):
                    return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                return {"error": "Invalid email or password"}, 401
            return _create_login_response(store, existing_user)
        else:
            # New member — require password for signup into existing org
            pwd_errors = _validate_password_strength(password) if password else ["Password is required"]
            if pwd_errors:
                return {"error": pwd_errors[0]}, 400
            password_hash = _hash_password(password)
            user = store.create_user(target_org["id"], email, "member", password_hash)
            return _create_login_response(store, user)
    else:
        # No invite code — check across all orgs
        orgs = store.list_organizations()
        for org in orgs:
            user = store.get_user(org["id"], email)
            if user:
                # Fail closed: password-less users cannot log in with email
                # alone (matches api/auth.py _login_user semantics).
                if not user.get("password_hash"):
                    if not _check_and_record_failed_attempt(email):
                        return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                    return {"error": "Invalid email or password"}, 401
                if not password:
                    if not _check_and_record_failed_attempt(email):
                        return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                    return {"error": "Invalid email or password"}, 401
                if not _verify_password(password, user["password_hash"]):
                    if not _check_and_record_failed_attempt(email):
                        return {"error": f"Too many attempts. Try again in {_RATE_WINDOW_SECONDS // 60} minutes."}, 429
                    return {"error": "Invalid email or password"}, 401
                return _create_login_response(store, user)

        # First-time user — need to create org
        token = _generate_token(email=email, purpose="org_setup")
        return {"token": token, "redirect": "/org/setup", "needs_org": True}, 200


def handle_org_create(body: dict, session_token: str) -> dict:
    """POST /api/org/create - Create organization and first project.

    Body: {org_name, org_slug, project_name, project_slug, email, [password]}
    """
    org_name = (body.get("org_name") or "").strip()
    org_slug = (body.get("org_slug") or "").strip().lower()
    project_name = (body.get("project_name") or "").strip()
    project_slug = (body.get("project_slug") or "").strip().lower()
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()

    if not org_name or not org_slug:
        return {"error": "Organization name and slug are required"}, 400
    if not SLUG_RE.match(org_slug):
        return {"error": "Slug must be lowercase alphanumeric with hyphens (e.g. 'my-org')"}, 400
    if not project_name or not project_slug:
        return {"error": "Project name and slug are required"}, 400
    if not SLUG_RE.match(project_slug):
        return {"error": "Project slug must be lowercase alphanumeric with hyphens"}, 400
    if not email:
        return {"error": "Email is required for org creation"}, 400

    # Security (P0): the org-setup token is bound to the email that requested
    # it — refuse to create an account for a different email.
    token_payload = _decode_token(session_token) if session_token else None
    token_email = (token_payload or {}).get("email", "")
    if not token_email or token_email.lower() != email:
        return {"error": "Invalid or expired session for this email"}, 401

    store = Store()

    # Check slug uniqueness
    if store.get_organization(org_slug):
        return {"error": f"Organization slug '{org_slug}' is already taken"}, 409

    # Create org
    org = store.create_organization(org_name, org_slug)

    # Create user as admin — with optional password
    if password:
        pwd_errors = _validate_password_strength(password)
        if pwd_errors:
            return {"error": pwd_errors[0]}, 400
    password_hash = _hash_password(password) if password else None
    user = store.create_user(org["id"], email, "admin", password_hash)

    # Create first project
    store.create_org_project(org["id"], project_name, project_slug)

    # Create session
    token = _generate_token(user["id"], org["id"], email)
    store.create_session(user["id"], token, SESSION_TTL_HOURS)

    return {
        "token": token,
        "redirect": "/project/select",
        "org_id": org["id"],
        "org_slug": org_slug,
    }, 200


def handle_session_info(session_token: str) -> dict:
    """GET /api/auth/session - Get current session info."""
    user_info = get_session_user(session_token)
    if not user_info:
        return {"error": "Invalid or expired session"}, 401

    store = Store()
    projects = store.list_org_projects(user_info["org_id"])

    return {
        "user_id": user_info["user_id"],
        "org_id": user_info["org_id"],
        "email": user_info["email"],
        "role": user_info["role"],
        "org_name": user_info["org_name"],
        "org_slug": user_info["org_slug"],
        "projects": [
            {"id": p["id"], "name": p["name"], "slug": p["slug"]}
            for p in projects
        ],
    }, 200


def handle_logout(session_token: str) -> dict:
    """POST /api/auth/logout - Invalidate session."""
    if session_token:
        store = Store()
        store.delete_session(session_token)
    return {"status": "ok"}, 200


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

def handle_project_list(session_token: str) -> dict:
    """GET /api/project/list - List projects for user's org."""
    user_info = get_session_user(session_token)
    if not user_info:
        return {"error": "Unauthorized"}, 401

    store = Store()
    projects = store.list_org_projects(user_info["org_id"])
    return {
        "projects": [
            {"id": p["id"], "name": p["name"], "slug": p["slug"],
             "description": p.get("description", ""), "created_at": p["created_at"]}
            for p in projects
        ],
    }, 200


def handle_project_create(body: dict, session_token: str) -> dict:
    """POST /api/project/create - Create a new project in user's org."""
    user_info = get_session_user(session_token)
    if not user_info:
        return {"error": "Unauthorized"}, 401

    name = (body.get("name") or "").strip()
    slug = (body.get("slug") or "").strip().lower()

    if not name or not slug:
        return {"error": "Name and slug are required"}, 400
    if not SLUG_RE.match(slug):
        return {"error": "Slug must be lowercase alphanumeric with hyphens"}, 400

    store = Store()
    if store.get_org_project(user_info["org_id"], slug):
        return {"error": f"Project slug '{slug}' already exists in this organization"}, 409

    project = store.create_org_project(user_info["org_id"], name, slug)
    return {
        "id": project["id"], "name": project["name"],
        "slug": project["slug"], "created_at": project["created_at"],
    }, 200


def handle_org_info(session_token: str) -> dict:
    """GET /api/org/info - Get org info including member list."""
    user_info = get_session_user(session_token)
    if not user_info:
        return {"error": "Unauthorized"}, 401

    store = Store()
    org = store.get_organization_by_id(user_info["org_id"])
    users = store.list_users(user_info["org_id"])
    projects = store.list_org_projects(user_info["org_id"])

    return {
        "id": org["id"], "name": org["name"], "slug": org["slug"],
        "created_at": org["created_at"],
        "members": [
            {"id": u["id"], "email": u.get("email", ""), "role": u.get("role", "member")}
            for u in users
        ],
        "projects": [
            {"id": p["id"], "name": p["name"], "slug": p["slug"]}
            for p in projects
        ],
    }, 200


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_login_response(store: Store, user: dict) -> dict:
    """Create a session for the user and return the response."""
    token = _generate_token(user["id"], user.get("org_id", 0), user.get("email", ""))
    store.create_session(user["id"], token, SESSION_TTL_HOURS)
    return {
        "token": token,
        "redirect": "/project/select",
        "user_id": user["id"],
        "org_id": user.get("org_id", 0),
        "role": user.get("role", "member"),
    }, 200
