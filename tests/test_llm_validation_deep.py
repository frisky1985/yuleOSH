#!/usr/bin/env python3

# @tests src/yuleosh/llm/validation.py

"""Deep tests for llm/validation.py — CR-004 input validation."""

import pytest

from yuleosh.llm.validation import (
    validate_llm_output,
    _try_parse_json,
    _extract_shall_statements,
    VALID_SCHEMA_TYPES,
)


class TestValidateJsonType:
    def test_valid_json_object(self):
        output = '{"title": "hello", "summary": "world"}'
        result = validate_llm_output(output, {"type": "json", "required_fields": ["title", "summary"]})
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_required_field(self):
        output = '{"title": "hello"}'
        result = validate_llm_output(output, {"type": "json", "required_fields": ["title", "summary"]})
        assert result["valid"] is False
        assert any("summary" in e for e in result["errors"])

    def test_empty_required_field(self):
        output = '{"title": ""}'
        result = validate_llm_output(output, {"type": "json", "required_fields": ["title"]})
        assert result["valid"] is False
        assert any("empty" in e for e in result["errors"])

    def test_invalid_json(self):
        output = "not json at all"
        result = validate_llm_output(output, {"type": "json"})
        assert result["valid"] is False
        assert any("not valid JSON" in e for e in result["errors"])

    def test_json_with_code_fence(self):
        output = '```json\n{"title": "hello"}\n```'
        result = validate_llm_output(output, {"type": "json", "required_fields": ["title"]})
        assert result["valid"] is True

    def test_optional_field_missing_is_warning(self):
        output = '{"title": "hello"}'
        result = validate_llm_output(output, {"type": "json", "optional_fields": ["description"]})
        assert result["valid"] is True
        assert any("description" in w for w in result["warnings"])


class TestValidateObjectType:
    def test_valid_object(self):
        output = '{"name": "test"}'
        result = validate_llm_output(output, {"type": "object"})
        assert result["valid"] is True

    def test_array_rejected_as_object(self):
        output = '[1, 2, 3]'
        result = validate_llm_output(output, {"type": "object"})
        assert result["valid"] is False
        assert any("Expected JSON object" in e for e in result["errors"])


class TestValidateArrayType:
    def test_valid_array(self):
        output = '[1, 2, 3]'
        result = validate_llm_output(output, {"type": "array"})
        assert result["valid"] is True

    def test_object_rejected_as_array(self):
        output = '{"a": 1}'
        result = validate_llm_output(output, {"type": "array"})
        assert result["valid"] is False
        assert any("Expected JSON array" in e for e in result["errors"])


class TestValidateStringType:
    def test_min_length_pass(self):
        result = validate_llm_output("hello world", {"type": "string", "min_length": 5})
        assert result["valid"] is True

    def test_min_length_fail(self):
        result = validate_llm_output("hi", {"type": "string", "min_length": 10})
        assert result["valid"] is False
        assert any("too short" in e for e in result["errors"])


class TestShallRequired:
    def test_shall_present(self):
        output = "The system SHALL process input data."
        result = validate_llm_output(output, {"type": "string", "shalls_required": True})
        assert result["valid"] is True

    def test_shall_missing(self):
        output = "This is a description without shall."
        result = validate_llm_output(output, {"type": "string", "shalls_required": True})
        assert result["valid"] is False
        assert any("SHALL" in e for e in result["errors"])


class TestPatternValidation:
    def test_forbidden_pattern_detected(self):
        output = "This contains TODO: fix later"
        result = validate_llm_output(output, {"type": "string", "forbidden_patterns": [r"TODO:"]})
        assert result["valid"] is False

    def test_required_pattern_missing(self):
        output = "Some output without the marker"
        result = validate_llm_output(output, {"type": "string", "required_patterns": [r"VERSION-\d+"]})
        assert result["valid"] is False

    def test_required_pattern_present(self):
        output = "Output VERSION-42 included"
        result = validate_llm_output(output, {"type": "string", "required_patterns": [r"VERSION-\d+"]})
        assert result["valid"] is True


class TestMarkdownStructure:
    def test_required_header_present(self):
        output = "# Summary\nSome content\n## Details\nMore"
        result = validate_llm_output(output, {"type": "object", "required_fields": ["Summary"]})
        assert result["valid"] is True

    def test_required_header_missing(self):
        output = "# Only One Section\nContent"
        result = validate_llm_output(output, {"type": "object", "required_fields": ["Summary", "Details"]})
        assert result["valid"] is False
        assert any("Details" in e for e in result["errors"])


class TestJsonSchema:
    def test_type_mismatch(self):
        output = '{"count": "not_a_number"}'
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
            },
        }
        result = validate_llm_output(output, schema)
        assert result["valid"] is False

    def test_enum_violation(self):
        output = '{"status": "unknown"}'
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["active", "inactive"]}},
            },
        }
        result = validate_llm_output(output, schema)
        assert result["valid"] is False

    def test_minimum_maximum(self):
        output = '{"value": 150}'
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "properties": {"value": {"type": "number", "minimum": 0, "maximum": 100}},
            },
        }
        result = validate_llm_output(output, schema)
        assert result["valid"] is False

    def test_valid_schema(self):
        output = '{"name": "test", "count": 5}'
        schema = {
            "type": "json",
            "json_schema": {
                "type": "object",
                "required": ["name", "count"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "count": {"type": "integer", "minimum": 0},
                },
            },
        }
        result = validate_llm_output(output, schema)
        assert result["valid"] is True


class TestHelpers:
    def test_try_parse_json_valid(self):
        assert _try_parse_json('{"a": 1}') == {"a": 1}

    def test_try_parse_json_invalid(self):
        assert _try_parse_json("not json") is None

    def test_try_parse_json_code_fence(self):
        assert _try_parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_extract_shall_statements(self):
        text = "The system SHALL do X.\nThe system SHALL do Y."
        stmts = _extract_shall_statements(text)
        assert len(stmts) == 2

    def test_extract_shall_empty(self):
        assert _extract_shall_statements("no shall here") == []

    def test_valid_schema_types(self):
        assert "json" in VALID_SCHEMA_TYPES
        assert "object" in VALID_SCHEMA_TYPES
        assert "string" in VALID_SCHEMA_TYPES
