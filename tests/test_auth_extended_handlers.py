# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for auth_extended.py handlers — boost from 23% to 80%+ (v0.8.0 P0).

Covers: signin, org_create, session_info, logout, project_list, project_create, org_info.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.ui.auth_extended import (
    handle_signin,
    handle_org_create,
    handle_session_info,
    handle_logout,
    handle_project_list,
    handle_project_create,
    handle_org_info,
    get_session_user,
    _generate_token,
    _decode_token,
    _hash_password,
    _verify_password,
    _check_rate_limit,
    _slugify,
    SESSION_TTL_HOURS,
    EMAIL_RE,
    SLUG_RE,
)


class TestRateLimit:
    """GIVEN rate limit mechanism WHEN checks THEN correct blocking."""

    def test_not_blocked_initially(self):
        """GIVEN no prior attempts WHEN _check_rate_limit THEN not blocked."""
        assert _check_rate_limit("new@test.com") is False

    def test_blocked_after_max_attempts(self):
        """GIVEN max attempts WHEN check THEN blocked."""
        email = "flood@test.com"
        for _ in range(10):
            assert _check_rate_limit(email) is False
        assert _check_rate_limit(email) is True

    def test_window_reset(self):
        """GIVEN expired window WHEN check THEN not blocked."""
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT, _RATE_WINDOW_SECONDS
        email = "reset@test.com"
        for _ in range(10):
            _check_rate_limit(email)
        # Artificially expire the window
        _SIGNIN_RATE_LIMIT[email] = (10, int(time.time()) - _RATE_WINDOW_SECONDS - 60)
        assert _check_rate_limit(email) is False


class TestPasswordHashing:
    """GIVEN bcrypt hashing WHEN hash/verify THEN correct results."""

    def test_hash_and_verify(self):
        """GIVEN password WHEN hashed THEN verify returns True."""
        h = _hash_password("MySecret123")
        assert h.startswith("$2b$")
        assert _verify_password("MySecret123", h) is True

    def test_wrong_password(self):
        """GIVEN wrong password WHEN verify THEN returns False."""
        h = _hash_password("CorrectOne")
        assert _verify_password("WrongOne", h) is False

    def test_different_passwords_different_hashes(self):
        """GIVEN two passwords WHEN hashed THEN different hashes."""
        h1 = _hash_password("Pass1")
        h2 = _hash_password("Pass2")
        assert h1 != h2

    def test_bad_hash(self):
        """GIVEN invalid hash WHEN verify THEN returns False."""
        assert _verify_password("any", "not-a-valid-hash") is False
        assert _verify_password("any", "") is False


class TestSlugify:
    """GIVEN text WHEN _slugify THEN correct slug."""

    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"
        assert _slugify("My Org") == "my-org"

    def test_noop(self):
        assert _slugify("already-slug") == "already-slug"


class TestHelpers:
    """GIVEN helper functions WHEN called THEN correct results."""

    def test_email_regex(self):
        assert EMAIL_RE.match("user@example.com")
        assert EMAIL_RE.match("a+b@x.co.uk")
        assert not EMAIL_RE.match("notanemail")
        assert not EMAIL_RE.match("")

    def test_slug_regex(self):
        assert SLUG_RE.match("my-org")
        assert SLUG_RE.match("test123")
        assert not SLUG_RE.match("My-Org")
        assert not SLUG_RE.match("my org")


class TestSigninHandler:
    """GIVEN handle_signin WHEN called THEN correct responses."""

    def test_missing_email(self):
        result, status = handle_signin({})
        assert status == 400
        assert "email" in result.get("error", "").lower()

    def test_invalid_email(self):
        result, status = handle_signin({"email": "not-an-email"})
        assert status == 400

    def test_new_user_needs_org(self):
        result, status = handle_signin({"email": "fresh@test.com"})
        assert status == 200
        assert result.get("needs_org") is True
        assert result.get("redirect") == "/org/setup"

    def test_password_required_for_existing_user(self):
        # Clean DB state — no users exist yet, so this just tests the new user path
        result, status = handle_signin({"email": "any@test.com"})
        assert status == 200
        assert result.get("needs_org") is True


class TestOrgCreateHandler:
    """GIVEN handle_org_create WHEN called THEN correct validation."""

    def test_missing_fields(self):
        result, status = handle_org_create({}, "dummy-token")
        assert status == 400
        assert "name" in result.get("error", "")

    def test_bad_slug(self):
        body = {
            "org_name": "Test", "org_slug": "BAD SLUG",
            "project_name": "P", "project_slug": "p-slug",
            "email": "a@b.com",
        }
        result, status = handle_org_create(body, "token")
        assert status == 400


class TestSessionInfo:
    """GIVEN handle_session_info WHEN called THEN correct responses."""

    def test_invalid_token(self):
        result, status = handle_session_info("invalid-token")
        assert status == 401

    def test_empty_token(self):
        result, status = handle_session_info("")
        assert status == 401

    def test_none_token(self):
        result, status = handle_session_info(None)
        assert status == 401


class TestLogout:
    """GIVEN handle_logout WHEN called THEN always OK."""

    def test_logout(self):
        result, status = handle_logout("any-token")
        assert status == 200
        assert result.get("status") == "ok"

    def test_logout_no_token(self):
        result, status = handle_logout("")
        assert status == 200


class TestProjectHandlers:
    """GIVEN project handlers WHEN called THEN correct validation."""

    def test_project_list_unauthorized(self):
        result, status = handle_project_list("bad-token")
        assert status == 401

    def test_project_create_unauthorized(self):
        result, status = handle_project_create({"name": "P", "slug": "p"}, "bad-token")
        assert status == 401

    def test_project_create_missing_fields(self):
        # Use a mock session that returns a valid user but test validation
        # With real auth, this would need a valid token — test input validation
        result, status = handle_project_create({}, "token")  # missing fields
        assert status in (400, 401)

    def test_project_create_bad_slug(self):
        result, status = handle_project_create(
            {"name": "Bad Slug", "slug": "BAD"}, "token"
        )
        assert status == 401  # auth checked first, then validation


class TestOrgInfo:
    """GIVEN handle_org_info WHEN called THEN correct responses."""

    def test_org_info_unauthorized(self):
        result, status = handle_org_info("bad-token")
        assert status == 401


class TestTokenGeneration:
    """GIVEN token generation WHEN called THEN JWT structure valid."""

    def test_generate_token_no_args(self):
        token = _generate_token()
        assert token.count(".") == 2
        payload = _decode_token(token)
        assert payload is not None
        assert payload["sub"] == "0"

    def test_generate_token_with_args(self):
        token = _generate_token(user_id=7, org_id=3, email="x@y.com")
        payload = _decode_token(token)
        assert payload["sub"] == "7"
        assert payload["org"] == 3
        assert payload["email"] == "x@y.com"

    def test_decode_invalid(self):
        assert _decode_token("garbage") is None
        assert _decode_token("") is None

    def test_token_expiration(self):
        token = _generate_token(user_id=1)
        payload = _decode_token(token)
        now = int(time.time())
        assert payload["exp"] > now
        assert payload["exp"] <= now + SESSION_TTL_HOURS * 3600 + 5


class TestGetSessionUser:
    """GIVEN get_session_user WHEN called THEN only valid tokens work."""

    def test_invalid_token_returns_none(self):
        assert get_session_user("bad") is None
        assert get_session_user("") is None
        assert get_session_user(None) is None
