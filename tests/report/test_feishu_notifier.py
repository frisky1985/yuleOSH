#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Unit tests for yuleosh.report.feishu_notifier

Tests the Feishu webhook card posting functionality with mocked HTTP requests.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest

# ── Ensure src is on path ──────────────────────────────────────────
_project_root = Path(__file__).resolve().parent.parent.parent / "src"
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Module under test ──────────────────────────────────────────────
from yuleosh.report.feishu_notifier import (
    post_quality_card_to_feishu,
    _resolve_webhook_url,
    _post_json,
    ENV_FEISHU_WEBHOOK_URL,
)


# ====================================================================
# _post_json
# ====================================================================


class TestPostJson:
    """Tests for the low-level _post_json helper."""

    def test_successful_post(self):
        """Happy path: POST returns 200."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b'{"code": 0}'

        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=mock_response) as mock_urlopen:
            result = _post_json("https://open.feishu.cn/hook/test", {"msg_type": "text", "content": {"text": "hello"}})

        assert result is True
        mock_urlopen.assert_called_once()

    def test_successful_post_202(self):
        """2xx range: POST returns 202 (accepted)."""
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.reason = "Accepted"
        mock_response.read.return_value = b'{"code": 0}'

        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=mock_response):
            result = _post_json("https://open.feishu.cn/hook/test", {})

        assert result is True

    def test_failed_post_non_2xx(self):
        """Non-2xx: POST returns 400."""
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.reason = "Bad Request"
        mock_response.read.return_value = b'{"code": 10003}'

        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=mock_response):
            result = _post_json("https://open.feishu.cn/hook/test", {})

        assert result is False

    def test_urlerror(self):
        """URLError: handled gracefully, returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=URLError("Connection refused")):
            result = _post_json("https://open.feishu.cn/hook/test", {})

        assert result is False

    def test_timeout(self):
        """Timeout: handled gracefully, returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=TimeoutError("timed out")):
            result = _post_json("https://open.feishu.cn/hook/test", {})

        assert result is False

    def test_generic_exception(self):
        """Generic exception: handled gracefully, returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=RuntimeError("unexpected")):
            result = _post_json("https://open.feishu.cn/hook/test", {})

        assert result is False

    def test_post_headers(self):
        """Headers include Content-Type: application/json."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b"ok"

        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=mock_response) as mock_urlopen:
            _post_json("https://open.feishu.cn/hook/test", {"key": "val"})

        call_args = mock_urlopen.call_args[0][0]  # The Request object
        assert call_args.method == "POST"
        # Check Content-Type header via the underlying data (urllib Request stores data after serialization)
        sent_data = json.loads(call_args.data)
        assert sent_data == {"key": "val"}

    def test_payload_serialization(self):
        """Payload is properly JSON-serialized."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.read.return_value = b"ok"

        payload = {"msg_type": "interactive", "card": {"header": {"title": "Test"}}}

        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=mock_response) as mock_urlopen:
            _post_json("https://open.feishu.cn/hook/test", payload)

        call_args = mock_urlopen.call_args[0][0]
        sent_data = json.loads(call_args.data)
        assert sent_data["msg_type"] == "interactive"
        assert sent_data["card"]["header"]["title"] == "Test"


# ====================================================================
# post_quality_card_to_feishu
# ====================================================================


class TestPostQualityCardToFeishu:
    """Tests for the main post_quality_card_to_feishu function."""

    @patch("yuleosh.report.feishu_notifier._post_json", return_value=True)
    def test_happy_path(self, mock_post):
        """Happy path: card generated and posted successfully.

        generate_feishu_card_json is imported inside the function, so we
        patch it at its actual module (card_generator).
        """
        with patch("yuleosh.report.card_generator.generate_feishu_card_json") as mock_generate:
            mock_generate.return_value = {"header": {"title": {"tag": "plain_text", "content": "Test"}}}

            with patch("yuleosh.report.feishu_notifier.Path.is_dir", return_value=True):
                result = post_quality_card_to_feishu(
                    webhook_url="https://open.feishu.cn/hook/test",
                    project_dir="/tmp/test-project",
                )

        assert result is True
        mock_generate.assert_called_once_with("/tmp/test-project")
        mock_post.assert_called_once()

    @patch("yuleosh.report.feishu_notifier._post_json", return_value=False)
    def test_post_failure(self, mock_post):
        """Post failure returns False."""
        with patch("yuleosh.report.card_generator.generate_feishu_card_json") as mock_generate:
            mock_generate.return_value = {"header": {"title": {"tag": "plain_text", "content": "Test"}}}

            with patch("yuleosh.report.feishu_notifier.Path.is_dir", return_value=True):
                result = post_quality_card_to_feishu(
                    webhook_url="https://open.feishu.cn/hook/test",
                    project_dir="/tmp/test-project",
                )

        assert result is False

    def test_empty_webhook_url(self):
        """Empty webhook URL returns False."""
        result = post_quality_card_to_feishu(
            webhook_url="",
            project_dir="/tmp/test-project",
        )
        assert result is False

    def test_nonexistent_project_dir(self):
        """Non-existent project directory returns False."""
        with patch("yuleosh.report.feishu_notifier.Path.is_dir", return_value=False):
            result = post_quality_card_to_feishu(
                webhook_url="https://open.feishu.cn/hook/test",
                project_dir="/nonexistent/path",
            )
        assert result is False

    def test_card_generation_error(self):
        """Card generation failure returns False."""
        with patch("yuleosh.report.card_generator.generate_feishu_card_json", side_effect=RuntimeError("card gen failed")):
            with patch("yuleosh.report.feishu_notifier.Path.is_dir", return_value=True):
                result = post_quality_card_to_feishu(
                    webhook_url="https://open.feishu.cn/hook/test",
                    project_dir="/tmp/test-project",
                )
        assert result is False

    @patch("yuleosh.report.feishu_notifier._post_json", return_value=True)
    def test_payload_wrapping(self, mock_post):
        """Payload is wrapped in msg_type: interactive."""
        with patch("yuleosh.report.card_generator.generate_feishu_card_json") as mock_generate:
            mock_generate.return_value = {"header": {"title": {"tag": "plain_text", "content": "quality card"}}}

            with patch("yuleosh.report.feishu_notifier.Path.is_dir", return_value=True):
                post_quality_card_to_feishu(
                    webhook_url="https://open.feishu.cn/hook/test",
                    project_dir="/tmp/test-project",
                )

        # Verify the wrapped payload
        call_args = mock_post.call_args[0]
        sent_payload = call_args[1]
        assert sent_payload["msg_type"] == "interactive"
        assert sent_payload["card"]["header"]["title"]["content"] == "quality card"


# ====================================================================
# _resolve_webhook_url
# ====================================================================


class TestResolveWebhookUrl:
    """Tests for the _resolve_webhook_url helper."""

    def test_cli_url_priority(self):
        """CLI URL takes priority over env var."""
        with patch.dict(os.environ, {ENV_FEISHU_WEBHOOK_URL: "https://env.url/hook"}):
            result = _resolve_webhook_url("https://cli.url/hook")
        assert result == "https://cli.url/hook"

    def test_env_var_fallback(self):
        """Falls back to env var when CLI URL is empty."""
        with patch.dict(os.environ, {ENV_FEISHU_WEBHOOK_URL: "https://env.url/hook"}):
            result = _resolve_webhook_url(None)
        assert result == "https://env.url/hook"

    def test_no_url_available(self):
        """Returns None when no URL is provided."""
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_webhook_url(None)
        assert result is None

    def test_empty_cli_url(self):
        """Empty string CLI URL falls back to env."""
        with patch.dict(os.environ, {ENV_FEISHU_WEBHOOK_URL: "https://env.url/hook"}):
            result = _resolve_webhook_url("  ")
        assert result == "https://env.url/hook"


# ====================================================================
# Exporter integration
# ====================================================================


class TestExporterIntegration:
    """Tests that exporter.py calls feishu_notifier when FEISHU_WEBHOOK_URL is set."""

    def test_auto_feishu_notify_called(self):
        """_auto_feishu_notify calls post_quality_card_to_feishu."""
        from yuleosh.report.exporter import _auto_feishu_notify

        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/hook/test"}):
            with patch("yuleosh.report.feishu_notifier.post_quality_card_to_feishu", return_value=True) as mock_post:
                _auto_feishu_notify("/tmp/project")

        mock_post.assert_called_once_with(
            webhook_url="https://open.feishu.cn/hook/test",
            project_dir="/tmp/project",
        )

    def test_auto_feishu_notify_skipped_when_no_env(self):
        """_auto_feishu_notify is skipped when FEISHU_WEBHOOK_URL is not set."""
        from yuleosh.report.exporter import _auto_feishu_notify

        with patch.dict(os.environ, {}, clear=True):
            with patch("yuleosh.report.feishu_notifier.post_quality_card_to_feishu") as mock_post:
                _auto_feishu_notify("/tmp/project")

        mock_post.assert_not_called()
