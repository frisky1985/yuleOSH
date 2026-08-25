#!/usr/bin/env python3

# @tests src/yuleosh/llm/client.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests for llm/validation.py — validate_llm_output()
"""

from yuleosh.llm.validation import (
    validate_llm_output,
    _extract_shall_statements,
    _try_parse_json,
)


class TestValidateLlmOutput:
    """Coverage-boosting tests for llm/validation."""

    def test_valid_string_min_length(self):
        """String output meeting min_length passes."""
        schema = {"type": "string", "min_length": 10}
        result = validate_llm_output("Hello, world!", schema)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_string_too_short(self):
        """String output below min_length fails."""
        schema = {"type": "string", "min_length": 50}
        result = validate_llm_output("Short", schema)
        assert result["valid"] is False
        assert len(result["errors"]) >= 1

    def test_required_fields_markdown(self):
        """Markdown output missing required header fails."""
        schema = {
            "type": "string",
            "required_fields": ["Title", "Summary"],
        }
        result = validate_llm_output("Some random text without headers", schema)
        assert result["valid"] is False
        assert any("Title" in e for e in result["errors"])

    def test_required_fields_markdown_present(self):
        """Markdown output with required headers passes."""
        schema = {"type": "string", "required_fields": ["Title"]}
        result = validate_llm_output("# Title\n\nContent here.", schema)
        assert result["valid"] is True

    def test_shalls_required_present(self):
        """Output with SHALL statements passes shalls_required check."""
        schema = {"type": "string", "shalls_required": True}
        result = validate_llm_output("The system SHALL do something.", schema)
        assert result["valid"] is True

    def test_shalls_required_missing(self):
        """Output without SHALL statements fails shalls_required check."""
        schema = {"type": "string", "shalls_required": True}
        result = validate_llm_output("This is a description without SHALL.", schema)
        assert result["valid"] is False
        assert any("SHALL" in e for e in result["errors"])

    def test_json_type_valid(self):
        """Valid JSON output passes json type validation."""
        schema = {"type": "json", "required_fields": ["name", "version"]}
        result = validate_llm_output('{"name": "test", "version": "1.0"}', schema)
        assert result["valid"] is True

    def test_json_type_invalid(self):
        """Invalid JSON output fails json type validation."""
        schema = {"type": "json"}
        result = validate_llm_output("not json at all", schema)
        assert result["valid"] is False

    def test_json_missing_required_field(self):
        """JSON missing required field fails."""
        schema = {"type": "json", "required_fields": ["missing_field"]}
        result = validate_llm_output('{"name": "test"}', schema)
        assert result["valid"] is False
        assert any("missing_field" in e for e in result["errors"])

    def test_json_code_fence(self):
        """JSON wrapped in markdown code fence is parsed correctly."""
        schema = {"type": "json", "required_fields": ["key"]}
        result = validate_llm_output(
            '```json\n{"key": "value"}\n```', schema
        )
        assert result["valid"] is True

    def test_forbidden_pattern(self):
        """Output containing forbidden pattern fails."""
        schema = {"type": "string", "forbidden_patterns": ["dangerous"]}
        result = validate_llm_output("This is dangerous content.", schema)
        assert result["valid"] is False

    def test_required_pattern(self):
        """Output missing required pattern fails."""
        schema = {"type": "string", "required_patterns": ["MUST.*SPEC"]}
        result = validate_llm_output("Just some text.", schema)
        assert result["valid"] is False

    def test_optional_field_warning(self):
        """Missing optional fields produce warnings, not errors."""
        schema = {"type": "json", "optional_fields": ["optional_field"]}
        result = validate_llm_output('{"name": "test"}', schema)
        assert result["valid"] is True  # optional missing is not an error
        assert len(result["warnings"]) >= 1

    def test_json_schema_validation(self):
        """JSON Schema (draft-07) validation works."""
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer", "minimum": 1},
                    "name": {"type": "string"},
                },
            },
        }
        result = validate_llm_output('{"id": 42, "name": "test"}', schema)
        assert result["valid"] is True

    def test_json_schema_missing_required(self):
        """JSON Schema catches missing required fields."""
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                },
            },
        }
        result = validate_llm_output('{"name": "test"}', schema)
        assert result["valid"] is False

    def test_json_schema_type_mismatch(self):
        """JSON Schema catches type mismatch."""
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                },
            },
        }
        result = validate_llm_output('{"id": "not-a-number"}', schema)
        assert result["valid"] is False

    def test_json_schema_enum(self):
        """JSON Schema enum validation."""
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "properties": {
                    "status": {"enum": ["active", "inactive"]},
                },
            },
        }
        result = validate_llm_output('{"status": "unknown"}', schema)
        assert result["valid"] is False

    def test_extract_shall_statements(self):
        """_extract_shall_statements finds SHALL statements."""
        text = "The system SHALL do X.\nIt SHALL also do Y."
        stmts = _extract_shall_statements(text)
        assert len(stmts) >= 2

    def test_try_parse_json(self):
        """_try_parse_json handles JSON and markdown-fenced JSON."""
        assert _try_parse_json('{"a": 1}') == {"a": 1}
        assert _try_parse_json('```json\n{"b": 2}\n```') == {"b": 2}
        assert _try_parse_json("not json") is None

    def test_type_object_with_parsed_json(self):
        """type: object validates parsed JSON correctly."""
        schema = {"type": "object", "required_fields": ["name"]}
        result = validate_llm_output('{"name": "test", "value": 123}', schema)
        assert result["valid"] is True

    def test_type_array(self):
        """type: array validates parsed JSON array."""
        schema = {"type": "array"}
        result = validate_llm_output('[1, 2, 3]', schema)
        assert result["valid"] is True

    def test_type_array_got_object(self):
        """type: array fails if parsed result is an object."""
        schema = {"type": "array"}
        result = validate_llm_output('{"key": "value"}', schema)
        assert result["valid"] is False
