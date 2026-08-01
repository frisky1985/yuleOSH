# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Unit tests for src/llm/client.py — LLMClient adapter.

Tests the refactored LLMClient API with mocked provider.
Covers: config resolution, provider routing, chat_completion,
cost logging, and error handling.
"""

import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.llm.client import (
    chat_completion,
    resolve_config,
    TASK_ROUTES,
)
from yuleosh.llm.providers.base import LLMConfig, LLMResponse


# ---------------------------------------------------------------------------
# resolve_config tests
# ---------------------------------------------------------------------------

class TestResolveConfig:
    """Tests for resolve_config() — LLM config resolution."""

    def test_returns_default_config(self):
        config = resolve_config("hi", None, None, None)
        assert isinstance(config, LLMConfig)
        assert config.provider == "deepseek"

    def test_task_specific_routing(self):
        for task_type in TASK_ROUTES:
            config = resolve_config("hi", None, task_type, None)
            assert config is not None

    def test_custom_model_override(self):
        config = resolve_config("hi", None, None, LLMConfig(model="custom-model", provider="deepseek"))
        assert config.model == "custom-model"


# ---------------------------------------------------------------------------
# chat_completion tests
# ---------------------------------------------------------------------------

class TestChatCompletion:
    """Tests for chat_completion() — backward-compatible wrapper (v3.4.0)."""

    def test_requires_prompt(self):
        """chat_completion requires positional system/user prompts."""
        with pytest.raises(TypeError):
            chat_completion()

    def test_no_key_raises(self):
        """Without an API key, chat_completion raises RuntimeError."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError):
                chat_completion("Be helpful", "Hello")

    def test_returns_dict_with_mocked_http(self):
        """chat_completion returns a dict with content/model/usage."""
        import json as _json
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = _json.dumps({
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 3},
        }).encode()
        fake_ctx = mock.MagicMock()
        fake_ctx.__enter__.return_value = fake_resp
        fake_ctx.__exit__.return_value = False
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}, clear=False):
            with mock.patch("urllib.request.urlopen", return_value=fake_ctx):
                result = chat_completion("Be helpful", "Hello", retries=1)
        assert isinstance(result, dict)
        assert result["content"] == "Hello!"
        assert result["model"] == "deepseek-chat"


# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------

class TestImports:
    """Verify that key exports are accessible."""

    def test_llm_client_imports(self):
        from yuleosh.llm.client import LLMClient, resolve_config, chat_completion
        assert LLMClient is not None

    def test_providers_import(self):
        from yuleosh.llm.providers.base import LLMConfig, LLMResponse, AbstractProvider
        assert AbstractProvider is not None


# ---------------------------------------------------------------------------
# TASK_ROUTES integrity
# ---------------------------------------------------------------------------

class TestTaskRoutes:
    """Verify that TASK_ROUTES contains expected entries."""

    def test_has_code_generation(self):
        assert "code_generation" in TASK_ROUTES

    def test_has_misra_review(self):
        assert "misra_review" in TASK_ROUTES

    def test_routes_not_empty(self):
        assert len(TASK_ROUTES) > 0
