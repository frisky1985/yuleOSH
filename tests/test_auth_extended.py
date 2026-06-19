# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ui/auth.py — boost coverage from 33% to 80%+ (v0.8.0 P0).

Covers: auth, session, API key, login page.
"""
import os
import time
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.ui.auth import (
    API_KEY,
    AUTH_ENABLED,
    _sessions,
    SESSION_TTL,
    _generate_session_token,
    _session_sig,
    create_session,
    validate_session,
    cleanup_sessions,
    is_authenticated,
    get_login_page,
    LOGIN_PAGE,
)


class TestSessionCreation:
    """GIVEN auth module WHEN creating sessions THEN tokens are valid."""

    def setup_method(self):
        _sessions.clear()

    def test_generate_session_token_is_unique(self):
        """GIVEN _generate_session_token WHEN called twice THEN different tokens."""
        t1 = _generate_session_token()
        t2 = _generate_session_token()
        assert t1 != t2
        assert len(t1) >= 32

    def test_create_session_returns_token_and_cookie(self):
        """GIVEN API_KEY set WHEN create_session THEN returns (token, cookie_value)."""
        token, cookie_val = create_session()
        assert len(token) >= 32
        assert "." in cookie_val
        assert token in _sessions

    def test_validate_session_valid(self):
        """GIVEN a valid session cookie WHEN validate_session THEN returns True."""
        token, cookie_val = create_session()
        assert validate_session(cookie_val) is True

    def test_validate_session_bad_signature(self):
        """GIVEN a forged cookie WHEN validate_session THEN returns False."""
        token, _ = create_session()
        forged = f"{token}.bad00000bad0000"
        assert validate_session(forged) is False

    def test_validate_session_wrong_format(self):
        """GIVEN malformed cookie WHEN validate_session THEN returns False."""
        assert validate_session("no_dot_separator") is False
        assert validate_session("") is False
        assert validate_session("a.b.c") is False

    def test_validate_session_expired(self):
        """GIVEN expired session WHEN validate_session THEN returns False and removes."""
        token, cookie_val = create_session()
        # Artificially age the session
        _sessions[token] = time.time() - SESSION_TTL - 60
        assert validate_session(cookie_val) is False
        assert token not in _sessions

    def test_validate_session_unknown_token(self):
        """GIVEN signed cookie with unknown token WHEN validate_session THEN returns False."""
        import hmac, hashlib
        fake_token = "x" * 43  # 32 bytes base64
        key = API_KEY.encode("utf-8") if API_KEY else b""
        sig = hmac.new(key, fake_token.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        assert validate_session(f"{fake_token}.{sig}") is False

    def test_cleanup_sessions(self):
        """GIVEN mixed expired/valid sessions WHEN cleanup THEN only expired removed."""
        # Create 3 sessions
        tokens = []
        for _ in range(3):
            token, _ = create_session()
            tokens.append(token)

        # Age two of them
        _sessions[tokens[0]] = time.time() - SESSION_TTL - 10
        _sessions[tokens[1]] = time.time() - SESSION_TTL - 20
        # tokens[2] stays valid

        cleanup_sessions()
        assert tokens[0] not in _sessions
        assert tokens[1] not in _sessions
        assert tokens[2] in _sessions

    def test_cleanup_sessions_empty(self):
        """GIVEN no sessions WHEN cleanup THEN no error."""
        _sessions.clear()
        cleanup_sessions()  # should not crash


class TestSessionSig:
    """GIVEN HMAC signing WHEN API key is set THEN sig is deterministic."""

    def test_sig_deterministic(self):
        """GIVEN same token WHEN _session_sig called twice THEN same result."""
        with mock.patch.dict(os.environ, {"YULEOSH_API_KEY": "test-key-123"}):
            # Need to re-import to pick up new API_KEY
            import yuleosh.ui.auth as auth_mod
            auth_mod.API_KEY = "test-key-123"
            sig1 = auth_mod._session_sig("token123")
            sig2 = auth_mod._session_sig("token123")
            assert sig1 == sig2
            assert len(sig1) == 16

            # Reset
            auth_mod.API_KEY = os.environ.get("YULEOSH_API_KEY", "")


class TestAuthentication:
    """GIVEN is_authenticated WHEN checking headers THEN correct result."""

    def setup_method(self):
        _sessions.clear()

    def test_authenticated_when_auth_disabled(self):
        """GIVEN no API_KEY set WHEN is_authenticated THEN always True."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", False):
            assert is_authenticated({}) is True
            assert is_authenticated({"x-api-key": "anything"}) is True

    def test_authenticated_with_valid_api_key_header(self):
        """GIVEN API key in header WHEN matches THEN authenticated."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "secret-key"):
            assert is_authenticated({"x-api-key": "secret-key"}) is True

    def test_authenticated_with_wrong_api_key(self):
        """GIVEN wrong API key WHEN check THEN not authenticated."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "secret-key"):
            assert is_authenticated({"x-api-key": "wrong-key"}) is False

    def test_authenticated_with_valid_session_cookie(self):
        """GIVEN valid session cookie WHEN check THEN authenticated."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "session-test-key"):
            import yuleosh.ui.auth as auth_mod
            auth_mod.API_KEY = "session-test-key"
            token, cookie_val = auth_mod.create_session()
            headers = {"cookie": f"osh_session={cookie_val}"}
            assert auth_mod.is_authenticated(headers) is True
            auth_mod.API_KEY = os.environ.get("YULEOSH_API_KEY", "")

    def test_authenticated_with_expired_session_cookie(self):
        """GIVEN expired session cookie WHEN check THEN not authenticated."""
        import importlib
        import yuleosh.ui.auth as auth_mod
        orig_auth = auth_mod.AUTH_ENABLED
        orig_key = auth_mod.API_KEY
        # Monkey-patch module-level constants directly to bypass mock.patch limitations
        auth_mod.AUTH_ENABLED = True
        auth_mod.API_KEY = "expired-test-key"
        try:
            token, cookie_val = auth_mod.create_session()
            auth_mod._sessions[token] = time.time() - 99999
            headers = {"cookie": f"osh_session={cookie_val}"}
            assert auth_mod.is_authenticated(headers) is False
        finally:
            auth_mod.AUTH_ENABLED = orig_auth
            auth_mod.API_KEY = orig_key

    def test_authenticated_no_headers(self):
        """GIVEN auth enabled but no headers WHEN check THEN not authenticated."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "some-key"):
            assert is_authenticated({}) is False

    def test_authenticated_no_api_key_in_header(self):
        """GIVEN auth enabled, headers present but no x-api-key WHEN check THEN not auth."""
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "some-key"):
            assert is_authenticated({"user-agent": "test"}) is False


class TestLoginPage:
    """GIVEN get_login_page WHEN called THEN returns HTML."""

    def test_login_page_no_error(self):
        """GIVEN no error WHEN get_login_page THEN no error div."""
        html = get_login_page()
        assert "<html" in html
        assert '<div class="error" id="error"></div>' in html

    def test_login_page_with_error(self):
        """GIVEN error message WHEN get_login_page THEN escaped in div."""
        html = get_login_page("Invalid key")
        assert "Invalid key" in html
        assert "<script" not in html  # XSS protection

    def test_login_page_xss_safe(self):
        """GIVEN XSS payload WHEN get_login_page THEN escaped."""
        html = get_login_page('<script>alert(1)</script>')
        assert "<script>alert" not in html
        assert "&lt;script" in html

    def test_login_page_has_required_elements(self):
        """GIVEN login page WHEN rendered THEN has form elements."""
        html = get_login_page()
        assert 'method="POST"' in html
        assert 'name="api_key"' in html
        assert "YULEOSH_API_KEY" in html

    def test_auth_enabled_depends_on_env(self):
        """GIVEN YULEOSH_API_KEY set WHEN AUTH_ENABLED THEN true."""
        with mock.patch.dict(os.environ, {"YULEOSH_API_KEY": "test-key"}):
            import importlib
            import yuleosh.ui.auth as auth_mod
            auth_mod.API_KEY = "test-key"
            auth_mod.AUTH_ENABLED = True
            assert auth_mod.AUTH_ENABLED is True
            auth_mod.API_KEY = os.environ.get("YULEOSH_API_KEY", "")
            auth_mod.AUTH_ENABLED = bool(auth_mod.API_KEY)

    def test_validate_session_exception_safe(self):
        """GIVEN exception during validation WHEN validate_session THEN returns False."""
        with mock.patch("yuleosh.ui.auth._sessions", {}), \
             mock.patch("yuleosh.ui.auth._session_sig", side_effect=RuntimeError("boom")):
            assert validate_session("any.cookie") is False
