# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH REST API — Subscription management (view, upgrade, cancel, webhook).

Mounted at /api/v1/subscription/ in the REST API router.

Integrates with:
  - Stripe Checkout (create_checkout_session)
  - Stripe webhooks (handle_stripe_webhook)
  - Usage metering (get_usage_summary, get_trial_status)
"""

import json
import logging
from datetime import datetime, timedelta

from yuleosh.store import Store
from yuleosh.usage import (
    get_usage_summary,
    get_trial_status,
    is_stripe_configured,
    create_checkout_session,
    handle_stripe_webhook,
    TIERS,
    TRIAL_DAYS,
)
from . import json_ok, json_error

logger = logging.getLogger("yuleosh.api.subscription")

# ---------------------------------------------------------------------------
# Auth token extraction helper
# ---------------------------------------------------------------------------

def _extract_token(headers: dict) -> str:
    """Extract Bearer token from request headers."""
    if callable(getattr(headers, "get", None)):
        auth = headers.get("Authorization", "")
    elif isinstance(headers, dict):
        auth = headers.get("Authorization", "")
    else:
        auth = str(headers) if headers else ""
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


def _get_authenticated_org(headers: dict) -> tuple:
    """Get org_id from JWT token. Returns (org_id, user_id, org_slug) or raises."""
    import jwt as pyjwt
    import os
    import secrets

    token = _extract_token(headers)
    if not token:
        raise PermissionError("Authentication required")

    secret = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        raise PermissionError("Invalid or expired token")

    org_id = payload.get("org_id") or payload.get("org", 0)
    user_id = payload.get("user_id") or int(payload.get("sub", 0))
    email = payload.get("email", "")
    return org_id, user_id, email


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

def handle_subscription(method: str, path_tail: str, body: dict,
                        query: dict, **kwargs) -> tuple:
    """Subscription REST API handler.

    Routes:
        GET  /api/v1/subscription/status     — View subscription + trial + usage
        POST /api/v1/subscription/upgrade    — Create Stripe Checkout session
        POST /api/v1/subscription/cancel     — Cancel subscription
        POST /api/v1/subscription/webhook    — Stripe webhook receiver
    """
    if method == "GET" and (path_tail == "" or path_tail == "status"):
        return _handle_sub_status(kwargs.get("handler"))
    elif method == "POST" and path_tail == "upgrade":
        return _handle_sub_upgrade(body, kwargs.get("handler"))
    elif method == "POST" and path_tail == "cancel":
        return _handle_sub_cancel(body, kwargs.get("handler"))
    elif method == "POST" and path_tail == "webhook":
        return _handle_stripe_webhook(body, kwargs.get("handler"))
    else:
        return json_error(f"Unknown subscription endpoint: {method} /{path_tail}", 404)


# ---------------------------------------------------------------------------
# GET /api/v1/subscription/status
# ---------------------------------------------------------------------------

def _handle_sub_status(handler=None) -> tuple:
    """Get subscription status, trial info, and usage summary.

    Response: {
        tier, tier_name, subscription, trial, usage, trial_days_left,
        plans: [{name, price, ...}]
    }
    """
    if handler is None:
        return json_error("Unauthorized", 401)

    try:
        org_id, user_id, email = _get_authenticated_org(handler.headers)
    except PermissionError as e:
        return json_error(str(e), 401)

    store = Store()
    org = store.get_organization_by_id(org_id)
    if not org:
        return json_error("Organization not found", 404)

    tier = org.get("tier", "community")
    trial = get_trial_status(store, org_id)
    usage = get_usage_summary(store, org_id)
    subscription = store.get_subscription(org_id)

    # Build response
    result = {
        "org_name": org.get("name", ""),
        "org_slug": org.get("slug", ""),
        "tier": tier,
        "tier_name": TIERS.get(tier, {}).get("name", "Unknown"),
        "subscription": {
            "stripe_enabled": is_stripe_configured(),
            "has_subscription": subscription is not None and bool(
                subscription.get("stripe_subscription_id")
            ),
            "status": (subscription or {}).get("status", "none"),
            "current_period_end": (subscription or {}).get("current_period_end", ""),
            "stripe_subscription_id": (subscription or {}).get(
                "stripe_subscription_id", ""
            ),
        },
        "trial": trial,
        "usage": usage.get("usage", {}),
        "plans": [
            {
                "name": "Free",
                "tier": "free",
                "price_monthly": 0,
                "max_projects": 1,
            },
            {
                "name": "Pro",
                "tier": "pro",
                "price_monthly": TIERS.get("pro", {}).get("price_monthly", 299),
            },
            {
                "name": "Enterprise",
                "tier": "enterprise",
                "price_monthly": TIERS.get("enterprise", {}).get(
                    "price_monthly", 2999
                ),
            },
        ],
    }

    return json_ok(result)


# ---------------------------------------------------------------------------
# POST /api/v1/subscription/upgrade
# ---------------------------------------------------------------------------

def _handle_sub_upgrade(body: dict, handler=None) -> tuple:
    """Create a Stripe Checkout session for upgrading.

    Body: {tier: "pro" | "enterprise"}
    Response: {url: "https://checkout.stripe.com/...", session_id: "..."}
    """
    if handler is None:
        return json_error("Unauthorized", 401)

    try:
        org_id, user_id, email = _get_authenticated_org(handler.headers)
    except PermissionError as e:
        return json_error(str(e), 401)

    target_tier = (body.get("tier") or "pro").strip().lower()
    if target_tier not in ("pro", "enterprise"):
        return json_error("Invalid tier. Choose 'pro' or 'enterprise'", 400)

    if not is_stripe_configured():
        return json_error("Payment gateway not configured. Set STRIPE_SECRET_KEY", 503)

    store = Store()
    org = store.get_organization_by_id(org_id)
    if not org:
        return json_error("Organization not found", 404)

    # Create checkout session
    result = create_checkout_session(org_id, target_tier, email, org["slug"])
    if "error" in result:
        return json_error(result["error"], 500)

    return json_ok(result)


# ---------------------------------------------------------------------------
# POST /api/v1/subscription/cancel
# ---------------------------------------------------------------------------

def _handle_sub_cancel(body: dict, handler=None) -> tuple:
    """Cancel the current subscription (at period end).

    Body: {} (empty)
    Response: {status: "canceled", ...}
    """
    if handler is None:
        return json_error("Unauthorized", 401)

    try:
        org_id, user_id, email = _get_authenticated_org(handler.headers)
    except PermissionError as e:
        return json_error(str(e), 401)

    store = Store()
    subscription = store.get_subscription(org_id)
    if not subscription or not subscription.get("stripe_subscription_id"):
        return json_error("No active subscription found", 404)

    # Cancel at period end via Stripe
    try:
        import stripe
        import os

        sk = os.environ.get("STRIPE_SECRET_KEY", "")
        if not sk:
            return json_error("Payment gateway not configured", 503)

        stripe.api_key = sk
        stripe.Subscription.modify(
            subscription["stripe_subscription_id"],
            cancel_at_period_end=True,
        )

        # Update local subscription status
        store.upsert_subscription(org_id, {"status": "cancel_at_period_end"})

        return json_ok({
            "status": "cancel_at_period_end",
            "message": "Subscription will be canceled at the end of the current billing period",
            "current_period_end": subscription.get("current_period_end", ""),
        })

    except ImportError:
        return json_error("stripe package not installed. pip install stripe", 500)
    except Exception as e:
        logger.error("Stripe cancel error: %s", e)
        return json_error(f"Failed to cancel: {e}", 500)


# ---------------------------------------------------------------------------
# POST /api/v1/subscription/webhook
# ---------------------------------------------------------------------------

def _handle_stripe_webhook(body: dict, handler=None) -> tuple:
    """Handle Stripe webhook events.

    Reads raw body from handler.rfile and stripe-signature header.
    """
    if handler is None:
        return json_error("Internal error", 500)

    # Read raw body
    content_length = int(handler.headers.get("Content-Length", 0))
    raw_body = handler.rfile.read(content_length) if content_length > 0 else b""

    signature = handler.headers.get("Stripe-Signature", "")
    if not signature:
        return json_error("Missing Stripe signature", 400)

    result = handle_stripe_webhook(raw_body, signature)
    if result.get("status") == "error":
        return json_error(result.get("message", "Webhook processing failed"), 400)

    return json_ok(result)
