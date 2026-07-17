# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Notification config endpoints — GET/PUT notification settings."""

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
def handle_notify(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to notification sub-resources."""
    if path_tail in ("", "config"):
        if method == "GET":
            return _get_config()
        if method == "PUT":
            return _put_config(body)
        return json_error("Use GET or PUT for config", 405)

    return json_error(f"Unknown notify resource: {path_tail}", 404)


def _get_config():
    """GET /api/v1/notify/config — return current notification config."""
    from yuleosh.notify import get_config

    cfg = get_config()
    return json_ok(cfg.to_dict())


def _put_config(body: dict):
    """PUT /api/v1/notify/config — update notification config.

    All fields are optional. Only provided fields are updated.
    """
    from yuleosh.notify import get_config, set_config, NotifyConfig

    if not isinstance(body, dict):
        return json_error("Body must be a JSON object", 400)

    current = get_config()
    cfg = NotifyConfig(
        feishu_url=body.get("feishu_url", current.feishu_url),
        email_smtp=body.get("email_smtp", current.email_smtp),
        email_from=body.get("email_from", current.email_from),
        email_to=body.get("email_to", current.email_to),
        email_user=body.get("email_user", current.email_user),
        email_pass=body.get("email_pass", current.email_pass),
        email_port=int(body.get("email_port", current.email_port)),
        email_tls=body.get("email_tls", current.email_tls) if "email_tls" in body else current.email_tls,
        webhook_url=body.get("webhook_url", current.webhook_url),
    )

    set_config(cfg)
    return json_ok(cfg.to_dict())
