#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Notification System — Multi-channel event notifications.

Supports:
  - Feishu webhook cards
  - SMTP email
  - Generic HTTP webhook

All channels are optional (disabled by default). Enable via environment variables.
"""

import json
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

log = logging.getLogger("notify")


# ---------------------------------------------------------------------------
# Env var keys
# ---------------------------------------------------------------------------

ENV_FEISHU_URL = "YULEOSH_NOTIFY_FEISHU_URL"
ENV_EMAIL_SMTP = "YULEOSH_NOTIFY_EMAIL_SMTP"
ENV_EMAIL_FROM = "YULEOSH_NOTIFY_EMAIL_FROM"
ENV_EMAIL_TO = "YULEOSH_NOTIFY_EMAIL_TO"
ENV_EMAIL_USER = "YULEOSH_NOTIFY_EMAIL_USER"
ENV_EMAIL_PASS = "YULEOSH_NOTIFY_EMAIL_PASS"
ENV_EMAIL_PORT = "YULEOSH_NOTIFY_EMAIL_PORT"
ENV_EMAIL_TLS = "YULEOSH_NOTIFY_EMAIL_TLS"
ENV_WEBHOOK_URL = "YULEOSH_NOTIFY_WEBHOOK_URL"

# Default SMTP port
_DEFAULT_SMTP_PORT = 587


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class NotifyConfig:
    """Runtime notification configuration, read from env vars.

    All fields are optional. A channel is enabled only when its required
    env var is set to a non-empty value.
    """

    @classmethod
    def from_env(cls) -> "NotifyConfig":
        return cls(
            feishu_url=os.environ.get(ENV_FEISHU_URL, "").strip(),
            email_smtp=os.environ.get(ENV_EMAIL_SMTP, "").strip(),
            email_from=os.environ.get(ENV_EMAIL_FROM, "").strip(),
            email_to=os.environ.get(ENV_EMAIL_TO, "").strip(),
            email_user=os.environ.get(ENV_EMAIL_USER, "").strip(),
            email_pass=os.environ.get(ENV_EMAIL_PASS, "").strip(),
            email_port=int(os.environ.get(ENV_EMAIL_PORT, str(_DEFAULT_SMTP_PORT))),
            email_tls=os.environ.get(ENV_EMAIL_TLS, "1").strip() in ("1", "true", "yes"),
            webhook_url=os.environ.get(ENV_WEBHOOK_URL, "").strip(),
        )

    def __init__(
        self,
        feishu_url: str = "",
        email_smtp: str = "",
        email_from: str = "",
        email_to: str = "",
        email_user: str = "",
        email_pass: str = "",
        email_port: int = _DEFAULT_SMTP_PORT,
        email_tls: bool = True,
        webhook_url: str = "",
    ):
        self.feishu_url = feishu_url
        self.email_smtp = email_smtp
        self.email_from = email_from
        self.email_to = email_to
        self.email_user = email_user
        self.email_pass = email_pass
        self.email_port = email_port
        self.email_tls = email_tls
        self.webhook_url = webhook_url

    @property
    def feishu_enabled(self) -> bool:
        return bool(self.feishu_url)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_smtp and self.email_from and self.email_to)

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.webhook_url)

    def to_dict(self) -> dict:
        return {
            "feishu_url": self.feishu_url or "",
            "feishu_enabled": self.feishu_enabled,
            "email_smtp": self.email_smtp or "",
            "email_from": self.email_from or "",
            "email_to": self.email_to or "",
            "email_enabled": self.email_enabled,
            "webhook_url": self.webhook_url or "",
            "webhook_enabled": self.webhook_enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NotifyConfig":
        return cls(
            feishu_url=d.get("feishu_url", ""),
            email_smtp=d.get("email_smtp", ""),
            email_from=d.get("email_from", ""),
            email_to=d.get("email_to", ""),
            email_user=d.get("email_user", ""),
            email_pass=d.get("email_pass", ""),
            email_port=int(d.get("email_port", _DEFAULT_SMTP_PORT)),
            email_tls=d.get("email_tls", True),
            webhook_url=d.get("webhook_url", ""),
        )

    def apply_to_env(self):
        """Apply this config back into the current process environment."""
        if self.feishu_url:
            os.environ[ENV_FEISHU_URL] = self.feishu_url
        if self.email_smtp:
            os.environ[ENV_EMAIL_SMTP] = self.email_smtp
        if self.email_from:
            os.environ[ENV_EMAIL_FROM] = self.email_from
        if self.email_to:
            os.environ[ENV_EMAIL_TO] = self.email_to
        if self.email_user:
            os.environ[ENV_EMAIL_USER] = self.email_user
        if self.email_pass:
            os.environ[ENV_EMAIL_PASS] = self.email_pass
        os.environ[ENV_EMAIL_PORT] = str(self.email_port)
        os.environ[ENV_EMAIL_TLS] = "1" if self.email_tls else "0"
        if self.webhook_url:
            os.environ[ENV_WEBHOOK_URL] = self.webhook_url


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------

# Keep a global store reference for persistent config
_store_instance = None


def _get_store():
    global _store_instance
    if _store_instance is None:
        try:
            from yuleosh.store import Store
            _store_instance = Store()
        except Exception as e:
            logging.getLogger("notify").warning("Notification send failed: %s", e)
            pass
    return _store_instance


def get_config() -> NotifyConfig:
    """Get the current notification config (from env vars)."""
    return NotifyConfig.from_env()


def set_config(cfg: NotifyConfig):
    """Persist a notification config to env vars (process-local)."""
    cfg.apply_to_env()


# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------

def _feishu_card_payload(title: str, content: str, color: str = "blue") -> dict:
    """Build a Feishu interactive card payload."""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": [
                {"tag": "markdown", "content": content},
                {
                    "tag": "hr",
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"yuleOSH · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        }
                    ],
                },
            ],
        },
    }


def _feishu_text_payload(text: str) -> dict:
    """Build a simple text message payload for Feishu."""
    return {"msg_type": "text", "content": {"text": text}}


def _post_json(url: str, payload: dict, timeout: int = 10) -> bool:
    """POST a JSON payload to a URL. Returns True on success."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8")
        log.info("Webhook POST %s -> %s %s", url, resp.status, body[:200])
        return 200 <= resp.status < 300
    except URLError as e:
        log.error("Webhook POST %s failed: %s", url, e)
        return False
    except Exception as e:
        log.error("Webhook POST %s error: %s", url, e)
        return False


# ---------------------------------------------------------------------------
# Public send functions
# ---------------------------------------------------------------------------

def send_feishu(
    title: str,
    content: str,
    color: str = "blue",
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a Feishu interactive card notification.

    Args:
        title: Card header title.
        content: Markdown body text.
        color: One of "blue", "green", "red", "yellow", "purple", "grey".
        webhook_url: Override the Feishu webhook URL (default: from env).

    Returns:
        True if sent successfully.
    """
    url = webhook_url or os.environ.get(ENV_FEISHU_URL, "")
    if not url:
        log.warning("Feishu not configured — set %s", ENV_FEISHU_URL)
        return False

    payload = _feishu_card_payload(title, content, color)
    success = _post_json(url, payload)
    if success:
        log.info("Feishu notification sent: %s", title)
    else:
        log.error("Feishu notification failed: %s", title)
    return success


def send_email(
    subject: str,
    body: str,
    smtp_server: Optional[str] = None,
    from_addr: Optional[str] = None,
    to_addrs: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: Optional[int] = None,
    use_tls: bool = True,
) -> bool:
    """Send an email notification.

    Args:
        subject: Email subject.
        body: Plain-text body.
        smtp_server: SMTP hostname. Default from env YULEOSH_NOTIFY_EMAIL_SMTP.
        from_addr: Sender address. Default from env YULEOSH_NOTIFY_EMAIL_FROM.
        to_addrs: Comma-separated recipient addresses. Default from env.
        username: SMTP auth user. Default from env YULEOSH_NOTIFY_EMAIL_USER.
        password: SMTP auth password. Default from env YULEOSH_NOTIFY_EMAIL_PASS.
        port: SMTP port. Default from env YULEOSH_NOTIFY_EMAIL_PORT or 587.
        use_tls: Use STARTTLS. Default from env YULEOSH_NOTIFY_EMAIL_TLS.

    Returns:
        True if sent successfully.
    """
    smtp = smtp_server or os.environ.get(ENV_EMAIL_SMTP, "")
    fr = from_addr or os.environ.get(ENV_EMAIL_FROM, "")
    to = to_addrs or os.environ.get(ENV_EMAIL_TO, "")

    if not (smtp and fr and to):
        log.warning("Email not configured — set %s, %s, %s", ENV_EMAIL_SMTP, ENV_EMAIL_FROM, ENV_EMAIL_TO)
        return False

    user = username or os.environ.get(ENV_EMAIL_USER, "") or fr
    pw = password or os.environ.get(ENV_EMAIL_PASS, "") or ""
    prt = port if port is not None else int(os.environ.get(ENV_EMAIL_PORT, str(_DEFAULT_SMTP_PORT)))
    tls = use_tls if use_tls is not None else os.environ.get(ENV_EMAIL_TLS, "1").strip() in ("1", "true", "yes")

    recipients = [a.strip() for a in to.split(",") if a.strip()]

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = fr
        msg["To"] = ", ".join(recipients)

        context = ssl.create_default_context() if tls else None
        if tls:
            with smtplib.SMTP(smtp, prt, timeout=15) as server:
                server.starttls(context=context)
                if user and pw:
                    server.login(user, pw)
                server.sendmail(fr, recipients, msg.as_string())
        else:
            with smtplib.SMTP_SSL(smtp, prt, timeout=15) as server:
                if user and pw:
                    server.login(user, pw)
                server.sendmail(fr, recipients, msg.as_string())

        log.info("Email sent to %s: %s", to, subject)
        return True
    except smtplib.SMTPException as e:
        log.error("Email send failed: %s", e)
        return False
    except Exception as e:
        log.error("Email send error: %s", e)
        return False


def send_webhook(
    payload: dict,
    url: Optional[str] = None,
) -> bool:
    """Send a generic webhook notification.

    Args:
        payload: Arbitrary JSON-serialisable dict.
        url: Target URL. Default from env YULEOSH_NOTIFY_WEBHOOK_URL.

    Returns:
        True if the POST returned a 2xx status.
    """
    target = url or os.environ.get(ENV_WEBHOOK_URL, "")
    if not target:
        log.warning("Webhook not configured — set %s", ENV_WEBHOOK_URL)
        return False

    return _post_json(target, payload)


# ---------------------------------------------------------------------------
# Convenience: pipeline events
# ---------------------------------------------------------------------------

def notify_pipeline(name: str, status: str, total_steps: int, completed_steps: int, errors: list[str] = None):
    """Send notifications for a pipeline completion or failure event.

    Sends to all enabled channels (Feishu, email, webhook).
    """
    errors = errors or []
    is_success = status == "completed"

    if is_success:
        title = "✅ yuleOSH Pipeline Completed"
        color = "green"
    else:
        title = "❌ yuleOSH Pipeline Failed"
        color = "red"

    error_text = ""
    if errors:
        error_text = "\n**Errors**:\n" + "\n".join(f"- {e}" for e in errors[:5])
        if len(errors) > 5:
            error_text += f"\n- ... and {len(errors) - 5} more"

    content = (
        f"**Pipeline**: {name}\n"
        f"**Status**: {'✅ Passed' if is_success else '❌ Failed'}\n"
        f"**Steps**: {completed_steps}/{total_steps}"
        f"{error_text}"
    )

    # Feishu
    send_feishu(title, content, color)

    # Email
    send_email(
        subject=f"[yuleOSH] Pipeline {name} {status}",
        body=(
            f"Pipeline: {name}\n"
            f"Status: {status}\n"
            f"Steps: {completed_steps}/{total_steps}\n"
            f"Errors: {', '.join(errors[:3]) if errors else 'None'}\n"
        ),
    )

    # Generic webhook
    send_webhook({
        "event": "pipeline",
        "name": name,
        "status": status,
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "errors": errors,
        "timestamp": datetime.now().isoformat(),
    })

    log.info("Pipeline notification sent: %s status=%s", name, status)


def notify_ci(layer: int, status: str, stages: list[dict] = None, errors: list[str] = None):
    """Send notifications for a CI layer completion or failure event."""
    stages = stages or []
    errors = errors or []
    is_success = status == "passed"

    if is_success:
        title = f"✅ yuleOSH CI Layer {layer} Passed"
        color = "green"
    else:
        title = f"❌ yuleOSH CI Layer {layer} Failed"
        color = "red"

    passed_stages = sum(1 for s in stages if s.get("status") == "passed")
    total_stages = len(stages)

    stage_details = ""
    if stages:
        stage_details = "\n**Stages**:\n" + "\n".join(
            f"- {'✅' if s.get('status') == 'passed' else '❌' if s.get('status') == 'failed' else '⏭️'} "
            f"{s.get('name', '?')}: {s.get('status', '?')}"
            for s in stages
        )

    error_text = ""
    if errors:
        error_text = "\n**Errors**:\n" + "\n".join(f"- {e}" for e in errors[:5])
        if len(errors) > 5:
            error_text += f"\n- ... and {len(errors) - 5} more"

    content = (
        f"**CI Layer**: {layer}\n"
        f"**Status**: {'✅ Passed' if is_success else '❌ Failed'}\n"
        f"**Stages**: {passed_stages}/{total_stages}"
        f"{stage_details}"
        f"{error_text}"
    )

    send_feishu(title, content, color)

    send_email(
        subject=f"[yuleOSH] CI Layer {layer} {status}",
        body=(
            f"CI Layer: {layer}\n"
            f"Status: {status}\n"
            f"Stages: {passed_stages}/{total_stages}\n"
            f"Errors: {', '.join(errors[:3]) if errors else 'None'}\n"
        ),
    )

    send_webhook({
        "event": "ci",
        "layer": layer,
        "status": status,
        "stages": stages,
        "errors": errors,
        "timestamp": datetime.now().isoformat(),
    })

    log.info("CI notification sent: layer=%s status=%s", layer, status)
