"""Smoke tests for yuleosh.llm.client — LLM client functions."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestLlmClient:
    def test_import(self):
        import yuleosh.llm.client as c
        assert hasattr(c, "chat_completion")
        assert hasattr(c, "_build_payload")

    def test_build_payload(self):
        from yuleosh.llm.client import _build_payload
        result = _build_payload("gpt-4", "hello", [])
        assert isinstance(result, bytes)

    def test_build_request(self):
        from yuleosh.llm.client import _build_request
        req = _build_request("https://api.openai.com/v1/chat/completions",
                              "sk-test", b"{}")
        assert req.get_method() == "POST"
        assert req.headers.get("Authorization") == "Bearer sk-test"

    def test_resolve_env(self):
        from yuleosh.llm.client import _resolve_env
        key, url, model = _resolve_env()
        assert isinstance(url, str)
        assert isinstance(key, str)
        assert isinstance(model, str) and len(model) > 0
