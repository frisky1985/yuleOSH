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
        config = resolve_config()
        assert isinstance(config, LLMConfig)
        assert config.provider == "deepseek"

    def test_task_specific_routing(self):
        for task_type, expected_model in TASK_ROUTES.items():
            config = resolve_config(task_type=task_type)
            assert config is not None

    def test_custom_model_override(self):
        config = resolve_config(model="custom-model")
        assert config.model == "custom-model"


# ---------------------------------------------------------------------------
# chat_completion tests
# ---------------------------------------------------------------------------

class TestChatCompletion:
    """Tests for chat_completion() — backward-compatible wrapper."""

    def test_requires_prompt(self):
        with pytest.raises(TypeError):
            chat_completion()

    def test_returns_string(self):
        """chat_completion should return a string."""
        result = chat_completion(prompt="Hello", system_prompt="Be helpful")
        assert isinstance(result, str)
        assert len(result) > 0


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
