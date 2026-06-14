"""Tests for src/usage/ — Usage metering and Stripe payment integration.

Uses mocking for store and stripe dependencies.
"""

import sys
import os
import json
from unittest import mock
from datetime import datetime, timedelta

import pytest

# Ensure we import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    """Create a mock PostgresStore with common methods."""
    store = mock.MagicMock()

    # Default: org exists with "community" tier
    store.get_organization_by_id.return_value = {
        "id": 1, "name": "TestOrg", "slug": "test-org",
        "tier": "community", "created_at": datetime.now().isoformat(),
    }

    # Default subscription: no stripe (trial)
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


# ---------------------------------------------------------------------------
# metering — Tier helpers
# ---------------------------------------------------------------------------

class TestGetOrgTier:
    """Tests for get_org_tier()."""

    def test_existing_org(self, mock_store):
        """Should return the org's configured tier."""
        from usage.metering import get_org_tier
        tier = get_org_tier(mock_store, 1)
        assert tier == "community"

    def test_nonexistent_org(self, mock_store):
        """Should return 'community' for missing org."""
        from usage.metering import get_org_tier
        mock_store.get_organization_by_id.return_value = None
        tier = get_org_tier(mock_store, 999)
        assert tier == "community"

    def test_pro_org(self, mock_store):
        """Should return 'pro' for pro-tier org."""
        from usage.metering import get_org_tier
        mock_store.get_organization_by_id.return_value = {
            "id": 2, "tier": "pro", "created_at": datetime.now().isoformat(),
        }
        tier = get_org_tier(mock_store, 2)
        assert tier == "pro"


class TestGetTrialStatus:
    """Tests for get_trial_status()."""

    def test_in_trial(self, mock_store):
        """New pro org without stripe sub should be in trial."""
        from usage.metering import get_trial_status
        # Org created today
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "tier": "pro",
            "created_at": datetime.now().isoformat(),
        }
        # No stripe sub
        mock_store.get_subscription.return_value = {
            "stripe_subscription_id": None,
        }

        status = get_trial_status(mock_store, 1)
        assert status["in_trial"] is True
        assert status["days_left"] == 14

    def test_no_trial_for_community(self, mock_store):
        """Community tier should not be in trial."""
        from usage.metering import get_trial_status
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "tier": "community",
            "created_at": datetime.now().isoformat(),
        }

        status = get_trial_status(mock_store, 1)
        assert status["in_trial"] is False

    def test_trial_expired(self, mock_store):
        """Org created more than 14 days ago should have expired trial."""
        from usage.metering import get_trial_status
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "tier": "pro",
            "created_at": old_date,
        }

        status = get_trial_status(mock_store, 1)
        assert status["in_trial"] is False
        assert status["days_left"] == 0

    def test_nonexistent_org(self, mock_store):
        """Missing org should return no trial."""
        from usage.metering import get_trial_status
        mock_store.get_organization_by_id.return_value = None

        status = get_trial_status(mock_store, 999)
        assert status["in_trial"] is False


class TestCheckTierLimit:
    """Tests for check_tier_limit()."""

    def test_within_limit(self, mock_store):
        """Should return allowed=True when under the limit."""
        from usage.metering import check_tier_limit
        mock_store.get_monthly_usage.return_value = {
            "project_count": 0, "pipeline_runs": 5,
            "llm_tokens": 1000, "storage_mb": 10,
        }

        result = check_tier_limit(mock_store, 1, "pipeline_runs")
        assert result["allowed"] is True
        assert result["limit"] == 100  # community max

    def test_exceeds_limit(self, mock_store):
        """Should return allowed=False when over the limit."""
        from usage.metering import check_tier_limit
        mock_store.get_monthly_usage.return_value = {
            "pipeline_runs": 99999,
        }

        result = check_tier_limit(mock_store, 1, "pipeline_runs")
        assert result["allowed"] is False
        assert "limit reached" in result["message"]

    def test_unknown_resource(self, mock_store):
        """Unknown resource should always be allowed."""
        from usage.metering import check_tier_limit
        result = check_tier_limit(mock_store, 1, "unknown_resource")
        assert result["allowed"] is True


class TestRecordPipelineRun:
    """Tests for record_pipeline_run()."""

    def test_records_pipeline_run(self, mock_store):
        """Should record a pipeline run with llm_tokens."""
        from usage.metering import record_pipeline_run
        record_pipeline_run(mock_store, 1, 1, llm_tokens=500)
        # record_usage should be called twice (run + tokens)
        assert mock_store.record_usage.call_count == 2

    def test_records_run_only(self, mock_store):
        """Should record only the pipeline run when no tokens."""
        from usage.metering import record_pipeline_run
        record_pipeline_run(mock_store, 1, 1)
        assert mock_store.record_usage.call_count == 1


class TestGetUsageSummary:
    """Tests for get_usage_summary()."""

    def test_returns_summary(self, mock_store):
        """Should return full usage summary dict."""
        from usage.metering import get_usage_summary
        result = get_usage_summary(mock_store, 1)
        assert "tier" in result
        assert "usage" in result
        assert "projects" in result["usage"]
        assert "pipeline_runs" in result["usage"]
        assert "llm_tokens" in result["usage"]
        assert "storage_mb" in result["usage"]
        assert "llm_enabled" in result
        assert "trial" in result

    def test_llm_enabled_for_pro(self, mock_store):
        """LLM should be enabled for pro tier."""
        from usage.metering import get_usage_summary
        mock_store.get_organization_by_id.return_value = {
            "id": 1, "tier": "pro", "created_at": datetime.now().isoformat(),
        }
        result = get_usage_summary(mock_store, 1)
        assert result["llm_enabled"] is True

    def test_llm_disabled_for_community(self, mock_store):
        """LLM should be disabled for community tier."""
        from usage.metering import get_usage_summary
        result = get_usage_summary(mock_store, 1)
        assert result["llm_enabled"] is False


# ---------------------------------------------------------------------------
# stripe_gateway — Stripe integration
# ---------------------------------------------------------------------------

class TestStripeConfigured:
    """Tests for is_stripe_configured()."""

    def test_not_configured(self):
        """Should return False when no stripe key."""
        from usage.stripe_gateway import is_stripe_configured
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("usage.stripe_gateway.STRIPE_SECRET_KEY", ""):
                assert is_stripe_configured() is False

    def test_configured(self):
        """Should return True when stripe key is set."""
        from usage.stripe_gateway import is_stripe_configured
        with mock.patch("usage.stripe_gateway.STRIPE_SECRET_KEY", "sk_test_xxx"):
            assert is_stripe_configured() is True


class TestCreateCheckoutSession:
    """Tests for create_checkout_session()."""

    def test_not_configured_returns_error(self):
        """Should return error when stripe not configured."""
        from usage.stripe_gateway import create_checkout_session
        with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=False):
            result = create_checkout_session(1, "pro", "user@test.com", "test-org")
        assert "error" in result
        assert "not configured" in result["error"]

    def test_missing_price_id(self):
        """Should return error when tier has no price ID configured."""
        # Mock stripe as importable but not called because we fail early
        with mock.patch.dict("sys.modules", {"stripe": mock.MagicMock()}):
            from usage.stripe_gateway import create_checkout_session
            with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=True):
                result = create_checkout_session(1, "pro", "user@test.com", "test-org")
            assert "error" in result
            assert "price ID" in result["error"]

    def test_successful_session(self):
        """Should return checkout URL on success."""
        mock_stripe = mock.MagicMock()
        mock_stripe.checkout.Session.create.return_value = mock.MagicMock(
            url="https://checkout.stripe.com/test",
            id="cs_test_abc",
        )
        with mock.patch.dict("sys.modules", {"stripe": mock_stripe}):
            # Patch TIERS to include a price_id for pro
            from usage import metering
            original = metering.TIERS.copy()
            metering.TIERS["pro"]["stripe_price_id"] = "price_pro_123"

            from usage.stripe_gateway import create_checkout_session
            with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=True):
                result = create_checkout_session(1, "pro", "user@test.com", "test-org")

            assert "url" in result
            assert "session_id" in result
            assert "stripe.com" in result["url"]

            # Restore
            metering.TIERS.clear()
            metering.TIERS.update(original)


class TestHandleStripeWebhook:
    """Tests for handle_stripe_webhook()."""

    def test_not_configured(self):
        """Should return error when stripe not configured."""
        from usage.stripe_gateway import handle_stripe_webhook
        with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=False):
            result = handle_stripe_webhook(b"{}", "sig")
        assert result["status"] == "error"

    def test_verification_failure(self):
        """Should return error when signature verification fails."""
        mock_stripe = mock.MagicMock()
        mock_stripe.Webhook.construct_event.side_effect = ValueError("Invalid signature")

        with mock.patch.dict("sys.modules", {"stripe": mock_stripe}):
            from usage.stripe_gateway import handle_stripe_webhook
            with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=True):
                result = handle_stripe_webhook(b"{}", "bad_sig")

        assert result["status"] == "error"
        assert "verification failed" in result["message"]

    def test_checkout_completed(self):
        """Should handle checkout.session.completed."""
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"org_id": "1", "org_slug": "test-org", "tier": "pro"},
                    "subscription": "sub_abc",
                    "customer": "cus_xyz",
                }
            },
        }
        mock_stripe = mock.MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event

        with mock.patch.dict("sys.modules", {"stripe": mock_stripe}):
            from usage.stripe_gateway import handle_stripe_webhook
            from yuleosh.store import Store  # noqa: used by import inside handler

            with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=True), \
                 mock.patch("yuleosh.store.Store") as MockStore:
                mock_store_instance = mock.MagicMock()
                MockStore.return_value = mock_store_instance
                result = handle_stripe_webhook(b"{}", "valid_sig")

        assert result["status"] == "ok"
        assert result["handled"] is True
        # Verify store methods were called
        mock_store_instance.upsert_subscription.assert_called_once()
        mock_store_instance.update_org_tier.assert_called_once_with(1, "pro")

    def test_subscription_deleted(self):
        """Should downgrade tier when subscription is deleted."""
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {"id": "sub_del"},
            },
        }
        mock_stripe = mock.MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_store_instance = mock.MagicMock()
        mock_store_instance.get_org_by_stripe_subscription.return_value = {"id": 1}

        with mock.patch.dict("sys.modules", {"stripe": mock_stripe}):
            from usage.stripe_gateway import handle_stripe_webhook

            with mock.patch("usage.stripe_gateway.is_stripe_configured", return_value=True), \
                 mock.patch("yuleosh.store.Store") as MockStore:
                MockStore.return_value = mock_store_instance
                result = handle_stripe_webhook(b"{}", "valid_sig")

        assert result["status"] == "ok"
        assert result["handled"] is True
        mock_store_instance.update_org_tier.assert_called_once_with(1, "community")
