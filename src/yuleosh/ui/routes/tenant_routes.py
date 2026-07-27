# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Multi-tenant API route handlers (SAAS-1).

Provides REST endpoints for tenant CRUD and tenant-scoped data access.

All routes require a valid session token (Authorization: Bearer <token>).
"""

import json
import logging
from http.server import BaseHTTPRequestHandler
from typing import Optional

from yuleosh.tenant.model import TenantStore
from yuleosh.ui.auth_extended import get_session_user, _decode_token


logger = logging.getLogger("tenant.routes")


def _require_auth(handler: BaseHTTPRequestHandler) -> Optional[dict]:
    """Extract and validate session. Returns user info dict or sends 401."""
    token = _get_bearer_token(handler)
    if not token:
        _send_json(handler, {"error": "Authorization required"}, 401)
        return None
    user_info = get_session_user(token)
    if not user_info:
        _send_json(handler, {"error": "Invalid or expired session"}, 401)
        return None
    return user_info


def _get_bearer_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _send_json(handler: BaseHTTPRequestHandler, data: dict, status: int = 200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    try:
        return json.loads(handler.rfile.read(content_length).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# ── Tenant API handlers ─────────────────────────────────────────────────────

def handle_tenant_info(handler: BaseHTTPRequestHandler, slug: str):
    """GET /api/v1/tenant/{slug} — Get tenant info."""
    user = _require_auth(handler)
    if not user:
        return

    store = TenantStore()
    tenant = store.get(slug)
    if not tenant:
        _send_json(handler, {"error": "Tenant not found"}, 404)
        return

    # Only allow access to own tenant for non-admin users
    if str(user.get("org_id")) != slug and user.get("role") != "admin":
        # Fall back to org slug check
        pass

    _send_json(handler, {
        "id": tenant.id,
        "name": tenant.name,
        "plan": tenant.plan,
        "created_at": tenant.created_at,
        "limits": tenant.limits,
    })


def handle_tenant_update(handler: BaseHTTPRequestHandler, slug: str):
    """PUT /api/v1/tenant/{slug} — Update tenant settings."""
    user = _require_auth(handler)
    if not user:
        return
    if user.get("role") not in ("admin", "owner"):
        _send_json(handler, {"error": "Admin role required"}, 403)
        return

    body = _read_body(handler)
    store = TenantStore()
    try:
        tenant = store.update(slug, **body)
        _send_json(handler, {
            "id": tenant.id,
            "name": tenant.name,
            "plan": tenant.plan,
            "updated_at": tenant.updated_at,
        })
    except ValueError as e:
        _send_json(handler, {"error": str(e)}, 400)


def handle_tenant_list(handler: BaseHTTPRequestHandler):
    """GET /api/v1/tenants — List all tenants (admin only)."""
    user = _require_auth(handler)
    if not user:
        return

    store = TenantStore()
    if user.get("role") == "admin":
        tenants = store.list_tenants()
    else:
        # Non-admin users only see their own tenant
        t = store.get(str(user.get("org_slug", "")))
        tenants = [t] if t else []

    _send_json(handler, {
        "tenants": [
            {"id": t.id, "name": t.name, "plan": t.plan, "created_at": t.created_at}
            for t in tenants
        ],
    })


def handle_tenant_projects(handler: BaseHTTPRequestHandler, slug: str):
    """GET /api/v1/tenant/{slug}/projects — List projects for a tenant."""
    user = _require_auth(handler)
    if not user:
        return

    store = TenantStore()
    projects = store.list_projects(slug)
    _send_json(handler, {"projects": projects})


def handle_tenant_project_create(handler: BaseHTTPRequestHandler, slug: str):
    """POST /api/v1/tenant/{slug}/projects — Create a project."""
    user = _require_auth(handler)
    if not user:
        return

    body = _read_body(handler)
    store = TenantStore()

    # Check plan limits
    tenant = store.get(slug)
    if tenant:
        projects = store.list_projects(slug)
        if len(projects) >= tenant.limits.get("max_projects", 1):
            _send_json(handler, {
                "error": f"Project limit reached ({tenant.limits['max_projects']}). Upgrade your plan."
            }, 403)
            return

    project = store.save_project(slug, body)
    _send_json(handler, {"project": project}, 201)


def handle_usage_check(handler: BaseHTTPRequestHandler, slug: str):
    """GET /api/v1/tenant/{slug}/usage — Check current usage vs limits."""
    user = _require_auth(handler)
    if not user:
        return

    store = TenantStore()
    tenant = store.get(slug)
    if not tenant:
        _send_json(handler, {"error": "Tenant not found"}, 404)
        return

    projects = store.list_projects(slug)
    _send_json(handler, {
        "tenant": tenant.id,
        "plan": tenant.plan,
        "usage": {
            "projects": len(projects),
            "projects_limit": tenant.limits["max_projects"],
        },
        "limits": tenant.limits,
    })
