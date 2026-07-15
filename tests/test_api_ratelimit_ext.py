"""Tests for api/ratelimit.py — Rate limiter."""

import time
import pytest
from yuleosh.api.ratelimit import (
    check_rate_limit,
    get_remaining,
    reset,
    _RATE_LIMIT,
)


class TestRateLimit:
    """Test rate limiter."""

    def setup_method(self):
        reset()

    def test_allowed(self):
        """First request is allowed."""
        allowed, retry = check_rate_limit("1.2.3.4")
        assert allowed is True
        assert retry == 0

    def test_remaining(self):
        """get_remaining returns correct count."""
        reset()
        allowed, _ = check_rate_limit("10.0.0.1")
        assert allowed
        remaining = get_remaining("10.0.0.1")
        assert remaining == _RATE_LIMIT - 1

    def test_exceed_limit(self):
        """Exceeding limit blocks."""
        reset()
        ip = "10.0.0.2"
        for _ in range(_RATE_LIMIT):
            allowed, _ = check_rate_limit(ip)
            assert allowed

        allowed, retry = check_rate_limit(ip)
        assert allowed is False
        assert retry > 0

    def test_get_remaining_exceeded(self):
        """get_remaining returns 0 when exceeded."""
        reset()
        ip = "10.0.0.3"
        for _ in range(_RATE_LIMIT):
            check_rate_limit(ip)

        remaining = get_remaining(ip)
        assert remaining == 0

    def test_different_ips_independent(self):
        """Different IPs don't affect each other."""
        reset()
        ip1 = "10.0.0.10"
        ip2 = "10.0.0.11"

        for _ in range(_RATE_LIMIT):
            check_rate_limit(ip1)

        allowed, _ = check_rate_limit(ip2)
        assert allowed is True

    def test_reset_clears(self):
        """reset() clears all state."""
        reset()
        ip = "10.0.0.20"
        check_rate_limit(ip)
        reset()

        remaining = get_remaining(ip)
        assert remaining == _RATE_LIMIT

    def test_retry_after_positive(self):
        """retry_after returns positive when blocked."""
        reset()
        ip = "10.0.0.30"
        for _ in range(_RATE_LIMIT):
            check_rate_limit(ip)

        _, retry = check_rate_limit(ip)
        assert retry >= 1
