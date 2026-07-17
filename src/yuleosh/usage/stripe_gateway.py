# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH v0.9.0 — Stripe Payment Integration.

Handles Stripe Checkout sessions and webhook events.
"""
import json
import os
from datetime import datetime
from typing import Optional

# Stripe configuration
ENV = os.environ.get
STRIPE_SECRET_KEY = ENV("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = ENV("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = ENV("YULEOSH_BASE_URL", "http://localhost:8080")
SUCCESS_URL = BASE_URL + "/dashboard"
CANCEL_URL = BASE_URL + "/pricing"


def is_stripe_configured() -> bool:
    """Check if Stripe is configured."""
    return bool(STRIPE_SECRET_KEY)


def create_checkout_session(org_id: int, tier: str, email: str, org_slug: str) -> dict:
    """Create a Stripe Checkout session for subscription."""
    if not is_stripe_configured():
        return {"error": "Payment not configured"}

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        from yuleosh.usage.metering import TIERS
        tier_config = TIERS.get(tier, TIERS["pro"])

        if not tier_config.get("stripe_price_id"):
            return {"error": f"No price ID configured for tier '{tier}'"}

        session = stripe.checkout.Session.create(
            customer_email=email,
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": tier_config["stripe_price_id"], "quantity": 1}],
            metadata={"org_id": str(org_id), "org_slug": org_slug, "tier": tier},
            success_url=SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=CANCEL_URL,
        )
        return {"url": session.url, "session_id": session.id}

    except ImportError:
        return {"error": "stripe package not installed. pip install stripe"}
    except Exception as e:
        return {"error": f"Stripe error: {e}"}


def handle_stripe_webhook(payload: bytes, signature: str) -> dict:
    """Process Stripe webhook events."""
    if not is_stripe_configured():
        return {"status": "error", "message": "Payment not configured"}

    if not STRIPE_WEBHOOK_SECRET:
        return {"status": "error", "message": "STRIPE_WEBHOOK_SECRET not configured"}

    if not signature:
        return {"status": "error", "message": "Missing Stripe signature header"}

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return {"status": "error", "message": f"Webhook verification failed: {e}"}

    event_type = event["type"]
    handled = False
    from yuleosh.store import Store
    store = Store()

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        org_id = int(meta.get("org_id", 0))
        tier = meta.get("tier", "pro")
        if org_id and session.get("subscription"):
            store.upsert_subscription(org_id, {
                "stripe_subscription_id": session["subscription"],
                "stripe_customer_id": session.get("customer", ""),
                "tier": tier, "status": "active",
                "current_period_end": datetime.now().isoformat(),
            })
            store.update_org_tier(org_id, tier)
            handled = True

    elif event_type == "customer.subscription.updated":
        sub = event["data"]["object"]
        org = store.get_org_by_stripe_subscription(sub["id"])
        if org:
            store.upsert_subscription(org["id"], {
                "stripe_subscription_id": sub["id"],
                "status": sub["status"],
                "current_period_end": datetime.fromtimestamp(
                    sub.get("current_period_end", 0)).isoformat() if sub.get("current_period_end") else "",
            })
            if sub["status"] in ("canceled", "unpaid"):
                store.update_org_tier(org["id"], "community")
            handled = True

    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        org = store.get_org_by_stripe_subscription(sub["id"])
        if org:
            store.update_org_tier(org["id"], "community")
            handled = True

    return {"status": "ok", "event_type": event_type, "handled": handled}
