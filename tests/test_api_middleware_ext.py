"""Tests for api/middleware.py — JWT auth middleware."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.middleware import (
    require_auth,
    _decode_token,
    _extract_token,
)


class TestMiddleware:
    """Test middleware components."""

    def test_decode_token_valid(self):
        """Valid JWT is decoded successfully."""
        import jwt, time
        secret = "test-secret"
        payload = {"user_id": 1, "org_id": 2, "email": "test@test.com"}
        token = jwt.encode(payload, secret, algorithm="HS256")

        with patch("yuleosh.api.middleware._JWT_SECRET", secret):
            result = _decode_token(token)
            assert result is not None
            assert result["user_id"] == 1

    def test_decode_token_expired(self):
        """Expired JWT returns None."""
        import jwt, time
        secret = "test-secret"
        payload = {"user_id": 1, "exp": int(time.time()) - 3600}
        token = jwt.encode(payload, secret, algorithm="HS256")

        with patch("yuleosh.api.middleware._JWT_SECRET", secret):
            result = _decode_token(token)
            assert result is None

    def test_decode_token_invalid(self):
        """Invalid JWT returns None."""
        result = _decode_token("not-a-valid-token")
        assert result is None

    def test_extract_token_bearer(self):
        """Extract Bearer token from headers dict."""
        headers = {"Authorization": "Bearer mytoken123"}
        result = _extract_token(headers)
        assert result == "mytoken123"

    def test_extract_token_missing(self):
        """Missing auth header returns None."""
        result = _extract_token({})
        assert result is None

    def test_extract_token_not_bearer(self):
        """Non-Bearer auth returns None."""
        headers = {"Authorization": "Basic xyz"}
        result = _extract_token(headers)
        assert result is None

    def test_extract_token_non_dict(self):
        """Non-dict headers returns None."""
        result = _extract_token("not-dict")
        assert result is None

    def test_require_auth_no_handler(self):
        """require_auth without handler injects dummy user."""

        @require_auth
        def my_handler(**kwargs):
            assert "current_user" in kwargs
            return {"ok": True, "user": kwargs["current_user"]}, 200

        result, code = my_handler(method="GET", path_tail="", body={}, query={})
        assert code == 200
        assert result["ok"] is True
        assert result["user"]["user_id"] == "test-unit"

    def test_require_auth_no_token(self):
        """require_auth without token returns 401."""
        mock_handler = MagicMock()
        mock_handler.headers = {}

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        result, code = my_handler(
            method="GET", path_tail="", body={}, query={}, handler=mock_handler
        )
        assert code == 401

    def test_require_auth_invalid_token(self):
        """require_auth with invalid token returns 401."""
        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": "Bearer invalid"}

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        result, code = my_handler(
            method="GET", path_tail="", body={}, query={}, handler=mock_handler
        )
        assert code == 401

    @patch("yuleosh.store.Store")
    def test_require_auth_user_not_found(self, mock_store_cls):
        """require_auth with valid token but missing user returns 401."""
        import jwt, time
        secret = "test-secret2"
        payload = {"user_id": 99, "org_id": 1}
        token = jwt.encode(payload, secret, algorithm="HS256")

        mock_store = MagicMock()
        mock_store.get_user_by_id.return_value = None
        mock_store_cls.return_value = mock_store

        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": f"Bearer {token}"}

        with patch("yuleosh.api.middleware._JWT_SECRET", secret):
            @require_auth
            def my_handler(**kwargs):
                return {"ok": True}, 200

            result, code = my_handler(
                method="GET", path_tail="", body={}, query={}, handler=mock_handler
            )
            assert code == 401

    @patch("yuleosh.store.Store")
    def test_require_auth_no_session(self, mock_store_cls):
        """require_auth with no active session returns 401."""
        import jwt, time
        secret = "test-secret3"
        payload = {"user_id": 1, "org_id": 1}
        token = jwt.encode(payload, secret, algorithm="HS256")

        mock_store = MagicMock()
        mock_store.get_user_by_id.return_value = {"role": "admin", "user_id": 1}
        mock_store.get_session.return_value = None
        mock_store_cls.return_value = mock_store

        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": f"Bearer {token}"}

        with patch("yuleosh.api.middleware._JWT_SECRET", secret):
            @require_auth
            def my_handler(**kwargs):
                return {"ok": True}, 200

            result, code = my_handler(
                method="GET", path_tail="", body={}, query={}, handler=mock_handler
            )
            assert code == 401

    @patch("yuleosh.store.Store")
    def test_require_auth_success(self, mock_store_cls):
        """require_auth with valid everything returns handler result."""
        import jwt, time
        secret = "test-secret4"
        payload = {"user_id": 1, "org_id": 5, "email": "u@test.com"}
        token = jwt.encode(payload, secret, algorithm="HS256")

        mock_store = MagicMock()
        mock_store.get_user_by_id.return_value = {"role": "admin", "user_id": 1}
        mock_store.get_session.return_value = {"active": True}
        mock_store_cls.return_value = mock_store

        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": f"Bearer {token}"}

        with patch("yuleosh.api.middleware._JWT_SECRET", secret):
            @require_auth
            def my_handler(**kwargs):
                assert "current_user" in kwargs
                assert kwargs["current_user"]["user_id"] == 1
                return {"ok": True}, 200

            result, code = my_handler(
                method="GET", path_tail="", body={}, query={}, handler=mock_handler
            )
            assert code == 200
            assert result["ok"] is True

    def test_extract_token_with_get_method(self):
        """extract_token when headers has .get method."""
        class HeadersWithGet:
            def get(self, key, default=""):
                return "Bearer token123"

        result = _extract_token(HeadersWithGet())
        assert result == "token123"
