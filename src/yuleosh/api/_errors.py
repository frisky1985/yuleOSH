# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Internal-error helper for API endpoints (P1-7 / SEC-C2).

Centralizes the contract: log the real exception server-side (with
``exc_info``) and return a generic "Internal server error" payload to the
client — never echo exception details (absolute paths, SQL fragments,
module state) into the JSON error body.
"""

import logging

from . import json_error


def internal_error(module: str, e: BaseException,
                   status: int = 500) -> tuple[dict, int]:
    """Log ``e`` under ``api.<module>`` and return a generic error tuple."""
    logging.getLogger(f"api.{module}").error(
        "%s: %s", type(e).__name__, e, exc_info=True)
    return json_error("Internal server error", status)
