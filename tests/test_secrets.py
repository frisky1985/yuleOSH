# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Regression tests for the encrypted provider-secret vault (SEC-PK)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from yuleosh import secret_vault as vault
from yuleosh.store import Store


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the default Store at a temp DB and reset the singleton."""
    monkeypatch.setenv("YULEOSH_JWT_SECRET", "test-master-secret-do-not-use")
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    monkeypatch.setenv("YULEOSH_DB", str(tmp_path / ".yuleosh" / "store.db"))
    Store.reset()
    yield tmp_path
    Store.reset()


def test_encrypt_decrypt_roundtrip(tmp_db):
    ct = vault.encrypt_secret("sk-deepseek-12345")
    assert ct != "sk-deepseek-12345"
    assert vault.decrypt_secret(ct) == "sk-deepseek-12345"


def test_vault_available_depends_on_secret(monkeypatch):
    monkeypatch.delenv("YULEOSH_MASTER_KEY", raising=False)
    monkeypatch.delenv("YULEOSH_JWT_SECRET", raising=False)
    assert vault.vault_available() is False
    monkeypatch.setenv("YULEOSH_JWT_SECRET", "x")
    assert vault.vault_available() is True


def test_store_set_get_list_delete(tmp_db):
    rec = vault.set_provider_secret("deepseek", "DEEPSEEK_API_KEY", "sk-plaintext-secret")
    assert rec["provider"] == "deepseek"
    assert rec["key_name"] == "DEEPSEEK_API_KEY"
    assert "id" in rec

    # get returns decrypted plaintext
    assert vault.get_provider_secret("deepseek", "DEEPSEEK_API_KEY") == "sk-plaintext-secret"

    # list returns metadata ONLY (no value / no ciphertext leaked)
    listing = vault.list_provider_secrets()
    assert any(s["key_name"] == "DEEPSEEK_API_KEY" for s in listing)
    assert all("ciphertext" not in s for s in listing)

    # ciphertext stored (not plaintext) — verify at the DB layer
    stored = Store().get_provider_secret_ciphertext("deepseek", "DEEPSEEK_API_KEY")
    assert stored != "sk-plaintext-secret"

    assert vault.delete_provider_secret(rec["id"]) is True
    assert vault.get_provider_secret("deepseek", "DEEPSEEK_API_KEY") is None


def test_resolver_env_first_then_vault(tmp_db, monkeypatch):
    # vault has a value
    vault.set_provider_secret("deepseek", "DEEPSEEK_API_KEY", "vault-key")

    # env takes priority
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    assert vault.resolve_provider_api_key("deepseek") == "env-key"
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    # vault fallback when env empty
    assert vault.resolve_provider_api_key("deepseek") == "vault-key"


def test_resolver_returns_empty_when_unset(tmp_db, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert vault.resolve_provider_api_key("deepseek") == ""


# ── OpenAI-compatible endpoint resolver (Ollama / 自定义) ──────────────────


def test_openai_compat_whitelist_allows_endpoint_keys(tmp_db):
    # LLM_BASE_URL / LLM_MODEL 现在在白名单内，可入库。
    for kn in ("LLM_BASE_URL", "LLM_MODEL"):
        rec = vault.set_provider_secret("ollama", kn, f"val-{kn}")
        assert rec["key_name"] == kn
        assert vault.get_provider_secret("ollama", kn) == f"val-{kn}"


def test_openai_compat_empty_when_unset(tmp_db, monkeypatch):
    for e in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    assert vault.resolve_openai_compat() == {}


def test_openai_compat_env_first(tmp_db, monkeypatch):
    # 环境变量优先于保险库。
    monkeypatch.setenv("LLM_BASE_URL", "http://env:11434")
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    assert vault.resolve_openai_compat().get("base_url") == "http://env:11434"
    assert vault.resolve_openai_compat().get("api_key") == "env-key"
    # 保险库里的同名配置不被优先采用
    vault.set_provider_secret("ollama", "LLM_BASE_URL", "http://vault:11434")
    assert vault.resolve_openai_compat().get("base_url") == "http://env:11434"


def test_openai_compat_vault_fallback(tmp_db, monkeypatch):
    # 环境变量清空时，跨 ollama/custom 命名空间兜底。
    for e in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(e, raising=False)
    base_rec = vault.set_provider_secret("ollama", "LLM_BASE_URL", "http://localhost:11434")
    model_rec = vault.set_provider_secret("ollama", "LLM_MODEL", "deepseek-r1:7b")
    key_rec = vault.set_provider_secret("ollama", "LLM_API_KEY", "ollama")
    compat = vault.resolve_openai_compat()
    assert compat.get("base_url") == "http://localhost:11434"
    assert compat.get("model") == "deepseek-r1:7b"
    assert compat.get("api_key") == "ollama"
    # 仅存的字段才返回（删除 LLM_MODEL 后不应再有 model 键）
    assert vault.delete_provider_secret(model_rec["id"]) is True
    compat2 = vault.resolve_openai_compat()
    assert "model" not in compat2
    assert compat2.get("base_url") == "http://localhost:11434"
    # 清理其余
    vault.delete_provider_secret(base_rec["id"])
    vault.delete_provider_secret(key_rec["id"])
