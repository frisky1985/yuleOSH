# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for llm/client.py — LLM API client edge cases.

Target: 80%+ branch coverage.
Covers: _do_request URLError, _resolve_env no keys, chat_completion
        retry exhaustion, null content, all retry paths.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


# ======================================================================
# _do_request — URLError coverage
# ======================================================================

class TestDoRequest:
    """GIVEN _do_request WHEN errors occur THEN raises RuntimeError."""

    def _make_response(self, data: bytes):
        """Create a simple response-like object that returns data on read()."""
        class FakeResponse:
            def read(self):
                return data
        return FakeResponse()

    def test_http_error(self):
        """GIVEN HTTP error WHEN _do_request THEN raises RuntimeError with detail."""
        from yuleosh.llm.client import _do_request
        req = urllib.request.Request("http://example.com", data=b"{}",
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with patch("yuleosh.llm.client.urllib.request.urlopen") as mock_urlopen:
            body = json.dumps({"error": {"message": "Rate limited"}}).encode()
            http_err = urllib.error.HTTPError(
                url="http://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={},
                fp=None,
            )
            http_err.fp = self._make_response(body)
            mock_urlopen.side_effect = http_err
            with pytest.raises(RuntimeError) as exc:
                _do_request(req)
            assert "LLM API error" in str(exc.value)

    def test_http_error_non_json(self):
        """GIVEN HTTP error with non-JSON body WHEN _do_request THEN raises."""
        from yuleosh.llm.client import _do_request
        req = urllib.request.Request("http://example.com", data=b"{}",
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with patch("yuleosh.llm.client.urllib.request.urlopen") as mock_urlopen:
            http_err = urllib.error.HTTPError(
                url="http://example.com",
                code=500,
                msg="Server Error",
                hdrs={},
                fp=None,
            )
            http_err.fp = self._make_response(b"not json at all")
            mock_urlopen.side_effect = http_err
            with pytest.raises(RuntimeError) as exc:
                _do_request(req)
            assert "LLM API error" in str(exc.value)

    def test_url_error(self):
        """GIVEN URLError WHEN _do_request THEN raises RuntimeError."""
        from yuleosh.llm.client import _do_request
        req = urllib.request.Request("http://example.com", data=b"{}",
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with patch("yuleosh.llm.client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError(reason="Connection refused")
            with pytest.raises(RuntimeError) as exc:
                _do_request(req)
            assert "LLM API connection error" in str(exc.value)

    def test_json_decode_error(self):
        """GIVEN invalid JSON response WHEN _do_request THEN raises RuntimeError."""
        from yuleosh.llm.client import _do_request
        req = urllib.request.Request("http://example.com", data=b"{}",
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with patch("yuleosh.llm.client.urllib.request.urlopen") as mock_urlopen:
            # Use a simple class instead of MagicMock to avoid chaining issues
            class FakeResp:
                def read(self):
                    return b"not-json{{{"
            mock_urlopen.return_value.__enter__.return_value = FakeResp()
            with pytest.raises(RuntimeError) as exc:
                _do_request(req)
            assert "invalid json" in str(exc.value).lower()

    def test_successful_request(self):
        """GIVEN valid response WHEN _do_request THEN returns dict."""
        from yuleosh.llm.client import _do_request
        req = urllib.request.Request("http://example.com", data=b"{}",
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with patch("yuleosh.llm.client.urllib.request.urlopen") as mock_urlopen:
            class FakeResp:
                def read(self):
                    return json.dumps({"key": "value"}).encode()
            mock_urlopen.return_value.__enter__.return_value = FakeResp()
            result = _do_request(req)
            assert result["key"] == "value"


# ======================================================================
# _resolve_env — no keys
# ======================================================================

class TestResolveEnv:
    """GIVEN _resolve_env WHEN no env keys THEN returns empty string."""

    def test_no_keys(self, monkeypatch):
        """GIVEN no LLM env vars WHEN _resolve_env THEN empty key."""
        from yuleosh.llm.client import _resolve_env
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        key, base, model = _resolve_env()
        assert key == ""
        assert base == "https://api.deepseek.com"
        assert model == "deepseek-chat"

    def test_custom_base_model(self, monkeypatch):
        """GIVEN LLM_BASE_URL and LLM_MODEL WHEN _resolve_env THEN custom."""
        from yuleosh.llm.client import _resolve_env
        monkeypatch.setenv("LLM_API_KEY", "key")
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.example.com")
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        key, base, model = _resolve_env()
        assert key == "key"
        assert base == "https://custom.example.com"
        assert model == "custom-model"

    def test_base_url_strips_trailing_slash(self, monkeypatch):
        """GIVEN base URL with trailing slash WHEN _resolve_env THEN stripped."""
        from yuleosh.llm.client import _resolve_env
        monkeypatch.setenv("LLM_API_KEY", "key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/")
        _, base, _ = _resolve_env()
        assert base == "https://api.example.com"


# ======================================================================
# _build_payload
# ======================================================================

class TestBuildPayload:
    """GIVEN _build_payload WHEN called THEN correct JSON body."""

    def test_default_params(self):
        """GIVEN system+user prompts WHEN _build_payload THEN default temp/max."""
        from yuleosh.llm.client import _build_payload
        payload = json.loads(_build_payload("sys", "user", "model-x"))
        assert payload["model"] == "model-x"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 4096
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2

    def test_custom_temperature(self):
        """GIVEN custom temperature WHEN _build_payload THEN uses it."""
        from yuleosh.llm.client import _build_payload
        payload = json.loads(_build_payload("sys", "user", "m", temperature=0.8))
        assert payload["temperature"] == 0.8

    def test_custom_max_tokens(self):
        """GIVEN custom max_tokens WHEN _build_payload THEN uses it."""
        from yuleosh.llm.client import _build_payload
        payload = json.loads(_build_payload("sys", "user", "m", max_tokens=1024))
        assert payload["max_tokens"] == 1024


# ======================================================================
# _build_request
# ======================================================================

class TestBuildRequest:
    """GIVEN _build_request WHEN called THEN correct headers."""

    def test_bearer_token(self):
        """GIVEN api key WHEN _build_request THEN Authorization header set."""
        from yuleosh.llm.client import _build_request
        req = _build_request("http://example.com", "sk-test", b"{}")
        assert req.headers["Authorization"] == "Bearer sk-test"
        assert req.headers["Content-type"] == "application/json"
        assert req.method == "POST"
        assert req.data == b"{}"


# ======================================================================
# chat_completion — edge cases
# ======================================================================

class TestChatCompletion:
    """GIVEN chat_completion WHEN edge cases THEN correct behavior."""

    def test_no_api_key(self, monkeypatch):
        """GIVEN no API key WHEN chat_completion THEN RuntimeError."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError) as exc:
            chat_completion("sys", "user")
        assert "No LLM API key found" in str(exc.value)

    def test_retry_exhaustion(self, monkeypatch):
        """GIVEN failing requests WHEN chat_completion THEN retries and raises."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.side_effect = RuntimeError("API error")
            with pytest.raises(RuntimeError) as exc:
                chat_completion("sys", "user", retries=2)
            # The original error is re-raised on last attempt
            assert "API error" in str(exc.value)
            assert mock_do.call_count == 2

    def test_retry_then_success(self, monkeypatch):
        """GIVEN failure then success WHEN chat_completion THEN succeeds."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            success_response = {
                "choices": [{"message": {"content": "Hello"}}],
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            mock_do.side_effect = [RuntimeError("fail"), success_response]
            result = chat_completion("sys", "user", retries=3)
            assert result["content"] == "Hello"
            assert mock_do.call_count == 2

    def test_null_content(self, monkeypatch):
        """GIVEN null content in response WHEN chat_completion THEN fallback."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            response = {
                "choices": [{
                    "message": {"content": None},
                    "finish_reason": "content_filter",
                }],
                "model": "deepseek-chat",
                "usage": {},
            }
            mock_do.return_value = response
            result = chat_completion("sys", "user")
            assert "[LLM refused" in result["content"]
            assert "content_filter" in result["content"]

    def test_no_choices(self, monkeypatch):
        """GIVEN no choices WHEN chat_completion THEN raises."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.return_value = {"id": "no-choices"}
            with pytest.raises(RuntimeError) as exc:
                chat_completion("sys", "user")
            assert "Unexpected API response" in str(exc.value)

    def test_empty_choices(self, monkeypatch):
        """GIVEN empty choices list WHEN chat_completion THEN raises."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.return_value = {"choices": []}
            with pytest.raises(RuntimeError) as exc:
                chat_completion("sys", "user")
            assert "Unexpected API response" in str(exc.value)

    def test_custom_timeout(self, monkeypatch):
        """GIVEN custom timeout WHEN chat_completion THEN passed to _do_request."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.return_value = {
                "choices": [{"message": {"content": "ok"}}],
                "model": "m",
                "usage": {},
            }
            result = chat_completion("sys", "user", timeout=30)
            assert result["content"] == "ok"
            # Verify timeout was passed
            call_kwargs = mock_do.call_args[1]
            assert call_kwargs.get("timeout") == 30

    def test_uses_model_from_response(self, monkeypatch):
        """GIVEN model in response WHEN chat_completion THEN uses it."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.return_value = {
                "choices": [{"message": {"content": "hi"}}],
                "model": "gpt-4",
                "usage": {"total_tokens": 5},
            }
            result = chat_completion("sys", "user")
            assert result["model"] == "gpt-4"

    def test_returns_usage(self, monkeypatch):
        """GIVEN usage in response WHEN chat_completion THEN returns it."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.return_value = {
                "choices": [{"message": {"content": "hello"}}],
                "model": "m",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            result = chat_completion("sys", "user")
            assert result["usage"]["prompt_tokens"] == 10

    def test_backoff_sleep(self, monkeypatch):
        """GIVEN retries WHEN chat_completion THEN sleeps between attempts."""
        from yuleosh.llm.client import chat_completion
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("yuleosh.llm.client._do_request") as mock_do:
            mock_do.side_effect = RuntimeError("fail")
            with patch("yuleosh.llm.client.time.sleep") as mock_sleep:
                with pytest.raises(RuntimeError):
                    chat_completion("sys", "user", retries=3)
                # Retry 1 fails -> sleep(1.0), Retry 2 fails -> sleep(2.0), Retry 3 fails -> raise
                assert mock_sleep.call_count == 2
