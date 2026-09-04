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
