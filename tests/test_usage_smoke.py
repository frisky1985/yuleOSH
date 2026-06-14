"""Smoke tests for yuleosh.usage — metering and stripe."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestUsage:
    def test_import(self):
        import yuleosh.usage
        assert hasattr(yuleosh.usage, "metering")

    def test_metering_functions(self):
        from yuleosh.usage.metering import (
            record_pipeline_run, check_tier_limit,
            get_usage_summary, get_org_tier
        )
        assert callable(record_pipeline_run)
        assert callable(check_tier_limit)

    def test_stripe_functions(self):
        from yuleosh.usage.stripe_gateway import (
            is_stripe_configured, create_checkout_session,
            handle_stripe_webhook
        )
        assert callable(is_stripe_configured)
        assert callable(create_checkout_session)

    def test_tiers(self):
        from yuleosh.usage.metering import TIERS, TRIAL_DAYS
        assert isinstance(TIERS, dict)
        assert isinstance(TRIAL_DAYS, int)
