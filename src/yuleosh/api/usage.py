#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Per-user usage & org LLM model config API (v9, 2026-08-30).

Endpoints:
    GET  /api/v1/me/usage        — current user's usage summary
                                    (pipeline runs / LLM calls / tokens / cost /
                                     current model). Org-scoped via current_user.
    GET  /api/v1/org/llm-config   — org's pinned LLM provider/model
    PUT  /api/v1/org/llm-config   — update org's pinned LLM provider/model

All routes are org-scoped to the authenticated user (current_user.org_id) and
fail closed (403) when no org context is present.
"""

import logging
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth
from yuleosh.store import Store

log = logging.getLogger("api.usage")


@require_auth
def handle_me(method: str, path_tail: str, body: Optional[dict], query: dict,
              handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """GET /api/v1/me/usage — current user usage summary for the cockpit panel.

    Sub-resource dispatcher for /api/v1/me/* — only handles the `usage`
    sub-path; everything else is forwarded to ``yuleosh.api.me.handle_me``
    (account info / account deletion).
    """
    sub = (path_tail or "").strip("/")
    if sub != "usage":
        # Delegate other /me/ sub-resources (e.g. /me/account) to the
        # dedicated me handler.  This avoids registering a second route
        # and keeps the resource key ("me") stable in router.py.
        from .me import handle_me as _me_handle
        return _me_handle(method, path_tail, body, query, handler=handler, **kwargs)

    current_user = kwargs.get("current_user") or {}
    org_id = current_user.get("org_id")
    if org_id is None:
        return json_error("无法识别当前用户组织 (org_id 缺失)", 403)
    if method != "GET":
        return json_error(f"不支持的方法: {method}", 405)

    user_id = current_user.get("user_id")
    store = Store()
    summary = store.get_user_usage_summary(org_id, user_id)
    summary["org_id"] = org_id
    summary["email"] = current_user.get("email") or ""
    return json_ok(summary)


@require_auth
def handle_org(method: str, path_tail: str, body: Optional[dict], query: dict,
               handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """GET/PUT /api/v1/org/llm-config — org-pinned LLM provider/model."""
    current_user = kwargs.get("current_user") or {}
    org_id = current_user.get("org_id")
    if org_id is None:
        return json_error("无法识别当前用户组织 (org_id 缺失)", 403)

    if path_tail != "llm-config":
        return json_error(f"Unknown org sub-path: {path_tail}", 404)

    store = Store()

    if method == "GET":
        return json_ok(store.get_org_llm_config(org_id))

    if method == "PUT":
        provider = (body or {}).get("provider")
        model = (body or {}).get("model")
        # Accept explicit "system"/"default" sentinels as "unset" (NULL).
        if provider in (None, "", "system", "default"):
            provider = None
        if model in (None, "", "system", "default"):
            model = None
        cfg = store.set_org_llm_config(org_id, provider, model)
        return json_ok(cfg)

    return json_error(f"不支持的方法: {method}", 405)
