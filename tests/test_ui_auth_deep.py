# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for yuleosh.ui.auth — session management, login page, validation."""

import hashlib
import hmac
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import directly — tests that need different API_KEY values patch module vars
from yuleosh import ui as _ui
# We import the module directly and access its attributes
import yuleosh.ui.auth as auth_mod


class TestAuthConfig:
    """GIVEN auth module WHEN loaded THEN config reflects env."""

    def test_auth_enabled_with_key(self):
        """GIVEN API_KEY set WHEN auth imported THEN AUTH_ENABLED True."""
        with patch.dict(os.environ, {"YULEOSH_API_KEY": "sk-test"}, clear=True):
            import importlib
            import yuleosh.ui.auth as a
            importlib.reload(a)
            assert a.AUTH_ENABLED is True
            assert a.API_KEY == "sk-test"

    def test_auth_disabled_without_key(self):
        """GIVEN no API_KEY WHEN auth imported THEN AUTH_ENABLED False."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import yuleosh.ui.auth as a
            importlib.reload(a)
            assert a.AUTH_ENABLED is False

    def test_session_ttl_default(self):
        """GIVEN auth module WHEN loaded THEN SESSION_TTL set."""
        assert auth_mod.SESSION_TTL == 86400


class TestSessionToken:
    """GIVEN session token functions WHEN called THEN correct behavior."""

    def test_generate_session_token(self):
        """GIVEN _generate_session_token WHEN called THEN returns url-safe token."""
        token = auth_mod._generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 20

    def test_generate_session_token_unique(self):
        """GIVEN two calls WHEN _generate_session_token THEN different tokens."""
        t1 = auth_mod._generate_session_token()
        t2 = auth_mod._generate_session_token()
        assert t1 != t2

    def test_session_sig_deterministic(self):
        """GIVEN same key+token WHEN _session_sig twice THEN same result."""
        with patch.object(auth_mod, "API_KEY", "test-key-123"):
            sig1 = auth_mod._session_sig("mytoken123")
            sig2 = auth_mod._session_sig("mytoken123")
            assert sig1 == sig2
            assert len(sig1) == 16

    def test_session_sig_different_tokens(self):
        """GIVEN different tokens WHEN _session_sig THEN different sigs."""
        with patch.object(auth_mod, "API_KEY", "test-key-123"):
            sig1 = auth_mod._session_sig("tokenA")
            sig2 = auth_mod._session_sig("tokenB")
            assert sig1 != sig2


class TestCreateSession:
    """GIVEN create_session WHEN called THEN returns token and cookie."""

    def test_create_session_returns_pair(self):
        """GIVEN create_session WHEN called THEN returns (token, cookie)."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            token, cookie = auth_mod.create_session()
            assert isinstance(token, str)
            assert isinstance(cookie, str)
            assert "." in cookie

    def test_create_session_cookie_format(self):
        """GIVEN create_session WHEN called THEN cookie has token.sig format."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            _, cookie = auth_mod.create_session()
            parts = cookie.split(".")
            assert len(parts) == 2
            assert len(parts[0]) > 0
            assert len(parts[1]) == 16

    def test_create_session_stores_internal(self):
        """GIVEN create_session WHEN called THEN token stored in _sessions."""
        # Clear _sessions to avoid interference
        old_sessions = dict(auth_mod._sessions)
        auth_mod._sessions.clear()
        try:
            with patch.object(auth_mod, "API_KEY", "test-key"):
                token, _ = auth_mod.create_session()
                assert token in auth_mod._sessions
        finally:
            auth_mod._sessions.update(old_sessions)


class TestValidateSession:
    """GIVEN validate_session WHEN called THEN validates cookie correctly."""

    def test_validate_valid_cookie(self):
        """GIVEN valid cookie WHEN validate_session THEN returns True."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            _, cookie = auth_mod.create_session()
            assert auth_mod.validate_session(cookie) is True

    def test_validate_cookie_wrong_format(self):
        """GIVEN cookie without dot WHEN validate_session THEN False."""
        assert auth_mod.validate_session("invalidcookie") is False

    def test_validate_cookie_bad_sig(self):
        """GIVEN cookie with wrong signature WHEN validate_session THEN False."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            _, cookie = auth_mod.create_session()
            parts = cookie.split(".")
            bad_cookie = parts[0] + "." + "x" * 16
            assert auth_mod.validate_session(bad_cookie) is False

    def test_validate_cookie_expired(self):
        """GIVEN expired cookie WHEN validate_session THEN False."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            token, cookie = auth_mod.create_session()
            auth_mod._sessions[token] = time.time() - 100000  # well past 86400 TTL
            assert auth_mod.validate_session(cookie) is False

    def test_validate_cookie_unknown_token(self):
        """GIVEN valid sig but unknown token WHEN validate_session THEN False."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            token = "bogus-token"
            sig = auth_mod._session_sig(token)
            cookie = f"{token}.{sig}"
            # Don't add token to _sessions
            assert auth_mod.validate_session(cookie) is False

    def test_validate_removes_expired_from_store(self):
        """GIVEN expired session WHEN validate_session THEN token removed."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            token, cookie = auth_mod.create_session()
            auth_mod._sessions[token] = time.time() - 100000
            auth_mod.validate_session(cookie)
            assert token not in auth_mod._sessions

    def test_validate_cookie_edge_case_exception(self):
        """GIVEN exception during validation WHEN validate_session THEN False."""
        assert auth_mod.validate_session("") is False


class TestCleanupSessions:
    """GIVEN cleanup_sessions WHEN called THEN expired sessions removed."""

    def test_cleanup_removes_stale(self):
        """GIVEN stale sessions WHEN cleanup_sessions THEN removed."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            tokens = []
            for _ in range(3):
                t, _ = auth_mod.create_session()
                tokens.append(t)
            fresh_t, _ = auth_mod.create_session()

            for t in tokens:
                auth_mod._sessions[t] = time.time() - 100000

            auth_mod.cleanup_sessions()
            for t in tokens:
                assert t not in auth_mod._sessions
            assert fresh_t in auth_mod._sessions


class TestIsAuthenticated:
    """GIVEN is_authenticated WHEN called THEN checks headers/sessions."""

    def test_auth_disabled_always_true(self):
        """GIVEN auth disabled WHEN is_authenticated THEN True."""
        with patch.object(auth_mod, "AUTH_ENABLED", False):
            assert auth_mod.is_authenticated({}) is True
            assert auth_mod.is_authenticated({"x-api-key": "anything"}) is True

    def test_auth_enabled_valid_api_key(self):
        """GIVEN correct X-API-Key WHEN is_authenticated THEN True."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                assert auth_mod.is_authenticated({"x-api-key": "correct-key"}) is True

    def test_auth_enabled_wrong_api_key(self):
        """GIVEN wrong X-API-Key WHEN is_authenticated THEN False."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                assert auth_mod.is_authenticated({"x-api-key": "wrong-key"}) is False

    def test_auth_enabled_no_headers(self):
        """GIVEN no headers WHEN is_authenticated THEN False."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                assert auth_mod.is_authenticated({}) is False

    def test_auth_enabled_valid_session_cookie(self):
        """GIVEN valid osh_session cookie WHEN is_authenticated THEN True."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                auth_mod._sessions.clear()
                _, cookie = auth_mod.create_session()
                assert auth_mod.is_authenticated({"cookie": f"osh_session={cookie}"}) is True

    def test_auth_enabled_invalid_session_cookie(self):
        """GIVEN invalid osh_session cookie WHEN is_authenticated THEN False."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                assert auth_mod.is_authenticated({"cookie": "osh_session=badtoken.badsig"}) is False

    def test_auth_enabled_wrong_cookie_name(self):
        """GIVEN cookie with different name WHEN is_authenticated THEN False."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "correct-key"):
                assert auth_mod.is_authenticated({"cookie": "other_cookie=value"}) is False

    def test_auth_api_key_matches(self):
        """GIVEN matching x-api-key WHEN is_authenticated THEN True."""
        with patch.object(auth_mod, "AUTH_ENABLED", True):
            with patch.object(auth_mod, "API_KEY", "my-key"):
                assert auth_mod.is_authenticated({"x-api-key": "my-key"}) is True


class TestGetLoginPage:
    """GIVEN get_login_page WHEN called THEN returns HTML with optional error."""

    def test_login_page_no_error(self):
        """GIVEN no error WHEN get_login_page THEN HTML without error text."""
        html = auth_mod.get_login_page()
        assert "OSH-Fusion" in html
        assert "API key" in html
        # The error div exists but is empty when no error passed
        assert 'id="error"' in html

    def test_login_page_with_error(self):
        """GIVEN error string WHEN get_login_page THEN error shown."""
        html = auth_mod.get_login_page("Invalid key")
        assert "Invalid key" in html

    def test_login_page_escapes_html(self):
        """GIVEN error with HTML WHEN get_login_page THEN escaped."""
        html = auth_mod.get_login_page("<script>alert('xss')</script>")
        assert "&lt;script&gt;" in html

    def test_login_page_contains_form(self):
        """GIVEN login page WHEN rendered THEN has form and input."""
        html = auth_mod.get_login_page()
        assert '<form method="POST" action="/_auth/login">' in html
        assert 'type="password"' in html


class TestCleanupSessionsEdge:
    """GIVEN cleanup_sessions WHEN no stale sessions THEN nothing removed."""

    def test_cleanup_no_op(self):
        """GIVEN all sessions fresh WHEN cleanup_sessions THEN nothing removed."""
        with patch.object(auth_mod, "API_KEY", "test-key"):
            auth_mod._sessions.clear()
            tokens = []
            for _ in range(5):
                t, _ = auth_mod.create_session()
                tokens.append(t)
            auth_mod.cleanup_sessions()
            for t in tokens:
                assert t in auth_mod._sessions

    def test_cleanup_empty_sessions(self):
        """GIVEN empty _sessions WHEN cleanup_sessions THEN no error."""
        auth_mod._sessions.clear()
        auth_mod.cleanup_sessions()  # should not raise
