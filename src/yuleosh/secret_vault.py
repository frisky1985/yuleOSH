# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Encrypted provider-secret vault (SEC-PK).

Stores LLM provider API keys (and other sensitive credentials) **encrypted at
rest** using Fernet (AES-128-CBC + HMAC-SHA256, symmetric).

Security model
--------------
- Master key: ``YULEOSH_MASTER_KEY`` if set, else derived from
  ``YULEOSH_JWT_SECRET`` via SHA-256. NEVER stored; only held in process memory.
- Plaintext is only ever held transiently (in memory) at set/resolve time.
  Only ciphertext is persisted (``provider_secrets`` table).
- ``list_provider_secrets`` / ``GET /api/v1/secrets`` return metadata ONLY
  (provider, key_name, timestamps) — never the plaintext or ciphertext.
- Env vars take priority over the vault (backward-compatible with ``.env``
  deployments); the vault is a fallback so secrets need not live in the env.

Rotating the master secret renders all stored ciphertext undecryptable — by
design (re-set the keys after rotation).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet

log = logging.getLogger("yuleosh.secret_vault")

# Provider -> ordered list of env-var names that may carry its API key.
# Mirrors llm/provider_fallback.PROVIDER_KEY_ENV.
PROVIDER_KEY_ENV: dict[str, tuple[str, ...]] = {
    "deepseek": ("DEEPSEEK_API_KEY", "LLM_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY", "LLM_API_KEY"),
    "embed": ("YULEOSH_EMBED_API_KEY",),
}

# Key names accepted by the vault API (whitelist, prevents storing arbitrary
# sensitive env vars).
#
# OpenAI-compatible endpoints (本机 Ollama / 自定义模型) 需要三类配置：
#   - LLM_BASE_URL  OpenAI 兼容端点地址（如 http://localhost:11434）
#   - LLM_MODEL     模型 tag（如 deepseek-r1:7b / qwen2.5-coder:14b）
#   - LLM_API_KEY   自建端点可填任意非空串（Ollama 通常留空或 "ollama"）
# 三者与 LLM_API_KEY 一并开放入库，使 UI 配置的 Ollama/自定义端点真正被
# openai provider 链路消费（见 resolve_openai_compat）。
ALLOWED_KEY_NAMES = {
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "YULEOSH_EMBED_API_KEY",
}


def _master_key_raw() -> bytes:
    """Return the raw master key bytes, or b'' if no secret is configured."""
    raw = os.environ.get("YULEOSH_MASTER_KEY") or os.environ.get("YULEOSH_JWT_SECRET")
    if not raw:
        return b""
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _fernet() -> Optional[Fernet]:
    mk = _master_key_raw()
    if not mk:
        return None
    return Fernet(base64.urlsafe_b64encode(mk))


def vault_available() -> bool:
    """True if a master key is configured and the vault can encrypt/decrypt."""
    return _master_key_raw() != b""


def encrypt_secret(plaintext: str) -> str:
    """Encrypt plaintext -> Fernet token (ascii). Raises if vault unavailable."""
    f = _fernet()
    if f is None:
        raise RuntimeError(
            "Secret vault unavailable: set YULEOSH_JWT_SECRET or YULEOSH_MASTER_KEY"
        )
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a Fernet token -> plaintext. Raises if vault unavailable."""
    f = _fernet()
    if f is None:
        raise RuntimeError("Secret vault unavailable")
    return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")


# ── Store-backed vault operations ───────────────────────────────────────
# Store is imported lazily to avoid import cycles (providers import this
# module; the Store imports nothing from llm).


def set_provider_secret(provider: str, key_name: str, value: str) -> dict:
    """Encrypt ``value`` and upsert into the vault. Returns metadata (no value)."""
    if key_name not in ALLOWED_KEY_NAMES:
        raise ValueError(f"key_name {key_name!r} is not allowed")
    ciphertext = encrypt_secret(value)
    from yuleosh.store import Store

    store = Store()
    return store.set_provider_secret(provider, key_name, ciphertext)


def get_provider_secret(provider: str, key_name: str) -> Optional[str]:
    """Return decrypted secret, or None if absent/unavailable."""
    try:
        from yuleosh.store import Store

        store = Store()
        ct = store.get_provider_secret_ciphertext(provider, key_name)
    except Exception as e:  # vault unavailable / db error -> treat as absent
        log.debug("get_provider_secret failed: %s", e)
        return None
    if not ct:
        return None
    try:
        return decrypt_secret(ct)
    except Exception as e:
        log.warning("Failed to decrypt provider secret %s/%s: %s", provider, key_name, e)
        return None


def list_provider_secrets() -> list[dict]:
    from yuleosh.store import Store

    store = Store()
    return store.list_provider_secrets()


def delete_provider_secret(secret_id: int) -> bool:
    from yuleosh.store import Store

    store = Store()
    return store.delete_provider_secret(secret_id)


def touch_provider_secret_used(provider: str, key_name: str) -> None:
    try:
        from yuleosh.store import Store

        Store().touch_provider_secret_used(provider, key_name)
    except Exception as e:  # best-effort
        log.debug("touch_provider_secret_used failed: %s", e)


def resolve_api_key(*env_names: str, provider: Optional[str] = None) -> str:
    """Resolve an API key: env vars first, vault fallback. Returns '' if unset.

    ``env_names`` are the candidate environment variable names (checked in
    order). When ``provider`` is given and env yields nothing, the vault is
    consulted for each env name under that provider.
    """
    for n in env_names:
        v = os.environ.get(n)
        if v:
            return v
    if provider:
        for n in env_names:
            secret = get_provider_secret(provider, n)
            if secret:
                touch_provider_secret_used(provider, n)
                return secret
    return ""


def resolve_provider_api_key(provider: str) -> str:
    """Convenience: resolve a provider's API key via its known env names."""
    return resolve_api_key(*PROVIDER_KEY_ENV.get(provider, ()), provider=provider)


def _resolve_one(env_names: tuple[str, ...], vault_providers: tuple[str, ...]) -> str:
    """Resolve a single logical value: env vars first, then vault across providers.

    Returns the first non-empty hit (env checked before vault; within each
    layer the given order is respected). Returns '' if nothing found.
    """
    for n in env_names:
        v = os.environ.get(n)
        if v:
            return v
    for prov in vault_providers:
        for n in env_names:
            secret = get_provider_secret(prov, n)
            if secret:
                touch_provider_secret_used(prov, n)
                return secret
    return ""


def resolve_openai_compat(
    *,
    vault_providers: tuple[str, ...] = ("openai", "ollama", "custom"),
) -> dict[str, str]:
    """Resolve an OpenAI-compatible endpoint config (本机 Ollama / 自定义模型).

    Ollama 与自定义模型在架构上就是 ``openai`` provider 的
    ``LLM_BASE_URL`` / ``LLM_MODEL`` / ``LLM_API_KEY`` 三件套，复用现有
    OpenAI 传输层，无需新增 provider 类。本函数统一按
    **环境变量优先、保险库兜底** 的取值链解析三者，便于 UI 在
    ``provider=ollama`` / ``custom`` 下写入的配置被 LLM 链路真正消费。

    Returns a dict containing only the keys found (``base_url`` / ``api_key``
    / ``model``); callers fall back to defaults for the rest.
    """
    out: dict[str, str] = {}
    base_url = _resolve_one(("LLM_BASE_URL",), vault_providers)
    if base_url:
        out["base_url"] = base_url
    api_key = _resolve_one(("OPENAI_API_KEY", "LLM_API_KEY"), vault_providers)
    if api_key:
        out["api_key"] = api_key
    model = _resolve_one(("LLM_MODEL",), vault_providers)
    if model:
        out["model"] = model
    return out
