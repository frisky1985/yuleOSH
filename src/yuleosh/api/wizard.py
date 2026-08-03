# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""First-run Wizard API handler."""

from . import json_ok, json_error
from yuleosh.store import Store
from yuleosh.ui.auth_extended import JWT_SECRET, JWT_ALGORITHM  # A1/F1: unified source


def _get_org_id_from_handler(handler) -> int:
    """Extract org_id from JWT in the Authorization header.

    A1/F1 (v3.8.0): JWT secret from the single source (ui.auth_extended),
    no per-call random fallback (the old default made cross-call
    verification always fail).
    """
    if handler is None:
        return 0
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return 0
    token = auth[7:]
    try:
        import jwt
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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
