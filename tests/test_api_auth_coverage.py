#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Targeted tests for api/auth.py — covering internal helpers and routing.

Target: 70%+ statement coverage.
"""

import time
from unittest import mock

import pytest


class TestAuthInternalHelpers:
    """Test internal functions from auth.py."""

    def test_slugify_basic(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("Hello World") == "hello-world"

    def test_slugify_special_chars(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("Hello@#$World!") == "helloworld"

    def test_slugify_empty(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("") == ""

    def test_email_regex_valid(self):
        from yuleosh.api.auth import EMAIL_RE
        assert EMAIL_RE.match("user@example.com")
        assert EMAIL_RE.match("test.user+tag@sub.domain.co")

    def test_email_regex_invalid(self):
        from yuleosh.api.auth import EMAIL_RE
        assert not EMAIL_RE.match("not-an-email")
        assert not EMAIL_RE.match("@no-local.com")
        assert not EMAIL_RE.match("")

    def test_token_constants(self):
        from yuleosh.api.auth import TOKEN_TTL_HOURS
        assert TOKEN_TTL_HOURS == 24

    def test_rate_limit_constants(self):
        from yuleosh.api.auth import _MAX_SIGNIN_ATTEMPTS, _RATE_WINDOW_SECONDS
        assert _MAX_SIGNIN_ATTEMPTS == 10
        assert _RATE_WINDOW_SECONDS == 300

    @mock.patch("yuleosh.api.auth.bcrypt.hashpw")
    def test_hash_password(self, mock_hash):
        from yuleosh.api.auth import _hash_password

        mock_hash.return_value = b"$2b$12$hashedpassword123"
        result = _hash_password("testpass")
        assert result is not None
        assert isinstance(result, str)

    @mock.patch("yuleosh.api.auth.bcrypt.checkpw")
    def test_verify_password_correct(self, mock_check):
        from yuleosh.api.auth import _verify_password

        mock_check.return_value = True
        assert _verify_password("testpass", "hashed") is True

    @mock.patch("yuleosh.api.auth.bcrypt.checkpw")
    def test_verify_password_incorrect(self, mock_check):
        from yuleosh.api.auth import _verify_password

        mock_check.return_value = False
        assert _verify_password("wrongpass", "hashed") is False

    def test_generate_token(self):
        from yuleosh.api.auth import _generate_token

        token = _generate_token(user_id=1, org_id=2, email="test@example.com")
        assert token is not None
        assert isinstance(token, str)

    def test_decode_token_valid(self):
        from yuleosh.api.auth import _generate_token, _decode_token

        token = _generate_token(user_id=1, org_id=2, email="test@example.com")
        decoded = _decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == 1

    def test_decode_token_invalid(self):
        from yuleosh.api.auth import _decode_token

        result = _decode_token("invalid-token")
        assert result is None

    def test_extract_token_found(self):
        from yuleosh.api.auth import _extract_token

        result = _extract_token({"Authorization": "Bearer test-token-123"})
        assert result == "test-token-123"

    def test_extract_token_missing(self):
        from yuleosh.api.auth import _extract_token

        result = _extract_token({})
        assert result is None

    def test_extract_token_wrong_prefix(self):
        from yuleosh.api.auth import _extract_token

        result = _extract_token({"Authorization": "Basic dGVzdDpwYXNz"})
        assert result is None

    def test_extract_token_empty_header(self):
        from yuleosh.api.auth import _extract_token

        result = _extract_token({"Authorization": ""})
        assert result is None

    def test_check_rate_limit_first_request(self):
        from yuleosh.api.auth import _check_rate_limit
        import yuleosh.api.auth as auth_mod
        auth_mod._SIGNIN_RATE_LIMIT.clear()

        # Returns False = allowed (first request)
        assert _check_rate_limit("new@test.com") is False

    def test_check_rate_limit_exceeded(self):
        from yuleosh.api.auth import _check_rate_limit
        import yuleosh.api.auth as auth_mod

        auth_mod._SIGNIN_RATE_LIMIT.clear()
        auth_mod._SIGNIN_RATE_LIMIT["flood@test.com"] = (15, int(time.time()))

        # Returns True = blocked (exceeds max)
        assert _check_rate_limit("flood@test.com") is True

    def test_check_rate_limit_window_expired(self):
        from yuleosh.api.auth import _check_rate_limit
        import yuleosh.api.auth as auth_mod

        auth_mod._SIGNIN_RATE_LIMIT.clear()
        old_time = int(time.time()) - 600  # over 5 min ago
        auth_mod._SIGNIN_RATE_LIMIT["old@test.com"] = (15, old_time)

        # Returns False = allowed (window expired, counter reset)
        assert _check_rate_limit("old@test.com") is False

    def test_check_rate_limit_under_limit(self):
        from yuleosh.api.auth import _check_rate_limit
        import yuleosh.api.auth as auth_mod

        auth_mod._SIGNIN_RATE_LIMIT.clear()
        # Set 8 attempts (8 < 10 = under limit)
        auth_mod._SIGNIN_RATE_LIMIT["almost@test.com"] = (8, int(time.time()))

        # Returns False = allowed (8+1=9 < 10)
        assert _check_rate_limit("almost@test.com") is False


class TestAuthRouting:
    """Test handle_auth routing."""

    @mock.patch("yuleosh.api.auth.Store")
    def test_unknown_path(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("GET", "unknown", {}, {})
        assert result[1] == 404
        assert not result[0]["ok"]

    @mock.patch("yuleosh.api.auth.Store")
    def test_login_wrong_method(self, mock_store):
        from yuleosh.api.auth import handle_auth

        # auth returns 404 for unrecognized method/path combinations
        result = handle_auth("GET", "login", {}, {})
        assert result[1] == 404

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_wrong_method(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("GET", "register", {}, {})
        assert result[1] == 404

    @mock.patch("yuleosh.api.auth.Store")
    def test_logout_wrong_method(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("GET", "logout", {}, {})
        assert result[1] == 404

    @mock.patch("yuleosh.api.auth.Store")
    def test_me_wrong_method(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("PUT", "me", {}, {})
        assert result[1] == 404

    @mock.patch("yuleosh.api.auth.Store")
    def test_login_missing_body(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("POST", "login", {}, {})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_login_empty_body(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("POST", "login", {"email": "", "password": "x"}, {})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_login_bad_email(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("POST", "login", {"email": "bad", "password": "x"}, {})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_missing_fields(self, mock_store):
        from yuleosh.api.auth import handle_auth

        result = handle_auth("POST", "register", {}, {})
        assert result[1] == 400

    def test_user_response_with_org(self):
        from yuleosh.api.auth import _user_response

        user = {"id": 1, "email": "u@t.com", "display_name": "Test"}
        org = {"id": 10, "name": "TestOrg"}
        result = _user_response(user, org)
        assert result["email"] == "u@t.com"
        assert result["org"]["id"] == 10
        assert result["org"]["name"] == "TestOrg"

    def test_user_response_without_org(self):
        from yuleosh.api.auth import _user_response

        user = {"id": 2, "email": "u2@t.com", "display_name": "Test2"}
        org = {"id": 0, "name": "", "slug": ""}
        result = _user_response(user, org)
        assert result["email"] == "u2@t.com"


class TestAuthRegisterValidation:
    """Test the inline validation in _handle_register."""

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_missing_email(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({"password": "pass123", "display_name": "T"})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_missing_password(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({"email": "x@y.com", "display_name": "T"})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_missing_display_name(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({"email": "x@y.com", "password": "pass123!"})
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_bad_email_format(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({
            "email": "not-email",
            "password": "securePass1!",
            "display_name": "Test User",
        })
        assert result[1] == 400

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_weak_password(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({
            "email": "new@test.com",
            "password": "ab",
            "display_name": "Test User",
        })
        # Password too short returns 400, not 422 (simplified validation)
        assert result[1] in (400, 422)

    @mock.patch("yuleosh.api.auth.Store")
    def test_register_empty_display_name(self, mock_store):
        from yuleosh.api.auth import _handle_register

        result = _handle_register({
            "email": "new@test.com",
            "password": "securePass1!",
            "display_name": "",
        })
        assert result[1] == 400
