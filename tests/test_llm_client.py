# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Unit tests for src/llm/client.py — LLM API client.

Tests the OpenAI-compatible chat completion client with mocked HTTP.
Covers: payload building, key resolution, retry logic, error handling,
timeouts, malformed responses, and the main chat_completion flow.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from unittest import mock

import pytest

# Ensure we import the module under test without side effects
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.llm.client import (
    _build_payload,
    _build_request,
    _do_request,
    _resolve_env,
    chat_completion,
)


# ---------------------------------------------------------------------------
# _resolve_env tests
# ---------------------------------------------------------------------------

class TestResolveEnv:
    """Tests for _resolve_env() — LLM API key resolution."""

    def test_uses_llm_api_key_first(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "key-llm")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key-deepseek")
        monkeypatch.setenv("OPENAI_API_KEY", "key-openai")
        key, base, model = _resolve_env()
        assert key == "key-llm"

    def test_falls_back_to_deepseek(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "key-deepseek")
        monkeypatch.setenv("OPENAI_API_KEY", "key-openai")
        key, _, _ = _resolve_env()
        assert key == "key-deepseek"

    def test_falls_back_to_openai(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "key-openai")
        key, _, _ = _resolve_env()
        assert key == "key-openai"

    def test_empty_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        key, _, _ = _resolve_env()
        assert key == ""

    def test_default_base_url(self, monkeypatch):
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        _, base, _ = _resolve_env()
        assert base == "https://api.deepseek.com"

    def test_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "https://custom.api.com")
        _, base, _ = _resolve_env()
        assert base == "https://custom.api.com"

    def test_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/")
        _, base, _ = _resolve_env()
        assert base == "https://api.example.com"

    def test_default_model(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        _, _, model = _resolve_env()
        assert model == "deepseek-chat"

    def test_custom_model(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        _, _, model = _resolve_env()
        assert model == "gpt-4"


# ---------------------------------------------------------------------------
# _build_payload tests
# ---------------------------------------------------------------------------

class TestBuildPayload:
    """Tests for _build_payload() — JSON request body construction."""

    def test_returns_bytes(self):
        payload = _build_payload("sys", "user", "test-model")
        assert isinstance(payload, bytes)

    def test_valid_json(self):
        payload = _build_payload("Be helpful", "Hello", "gpt-4")
        data = json.loads(payload)
        assert data["model"] == "gpt-4"
        assert data["temperature"] == 0.3
        assert data["max_tokens"] == 4096
        assert data["stream"] is False

    def test_messages_structure(self):
        payload = _build_payload("system prompt", "user message", "m", temperature=0.7, max_tokens=2048)
        data = json.loads(payload)
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "system"
        assert data["messages"][0]["content"] == "system prompt"
        assert data["messages"][1]["role"] == "user"
        assert data["messages"][1]["content"] == "user message"
        assert data["temperature"] == 0.7
        assert data["max_tokens"] == 2048

    def test_unicode_content(self):
        payload = _build_payload("你好", "世界", "m")
        data = json.loads(payload)
        assert data["messages"][0]["content"] == "你好"
        assert data["messages"][1]["content"] == "世界"


# ---------------------------------------------------------------------------
# _build_request tests
# ---------------------------------------------------------------------------

class TestBuildRequest:
    """Tests for _build_request() — urllib.Request construction."""

    def test_has_correct_url(self):
        payload = b"{}"
        req = _build_request("https://api.example.com/v1/chat/completions", "sk-test", payload)
        assert req.full_url == "https://api.example.com/v1/chat/completions"

    def test_has_auth_header(self):
        req = _build_request("https://api.example.com", "sk-secret-123", b"{}")
        assert req.headers["Authorization"] == "Bearer sk-secret-123"

    def test_has_content_type(self):
        req = _build_request("https://api.example.com", "key", b"{}")
        # urllib.Request normalises header names to title case
        assert req.get_header("Content-type") == "application/json"

    def test_is_post(self):
        req = _build_request("https://api.example.com", "key", b"{}")
        assert req.method == "POST"

    def test_data_preserved(self):
        payload = json.dumps({"model": "test-model"}).encode("utf-8")
        req = _build_request("https://api.example.com", "key", payload)
        assert req.data == payload


# ---------------------------------------------------------------------------
# _do_request tests
# ---------------------------------------------------------------------------

class TestDoRequest:
    """Tests for _do_request() — low-level HTTP + JSON parsing."""

    def test_successful_response(self):
        fake_resp = io.BytesIO(json.dumps({
            "choices": [{"message": {"content": "Hello!"}}],
            "model": "gpt-4",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }).encode("utf-8"))

        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            result = _do_request(mock.MagicMock())
            assert result["choices"][0]["message"]["content"] == "Hello!"
            assert result["model"] == "gpt-4"

    def test_http_error_raises_runtime_error(self):
        http_error = urllib.error.HTTPError(
            "http://example.com", 401,
            "Unauthorized",
            mock.MagicMock(),
            io.BytesIO(json.dumps({"error": {"message": "Invalid API key"}}).encode("utf-8")),
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(RuntimeError, match="Invalid API key"):
                _do_request(mock.MagicMock())

    def test_http_error_no_body(self):
        http_error = urllib.error.HTTPError(
            "http://example.com", 500,
            "Server Error",
            mock.MagicMock(),
            io.BytesIO(b""),
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(RuntimeError, match="Server Error"):
                _do_request(mock.MagicMock())

    def test_url_error_raises_runtime_error(self):
        url_error = urllib.error.URLError("Connection refused")
        with mock.patch("urllib.request.urlopen", side_effect=url_error):
            with pytest.raises(RuntimeError, match="Connection refused"):
                _do_request(mock.MagicMock())

    def test_malformed_json_raises_runtime_error(self):
        fake_resp = io.BytesIO(b"not json at all")
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            with pytest.raises(RuntimeError, match="invalid JSON"):
                _do_request(mock.MagicMock())


# ---------------------------------------------------------------------------
# chat_completion — main API tests
# ---------------------------------------------------------------------------

def _make_llm_response(content="Hello!", model="deepseek-chat", prompt_tokens=10, completion_tokens=5):
    """Helper: build a fake LLM API response as a BytesIO."""
    return io.BytesIO(json.dumps({
        "id": "cmpl-xxx",
        "object": "chat.completion",
        "created": 1700000000,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }).encode("utf-8"))


class TestChatCompletion:
    """Tests for chat_completion() — the high-level API."""

    def test_basic_success(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        fake_resp = _make_llm_response(
            content="This is a test response",
            model="deepseek-chat",
            prompt_tokens=50,
            completion_tokens=20,
        )
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            result = chat_completion("system prompt", "user message")

        assert result["content"] == "This is a test response"
        assert result["model"] == "deepseek-chat"
        assert result["usage"]["prompt_tokens"] == 50
        assert result["usage"]["total_tokens"] == 70

    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="No LLM API key"):
            chat_completion("sys", "user")

    def test_null_content_handled(self, monkeypatch):
        """Some APIs return null content for refusal."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        fake_resp = io.BytesIO(json.dumps({
            "choices": [{"message": {"content": None}, "finish_reason": "content_filter"}],
            "usage": {},
        }).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            result = chat_completion("sys", "user")
        assert "refused" in result["content"]
        assert "content_filter" in result["content"]

    def test_empty_choices_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        fake_resp = io.BytesIO(json.dumps({
            "choices": [],
            "usage": {},
        }).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            with pytest.raises(RuntimeError, match="Unexpected API response"):
                chat_completion("sys", "user", retries=1)

    def test_missing_choices_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        fake_resp = io.BytesIO(json.dumps({
            "error": "not found",
        }).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            with pytest.raises(RuntimeError, match="Unexpected API response"):
                chat_completion("sys", "user", retries=1)

    def test_retry_on_http_error(self, monkeypatch):
        """Should retry on transient HTTP error, then succeed."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")

        # First call: HTTP 503 error, second call: success
        http_error = urllib.error.HTTPError(
            "http://example.com", 503,
            "Service Unavailable",
            mock.MagicMock(),
            io.BytesIO(b""),
        )
        fake_resp = _make_llm_response(content="Success after retry")

        mock_urlopen = mock.MagicMock()
        mock_urlopen.side_effect = [http_error, fake_resp]
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", retries=3)
        assert result["content"] == "Success after retry"
        assert mock_urlopen.call_count == 2

    def test_all_retries_exhausted(self, monkeypatch):
        """Should raise after all retries fail."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")

        http_error = urllib.error.HTTPError(
            "http://example.com", 503,
            "Always Down",
            mock.MagicMock(),
            io.BytesIO(b""),
        )
        mock_urlopen = mock.MagicMock(side_effect=http_error)
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(RuntimeError, match="Always Down"):
                chat_completion("sys", "user", retries=2)
        assert mock_urlopen.call_count == 2

    def test_custom_temperature_and_tokens(self, monkeypatch):
        """Verify custom params are passed through."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")

        fake_resp = _make_llm_response(content="Custom params")
        captured_body = []

        def capturing_urlopen(req, **kwargs):
            captured_body.append(json.loads(req.data))
            return fake_resp

        with mock.patch("urllib.request.urlopen", capturing_urlopen):
            result = chat_completion("sys", "user", temperature=0.9, max_tokens=1000)

        assert result["content"] == "Custom params"
        assert captured_body[0]["temperature"] == 0.9
        assert captured_body[0]["max_tokens"] == 1000

    def test_timeout_passed_to_urlopen(self, monkeypatch):
        """Verify the timeout parameter is forwarded."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        fake_resp = _make_llm_response(content="Timed out version")

        mock_urlopen = mock.MagicMock(return_value=fake_resp)
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", timeout=120)

        # The timeout should be passed as a keyword arg to urlopen
        call_kwargs = mock_urlopen.call_args[1]
        assert call_kwargs.get("timeout") == 120

    def test_uses_correct_endpoint(self, monkeypatch):
        """Verify the request URL includes the correct path."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://my-custom.com")
        monkeypatch.setenv("LLM_MODEL", "gpt-4")

        # Return the model name from the response unchanged
        fake_resp = _make_llm_response(content="Custom endpoint", model="gpt-4")
        mock_urlopen = mock.MagicMock(return_value=fake_resp)
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user")
            assert result["model"] == "gpt-4"

        url = mock_urlopen.call_args[0][0].full_url
        assert url == "https://my-custom.com/v1/chat/completions"

    def test_large_prompt_truncation_not_an_issue(self, monkeypatch):
        """Large prompts should still work (no artificial limit in client)."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        large_system = "A" * 100_000
        large_user = "B" * 100_000

        fake_resp = _make_llm_response(content="Large prompt response", prompt_tokens=50000)
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            result = chat_completion(large_system, large_user, max_tokens=100)
        assert result["content"] == "Large prompt response"

    def test_backoff_doubles(self, monkeypatch):
        """Retry backoff should be 1, 2, 4 seconds for retries=3."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        http_error = urllib.error.HTTPError(
            "http://example.com", 429,
            "Rate Limited",
            mock.MagicMock(),
            io.BytesIO(b""),
        )
        fake_resp = _make_llm_response(content="Finally ok")

        mock_sleep = mock.MagicMock()
        mock_urlopen = mock.MagicMock(side_effect=[http_error, http_error, fake_resp])

        with mock.patch("urllib.request.urlopen", mock_urlopen), \
             mock.patch("time.sleep", mock_sleep):
            result = chat_completion("sys", "user", retries=3)

        assert result["content"] == "Finally ok"
        # sleep called 2 times with backoff: 1.0, 2.0
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args[0] == 1.0
        assert mock_sleep.call_args_list[1].args[0] == 2.0


# ---------------------------------------------------------------------------
# Logging / edge cases
# ---------------------------------------------------------------------------

def test_logging_during_llm_call(caplog):
    """Verify informative log messages during LLM calls."""
    import logging
    caplog.set_level(logging.INFO)
    caplog.clear()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("LLM_API_KEY", "sk-test")

    fake_resp = _make_llm_response(content="Logged response")
    with mock.patch("urllib.request.urlopen", return_value=fake_resp), monkeypatch.context():
        chat_completion("Hello system", "Hello user")

    logs = [r for r in caplog.records if r.name == "llm.client"]
    request_logs = [r for r in logs if "LLM request" in r.getMessage()]
    assert len(request_logs) >= 1
    assert "attempt 1/3" in request_logs[0].getMessage()
