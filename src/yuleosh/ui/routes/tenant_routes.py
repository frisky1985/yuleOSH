# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Multi-tenant API route handlers (SAAS-1).

Provides REST endpoints for tenant CRUD and tenant-scoped data access.

A3 (v3.8.0): migrated from the legacy ``fn(handler, slug)`` signature to
the new-style ``fn(method, path_tail, body, query, handler) -> tuple`` so
these endpoints are served by the router's ROUTES table (single dispatch
path — no ``_dispatch_legacy``).  Response bodies / status codes are
unchanged (SHALL-A3.4): handlers return PLAIN dicts (not the ok/data
wrapper) exactly as the legacy ``_send_json`` wrote them.
"""

import logging
from typing import Optional

from yuleosh.tenant.model import TenantStore
from yuleosh.ui.auth_extended import get_session_user


logger = logging.getLogger("tenant.routes")


def _get_bearer_token(handler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _require_auth(handler) -> Optional[dict]:
    """Extract and validate session. Returns user info dict or None.

    Legacy semantics: no token → 401 {"error": "Authorization required"};
    invalid/expired session → 401 {"error": "Invalid or expired session"}.
    Handlers disambiguate via ``_get_bearer_token``.
    """
    token = _get_bearer_token(handler)
    if not token:
        return None
    return get_session_user(token)


def _auth_error(handler) -> tuple:
    """401 — exact legacy body for a missing vs invalid session (SHALL-A3.4)."""
    if not _get_bearer_token(handler):
        return {"error": "Authorization required"}, 401
    return {"error": "Invalid or expired session"}, 401


# ── Tenant API handlers (new-style) ─────────────────────────────────────────

def handle_tenant(method: str, path_tail: str, body: dict, query: dict,
                  handler=None) -> tuple:
    """Dispatcher for /api/v1/tenant/* (A3, B7).

    path_tail examples:
      "acme"              → tenant info (GET) / update (PUT)
      "acme/projects"     → list projects (GET) / create project (POST)
      "acme/usage"        → usage check (GET)
    """
    parts = (path_tail or "").split("/")
    slug = parts[0] if parts and parts[0] else ""
    sub = parts[1] if len(parts) > 1 else ""

    if method == "GET":
        if not sub:
            return handle_tenant_info(method, path_tail, body, query, handler)
        if sub == "projects":
            return handle_tenant_projects(method, path_tail, body, query, handler)
        if sub == "usage":
            return handle_usage_check(method, path_tail, body, query, handler)
    elif method == "PUT":
        if not sub:
            return handle_tenant_update(method, path_tail, body, query, handler)
    elif method == "POST":
        if sub == "projects":
            return handle_tenant_project_create(method, path_tail, body, query,
                                                handler)
    return {"error": "Method not allowed"}, 405


def handle_tenant_info(method: str, path_tail: str, body: dict, query: dict,
                       handler=None) -> tuple:
    """GET /api/v1/tenant/{slug} — Get tenant info."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)
    slug = (path_tail or "").split("/")[0]
    if not slug:
        return {"error": "Tenant slug required"}, 400

    store = TenantStore()
    tenant = store.get(slug)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    return {
        "id": tenant.id,
        "name": tenant.name,
        "plan": tenant.plan,
        "created_at": tenant.created_at,
        "limits": tenant.limits,
    }, 200


def handle_tenant_update(method: str, path_tail: str, body: dict, query: dict,
                         handler=None) -> tuple:
    """PUT /api/v1/tenant/{slug} — Update tenant settings."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)
    if user.get("role") not in ("admin", "owner"):
        return {"error": "Admin role required"}, 403

    slug = (path_tail or "").split("/")[0]
    store = TenantStore()
    try:
        tenant = store.update(slug, **body)
        return {
            "id": tenant.id,
            "name": tenant.name,
            "plan": tenant.plan,
            "updated_at": tenant.updated_at,
        }, 200
    except ValueError as e:
        return {"error": str(e)}, 400


def handle_tenant_list(method: str, path_tail: str, body: dict, query: dict,
                       handler=None) -> tuple:
    """GET /api/v1/tenants — List all tenants (admin only)."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    store = TenantStore()
    if user.get("role") == "admin":
        tenants = store.list_tenants()
    else:
        # Non-admin users only see their own tenant
        t = store.get(str(user.get("org_slug", "")))
        tenants = [t] if t else []

    return {
        "tenants": [
            {"id": t.id, "name": t.name, "plan": t.plan, "created_at": t.created_at}
            for t in tenants
        ],
    }, 200


def handle_tenant_projects(method: str, path_tail: str, body: dict, query: dict,
                           handler=None) -> tuple:
    """GET /api/v1/tenant/{slug}/projects — List projects for a tenant."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    slug = (path_tail or "").split("/")[0]
    store = TenantStore()
    projects = store.list_projects(slug)
    return {"projects": projects}, 200


def handle_tenant_project_create(method: str, path_tail: str, body: dict,
                                 query: dict, handler=None) -> tuple:
    """POST /api/v1/tenant/{slug}/projects — Create a project."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    slug = (path_tail or "").split("/")[0]
    store = TenantStore()

    # Check plan limits
    tenant = store.get(slug)
    if tenant:
        projects = store.list_projects(slug)
        if len(projects) >= tenant.limits.get("max_projects", 1):
            return {
                "error": f"Project limit reached ({tenant.limits['max_projects']}). Upgrade your plan."
            }, 403

    project = store.save_project(slug, body)
    return {"project": project}, 201


def handle_usage_check(method: str, path_tail: str, body: dict, query: dict,
                       handler=None) -> tuple:
    """GET /api/v1/tenant/{slug}/usage — Check current usage vs limits."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    slug = (path_tail or "").split("/")[0]
    store = TenantStore()
    tenant = store.get(slug)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    projects = store.list_projects(slug)
    return {
        "tenant": tenant.id,
        "plan": tenant.plan,
        "usage": {
            "projects": len(projects),
            "projects_limit": tenant.limits["max_projects"],
        },
        "limits": tenant.limits,
    }, 200
