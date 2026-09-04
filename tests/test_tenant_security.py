# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Regression tests for tenant_security credential storage (SEC-PK migration).

Verifies that API-key credentials are routed into the encrypted vault (never
plaintext) while legacy credentials.json remains a read-only fallback and
non-secret OLLAMA_HOST is handled via the legacy file.
"""
from __future__ import annotations

import pytest

from yuleosh.engine import tenant_security as ts


@pytest.fixture
def tmp_tenant(tmp_path):
    d = tmp_path / "slug"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """防止 shell 中真实 API Key 环境变量（env-first 解析）污染断言。"""
    for var in (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "YULEOSH_EMBED_API_KEY",
        "OLLAMA_HOST",
        "LLM_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    # 还原 Store 单例，避免跨测试污染（api_smoke 等同进程模块）。
    import yuleosh.store as store_mod

    store_mod.Store.reset()


def test_write_credentials_encrypts_api_keys_into_vault(tmp_tenant, monkeypatch):
    """API keys go to the encrypted vault; no plaintext credentials.json written."""
    monkeypatch.setenv("YULEOSH_JWT_SECRET", "test-secret-for-vault")
    # Fresh in-memory store so the vault is empty at start.
    import yuleosh.store as store_mod

    store_mod.Store.reset()
    monkeypatch.setenv("YULEOSH_DB", str(tmp_tenant / "vault.db"))

    ts.write_credentials(
        tmp_tenant,
        {
            "DEEPSEEK_API_KEY": "sk-deepseek-plaintext-123",
            "OLLAMA_HOST": "http://localhost:11434",
        },
    )

    # The key is resolvable from the vault (env-first, vault-second).
    from yuleosh import secret_vault as vault

    assert vault.resolve_provider_api_key("deepseek") == "sk-deepseek-plaintext-123"

    # load_credentials returns it (env may be empty in test -> vault fallback).
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    creds = ts.load_credentials(tmp_tenant)
    assert creds["DEEPSEEK_API_KEY"] == "sk-deepseek-plaintext-123"
    assert creds["OLLAMA_HOST"] == "http://localhost:11434"

    # No plaintext credentials.json should exist for the API key path
    # (OLLAMA_HOST non-secret may still write a legacy file; the API key must not).
    legacy = tmp_tenant / "config" / "credentials.json"
    if legacy.exists():
        data = __import__("json").loads(legacy.read_text(encoding="utf-8"))
        assert "DEEPSEEK_API_KEY" not in data, "API key must not be written in plaintext"


def test_load_credentials_legacy_fallback(tmp_tenant):
    """Existing plaintext credentials.json is still readable (backward compat)."""
    (tmp_tenant / "config").mkdir(parents=True, exist_ok=True)
    (tmp_tenant / "config" / "credentials.json").write_text(
        __import__("json").dumps(
            {"OPENAI_API_KEY": "sk-legacy-456", "OLLAMA_HOST": "http://host:11434"}
        ),
        encoding="utf-8",
    )
    creds = ts.load_credentials(tmp_tenant)
    assert creds["OPENAI_API_KEY"] == "sk-legacy-456"
    assert creds["OLLAMA_HOST"] == "http://host:11434"


def test_load_credentials_env_takes_priority(tmp_tenant, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-wins")
    creds = ts.load_credentials(tmp_tenant)
    assert creds["ANTHROPIC_API_KEY"] == "sk-env-wins"


def test_write_credentials_whitelist_filter(tmp_tenant, monkeypatch):
    monkeypatch.setenv("YULEOSH_JWT_SECRET", "test-secret-for-vault")
    import yuleosh.store as store_mod

    store_mod.Store.reset()
    monkeypatch.setenv("YULEOSH_DB", str(tmp_tenant / "vault.db"))

    # An out-of-whitelist key must be dropped silently.
    ts.write_credentials(tmp_tenant, {"EVIL_KEY": "should-be-dropped", "DEEPSEEK_API_KEY": "ok"})
    from yuleosh import secret_vault as vault

    assert vault.resolve_provider_api_key("deepseek") == "ok"
    creds = ts.load_credentials(tmp_tenant)
    assert "EVIL_KEY" not in creds
