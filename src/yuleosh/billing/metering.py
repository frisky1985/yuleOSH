# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Usage metering & Stripe billing integration (SAAS-5).

Supports mock mode — when STRIPE_SECRET_KEY is not set, all Stripe
operations create mock sessions in memory. No real API calls made.

Usage:
    meter = UsageMeter()
    meter.increment_ci_run("my-org")
    usage = meter.get_usage("my-org")
    if usage["ci_runs"] >= meter.get_limit("my-org", "max_ci_runs"):
        # Block CI run — limit reached
        ...

    billing = BillingManager()
    session = billing.create_checkout_session("my-org", "pro")
    # Redirect user to session.url

    # Stripe webhook handler:
    billing.handle_webhook({"type": "checkout.session.completed", ...})
"""

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


logger = logging.getLogger("billing.metering")


# ── Plan definitions ────────────────────────────────────────────────────────

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"

PLAN_LIMITS = {
    PLAN_FREE: {
        "max_projects": 1,
        "max_users": 1,
        "max_ci_runs": 50,
        "max_storage_mb": 100,
        "features": ["basic_pipeline", "misra_check"],
        "price_monthly_cents": 0,
        "label": "Free (Community)",
    },
    PLAN_PRO: {
        "max_projects": 10,
        "max_users": 5,
        "max_ci_runs": 500,
        "max_storage_mb": 1024,
        "features": ["basic_pipeline", "misra_check", "audit_log", "kanban",
                      "rbac", "ci_cd", "evidence_export"],
        "price_monthly_cents": 2999,  # $29.99/month
        "stripe_price_id": "price_pro_monthly_mock",
        "label": "Pro",
    },
    PLAN_ENTERPRISE: {
        "max_projects": 9999,
        "max_users": 9999,
        "max_ci_runs": 50000,
        "max_storage_mb": 102400,
        "features": ["all"],
        "price_monthly_cents": 9999,  # $99.99/month
        "stripe_price_id": "price_enterprise_monthly_mock",
        "label": "Enterprise",
    },
}

PLANS = [PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE]


# ── Usage data ──────────────────────────────────────────────────────────────

@dataclass
class UsageEntry:
    """A single usage metric entry."""
    resource: str        # "ci_run" | "storage_bytes" | "api_call"
    tenant: str          # tenant slug
    amount: int = 1      # increment size
    timestamp: str = ""  # ISO 8601

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class UsageMeter:
    """File-system-backed usage metering.

    Storage:
      data/{tenant}/usage/YYYY-MM.jsonl  — Monthly usage entries

    Also provides a convenience in-memory cache for fast checks.
    """

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            osh_home = os.environ.get(
                "OSH_HOME",
                str(Path.home() / ".openclaw" / "workspace" / "tasks" / "yuleOSH"),
            )
            data_root = os.path.join(osh_home, "data")
        self.data_root = Path(data_root)

    def _get_month_file(self, tenant: str, month: str = "") -> Path:
        """Get usage file path for a tenant/month.
        month format: YYYY-MM (default: current month)
        """
        if not month:
            month = date.today().isoformat()[:7]  # YYYY-MM
        path = self.data_root / tenant / "usage"
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{month}.jsonl"

    def increment(self, tenant: str, resource: str, amount: int = 1):
        """Record a usage event."""
        entry = UsageEntry(
            resource=resource,
            tenant=tenant,
            amount=amount,
        )
        file_path = self._get_month_file(tenant)
        with open(file_path, "a") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def increment_ci_run(self, tenant: str):
        """Convenience: record a CI run."""
        self.increment(tenant, "ci_run")

    def get_monthly_usage(self, tenant: str, month: str = "") -> dict:
        """Get aggregated usage for a given month."""
        file_path = self._get_month_file(tenant, month)
        if not file_path.exists():
            return {"ci_runs": 0, "api_calls": 0, "storage_mb": 0}

        usage = defaultdict(int)
        try:
            with open(file_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        usage[data.get("resource", "unknown")] += data.get("amount", 1)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return {
            "ci_runs": usage.get("ci_run", 0),
            "api_calls": usage.get("api_call", 0),
            "storage_mb": usage.get("storage_mb", 0),
        }

    def get_usage_summary(self, tenant: str, plan: str = PLAN_FREE) -> dict:
        """Get usage summary with limits comparison."""
        usage = self.get_monthly_usage(tenant)
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[PLAN_FREE])

        return {
            "tenant": tenant,
            "plan": plan,
            "period": date.today().isoformat()[:7],
            "usage": usage,
            "limits": {
                "ci_runs": limits["max_ci_runs"],
                "projects": limits["max_projects"],
                "users": limits["max_users"],
                "storage_mb": limits["max_storage_mb"],
            },
            "within_limits": (
                usage["ci_runs"] <= limits["max_ci_runs"]
            ),
        }

    def is_within_limits(self, tenant: str, plan: str = PLAN_FREE) -> dict:
        """Check if tenant is within plan limits. Returns check results."""
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[PLAN_FREE])
        usage = self.get_monthly_usage(tenant)

        checks = {
            "ci_runs": usage["ci_runs"] < limits["max_ci_runs"],
            "storage": usage["storage_mb"] < limits["max_storage_mb"],
        }
        return {
            "all_pass": all(checks.values()),
            "checks": checks,
            "usage": usage,
            "limits": limits,
        }


# ── Stripe Billing (mock mode) ──────────────────────────────────────────────

class MockStripeSession:
    """Mock Stripe Checkout Session for testing without real API key."""

    def __init__(self, customer_id: str, price_id: str, tenant: str, plan: str):
        self.id = f"cs_mock_{int(time.time())}_{hash(tenant) % 10000}"
        self.customer_id = customer_id or f"cus_mock_{hash(tenant) % 100000}"
        self.price_id = price_id
        self.tenant = tenant
        self.plan = plan
        self.url = f"/mock/stripe/checkout?session_id={self.id}&tenant={tenant}&plan={plan}"
        self.payment_status = "unpaid"
        self.status = "open"


class BillingManager:
    """Billing and subscription management.

    Uses real Stripe SDK when STRIPE_SECRET_KEY is set, otherwise mock mode.
    """

    def __init__(self, data_root: Optional[str] = None):
        if data_root is None:
            osh_home = os.environ.get(
                "OSH_HOME",
                str(Path.home() / ".openclaw" / "workspace" / "tasks" / "yuleOSH"),
            )
            data_root = os.path.join(osh_home, "data")
        self.data_root = Path(data_root)
        self.subscriptions_dir = self.data_root / "subscriptions"
        self.subscriptions_dir.mkdir(parents=True, exist_ok=True)

        # Check for real Stripe key
        self.stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self.mock_mode = not bool(self.stripe_key)

        if self.mock_mode:
            logger.info("BillingManager: STRIPE_SECRET_KEY not set, using MOCK mode")
            self._mock_sessions = {}
        else:
            import stripe
            stripe.api_key = self.stripe_key
            logger.info("BillingManager: Stripe live mode enabled")

    def create_checkout_session(self, tenant: str, plan: str,
                                 customer_id: str = "",
                                 success_url: str = "/billing",
                                 cancel_url: str = "/billing") -> dict:
        """Create a Stripe Checkout Session for upgrading.

        In mock mode, returns a mock session object.
        In live mode, delegates to stripe.checkout.Session.create().
        """
        if plan not in PLANS:
            return {"error": f"Invalid plan '{plan}'. Valid: {PLANS}"}

        if self.mock_mode:
            session = MockStripeSession(
                customer_id=customer_id,
                price_id=PLAN_LIMITS[plan].get("stripe_price_id", f"price_{plan}_mock"),
                tenant=tenant,
                plan=plan,
            )
            self._mock_sessions[session.id] = session
            # Auto-complete and activate subscription in mock mode
            session.payment_status = "paid"
            session.status = "complete"
            self._activate_subscription(tenant, plan)
            return {
                "ok": True,
                "session_id": session.id,
                "url": session.url,
                "mock": True,
                "payment_status": "paid",
            }
        else:
            import stripe
            try:
                session = stripe.checkout.Session.create(
                    mode="subscription",
                    line_items=[{"price": PLAN_LIMITS[plan]["stripe_price_id"], "quantity": 1}],
                    customer=customer_id or None,
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
                return {
                    "ok": True,
                    "session_id": session.id,
                    "url": session.url,
                    "mock": False,
                }
            except Exception as e:
                logger.error("Stripe checkout failed: %s", e)
                return {"error": f"Stripe checkout failed: {e}"}

    def handle_webhook(self, payload: dict) -> dict:
        """Handle Stripe webhook events (mock mode).

        In real mode, this would validate webhook signatures.
        """
        event_type = payload.get("type", "")

        if event_type == "checkout.session.completed":
            session_data = payload.get("data", {}).get("object", {})
            tenant = session_data.get("metadata", {}).get("tenant", "")
            plan = session_data.get("metadata", {}).get("plan", PLAN_PRO)

            if tenant:
                self._activate_subscription(tenant, plan)
                return {"ok": True, "action": "subscription_activated", "tenant": tenant, "plan": plan}

        elif event_type == "invoice.paid":
            # Renew subscription
            tenant = payload.get("data", {}).get("object", {}).get("metadata", {}).get("tenant", "")
            if tenant:
                self._renew_subscription(tenant)
                return {"ok": True, "action": "subscription_renewed", "tenant": tenant}

        elif event_type == "customer.subscription.deleted":
            # Downgrade to free
            tenant = payload.get("data", {}).get("object", {}).get("metadata", {}).get("tenant", "")
            if tenant:
                self._downgrade_to_free(tenant)
                return {"ok": True, "action": "subscription_cancelled", "tenant": tenant}

        return {"ok": True, "action": "unhandled", "type": event_type}

    def _activate_subscription(self, tenant: str, plan: str):
        """Persist an active subscription."""
        path = self.subscriptions_dir / f"{tenant}.json"
        data = {
            "tenant": tenant,
            "plan": plan,
            "status": "active",
            "current_period_start": date.today().isoformat(),
            "current_period_end": (date.today() + timedelta(days=30)).isoformat(),
            "created_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _renew_subscription(self, tenant: str):
        """Extend subscription period."""
        path = self.subscriptions_dir / f"{tenant}.json"
        if path.exists():
            data = json.loads(path.read_text())
            data["current_period_end"] = (date.today() + timedelta(days=30)).isoformat()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _downgrade_to_free(self, tenant: str):
        """Downgrade to free plan."""
        path = self.subscriptions_dir / f"{tenant}.json"
        if path.exists():
            data = json.loads(path.read_text())
            data["plan"] = PLAN_FREE
            data["status"] = "cancelled"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def get_subscription(self, tenant: str) -> dict:
        """Get current subscription for a tenant."""
        path = self.subscriptions_dir / f"{tenant}.json"
        if not path.exists():
            return {
                "tenant": tenant,
                "plan": PLAN_FREE,
                "status": "active",
                "mock": self.mock_mode,
            }
        data = json.loads(path.read_text())
        data["mock"] = self.mock_mode
        return data

    def cancel_subscription(self, tenant: str) -> dict:
        """Cancel (downgrade to free)."""
        self._downgrade_to_free(tenant)
        return {"ok": True, "tenant": tenant, "plan": PLAN_FREE, "status": "cancelled"}
