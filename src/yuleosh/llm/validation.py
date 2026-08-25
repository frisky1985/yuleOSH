#!/usr/bin/env python3

# @req RS-001  @req CR-004
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
LLM Output Validation — schema, structure, and content validation.

Verifies LLM-generated output against structural templates and schemas,
supporting SHALL/SHOULD/MAY validation, JSON schema validation, and
required field checks.

Usage::

    from yuleosh.llm.validation import validate_llm_output

    schema = {
        "type": "object",
        "required_fields": ["title", "summary"],
        "shalls_required": True,
    }
    result = validate_llm_output(llm_output, schema)
    if not result["valid"]:
        print(result["errors"])
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger("llm.validation")


# ------------------------------------------------------------------
# Schema types
# ------------------------------------------------------------------

VALID_SCHEMA_TYPES = ("object", "array", "string", "json")


def validate_llm_output(output: str, schema: dict) -> dict:
    """Validate LLM-generated output against a schema.

    Supports:
      - JSON schema validation (if schema has 'json_schema')
      - SHALL/SHOULD/MAY structural validation
      - Required field checks for markdown/plain text output
      - Minimum length checks

    Parameters
    ----------
    output : str
        The raw LLM-generated text to validate.
    schema : dict
        Validation schema with optional keys:
        - ``type``: expected output type (``"object"``, ``"array"``,
          ``"string"``, ``"json"``).
        - ``required_fields``: list of field names that must be present
          in the output (for markdown headers or JSON keys).
        - ``shalls_required``: if True, at least one ``SHALL`` statement
          must be present.
        - ``json_schema``: a dict for JSON Schema (draft-07) validation
          when ``type`` is ``"json"`` or ``"object"``.
        - ``min_length``: minimum character count.
        - ``forbidden_patterns``: list of regex patterns that must NOT
          match.
        - ``required_patterns``: list of regex patterns that MUST match.
        - ``optional_fields``: list of SHOULD/MAY fields (warn if missing,
          not an error).

    Returns
    -------
    dict
        ``{"valid": bool, "errors": list[str], "warnings": list[str]}``
    """
    errors: list[str] = []
    warnings: list[str] = []

    schema_type = schema.get("type", "string")

    # --- Type-based validation ---

    if schema_type == "json":
        _validate_json(output, schema, errors, warnings)
    elif schema_type in ("object", "array"):
        # Try to parse as JSON first
        parsed = _try_parse_json(output)
        if parsed is not None:
            if schema_type == "object" and not isinstance(parsed, dict):
                errors.append(f"Expected JSON object, got {type(parsed).__name__}")
            elif schema_type == "array" and not isinstance(parsed, list):
                errors.append(f"Expected JSON array, got {type(parsed).__name__}")
            else:
                _validate_parsed(parsed, schema, errors, warnings)
        else:
            # Fallback: try markdown-style field extraction
            _validate_markdown_structure(output, schema, errors, warnings)
    elif schema_type == "string":
        _validate_string(output, schema, errors, warnings)
        # Also check required fields for string type output
        if schema.get("required_fields"):
            _validate_markdown_structure(output, schema, errors, warnings)

    # --- SHALL/SHOULD/MAY validation ---
    if schema.get("shalls_required", False):
        shall_count = len(_extract_shall_statements(output))
        if shall_count == 0:
            errors.append("No SHALL statements found (at least 1 required)")

    # --- Pattern validation ---
    forbidden = schema.get("forbidden_patterns", [])
    for pattern in forbidden:
        if re.search(pattern, output, re.IGNORECASE):
            errors.append(f"Output contains forbidden pattern: {pattern}")

    required_patterns = schema.get("required_patterns", [])
    for pattern in required_patterns:
        if not re.search(pattern, output, re.IGNORECASE):
            errors.append(f"Output missing required pattern: {pattern}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _try_parse_json(text: str) -> Any | None:
    """Try to parse text as JSON. Strips markdown code fences first."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` wrappers
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _validate_json(output: str, schema: dict, errors: list, warnings: list) -> None:
    """Validate output as pure JSON, optionally against a JSON schema."""
    parsed = _try_parse_json(output)
    if parsed is None:
        errors.append("Output is not valid JSON")
        return

    _validate_parsed(parsed, schema, errors, warnings)

    # Check required fields in the JSON
    required = schema.get("required_fields", [])
    if isinstance(parsed, dict):
        for field in required:
            if field not in parsed:
                errors.append(f"Missing required JSON field: '{field}'")
            elif parsed[field] is None or parsed[field] == "":
                errors.append(f"Required JSON field '{field}' is empty/null")

    optional = schema.get("optional_fields", [])
    if isinstance(parsed, dict):
        for field in optional:
            if field not in parsed:
                warnings.append(f"Optional JSON field '{field}' is missing")


def _validate_parsed(parsed: Any, schema: dict, errors: list, warnings: list) -> None:
    """Validate an already-parsed JSON object/array."""
    # JSON Schema (simple draft-07 support)
    json_schema = schema.get("json_schema")
    if json_schema and isinstance(parsed, dict):
        _validate_against_json_schema(parsed, json_schema, errors)

    # Required fields for objects
    required = schema.get("required_fields", [])
    if isinstance(parsed, dict):
        for field in required:
            if field not in parsed or parsed[field] is None:
                errors.append(f"Missing required field: '{field}'")


def _validate_markdown_structure(output: str, schema: dict, errors: list, warnings: list) -> None:
    """Validate markdown content for required fields and structure."""
    required = schema.get("required_fields", [])
    for field in required:
        # Check for markdown headers matching the field
        pattern = rf"^#{{1,6}}\s+{re.escape(field)}\s*$"
        if not re.search(pattern, output, re.MULTILINE):
            # Also check for field: value patterns
            inline_pattern = rf"(?:^|\n){re.escape(field)}\s*[:=]"
            if not re.search(inline_pattern, output, re.MULTILINE):
                errors.append(f"Missing required field/header: '{field}'")

    optional = schema.get("optional_fields", [])
    for field in optional:
        pattern = rf"^#{{1,6}}\s+{re.escape(field)}\s*$"
        if not re.search(pattern, output, re.MULTILINE):
            inline_pattern = rf"(?:^|\n){re.escape(field)}\s*[:=]"
            if not re.search(inline_pattern, output, re.MULTILINE):
                warnings.append(f"Optional field/header '{field}' not found")


def _validate_string(output: str, schema: dict, errors: list, warnings: list) -> None:
    """Validate plain string output."""
    min_length = schema.get("min_length", 0)
    if len(output.strip()) < min_length:
        errors.append(
            f"Output too short: {len(output.strip())} chars, "
            f"minimum {min_length}"
        )


def _validate_against_json_schema(instance: dict, js_schema: dict, errors: list) -> None:
    """Simple JSON Schema (draft-07 style) validation.

    Supports: type, required, properties (with type), enum, pattern,
    minLength, maxLength, minimum, maximum.
    """
    def _val(value: Any, node: dict, path: str) -> None:
        if "type" in node:
            expected = node["type"]
            type_map = {
                "string": str, "number": (int, float), "integer": int,
                "boolean": bool, "object": dict, "array": list,
            }
            py_type = type_map.get(expected)
            if py_type and not isinstance(value, py_type):
                errors.append(
                    f"Schema mismatch at {path}: expected {expected}, "
                    f"got {type(value).__name__}"
                )
                return

        if "enum" in node and value not in node["enum"]:
            errors.append(
                f"Schema mismatch at {path}: value '{value}' not in "
                f"allowed values {node['enum']}"
            )

        if isinstance(value, str):
            if "minLength" in node and len(value) < node["minLength"]:
                errors.append(f"Schema mismatch at {path}: too short ({len(value)} < {node['minLength']})")
            if "maxLength" in node and len(value) > node["maxLength"]:
                errors.append(f"Schema mismatch at {path}: too long ({len(value)} > {node['maxLength']})")
            if "pattern" in node and not re.match(node["pattern"], value):
                errors.append(f"Schema mismatch at {path}: does not match pattern {node['pattern']}")

        if isinstance(value, (int, float)):
            if "minimum" in node and value < node["minimum"]:
                errors.append(f"Schema mismatch at {path}: {value} < minimum {node['minimum']}")
            if "maximum" in node and value > node["maximum"]:
                errors.append(f"Schema mismatch at {path}: {value} > maximum {node['maximum']}")

        if isinstance(value, dict) and "properties" in node:
            for prop_name, prop_schema in node["properties"].items():
                if prop_name in value:
                    _val(value[prop_name], prop_schema, f"{path}.{prop_name}")

        if isinstance(value, list) and "items" in node:
            for i, item in enumerate(value):
                _val(item, node["items"], f"{path}[{i}]")

    if "required" in js_schema:
        for field in js_schema["required"]:
            if field not in instance:
                errors.append(f"Schema validation: missing required field '{field}'")

    _val(instance, js_schema, "$")


def _extract_shall_statements(output: str) -> list[str]:
    """Extract all SHALL statements from the output.

    A SHALL statement must include at least one word after 'SHALL'.
    Handles both list items and inline SHALL references.
    """
    statements = []
    seen = set()
    # Match lines that contain SHALL followed by at least one word
    # This matches:
    #   "- The system SHALL do X."
    #   "SHALL do X"
    #   "### SHALL: something"
    pattern = r"\bSHALL\b\s+\w[^.!?\n]*"
    for match in re.finditer(pattern, output):
        stmt = match.group().strip()
        if stmt and stmt not in seen:
            seen.add(stmt)
            statements.append(stmt)
    return statements
