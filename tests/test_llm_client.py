
# @tests src/yuleosh/llm/client.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src
from yuleosh.llm.client import (
    chat_completion,
    resolve_config,
    TASK_ROUTES,
    AGENT_MODEL_ROUTES,
    SMALL_MODELS,
    VALID_PROVIDERS,
    PROVIDER_DEFAULT_MODELS,
    PROVIDER_MODEL_MAP,
    TASK_RISK_LEVELS,
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


class TestResolveConfigBranches:
    """Branch-level tests for resolve_config() — P1-3a."""

    def _resolve(self, task_type=None, env=None):
        with mock.patch.dict(os.environ, env or {}, clear=True):
            return resolve_config("prompt", None, task_type, None)

    # ── YULEOSH_LLM_PROVIDER env override ──────────────────────────

    @pytest.mark.parametrize("provider", list(PROVIDER_DEFAULT_MODELS))
    def test_provider_env_uses_default_model(self, provider):
        cfg = self._resolve(env={"YULEOSH_LLM_PROVIDER": provider})
        assert cfg.provider == provider
        assert cfg.model == PROVIDER_DEFAULT_MODELS[provider]

    def test_provider_env_invalid_raises(self):
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "bogus"}, clear=True):
            with pytest.raises(ValueError, match="YULEOSH_LLM_PROVIDER"):
                resolve_config("hi", None, None, None)

    def test_provider_env_case_insensitive(self):
        cfg = self._resolve(env={"YULEOSH_LLM_PROVIDER": "  Anthropic  "})
        assert cfg.provider == "anthropic"
        assert cfg.model == PROVIDER_DEFAULT_MODELS["anthropic"]

    def test_provider_env_beats_task_routes(self):
        cfg = self._resolve(
            task_type="misra_review",
            env={"YULEOSH_LLM_PROVIDER": "openai"},
        )
        assert cfg.provider == "openai"
        assert cfg.model == PROVIDER_DEFAULT_MODELS["openai"]

    # ── LLM_MODEL env override ─────────────────────────────────────

    def test_model_env_overrides_default(self):
        cfg = self._resolve(env={"LLM_MODEL": "gpt-4o"})
        assert cfg.model == "gpt-4o"
        assert cfg.provider == "openai"

    def test_model_env_with_provider_env(self):
        cfg = self._resolve(
            env={"LLM_MODEL": "claude-4-haiku", "YULEOSH_LLM_PROVIDER": "anthropic"},
        )
        assert cfg.model == "claude-4-haiku"
        assert cfg.provider == "anthropic"

    def test_model_env_unknown_keeps_deepseek_provider(self):
        cfg = self._resolve(env={"LLM_MODEL": "unknown-model-xyz"})
        assert cfg.model == "unknown-model-xyz"
        assert cfg.provider == "deepseek"

    # ── Agent label routing (C3) ────────────────────────────────────

    @pytest.mark.parametrize("agent", list(AGENT_MODEL_ROUTES))
    def test_agent_label_routing(self, agent):
        route = AGENT_MODEL_ROUTES[agent]
        cfg = self._resolve(task_type=agent)
        assert cfg.task_type == route["task_type"]
        assert cfg.provider == route["provider"]
        assert cfg.model == route["model"]

    def test_agent_label_qemu_simple_summary(self):
        cfg = self._resolve(task_type="QEMU")
        assert cfg.task_type == "simple_summary"
        assert cfg.rag_enabled is False
        assert cfg.memory_enabled is False

    # ── C3 hard rule: L3/L4 anti-hallucination ──────────────────────

    @pytest.mark.parametrize("small_model", list(SMALL_MODELS))
    def test_l3_l4_blocks_small_model(self, small_model):
        for task_type, risk in TASK_RISK_LEVELS.items():
            if risk not in ("L3", "L4"):
                continue
            cfg = self._resolve(
                task_type=task_type,
                env={"LLM_MODEL": small_model},
            )
            assert cfg.model != small_model, (
                f"L3/L4 task {task_type} must not use small model {small_model}"
            )

    def test_l3_l4_not_enforced_without_explicit_task_type(self):
        cfg = self._resolve(
            task_type=None,
            env={"LLM_MODEL": "deepseek-chat"},
        )
        assert cfg.model == "deepseek-chat"

    def test_l1_l2_allows_small_model(self):
        cfg = self._resolve(
            task_type="test_generation",
            env={"LLM_MODEL": "deepseek-chat"},
        )
        assert cfg.model == "deepseek-chat"

    # ── simple_summary disables RAG and memory ─────────────────────

    def test_simple_summary_no_rag_no_memory(self):
        cfg = self._resolve(task_type="simple_summary")
        assert cfg.rag_enabled is False
        assert cfg.memory_enabled is False
        assert cfg.rag_sources == []

    def test_code_generation_enables_rag_and_memory(self):
        cfg = self._resolve(task_type="code_generation")
        assert cfg.rag_enabled is True
        assert cfg.memory_enabled is True
        assert len(cfg.rag_sources) > 0

    # ── Unknown task_type fallback ──────────────────────────────────

    def test_unknown_task_type_falls_back(self):
        cfg = self._resolve(task_type="nonexistent_task")
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"

    # ── max_tokens cap ──────────────────────────────────────────────

    def test_max_tokens_capped_at_4096(self):
        cfg = self._resolve(task_type="test_generation")
        assert cfg.max_tokens <= 4096

    # ── Valid providers constant ────────────────────────────────────

    def test_valid_providers_tuple(self):
        assert isinstance(VALID_PROVIDERS, tuple)
        assert "mock" in VALID_PROVIDERS
        assert len(VALID_PROVIDERS) >= 4

    # ── Reproducibility fields (H1-1 + Q4) ─────────────────────────

    def test_codegen_seed_pinned(self):
        # Q4: codegen 必须确定性 —— 默认（code_generation）任务固定 seed=42。
        cfg = self._resolve()
        assert cfg.seed == 42
        assert cfg.temperature == 0.0

    def test_non_codegen_seed_none(self):
        cfg = self._resolve(task_type="test_generation")
        assert cfg.seed is None
        assert cfg.temperature == 0.3

    def test_frequency_penalty_default_zero(self):
        cfg = self._resolve()
        assert cfg.frequency_penalty == 0.0

    def test_presence_penalty_default_zero(self):
        cfg = self._resolve()
        assert cfg.presence_penalty == 0.0

    def test_seed_explicit_passthrough(self):
        cfg = LLMConfig(model="deepseek-v4", provider="deepseek", seed=42)
        assert cfg.seed == 42

    def test_penalty_explicit_passthrough(self):
        cfg = LLMConfig(
            model="deepseek-v4", provider="deepseek",
            frequency_penalty=0.5, presence_penalty=0.3,
        )
        assert cfg.frequency_penalty == 0.5
        assert cfg.presence_penalty == 0.3


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
