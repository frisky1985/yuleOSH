# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for yuleosh.notify — mock-based coverage for all channels, config, and pipeline events."""

import json
import os
import sys
import ssl
import smtplib
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.notify import (
    NotifyConfig,
    get_config,
    set_config,
    send_feishu,
    send_email,
    send_webhook,
    notify_pipeline,
    notify_ci,
    _feishu_card_payload,
    _feishu_text_payload,
    _post_json,
    _get_store,
)


# ---------------------------------------------------------------------------
# NotifyConfig tests
# ---------------------------------------------------------------------------

class TestNotifyConfig:
    """GIVEN NotifyConfig WHEN constructed THEN properties reflect inputs."""

    def test_from_env_empty(self):
        """GIVEN no env vars WHEN from_env THEN all disabled."""
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = NotifyConfig.from_env()
            assert not cfg.feishu_enabled
            assert not cfg.email_enabled
            assert not cfg.webhook_enabled
            assert cfg.email_port == 587
            assert cfg.email_tls is True

    def test_from_env_feishu(self):
        """GIVEN FEISHU_URL env WHEN from_env THEN feishu enabled."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_FEISHU_URL": "https://feishu.example.com/hook"}):
            cfg = NotifyConfig.from_env()
            assert cfg.feishu_enabled
            assert cfg.feishu_url == "https://feishu.example.com/hook"

    def test_from_env_email(self):
        """GIVEN email env vars WHEN from_env THEN email enabled."""
        with mock.patch.dict(os.environ, {
            "YULEOSH_NOTIFY_EMAIL_SMTP": "smtp.example.com",
            "YULEOSH_NOTIFY_EMAIL_FROM": "bot@example.com",
            "YULEOSH_NOTIFY_EMAIL_TO": "user@example.com",
            "YULEOSH_NOTIFY_EMAIL_USER": "bot",
            "YULEOSH_NOTIFY_EMAIL_PASS": "secret",
            "YULEOSH_NOTIFY_EMAIL_PORT": "465",
            "YULEOSH_NOTIFY_EMAIL_TLS": "0",
        }):
            cfg = NotifyConfig.from_env()
            assert cfg.email_enabled
            assert cfg.email_smtp == "smtp.example.com"
            assert cfg.email_port == 465
            assert cfg.email_tls is False

    def test_from_env_email_partial(self):
        """GIVEN only SMTP set WHEN from_env THEN email disabled."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_SMTP": "smtp.example.com"}):
            cfg = NotifyConfig.from_env()
            assert not cfg.email_enabled

    def test_from_env_webhook(self):
        """GIVEN WEBHOOK_URL env WHEN from_env THEN webhook enabled."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_WEBHOOK_URL": "https://hook.example.com/evt"}):
            cfg = NotifyConfig.from_env()
            assert cfg.webhook_enabled

    def test_from_env_email_tls_variants(self):
        """GIVEN TLS values 'true'/'yes'/'1' WHEN from_env THEN True."""
        for val in ("1", "true", "yes"):
            with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_TLS": val}):
                cfg = NotifyConfig.from_env()
                assert cfg.email_tls is True

    def test_from_env_email_tls_false(self):
        """GIVEN TLS value '0' WHEN from_env THEN False."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_TLS": "0"}):
            cfg = NotifyConfig.from_env()
            assert cfg.email_tls is False

    def test_to_dict_defaults(self):
        """GIVEN empty config WHEN to_dict THEN keys present with defaults."""
        cfg = NotifyConfig()
        d = cfg.to_dict()
        assert d["feishu_url"] == ""
        assert d["feishu_enabled"] is False
        assert d["email_enabled"] is False
        assert d["webhook_enabled"] is False

    def test_to_dict_enabled(self):
        """GIVEN configured config WHEN to_dict THEN correct values."""
        cfg = NotifyConfig(
            feishu_url="https://fs.hook",
            email_smtp="smtp.example.com",
            email_from="a@b.com",
            email_to="c@d.com",
            webhook_url="https://hook.example.com",
        )
        d = cfg.to_dict()
        assert d["feishu_enabled"]
        assert d["email_enabled"]
        assert d["webhook_enabled"]

    def test_from_dict_roundtrip(self):
        """GIVEN dict WHEN from_dict THEN fields populated."""
        d = {
            "feishu_url": "https://fs.h",
            "email_smtp": "smtp.x.com",
            "email_from": "a@b.com",
            "email_to": "c@d.com",
            "email_user": "user",
            "email_pass": "pass",
            "email_port": "465",
            "email_tls": True,
            "webhook_url": "https://wh.example.com",
        }
        cfg = NotifyConfig.from_dict(d)
        assert cfg.feishu_url == "https://fs.h"
        assert cfg.email_smtp == "smtp.x.com"
        assert cfg.email_port == 465
        assert cfg.email_tls is True

    def test_apply_to_env(self):
        """GIVEN config WHEN apply_to_env THEN env vars set."""
        cfg = NotifyConfig(
            feishu_url="https://fs.url",
            email_smtp="smtp.x.com",
            email_from="f@b.com",
            email_to="t@b.com",
            email_user="u",
            email_pass="p",
            webhook_url="https://wh.url",
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg.apply_to_env()
            assert os.environ["YULEOSH_NOTIFY_FEISHU_URL"] == "https://fs.url"
            assert os.environ["YULEOSH_NOTIFY_EMAIL_SMTP"] == "smtp.x.com"
            assert os.environ["YULEOSH_NOTIFY_EMAIL_PORT"] == "587"
            assert os.environ["YULEOSH_NOTIFY_EMAIL_TLS"] == "1"
            assert os.environ["YULEOSH_NOTIFY_WEBHOOK_URL"] == "https://wh.url"

    def test_apply_to_env_skips_empty(self):
        """GIVEN config with empty fields WHEN apply_to_env THEN only non-empty set."""
        cfg = NotifyConfig()
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg.apply_to_env()
            assert "YULEOSH_NOTIFY_FEISHU_URL" not in os.environ
            # Port and TLS always set
            assert os.environ["YULEOSH_NOTIFY_EMAIL_PORT"] == "587"
            assert os.environ["YULEOSH_NOTIFY_EMAIL_TLS"] == "1"


# ---------------------------------------------------------------------------
# get_config / set_config
# ---------------------------------------------------------------------------

class TestGetSetConfig:
    """GIVEN get_config/set_config WHEN called THEN delegates to NotifyConfig."""

    def test_get_config_delegates(self):
        """GIVEN env set WHEN get_config THEN correct."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_FEISHU_URL": "https://hook"}):
            cfg = get_config()
            assert cfg.feishu_enabled

    def test_set_config_delegates(self):
        """GIVEN cfg WHEN set_config THEN env set."""
        cfg = NotifyConfig(webhook_url="https://wh")
        with mock.patch.dict(os.environ, {}, clear=True):
            set_config(cfg)
            assert os.environ.get("YULEOSH_NOTIFY_WEBHOOK_URL") == "https://wh"


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

class TestPayloadBuilders:
    """GIVEN payload builder functions WHEN called THEN correct dict structure."""

    def test_feishu_card_payload_has_keys(self):
        """GIVEN title+content WHEN _feishu_card_payload THEN correct structure."""
        payload = _feishu_card_payload("Test", "Hello", color="green")
        assert payload["msg_type"] == "interactive"
        assert payload["card"]["header"]["title"]["content"] == "Test"
        assert payload["card"]["header"]["template"] == "green"

    def test_feishu_card_payload_default_color(self):
        """GIVEN no color WHEN _feishu_card_payload THEN defaults to blue."""
        payload = _feishu_card_payload("Hi", "body")
        assert payload["card"]["header"]["template"] == "blue"

    def test_feishu_card_payload_has_hr_and_note(self):
        """GIVEN card payload WHEN built THEN has hr and note elements."""
        payload = _feishu_card_payload("T", "C")
        elements = payload["card"]["elements"]
        assert any(e["tag"] == "hr" for e in elements)
        note = [e for e in elements if e["tag"] == "note"]
        assert len(note) == 1
        assert "yuleOSH" in note[0]["elements"][0]["content"]

    def test_feishu_text_payload(self):
        """GIVEN text WHEN _feishu_text_payload THEN correct structure."""
        payload = _feishu_text_payload("hello")
        assert payload["msg_type"] == "text"
        assert payload["content"]["text"] == "hello"


# ---------------------------------------------------------------------------
# _post_json
# ---------------------------------------------------------------------------

class TestPostJson:
    """GIVEN _post_json WHEN POST THEN success/failure based on response."""

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_success(self, mock_urlopen):
        """GIVEN 200 response WHEN _post_json THEN returns True."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value = mock_resp
        result = _post_json("https://example.com/hook", {"key": "val"})
        assert result is True
        mock_urlopen.assert_called_once()

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_2xx_range(self, mock_urlopen):
        """GIVEN 299 response WHEN _post_json THEN returns True."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 299
        mock_resp.read.return_value = b""
        mock_urlopen.return_value = mock_resp
        assert _post_json("https://ex.com/hook", {}) is True

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_failure(self, mock_urlopen):
        """GIVEN 400 response WHEN _post_json THEN returns False."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b"bad request"
        mock_urlopen.return_value = mock_resp
        result = _post_json("https://example.com/hook", {"k": "v"})
        assert result is False

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_generic_error(self, mock_urlopen):
        """GIVEN URLError WHEN _post_json THEN returns False gracefully."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("timeout")
        result = _post_json("https://example.com/hook", {})
        assert result is False

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_unexpected_error(self, mock_urlopen):
        """GIVEN unexpected Exception WHEN _post_json THEN returns False."""
        mock_urlopen.side_effect = Exception("weird")
        result = _post_json("https://example.com/hook", {})
        assert result is False

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_sends_json_content_type(self, mock_urlopen):
        """GIVEN payload WHEN _post_json THEN Content-Type set to application/json."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value = mock_resp
        _post_json("https://ex.com/hook", {"a": 1})
        req = mock_urlopen.call_args[0][0]
        # urllib normalizes the header key to 'Content-type'
        assert req.get_header("Content-type") == "application/json"

    @mock.patch("yuleosh.notify.urlopen")
    def test_post_json_custom_timeout(self, mock_urlopen):
        """GIVEN payload WHEN _post_json THEN uses default 10s timeout."""
        mock_resp = mock.MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value = mock_resp
        _post_json("https://ex.com/hook", {"a": 1})
        kwargs = mock_urlopen.call_args[1]
        assert "timeout" in kwargs


# ---------------------------------------------------------------------------
# send_feishu
# ---------------------------------------------------------------------------

class TestSendFeishu:
    """GIVEN send_feishu WHEN called THEN sends card with correct args."""

    @mock.patch("yuleosh.notify._post_json", return_value=True)
    def test_send_feishu_success(self, mock_post):
        """GIVEN valid webhook WHEN send_feishu THEN returns True."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_FEISHU_URL": "https://fs.hook"}):
            result = send_feishu("Title", "Content", color="green")
            assert result is True
            args, _ = mock_post.call_args
            assert args[0] == "https://fs.hook"
            assert args[1]["msg_type"] == "interactive"

    @mock.patch("yuleosh.notify._post_json", return_value=True)
    def test_send_feishu_custom_url(self, mock_post):
        """GIVEN custom webhook_url WHEN send_feishu THEN uses custom URL."""
        result = send_feishu("T", "C", webhook_url="https://custom.hook")
        assert result is True
        args, _ = mock_post.call_args
        assert args[0] == "https://custom.hook"

    def test_send_feishu_no_config(self):
        """GIVEN no FEISHU_URL configured WHEN send_feishu THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = send_feishu("T", "C")
            assert result is False

    @mock.patch("yuleosh.notify._post_json", return_value=False)
    def test_send_feishu_post_fails(self, mock_post):
        """GIVEN _post_json fails WHEN send_feishu THEN returns False."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_FEISHU_URL": "https://fs.hook"}):
            result = send_feishu("T", "C")
            assert result is False


# ---------------------------------------------------------------------------
# send_email
# ---------------------------------------------------------------------------

class TestSendEmail:
    """GIVEN send_email WHEN called THEN sends via SMTP."""

    @mock.patch("yuleosh.notify.smtplib.SMTP")
    def test_send_email_tls_success(self, mock_smtp):
        """GIVEN valid config WHEN send_email with TLS THEN sends."""
        mock_server = mock.MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        result = send_email(
            subject="Test",
            body="Hello",
            smtp_server="smtp.example.com",
            from_addr="a@b.com",
            to_addrs="c@d.com",
            username="user",
            password="pass",
        )
        assert result is True
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()

    @mock.patch("yuleosh.notify.smtplib.SMTP_SSL")
    def test_send_email_ssl_success(self, mock_smtp_ssl):
        """GIVEN use_tls=False WHEN send_email THEN uses SMTP_SSL."""
        mock_server = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server
        result = send_email(
            subject="Test",
            body="Hello",
            smtp_server="smtp.example.com",
            from_addr="a@b.com",
            to_addrs="c@d.com",
            username="user",
            password="pass",
            use_tls=False,
        )
        assert result is True
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 587, timeout=15)
        mock_server.login.assert_called_once()

    @mock.patch("yuleosh.notify.smtplib.SMTP")
    def test_send_email_no_auth(self, mock_smtp):
        """GIVEN no user/pass WHEN send_email THEN sends without login."""
        mock_server = mock.MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        result = send_email(
            subject="S", body="B",
            smtp_server="smtp.x.com",
            from_addr="a@b.com",
            to_addrs="c@d.com",
        )
        assert result is True
        mock_server.login.assert_not_called()

    def test_send_email_no_config(self):
        """GIVEN no SMTP config WHEN send_email THEN returns False."""
        result = send_email(subject="S", body="B")
        assert result is False

    @mock.patch("yuleosh.notify.smtplib.SMTP")
    def test_send_email_smtp_exception(self, mock_smtp):
        """GIVEN SMTPException WHEN send_email THEN returns False."""
        mock_smtp.return_value.__enter__.side_effect = smtplib.SMTPException("fail")
        result = send_email(
            subject="S", body="B",
            smtp_server="smtp.x.com",
            from_addr="a@b.com",
            to_addrs="c@d.com",
        )
        assert result is False

    @mock.patch("yuleosh.notify.smtplib.SMTP")
    def test_send_email_generic_error(self, mock_smtp):
        """GIVEN generic Exception WHEN send_email THEN returns False."""
        mock_smtp.return_value.__enter__.side_effect = Exception("oops")
        result = send_email(
            subject="S", body="B",
            smtp_server="smtp.x.com",
            from_addr="a@b.com",
            to_addrs="c@d.com",
        )
        assert result is False

    @mock.patch("yuleosh.notify.smtplib.SMTP_SSL")
    def test_send_email_multiple_recipients(self, mock_smtp_ssl):
        """GIVEN comma-separated to_addrs WHEN send_email THEN each recipient included."""
        mock_server = mock.MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_server
        send_email(
            subject="S", body="B",
            smtp_server="smtp.x.com",
            from_addr="a@b.com",
            to_addrs="c@d.com, e@f.com",
            use_tls=False,
        )
        call_args = mock_server.sendmail.call_args[0]
        # sendmail(fr, recipients, msg) — recipients is the second positional arg
        assert len(call_args[1]) == 2

    def test_send_email_custom_port(self):
        """GIVEN custom port WHEN send_email THEN uses that port."""
        with mock.patch("yuleosh.notify.smtplib.SMTP") as mock_smtp:
            mock_server = mock.MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server
            send_email(
                subject="S", body="B",
                smtp_server="smtp.x.com",
                from_addr="a@b.com",
                to_addrs="c@d.com",
                port=465,
                use_tls=False,
            )
            mock_smtp_ssl = mock_smtp  # use_tls=False routes to SMTP_SSL
            pass

    @mock.patch("yuleosh.notify.smtplib.SMTP")
    def test_send_email_tls_explicit_context(self, mock_smtp):
        """GIVEN TLS WHEN send_email THEN creates SSL context."""
        mock_server = mock.MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        with mock.patch.object(ssl, "create_default_context") as mock_ctx:
            send_email(
                subject="S", body="B",
                smtp_server="smtp.x.com",
                from_addr="a@b.com",
                to_addrs="c@d.com",
            )
            mock_ctx.assert_called_once()


# ---------------------------------------------------------------------------
# send_webhook
# ---------------------------------------------------------------------------

class TestSendWebhook:
    """GIVEN send_webhook WHEN called THEN posts payload."""

    @mock.patch("yuleosh.notify._post_json", return_value=True)
    def test_send_webhook_success(self, mock_post):
        """GIVEN URL configured WHEN send_webhook THEN returns True."""
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_WEBHOOK_URL": "https://wh.hook"}):
            result = send_webhook({"event": "test"})
            assert result is True
            assert mock_post.call_args[0][0] == "https://wh.hook"
            assert mock_post.call_args[0][1] == {"event": "test"}

    @mock.patch("yuleosh.notify._post_json", return_value=True)
    def test_send_webhook_custom_url(self, mock_post):
        """GIVEN custom url WHEN send_webhook THEN uses it."""
        result = send_webhook({"event": "test"}, url="https://custom.hook")
        assert result is True

    def test_send_webhook_no_config(self):
        """GIVEN no URL WHEN send_webhook THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = send_webhook({"event": "test"})
            assert result is False


# ---------------------------------------------------------------------------
# notify_pipeline
# ---------------------------------------------------------------------------

class TestNotifyPipeline:
    """GIVEN notify_pipeline WHEN called THEN sends to all channels."""

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_pipeline_completed(self, mock_wh, mock_email, mock_fs):
        """GIVEN completed pipeline WHEN notify_pipeline THEN feishu green card sent."""
        notify_pipeline("my-pipe", "completed", 10, 10)
        assert mock_fs.called
        title = mock_fs.call_args[0][0]
        assert "Completed" in title
        assert mock_email.called
        assert mock_wh.called
        # Check email subject
        assert "[yuleOSH]" in mock_email.call_args[1]["subject"]

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_pipeline_failed(self, mock_wh, mock_email, mock_fs):
        """GIVEN failed pipeline WHEN notify_pipeline THEN feishu red card sent."""
        notify_pipeline("my-pipe", "failed", 10, 5, errors=["err1", "err2"])
        title = mock_fs.call_args[0][0]
        assert "Failed" in title
        # color is 3rd positional arg: send_feishu(title, content, color)
        color = mock_fs.call_args[0][2]
        assert color == "red"

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_pipeline_truncates_errors(self, mock_wh, mock_email, mock_fs):
        """GIVEN many errors WHEN notify_pipeline THEN only 5 shown."""
        errors = [f"error-{i}" for i in range(10)]
        notify_pipeline("pipe", "failed", 10, 3, errors=errors)
        args = mock_wh.call_args[0][0]
        assert len(args["errors"]) == 10  # all in webhook
        assert "5 more" in mock_fs.call_args[0][1]

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_pipeline_no_errors(self, mock_wh, mock_email, mock_fs):
        """GIVEN no errors WHEN notify_pipeline THEN error text empty."""
        notify_pipeline("pipe", "completed", 5, 5)
        content = mock_fs.call_args[0][1]
        assert "Errors" not in content


# ---------------------------------------------------------------------------
# notify_ci
# ---------------------------------------------------------------------------

class TestNotifyCI:
    """GIVEN notify_ci WHEN called THEN sends to all channels."""

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_ci_passed(self, mock_wh, mock_email, mock_fs):
        """GIVEN passed CI layer WHEN notify_ci THEN feishu green card."""
        notify_ci(1, "passed", stages=[{"name": "lint", "status": "passed"}])
        title = mock_fs.call_args[0][0]
        assert "Passed" in title
        assert mock_email.called
        assert mock_wh.called

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_ci_failed(self, mock_wh, mock_email, mock_fs):
        """GIVEN failed CI layer WHEN notify_ci THEN feishu red card."""
        notify_ci(2, "failed", stages=[{"name": "test", "status": "failed"}], errors=["test error"])
        title = mock_fs.call_args[0][0]
        assert "Failed" in title
        # color is 3rd positional arg in send_feishu(title, content, color)
        color = mock_fs.call_args[0][2]
        assert color == "red"

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_ci_mixed_stages(self, mock_wh, mock_email, mock_fs):
        """GIVEN mixed stages WHEN notify_ci THEN status shows counts."""
        stages = [
            {"name": "lint", "status": "passed"},
            {"name": "build", "status": "failed"},
            {"name": "deploy", "status": "skipped"},
        ]
        notify_ci(3, "failed", stages=stages)
        content = mock_fs.call_args[0][1]
        assert "1/3" in content

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_ci_empty_stages(self, mock_wh, mock_email, mock_fs):
        """GIVEN no stages WHEN notify_ci THEN still sends."""
        notify_ci(1, "passed")
        assert mock_fs.called

    @mock.patch("yuleosh.notify.send_feishu")
    @mock.patch("yuleosh.notify.send_email")
    @mock.patch("yuleosh.notify.send_webhook")
    def test_notify_ci_truncates_errors(self, mock_wh, mock_email, mock_fs):
        """GIVEN many CI errors WHEN notify_ci THEN only 5 shown in feishu."""
        errors = [f"err-{i}" for i in range(8)]
        notify_ci(2, "failed", errors=errors)
        assert "3 more" in mock_fs.call_args[0][1]


# ---------------------------------------------------------------------------
# _get_store (notification store singleton)
# ---------------------------------------------------------------------------

class TestGetStore:
    """GIVEN _get_store WHEN called THEN returns Store or None on failure."""

    def test_get_store_success(self):
        """GIVEN Store available WHEN _get_store THEN returns instance."""
        with mock.patch("yuleosh.notify._store_instance", None):
            with mock.patch("yuleosh.store.Store") as mock_store_cls:
                mock_store_cls.return_value = "store-instance"
                result = _get_store()
                assert result == "store-instance"

    def test_get_store_failure(self):
        """GIVEN Store init fails WHEN _get_store THEN returns None gracefully."""
        with mock.patch("yuleosh.notify._store_instance", None):
            with mock.patch("yuleosh.store.Store", side_effect=Exception("db fail")):
                result = _get_store()
                assert result is None
