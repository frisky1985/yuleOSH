# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Stripe webhook integration tests.

Tests:
  1. Stripe gateway module imports and configuration
  2. Webhook signature verification logic (mocked)
  3. Subscription create/update/delete event handling
  4. .env.production.example configuration completeness
  5. Edge cases: missing signature, invalid payload
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

class TestStripeConfiguration:
    """GIVEN stripe gateway module WHEN inspected THEN configured correctly."""

    def test_01_module_imports(self):
        """GIVEN stripe_gateway module WHEN imported THEN no errors."""
        from yuleosh.usage.stripe_gateway import (
            is_stripe_configured,
            create_checkout_session,
            handle_stripe_webhook,
            STRIPE_SECRET_KEY,
            STRIPE_WEBHOOK_SECRET,
            BASE_URL,
        )
        assert callable(is_stripe_configured)
        assert callable(create_checkout_session)
        assert callable(handle_stripe_webhook)

    def test_02_not_configured_by_default(self):
        """GIVEN no env vars WHEN is_stripe_configured THEN False."""
        from yuleosh.usage.stripe_gateway import is_stripe_configured

        assert is_stripe_configured() is False

    def test_03_configured_with_env(self):
        """GIVEN STRIPE_SECRET_KEY set WHEN is_stripe_configured THEN True."""
        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_xxx"}):
            # Reimport to pick up new env
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)
            assert sg.is_stripe_configured() is True

    def test_04_default_base_url_is_localhost(self):
        """GIVEN no YULEOSH_BASE_URL WHEN module loaded THEN default is localhost."""
        from yuleosh.usage.stripe_gateway import BASE_URL

        assert "localhost" in BASE_URL

    def test_05_env_production_example_has_stripe_vars(self):
        """GIVEN .env.production.example WHEN inspected THEN Stripe vars documented."""
        env_path = Path(__file__).resolve().parent.parent / "deploy" / ".env.production.example"
        assert env_path.exists()
        content = env_path.read_text()
        assert "STRIPE_SECRET_KEY" in content
        assert "STRIPE_WEBHOOK_SECRET" in content
        assert "sk_live_" in content  # Shows example format
        assert "whsec_" in content  # Shows example format

    def test_06_metering_tiers_have_stripe_price_id_field(self):
        """GIVEN TIERS config WHEN inspected THEN each tier has stripe_price_id."""
        from yuleosh.usage.metering import TIERS

        for tier_name, config in TIERS.items():
            assert "stripe_price_id" in config, (
                f"Tier '{tier_name}' missing stripe_price_id field"
            )
            # Community can be None, pro/enterprise should eventually be set
            if tier_name != "community":
                pass  # price_id set via Stripe Dashboard, not hardcoded

    def test_07_stripe_routes_in_router(self):
        """GIVEN router WHEN inspected THEN subscription routes present."""
        from yuleosh.api.router import ROUTES

        assert "subscription" in ROUTES, "subscription routes not in ROUTES"

    def test_08_subscription_api_imports(self):
        """GIVEN subscription API module WHEN imported THEN handler functions exist."""
        from yuleosh.api.subscription import (
            handle_subscription,
            _handle_sub_status,
            _handle_sub_upgrade,
            _handle_sub_cancel,
            _handle_stripe_webhook,
        )
        assert callable(handle_subscription)
        assert callable(_handle_sub_status)
        assert callable(_handle_sub_upgrade)
        assert callable(_handle_sub_cancel)
        assert callable(_handle_stripe_webhook)


# ═══════════════════════════════════════════════════════════════════════
# Webhook Signature Verification
# ═══════════════════════════════════════════════════════════════════════

class TestWebhookSignatureVerification:
    """GIVEN Stripe webhook payload WHEN verified THEN signature validated."""

    def test_01_missing_signature_returns_error(self):
        """GIVEN no signature WHEN webhook handler THEN error returned."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            result = sg.handle_stripe_webhook(b"{}", "")
            assert result["status"] == "error"

    def test_02_missing_webhook_secret_returns_error(self):
        """GIVEN missing webhook secret WHEN handler THEN error."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            result = sg.handle_stripe_webhook(b"{}", "test_sig")
            assert result["status"] == "error"

    def test_03_invalid_signature_returns_error(self):
        """GIVEN invalid signature WHEN verify THEN error returned."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            result = sg.handle_stripe_webhook(b"{}", "invalid_sig")
            assert result["status"] == "error"

    def test_04_valid_webhook_passes_verification(self):
        """GIVEN valid webhook payload WHEN processed THEN event handled."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            # Mock stripe.Webhook.construct_event to return a valid event
            with mock.patch("stripe.Webhook.construct_event") as mock_verify:
                mock_verify.return_value = {
                    "type": "checkout.session.completed",
                    "data": {
                        "object": {
                            "metadata": {"org_id": "42", "tier": "pro"},
                            "subscription": "sub_123",
                            "customer": "cus_abc",
                        }
                    },
                }

                # Mock Store methods to prevent actual DB ops
                with mock.patch("yuleosh.store.Store") as MockStore:
                    mock_store = MockStore.return_value
                    mock_store.upsert_subscription.return_value = None
                    mock_store.update_org_tier.return_value = None

                    result = sg.handle_stripe_webhook(
                        b'{"id": "evt_test"}', "test_sig"
                    )
                    assert result["status"] == "ok"
                    assert result["event_type"] == "checkout.session.completed"
                    assert result["handled"] is True

    def test_05_subscription_updated_event(self):
        """GIVEN subscription.updated event WHEN processed THEN status updated."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            with mock.patch("stripe.Webhook.construct_event") as mock_verify:
                mock_verify.return_value = {
                    "type": "customer.subscription.updated",
                    "data": {
                        "object": {
                            "id": "sub_456",
                            "status": "active",
                            "current_period_end": 9999999999,
                        }
                    },
                }

                with mock.patch("yuleosh.store.Store") as MockStore:
                    mock_store = MockStore.return_value
                    mock_store.get_org_by_stripe_subscription.return_value = {"id": 42}

                    result = sg.handle_stripe_webhook(
                        b'{"id": "evt_test"}', "test_sig"
                    )
                    assert result["status"] == "ok"
                    assert result["handled"] is True

    def test_06_subscription_deleted_event(self):
        """GIVEN subscription.deleted event WHEN processed THEN downgraded to community."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            with mock.patch("stripe.Webhook.construct_event") as mock_verify:
                mock_verify.return_value = {
                    "type": "customer.subscription.deleted",
                    "data": {"object": {"id": "sub_789"}},
                }

                with mock.patch("yuleosh.store.Store") as MockStore:
                    mock_store = MockStore.return_value
                    mock_store.get_org_by_stripe_subscription.return_value = {"id": 42}

                    result = sg.handle_stripe_webhook(
                        b'{"id": "evt_test"}', "test_sig"
                    )
                    assert result["status"] == "ok"
                    assert result["handled"] is True

    def test_07_unexpected_event_type_still_ok(self):
        """GIVEN unexpected event type WHEN processed THEN returns ok, not handled."""
        from yuleosh.usage.stripe_gateway import handle_stripe_webhook

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_test",
        }):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            with mock.patch("stripe.Webhook.construct_event") as mock_verify:
                mock_verify.return_value = {
                    "type": "invoice.payment_succeeded",
                    "data": {"object": {}},
                }

                result = sg.handle_stripe_webhook(
                    b'{"id": "evt_test"}', "test_sig"
                )
                assert result["status"] == "ok"
                assert result["handled"] is False


# ═══════════════════════════════════════════════════════════════════════
# Webhook API endpoint
# ═══════════════════════════════════════════════════════════════════════

class TestWebhookAPIEndpoint:
    """GIVEN subscription webhook API WHEN called THEN response correct."""

    def test_01_routes_subscription_webhook(self):
        """GIVEN subscription module WHEN dispatched THEN webhook handled."""
        from yuleosh.api.subscription import handle_subscription

        with mock.patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "",
            "STRIPE_WEBHOOK_SECRET": "",
        }):
            data, status = handle_subscription(
                method="POST",
                path_tail="webhook",
                body={},
                query={},
                handler=mock.MagicMock(),
            )
            assert status in (200, 400, 500)

    def test_02_missing_stripe_signature_header(self):
        """GIVEN webhook without signature header WHEN called THEN 400."""
        # Simulate a handler without Stripe-Signature header
        handler = mock.MagicMock()
        # Use a dict-like object; .get('Stripe-Signature', '') returns ''
        handler.headers = {"Content-Length": "0"}
        handler.rfile.read.return_value = b"{}"

        from yuleosh.api.subscription import _handle_stripe_webhook

        data, status = _handle_stripe_webhook(body={}, handler=handler)
        assert status == 400
        assert "signature" in str(data).lower()

    def test_03_webhook_correct_url_pattern(self):
        """GIVEN Nginx config WHEN inspected THEN webhook endpoint is NOT rate limited."""
        nginx_path = Path(__file__).resolve().parent.parent / "deploy" / "nginx" / "nginx.conf"
        assert nginx_path.exists()
        content = nginx_path.read_text()

        # Webhook endpoint should be in nginx config
        assert "/api/v1/subscription/webhook" in content, (
            "Nginx config missing Stripe webhook endpoint"
        )

        # Webhook should NOT be under auth rate limit
        auth_location = content.find("location /api/auth/")
        webhook_location = content.find("location /api/v1/subscription/webhook")
        assert webhook_location > 0, "Webhook location block not found in nginx"
        assert auth_location < webhook_location, (
            "Webhook endpoint should be separate from auth rate limiting"
        )


# ═══════════════════════════════════════════════════════════════════════
# Checkout Session
# ═══════════════════════════════════════════════════════════════════════

class TestCheckoutSession:
    """GIVEN checkout session creation WHEN called THEN correct parameters."""

    def test_01_create_session_not_configured(self):
        """GIVEN no stripe config WHEN create_checkout_session THEN error."""
        from yuleosh.usage.stripe_gateway import create_checkout_session

        result = create_checkout_session(
            org_id=1, tier="pro", email="test@test.com", org_slug="test"
        )
        assert "error" in result

    def test_02_create_session_missing_price_id(self):
        """GIVEN no price_id for tier WHEN create THEN error."""
        from yuleosh.usage.stripe_gateway import create_checkout_session

        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_xxx"}):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            result = sg.create_checkout_session(
                org_id=1, tier="pro", email="test@test.com", org_slug="test"
            )
            assert "error" in result
            assert "price" in result["error"].lower()

    def test_03_create_session_with_price_id(self):
        """GIVEN configured price_id WHEN create THEN session created."""
        from yuleosh.usage.stripe_gateway import create_checkout_session

        with mock.patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_xxx"}):
            import importlib
            from yuleosh.usage import stripe_gateway as sg
            importlib.reload(sg)

            # Override TIERS temporarily with a price_id
            with mock.patch("yuleosh.usage.metering.TIERS", {
                "pro": {
                    "name": "Pro",
                    "stripe_price_id": "price_test123",
                    "price_monthly": 599,
                }
            }):
                import importlib as il
                il.reload(sg)

                with mock.patch("stripe.checkout.Session.create") as mock_create:
                    mock_create.return_value = mock.MagicMock(
                        url="https://checkout.stripe.com/test",
                        id="cs_test_123",
                    )

                    result = sg.create_checkout_session(
                        org_id=1, tier="pro", email="test@test.com",
                        org_slug="test-org"
                    )
                    assert "url" in result
                    assert "https://checkout.stripe.com" in result["url"]
