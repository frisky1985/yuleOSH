"""Smoke tests for yuleosh.llm.client — LLM client functions (v3.4.0 API)."""

# @tests src/yuleosh/llm/client.py
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


class TestLlmClient:
    def test_import(self):
        import yuleosh.llm.client as c
        assert hasattr(c, "chat_completion")
        assert hasattr(c, "resolve_config")
        assert hasattr(c, "LLMClient")

    def test_resolve_config_returns_config(self):
        from yuleosh.llm.client import resolve_config
        config = resolve_config(prompt="hi", system_prompt=None, task_type=None, config=None)
        assert config is not None
        assert config.model

    def test_chat_completion_requires_key(self):
        """Without an API key, chat_completion raises RuntimeError."""
        from yuleosh.llm.client import chat_completion
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {"YULEOSH_JWT_SECRET": "x"}, clear=False):
                with pytest.raises(RuntimeError):
                    chat_completion("sys", "user")

    def test_chat_completion_mocked_request(self):
        """chat_completion returns dict with content when HTTP is mocked."""
        from yuleosh.llm.client import chat_completion
        import json
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 5},
        }).encode()
        fake_ctx = MagicMock()
        fake_ctx.__enter__.return_value = fake_resp
        fake_ctx.__exit__.return_value = False
        with patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}, clear=False):
            with patch("urllib.request.urlopen", return_value=fake_ctx):
                result = chat_completion("sys", "user", retries=1)
        assert result["content"] == "hi"
        assert result["model"] == "deepseek-chat"

    def test_resolve_env(self):
        from yuleosh.llm.client import resolve_config
        cfg = resolve_config(prompt="hi", system_prompt=None, task_type="code_generation", config=None)
        assert isinstance(cfg.provider, str)
        assert isinstance(cfg.model, str) and len(cfg.model) > 0
