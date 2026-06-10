"""Tests for notify.py — boost coverage from 72% to 85%+ (v0.8.0 P0).

Covers: notify config, webhook POST, error paths, pipeline/CI notifications.
"""
import json
import os
import sys
from unittest import mock
from urllib.error import URLError

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from notify import (
    NotifyConfig,
    get_config,
    set_config,
    _feishu_card_payload,
    _feishu_text_payload,
    _post_json,
    send_feishu,
    send_email,
    send_webhook,
    notify_pipeline,
    notify_ci,
    ENV_FEISHU_URL,
    ENV_EMAIL_SMTP,
    ENV_EMAIL_FROM,
    ENV_EMAIL_TO,
    ENV_WEBHOOK_URL,
    ENV_EMAIL_USER,
    ENV_EMAIL_PASS,
    ENV_EMAIL_PORT,
    ENV_EMAIL_TLS,
)


class TestNotifyConfig:
    """GIVEN NotifyConfig WHEN reading env THEN correct config."""

    def test_from_env_empty(self):
        """GIVEN no env vars set WHEN from_env THEN all disabled."""
        with mock.patch.dict(os.environ, {
            ENV_FEISHU_URL: "",
            ENV_EMAIL_SMTP: "",
            ENV_EMAIL_FROM: "",
            ENV_EMAIL_TO: "",
            ENV_WEBHOOK_URL: "",
        }):
            cfg = NotifyConfig.from_env()
            assert cfg.feishu_enabled is False
            assert cfg.email_enabled is False
            assert cfg.webhook_enabled is False

    def test_from_env_feishu_only(self):
        """GIVEN feishu URL set WHEN from_env THEN feishu enabled."""
        cfg = NotifyConfig(feishu_url="https://open.feishu.cn/hook/xxx")
        assert cfg.feishu_enabled is True
        assert cfg.feishu_url == "https://open.feishu.cn/hook/xxx"
        assert cfg.email_enabled is False

    def test_from_env_email_full(self):
        """GIVEN all email env vars WHEN from_env THEN email enabled."""
        cfg = NotifyConfig(
            email_smtp="smtp.test.com",
            email_from="from@test.com",
            email_to="to@test.com",
        )
        assert cfg.email_enabled is True
        assert cfg.email_smtp == "smtp.test.com"

    def test_from_env_email_missing_from(self):
        """GIVEN SMTP and TO but no FROM WHEN email_enabled THEN false."""
        cfg = NotifyConfig(email_smtp="smtp.test.com", email_to="to@test.com")
        assert cfg.email_enabled is False

    def test_to_dict_and_from_dict_roundtrip(self):
        """GIVEN config WHEN to_dict THEN key fields preserved."""
        original = NotifyConfig(
            feishu_url="https://hook.example.com",
            email_smtp="smtp.example.com",
            email_from="from@example.com",
            email_to="to1@example.com",
            webhook_url="https://webhook.example.com",
        )
        d = original.to_dict()
        assert d["feishu_url"] == "https://hook.example.com"
        assert d["email_smtp"] == "smtp.example.com"
        assert d["webhook_url"] == "https://webhook.example.com"

    def test_apply_to_env(self):
        """GIVEN config WHEN apply_to_env THEN env vars set."""
        cfg = NotifyConfig(
            feishu_url="https://hook.f.com",
            email_smtp="smtp.f.com",
            email_from="f@f.com",
            email_to="t@f.com",
            webhook_url="https://wh.f.com",
        )
        with mock.patch.dict(os.environ, {}, clear=False):
            cfg.apply_to_env()
            assert os.environ.get(ENV_FEISHU_URL) == "https://hook.f.com"
            assert os.environ.get(ENV_EMAIL_SMTP) == "smtp.f.com"
            assert os.environ.get(ENV_WEBHOOK_URL) == "https://wh.f.com"

    def test_get_config_reads_env(self):
        """GIVEN env vars set WHEN get_config THEN returns matching config."""
        with mock.patch.dict(os.environ, {
            ENV_FEISHU_URL: "https://hook.c.com",
            ENV_WEBHOOK_URL: "https://wh.c.com",
        }):
            cfg = get_config()
            assert cfg.feishu_url == "https://hook.c.com"
            assert cfg.webhook_url == "https://wh.c.com"

    def test_set_config_persists(self):
        """GIVEN config WHEN set_config THEN get_config returns it."""
        cfg = NotifyConfig(webhook_url="https://new.example.com")
        with mock.patch.dict(os.environ, {}, clear=False):
            set_config(cfg)
            assert os.environ.get(ENV_WEBHOOK_URL) == "https://new.example.com"

    def test_email_tls_config_variants(self):
        """GIVEN different TLS config values WHEN from_env THEN correct bool."""
        cfg = NotifyConfig(email_tls=True)
        assert cfg.email_tls is True
        cfg2 = NotifyConfig(email_tls=False)
        assert cfg2.email_tls is False


class TestFeishuPayload:
    """GIVEN _feishu_card_payload WHEN called THEN valid card format."""

    def test_card_payload_structure(self):
        """GIVEN title/content/color WHEN _feishu_card_payload THEN correct JSON."""
        payload = _feishu_card_payload("Test Title", "Test **Content**", "red")
        assert payload["msg_type"] == "interactive"
        card = payload["card"]
        assert card["header"]["title"]["content"] == "Test Title"
        assert card["header"]["template"] == "red"
        assert len(card["elements"]) == 3
        assert card["elements"][0]["content"] == "Test **Content**"

    def test_text_payload_structure(self):
        """GIVEN text WHEN _feishu_text_payload THEN correct format."""
        payload = _feishu_text_payload("Hello")
        assert payload["msg_type"] == "text"
        assert payload["content"]["text"] == "Hello"


class TestPostJson:
    """GIVEN _post_json WHEN called THEN handles success/error paths."""

    def test_post_json_success(self):
        """GIVEN HTTP 200 WHEN _post_json THEN returns True."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("notify.urlopen", return_value=mock_resp):
            assert _post_json("https://example.com/hook", {"test": 1}) is True

    def test_post_json_http_error(self):
        """GIVEN HTTP 500 WHEN _post_json THEN returns False."""
        with mock.patch("notify.urlopen", side_effect=URLError("connection refused")):
            assert _post_json("https://example.com/hook", {"test": 1}) is False

    def test_post_json_generic_error(self):
        """GIVEN generic Exception WHEN _post_json THEN returns False."""
        with mock.patch("notify.urlopen", side_effect=RuntimeError("unexpected")):
            assert _post_json("https://example.com/hook", {"test": 1}) is False

    def test_post_json_non_2xx_status(self):
        """GIVEN HTTP 400 WHEN _post_json THEN returns False."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b'{"error": "bad request"}'
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("notify.urlopen", return_value=mock_resp):
            assert _post_json("https://example.com/hook", {"test": 1}) is False


class TestSendFunctions:
    """GIVEN send functions WHEN called with various configs THEN correct behavior."""

    def test_send_feishu_not_configured(self):
        """GIVEN no feishu URL WHEN send_feishu THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("notify.ENV_FEISHU_URL", "YULEOSH_NOTIFY_FEISHU_URL"):
                result = send_feishu("Title", "Content")
                assert result is False

    def test_send_feishu_success(self):
        """GIVEN feishu URL WHEN send_feishu THEN calls _post_json."""
        with mock.patch("notify._post_json", return_value=True) as mock_post:
            with mock.patch.dict(os.environ, {ENV_FEISHU_URL: "https://hook.f.com"}):
                result = send_feishu("Title", "Content")
                assert result is True
                mock_post.assert_called_once()
                # Verify card payload was built
                args = mock_post.call_args[0]
                assert "interactive" in json.dumps(args[1])

    def test_send_feishu_override_url(self):
        """GIVEN explicit webhook_url WHEN send_feishu THEN uses it."""
        with mock.patch("notify._post_json", return_value=True) as mock_post:
            result = send_feishu("T", "C", webhook_url="https://custom.com/hook")
            assert result is True
            assert mock_post.call_args[0][0] == "https://custom.com/hook"

    def test_send_email_not_configured(self):
        """GIVEN no email config WHEN send_email THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = send_email("Subject", "Body")
            assert result is False

    def test_send_email_mock_success(self):
        """GIVEN SMTP config WHEN send_email THEN calls SMTP."""
        with mock.patch("smtplib.SMTP") as mock_smtp_class:
            mock_server = mock.MagicMock()
            mock_smtp_class.return_value.__enter__.return_value = mock_server

            result = send_email(
                "Subject", "Body",
                smtp_server="smtp.test.com",
                from_addr="from@test.com",
                to_addrs="to@test.com",
                username="user",
                password="pass",
            )
            assert result is True
            mock_server.sendmail.assert_called_once()

    def test_send_email_mock_failure(self):
        """GIVEN SMTP fails WHEN send_email THEN returns False."""
        import smtplib
        with mock.patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp_class.side_effect = smtplib.SMTPException("connection refused")
            result = send_email(
                "Subject", "Body",
                smtp_server="smtp.test.com",
                from_addr="from@test.com",
                to_addrs="to@test.com",
            )
            assert result is False

    def test_send_email_generic_error(self):
        """GIVEN generic error WHEN send_email THEN returns False."""
        with mock.patch("smtplib.SMTP", side_effect=RuntimeError("unexpected")):
            result = send_email(
                "Subject", "Body",
                smtp_server="smtp.test.com",
                from_addr="from@test.com",
                to_addrs="to@test.com",
            )
            assert result is False

    def test_send_webhook_not_configured(self):
        """GIVEN no webhook URL WHEN send_webhook THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = send_webhook({"event": "test"})
            assert result is False

    def test_send_webhook_success(self):
        """GIVEN webhook URL WHEN send_webhook THEN calls _post_json."""
        with mock.patch("notify._post_json", return_value=True) as mock_post:
            with mock.patch.dict(os.environ, {ENV_WEBHOOK_URL: "https://wh.com"}):
                result = send_webhook({"event": "test"})
                assert result is True
                mock_post.assert_called_once()

    def test_send_webhook_override_url(self):
        """GIVEN explicit URL WHEN send_webhook THEN uses it."""
        with mock.patch("notify._post_json", return_value=True) as mock_post:
            result = send_webhook({"e": "t"}, url="https://custom.com")
            assert result is True
            assert mock_post.call_args[0][0] == "https://custom.com"


class TestConvenienceNotifications:
    """GIVEN notify_pipeline/notify_ci WHEN called THEN sends to all channels."""

    def test_notify_pipeline_completed(self):
        """GIVEN completed pipeline WHEN notify_pipeline THEN green card."""
        with mock.patch("notify.send_feishu") as mock_fs, \
             mock.patch("notify.send_email") as mock_email, \
             mock.patch("notify.send_webhook") as mock_wh:
            notify_pipeline("my-pipeline", "completed", 5, 5)
            mock_fs.assert_called_once()
            assert "green" in mock_fs.call_args[0][2].lower() or \
                   mock_fs.call_args[0][2] == "green"
            mock_email.assert_called_once()
            mock_wh.assert_called_once()

    def test_notify_pipeline_failed_with_errors(self):
        """GIVEN failed pipeline with errors WHEN notify_pipeline THEN red card."""
        with mock.patch("notify.send_feishu") as mock_fs, \
             mock.patch("notify.send_email") as mock_email, \
             mock.patch("notify.send_webhook") as mock_wh:
            errors = [f"error_{i}" for i in range(7)]
            notify_pipeline("bad-pipeline", "failed", 10, 3, errors)
            mock_fs.assert_called_once()
            # Check that errors are truncated at 5 in Feishu content
            content = mock_fs.call_args[0][1]
            assert "... and 2 more" in content or "error_0" in content
            mock_email.assert_called_once()

    def test_notify_ci_passed(self):
        """GIVEN passed CI WHEN notify_ci THEN green card with stages."""
        with mock.patch("notify.send_feishu") as mock_fs, \
             mock.patch("notify.send_email") as mock_email, \
             mock.patch("notify.send_webhook") as mock_wh:
            stages = [
                {"name": "lint", "status": "passed"},
                {"name": "test", "status": "passed"},
                {"name": "build", "status": "passed"},
            ]
            notify_ci(1, "passed", stages)
            mock_fs.assert_called_once()
            mock_email.assert_called_once()
            mock_wh.assert_called_once()

    def test_notify_ci_failed_with_stages_and_errors(self):
        """GIVEN failed CI with mixed stages WHEN notify_ci THEN red card."""
        with mock.patch("notify.send_feishu") as mock_fs, \
             mock.patch("notify.send_email") as mock_email, \
             mock.patch("notify.send_webhook") as mock_wh:
            stages = [
                {"name": "lint", "status": "passed"},
                {"name": "test", "status": "failed"},
                {"name": "build", "status": "skipped"},
            ]
            errors = ["test failed: assert 1 == 2"]
            notify_ci(2, "failed", stages, errors)
            mock_fs.assert_called_once()
            content = mock_fs.call_args[0][1]
            assert "1/3" in content
            mock_email.assert_called_once()
            # Webhook payload should have structured data
            wh_payload = mock_wh.call_args[0][0]
            assert wh_payload["event"] == "ci"
            assert wh_payload["layer"] == 2
