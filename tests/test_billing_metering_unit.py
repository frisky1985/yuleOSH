"""Unit tests for yuleosh.billing.metering — UsageMeter + BillingManager (v3.4.2 Wave 0).

Covers:
  - Plan limits sanity
  - UsageEntry defaults
  - UsageMeter: month file paths, increment/increment_ci_run, monthly usage
    aggregation (empty/corrupt/OSError), usage summary, within-limits checks
  - MockStripeSession fields
  - BillingManager: mock/live mode init, checkout sessions (invalid plan,
    mock success, live success, live error), webhook handlers, subscription
    lifecycle (_activate/_renew/_downgrade), get/cancel subscription
"""

import json
import os
import sys
from datetime import date
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.billing.metering import (
    PLAN_FREE,
    PLAN_PRO,
    PLAN_ENTERPRISE,
    PLANS,
    PLAN_LIMITS,
    UsageEntry,
    UsageMeter,
    MockStripeSession,
    BillingManager,
)


# ── Constants / UsageEntry ────────────────────────────────────────────

class TestConstantsAndEntry:
    def test_plans_defined(self):
        """GIVEN plan constants WHEN checked THEN limits/price present."""
        assert PLANS == [PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE]
        assert PLAN_LIMITS[PLAN_PRO]["price_monthly_cents"] == 2999
        assert PLAN_LIMITS[PLAN_ENTERPRISE]["max_ci_runs"] == 50000

    def test_usage_entry_defaults(self):
        """GIVEN minimal entry WHEN constructed THEN defaults filled."""
        e = UsageEntry(resource="ci_run", tenant="acme")
        assert e.amount == 1
        assert e.timestamp


# ── UsageMeter ────────────────────────────────────────────────────────

@pytest.fixture
def meter(tmp_path):
    return UsageMeter(data_root=str(tmp_path))


class TestUsageMeter:
    def test_month_file_default(self, meter):
        """GIVEN no month WHEN _get_month_file THEN current YYYY-MM."""
        p = meter._get_month_file("acme")
        assert p.name == f"{date.today().isoformat()[:7]}.jsonl"
        assert p.parent.name == "usage"
        assert p.parent.is_dir()

    def test_month_file_explicit(self, meter):
        """GIVEN month WHEN _get_month_file THEN that month's file."""
        p = meter._get_month_file("acme", "2026-05")
        assert p.name == "2026-05.jsonl"

    def test_increment_writes_entry(self, meter):
        """GIVEN increment WHEN called THEN JSONL line appended."""
        meter.increment("acme", "ci_run")
        meter.increment("acme", "api_call", amount=3)
        lines = meter._get_month_file("acme").read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["resource"] == "ci_run"
        assert first["tenant"] == "acme"

    def test_increment_ci_run(self, meter):
        """GIVEN increment_ci_run WHEN called THEN ci_run recorded."""
        meter.increment_ci_run("acme")
        usage = meter.get_monthly_usage("acme")
        assert usage["ci_runs"] == 1

    def test_get_monthly_usage_empty(self, meter):
        """GIVEN no file WHEN get_monthly_usage THEN zeros."""
        assert meter.get_monthly_usage("ghost") == {
            "ci_runs": 0, "api_calls": 0, "storage_mb": 0}

    def test_get_monthly_usage_aggregates(self, meter):
        """GIVEN entries WHEN get_monthly_usage THEN aggregated counts."""
        meter.increment("acme", "ci_run")
        meter.increment("acme", "ci_run")
        meter.increment("acme", "storage_mb", amount=10)
        usage = meter.get_monthly_usage("acme")
        assert usage["ci_runs"] == 2
        assert usage["storage_mb"] == 10

    def test_get_monthly_usage_skips_corrupt(self, meter):
        """GIVEN corrupt line WHEN get_monthly_usage THEN skipped."""
        p = meter._get_month_file("acme")
        p.write_text('{"resource": "ci_run", "tenant": "acme", "amount": 1, "timestamp": "t"}\n'
                     "garbage\n")
        usage = meter.get_monthly_usage("acme")
        assert usage["ci_runs"] == 1

    def test_get_monthly_usage_oserror(self, meter):
        """GIVEN OSError reading file WHEN get_monthly_usage THEN zeros."""
        p = meter._get_month_file("acme")
        p.write_text("x")
        with mock.patch("builtins.open", side_effect=OSError("boom")):
            usage = meter.get_monthly_usage("acme")
        assert usage["ci_runs"] == 0

    def test_get_usage_summary(self, meter):
        """GIVEN usage under limit WHEN get_usage_summary THEN within_limits."""
        meter.increment_ci_run("acme")
        s = meter.get_usage_summary("acme", PLAN_FREE)
        assert s["tenant"] == "acme"
        assert s["period"] == date.today().isoformat()[:7]
        assert s["usage"]["ci_runs"] == 1
        assert s["limits"]["ci_runs"] == 50
        assert s["within_limits"] is True

    def test_get_usage_summary_unknown_plan(self, meter):
        """GIVEN unknown plan WHEN get_usage_summary THEN free limits used."""
        s = meter.get_usage_summary("acme", "gold")
        assert s["limits"]["ci_runs"] == PLAN_LIMITS[PLAN_FREE]["max_ci_runs"]

    def test_is_within_limits_pass(self, meter):
        """GIVEN usage under limits WHEN is_within_limits THEN all_pass."""
        meter.increment_ci_run("acme")
        r = meter.is_within_limits("acme", PLAN_FREE)
        assert r["all_pass"] is True
        assert r["checks"]["ci_runs"] is True

    def test_is_within_limits_fail(self, meter):
        """GIVEN usage at/over limit WHEN is_within_limits THEN ci check fails."""
        for _ in range(50):
            meter.increment("acme", "ci_run")
        r = meter.is_within_limits("acme", PLAN_FREE)
        assert r["checks"]["ci_runs"] is False  # 50 < 50 → False
        assert r["all_pass"] is False


# ── BillingManager ────────────────────────────────────────────────────

class TestBillingManager:
    def test_init_mock_mode(self, tmp_path):
        """GIVEN no STRIPE_SECRET_KEY WHEN init THEN mock mode."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STRIPE_SECRET_KEY", None)
            bm = BillingManager(data_root=str(tmp_path))
        assert bm.mock_mode is True
        assert bm.subscriptions_dir.is_dir()

    def test_init_live_mode(self, tmp_path):
        """GIVEN STRIPE_SECRET_KEY WHEN init THEN live mode + stripe import."""
        fake_stripe = mock.MagicMock()
        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"}):
            with mock.patch.dict(sys.modules, {"stripe": fake_stripe}):
                bm = BillingManager(data_root=str(tmp_path))
        assert bm.mock_mode is False
        assert fake_stripe.api_key == "sk_test_x"

    def test_checkout_invalid_plan(self, tmp_path):
        """GIVEN invalid plan WHEN create_checkout_session THEN error dict."""
        bm = BillingManager(data_root=str(tmp_path))
        r = bm.create_checkout_session("acme", "platinum")
        assert "error" in r
        assert "Invalid plan" in r["error"]

    def test_checkout_mock_success(self, tmp_path):
        """GIVEN mock mode WHEN checkout THEN paid session + subscription."""
        bm = BillingManager(data_root=str(tmp_path))
        r = bm.create_checkout_session("acme", PLAN_PRO)
        assert r["ok"] is True
        assert r["mock"] is True
        assert r["payment_status"] == "paid"
        assert "cs_mock_" in r["session_id"]
        sub = bm.get_subscription("acme")
        assert sub["plan"] == PLAN_PRO
        assert sub["status"] == "active"

    def test_checkout_live_success(self, tmp_path):
        """GIVEN live mode WHEN checkout succeeds THEN ok with session id."""
        fake_stripe = mock.MagicMock()
        fake_stripe.checkout.Session.create.return_value = mock.MagicMock(
            id="cs_live_1", url="https://stripe.example/1")
        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"}):
            with mock.patch.dict(sys.modules, {"stripe": fake_stripe}):
                bm = BillingManager(data_root=str(tmp_path))
                r = bm.create_checkout_session("acme", PLAN_PRO,
                                               success_url="/ok", cancel_url="/no")
        assert r["ok"] is True and r["mock"] is False
        assert r["session_id"] == "cs_live_1"
        fake_stripe.checkout.Session.create.assert_called_once()

    def test_checkout_live_error(self, tmp_path):
        """GIVEN live mode WHEN stripe raises THEN error dict logged."""
        fake_stripe = mock.MagicMock()
        fake_stripe.checkout.Session.create.side_effect = Exception("card declined")
        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_x"}):
            with mock.patch.dict(sys.modules, {"stripe": fake_stripe}):
                bm = BillingManager(data_root=str(tmp_path))
                with mock.patch("yuleosh.billing.metering.logger") as mlog:
                    r = bm.create_checkout_session("acme", PLAN_PRO)
        assert "error" in r and "card declined" in r["error"]
        mlog.error.assert_called()

    def test_webhook_checkout_completed(self, tmp_path):
        """GIVEN checkout.session.completed webhook WHEN handle THEN activates."""
        bm = BillingManager(data_root=str(tmp_path))
        r = bm.handle_webhook({"type": "checkout.session.completed",
                               "data": {"object": {"metadata": {"tenant": "acme",
                                                                "plan": PLAN_PRO}}}})
        assert r["action"] == "subscription_activated"
        assert bm.get_subscription("acme")["plan"] == PLAN_PRO

    def test_webhook_checkout_completed_no_tenant(self, tmp_path):
        """GIVEN completed webhook w/o tenant WHEN handle THEN unhandled."""
        bm = BillingManager(data_root=str(tmp_path))
        r = bm.handle_webhook({"type": "checkout.session.completed",
                               "data": {"object": {"metadata": {}}}})
        assert r["action"] == "unhandled"

    def test_webhook_invoice_paid(self, tmp_path):
        """GIVEN invoice.paid webhook WHEN handle THEN subscription renewed."""
        bm = BillingManager(data_root=str(tmp_path))
        bm._activate_subscription("acme", PLAN_PRO)
        before = bm.get_subscription("acme")["current_period_end"]
        r = bm.handle_webhook({"type": "invoice.paid",
                               "data": {"object": {"metadata": {"tenant": "acme"}}}})
        assert r["action"] == "subscription_renewed"
        assert bm.get_subscription("acme")["current_period_end"] >= before

    def test_webhook_subscription_deleted(self, tmp_path):
        """GIVEN subscription.deleted webhook WHEN handle THEN downgraded."""
        bm = BillingManager(data_root=str(tmp_path))
        bm._activate_subscription("acme", PLAN_ENTERPRISE)
        r = bm.handle_webhook({"type": "customer.subscription.deleted",
                               "data": {"object": {"metadata": {"tenant": "acme"}}}})
        assert r["action"] == "subscription_cancelled"
        sub = bm.get_subscription("acme")
        assert sub["plan"] == PLAN_FREE
        assert sub["status"] == "cancelled"

    def test_webhook_unhandled(self, tmp_path):
        """GIVEN unknown webhook type WHEN handle THEN unhandled result."""
        bm = BillingManager(data_root=str(tmp_path))
        r = bm.handle_webhook({"type": "something.else"})
        assert r["action"] == "unhandled"
        assert r["type"] == "something.else"

    def test_mock_session_fields(self, tmp_path):
        """GIVEN MockStripeSession WHEN created THEN fields populated."""
        s = MockStripeSession("cus_1", "price_x", "acme", PLAN_PRO)
        assert s.id.startswith("cs_mock_")
        assert s.customer_id == "cus_1"
        assert s.plan == PLAN_PRO
        assert s.payment_status == "unpaid"
        assert s.status == "open"
        assert "acme" in s.url

    def test_mock_session_default_customer(self):
        """GIVEN empty customer WHEN MockStripeSession THEN generated id."""
        s = MockStripeSession("", "price_x", "acme", PLAN_FREE)
        assert s.customer_id.startswith("cus_mock_")

    def test_renew_subscription_missing_file(self, tmp_path):
        """GIVEN no subscription file WHEN _renew THEN no crash."""
        bm = BillingManager(data_root=str(tmp_path))
        bm._renew_subscription("ghost")  # no exception expected

    def test_cancel_subscription(self, tmp_path):
        """GIVEN active sub WHEN cancel_subscription THEN downgraded."""
        bm = BillingManager(data_root=str(tmp_path))
        bm._activate_subscription("acme", PLAN_PRO)
        r = bm.cancel_subscription("acme")
        assert r["ok"] is True and r["plan"] == PLAN_FREE
        assert bm.get_subscription("acme")["status"] == "cancelled"

    def test_get_subscription_default_free(self, tmp_path):
        """GIVEN no sub file WHEN get_subscription THEN free plan default."""
        bm = BillingManager(data_root=str(tmp_path))
        sub = bm.get_subscription("ghost")
        assert sub["plan"] == PLAN_FREE
        assert sub["status"] == "active"
        assert sub["mock"] is True
