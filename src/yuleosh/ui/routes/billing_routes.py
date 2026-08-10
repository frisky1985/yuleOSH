# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Billing & usage API route handlers (SAAS-5).

Endpoints:
    GET  /api/v1/billing/usage   — Get current usage for user's tenant
    GET  /api/v1/billing/plan    — Get current subscription/plan info
    POST /api/v1/billing/upgrade — Upgrade to a plan (creates Stripe checkout)

A3 (v3.8.0): migrated to the new-style router signature
``fn(method, path_tail, body, query, handler) -> tuple``; responses are
plain dicts identical to the legacy handlers (SHALL-A3.4).
"""

import logging
from typing import Optional

from yuleosh.billing.metering import (
    UsageMeter, BillingManager, PLAN_LIMITS, PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE,
)
from yuleosh.ui.auth_extended import get_session_user


logger = logging.getLogger("billing.routes")


def _get_token(handler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _require_auth(handler) -> Optional[dict]:
    token = _get_token(handler)
    if not token:
        return None
    return get_session_user(token)


def _auth_error(handler) -> tuple:
    """401 — exact legacy body for a missing vs invalid session."""
    if not _get_token(handler):
        return {"error": "Authorization required"}, 401
    return {"error": "Invalid session"}, 401


def _get_tenant_slug(user_info: dict) -> str:
    return user_info.get("org_slug", "")


def handle_billing(method: str, path_tail: str, body: dict, query: dict,
                   handler=None) -> tuple:
    """Dispatcher for /api/v1/billing/* (A3, B7).

    path_tail: "usage" | "plan" | "upgrade"
    """
    sub = (path_tail or "").strip().rstrip("/")
    if method == "GET" and sub == "usage":
        return handle_get_usage(method, path_tail, body, query, handler)
    if method == "GET" and sub == "plan":
        return handle_get_plan(method, path_tail, body, query, handler)
    if method == "POST" and sub == "upgrade":
        return handle_upgrade_plan(method, path_tail, body, query, handler)
    return {"error": "Method not allowed"}, 405


# ── GET: Usage ──────────────────────────────────────────────────────────────

def handle_get_usage(method: str, path_tail: str, body: dict, query: dict,
                     handler=None) -> tuple:
    """GET /api/v1/billing/usage — Get current month usage.

    Phase 9 (2026-08-10): dual-source merge — ci_runs/api_calls/storage_mb
    from jsonl UsageMeter (tenant slug) + llm_tokens/pipeline_runs from
    sqlite usage_log (org_id). The slug → org bridge closes the gap that
    previously made LLM consumption invisible on the billing page.
    """
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "view"):
        return {"error": "Insufficient permissions"}, 403

    tenant_slug = _get_tenant_slug(user)
    if not tenant_slug:
        return {"error": "No organization found"}, 404

    # ── Source 1: jsonl UsageMeter (ci_runs / api_calls / storage_mb) ──
    meter = UsageMeter()
    usage = meter.get_usage_summary(tenant_slug)
    usage_data = usage.get("usage", {})
    limits = usage.get("limits", {})

    # ── Source 2: sqlite usage_log via slug → org bridge (llm_tokens) ──
    llm_tokens_used = 0
    pipeline_runs_used = 0
    project_count = 0
    user_count = 0
    llm_tokens_limit = 0
    by_user: list[dict] = []
    from yuleosh.store import Store
    org = None
    try:
        store = Store()
        org = store.get_organization(tenant_slug)
        if org:
            org_usage = store.get_monthly_usage(org["id"])
            llm_tokens_used = org_usage.get("llm_tokens", 0) or 0
            pipeline_runs_used = org_usage.get("pipeline_runs", 0) or 0
            project_count = org_usage.get("project_count", 0) or 0
            user_count = store.count_org_users(org["id"])
            by_user = store.get_monthly_usage_by_user(org["id"])
            # LLM token quota from TIERS (tier-aware), merged into limits.
            from yuleosh.usage.metering import TIERS
            _tier = org.get("tier", "community") or "community"
            _cfg = TIERS.get(_tier, TIERS.get("community", {}))
            llm_tokens_limit = _cfg.get("max_llm_tokens", 0) or 0
    except Exception as e:  # noqa: BLE001 — billing read must never 500
        logger.warning("billing usage sqlite merge failed: %s", e)

    # ── Merge: flat contract (frontend expects usage.ci_runs style keys) ──
    merged_limits = dict(limits)
    if llm_tokens_limit:
        merged_limits["llm_tokens"] = llm_tokens_limit
    merged = {
        "tenant": usage.get("tenant", tenant_slug),
        "plan": usage.get("plan", "free"),
        "period": usage.get("period", ""),
        "role": user.get("role", "member"),
        "usage": {
            "ci_runs": usage_data.get("ci_runs", 0),
            "api_calls": usage_data.get("api_calls", 0),
            "storage_mb": usage_data.get("storage_mb", 0),
            "llm_tokens": llm_tokens_used,
            "pipeline_runs": pipeline_runs_used,
            "projects": project_count,
            "users": user_count,
        },
        "limits": merged_limits,
        "by_user": by_user,
        "within_limits": usage.get("within_limits", True),
    }
    return merged, 200


# ── GET: Plan info ──────────────────────────────────────────────────────────

def handle_get_plan(method: str, path_tail: str, body: dict, query: dict,
                    handler=None) -> tuple:
    """GET /api/v1/billing/plan — Get current plan and available plans."""
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "view"):
        return {"error": "Insufficient permissions"}, 403

    tenant_slug = _get_tenant_slug(user)
    billing = BillingManager()
    subscription = billing.get_subscription(tenant_slug)

    # Available plans
    plans = []
    for plan_id in [PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE]:
        limits = PLAN_LIMITS[plan_id]
        plans.append({
            "id": plan_id,
            "label": limits["label"],
            "price_monthly_cents": limits["price_monthly_cents"],
            "limits": {
                "max_projects": limits["max_projects"],
                "max_users": limits["max_users"],
                "max_ci_runs": limits["max_ci_runs"],
                "max_storage_mb": limits["max_storage_mb"],
            },
        })

    return {
        "tenant": tenant_slug,
        "current_plan": subscription.get("plan", PLAN_FREE),
        "current_period_end": subscription.get("current_period_end", ""),
        "status": subscription.get("status", "active"),
        "mock_mode": subscription.get("mock", True),
        "available_plans": plans,
    }, 200


# ── POST: Upgrade ───────────────────────────────────────────────────────────

def handle_upgrade_plan(method: str, path_tail: str, body: dict, query: dict,
                        handler=None) -> tuple:
    """POST /api/v1/billing/upgrade — Upgrade tenant plan.

    Body:
        {plan: "pro"|"enterprise", success_url: "...", cancel_url: "..."}
    """
    user = _require_auth(handler)
    if not user:
        return _auth_error(handler)

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "upgrade"):
        return {"error": "Insufficient permissions. Admin role required."}, 403

    plan = body.get("plan", "").strip().lower()

    if plan not in [PLAN_PRO, PLAN_ENTERPRISE]:
        return {"error": f"Invalid plan. Choose 'pro' or 'enterprise'"}, 400

    tenant_slug = _get_tenant_slug(user)
    success_url = body.get("success_url", "/billing")
    cancel_url = body.get("cancel_url", "/billing")

    billing = BillingManager()
    result = billing.create_checkout_session(
        tenant=tenant_slug,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    if "error" in result:
        return result, 400
    return result, 200
