"""Tests for api/wizard.py — Wizard completion endpoint."""

from unittest.mock import patch, MagicMock
from yuleosh.api.wizard import handle_wizard, _get_org_id_from_handler


class TestWizard:
    """Test wizard endpoint."""

    def test_get_not_allowed(self):
        """GET returns 405."""
        result, code = handle_wizard("GET")
        assert code == 405

    @patch("yuleosh.api.wizard.Store")
    def test_wizard_complete(self, mock_store_cls):
        """POST /wizard/complete marks wizard as completed."""
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": "Bearer test-token"}

        result, code = handle_wizard("POST", handler=mock_handler)
        assert code == 200
        assert result["data"]["completed"] is True

    @patch("yuleosh.api.wizard.Store")
    def test_wizard_complete_no_auth(self, mock_store_cls):
        """POST without auth still works."""
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        result, code = handle_wizard("POST", handler=None)
        assert code == 200

    def test_get_org_id_no_handler(self):
        """_get_org_id_from_handler with None handler."""
        org_id = _get_org_id_from_handler(None)
        assert org_id == 0

    def test_get_org_id_no_auth(self):
        """_get_org_id_from_handler without auth header."""
        mock_handler = MagicMock()
        mock_handler.headers = {}
        org_id = _get_org_id_from_handler(mock_handler)
        assert org_id == 0

    def test_get_org_id_no_bearer(self):
        """_get_org_id_from_handler with non-Bearer auth."""
        mock_handler = MagicMock()
        mock_handler.headers = {"Authorization": "Basic xyz"}
        org_id = _get_org_id_from_handler(mock_handler)
        assert org_id == 0
