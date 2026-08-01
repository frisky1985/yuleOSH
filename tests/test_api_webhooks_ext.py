"""Tests for api/webhooks.py — GitHub Webhook handler (updated for pipeline trigger)."""

import hmac
import hashlib
import json
import os

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.webhooks import (
    handle_webhooks,
    _handle_github_push,
    _trigger_pipeline,
)


WEBHOOK_SECRET = "test-webhook-secret-for-ext-tests"


def _signed(payload: dict) -> MagicMock:
    """Build a handler mock with a valid X-Hub-Signature-256."""
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    handler = MagicMock()
    handler._raw_body = raw
    handler.headers = {"X-Hub-Signature-256": sig}
    return handler


def _call(payload: dict):
    with patch.dict(os.environ, {"YULEOSH_GITHUB_WEBHOOK_SECRET": WEBHOOK_SECRET}):
        return handle_webhooks("POST", "github", payload, {}, handler=_signed(payload))


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

    @patch("yuleosh.api.webhooks._trigger_pipeline")
    def test_github_push(self, mock_trigger_pipeline):
        """POST /webhooks/github processes push event."""
        mock_trigger_pipeline.return_value = {"job_id": "abc123", "status": "queued", "type": "full"}

        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "myorg/myrepo", "name": "myrepo"},
            "head_commit": {
                "id": "abc123def456",
                "message": "Fix bug",
            },
            "pusher": {"name": "devuser"},
        }

        result, code = _call(payload)
        assert code == 200
        assert result["data"]["status"] == "received"
        assert result["data"]["pipeline_triggered"] is True

    def test_github_push_bad_signature(self):
        """P0: webhook with invalid HMAC is rejected with 401."""
        payload = {"ref": "refs/heads/main", "repository": {"full_name": "org/repo"}}
        handler = MagicMock()
        handler._raw_body = json.dumps(payload).encode()
        handler.headers = {"X-Hub-Signature-256": "sha256=" + "a" * 64}
        with patch.dict(os.environ, {"YULEOSH_GITHUB_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            result, code = handle_webhooks("POST", "github", payload, {}, handler=handler)
        assert code == 401

    @patch("yuleosh.api.webhooks._trigger_pipeline")
    def test_github_push_no_commit(self, mock_trigger_pipeline):
        """Push without head_commit still works."""
        mock_trigger_pipeline.return_value = None

        payload = {"ref": "refs/heads/develop", "repository": {"full_name": "org/repo"}}
        result, code = _handle_github_push(payload, None)
        assert code == 200
        assert result["data"]["pipeline_triggered"] is False

    def test_github_push_exception(self):
        """Exception returns 200 (GitHub best practice)."""
        with patch("yuleosh.api.webhooks._trigger_pipeline") as mock_t:
            mock_t.side_effect = Exception("Simulated error")
            payload = {
                "ref": "refs/heads/main",
                "repository": {"full_name": "org/repo"},
                "head_commit": {"id": "abc123"},
            }
            result, code = _handle_github_push(payload, None)
            assert code == 200
            assert result["data"]["pipeline_triggered"] is False

    def test_github_push_no_ref(self):
        """Push without ref still works."""
        payload = {
            "repository": {"full_name": "org/repo"},
            "head_commit": {"id": "abc"},
        }
        with patch("yuleosh.api.webhooks._trigger_pipeline") as mock_trig:
            mock_trig.return_value = None
            result, code = _handle_github_push(payload, None)
            assert code == 200

    @patch("yuleosh.pipeline.async_runner.submit_pipeline")
    def test_trigger_pipeline_ci(self, mock_submit_pipeline):
        """_trigger_pipeline submits CI pipeline."""
        mock_submit_pipeline.return_value = "job-123"
        result = _trigger_pipeline(
            project_dir="/tmp/test",
            repo_name="generic/repo",
            project_type="generic-embedded-c",
            branch="main",
            commit_hash="abc123",
            commit_message="Fix",
        )
        assert result is not None
        assert result["job_id"] == "job-123"
        assert result["type"] == "ci"

    @patch("yuleosh.pipeline.async_runner.submit_full_pipeline")
    def test_trigger_pipeline_full(self, mock_submit_full):
        """_trigger_pipeline submits full pipeline for autosar."""
        mock_submit_full.return_value = "job-456"
        result = _trigger_pipeline(
            project_dir="/tmp/test",
            repo_name="yuleASR",
            project_type="autosar",
            branch="main",
            commit_hash="abc123",
            commit_message="Fix",
        )
        assert result is not None
        assert result["job_id"] == "job-456"
        assert result["type"] == "full"

    @patch("yuleosh.pipeline.async_runner.submit_pipeline")
    def test_trigger_pipeline_failure(self, mock_submit_pipeline):
        """_trigger_pipeline returns None on failure."""
        mock_submit_pipeline.side_effect = Exception("Something")
        result = _trigger_pipeline(
            project_dir="/tmp/test",
            repo_name="generic/repo",
            project_type="generic-embedded-c",
            branch="main",
            commit_hash="abc123",
            commit_message="Fix",
        )
        assert result is None

    @patch("yuleosh.pipeline.async_runner.submit_pipeline")
    def test_trigger_pipeline_import_error(self, mock_submit_pipeline):
        """ImportError returns None."""
        mock_submit_pipeline.side_effect = ImportError("No module")
        result = _trigger_pipeline(
            project_dir="/tmp/test",
            repo_name="generic/repo",
            project_type="generic-embedded-c",
            branch="main",
            commit_hash="abc123",
            commit_message="Fix",
        )
        assert result is None
