"""Tests for JWT auth integration (v0.8.0)."""
import os
import sys
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ui.auth_extended import (
    _generate_token,
    _decode_token,
    JWT_SECRET,
    JWT_ALGORITHM,
    SESSION_TTL_HOURS,
)


class TestJWTToken:
    """GIVEN JWT token generation WHEN created THEN can decode with claims."""

    def test_generate_token_has_claims(self):
        """GIVEN user info WHEN _generate_token THEN JWT with sub/org/email."""
        token = _generate_token(user_id=42, org_id=7, email="test@example.com")
        payload = _decode_token(token)
        assert payload["sub"] == "42"
        assert payload["org"] == 7
        assert payload["email"] == "test@example.com"

    def test_token_has_expiration(self):
        """GIVEN a token WHEN decoded THEN has exp claim ~72h in future."""
        token = _generate_token(user_id=1)
        payload = _decode_token(token)
        now = int(time.time())
        expected_exp = now + SESSION_TTL_HOURS * 3600
        # Allow 5s tolerance
        assert abs(payload["exp"] - expected_exp) < 5

    def test_init_token_string(self):
        """GIVEN no user_id WHEN _generate_token THEN still returns valid JWT."""
        token = _generate_token()
        payload = _decode_token(token)
        assert payload["sub"] == "0"
        assert payload["org"] == 0

    def test_decode_invalid_token(self):
        """GIVEN garbage token WHEN _decode_token THEN returns None."""
        assert _decode_token("not.a.real.jwt") is None
        assert _decode_token("") is None
        assert _decode_token("a.b.c") is None

    def test_decode_expired_token(self):
        """GIVEN a token with exp in past WHEN _decode_token THEN returns None."""
        import jwt as pyjwt
        now = int(time.time())
        expired_payload = {"sub": "1", "iat": now - 99999, "exp": now - 3600}
        expired_token = pyjwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        assert _decode_token(expired_token) is None

    def test_decode_wrong_secret(self):
        """GIVEN token signed with wrong secret WHEN _decode_token THEN None."""
        import jwt as pyjwt
        payload = {"sub": "1", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        wrong_token = pyjwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        assert _decode_token(wrong_token) is None

    def test_token_is_string(self):
        """GIVEN token generation WHEN returns THEN Python string."""
        token = _generate_token(1, 2, "x@y.com")
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT format: header.payload.signature
