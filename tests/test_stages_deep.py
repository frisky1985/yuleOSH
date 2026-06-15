#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep tests for yuleosh.pipeline.stages — covers remaining uncovered lines.

Target coverage improvements:
  40-42   Store init exception (module-level)
  130-131 _parse_spec cache-read except
  142-143 _parse_spec cache-write except
  183-184 _parse_requirements except
  201-202 _parse_scenarios except
  212-228 _check_llm_key body (key-missing path + print + return None)
  251-252 _try_parse_hermes_json bare-JSON fail
  299-300 _try_parse_hermes_json brace-track JSON fail
  125→134 _parse_spec branch: _store is falsy → parse-fresh fallthrough
  139→145 _parse_spec branch: _store is falsy → skip cache-write
  290→303 _try_parse_hermes_json branch: brace-tracking exhausted → final fallback
"""

import json
import logging
import os
import sys
import subprocess
from pathlib import Path
from unittest import mock

import pytest


# ===================================================================
# timed_step — failure path (lines 73-76 in current file)
# ===================================================================


class TestTimedStepFailure:
    """Cover the timed_step decorator's except/re-raise path."""

    def test_handler_raises_re_raises_and_logs(self, caplog):
        """Verify that a failing handler goes through the except block and re-raises."""
        from yuleosh.pipeline.stages import timed_step

        def failing_handler(session):
            raise RuntimeError("boom")

        wrapped = timed_step(failing_handler)
        caplog.set_level(logging.INFO)

        with pytest.raises(RuntimeError, match="boom"):
            wrapped(session=None)

        # The FAILED log message must be present
        assert any(
            "FAILED after" in r.message for r in caplog.records
        ), f"Expected 'FAILED after' in logs: {[r.message for r in caplog.records]}"
        assert any(
            "failing_handler" in r.message for r in caplog.records
        ), f"Expected handler name in logs: {[r.message for r in caplog.records]}"

    def test_success_path_still_logs_ok(self, caplog):
        """Verify a normal handler goes through the happy path without regression."""
        from yuleosh.pipeline.stages import timed_step

        def ok_handler(session):
            return "ok"

        wrapped = timed_step(ok_handler)
        caplog.set_level(logging.INFO)

        result = wrapped(session=None)
        assert result == "ok"

        # Took log (not FAILED)
        assert any(
            "took" in r.message for r in caplog.records
        ), f"Expected 'took' in logs: {[r.message for r in caplog.records]}"


# ===================================================================
# Module-level store init failure (lines 40-42)
# ===================================================================


class TestModuleStoreInitFailure:
    """Cover the module-level 'except Exception' block for Store init.

    We use importlib.reload with a mocked Store class that raises on
    construction, forcing the except handler at lines 40-42 to execute.
    """

    def test_store_init_fails_except_assigns_none(self):
        """
        When ``Store()`` raises during import, the except block should
        log a warning and set ``_store = None``.
        """
        import importlib

        from yuleosh.pipeline import stages

        import store as store_mod
        orig_store_cls = store_mod.Store
        orig_stages_store = stages._store

        try:
            with mock.patch.object(store_mod, "Store") as mock_store_cls:
                mock_store_cls.side_effect = RuntimeError("store init mock fail")
                # Reload to re-execute the module-level try/except
                importlib.reload(stages)
            assert stages._store is None
        finally:
            store_mod.Store = orig_store_cls
            importlib.reload(stages)


# ===================================================================
# _parse_spec — cache exception paths (lines 130-131, 142-143)
# ===================================================================


class TestParseSpecCacheExceptions:
    """Cover cache-read and cache-write exception handlers in _parse_spec."""

    def test_cache_read_raises_logs_warning_falls_through(self, tmp_path, caplog):
        """When _store.get_cached_spec_parse raises, log warning and re-parse."""
        from yuleosh.pipeline import stages

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("### Req-001\n- The system SHALL work.\n")

        caplog.set_level(logging.WARNING)

        with mock.patch.object(stages, "_store") as mock_store:
            mock_store.get_cached_spec_parse.side_effect = RuntimeError("cache read boom")
            # The mock_store is truthy, so the try block is entered
            result = stages._parse_spec(str(spec_file))

        # Falls through and returns fresh-parse result
        assert "requirements" in result
        assert len(result["requirements"]) == 1
        assert result["requirements"][0]["name"] == "Req-001"
        assert any("cache read failed" in r.message.lower() for r in caplog.records), (
            f"Expected cache-read warning, got: {[r.message for r in caplog.records]}"
        )

    def test_cache_write_raises_logs_warning_returns_result(self, tmp_path, caplog):
        """When _store.cache_spec_parse raises, log warning and still return result."""
        from yuleosh.pipeline import stages

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("### Req-001\n- The system SHALL work.\n")

        caplog.set_level(logging.WARNING)

        # set return_value=None so the cache is a miss → falls through to fresh-parse
        with mock.patch.object(stages, "_store") as mock_store:
            mock_store.get_cached_spec_parse.return_value = None  # cache miss
            mock_store.cache_spec_parse.side_effect = RuntimeError("cache write boom")
            result = stages._parse_spec(str(spec_file))

        # Returns the fresh-parsed result despite write failure
        assert "requirements" in result
        assert len(result["requirements"]) == 1
        assert result["requirements"][0]["name"] == "Req-001"
        assert any("cache write failed" in r.message.lower() for r in caplog.records), (
            f"Expected cache-write warning, got: {[r.message for r in caplog.records]}"
        )


# ===================================================================
# _parse_spec — branch: _store is falsy (125→134, 139→145)
# ===================================================================


class TestParseSpecStoreIsNone:
    """Cover the False branch of ``if _store:`` at lines 125 and 139.

    When _store is None/falsy, the function should skip cache entirely and
    go straight to fresh parsing (125→134 arrow), and skip cache-write
    afterward (139→145 arrow).
    """

    def test_store_is_none_skips_cache_read_and_write(self, tmp_path):
        from yuleosh.pipeline import stages

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("### Req-001\n- The system SHALL work.\n")

        # Patch _store to None — both 'if _store:' guards become False
        with mock.patch.object(stages, "_store", None):
            result = stages._parse_spec(str(spec_file))

        assert "requirements" in result
        assert len(result["requirements"]) == 1


# ===================================================================
# _parse_requirements — except block (lines 183-184)
# ===================================================================


class TestParseRequirementsExceptions:
    """Cover the _parse_requirements except handler."""

    def test_read_text_raises_logs_warning_returns_empty(self, tmp_path, caplog):
        from yuleosh.pipeline.stages import _parse_requirements

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("dummy content")  # file exists

        caplog.set_level(logging.WARNING)

        # Patch Path.read_text so that after Path.exists() returns True,
        # the read raises
        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "read_text", side_effect=OSError("permission denied")):
                result = _parse_requirements(str(spec_file))

        assert result == []
        assert any("Failed to parse requirements" in r.message for r in caplog.records), (
            f"Expected parse-failure warning, got: {[r.message for r in caplog.records]}"
        )


# ===================================================================
# _parse_scenarios — except block (lines 201-202)
# ===================================================================


class TestParseScenariosExceptions:
    """Cover the _parse_scenarios except handler."""

    def test_read_text_raises_logs_warning_returns_empty(self, tmp_path, caplog):
        from yuleosh.pipeline.stages import _parse_scenarios

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("dummy content")  # file exists

        caplog.set_level(logging.WARNING)

        with mock.patch.object(Path, "exists", return_value=True):
            with mock.patch.object(Path, "read_text", side_effect=OSError("permission denied")):
                result = _parse_scenarios(str(spec_file))

        assert result == []
        assert any("Failed to parse scenarios" in r.message for r in caplog.records), (
            f"Expected parse-failure warning, got: {[r.message for r in caplog.records]}"
        )

    def test_file_not_found_logs_warning_returns_empty(self, tmp_path, caplog):
        from yuleosh.pipeline.stages import _parse_scenarios

        caplog.set_level(logging.WARNING)

        result = _parse_scenarios(str(tmp_path / "nope.md"))

        assert result == []
        assert any("not found for scenarios" in r.message.lower() for r in caplog.records), (
            f"Expected 'not found' warning, got: {[r.message for r in caplog.records]}"
        )

    def test_no_given_when_then_lines_returns_empty(self, tmp_path):
        from yuleosh.pipeline.stages import _parse_scenarios

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Just a regular spec\n\nNo scenario markers here.\n")

        result = _parse_scenarios(str(spec_file))
        assert result == []

    def test_parses_given_when_then_lines(self, tmp_path):
        from yuleosh.pipeline.stages import _parse_scenarios

        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "### GIVEN a valid user\n"
            "### WHEN they login\n"
            "### THEN they succeed\n"
        )

        result = _parse_scenarios(str(spec_file))
        assert len(result) == 3
        assert result[0] == "GIVEN a valid user"
        assert result[1] == "WHEN they login"
        assert result[2] == "THEN they succeed"


# ===================================================================
# _check_llm_key — key present / key missing (lines 212-228)
# ===================================================================


class TestCheckLlmKey:
    """Cover both branches of _check_llm_key."""

    def test_key_found_via_llm_api_key(self):
        from yuleosh.pipeline.stages import _check_llm_key

        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}):
            key = _check_llm_key()

        assert key == "sk-test"

    def test_key_found_via_openai_api_key(self):
        from yuleosh.pipeline.stages import _check_llm_key

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai"}):
            key = _check_llm_key()

        assert key == "sk-openai"

    def test_key_missing_prints_error_returns_none(self, capsys):
        from yuleosh.pipeline.stages import _check_llm_key

        with mock.patch.dict(os.environ, {}, clear=True):
            key = _check_llm_key()

        assert key is None

        # Verify the error message was printed
        captured = capsys.readouterr()
        assert "LLM API key not found" in captured.out


# ===================================================================
# _try_parse_hermes_json — bare JSON fail path (lines 251-252)
# ===================================================================


class TestTryParseHermesJsonBareFail:
    """Cover the bare-JSON fallthrough (JSONDecodeError caught, passes to next strategy)."""

    def test_bare_json_structure_passes_inner_except_then_fails_fully(self):
        """Input starts/ends with braces but is invalid JSON → except at line 251 is hit."""
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = "{invalid}"  # starts with {, ends with }, but not valid JSON

        result = _try_parse_hermes_json(raw, "test-session")

        # Since no other parse strategy works either, it should fall to final fallback
        assert result["status"] == "retry"
        assert "_raw_llm_output" in result

    def test_bare_json_fails_then_fence_succeeds(self):
        """Bare JSON fails, but ```json fences contain valid JSON.

        This exercises the bare-JSON except handler (lines 251-252) and the
        fence-parsing path (lines 278-283).
        """
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = (
            "{invalid}\n\n"
            "```json\n"
            '{"status": "passed", "findings": [], '
            '"finding_breakdown": {"critical": 0, "major": 0, "minor": 0, "info": 0}, '
            '"summary": "fence recovery"}'
            "\n```"
        )

        result = _try_parse_hermes_json(raw, "test-session")
        assert result["status"] == "passed"
        assert result["summary"] == "fence recovery"


# ===================================================================
# _try_parse_hermes_json — brace-tracking fail path (lines 299-300)
# and branch 290→303 (brace exhaustion → final fallback)
# ===================================================================


class TestTryParseHermesJsonBraceFail:
    """Cover brace-tracking JSON parse exception + fallthrough to final fallback."""

    def test_brace_tracking_fails_then_falls_to_final(self):
        """Leading text with {invalid} braces: brace-track finds it, parse fails, falls back."""
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = "Some text {invalid} trailing stuff"

        result = _try_parse_hermes_json(raw, "test-session")
        assert result["status"] == "retry"
        assert "_raw_llm_output" in result
        assert "invalid" in result["findings"][0]["message"].lower() or \
            result["findings"][0]["severity"] == "major"

    def test_brace_tracking_direct_find(self):
        """Brace tracking directly finds valid JSON without fence markers.

        Uses a single valid JSON block preceded by leading text.
        """
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = (
            "Here is the review: "
            '{"status": "passed", "findings": [], '
            '"finding_breakdown": {"critical": 0, "major": 0, "minor": 0, "info": 0}, '
            '"summary": "valid via brace track"}'
            "\n---\n_Generated by tool_"
        )

        result = _try_parse_hermes_json(raw, "test-session")
        assert result["status"] == "passed"
        assert result["summary"] == "valid via brace track"

    def test_non_json_fence_skips_and_falls_to_brace(self):
        """```python fence is skipped, brace tracking then finds valid JSON."""
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = (
            "```python\n"
            "x = 1\n"
            "```\n"
            'Tail: {"status": "passed", "findings": [], '
            '"finding_breakdown": {"critical": 0, "major": 0, "minor": 0, "info": 0}, '
            '"summary": "fence skip + brace ok"}'
        )

        result = _try_parse_hermes_json(raw, "test-session")
        assert result["status"] == "passed"
        assert result["summary"] == "fence skip + brace ok"

    def test_multiple_blocks_first_invalid_second_valid(self):
        """Two fenced blocks: first invalid JSON, second valid JSON."""
        from yuleosh.pipeline.stages import _try_parse_hermes_json

        raw = (
            "```json\n"
            "{not valid}\n"
            "```\n"
            "```json\n"
            '{"status": "passed", "findings": [], '
            '"finding_breakdown": {"critical": 0, "major": 0, "minor": 0, "info": 0}, '
            '"summary": "second block wins"}'
            "\n```"
        )

        result = _try_parse_hermes_json(raw, "test-session")
        assert result["status"] == "passed"
        assert result["summary"] == "second block wins"


# ===================================================================
# _call_llm — function path (lines 109-111)
# ===================================================================


class TestCallLlm:
    """Cover the _call_llm function body with both client paths."""

    def test_uses_session_llm_client(self):
        from yuleosh.pipeline.stages import _call_llm

        mock_fn = mock.MagicMock(return_value={"content": "injected"})
        mock_session = mock.MagicMock()
        mock_session.llm_client = mock_fn

        result = _call_llm(mock_session, "sys", "user")

        assert result["content"] == "injected"
        mock_fn.assert_called_once_with("sys", "user")

    def test_falls_back_to_global_chat_completion(self, monkeypatch):
        from yuleosh.pipeline.stages import _call_llm

        mock_fallback = mock.MagicMock(return_value={"content": "global"})
        mock_session = mock.MagicMock()
        mock_session.llm_client = None

        # Patch the deferred import target
        with mock.patch("yuleosh.pipeline.run.chat_completion", mock_fallback):
            result = _call_llm(mock_session, "sys", "user")

        assert result["content"] == "global"
        mock_fallback.assert_called_once_with("sys", "user")

    def test_passes_kwargs(self):
        from yuleosh.pipeline.stages import _call_llm

        mock_fn = mock.MagicMock(return_value={"content": "kwarg test"})
        mock_session = mock.MagicMock()
        mock_session.llm_client = mock_fn

        result = _call_llm(mock_session, "sys", "user", max_tokens=2048, temperature=0.7)

        assert result["content"] == "kwarg test"
        mock_fn.assert_called_once_with("sys", "user", max_tokens=2048, temperature=0.7)
