"""
Extended tests for yuleosh.report.feishu_notifier — _post_json,
post_quality_card_to_feishu, _resolve_webhook_url, and CLI main().
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.report.feishu_notifier import (
    _post_json,
    _resolve_webhook_url,
    post_quality_card_to_feishu,
    main,
)
from urllib.error import URLError


# ═══════════════════════════════════════════════════════════════
# _post_json
# ═══════════════════════════════════════════════════════════════

class MockResponse:
    """Minimal mock for http.client.HTTPResponse."""
    def __init__(self, status: int, reason: str = "OK", data: str = '{"ok":true}'):
        self.status = status
        self.reason = reason
        self._data = data.encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestPostJson:
    """Tests for _post_json."""

    def test_success(self):
        """GIVEN valid URL and payload WHEN posting THEN returns True."""
        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=MockResponse(200)):
            result = _post_json("https://example.com/webhook", {"key": "value"})
            assert result is True

    def test_success_status_299(self):
        """GIVEN response with status 299 WHEN posting THEN returns True."""
        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=MockResponse(299)):
            result = _post_json("https://example.com/webhook", {})
            assert result is True

    def test_failure_status_400(self):
        """GIVEN response with status 400 WHEN posting THEN returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", return_value=MockResponse(400, "Bad Request")):
            result = _post_json("https://example.com/webhook", {})
            assert result is False

    def test_urlerror(self):
        """GIVEN URLError during post WHEN posting THEN returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=URLError("connection refused")):
            result = _post_json("https://example.com/webhook", {})
            assert result is False

    def test_timeouterror(self):
        """GIVEN TimeoutError during post WHEN posting THEN returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=TimeoutError("timed out")):
            result = _post_json("https://example.com/webhook", {}, timeout=5)
            assert result is False

    def test_generic_exception(self):
        """GIVEN generic Exception during post WHEN posting THEN returns False."""
        with patch("yuleosh.report.feishu_notifier.urlopen", side_effect=ValueError("bad encoding")):
            result = _post_json("https://example.com/webhook", {})
            assert result is False


# ═══════════════════════════════════════════════════════════════
# post_quality_card_to_feishu
# ═══════════════════════════════════════════════════════════════

class TestPostQualityCardToFeishu:
    """Tests for post_quality_card_to_feishu."""

    def test_happy_path(self, tmp_path):
        """GIVEN valid inputs WHEN posting quality card THEN returns True."""
        with patch(
            "yuleosh.report.feishu_notifier._post_json",
            return_value=True,
        ) as mock_post:
            result = post_quality_card_to_feishu(
                webhook_url="https://open.feishu.cn/hook/test",
                project_dir=str(tmp_path),
            )
            assert result is True
            # Verify the payload was built
            call_args = mock_post.call_args
            assert call_args is not None
            url, payload = call_args[0]
            assert url == "https://open.feishu.cn/hook/test"
            assert payload["msg_type"] == "interactive"
            assert "card" in payload

    def test_empty_webhook_url(self, tmp_path):
        """GIVEN empty webhook URL WHEN posting THEN returns False."""
        result = post_quality_card_to_feishu(
            webhook_url="",
            project_dir=str(tmp_path),
        )
        assert result is False

    def test_whitespace_webhook_url(self, tmp_path):
        """GIVEN whitespace-only webhook URL WHEN posting THEN returns False."""
        result = post_quality_card_to_feishu(
            webhook_url="   ",
            project_dir=str(tmp_path),
        )
        assert result is False

    def test_nonexistent_project_dir(self):
        """GIVEN non-existent project dir WHEN posting THEN returns False."""
        result = post_quality_card_to_feishu(
            webhook_url="https://example.com/hook",
            project_dir="/nonexistent/path/xyz",
        )
        assert result is False

    def test_card_generation_exception(self, tmp_path):
        """GIVEN card generation raises exception WHEN posting THEN returns False."""
        with patch(
            "yuleosh.report.card_generator.generate_feishu_card_json",
            side_effect=ValueError("mock card error"),
        ):
            result = post_quality_card_to_feishu(
                webhook_url="https://example.com/hook",
                project_dir=str(tmp_path),
            )
            assert result is False

    def test_post_json_returns_false(self, tmp_path):
        """GIVEN _post_json returns False WHEN posting THEN returns False."""
        with patch(
            "yuleosh.report.feishu_notifier._post_json",
            return_value=False,
        ):
            result = post_quality_card_to_feishu(
                webhook_url="https://example.com/hook",
                project_dir=str(tmp_path),
            )
            assert result is False


# ═══════════════════════════════════════════════════════════════
# _resolve_webhook_url
# ═══════════════════════════════════════════════════════════════

class TestResolveWebhookUrl:
    """Tests for _resolve_webhook_url."""

    def test_from_cli_argument(self):
        """GIVEN CLI URL WHEN resolving THEN returns that URL."""
        result = _resolve_webhook_url("https://cli.example.com/hook")
        assert result == "https://cli.example.com/hook"

    def test_from_env_variable(self):
        """GIVEN environment variable WHEN resolving THEN returns env URL."""
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://env.example.com/hook"}, clear=True):
            result = _resolve_webhook_url(None)
            assert result == "https://env.example.com/hook"

    def test_cli_overrides_env(self):
        """GIVEN both CLI URL and env var WHEN resolving THEN CLI wins."""
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://env.example.com/hook"}, clear=True):
            result = _resolve_webhook_url("https://cli.example.com/hook")
            assert result == "https://cli.example.com/hook"

    def test_neither_set(self):
        """GIVEN no URL in CLI or env WHEN resolving THEN returns None."""
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_webhook_url(None)
            assert result is None

    def test_env_var_empty_string(self):
        """GIVEN empty env var WHEN resolving THEN returns None."""
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": ""}, clear=True):
            result = _resolve_webhook_url(None)
            assert result is None


# ═══════════════════════════════════════════════════════════════
# main() CLI
# ═══════════════════════════════════════════════════════════════

class TestCliMain:
    """Tests for CLI main()."""

    def test_no_webhook_url_exits_with_error(self):
        """GIVEN no webhook URL provided WHEN main runs THEN exits with 1."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "yuleosh.report.feishu_notifier.sys.argv",
                ["feishu_notifier.py", "--project-dir", "/tmp"],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1

    def test_success_path(self, tmp_path):
        """GIVEN all inputs valid WHEN main runs THEN exits with 0."""
        with patch(
            "yuleosh.report.feishu_notifier.post_quality_card_to_feishu",
            return_value=True,
        ):
            with patch(
                "yuleosh.report.feishu_notifier.sys.argv",
                [
                    "feishu_notifier.py",
                    "--webhook-url", "https://example.com/hook",
                    "--project-dir", str(tmp_path),
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0

    def test_failure_path(self, tmp_path):
        """GIVEN posting fails WHEN main runs THEN exits with 1."""
        with patch(
            "yuleosh.report.feishu_notifier.post_quality_card_to_feishu",
            return_value=False,
        ):
            with patch(
                "yuleosh.report.feishu_notifier.sys.argv",
                [
                    "feishu_notifier.py",
                    "--webhook-url", "https://example.com/hook",
                    "--project-dir", str(tmp_path),
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 1

    def test_verbose_flag(self, tmp_path):
        """GIVEN verbose flag WHEN main runs THEN exits with 0."""
        with patch(
            "yuleosh.report.feishu_notifier.post_quality_card_to_feishu",
            return_value=True,
        ):
            with patch(
                "yuleosh.report.feishu_notifier.sys.argv",
                [
                    "feishu_notifier.py",
                    "--webhook-url", "https://example.com/hook",
                    "--project-dir", str(tmp_path),
                    "--verbose",
                ],
            ):
                with pytest.raises(SystemExit) as exc:
                    main()
                assert exc.value.code == 0
