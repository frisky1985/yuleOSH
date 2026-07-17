# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH v0.9.0 — Usage Metering.

Tracks per-organization usage: pipeline runs, LLM tokens, storage, projects.
Enforces tier limits.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ── Tier configuration ────────────────────────────────────────────────────────
#
# stripe_price_id: Set via Stripe Dashboard after creating products/prices.
#   Steps:
#     1. Go to https://dashboard.stripe.com/products → Add Product
#     2. Create product named "yuleOSH Pro" with recurring monthly price
#     3. Copy the Price ID (starts with price_) and set it here
#     4. Repeat for Enterprise tier
#     5. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET in .env.production
#     6. Create a Webhook Endpoint pointing to: {BASE_URL}/api/v1/subscription/webhook
#        Subscribe to: checkout.session.completed, customer.subscription.updated,
#        customer.subscription.deleted
#
#   Example:
#     "pro": {
#         ...,
#         "stripe_price_id": "price_1Qwerty123456789",
#     }

TIERS = {
    "community": {
        "name": "Community",
        "max_projects": 1,
        "max_pipeline_runs": 100,
        "max_llm_tokens": 50000,
        "max_storage_mb": 100,
        "llm_enabled": False,
        "price_monthly": 0,
        "stripe_price_id": None,
    },
    "pro": {
        "name": "Pro",
        "max_projects": 10,
        "max_pipeline_runs": 1000,
        "max_llm_tokens": 500000,
        "max_storage_mb": 1000,
        "llm_enabled": True,
        "price_monthly": 599,
        "stripe_price_id": None,  # Set via Stripe Dashboard
    },
    "enterprise": {
        "name": "Enterprise",
        "max_projects": 999,
        "max_pipeline_runs": 99999,
        "max_llm_tokens": 99999999,
        "max_storage_mb": 10240,
        "llm_enabled": True,
        "price_monthly": 8167,
        "stripe_price_id": None,
    },
}

TRIAL_DAYS = 14


def get_org_tier(store, org_id: int) -> str:
    """Get the current subscription tier for an org."""
    org = store.get_organization_by_id(org_id)
    if not org:
        return "community"
    return org.get("tier", "community")


def get_trial_status(store, org_id: int) -> dict:
    """Get trial status for an org."""
    org = store.get_organization_by_id(org_id)
    if not org:
        return {"in_trial": False, "days_left": 0}

    created_at = org.get("created_at", "")
    if not created_at:
        return {"in_trial": False, "days_left": 0}

    try:
        created = datetime.fromisoformat(created_at)
    except (ValueError, TypeError):
        return {"in_trial": False, "days_left": 0}

    elapsed = (datetime.now() - created).days
    days_left = max(0, TRIAL_DAYS - elapsed)

    # Only in trial if on Pro tier and never paid
    tier = get_org_tier(store, org_id)
    subscription = store.get_subscription(org_id)
    has_paid = subscription and subscription.get("stripe_subscription_id") and subscription["stripe_subscription_id"] != "trialing"

    if tier == "pro" and not has_paid and days_left > 0:
        return {"in_trial": True, "days_left": days_left,
                "trial_end": (created + timedelta(days=TRIAL_DAYS)).isoformat()}

    return {"in_trial": False, "days_left": 0}


def check_tier_limit(store, org_id: int, resource: str) -> dict:
    """Check if an org has exceeded a resource limit. Returns {allowed, limit, used, message}."""
    tier = get_org_tier(store, org_id)
    config = TIERS.get(tier, TIERS["community"])
    usage = store.get_monthly_usage(org_id)

    limits = {
        "projects": ("max_projects", usage.get("project_count", 0)),
        "pipeline_runs": ("max_pipeline_runs", usage.get("pipeline_runs", 0)),
        "llm_tokens": ("max_llm_tokens", usage.get("llm_tokens", 0)),
        "storage_mb": ("max_storage_mb", usage.get("storage_mb", 0)),
    }

    if resource not in limits:
        return {"allowed": True, "limit": 0, "used": 0, "message": ""}

    limit_key, used = limits[resource]
    limit = config.get(limit_key, 0)

    if used >= limit > 0:
        return {"allowed": False, "limit": limit, "used": used,
                "message": f"{resource} limit reached ({used}/{limit}). Upgrade to continue."}

    return {"allowed": True, "limit": limit, "used": used, "message": ""}


def record_pipeline_run(store, org_id: int, project_id: int, llm_tokens: int = 0):
    """Record a pipeline run for usage metering."""
    store.record_usage(org_id, project_id, "pipeline_run", 1)
    if llm_tokens:
        store.record_usage(org_id, project_id, "llm_tokens", llm_tokens)


def get_usage_summary(store, org_id: int) -> dict:
    """Get usage summary with tier limits."""
    tier = get_org_tier(store, org_id)
    config = TIERS.get(tier, TIERS["community"])
    usage = store.get_monthly_usage(org_id)
    trial = get_trial_status(store, org_id)

    return {
        "tier": tier,
        "tier_name": config["name"],
        "trial": trial,
        "usage": {
            "projects": {"used": usage.get("project_count", 0), "limit": config["max_projects"]},
            "pipeline_runs": {"used": usage.get("pipeline_runs", 0), "limit": config["max_pipeline_runs"]},
            "llm_tokens": {"used": usage.get("llm_tokens", 0), "limit": config["max_llm_tokens"]},
            "storage_mb": {"used": usage.get("storage_mb", 0), "limit": config["max_storage_mb"]},
        },
        "llm_enabled": config["llm_enabled"],
    }
