# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Billing & usage API route handlers (SAAS-5).

Endpoints:
    GET  /api/v1/billing/usage   — Get current usage for user's tenant
    GET  /api/v1/billing/plan    — Get current subscription/plan info
    POST /api/v1/billing/upgrade — Upgrade to a plan (creates Stripe checkout)
"""

import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Optional

from yuleosh.billing.metering import UsageMeter, BillingManager, PLAN_LIMITS, PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE


logger = logging.getLogger("billing.routes")


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


def _get_tenant_slug(user_info: dict) -> str:
    return user_info.get("org_slug", "")


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


# ── GET: Usage ──────────────────────────────────────────────────────────────

def handle_get_usage(handler: BaseHTTPRequestHandler):
    """GET /api/v1/billing/usage — Get current month usage."""
    user = _require_auth(handler)
    if not user:
        return

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "view"):
        _send_json(handler, {"error": "Insufficient permissions"}, 403)
        return

    tenant_slug = _get_tenant_slug(user)
    if not tenant_slug:
        _send_json(handler, {"error": "No organization found"}, 404)
        return

    meter = UsageMeter()
    usage = meter.get_usage_summary(tenant_slug)

    _send_json(handler, usage)


# ── GET: Plan info ─────────────────────────────────────────────────────────

def handle_get_plan(handler: BaseHTTPRequestHandler):
    """GET /api/v1/billing/plan — Get current plan and available plans."""
    user = _require_auth(handler)
    if not user:
        return

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "view"):
        _send_json(handler, {"error": "Insufficient permissions"}, 403)
        return

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

    _send_json(handler, {
        "tenant": tenant_slug,
        "current_plan": subscription.get("plan", PLAN_FREE),
        "current_period_end": subscription.get("current_period_end", ""),
        "status": subscription.get("status", "active"),
        "mock_mode": subscription.get("mock", True),
        "available_plans": plans,
    })


# ── POST: Upgrade ───────────────────────────────────────────────────────────

def handle_upgrade_plan(handler: BaseHTTPRequestHandler):
    """POST /api/v1/billing/upgrade — Upgrade tenant plan.

    Body:
        {plan: "pro"|"enterprise", success_url: "...", cancel_url: "..."}
    """
    user = _require_auth(handler)
    if not user:
        return

    from yuleosh.rbac import check_role
    if not check_role(user, "billing", "upgrade"):
        _send_json(handler, {"error": "Insufficient permissions. Admin role required."}, 403)
        return

    body = _read_body(handler)
    plan = body.get("plan", "").strip().lower()

    if plan not in [PLAN_PRO, PLAN_ENTERPRISE]:
        _send_json(handler, {"error": f"Invalid plan. Choose 'pro' or 'enterprise'"}, 400)
        return

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
        _send_json(handler, result, 400)
    else:
        _send_json(handler, result)
