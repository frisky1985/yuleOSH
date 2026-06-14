# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""First-run Wizard API handler."""

from . import json_ok, json_error
from yuleosh.store import Store


def handle_wizard(method: str, **kwargs):
    """Handle wizard-related API calls.

    POST /api/v1/wizard/complete — Mark the wizard as completed.
    """
    store = Store()

    if method != "POST":
        return json_error("Method not allowed", 405)

    store.complete_wizard()
    return json_ok({"completed": True})
