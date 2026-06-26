# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
YAML 配置文件验证器 (E06).

验证 ``.yuleosh/ci-config.yaml`` 和 ``misra-rules.yaml`` 的 schema 合规性。
用于 CI 门禁 — 确保配置格式正确后再执行后续流水线。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("ci.yaml_validator")

# ------------------------------------------------------------------
# Schema helpers
# ------------------------------------------------------------------

_CI_CONFIG_SCHEMA = {
    "ci": {
        "type": "dict",
        "keys": {
            "layers": {"type": "list", "items": "int"},
            "layer_dependencies": {"type": "dict"},
        },
    },
    "coverage": {
        "type": "dict",
        "keys": {
            "threshold_line": {"type": "float"},
            "threshold_condition": {"type": "float"},
            "strict": {"type": "bool"},
            "c_fail_under": {"type": "int"},
            "module_thresholds": {"type": "dict"},
        },
    },
    "docsync": {
        "type": "dict",
        "keys": {
            "enabled": {"type": "bool"},
            "rules": {"type": "list"},
            "mode": {"type": "str"},
            "exempt_paths": {"type": "list"},
            "critical_docs": {"type": "list"},
            "staleness_days": {"type": "int"},
            "audit": {"type": "dict"},
        },
    },
    "misra": {
        "type": "dict",
        "keys": {
            "enabled": {"type": "bool"},
            "addon": {"type": "str"},
            "fail_on_required": {"type": "bool"},
            "fail_on_violation": {"type": "bool"},
            "fail_on_advisory": {"type": "bool"},
            "fail_threshold": {"type": "int"},
            "violations_per_kloc": {"type": "float"},
            "cppcheck_std": {"type": "str"},
            "active_profile": {"type": "str"},
            "rule_texts_path": {"type": "str"},
            "suppress_rules": {"type": "list"},
            "rules": {"type": "dict"},
            "deviations": {"type": "list"},
            "alm": {"type": "dict"},
            "profiles": {"type": "dict"},
            "exclude_paths": {"type": "list"},
        },
    },
    "hardware_test": {"type": "dict"},
}

_MISRA_RULE_SCHEMA = {
    "severity": {"type": "str", "values": ["required", "advisory"]},
    "category": {"type": "str"},
    "description": {"type": "str"},
    "title": {"type": "str"},
    "spec_ref": {"type": "str"},
    "check_method": {"type": "str"},
    "auto_checkable": {"type": "bool"},
    "mcu": {"type": "str"},
    "profile": {"type": "str", "values": ["safety", "performance", "testing"]},
}


def _check_type(value: Any, expected: str, path: str) -> list[str]:
    """Check that *value* matches *expected* type. Returns list of errors."""
    errors: list[str] = []
    if expected == "str":
        if not isinstance(value, str):
            errors.append(f"{path}: expected str, got {type(value).__name__}")
    elif expected == "int":
        if not isinstance(value, int):
            errors.append(f"{path}: expected int, got {type(value).__name__}")
    elif expected == "float":
        if not isinstance(value, (int, float)):
            errors.append(f"{path}: expected float, got {type(value).__name__}")
    elif expected == "bool":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected bool, got {type(value).__name__}")
    elif expected == "dict":
        if not isinstance(value, dict):
            errors.append(f"{path}: expected dict, got {type(value).__name__}")
    elif expected == "list":
        if not isinstance(value, list):
            errors.append(f"{path}: expected list, got {type(value).__name__}")
    return errors


def _validate_against_schema(
    data: dict,
    schema: dict,
    prefix: str = "",
) -> list[str]:
    """Validate *data* against a schema dict. Returns list of error strings."""
    errors: list[str] = []

    if not isinstance(data, dict):
        errors.append(f"{prefix or 'root'}: expected dict, got {type(data).__name__}")
        return errors

    for field, expected in schema.items():
        field_path = f"{prefix}.{field}" if prefix else field
        if field not in data:
            continue  # Optional field — skip if not present

        value = data[field]
        expected_type = expected.get("type", "dict")

        # Type check
        errors.extend(_check_type(value, expected_type, field_path))

        if expected_type == "dict":
            sub_schema = expected.get("keys", {})
            if isinstance(value, dict):
                errors.extend(_validate_against_schema(value, sub_schema, field_path))
        elif expected_type == "list":
            items_type = expected.get("items")
            if items_type and isinstance(value, list):
                for i, item in enumerate(value):
                    item_path = f"{field_path}[{i}]"
                    errors.extend(_check_type(item, items_type, item_path))

        # Allowed values check
        allowed = expected.get("values")
        if allowed and value not in allowed and isinstance(value, str):
            errors.append(f"{field_path}: value '{value}' not in {allowed}")

    return errors


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def validate_ci_config(path: str) -> dict:
    """Validate ``ci-config.yaml`` schema compliance.

    Parameters
    ----------
    path : str
        Path to the ``ci-config.yaml`` file.

    Returns
    -------
    dict
        ``{"valid": True/False, "errors": [...], "path": path}``
    """
    errors: list[str] = []

    if not os.path.isfile(path):
        return {"valid": False, "errors": [f"File not found: {path}"], "path": path}

    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return {"valid": False, "errors": [f"YAML parse error: {e}"], "path": path}
    except OSError as e:
        return {"valid": False, "errors": [f"IO error: {e}"], "path": path}

    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["Root must be a dict"], "path": path}

    # Check top-level keys against schema
    errors.extend(_validate_against_schema(raw, _CI_CONFIG_SCHEMA))

    # Check unknown top-level keys
    known_keys = set(_CI_CONFIG_SCHEMA.keys())
    for key in raw:
        if key not in known_keys:
            errors.append(f"root.{key}: unexpected key")

    return {"valid": len(errors) == 0, "errors": errors, "path": path}


def validate_misra_rules(path: str) -> dict:
    """Validate ``misra-rules.yaml`` schema compliance.

    Parameters
    ----------
    path : str
        Path to the ``misra-rules.yaml`` file.

    Returns
    -------
    dict
        ``{"valid": True/False, "errors": [...], "path": path}``
    """
    errors: list[str] = []

    if not os.path.isfile(path):
        return {"valid": False, "errors": [f"File not found: {path}"], "path": path}

    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return {"valid": False, "errors": [f"YAML parse error: {e}"], "path": path}
    except OSError as e:
        return {"valid": False, "errors": [f"IO error: {e}"], "path": path}

    if not isinstance(raw, dict):
        return {"valid": False, "errors": ["Root must be a dict"], "path": path}

    # Validate each rule entry
    for rule_id, rule_data in raw.items():
        if rule_id == "meta":
            continue  # Skip meta block
        if not isinstance(rule_data, dict):
            errors.append(f"{rule_id}: expected dict, got {type(rule_data).__name__}")
            continue

        rule_errors = _validate_against_schema(rule_data, _MISRA_RULE_SCHEMA, rule_id)
        errors.extend(rule_errors)

    return {"valid": len(errors) == 0, "errors": errors, "path": path}


def validate_all(path: str = ".") -> dict:
    """Full YAML validation — check both ``ci-config.yaml`` and ``misra-rules.yaml``.

    Parameters
    ----------
    path : str
        Project root directory (default: current directory).

    Returns
    -------
    dict
        ``{"valid": True/False, "errors": {...}, "summaries": {...}}``
    """
    base = Path(path).resolve()

    ci_config_path = str(base / ".yuleosh" / "ci-config.yaml")
    misra_rules_path = str(base / "misra-rules.yaml")

    ci_result = validate_ci_config(ci_config_path)
    misra_result = validate_misra_rules(misra_rules_path)

    all_valid = ci_result["valid"] and misra_result["valid"]
    all_errors = {
        "ci-config": ci_result["errors"],
        "misra-rules": misra_result["errors"],
    }

    return {
        "valid": all_valid,
        "errors": all_errors,
        "summaries": {
            "ci-config": ci_result,
            "misra-rules": misra_result,
        },
        "path": str(base),
    }
