# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH REST API — current user account management (me).

Mounted at /api/v1/me/ in the REST API router.

Endpoints:
    GET    /api/v1/me/account       — 当前登录账户的完整信息（id/email/role/组织/status 等）
    DELETE /api/v1/me/account       — 注销当前账户（软注销 + 清 session + 审计）

所有路由走 cookie/Bearer 鉴权（@require_auth）和数据级 org_id 隔离。
"""

import logging
import os
from datetime import datetime
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth
from yuleosh.audit.model import AuditLog
from yuleosh.ui.auth_extended import _verify_password
from yuleosh.store import Store

log = logging.getLogger("api.me")

# 软注销要校验的固定确认字符串。前端必须把字符串原文展示给用户输入。
# 用一串读起来语义明确又不太容易误打的话（前后各 6 个连字符强调），避免脚本/宏替换误触。
DELETE_CONFIRMATION_CODE = "DELETE-MY-ACCOUNT"


@require_auth
def handle_me(method: str, path_tail: str, body: Optional[dict], query: dict,
              handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Route /api/v1/me/* requests (current user account management)."""
    current_user = kwargs.get("current_user") or {}
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    # path_tail examples: "" (no trailing), "account", "account/anything"
    sub = (path_tail or "").strip("/")
    if not sub or sub == "account":
        # Treat "" and "account" both as the /me/account endpoint.
        if method == "GET":
            return _get_account(current_user)
        if method == "DELETE":
            return _delete_account(current_user, body or {})
        return json_error(f"不支持的方法: {method}", 405)

    return json_error(f"Unknown me sub-path: {sub}", 404)


# ─────────────────────────────────────────────────────────────────────────
# GET /api/v1/me/account
# ─────────────────────────────────────────────────────────────────────────

def _get_account(current_user: dict) -> tuple:
    """Return the full account profile for the current user."""
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")

    if user_id is None or org_id is None:
        return json_error("无法识别当前用户", 403)

    store = Store()
    user = store.get_user_by_id(user_id)
    org = store.get_organization_by_id(org_id)
    if not user or not org:
        return json_error("用户或组织不存在", 404)

    # Count of still-active sessions for this user (best-effort, cheap COUNT).
    try:
        cur = store.conn.execute(
            "SELECT COUNT(*) AS c FROM sessions WHERE user_id=? AND expires_at > datetime('now')",
            (user_id,),
        )
        active_sessions = cur.fetchone()["c"]
    except Exception:
        active_sessions = None  # do not block the response on this ancillary

    # Serialize created_at → ISO string (sqlite stores it as TEXT already)
    created_at = user.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        try:
            created_at = str(created_at)
        except Exception:
            created_at = None

    return json_ok({
        "user": {
            "id": user["id"],
            "email": user.get("email"),
            "role": user.get("role"),
            "status": user.get("status") or "active",
            "created_at": created_at,
        },
        "org": {
            "id": org["id"],
            "name": org.get("name"),
            "slug": org.get("slug"),
        },
        "active_sessions": active_sessions,
    })


# ─────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/me/account
# ─────────────────────────────────────────────────────────────────────────

def _delete_account(current_user: dict, body: dict) -> tuple:
    """Soft-delete the current user account.

    Validation:
      * confirmation_code must equal DELETE_CONFIRMATION_CODE  (the "额外的码")
      * password must match the current user's stored bcrypt hash

    Effects:
      * UPDATE users SET status='deleted' WHERE id=?
      * DELETE FROM sessions WHERE user_id=?   (invalidate all sessions for this user)
      * Audit event "auth.account.delete" with actor=current_user, target=user:<id>
    """
    user_id = current_user.get("user_id")
    org_id = current_user.get("org_id")
    if user_id is None or org_id is None:
        return json_error("无法识别当前用户", 403)

    # 本地免登录模式下 current_user["user_id"]="local-dev"，是注入的 stub user。
    # 真删它会破坏演示账户，拒掉。
    if user_id == "local-dev":
        return json_error(
            "本地演示模式不支持注销账户；请在开启 AUTH_ENABLED 后的真实环境使用。",
            400,
        )

    confirmation_code = (body.get("confirmation_code") or "").strip()
    password = body.get("password") or ""

    if confirmation_code != DELETE_CONFIRMATION_CODE:
        return json_error(
            f"确认串不正确，必须为：{DELETE_CONFIRMATION_CODE}",
            400,
        )
    if not password:
        return json_error("需要输入当前登录密码以二次确认", 400)

    store = Store()
    user = store.get_user_by_id(user_id)
    if not user:
        return json_error("用户不存在", 404)

    pw_hash = user.get("password_hash") or ""
    if not pw_hash or not _verify_password(password, pw_hash):
        # 故意含糊错误信息，避免泄漏字段命中侧信道。
        return json_error("确认串或密码不正确", 400)

    # 已是 deleted 状态 → 幂等返回（避免重复扣减 session 行）
    prev_status = user.get("status") or "active"

    try:
        store.conn.execute(
            "UPDATE users SET status='deleted' WHERE id=?",
            (user_id,),
        )
        store.conn.execute(
            "DELETE FROM sessions WHERE user_id=?",
            (user_id,),
        )
        store.conn.commit()
    except Exception as e:
        log.error("account delete failed: %s", e)
        store.conn.rollback()
        return json_error("注销失败，请稍后再试", 500)

    # 审计事件：写到全局共享的 yuleosh audit 链中。
    # 不影响业务，但事后可证、可定位、可抵赖抵抗。
    try:
        _audit_root = os.environ.get("YULEOSH_AUDIT_ROOT")
        audit = AuditLog(data_root=_audit_root)
        audit.record(
            actor=f"user:{user_id}",
            action="auth.account.delete",
            target=f"user:{user_id}",
            tenant=f"org:{org_id}",
            detail={
                "previous_status": prev_status,
                "new_status": "deleted",
                "deleted_at": datetime.utcnow().isoformat() + "Z",
            },
        )
    except Exception as e:  # 审计失败不应阻塞主流程
        log.warning("audit.record for account delete failed: %s", e)

    log.info("user %s soft-deleted (prev_status=%s)", user_id, prev_status)
    return json_ok({
        "status": "deleted",
        "user_id": user_id,
        "note": "已注销。已清除该用户所有会话。",
    })
