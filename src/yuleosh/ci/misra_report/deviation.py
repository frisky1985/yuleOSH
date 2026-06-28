#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI MISRA Report — Deviation.

Part of the misra_report/ package split from misra_report.py (Phase 2.2).
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("ci.misra_report")


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------





def _deviation_to_dict(dev: tuple | dict | object) -> dict:
    """Normalize a deviation entry to a dict with common fields.

    Accepts:
    - tuple[str, str] (backward compat: rule_id, file_pattern)
    - dict (rich format with rule_id, file_pattern, reason, approved_by,
      risk_level, expires, status, alm_ticket)
    - MisraDeviation dataclass object

    R5-P2-1: Also propagates ``alm_ticket`` field if present.
    """
    if isinstance(dev, dict):
        return {
            "deviation_rule": dev.get("rule_id", ""),
            "file_pattern": dev.get("file_pattern", ""),
            "reason": dev.get("reason", ""),
            "approved_by": dev.get("approved_by", ""),
            "risk_level": dev.get("risk_level", "mid"),
            "expires": dev.get("expires", ""),
            "status": dev.get("status", "pending"),
            # R5-P2-1: ALM ticket reference
            "alm_ticket": dev.get("alm_ticket", ""),
        }
    if isinstance(dev, tuple):
        # Tuple format: (rule_id, file_pattern) or (rule_id, file_pattern, reason, ...)
        fields = tuple(dev)
        return {
            "deviation_rule": fields[0] if len(fields) > 0 else "",
            "file_pattern": fields[1] if len(fields) > 1 else "",
            "reason": fields[2] if len(fields) > 2 else "",
            "approved_by": fields[3] if len(fields) > 3 else "",
            "risk_level": fields[4] if len(fields) > 4 else "mid",
            "expires": fields[5] if len(fields) > 5 else "",
            "status": fields[6] if len(fields) > 6 else "pending",
            "alm_ticket": fields[7] if len(fields) > 7 else "",
        }
    # Object with attribute access (MisraDeviation)
    return {
        "deviation_rule": getattr(dev, "rule_id", ""),
        "file_pattern": getattr(dev, "file_pattern", ""),
        "reason": getattr(dev, "reason", ""),
        "approved_by": getattr(dev, "approved_by", ""),
        "risk_level": getattr(dev, "risk_level", "mid"),
        "expires": getattr(dev, "expires", ""),
        "status": getattr(dev, "status", "pending"),
        # R5-P2-1: ALM ticket reference
        "alm_ticket": getattr(dev, "alm_ticket", ""),
    }


def _is_deviation_expired(expires_str: str) -> bool:
    """Check if a deviation has expired based on its expires date.

    Returns True if expires is a valid ISO date and is in the past.
    Returns False if expires is empty or unparseable (assumes no expiry).
    """
    if not expires_str:
        return False
    try:
        from datetime import datetime
        expiry = datetime.fromisoformat(expires_str)
        return expiry < datetime.now()
    except (ValueError, TypeError):
        return False


def _match_deviation(
    rule_id: str,
    file_path: str,
    deviations: list,  # list[tuple | dict] — normalized internally
) -> tuple[bool, dict | None]:
    """Check if a violation matches any deviation record.

    Supports both simple tuple format (rule_id, file_pattern) and rich
    dict format with risk_level, expires, reason, approved_by, status.

    Returns (matched, deviation_info) where deviation_info contains
    the matched deviation details if found, including:
      - deviation_rule, file_pattern
      - reason, approved_by, risk_level, expires, status
      - risk_level_info: str description of risk level
      - expiration_status: dict with is_expired / expires fields
    """
    import fnmatch
    for dev in deviations:
        dev_dict = _deviation_to_dict(dev)
        dev_rule = dev_dict["deviation_rule"]
        dev_pattern = dev_dict["file_pattern"]

        # Match rule
        rule_match = (dev_rule == rule_id)
        if not rule_match and dev_rule:
            # Try suffix matching (e.g. rule_id="misra-c2023-17.7", dev="17.7")
            suffix = dev_rule.split("-")[-1] if "-" in dev_rule else dev_rule
            rule_match = rule_id.endswith(suffix)

        if rule_match and fnmatch.fnmatch(file_path, dev_pattern):
            # R3-P0-2: Enrich with risk_level info + expiration check
            risk_level = dev_dict.get("risk_level", "mid")
            expires = dev_dict.get("expires", "")
            is_expired = _is_deviation_expired(expires)

            info = dict(dev_dict)
            info["risk_level_info"] = {
                "low": "Low risk — accepted with documentation",
                "mid": "Medium risk — accepted with review",
                "high": "High risk — requires urgent resolution",
            }.get(risk_level, "Unknown risk level")
            info["expiration_status"] = {
                "is_expired": is_expired,
                "expires": expires,
            }
            return True, info
    return False, None
