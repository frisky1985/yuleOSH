"""Multi-tenant Organization, Project & User Authentication for yuleOSH.

Provides:
- Email-based signup/login with invite codes
- Organization creation and membership
- Project creation and switching
- Role-based access control (admin vs member)
- Session management with bearer tokens

Designed as a drop-in enhancement alongside src/ui/auth.py (API key auth).
Both can coexist: API key auth for automation, tenant auth for browser UI.
"""

import json
import os
import re
import secrets
import time
from typing import Optional

import jwt  # PyJWT

from src.store import Store


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SESSION_TTL_HOURS = 72

# ── JWT ──────────────────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_token(user_id: int = 0, org_id: int = 0, email: str = "") -> str:
    """Generate a signed JWT with embedded user/org claims and expiration."""
    import time as _time
    now = int(_time.time())
    payload = {
        "sub": str(user_id),
        "org": org_id,
        "email": email,
        "iat": now,
        "exp": now + SESSION_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT. Returns payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))


# ---------------------------------------------------------------------------
# Session helpers (used by server.py for cookie-based auth)
# ---------------------------------------------------------------------------

def get_session_user(token: str) -> Optional[dict]:
    """Resolve a bearer token to a user dict with org info.
    
    Returns dict with user_id, org_id, email, role, org_name, org_slug, or None.
    """
    if not token:
        return None
    store = Store()
    session = store.get_session(token)
    if not session:
        return None
    user = store.get_user_by_id(session["user_id"])
    if not user:
        return None
    org = store.get_organization_by_id(user["org_id"])
    if not org:
        return None
    return {
        "user_id": user["id"],
        "org_id": org["id"],
        "email": user["email"],
        "role": user["role"],
        "org_name": org["name"],
        "org_slug": org["slug"],
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

def handle_signin(body: dict) -> dict:
    """POST /api/auth/signin - Email + optional invite code.

    Flow:
    1. If invite_code provided and org exists → login or signup as member
    2. If no invite_code and user doesn't exist → first time, needs org creation
    3. If user exists (email + org found) → login

    Returns: {token, redirect} or {error}
    """
    email = (body.get("email") or "").strip().lower()
    invite_code = (body.get("invite_code") or "").strip().lower()

    if not email or not EMAIL_RE.match(email):
        return {"error": "Valid email is required"}, 400

    store = Store()

    # Check if invite_code points to an existing org
    target_org = None
    if invite_code:
        target_org = store.get_organization(invite_code)
        if not target_org:
            return {"error": f"Organization '{invite_code}' not found. Check the invite code."}, 404

    if target_org:
        # Joining an existing org
        existing_user = store.get_user(target_org["id"], email)
        if existing_user:
            # Login existing member
            return _create_login_response(store, existing_user)
        else:
            # Sign up as new member (role=member by default)
            user = store.create_user(target_org["id"], email, "member")
            return _create_login_response(store, user)
    else:
        # No invite code → check if user has an org
        # We need to find the user across all orgs
        orgs = store.list_organizations()
        for org in orgs:
            user = store.get_user(org["id"], email)
            if user:
                return _create_login_response(store, user)

        # First-time user — need to create org first
        token = _generate_token(email=email)
        return {"token": token, "redirect": "/org/setup", "needs_org": True}, 200


def handle_org_create(body: dict, session_token: str) -> dict:
    """POST /api/org/create - Create organization and first project.

    Requires a valid session token from signin (needs_org flow).
    """
    org_name = (body.get("org_name") or "").strip()
    org_slug = (body.get("org_slug") or "").strip().lower()
    project_name = (body.get("project_name") or "").strip()
    project_slug = (body.get("project_slug") or "").strip().lower()

    # Validate
    if not org_name or not org_slug:
        return {"error": "Organization name and slug are required"}, 400
    if not SLUG_RE.match(org_slug):
        return {"error": "Slug must be lowercase alphanumeric with hyphens (e.g. 'my-org')"}, 400
    if not project_name or not project_slug:
        return {"error": "Project name and slug are required"}, 400
    if not SLUG_RE.match(project_slug):
        return {"error": "Project slug must be lowercase alphanumeric with hyphens"}, 400

    store = Store()

    # Check slug uniqueness
    existing = store.get_organization(org_slug)
    if existing:
        return {"error": f"Organization slug '{org_slug}' is already taken"}, 409

    # We need the user's email from the signin flow
    # The session token was returned by handle_signin when needs_org was True.
    # For simplicity, we use the session token or an email in the body.
    email = (body.get("email") or "").strip().lower()

    # If email wasn't in body, try to get it from the signin flow
    # The client should pass it; if not, reject.
    if not email:
        return {"error": "Email is required for org creation"}, 400

    # Create org
    org = store.create_organization(org_name, org_slug)

    # Create user as admin
    user = store.create_user(org["id"], email, "admin")

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
    """GET /api/auth/session - Get current session info.

    Returns user, org, and project context.
    """
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

    # Check uniqueness within org
    existing = store.get_org_project(user_info["org_id"], slug)
    if existing:
        return {"error": f"Project slug '{slug}' already exists in this organization"}, 409

    project = store.create_org_project(
        user_info["org_id"], name, slug
    )

    return {
        "id": project["id"],
        "name": project["name"],
        "slug": project["slug"],
        "created_at": project["created_at"],
    }, 200


# ---------------------------------------------------------------------------
# Org endpoints
# ---------------------------------------------------------------------------

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
        "id": org["id"],
        "name": org["name"],
        "slug": org["slug"],
        "created_at": org["created_at"],
        "members": [
            {"id": u["id"], "email": u["email"], "role": u["role"]}
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
        "org_id": user["org_id"],
        "role": user["role"],
    }, 200
