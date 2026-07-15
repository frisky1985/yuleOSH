"""Gap-filling tests for usage/metering.py and usage/stripe_gateway.py.

Covers:
  - get_trial_status: edge cases (no org, no created_at, parse errors, paid sub)
  - check_tier_limit: various resources, limit checks
  - get_usage_summary: full summary with trial info
  - handle_stripe_webhook: all event types, edge cases
  - create_checkout_session: edge cases
"""

import json
import os
import sys
from datetime import datetime, timedelta
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.usage.metering import (
    get_trial_status,
    check_tier_limit,
    record_pipeline_run,
    get_usage_summary,
    get_org_tier,
)
from yuleosh.usage.stripe_gateway import (
    handle_stripe_webhook,
    create_checkout_session,
    is_stripe_configured,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_store():
    """Create a mock store with common defaults."""
    store = mock.MagicMock()
    store.get_organization_by_id.return_value = {
        "id": 1, "name": "TestOrg", "slug": "test-org",
        "tier": "community", "created_at": datetime.now().isoformat(),
    }
    store.get_subscription.return_value = {
        "id": 1, "org_id": 1,
        "stripe_subscription_id": None,
        "stripe_customer_id": None,
        "tier": "community", "status": "active",
    }
    store.get_monthly_usage.return_value = {
        "project_count": 0, "pipeline_runs": 0,
        "llm_tokens": 0, "storage_mb": 0,
    }
    return store


# ── get_trial_status (edge cases) ─────────────────────────────────────

class TestGetTrialStatus:
    def test_no_org(self, mock_store):
        """GIVEN org doesn't exist WHEN checking trial THEN no trial."""
        mock_store.get_organization_by_id.return_value = None
        result = get_trial_status(mock_store, 999)
        assert result["in_trial"] is False
        assert result["days_left"] == 0

    def test_no_created_at(self, mock_store):
        """GIVEN org without created_at WHEN checking trial THEN no trial."""
        mock_store.get_organization_by_id.return_value = {"id": 1, "name": "NoDate"}
        result = get_trial_status(mock_store, 1)
        assert result["in_trial"] is False

    def test_invalid_created_at(self, mock_store):
        """GIVEN org with invalid created_at WHEN checking trial THEN no trial."""
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "name": "BadDate", "created_at": "not-a-date-format"
        }
        result = get_trial_status(mock_store, 1)
        assert result["in_trial"] is False

    def test_paid_subscription_no_trial(self, mock_store):
        """GIVEN paid subscription WHEN checking trial THEN no trial."""
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "name": "Paid", "slug": "paid",
            "tier": "pro", "created_at": datetime.now().isoformat(),
        }
        mock_store.get_subscription.return_value = {
            "id": 1, "org_id": 1,
            "stripe_subscription_id": "sub_real",
            "stripe_customer_id": "cus_123",
            "tier": "pro", "status": "active",
        }
        result = get_trial_status(mock_store, 1)
        assert result["in_trial"] is False

    def test_trial_is_pro_no_paid(self, mock_store):
        """GIVEN pro tier without payment WHEN checking trial THEN in trial."""
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "name": "TrialOrg", "slug": "trial",
            "tier": "pro", "created_at": datetime.now().isoformat(),
        }
        result = get_trial_status(mock_store, 1)
        assert result["in_trial"] is True
        assert result["days_left"] > 0

    def test_trial_expired(self, mock_store):
        """GIVEN old org beyond trial period WHEN checking trial THEN no trial."""
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "name": "OldOrg", "slug": "old",
            "tier": "pro", "created_at": old_date,
        }
        result = get_trial_status(mock_store, 1)
        assert result["in_trial"] is False


# ── check_tier_limit ─────────────────────────────────────────────────

class TestCheckTierLimit:
    def test_unknown_resource(self, mock_store):
        """GIVEN unknown resource WHEN checking limit THEN allowed."""
        result = check_tier_limit(mock_store, 1, "unknown_resource")
        assert result["allowed"] is True

    def test_within_limit(self, mock_store):
        """GIVEN usage within limits WHEN checking THEN allowed."""
        result = check_tier_limit(mock_store, 1, "pipeline_runs")
        assert result["allowed"] is True

    def test_exceeded_limit(self, mock_store):
        """GIVEN usage exceeds limit WHEN checking THEN not allowed."""
        mock_store.get_monthly_usage.return_value = {
            "project_count": 100, "pipeline_runs": 0,
            "llm_tokens": 0, "storage_mb": 0,
        }
        result = check_tier_limit(mock_store, 1, "projects")
        assert result["allowed"] is False
        assert "limit reached" in result["message"]

    def test_enterprise_unlimited(self, mock_store):
        """GIVEN enterprise tier WHEN checking THEN always allowed."""
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "name": "Ent", "slug": "ent",
            "tier": "enterprise", "created_at": datetime.now().isoformat(),
        }
        mock_store.get_monthly_usage.return_value = {
            "project_count": 99999, "pipeline_runs": 99999,
            "llm_tokens": 99999, "storage_mb": 99999,
        }
        result = check_tier_limit(mock_store, 1, "projects")
        assert result["allowed"] is True


# ── record_pipeline_run ──────────────────────────────────────────────

class TestRecordPipelineRun:
    def test_basic_record(self, mock_store):
        """GIVEN pipeline run WHEN recording THEN calls store methods."""
        record_pipeline_run(mock_store, 1, 1)
        mock_store.record_usage.assert_called_with(1, 1, "pipeline_run", 1)

    def test_with_llm_tokens(self, mock_store):
        """GIVEN pipeline run with tokens WHEN recording THEN records both."""
        record_pipeline_run(mock_store, 1, 1, llm_tokens=500)
        assert mock_store.record_usage.call_count == 2

    def test_zero_tokens(self, mock_store):
        """GIVEN pipeline run with zero tokens WHEN recording THEN only records pipeline."""
        record_pipeline_run(mock_store, 1, 1, llm_tokens=0)
        mock_store.record_usage.assert_called_once()


# ── get_usage_summary ────────────────────────────────────────────────

class TestGetUsageSummary:
    def test_returns_all_fields(self, mock_store):
        """GIVEN valid org WHEN getting summary THEN all fields present."""
        summary = get_usage_summary(mock_store, 1)
        assert "tier" in summary
        assert "tier_name" in summary
        assert "trial" in summary
        assert "usage" in summary
        assert "llm_enabled" in summary

    def test_usage_has_correct_keys(self, mock_store):
        """GIVEN usage summary WHEN checking keys THEN has all resource types."""
        summary = get_usage_summary(mock_store, 1)
        for resource in ("projects", "pipeline_runs", "llm_tokens", "storage_mb"):
            assert resource in summary["usage"]

    def test_get_org_tier_default(self, mock_store):
        """GIVEN org without tier in dict WHEN getting tier THEN returns default."""
        mock_store.get_organization_by_id.return_value = {"id": 1, "name": "NoTier"}
        tier = get_org_tier(mock_store, 1)
        assert tier == "community"


# ── handle_stripe_webhook ─────────────────────────────────────────────

class TestHandleStripeWebhook:
    def test_not_configured(self):
        """GIVEN Stripe not configured WHEN handling webhook THEN error."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", ""):
            result = handle_stripe_webhook(b"{}", "sig")
            assert result["status"] == "error"

    def test_verification_failed(self):
        """GIVEN invalid webhook signature WHEN processing THEN error."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_WEBHOOK_SECRET", "whsec_xxx"):
                with mock.patch("yuleosh.usage.stripe_gateway.stripe.Webhook.construct_event",
                               side_effect=Exception("Bad signature")):
                    result = handle_stripe_webhook(b"{}", "bad_sig")
                    assert result["status"] == "error"

    def test_checkout_session_completed(self):
        """GIVEN checkout.session.completed event WHEN processing THEN creates subscription."""
        from datetime import datetime
        mock_stripe_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"org_id": "1", "tier": "pro"},
                    "subscription": "sub_123",
                    "customer": "cus_456",
                }
            },
        }
        mock_event = mock.MagicMock()
        mock_event.__getitem__.side_effect = mock_stripe_event.__getitem__
        mock_event.get.side_effect = mock_stripe_event.get

        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_WEBHOOK_SECRET", "whsec_xxx"):
                with mock.patch("yuleosh.usage.stripe_gateway.stripe.Webhook.construct_event",
                               return_value=mock_stripe_event):
                    with mock.patch("yuleosh.usage.stripe_gateway.Store") as MockStore:
                        mock_store = mock.MagicMock()
                        MockStore.return_value = mock_store
                        result = handle_stripe_webhook(b"{}", "sig")
                        assert result["status"] == "ok"
                        assert result["event_type"] == "checkout.session.completed"
                        assert result["handled"] is True
                        mock_store.upsert_subscription.assert_called_once()
                        mock_store.update_org_tier.assert_called_once()

    def test_customer_subscription_updated(self):
        """GIVEN customer.subscription.updated event WHEN processing THEN updates."""
        mock_stripe_event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_123",
                    "status": "past_due",
                    "current_period_end": 1700000000,
                }
            },
        }
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_WEBHOOK_SECRET", "whsec_xxx"):
                with mock.patch("yuleosh.usage.stripe_gateway.stripe.Webhook.construct_event",
                               return_value=mock_stripe_event):
                    with mock.patch("yuleosh.usage.stripe_gateway.Store") as MockStore:
                        mock_store = mock.MagicMock()
                        mock_store.get_org_by_stripe_subscription.return_value = {"id": 1}
                        MockStore.return_value = mock_store
                        result = handle_stripe_webhook(b"{}", "sig")
                        assert result["status"] == "ok"

    def test_subscription_deleted(self):
        """GIVEN customer.subscription.deleted event WHEN processing THEN downgrades."""
        mock_stripe_event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {"id": "sub_deleted"}
            },
        }
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_WEBHOOK_SECRET", "whsec_xxx"):
                with mock.patch("yuleosh.usage.stripe_gateway.stripe.Webhook.construct_event",
                               return_value=mock_stripe_event):
                    with mock.patch("yuleosh.usage.stripe_gateway.Store") as MockStore:
                        mock_store = mock.MagicMock()
                        mock_store.get_org_by_stripe_subscription.return_value = {"id": 1}
                        MockStore.return_value = mock_store
                        result = handle_stripe_webhook(b"{}", "sig")
                        assert result["status"] == "ok"
                        assert result["handled"] is True

    def test_canceled_subscription_downgrades(self):
        """GIVEN subscription updated to canceled WHEN processing THEN downgrades tier."""
        mock_stripe_event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_cancel",
                    "status": "canceled",
                    "current_period_end": 1700000000,
                }
            },
        }
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_WEBHOOK_SECRET", "whsec_xxx"):
                with mock.patch("yuleosh.usage.stripe_gateway.stripe.Webhook.construct_event",
                               return_value=mock_stripe_event):
                    with mock.patch("yuleosh.usage.stripe_gateway.Store") as MockStore:
                        mock_store = mock.MagicMock()
                        mock_store.get_org_by_stripe_subscription.return_value = {"id": 1}
                        MockStore.return_value = mock_store
                        result = handle_stripe_webhook(b"{}", "sig")
                        assert result["status"] == "ok"
                        mock_store.update_org_tier.assert_called_with(1, "community")


# ── create_checkout_session ──────────────────────────────────────────

class TestCreateCheckoutSession:
    def test_not_configured(self):
        """GIVEN Stripe not configured WHEN creating session THEN returns error."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", ""):
            result = create_checkout_session(mock.MagicMock(), 1, "pro")
            assert "error" in result

    def test_stripe_not_installed(self):
        """GIVEN stripe package not available WHEN creating session THEN returns error."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            with mock.patch.dict("sys.modules", {"stripe": None}):
                with mock.patch("yuleosh.usage.stripe_gateway.import_stripe",
                               side_effect=ImportError("no stripe")):
                    result = create_checkout_session(mock.MagicMock(), 1, "pro")
                    assert "error" in result


# ── is_stripe_configured ─────────────────────────────────────────────

class TestIsStripeConfigured:
    def test_not_configured(self):
        """GIVEN no keys WHEN checking THEN False."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", ""):
            assert is_stripe_configured() is False

    def test_configured(self):
        """GIVEN keys present WHEN checking THEN True."""
        with mock.patch("yuleosh.usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            assert is_stripe_configured() is True
