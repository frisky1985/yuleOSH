# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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

from yuleosh.store import Store
from yuleosh.ui.auth_cookies import (  # T1 (v3.9.0): single cookie policy source
    ACCESS_TTL_HOURS,     # 0.5h — short-lived access token (SHALL-T1.2)
    REFRESH_TTL_HOURS,    # 168h — long-lived refresh token (SHALL-T1.2)
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SESSION_TTL_HOURS = 72  # legacy single-token default (kept for direct callers)

# ── JWT ──────────────────────────────────────────────────────────────────────
# 本地免登录模式（YULEOSH_AUTH_DISABLED=1 → AUTH_ENABLED=False）下，JWT 签名
# 不会被任何代码路径使用（is_authenticated 直接放行），因此不必强制要求
# YULEOSH_JWT_SECRET —— 否则 import 阶段就 raise，会拖垮整条 /api/v1/* 路由
# （router.dispatch 间接 import auth_extended → 500 "API dispatch failed"）。
# 仅在鉴权真正启用时才 fail-closed 要求密钥；否则给一个非安全兜底值。
from yuleosh.ui.auth import AUTH_ENABLED  # 置于 import 顶部，避免顶层循环依赖

_YULEOSH_JWT_SECRET_ENV = os.environ.get("YULEOSH_JWT_SECRET")
if _YULEOSH_JWT_SECRET_ENV:
    JWT_SECRET = _YULEOSH_JWT_SECRET_ENV
elif AUTH_ENABLED:
    raise RuntimeError(
        "YULEOSH_JWT_SECRET environment variable is required for multi-tenant auth. "
        "Generate one with: openssl rand -base64 48"
    )
else:
    # 本地 dev：仅需要模块可 import，签名密钥不会被实际使用。
    JWT_SECRET = os.environ.get("YULEOSH_DEV_JWT_SECRET", "dev-insecure-secret-do-not-use")
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
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash. Constant-time comparison."""
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _generate_token(user_id: int = 0, org_id: int = 0, email: str = "",
                    purpose: Optional[str] = None,
                    ttl_hours: float = SESSION_TTL_HOURS) -> str:
    """Generate a signed JWT with embedded user/org claims and expiration.

    T1 (v3.9.0): ``ttl_hours`` overrides the lifetime per token — the
    access/refresh pair uses ACCESS_TTL_HOURS / REFRESH_TTL_HOURS while
    the legacy default (SESSION_TTL_HOURS=72h) is preserved for direct
    callers (org_setup tokens, tests, API clients).
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "email": email,
        "iat": now,
        "exp": now + int(ttl_hours * 3600),
        # T1 (v3.9.0): unique per-token id — the JWT is otherwise fully
        # deterministic for a given second (same user/org/iat/exp), so a
        # refresh issued within the same second would be byte-identical to
        # its predecessor and defeat rotation (session row hash collision).
        "jti": secrets.token_hex(16),
    }
    if purpose:
        payload["purpose"] = purpose
    import jwt
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict | None:
    """Decode and validate JWT. Returns payload dict or None if invalid/expired."""
    import jwt
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        logging.getLogger("auth_extended").warning("JWT decode failed: %s", e)
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))


def _is_refresh_token(payload: dict) -> bool:
    """T1 (v3.9.0): True when the JWT is a refresh token (purpose="refresh").

    Refresh tokens are ONLY valid at ``POST /api/auth/refresh`` (SHALL-T1.5)
    and must never authenticate ordinary API requests — otherwise the
    7-day refresh token would be a full-strength bearer credential and the
    short access TTL would be meaningless.  Both verify paths reject them
    (SHALL-T1.4, T-T1-07).
    """
    return bool(payload) and payload.get("purpose") == "refresh"


def _issue_token_pair(store: Store, user_id: int, org_id: int,
                      email: str) -> tuple:
    """T1 (v3.9.0): issue an access + refresh token pair (dual httpOnly cookies).

    - access  : short TTL (ACCESS_TTL_HOURS=30min) — used by API auth paths
    - refresh : long TTL (REFRESH_TTL_HOURS=7d) + purpose="refresh" — only
      accepted by the refresh endpoint (see _is_refresh_token)

    Both tokens get their own ``user_sessions`` row (sha256-hashed), so
    access expiry and refresh expiry are enforced independently by the DB
    (SHALL-T1.2: expires_at aligns with refresh lifetime).
    """
    access = _generate_token(user_id, org_id, email, ttl_hours=ACCESS_TTL_HOURS)
    refresh = _generate_token(user_id, org_id, email, purpose="refresh",
                              ttl_hours=REFRESH_TTL_HOURS)
    store.create_session(user_id, access, ACCESS_TTL_HOURS)
    store.create_session(user_id, refresh, REFRESH_TTL_HOURS)
    return access, refresh


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
    # T1 (v3.9.0): refresh tokens never authenticate API requests.
    if _is_refresh_token(payload):
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

def resolve_session(handler) -> dict | None:
    """Resolve the current user from a request handler, cookie-aware.

    SHALL-T1.4 (mirror ``auth.py:is_authenticated`` step 4): the frontend
    ``apiFetch`` uses ``credentials: "same-origin"`` and sends NO
    ``Authorization`` header, so a Bearer-only check would 401 every
    browser / local-dev request.  We therefore fall back to the
    ``yuleosh_at`` access cookie when no Bearer header is present.

    Contract:
      - ``AUTH_ENABLED=False`` (YULEOSH_AUTH_DISABLED=1) → inject the
        local-dev admin user (symmetric with ``api.middleware.require_auth``).
      - An ``Authorization`` header that IS present but is not ``Bearer``
        fails closed (no cookie fallback) — same rule as the API middleware.
      - Returns the user dict (incl. org info) on success, else None.
    """
    from yuleosh.ui.auth import AUTH_ENABLED
    if not AUTH_ENABLED:
        from yuleosh.api.middleware import _resolve_local_dev_user
        return _resolve_local_dev_user()
    auth = (handler.headers.get("Authorization", "")
            or handler.headers.get("authorization", ""))
    if auth:
        if auth.startswith("Bearer "):
            return get_session_user(auth[7:])
        return None  # present but not Bearer → fail closed, no cookie fallback
    from yuleosh.ui.auth_cookies import ACCESS_COOKIE_NAME, read_cookie_value
    cookie = read_cookie_value(handler.headers, ACCESS_COOKIE_NAME)
    if cookie:
        return get_session_user(cookie)
    return None


def get_session_user(token: str) -> dict | None:
    """Resolve a bearer token to a user dict with org info.

    P1-6 (S-P1-02): the JWT signature is verified first (defense in depth —
    only signed tokens can resolve a session), then the session row is
    looked up by its sha256 hash.  Random/forged strings never resolve.
    """
    if not token:
        return None
    payload = _decode_token(token)
    if payload is None:
        return None
    # T1 (v3.9.0): refresh tokens never resolve as a session credential.
    if _is_refresh_token(payload):
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

def register(body: dict) -> tuple:
    """Unified v1 register — org + admin user + token (A1, SHALL-A1.4).

    v1 semantics (POST /api/v1/auth/register):
      {email, password, organization_name} -> org (or reuse by slug) +
      admin user + session token; 409 when the email already exists in the
      target org; 400 on validation errors.

    This is the single implementation of the org+user+token signup flow
    used by the v1 API (the frontend uses handle_signin + handle_org_create).
    Returns ``(dict, status)`` with ``token/user_id/org_id/role`` on
    success or ``{"error": ...}`` on failure.
    """
    email = (body.get("email") or "").strip().lower()
    password = (body.get("password") or "").strip()
    org_name = (body.get("organization_name") or "").strip()

    if not email or not EMAIL_RE.match(email):
        return {"error": "Valid email is required"}, 400
    if not password or len(password) < 8:
        return {"error": "Password must be at least 8 characters"}, 400
    if not org_name:
        return {"error": "organization_name is required"}, 400

    store = Store()
    org_slug = _slugify(org_name)
    org = store.get_organization(org_slug)
    if org:
        existing = store.get_user(org["id"], email)
        if existing:
            return {"error": "Email already registered in this organization"}, 409
    else:
        org = store.create_organization(org_name, org_slug)

    password_hash = _hash_password(password)
    user = store.create_user(org["id"], email, "admin", password_hash)
    token, refresh_token = _issue_token_pair(  # T1 (v3.9.0): access+refresh
        store, user["id"], org["id"], email)
    return {"token": token, "refresh_token": refresh_token,
            "user_id": user["id"],
            "org_id": org["id"], "role": "admin"}, 200


# Demo account seeded at server startup so the documented credentials
# (demo@yuleosh.com / Demo2026!yuleosh) work out of the box.  Idempotent:
# creates the demo org + user when missing, and repairs a wrong/empty
# password_hash so the documented login always succeeds — without ever
# downgrading a password that already verifies.
DEMO_EMAIL = "demo@yuleosh.com"
DEMO_PASSWORD = "Demo2026!yuleosh"
DEMO_ORG_SLUG = "demo"
DEMO_ORG_NAME = "yuleOSH Demo"


def ensure_demo_account(store: "Store") -> None:
    """Ensure the demo account exists with the documented credentials.

    Called once at server startup (http_app.main).  Safe to call on every
    boot: it only creates/repairs, never clobbers a working password.

    The demo user may already live in ANY organization (e.g. org_id=86 from
    an earlier provisioning run) — so we search across all orgs by email,
    not just under a hardcoded slug "demo":

      - demo user found in some org, password empty/wrong -> reset to DEMO_PASSWORD
      - demo user found, password correct                -> no-op
      - demo user not found anywhere                     -> create demo org + admin
    """
    try:
        user = store.get_user_by_email(DEMO_EMAIL)
        if user:
            # Repair only a broken/empty password — never overwrite a good one.
            existing_hash = user.get("password_hash")
            if not existing_hash or not _verify_password(DEMO_PASSWORD, existing_hash):
                store.update_user_password(
                    user["org_id"], DEMO_EMAIL, _hash_password(DEMO_PASSWORD))
                logging.getLogger("yuleosh.auth").info(
                    "Repaired demo account password %s (org=%s)",
                    DEMO_EMAIL, user.get("org_id"))
            return
        # Not found anywhere — create a fresh demo org + admin user.
        org = store.get_organization(DEMO_ORG_SLUG)
        if not org:
            org = store.create_organization(DEMO_ORG_NAME, DEMO_ORG_SLUG)
        store.create_user(
            org["id"], DEMO_EMAIL, "admin", _hash_password(DEMO_PASSWORD))
        logging.getLogger("yuleosh.auth").info(
            "Seeded demo account %s (org=%s)", DEMO_EMAIL, DEMO_ORG_SLUG)
    except Exception as e:  # noqa: BLE001 — seed 失败不影响 dashboard 启动
        logging.getLogger("yuleosh.auth").warning("ensure_demo_account failed: %s", e)


# ── Dual-view test accounts ───────────────────────────────────────────────
# The dashboard shell splits by the user's role (see frontend
# use-session-role.ts / dashboard/layout.tsx):
#   - admin                         → horizontal TopNav  (decision-maker view)
#   - developer / reviewer / auditor → vertical EngineerSidebar (engineer view)
# These two seeded accounts let the two views be exercised by distinct users.
VIEW_DECISION_EMAIL = "decision@yuleosh.com"
VIEW_DECISION_PASSWORD = "Demo2026!decision"
VIEW_ENGINEER_EMAIL = "engineer@yuleosh.com"
VIEW_ENGINEER_PASSWORD = "Demo2026!engineer"


def ensure_view_test_accounts(store: "Store") -> None:
    """Seed two role-based test accounts so the dual dashboard view can be
    exercised by distinct users.

    Idempotent: creates/repairs only, never clobbers a working password.
    Both accounts co-locate with the demo account's org (so they share demo
    projects); falls back to a fresh demo org when the demo account is absent.
    """
    try:
        demo = store.get_user_by_email(DEMO_EMAIL)
        if demo:
            org_id = demo["org_id"]
        else:
            org = store.get_organization(DEMO_ORG_SLUG)
            if not org:
                org = store.create_organization(DEMO_ORG_NAME, DEMO_ORG_SLUG)
            org_id = org["id"]

        _seed_view_account(store, org_id, VIEW_DECISION_EMAIL, "admin", VIEW_DECISION_PASSWORD)
        _seed_view_account(store, org_id, VIEW_ENGINEER_EMAIL, "developer", VIEW_ENGINEER_PASSWORD)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("yuleosh.auth").warning("ensure_view_test_accounts failed: %s", e)


def _seed_view_account(store: "Store", org_id: int, email: str,
                       role: str, password: str) -> None:
    """Create or repair a single view-test account (idempotent)."""
    user = store.get_user_by_email(email)
    if user:
        # Repair only a broken/empty password — never overwrite a good one.
        existing_hash = user.get("password_hash")
        if not existing_hash or not _verify_password(password, existing_hash):
            store.update_user_password(
                user["org_id"], email, _hash_password(password))
            logging.getLogger("yuleosh.auth").info(
                "Repaired view-test account %s (org=%s)", email, user.get("org_id"))
        return
    store.create_user(org_id, email, role, _hash_password(password))
    logging.getLogger("yuleosh.auth").info(
        "Seeded view-test account %s (role=%s, org=%s)", email, role, org_id)


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

    # Create session — access + refresh pair (T1 v3.9.0, SHALL-T1.1)
    token, refresh_token = _issue_token_pair(store, user["id"], org["id"], email)

    return {
        "token": token,
        "refresh_token": refresh_token,
        "redirect": "/project/select",
        "org_id": org["id"],
        "org_slug": org_slug,
    }, 200


def handle_refresh(refresh_token: str) -> tuple:
    """POST /api/auth/refresh — issue a new access+refresh pair (T1.5).

    Accepts ONLY a refresh token (purpose="refresh"): signature/expiry +
    DB session row + user row must all be valid.  On success the old
    refresh session is rotated out (single-use, SHALL-T1.13 — B2 chose
    the dedicated endpoint so rotation is SHALL) and a fresh pair is
    issued.  The route layer converts the pair to Set-Cookie and clears
    both cookies on failure (T-T1-11-neg).
    """
    if not refresh_token:
        return {"error": "Refresh token required"}, 401
    payload = _decode_token(refresh_token)
    if payload is None or not _is_refresh_token(payload):
        return {"error": "Invalid or expired refresh token"}, 401

    user_id = payload.get("sub") or payload.get("user_id")
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id = None
    if user_id is None:
        return {"error": "Invalid or expired refresh token"}, 401

    store = Store()
    # DB session row must still exist (logout / expiry invalidates).
    session = store.get_session(refresh_token)
    if not session:
        return {"error": "Invalid or expired refresh token"}, 401
    user = store.get_user_by_id(user_id)
    if not user:
        return {"error": "Invalid or expired refresh token"}, 401

    org_id = payload.get("org") or payload.get("org_id")
    try:
        org_id = int(org_id) if org_id is not None else None
    except (TypeError, ValueError):
        org_id = None
    if org_id is None:
        org_id = user.get("org_id", 0)
    email = payload.get("email") or user.get("email", "")

    # Rotation (SHALL-T1.13): the old refresh token is single-use.
    store.delete_session(refresh_token)
    access, new_refresh = _issue_token_pair(store, user_id, org_id, email)
    return {"token": access, "refresh_token": new_refresh}, 200


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
    """Create a session for the user and return the response.

    T1 (v3.9.0): issues the access + refresh pair; the route layer pops
    ``refresh_token`` and emits it as the httpOnly refresh cookie, keeping
    the JSON body contract identical to v3.8.0 (SHALL-T1.1).
    """
    token, refresh_token = _issue_token_pair(
        store, user["id"], user.get("org_id", 0), user.get("email", ""))
    return {
        "token": token,
        "refresh_token": refresh_token,
        "redirect": "/project/select",
        "user_id": user["id"],
        "org_id": user.get("org_id", 0),
        "role": user.get("role", "member"),
    }, 200
