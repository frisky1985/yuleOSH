#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Layers — 验证与结果处理 (extracted from layers.py).

Provides:
  - validate_layer_result — 层结果验证
  - format_layer_summary — 层摘要格式化
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.layers.validator")


def validate_layer_result(result_path: str) -> dict:
    """Validate a layer result file and return summary.

    Parameters
    ----------
    result_path : str
        Path to the layer result JSON file.

    Returns
    -------
    dict
        Summary containing validation status.
    """
    path = Path(result_path)
    if not path.exists():
        return {"valid": False, "error": "Result file not found", "path": result_path}

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"valid": False, "error": str(e), "path": result_path}

    status = data.get("status", "unknown")
    stage_count = len(data.get("stages", []))
    error_count = len(data.get("errors", []))

    return {
        "valid": True,
        "status": status,
        "stage_count": stage_count,
        "error_count": error_count,
        "layer": data.get("layer"),
        "commit": data.get("commit"),
    }


def format_layer_summary(summary: dict) -> str:
    """Format a layer result summary for display.

    Parameters
    ----------
    summary : dict
        Result from validate_layer_result().

    Returns
    -------
    str
        Human-readable summary string.
    """
    if not summary.get("valid"):
        return f"\u274c Layer result invalid: {summary.get('error', 'unknown')}"

    status = summary.get("status", "unknown")
    icon = "\u2705" if status == "passed" else "\u274c"

    return (
        f"{icon} Layer {summary.get('layer', '?')} "
        f"(commit: {summary.get('commit', '?')[:8]}): "
        f"{status.upper()} "
        f"[{summary.get('stage_count', 0)} stages, "
        f"{summary.get('error_count', 0)} errors]"
    )
