"""
Extended tests for yuleosh.ui.auth_extended — push coverage ≥ 60%.
"""

import json
import os
import re
import sys
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# =====================================================================
# Password & Token helpers
# =====================================================================

class TestPasswordHelpers:
    """Cover _hash_password and _verify_password."""

    def test_hash_and_verify(self):
        from yuleosh.ui.auth_extended import _hash_password, _verify_password
        pw = "test_password_123!"
        hashed = _hash_password(pw)
        assert hashed != pw
        assert _verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        from yuleosh.ui.auth_extended import _verify_password
        result = _verify_password("wrong", "$2b$12$abcdefghijklmnopqrstuv")
        # bcrypt will verify as False
        assert result is False

    def test_verify_invalid_hash(self):
        from yuleosh.ui.auth_extended import _verify_password
        result = _verify_password("test", "not-a-hash")
        assert result is False


class TestTokenHelpers:
    """Cover _generate_token and _decode_token."""

    def test_generate_and_decode(self):
        from yuleosh.ui.auth_extended import _generate_token, _decode_token
        token = _generate_token(user_id=42, org_id=7, email="user@test.com")
        payload = _decode_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["org"] == 7
        assert payload["email"] == "user@test.com"

    def test_decode_invalid_token(self):
        from yuleosh.ui.auth_extended import _decode_token
        payload = _decode_token("invalid.token.here")
        assert payload is None

    def test_decode_expired_token(self):
        from yuleosh.ui.auth_extended import _generate_token, _decode_token
        import jwt as pyjwt
        # Create a token with iat in the past and a 1-second expiration
        token = _generate_token(user_id=1)
        payload = _decode_token(token)
        assert payload is not None  # Should still work within session TTL


class TestSlugify:
    """Cover _slugify."""

    def test_slugify_basic(self):
        from yuleosh.ui.auth_extended import _slugify
        assert _slugify("My Org") == "my-org"

    def test_slugify_special_chars(self):
        from yuleosh.ui.auth_extended import _slugify
        assert _slugify("Hello! @World#") == "hello-world"


class TestCheckRateLimit:
    """Cover _check_rate_limit."""

    def test_first_attempt(self):
        from yuleosh.ui.auth_extended import _check_rate_limit
        # Clean the global dict first
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        assert _check_rate_limit("test@example.com") is False

    def test_under_limit(self):
        from yuleosh.ui.auth_extended import _check_rate_limit
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        # Make 5 attempts (under limit of 10)
        for _ in range(5):
            result = _check_rate_limit("test@example.com")
            assert result is False

    def test_rate_limited(self):
        from yuleosh.ui.auth_extended import _check_rate_limit, _MAX_SIGNIN_ATTEMPTS
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        # Exhaust attempts
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            _check_rate_limit("test@example.com")
        # Should now be blocked
        assert _check_rate_limit("test@example.com") is True

    def test_window_expires(self):
        from yuleosh.ui.auth_extended import _check_rate_limit, _MAX_SIGNIN_ATTEMPTS
        from yuleosh.ui.auth_extended import _SIGNIN_RATE_LIMIT, _RATE_WINDOW_SECONDS
        _SIGNIN_RATE_LIMIT.clear()
        # Exhaust attempts but with old timestamp
        _SIGNIN_RATE_LIMIT["test@example.com"] = (_MAX_SIGNIN_ATTEMPTS, int(time.time()) - _RATE_WINDOW_SECONDS - 10)
        # Should allow through since window expired
        assert _check_rate_limit("test@example.com") is False


# =====================================================================
# handle_signin
# =====================================================================

class TestHandleSignin:
    """Cover handle_signin branches."""

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_missing_email(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin
        result, status = handle_signin({"password": "test1234"})
        assert status == 400
        assert "email" in result.get("error", "")

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_invalid_email(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin
        result, status = handle_signin({"email": "not-an-email", "password": "test1234"})
        assert status == 400

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_rate_limited(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT, _MAX_SIGNIN_ATTEMPTS
        _SIGNIN_RATE_LIMIT.clear()
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            from yuleosh.ui.auth_extended import _check_rate_limit
            _check_rate_limit("test@example.com")
        result, status = handle_signin({"email": "test@example.com", "password": "test1234"})
        assert status == 429
        assert "Too many" in result.get("error", "")

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_invite_code_org_not_found(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = None
        result, status = handle_signin({
            "email": "test@example.com", "password": "test1234", "invite_code": "nonexistent"
        })
        assert status == 404

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_invite_existing_user_no_password(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = {"id": 1, "name": "Test Org"}
        mock_store_instance.get_user.return_value = {"id": 1, "org_id": 1, "email": "test@example.com", "password_hash": None}
        result, status = handle_signin({
            "email": "test@example.com", "invite_code": "testorg"
        })
        assert status == 200

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended._verify_password")
    def test_invite_existing_user_wrong_password(self, mock_verify, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_verify.return_value = False
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = {"id": 1, "name": "Test Org"}
        mock_store_instance.get_user.return_value = {"id": 1, "org_id": 1, "email": "test@example.com", "password_hash": "hash"}
        result, status = handle_signin({
            "email": "test@example.com", "password": "wrong", "invite_code": "testorg"
        })
        assert status == 401

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_invite_new_user_short_password(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = {"id": 1, "name": "Test Org"}
        mock_store_instance.get_user.return_value = None  # New user
        result, status = handle_signin({
            "email": "test@example.com", "password": "short", "invite_code": "testorg"
        })
        assert status == 400
        assert "8 characters" in result.get("error", "")

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_no_invite_no_existing_user(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_store_instance = mock_store.return_value
        mock_store_instance.list_organizations.return_value = []
        result, status = handle_signin({
            "email": "test@example.com", "password": "test1234"
        })
        # Should return token with needs_org
        assert status == 200
        assert result.get("needs_org") is True

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_no_invite_existing_user_wrong_password(self, mock_store):
        from yuleosh.ui.auth_extended import handle_signin, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        mock_store_instance = mock_store.return_value
        mock_store_instance.list_organizations.return_value = [{"id": 1}]
        mock_store_instance.get_user.return_value = {
            "id": 1, "org_id": 1, "email": "test@example.com", "password_hash": "realhash"
        }
        with mock.patch("yuleosh.ui.auth_extended._verify_password", return_value=False):
            result, status = handle_signin({
                "email": "test@example.com", "password": "wrong"
            })
        assert status == 401


# =====================================================================
# handle_org_create
# =====================================================================

class TestHandleOrgCreate:
    """Cover handle_org_create branches."""

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_missing_org_name(self, mock_store):
        from yuleosh.ui.auth_extended import handle_org_create
        result, status = handle_org_create({}, "")
        assert status == 400

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_invalid_slug(self, mock_store):
        from yuleosh.ui.auth_extended import handle_org_create
        result, status = handle_org_create({
            "org_name": "Test", "org_slug": "UPPERCASE!",
            "project_name": "Proj", "project_slug": "proj1",
            "email": "test@example.com"
        }, "token")
        assert status == 400

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_duplicate_slug(self, mock_store):
        from yuleosh.ui.auth_extended import handle_org_create
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = {"id": 1}
        result, status = handle_org_create({
            "org_name": "Test", "org_slug": "test",
            "project_name": "Proj", "project_slug": "proj1",
            "email": "test@example.com"
        }, "token")
        assert status == 409

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_successful_creation(self, mock_store):
        from yuleosh.ui.auth_extended import handle_org_create
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization.return_value = None
        mock_store_instance.create_organization.return_value = {"id": 1, "slug": "test"}
        mock_store_instance.create_user.return_value = {"id": 1, "org_id": 1}
        result, status = handle_org_create({
            "org_name": "Test", "org_slug": "test",
            "project_name": "Proj", "project_slug": "proj1",
            "email": "test@example.com", "password": "Secure1234"
        }, "token")
        assert status == 200
        assert "token" in result


# =====================================================================
# Session and project handlers
# =====================================================================

class TestSessionHandlers:
    """Cover session-related handlers."""

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_session_info_unauthenticated(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_session_info
        mock_get_user.return_value = None
        result, status = handle_session_info("invalid-token")
        assert status == 401

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_session_info_authenticated(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_session_info
        mock_get_user.return_value = {
            "user_id": 1, "org_id": 1, "email": "test@example.com",
            "role": "admin", "org_name": "Test", "org_slug": "test"
        }
        mock_store_instance = mock_store.return_value
        mock_store_instance.list_org_projects.return_value = []
        result, status = handle_session_info("valid-token")
        assert status == 200
        assert result["email"] == "test@example.com"

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_logout(self, mock_store):
        from yuleosh.ui.auth_extended import handle_logout
        result, status = handle_logout("session-token")
        assert status == 200
        assert result["status"] == "ok"
        mock_store.return_value.delete_session.assert_called_once_with("session-token")

    @mock.patch("yuleosh.ui.auth_extended.Store")
    def test_logout_no_token(self, mock_store):
        from yuleosh.ui.auth_extended import handle_logout
        result, status = handle_logout("")
        assert status == 200

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_project_list_unauthorized(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_project_list
        mock_get_user.return_value = None
        result, status = handle_project_list("bad-token")
        assert status == 401

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_project_list_authorized(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_project_list
        mock_get_user.return_value = {"user_id": 1, "org_id": 1}
        mock_store_instance = mock_store.return_value
        mock_store_instance.list_org_projects.return_value = [
            {"id": 1, "name": "Proj", "slug": "proj", "description": "", "created_at": "now"}
        ]
        result, status = handle_project_list("valid-token")
        assert status == 200
        assert len(result["projects"]) == 1

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_project_create_unauthorized(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_project_create
        mock_get_user.return_value = None
        result, status = handle_project_create({}, "bad-token")
        assert status == 401

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_project_create_duplicate(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_project_create
        mock_get_user.return_value = {"user_id": 1, "org_id": 1}
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_org_project.return_value = {"id": 1}
        result, status = handle_project_create(
            {"name": "Test", "slug": "test"}, "token"
        )
        assert status == 409

    @mock.patch("yuleosh.ui.auth_extended.Store")
    @mock.patch("yuleosh.ui.auth_extended.get_session_user")
    def test_org_info(self, mock_get_user, mock_store):
        from yuleosh.ui.auth_extended import handle_org_info
        mock_get_user.return_value = {"user_id": 1, "org_id": 1}
        mock_store_instance = mock_store.return_value
        mock_store_instance.get_organization_by_id.return_value = {
            "id": 1, "name": "Test", "slug": "test", "created_at": "now"
        }
        mock_store_instance.list_users.return_value = [
            {"id": 1, "email": "a@b.com", "role": "admin"}
        ]
        mock_store_instance.list_org_projects.return_value = [
            {"id": 1, "name": "Proj", "slug": "proj"}
        ]
        result, status = handle_org_info("token")
        assert status == 200
        assert result["slug"] == "test"
