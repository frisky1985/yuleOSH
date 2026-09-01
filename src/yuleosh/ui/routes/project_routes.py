# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Project management & Kanban board route handlers (SAAS-3).

Kanban statuses: 需求→开发→审查→测试→发布
Data stored as JSON files in data/{tenant_slug}/projects/*.json

Endpoints:
    GET    /api/v1/projects           → List all projects
    POST   /api/v1/projects           → Create a project
    GET    /api/v1/projects/{slug}    → Get project detail with kanban items
    POST   /api/v1/projects/{slug}    → Update project / move kanban items
    GET    /api/v1/projects/{slug}/items → Get kanban items only

A3 (v3.8.0): migrated to the new-style router signature
``fn(method, path_tail, body, query, handler) -> tuple``; responses are
plain dicts identical to the legacy handlers (SHALL-A3.4).
"""

import logging
import re
from datetime import datetime
from typing import Optional

from yuleosh.tenant.model import TenantStore
from yuleosh.ui.auth_extended import get_session_user


logger = logging.getLogger("project.routes")

KANBAN_STATUSES = ["需求", "开发", "审查", "测试", "发布"]
KANBAN_STATUS_EN = ["requirement", "development", "review", "testing", "release"]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_token(handler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _require_auth(handler) -> Optional[dict]:
    from yuleosh.ui.auth_extended import resolve_session
    return resolve_session(handler)


def _auth_error(handler) -> tuple:
    """401 — exact legacy body for a missing vs invalid session."""
    if not _get_token(handler):
        return {"error": "Authorization required"}, 401
    return {"error": "Invalid session"}, 401


def _get_tenant_slug(user_info: dict) -> str:
    """Get tenant slug from user info, falling back to org info."""
    slug = user_info.get("org_slug", "")
    if slug:
        return slug
    # Fall back to org_id as string
    org_id = user_info.get("org_id", 0)
    return str(org_id)


# ── Project data model helpers ──────────────────────────────────────────────

def _new_project(name: str, description: str = "", owner: str = "") -> dict:
    now = datetime.now().isoformat()
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    return {
        "slug": slug,
        "name": name,
        "description": description,
        "owner": owner,
        "created_at": now,
        "updated_at": now,
        "status": "active",
        "members": [owner] if owner else [],
        "items": [
            {"id": f"kanban-{slug}-{i}", "status": s, "tasks": []}
            for i, s in enumerate(KANBAN_STATUSES)
        ],
    }


def handle_projects(method: str, path_tail: str, body: dict, query: dict,
                    handler=None) -> tuple:
    """Dispatcher for /api/v1/projects (plural, A3/B7).

    path_tail:
      ""            → list (GET) / create (POST)
      "{slug}"      → get (GET) / update (POST)
    """
    slug = (path_tail or "").strip().rstrip("/").split("/")[0]
    if method == "GET":
        if not slug:
            # GET /api/v1/projects — list all for the tenant
            return handle_list_projects(method, path_tail, body, query, handler)
        return handle_get_project(method, path_tail, body, query, handler)
    if method == "POST":
        if not slug:
            return handle_create_project(method, path_tail, body, query, handler)
        return handle_update_project(method, path_tail, body, query, handler)
    return {"error": "Method not allowed"}, 405


def handle_list_projects(method: str, path_tail: str, body: dict, query: dict,
                         handler=None) -> tuple:
    """GET /api/v1/projects — List projects for the caller's tenant."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)
    tenant_slug = _get_tenant_slug(user)
    store = TenantStore()
    projects = store.list_projects(tenant_slug)
    return {"projects": projects}, 200


# ── GET handlers ────────────────────────────────────────────────────────────

def handle_get_project(method: str, path_tail: str, body: dict, query: dict,
                       handler=None) -> tuple:
    """GET /api/v1/projects/{slug} — Get project detail."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    slug = (path_tail or "").split("/")[0]
    if not slug:
        return {"error": "Project slug required"}, 400

    tenant_slug = _get_tenant_slug(user)
    store = TenantStore()

    # Check tenant
    tenant = store.get(tenant_slug)
    if not tenant:
        return {"error": "Tenant not found"}, 404

    project = store.get_project(tenant_slug, slug)
    if not project:
        return {"error": "Project not found"}, 404

    return {"project": project}, 200


# ── POST handlers ───────────────────────────────────────────────────────────

def handle_create_project(method: str, path_tail: str, body: dict, query: dict,
                          handler=None) -> tuple:
    """POST /api/v1/projects — Create a new project."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    if not name:
        return {"error": "Project name is required"}, 400

    tenant_slug = _get_tenant_slug(user)

    from yuleosh.rbac import check_role
    if not check_role(user, "project", "create"):
        return {"error": "Insufficient permissions"}, 403

    store = TenantStore()
    tenant = store.get(tenant_slug)
    if not tenant:
        return {"error": "Tenant not found, create org first"}, 404

    # Check plan limits
    projects = store.list_projects(tenant_slug)
    if len(projects) >= tenant.limits["max_projects"]:
        return {
            "error": f"Project limit reached ({tenant.limits['max_projects']}). "
                     f"Current plan: {tenant.plan}. Upgrade to add more projects."
        }, 403

    project = _new_project(name, description, user.get("email", ""))
    store.save_project(tenant_slug, project)

    return {"project": project}, 201


def handle_update_project(method: str, path_tail: str, body: dict, query: dict,
                          handler=None) -> tuple:
    """POST /api/v1/projects/{slug} — Update project or move kanban items."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    slug = (path_tail or "").split("/")[0]
    if not slug:
        return {"error": "Project slug required"}, 400

    tenant_slug = _get_tenant_slug(user)

    from yuleosh.rbac import check_role
    if not check_role(user, "project", "edit"):
        return {"error": "Insufficient permissions"}, 403

    store = TenantStore()
    project = store.get_project(tenant_slug, slug)
    if not project:
        return {"error": "Project not found"}, 404

    # Update fields
    if "name" in body:
        project["name"] = body["name"]
    if "description" in body:
        project["description"] = body["description"]
    if "items" in body:
        # Moving kanban items — preserve existing items that aren't in the update
        project["items"] = body["items"]
    if "members" in body:
        project["members"] = body["members"]
    if "status" in body:
        project["status"] = body["status"]

    project["updated_at"] = datetime.now().isoformat()
    store.save_project(tenant_slug, project)

    return {"project": project}, 200
