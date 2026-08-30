# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH REST API — Middleware: JWT auth requirement for handler injection.

Provides `require_auth` decorator to protect API endpoints behind JWT bearer
token validation, injecting current user info into the handler's kwargs.
"""

import functools
import logging
from typing import Optional

from . import json_error
from yuleosh.ui.auth import AUTH_ENABLED  # 与 server._check_auth 同步：本地免登录开关
from yuleosh.ui.auth_extended import (
    JWT_SECRET as _JWT_SECRET,          # A1: unified source (SHALL-A1.1)
    JWT_ALGORITHM as _JWT_ALGORITHM,    # A1: unified source
    verify_token,                        # A1: unified verify (SHALL-A1.2)
)

logger = logging.getLogger("yuleosh.api.middleware")


def _apply_org_llm_override(user: dict) -> None:
    """Pin the org's LLM provider/model for the current request (v9).

    Reads the tenant's stored llm provider/model from the store and pushes it
    into a request-scoped ContextVar consumed by LLMClient.resolve_config.
    Best-effort: any failure degrades to the system default without breaking
    the request.
    """
    try:
        from yuleosh.llm.client import set_org_llm_override
        org_id = user.get("org_id")
        if not org_id:
            return
        from yuleosh.store import Store
        cfg = Store().get_org_llm_config(org_id)
        set_org_llm_override(cfg.get("provider"), cfg.get("model"))
    except Exception as e:  # noqa: BLE001
        logger.debug("org llm override skipped: %s", e)


def _resolve_local_dev_user() -> dict:
    """AUTH_DISABLED 本地开发模式：构造一个 admin 用户注入，使依赖
    ``current_user.org_id`` 的路由（如 dashboard/projects）也能正常工作。

    优先取 ``demo`` 组织；取不到时 org_id 留空（由路由自身决定行为）。
    仅在本地免登录模式下调用，任何异常都降级而非崩溃。
    """
    org_id = None
    try:
        from yuleosh.store import Store
        store = Store()
        org = store.get_organization("demo")
        if org:
            org_id = org.get("id")
    except Exception as e:  # 本地模式不应因 store 问题中断
        logger.debug("local-dev user org resolution failed: %s", e)
    return {
        "user_id": "local-dev",
        "org_id": org_id,
        "email": "local-dev@yuleosh.local",
        "role": "admin",
    }


# JWT secret — single source of truth (v3.8.0 A1): the value comes from
# ui/auth_extended.py.JWT_SECRET, never re-read from the environment here.
# ``_decode_token`` below is a THIN DELEGATION to the unified decoder —
# middleware must not implement JWT verification itself (SHALL-A1.2).
_JWT_ALGORITHM = "HS256"


def _decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None.

    A1 (v3.8.0): thin delegation to the unified decoder in
    ``ui/auth_extended.py`` — kept as a named wrapper so existing callers
    (and tests) keep a stable import surface, but the implementation is
    single-sourced.
    """
    from yuleosh.ui.auth_extended import _decode_token as _unified_decode
    return _unified_decode(token)


def _extract_token(headers) -> Optional[str]:
    """Extract Bearer token from request headers, falling back to the
    access cookie (T1 v3.9.0, SHALL-T1.4).

    Priority: ``Authorization: Bearer <token>`` first (API clients,
    desktop app); when NO Authorization header is present, the
    ``yuleosh_at`` access cookie is read (browser cookie mode).  An
    Authorization header that is present but not Bearer fails closed
    (no cookie fallback) — same token verdict via either channel.
    """
    if callable(getattr(headers, "get", None)):
        auth = headers.get("Authorization", "")
    elif isinstance(headers, dict):
        auth = headers.get("Authorization", "")
    else:
        return None

    if auth:
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

    # T1 (v3.9.0): no Authorization header → cookie fallback.
    from yuleosh.ui.auth_cookies import ACCESS_COOKIE_NAME, read_cookie_value
    return read_cookie_value(headers, ACCESS_COOKIE_NAME)


def require_auth(handler):
    """Decorator: enforces JWT auth on a route handler.

    Usage:
        @require_auth
        def handle_something(method, path_tail, body, query, **kwargs):
            # kwargs will include:
            #   current_user: dict with user_id, org_id, email, role
            pass

    On auth failure, the decorator short-circuits with a 401 JSON error.
    """
    @functools.wraps(handler)
    def wrapper(method: str, path_tail: str, body: dict, query: dict,
                **kwargs):
        # 与 server._check_auth 对称：本地免登录模式（YULEOSH_AUTH_DISABLED=1）
        # 直接注入本地 admin 用户并放行，使 /api/v1/* 也免认证。
        if not AUTH_ENABLED:
            kwargs["current_user"] = _resolve_local_dev_user()
            _apply_org_llm_override(kwargs["current_user"])
            return handler(method=method, path_tail=path_tail, body=body,
                           query=query, **kwargs)

        # Extract headers from the handler object
        http_handler = kwargs.get("handler")
        if http_handler is None:
            # Fail closed (P0): never fabricate an authenticated user when no
            # HTTP handler context is available.  The only sanctioned bypass
            # is an explicit current_user kwarg, which is unreachable from
            # HTTP (router.dispatch only ever passes handler=).
            injected_user = kwargs.get("current_user")
            if injected_user is not None:
                return handler(method=method, path_tail=path_tail, body=body,
                               query=query, **kwargs)
            return json_error(
                "Authorization header with Bearer token required", 401)

        token = _extract_token(getattr(http_handler, "headers", {}))
        if not token:
            return json_error("Authorization header with Bearer token required", 401)

        # ── A1 (v3.8.0): unified verify — same function as the ui side ──
        #   (ui/auth_extended.verify_token).  Accepts BOTH payload formats
        #   (sub/org from the frontend chain, user_id/org_id from the v1
        #   API) and performs decode + session check + user check in ONE
        #   place.  The middleware no longer re-implements JWT verification
        #   (SHALL-A1.2); verdicts match v3.7.0 exactly.
        user = verify_token(token)
        if not user:
            return json_error("Invalid or expired token", 401)

        # Inject current user into kwargs
        kwargs["current_user"] = {
            "user_id": user["user_id"],
            "org_id": user["org_id"],
            "email": user.get("email", ""),
            "role": user.get("role", "member"),
        }
        _apply_org_llm_override(kwargs["current_user"])

        return handler(method=method, path_tail=path_tail, body=body,
                       query=query, **kwargs)

    return wrapper
