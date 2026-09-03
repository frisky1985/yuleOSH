
# @req RS-007  @req CR-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""RBAC Role & Permission Model (SAAS-2).

Unified permission matrix covering all yuleOSH resources.

Roles:
  - Admin:            Full access — manage tenants, users, billing, settings
  - Developer:        Code, test, CI — run pipelines, view results, manage code
  - Reviewer:         Review sessions, view evidence, approve/reject pipeline artifacts
  - Auditor:          View-only — evidence, audit logs, reports, dashboards
  - Viewer:           Read-only on all modules — no create/edit/run/commit/approve
  - Quality Manager:  View all + approve/reject reviews + export evidence/audit
                      (quality oversight); no code commit / pipeline run

Usage:
    # In middleware:
    user_info = get_session_user(token)
    if not check_role(user_info, "developer"):
        return 403 error

    # Or as a decorator for route handlers:
    @require_role("admin")
    def handle_sensitive_op(handler, path):
        ...
"""

import functools
import json
import logging
from enum import Enum
from typing import Optional

from yuleosh.ui.auth_extended import get_session_user


logger = logging.getLogger("rbac.model")


# ── Role constants ──────────────────────────────────────────────────────────
# 角色字符串常量（ROLE_*）的唯一事实来源是 rbac/role_contract.py；
# 此处仅从契约导入，避免角色词表再次漂移。

# noqa: F401 — 这些常量被 PERMISSION_MATRIX / ALL_ROLES / 测试用例从 model 直接引用。
from yuleosh.rbac.role_contract import (  # isort: skip
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DEVELOPER,
    ROLE_QUALITY_MANAGER,
    ROLE_REVIEWER,
    ROLE_VIEWER,
)

ALL_ROLES = [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
             ROLE_VIEWER, ROLE_QUALITY_MANAGER]

# Human-readable labels
ROLE_LABELS = {
    ROLE_ADMIN: "Administrator",
    ROLE_DEVELOPER: "Developer",
    ROLE_REVIEWER: "Reviewer",
    ROLE_AUDITOR: "Auditor",
    ROLE_VIEWER: "Viewer",
    ROLE_QUALITY_MANAGER: "Quality Manager",
}


# ── Permission Matrix ───────────────────────────────────────────────────────
# Each resource maps to a set of roles that have access.
# Format: {resource: {action: [roles]}}
# Action types: view, create, edit, delete, approve, run

PERMISSION_MATRIX = {
    # ── Tenant management ───────────────────────────────────────────────
    "tenant": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "edit":       [ROLE_ADMIN],
        "delete":     [ROLE_ADMIN],
        "manage_billing": [ROLE_ADMIN],
    },
    # ── User management ─────────────────────────────────────────────────
    "user": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "invite":     [ROLE_ADMIN],
        "edit_role":  [ROLE_ADMIN],
        "remove":     [ROLE_ADMIN],
    },
    # ── Project / Kanban ────────────────────────────────────────────────
    "project": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "create":     [ROLE_ADMIN, ROLE_DEVELOPER],
        "edit":       [ROLE_ADMIN, ROLE_DEVELOPER],
        "delete":     [ROLE_ADMIN],
        "move_task":  [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER],
    },
    # ── Pipeline / CI ───────────────────────────────────────────────────
    "pipeline": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "run":        [ROLE_ADMIN, ROLE_DEVELOPER],
        "configure":  [ROLE_ADMIN, ROLE_DEVELOPER],
        "cancel":     [ROLE_ADMIN, ROLE_DEVELOPER],
    },
    # ── Code / Source ───────────────────────────────────────────────────
    "code": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "edit":       [ROLE_ADMIN, ROLE_DEVELOPER],
        "commit":     [ROLE_ADMIN, ROLE_DEVELOPER],
    },
    # ── Review sessions ─────────────────────────────────────────────────
    "review": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "create":     [ROLE_ADMIN, ROLE_REVIEWER],
        "approve":    [ROLE_ADMIN, ROLE_REVIEWER, ROLE_QUALITY_MANAGER],
        "reject":     [ROLE_ADMIN, ROLE_REVIEWER, ROLE_QUALITY_MANAGER],
        "comment":    [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER],
    },
    # ── Evidence ────────────────────────────────────────────────────────
    "evidence": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "upload":     [ROLE_ADMIN, ROLE_DEVELOPER],
        "delete":     [ROLE_ADMIN],
        "export":     [ROLE_ADMIN, ROLE_REVIEWER, ROLE_AUDITOR, ROLE_QUALITY_MANAGER],
    },
    # ── Audit logs ──────────────────────────────────────────────────────
    "audit": {
        "view":       [ROLE_ADMIN, ROLE_AUDITOR, ROLE_QUALITY_MANAGER],
        "export":     [ROLE_ADMIN, ROLE_AUDITOR, ROLE_QUALITY_MANAGER],
    },
    # ── Billing ─────────────────────────────────────────────────────────
    "billing": {
        "view":       [ROLE_ADMIN, ROLE_AUDITOR],
        "upgrade":    [ROLE_ADMIN],
        "cancel":     [ROLE_ADMIN],
    },
    # ── Settings ────────────────────────────────────────────────────────
    "settings": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "edit":       [ROLE_ADMIN],
    },
    # ── Test / CI results ───────────────────────────────────────────────
    "test": {
        "view":       [ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER, ROLE_AUDITOR,
                       ROLE_VIEWER, ROLE_QUALITY_MANAGER],
        "run":        [ROLE_ADMIN, ROLE_DEVELOPER],
        "upload":     [ROLE_ADMIN, ROLE_DEVELOPER],
    },
}


# ── Role class ──────────────────────────────────────────────────────────────

class Role:
    """Represents a role with its permissions."""

    def __init__(self, name: str):
        if name not in ALL_ROLES:
            raise ValueError(f"Unknown role: {name}. Valid: {ALL_ROLES}")
        self.name = name
        self.label = ROLE_LABELS.get(name, name)

    def can(self, resource: str, action: str = "view") -> bool:
        """Check if this role has permission for (resource, action)."""
        resource_perms = PERMISSION_MATRIX.get(resource, {})
        allowed_roles = resource_perms.get(action, [])
        return self.name in allowed_roles

    def __repr__(self) -> str:
        return f"Role({self.name})"


# ── PermissionSet ───────────────────────────────────────────────────────────

class PermissionSet:
    """Holds all permissions for a given role."""

    def __init__(self, role_name: str):
        self.role = Role(role_name)

    def can(self, resource: str, action: str = "view") -> bool:
        return self.role.can(resource, action)

    def resources(self) -> list[str]:
        """List all resources this role can access."""
        accessible = []
        for resource, actions in PERMISSION_MATRIX.items():
            for action, roles in actions.items():
                if self.role.name in roles:
                    accessible.append(resource)
                    break
        return accessible

    def to_dict(self) -> dict:
        """Return a human-readable permission dict."""
        perms = {}
        for resource, actions in PERMISSION_MATRIX.items():
            for action, roles in actions.items():
                if self.role.name in roles:
                    perms.setdefault(resource, []).append(action)
        return perms


# ── API Middleware ──────────────────────────────────────────────────────────

def get_role_from_user_info(user_info: Optional[dict]) -> str:
    """Extract the permission-tier string from decoded user info.

    Org roles are mapped to permission tiers via the authoritative contract
    (yuleosh.rbac.role_contract.ROLE_TO_TIER). Legacy 'member' maps to
    'developer'; unknown/legacy roles fall back to 'developer'.
    """
    if not user_info:
        return ROLE_AUDITOR  # Lowest access when unauthenticated
    role = user_info.get("role", "developer")
    # 懒导入避免与 role_contract 的循环依赖（role_contract 顶部导入 model 的 ROLE_* 常量）。
    from yuleosh.rbac.role_contract import ROLE_TO_TIER
    return ROLE_TO_TIER.get(role, ROLE_DEVELOPER)


def check_role(user_info: Optional[dict], required_resource: str,
               required_action: str = "view") -> bool:
    """Check if the user's role has permission for the given resource/action.

    Args:
        user_info: Result from get_session_user() or similar.
        required_resource: Resource name from PERMISSION_MATRIX.
        required_action: Action from PERMISSION_MATRIX (default: "view").

    Returns:
        True if the user has permission, False otherwise.
    """
    role_name = get_role_from_user_info(user_info)
    role = Role(role_name)
    has_perm = role.can(required_resource, required_action)
    if not has_perm:
        logger.warning(
            "RBAC DENIED: role=%s resource=%s action=%s user=%s",
            role_name, required_resource, required_action,
            user_info.get("email", "?") if user_info else "?",
        )
    return has_perm


def require_role(required_resource: str, required_action: str = "view"):
    """Decorator: require permission to access a route handler.

    Usage:
        @require_role("pipeline", "run")
        def handle_run_pipeline(handler, path):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(handler, *args, **kwargs):
            # Cookie-aware session resolution (SHALL-T1.4): Bearer OR
            # yuleosh_at access cookie — mirror auth_extended.resolve_session.
            from yuleosh.ui.auth_extended import resolve_session
            user_info = resolve_session(handler)

            if not check_role(user_info, required_resource, required_action):
                from yuleosh.ui.routes.http_response import _add_cors_header, _send_security_headers

                handler.send_response(403)
                handler.send_header("Content-Type", "application/json; charset=utf-8")
                body = json.dumps({
                    "ok": False,
                    "error": f"Insufficient permissions. Required: {required_resource}/{required_action}",
                }).encode()
                handler.send_header("Content-Length", str(len(body)))
                _add_cors_header(handler)
                _send_security_headers(handler)
                handler.end_headers()
                handler.wfile.write(body)
                return

            return func(handler, *args, **kwargs)
        return wrapper
    return decorator
