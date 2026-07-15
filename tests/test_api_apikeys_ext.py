"""Tests for api/apikeys.py — API key management endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.apikeys import (
    handle_apikeys,
    _generate_key,
    _list_keys,
    _revoke_key,
)


class TestApiKeys:
    """Test handle_apikeys routing and sub-functions."""

    def test_generate_key_missing_label(self):
        """POST without label returns 400."""
        result, code = handle_apikeys("POST", "", {}, {})
        assert code == 400
        assert result["ok"] is False

    def test_generate_key_empty_label(self):
        """POST with empty label returns 400."""
        result, code = handle_apikeys("POST", "", {"label": "  "}, {})
        assert code == 400
        assert result["ok"] is False

    def test_generate_key_label_too_long(self):
        """POST with label > 100 chars returns 400."""
        result, code = handle_apikeys("POST", "", {"label": "x" * 101}, {})
        assert code == 400
        assert result["ok"] is False

    @patch("yuleosh.api.apikeys.Store")
    def test_generate_key_success(self, mock_store_cls):
        """POST with valid label returns full key and prefix."""
        mock_store = MagicMock()
        mock_store.create_api_key.return_value = {
            "id": 1, "created_at": "2025-01-01T00:00:00"
        }
        mock_store_cls.return_value = mock_store

        result, code = handle_apikeys("POST", "", {"label": "My Key"}, {})
        assert code == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["label"] == "My Key"
        assert data["key"].startswith("yule_")
        assert len(data["key"]) > 20
        assert data["prefix"] == data["key"][:16]

    @patch("yuleosh.api.apikeys.Store")
    def test_generate_key_store_error(self, mock_store_cls):
        """POST when store fails returns 500."""
        mock_store = MagicMock()
        mock_store.create_api_key.side_effect = Exception("DB error")
        mock_store_cls.return_value = mock_store

        result, code = handle_apikeys("POST", "", {"label": "My Key"}, {})
        assert code == 500

    @patch("yuleosh.api.apikeys.Store")
    def test_list_keys(self, mock_store_cls):
        """GET returns list of keys."""
        mock_store = MagicMock()
        mock_store.list_api_keys.return_value = [
            {"id": 1, "prefix": "yule_abcd", "label": "My Key"}
        ]
        mock_store_cls.return_value = mock_store

        result, code = handle_apikeys("GET", "", {}, {})
        assert code == 200
        assert result["data"]["count"] == 1
        assert result["data"]["keys"][0]["prefix"] == "yule_abcd"

    @patch("yuleosh.api.apikeys.Store")
    def test_revoke_key_success(self, mock_store_cls):
        """DELETE with valid id returns success."""
        mock_store = MagicMock()
        mock_store.revoke_api_key.return_value = True
        mock_store_cls.return_value = mock_store

        result, code = handle_apikeys("DELETE", "1", {}, {})
        assert code == 200
        assert result["data"]["revoked"] is True

    @patch("yuleosh.api.apikeys.Store")
    def test_revoke_key_not_found(self, mock_store_cls):
        """DELETE with non-existent id returns 404."""
        mock_store = MagicMock()
        mock_store.revoke_api_key.return_value = False
        mock_store_cls.return_value = mock_store

        result, code = handle_apikeys("DELETE", "999", {}, {})
        assert code == 404

    def test_revoke_key_invalid_id(self):
        """DELETE with non-numeric id returns 400."""
        result, code = handle_apikeys("DELETE", "abc", {}, {})
        assert code == 400

    def test_unsupported_method(self):
        """PUT returns 404."""
        result, code = handle_apikeys("PUT", "", {}, {})
        assert code == 404

    # Direct function tests for branch coverage
    @patch("yuleosh.api.apikeys.Store")
    def test_generate_key_direct(self, mock_store_cls):
        mock_store = MagicMock()
        mock_store.create_api_key.return_value = {"id": 2, "created_at": "T1"}
        mock_store_cls.return_value = mock_store

        result, code = _generate_key({"label": "Direct"})
        assert result["data"]["label"] == "Direct"
        assert result["data"]["id"] == 2

    @patch("yuleosh.api.apikeys.Store")
    def test_list_keys_direct(self, mock_store_cls):
        mock_store = MagicMock()
        mock_store.list_api_keys.return_value = []
        mock_store_cls.return_value = mock_store

        result, code = _list_keys()
        assert result["data"]["count"] == 0

    @patch("yuleosh.api.apikeys.Store")
    def test_revoke_key_direct(self, mock_store_cls):
        mock_store = MagicMock()
        mock_store.revoke_api_key.return_value = True
        mock_store_cls.return_value = mock_store
        result, code = _revoke_key("5")
        assert result["data"]["revoked"]
