# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Deep tests for llm/client.py — chat_completion edge cases (v3.4.0).

Target: 80%+ branch coverage of chat_completion.
Covers: retry exhaustion, retry-then-success, null content, missing/empty
choices, custom timeout, model/usage passthrough, backoff sleep.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

import pytest

from yuleosh.llm.client import chat_completion


def _fake_http(response_body: dict, *, side_effect=None):
    """Build a urlopen context mock returning *response_body* JSON."""
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(response_body).encode()
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_resp
    fake_ctx.__exit__.return_value = False
    mock_urlopen = MagicMock()
    mock_urlopen.return_value = fake_ctx
    if side_effect is not None:
        mock_urlopen.side_effect = side_effect
    return mock_urlopen


@pytest.fixture(autouse=True)
def _api_key():
    with patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}, clear=False):
        yield


# ======================================================================
# chat_completion — error handling & retries
# ======================================================================

class TestChatCompletion:
    def test_no_api_key(self):
        """GIVEN no API key WHEN chat_completion THEN RuntimeError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError):
                chat_completion("sys", "user")

    def test_retry_exhaustion(self):
        """GIVEN persistent HTTPError WHEN chat_completion THEN RuntimeError."""
        http_err = __import__("urllib.error").error.HTTPError(
            url="http://x", code=500, msg="err", hdrs={}, fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with pytest.raises(RuntimeError):
                chat_completion("sys", "user", retries=2)

    def test_retry_then_success(self):
        """GIVEN one failure then success WHEN chat_completion THEN returns content."""
        http_err = __import__("urllib.error").error.HTTPError(
            url="http://x", code=429, msg="limited", hdrs={}, fp=None,
        )
        ok_ctx = _fake_http({
            "choices": [{"message": {"content": "recovered"}, "finish_reason": "stop"}],
            "model": "m", "usage": {},
        })
        mock_urlopen = MagicMock(side_effect=[http_err, ok_ctx.return_value])
        with patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", retries=2)
        assert result["content"] == "recovered"

    def test_null_content(self):
        """GIVEN content:null WHEN chat_completion THEN refuses with message."""
        mock_urlopen = _fake_http({
            "choices": [{"message": {"content": None}, "finish_reason": "length"}],
            "model": "m", "usage": {},
        })
        with patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", retries=1)
        assert "refused" in result["content"]
        assert "length" in result["content"]

    def test_no_choices(self):
        """GIVEN response without choices WHEN chat_completion THEN KeyError."""
        mock_urlopen = _fake_http({"model": "m", "usage": {}})
        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(KeyError):
                chat_completion("sys", "user", retries=1)

    def test_empty_choices(self):
        """GIVEN empty choices list WHEN chat_completion THEN IndexError."""
        mock_urlopen = _fake_http({"choices": [], "model": "m", "usage": {}})
        with patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(IndexError):
                chat_completion("sys", "user", retries=1)

    def test_custom_timeout(self):
        """GIVEN custom timeout WHEN chat_completion THEN passed to urlopen."""
        mock_urlopen = _fake_http({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "m", "usage": {},
        })
        with patch("urllib.request.urlopen", mock_urlopen):
            chat_completion("sys", "user", timeout=42, retries=1)
        # context manager mock → urlopen(request, timeout=42)
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 42

    def test_uses_model_from_response(self):
        """GIVEN model in response WHEN chat_completion THEN passthrough."""
        mock_urlopen = _fake_http({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "response-model-x", "usage": {},
        })
        with patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", retries=1)
        assert result["model"] == "response-model-x"

    def test_returns_usage(self):
        """GIVEN usage in response WHEN chat_completion THEN passthrough."""
        mock_urlopen = _fake_http({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "m", "usage": {"total_tokens": 7},
        })
        with patch("urllib.request.urlopen", mock_urlopen):
            result = chat_completion("sys", "user", retries=1)
        assert result["usage"]["total_tokens"] == 7

    def test_backoff_sleep(self):
        """GIVEN failure THEN success WHEN retries THEN exponential backoff sleep."""
        http_err = __import__("urllib.error").error.HTTPError(
            url="http://x", code=500, msg="err", hdrs={}, fp=None,
        )
        ok_ctx = _fake_http({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "m", "usage": {},
        })
        mock_urlopen = MagicMock(side_effect=[http_err, ok_ctx.return_value])
        with patch("urllib.request.urlopen", mock_urlopen), \
             patch("time.sleep") as m_sleep:
            chat_completion("sys", "user", retries=3)
        # attempt 1 → backoff 1.0s
        assert m_sleep.call_args[0][0] == 1.0

    def test_urllib_error_retry(self):
        """GIVEN URLError WHEN chat_completion THEN retries then raises."""
        import urllib.error
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError(reason="refused")):
            with pytest.raises(RuntimeError):
                chat_completion("sys", "user", retries=2)
