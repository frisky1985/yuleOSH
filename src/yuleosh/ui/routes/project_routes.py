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
"""

import json
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from yuleosh.tenant.model import TenantStore


logger = logging.getLogger("project.routes")

KANBAN_STATUSES = ["需求", "开发", "审查", "测试", "发布"]
KANBAN_STATUS_EN = ["requirement", "development", "review", "testing", "release"]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _require_auth(handler: BaseHTTPRequestHandler) -> Optional[dict]:
    from yuleosh.ui.auth_extended import get_session_user
    token = _get_token(handler)
    if not token:
        _send_json(handler, {"error": "Authorization required"}, 401)
        return None
    user_info = get_session_user(token)
    if not user_info:
        _send_json(handler, {"error": "Invalid session"}, 401)
        return None
    return user_info


def _send_json(handler: BaseHTTPRequestHandler, data, status: int = 200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse the request body (P1-5: unified clamped read_body).

    Delegates to yuleosh.api.read_body which clamps Content-Length to 10 MB
    and converts malformed headers to BadRequest.  Invalid JSON / bad
    Content-Length yield {} — caller validation returns the 4xx.
    """
    from yuleosh.api import read_body, BadRequest
    try:
        return read_body(handler)
    except BadRequest:
        return {}


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
    import re
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


# ── GET handlers ────────────────────────────────────────────────────────────

def handle_get_project(handler: BaseHTTPRequestHandler, path: str):
    """GET /api/v1/projects/{slug} — Get project detail."""
    user = _require_auth(handler)
    if not user:
        return

    slug = path.split("/")[-1]
    if not slug:
        _send_json(handler, {"error": "Project slug required"}, 400)
        return

    tenant_slug = _get_tenant_slug(user)
    store = TenantStore()

    # Check tenant
    tenant = store.get(tenant_slug)
    if not tenant:
        _send_json(handler, {"error": "Tenant not found"}, 404)
        return

    project = store.get_project(tenant_slug, slug)
    if not project:
        _send_json(handler, {"error": "Project not found"}, 404)
        return

    _send_json(handler, {"project": project})


# ── POST handlers ───────────────────────────────────────────────────────────

def handle_create_project(handler: BaseHTTPRequestHandler):
    """POST /api/v1/projects — Create a new project."""
    user = _require_auth(handler)
    if not user:
        return

    body = _read_body(handler)
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    if not name:
        _send_json(handler, {"error": "Project name is required"}, 400)
        return

    tenant_slug = _get_tenant_slug(user)

    from yuleosh.rbac import check_role
    if not check_role(user, "project", "create"):
        _send_json(handler, {"error": "Insufficient permissions"}, 403)
        return

    store = TenantStore()
    tenant = store.get(tenant_slug)
    if not tenant:
        _send_json(handler, {"error": "Tenant not found, create org first"}, 404)
        return

    # Check plan limits
    projects = store.list_projects(tenant_slug)
    if len(projects) >= tenant.limits["max_projects"]:
        _send_json(handler, {
            "error": f"Project limit reached ({tenant.limits['max_projects']}). "
                     f"Current plan: {tenant.plan}. Upgrade to add more projects."
        }, 403)
        return

    project = _new_project(name, description, user.get("email", ""))
    store.save_project(tenant_slug, project)

    _send_json(handler, {"project": project}, 201)


def handle_update_project(handler: BaseHTTPRequestHandler, path: str):
    """POST /api/v1/projects/{slug} — Update project or move kanban items."""
    user = _require_auth(handler)
    if not user:
        return

    slug = path.split("/")[-1]
    if not slug:
        _send_json(handler, {"error": "Project slug required"}, 400)
        return

    body = _read_body(handler)
    tenant_slug = _get_tenant_slug(user)

    from yuleosh.rbac import check_role
    if not check_role(user, "project", "edit"):
        _send_json(handler, {"error": "Insufficient permissions"}, 403)
        return

    store = TenantStore()
    project = store.get_project(tenant_slug, slug)
    if not project:
        _send_json(handler, {"error": "Project not found"}, 404)
        return

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

    _send_json(handler, {"project": project})
