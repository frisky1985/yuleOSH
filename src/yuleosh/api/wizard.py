# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""First-run Wizard API handler."""

import os
import secrets

from . import json_ok, json_error
from yuleosh.store import Store


def _get_org_id_from_handler(handler) -> int:
    """Extract org_id from JWT in the Authorization header."""
    if handler is None:
        return 0
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return 0
    token = auth[7:]
    secret = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
    if not secret:
        return 0
    try:
        import jwt
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload.get("org_id") or payload.get("org", 0)
    except Exception:
        return 0


def handle_wizard(method: str, **kwargs):
    """Handle wizard-related API calls.

    POST /api/v1/wizard/complete — Mark the wizard as completed.
    """
    store = Store()

    if method != "POST":
        return json_error("Method not allowed", 405)

    org_id = _get_org_id_from_handler(kwargs.get("handler"))
    store.complete_wizard(org_id=org_id)
    return json_ok({"completed": True})
