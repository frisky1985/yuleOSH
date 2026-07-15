"""Tests for pipeline/stages — LLM call, spec parsing, and timing utilities."""

import pytest
import json
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

from yuleosh.pipeline.stages import (
    timed_step,
    _call_llm,
    _check_llm_key,
    _parse_spec,
    _parse_requirements,
    _parse_scenarios,
    _try_parse_hermes_json,
    _get_spec_mtime,
)


class TestTimedStep:
    """Test timed_step decorator."""

    def test_timed_step_success(self):
        calls = []

        @timed_step
        def my_step(session):
            calls.append("called")
            return "result"

        result = my_step("session")
        assert result == "result"
        assert len(calls) == 1

    def test_timed_step_exception(self):
        @timed_step
        def failing_step(session):
            raise ValueError("Oops")

        with pytest.raises(ValueError):
            failing_step("session")


class TestCallLlm:
    """Test LLM call helper."""

    def test_call_llm_with_injected_client(self):
        """Injected client is used."""
        mock_client = MagicMock(return_value={"content": "mock response"})
        session = MagicMock()
        session.llm_client = mock_client

        result = _call_llm(session, "system", "user")
        assert result["content"] == "mock response"
        mock_client.assert_called_once_with("system", "user")

    @patch("yuleosh.pipeline.stages.llm.chat_completion")
    def test_call_llm_fallback(self, mock_fallback):
        """Fallback to global chat_completion."""
        mock_fallback.return_value = {"content": "fallback"}
        session = MagicMock()
        session.llm_client = None

        with patch("yuleosh.pipeline.run.chat_completion", mock_fallback):
            result = _call_llm(session, "sys", "usr")
            assert result["content"] == "fallback"

    def test_call_llm_with_kwargs(self):
        """Additional kwargs passed through."""
        mock_client = MagicMock(return_value={"content": "r"})
        session = MagicMock()
        session.llm_client = mock_client

        _call_llm(session, "sys", "usr", max_tokens=2048, temperature=0.5)
        mock_client.assert_called_once_with("sys", "usr", max_tokens=2048, temperature=0.5)


class TestCheckLlmKey:
    """Test LLM key checking."""

    def test_key_found(self):
        with patch("yuleosh.pipeline.stages.llm.os.environ.get") as mock_get:
            mock_get.return_value = "sk-test-key"
            key = _check_llm_key()
            assert key == "sk-test-key"

    def test_key_found_alternative(self):
        def environ_get(key, default=None):
            if key == "OPENAI_API_KEY":
                return "sk-openai"
            return None

        with patch("yuleosh.pipeline.stages.llm.os.environ.get", side_effect=environ_get):
            key = _check_llm_key()
            assert key == "sk-openai"

    def test_key_not_found(self):
        with patch("yuleosh.pipeline.stages.llm.os.environ.get") as mock_get:
            mock_get.return_value = None
            key = _check_llm_key()
            assert key is None


class TestParseSpec:
    """Test spec parsing from stages module."""

    def test_parse_requirements_found(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("""# Spec

### Req-001: Login

- The system SHALL authenticate users
- The system SHALL validate passwords

### Req-002: Logout

- The system SHALL end session

### Scenario: Login Flow

- GIVEN user registered
- WHEN user logs in
- THEN user is redirected
""")
        result = _parse_spec(str(f))
        assert len(result["requirements"]) == 2
        assert result["requirements"][0]["name"] == "Req-001: Login"
        assert len(result["requirements"][0]["shall_statements"]) == 2

    def test_parse_requirements_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("# Just a header")
        result = _parse_spec(str(f))
        assert len(result["requirements"]) == 0
        assert len(result["scenarios"]) == 0

    def test_parse_spec_file_not_found(self):
        result = _parse_spec("/nonexistent/file.md")
        assert len(result["requirements"]) == 0
        assert len(result["scenarios"]) == 0

    def test_parse_scenarios(self, tmp_path):
        f = tmp_path / "scenarios.md"
        f.write_text("""
### Scenario: GIVEN user exists WHEN action THEN result
### Scenario: WHEN system starts THEN initialization runs
""")
        scenarios = _parse_scenarios(str(f))
        assert len(scenarios) == 2

    def test_parse_scenarios_file_not_found(self):
        scenarios = _parse_scenarios("/nonexistent/file.md")
        assert len(scenarios) == 0


class TestTryParseHermesJson:
    """Test Hermes JSON parsing."""

    def test_bare_json(self):
        raw = '{"status": "passed", "findings": []}'
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "passed"

    def test_json_with_code_fence(self):
        raw = 'Here is the review:\n```json\n{"status": "passed", "findings": []}\n```\nDone.'
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "passed"

    def test_json_without_lang_fence(self):
        raw = '```\n{"status": "passed"}\n```'
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "passed"

    def test_json_with_non_json_fence(self):
        """Non-JSON code fences are skipped."""
        raw = '```python\nprint("hello")\n```\n```json\n{"status": "passed"}\n```'
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "passed"

    def test_brace_extraction(self):
        """Extract JSON from surrounding text."""
        raw = 'The review result is: {"status": "passed", "count": 5} and more text.'
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "passed"

    def test_retry_fallback(self):
        """Unparseable output returns retry status."""
        raw = "This is not JSON at all. Just plain text."
        result = _try_parse_hermes_json(raw, "session-1")
        assert result["status"] == "retry"
        assert "_raw_llm_output" in result
        assert len(result["findings"]) > 0

    def test_missing_fields_filled(self):
        """Bare JSON with all fields passes through."""
        raw = '{"status": "passed", "findings": [], "summary": "OK"}'
        result = _try_parse_hermes_json(raw, "s1")
        assert result["summary"] == "OK"

    def test_get_spec_mtime_missing(self):
        mtime = _get_spec_mtime("/nonexistent")
        assert mtime == 0.0
