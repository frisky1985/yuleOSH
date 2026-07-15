"""Tests for api/webhooks.py — GitHub Webhook handler."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.webhooks import (
    handle_webhooks,
    _handle_github_push,
    _trigger_ci,
)


class TestWebhooks:
    """Test webhook endpoints."""

    def test_get_not_allowed(self):
        """GET returns 405."""
        result, code = handle_webhooks("GET")
        assert code == 405

    def test_unknown_provider(self):
        """POST to unknown provider returns 404."""
        result, code = handle_webhooks(
            "POST", "gitlab", {"ref": "refs/heads/main"}, {}
        )
        assert code == 404

    def test_empty_path_tail(self):
        """POST with empty provider returns 404."""
        result, code = handle_webhooks("POST", "", {"ref": "refs/heads/main"}, {})
        assert code == 404

    @patch("yuleosh.api.webhooks._trigger_ci")
    def test_github_push(self, mock_trigger_ci):
        """POST /webhooks/github processes push event."""
        mock_trigger_ci.return_value = {"status": "passed"}

        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "myorg/myrepo", "name": "myrepo"},
            "head_commit": {
                "id": "abc123def456",
                "message": "Fix bug",
            },
            "pusher": {"name": "devuser"},
        }

        result, code = handle_webhooks("POST", "github", payload, {})
        assert code == 200
        assert result["data"]["status"] == "received"
        assert result["data"]["ci_triggered"] is True

    @patch("yuleosh.api.webhooks._trigger_ci")
    def test_github_push_no_commit(self, mock_trigger_ci):
        """Push without head_commit still works."""
        mock_trigger_ci.return_value = None

        payload = {"ref": "refs/heads/develop", "repository": {"full_name": "org/repo"}}
        result, code = _handle_github_push(payload, None)
        assert code == 200
        assert result["data"]["ci_triggered"] is False

    def test_github_push_exception(self):
        """Exception returns 200 (GitHub best practice).
        Force an exception by making _trigger_ci raise.
        """
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_t:
            mock_t.side_effect = Exception("Simulated error")
            payload = {
                "ref": "refs/heads/main",
                "repository": {"full_name": "org/repo"},
                "head_commit": {"id": "abc123"},
            }
            result, code = _handle_github_push(payload, None)
            assert code == 200
            assert result["data"]["ci_triggered"] is False

    def test_github_push_no_ref(self):
        """Push without ref still works."""
        payload = {
            "repository": {"full_name": "org/repo"},
            "head_commit": {"id": "abc"},
        }
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_trig:
            mock_trig.return_value = None
            result, code = _handle_github_push(payload, None)
            assert code == 200

    @patch("yuleosh.ci.run.run_layer1")
    @patch("yuleosh.store.Store")
    def test_trigger_ci_success(self, mock_store_cls, mock_run_layer1):
        """_trigger_ci runs Layer 1 successfully."""
        mock_run_layer1.return_value = True
        result = _trigger_ci("org/repo", "main", "abc123", "Fix")
        assert result["status"] == "passed"

    @patch("yuleosh.ci.run.run_layer1")
    @patch("yuleosh.store.Store")
    def test_trigger_ci_failure(self, mock_store_cls, mock_run_layer1):
        """_trigger_ci runs Layer 1 and reports failure."""
        mock_run_layer1.return_value = False
        result = _trigger_ci("org/repo", "main", "abc123", "Fix")
        assert result["status"] == "failed"

    @patch("yuleosh.ci.run.run_layer1")
    def test_trigger_ci_import_error(self, mock_run_layer1):
        """ImportError returns skipped."""
        mock_run_layer1.side_effect = ImportError("No module")
        result = _trigger_ci("org/repo", "main", "abc123", "Fix")
        assert result["status"] == "skipped"

    @patch("yuleosh.ci.run.run_layer1")
    @patch("yuleosh.store.Store")
    def test_trigger_ci_exception(self, mock_store_cls, mock_run_layer1):
        """Exception returns error."""
        mock_run_layer1.side_effect = Exception("Something")
        result = _trigger_ci("org/repo", "main", "abc123", "Fix")
        assert result["status"] == "error"
