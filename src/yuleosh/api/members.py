#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Role management API — mounted at /api/v1/members/.

Module ① of the dashboard design (docs/architecture/dashboard-design.md):
org-scoped member & role management on top of the existing store tables
(organizations / users / org_projects).

Endpoints:
    GET   /api/v1/members            — org member list (store users table, org-scoped)
    POST  /api/v1/members/invite     — invite a member {email, role}
    PATCH /api/v1/members/{id}       — change a member's role {role}
    GET   /api/v1/members/roles      — static role × module permission matrix
                                         (design doc chapter 4: 6 roles × 8 modules)

All routes are org-scoped to the authenticated user (current_user.org_id).
When the auth context carries no org the handler fails closed with 403 —
never fabricate members or fall back to demo data.
"""

import logging
import re
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.members")

# Role vocabulary (design doc chapter 3 / module ①)
VALID_ROLES = ("owner", "admin", "quality_manager", "architect", "developer", "viewer")

# Roles that may administer the 角色管理 module (design doc chapter 4: ✅ only)
ADMIN_ROLES = ("owner", "admin")

# 8 modules from the design doc chapter 4 permission matrix
PERMISSION_MODULES = (
    "数据座舱",
    "需求管理",
    "流水线管理",
    "阶段产出物",
    "测试用例",
    "设备管理",
    "测试日志",
    "角色管理",
)

# ── Static permission matrix (design doc chapter 4) ──────────────────────
# ✅ = full · 👁 = read · ❌ = none
_PERMISSION_MATRIX = {
    "owner": {
        "数据座舱": "full", "需求管理": "full", "流水线管理": "full",
        "阶段产出物": "full", "测试用例": "full", "设备管理": "full",
        "测试日志": "full", "角色管理": "full",
    },
    "admin": {
        "数据座舱": "full", "需求管理": "full", "流水线管理": "full",
        "阶段产出物": "full", "测试用例": "full", "设备管理": "full",
        "测试日志": "full", "角色管理": "full",
    },
    "quality_manager": {
        "数据座舱": "full", "需求管理": "full", "流水线管理": "full",
        "阶段产出物": "full", "测试用例": "full", "设备管理": "read",
        "测试日志": "full", "角色管理": "none",
    },
    "architect": {
        "数据座舱": "full", "需求管理": "full", "流水线管理": "full",
        "阶段产出物": "full", "测试用例": "full", "设备管理": "read",
        "测试日志": "full", "角色管理": "none",
    },
    "developer": {
        "数据座舱": "full", "需求管理": "full", "流水线管理": "full",
        "阶段产出物": "full", "测试用例": "full", "设备管理": "read",
        "测试日志": "full", "角色管理": "none",
    },
    "viewer": {
        "数据座舱": "full", "需求管理": "read", "流水线管理": "read",
        "阶段产出物": "read", "测试用例": "read", "设备管理": "read",
        "测试日志": "read", "角色管理": "none",
    },
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _q(query: dict, key: str, default: Any = None) -> Any:
    """Query param accessor — router passes lists (parse_qs), tests pass scalars."""
    val = query.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


@require_auth
def handle_members(method: str, path_tail: str, body: dict, query: dict,
                   handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Route /api/v1/members/... requests (role management).

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth
    (user_id / org_id / email / role).
    """
    current_user = kwargs.get("current_user") or {}
    org_id = current_user.get("org_id")

    # All member routes are org-scoped — fail closed (403) when the auth
    # context carries no org. Never serve cross-org or fabricated data.
    if org_id is None:
        return json_error("无法识别当前用户组织 (org_id 缺失)", 403)

    if method == "GET" and path_tail in ("", "list"):
        return _list_members(org_id, query)
    if method == "POST" and path_tail == "invite":
        return _invite_member(org_id, body, current_user)
    if method == "GET" and path_tail == "roles":
        return _roles_matrix(current_user)
    if method == "GET" and path_tail == "roles/audit":
        return _roles_audit(current_user)
    if method == "PATCH" and path_tail == "roles":
        return _update_roles(current_user, body)
    if method == "PATCH" and path_tail and "/" not in path_tail:
        return _update_role(org_id, path_tail, body, current_user)
    if method == "DELETE" and path_tail and "/" not in path_tail:
        return _delete_member(org_id, path_tail, current_user)

    return json_error(f"Unknown members sub-path or method: {method} {path_tail}", 404)


def _list_members(org_id: Any, query: dict) -> tuple[dict, int]:
    """GET /api/v1/members — org member list from the store users table.

    Real data only, scoped to the authenticated user's org. An explicit
    ``org_id`` query param pointing at another org is rejected (403).
    """
    requested = _q(query, "org_id")
    if requested is not None and str(requested) != str(org_id):
        return json_error("无权查看其他组织的成员", 403)

    try:
        from yuleosh.store import Store
        store = Store()
        members = store.list_users(org_id)
    except Exception as e:
        log.error("members list failed: %s", e)
        return json_error("成员数据加载失败，请稍后重试", 503)

    return json_ok({"members": members, "count": len(members), "note": None})


def _invite_member(org_id: Any, body: dict, current_user: dict) -> tuple[dict, int]:
    """POST /api/v1/members/invite — invite {email, role} into the org.

    Inserts a row in the store users table (password_hash left NULL — the
    invitee sets a password later). Role is validated against VALID_ROLES.
    """
    if current_user.get("role") not in ADMIN_ROLES:
        return json_error("仅 Owner/Admin 可以邀请成员", 403)

    email = str(body.get("email") or "").strip().lower()
    role = str(body.get("role") or "").strip()

    if not _EMAIL_RE.match(email):
        return json_error("无效的邮箱地址", 400)
    if role not in VALID_ROLES:
        return json_error(f"非法角色: {role}，可选: {', '.join(VALID_ROLES)}", 400)

    try:
        from yuleosh.store import Store
        store = Store()
        member = store.create_user(org_id, email, role, password_hash=None, status="pending")
    except Exception as e:
        log.error("member invite failed: %s", e)
        if "unique" in str(e).lower():
            return json_error(f"成员已存在: {email}", 409)
        return json_error("成员邀请失败，请稍后重试", 503)

    return json_ok({
        "member": {
            "id": member["id"],
            "email": member["email"],
            "role": member["role"],
            "created_at": member["created_at"],
        }
    })


def _update_role(org_id: Any, user_id_str: str, body: dict,
                 current_user: dict) -> tuple[dict, int]:
    """PATCH /api/v1/members/{id} — change a member's role {role}.

    Org-scoped: the target user must exist AND belong to the caller's org —
    a user id from another org resolves to 404 (no cross-org mutation).
    """
    if current_user.get("role") not in ADMIN_ROLES:
        return json_error("仅 Owner/Admin 可以修改成员角色", 403)

    role = str(body.get("role") or "").strip()
    if role not in VALID_ROLES:
        return json_error(f"非法角色: {role}，可选: {', '.join(VALID_ROLES)}", 400)
    if not user_id_str.isdigit():
        return json_error(f"无效的用户 ID: {user_id_str}", 400)

    try:
        from yuleosh.store import Store
        store = Store()
        user = store.get_user_by_id(int(user_id_str))
        if user is None or user.get("org_id") != org_id:
            return json_error(f"成员不存在: {user_id_str}", 404)
        store.conn.execute("UPDATE users SET role=? WHERE id=?", (role, user["id"]))
        store.conn.commit()
        updated = store.get_user_by_id(user["id"]) or user
    except Exception as e:
        log.error("member role update failed: %s", e)
        return json_error("角色更新失败，请稍后重试", 503)

    return json_ok({
        "member": {
            "id": updated["id"],
            "email": updated["email"],
            "role": updated["role"],
            "created_at": updated["created_at"],
        }
    })


def _delete_member(org_id: Any, user_id_str: str, current_user: dict) -> tuple[dict, int]:
    """DELETE /api/v1/members/{id} — 移除一名成员（仅 Owner/Admin）。

    Org-scoped 与防自删：调用者不能移除自己，避免组织失去管理员。
    """
    if current_user.get("role") not in ADMIN_ROLES:
        return json_error("仅 Owner/Admin 可以移除成员", 403)
    if not user_id_str.isdigit():
        return json_error(f"无效的用户 ID: {user_id_str}", 400)

    caller_id = str(current_user.get("user_id") or current_user.get("id") or "")
    if str(user_id_str) == caller_id:
        return json_error("不能移除你自己", 400)

    try:
        from yuleosh.store import Store
        store = Store()
        user = store.get_user_by_id(int(user_id_str))
        if user is None or user.get("org_id") != org_id:
            return json_error(f"成员不存在: {user_id_str}", 404)
        store.conn.execute(
            "DELETE FROM users WHERE id=? AND org_id=?", (user["id"], org_id)
        )
        store.conn.commit()
    except Exception as e:
        log.error("member delete failed: %s", e)
        return json_error("成员移除失败，请稍后重试", 503)

    return json_ok({"deleted": int(user_id_str)})


def _default_matrix() -> dict:
    """Build the design-doc default matrix as {role: {module: level}}.

    Keeps VALID_ROLES / PERMISSION_MODULES ordering for stable rendering.
    """
    return {
        role: {m: _PERMISSION_MATRIX.get(role, {}).get(m, "none") for m in PERMISSION_MODULES}
        for role in VALID_ROLES
    }


def _roles_matrix(current_user: dict) -> tuple[dict, int]:
    """GET /api/v1/members/roles — role × module permission matrix.

    Reads from the persistent role_permissions store; on first read (empty
    table) seeds it with the design-doc defaults so the matrix is always
    populated. ``can_edit`` is True only for Owner/Admin.
    """
    try:
        from yuleosh.store import Store
        store = Store()
        matrix = store.get_role_permissions()
        if not matrix:
            matrix = _default_matrix()
            store.save_role_permissions(matrix)
    except Exception as e:
        log.error("roles matrix load failed: %s", e)
        matrix = _default_matrix()

    roles = []
    for role in VALID_ROLES:
        perms = matrix.get(role, {})
        roles.append({
            "role": role,
            "permissions": {m: perms.get(m, "none") for m in PERMISSION_MODULES},
        })

    can_edit = current_user.get("role") in ADMIN_ROLES
    return json_ok({
        "roles": roles,
        "modules": list(PERMISSION_MODULES),
        "can_edit": bool(can_edit),
    })


def _roles_audit(current_user: dict) -> tuple[dict, int]:
    """GET /api/v1/members/roles/audit — 权限矩阵变更审计日志（T7）。

    返回最近 50 条逐格变更记录（actor / role / module / old→new / 时间），
    按时间倒序。读取失败时降级为空列表而不是 500（看板不因审计日志崩）。
    """
    try:
        from yuleosh.store import Store
        store = Store()
        rows = store.list_permission_audit(limit=50)
    except Exception as e:  # noqa: BLE001 — 审计只读，失败降级为空列表
        log.error("roles audit load failed: %s", e)
        return json_ok({"audit": [], "count": 0, "note": "审计日志暂不可用"})

    return json_ok({"audit": rows, "count": len(rows)})


def _update_roles(current_user: dict, body: dict) -> tuple[dict, int]:
    """PATCH /api/v1/members/roles — update the permission matrix.

    Body (either form accepted):
        {"matrix": {role: {module: level}}}            — full replacement
        {"updates": [{role, module, level}, ...]}      — partial patches
    Server-side enforced: only Owner/Admin may mutate. Levels are validated
    against (full / read / none) and roles/modules against the known vocab.
    """
    if current_user.get("role") not in ADMIN_ROLES:
        return json_error("仅 Owner/Admin 可以编辑权限矩阵", 403)

    # Resolve the incoming change set into a {role: {module: level}} delta.
    delta: dict = {}
    matrix_arg = body.get("matrix")
    updates_arg = body.get("updates")

    if isinstance(matrix_arg, dict):
        for role, perms in matrix_arg.items():
            if role not in VALID_ROLES:
                return json_error(f"非法角色: {role}", 400)
            if not isinstance(perms, dict):
                return json_error(f"角色 {role} 的权限必须是对象", 400)
            for module, level in perms.items():
                if module not in PERMISSION_MODULES:
                    return json_error(f"非法模块: {module}", 400)
                if level not in ("full", "read", "none"):
                    return json_error(f"非法权限级别: {level}（应为 full/read/none）", 400)
                delta.setdefault(role, {})[module] = level
    elif isinstance(updates_arg, list):
        for item in updates_arg:
            role = str(item.get("role") or "")
            module = str(item.get("module") or "")
            level = str(item.get("level") or "")
            if role not in VALID_ROLES:
                return json_error(f"非法角色: {role}", 400)
            if module not in PERMISSION_MODULES:
                return json_error(f"非法模块: {module}", 400)
            if level not in ("full", "read", "none"):
                return json_error(f"非法权限级别: {level}（应为 full/read/none）", 400)
            delta.setdefault(role, {})[module] = level
    else:
        return json_error("请求体需包含 matrix 或 updates 字段", 400)

    if not delta:
        return json_error("未提供任何权限变更", 400)

    try:
        from yuleosh.store import Store
        store = Store()
        # previous = 旧矩阵（审计 diff 基线）
        previous = store.get_role_permissions() or _default_matrix()
        # Merge delta onto the current matrix so partial updates keep the rest.
        current = {r: dict(p) for r, p in previous.items()}
        for role, perms in delta.items():
            current.setdefault(role, {})
            current[role].update(perms)
            # Drop any module not in the vocab (defensive).
            current[role] = {
                m: lv for m, lv in current[role].items() if m in PERMISSION_MODULES
            }
        # 审计：逐格比较 old/new，记录谁在何时改了哪一项（T7）
        actor = current_user.get("email") or str(current_user.get("user_id") or "unknown")
        for role in current:
            for module in PERMISSION_MODULES:
                old_lv = previous.get(role, {}).get(module)
                new_lv = current[role].get(module)
                if new_lv != old_lv:
                    store.add_permission_audit(actor, role, module, old_lv, new_lv)
        store.save_role_permissions(current)
    except Exception as e:
        log.error("roles matrix update failed: %s", e)
        return json_error("权限矩阵更新失败，请稍后重试", 503)

    roles = []
    for role in VALID_ROLES:
        perms = current.get(role, {})
        roles.append({
            "role": role,
            "permissions": {m: perms.get(m, "none") for m in PERMISSION_MODULES},
        })
    return json_ok({
        "roles": roles,
        "modules": list(PERMISSION_MODULES),
        "can_edit": True,
        "updated": sum(len(p) for p in delta.values()),
    })
