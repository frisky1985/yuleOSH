# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0
"""llm/health.py — LLM provider 健康诊断（项⑪ 真实 LLM 接入的可观测层）。

外部 LLM 在某些部署里 key 失效（余额 402 / 配置错 / key 误填），但系统仍
能跑（mock 兜底）。本模块把"哪些 provider 可用"变成可查询、可展示的状态，
且不泄露任何 key 明文：只回显 `sk-ab…cd12` 形式的掩码。

- ``diagnose_llm_providers(live=False)``：仅做配置就绪检查（key 是否设置）。
- ``diagnose_llm_providers(live=True)``：额外对每个已配置 provider 发一次极
  短探测（max_tokens=4，超时 ~8s），把 402/401/网络等真实错误 sanitize 后
  回显，便于用户自助充值 / 轮换 key。
"""

from __future__ import annotations

import asyncio
import os
import re

from yuleosh.llm.client import _get_provider
from yuleosh.llm.providers.base import LLMConfig

# 每个 provider 的 key 环境变量（按优先级），以及探针用的默认模型。
_PROVIDER_ENV: dict[str, list[str]] = {
    "deepseek": ["DEEPSEEK_API_KEY", "LLM_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
}
_PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}
_PROBED_PROVIDERS = ["deepseek", "openai", "anthropic"]


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}\u2026{key[-4:]}"


def _key_status(provider: str) -> tuple[bool, str | None]:
    for env in _PROVIDER_ENV[provider]:
        val = os.environ.get(env, "")
        if val:
            return True, _mask_key(val)
    return False, None


def _sanitize(msg: str, provider: str) -> str:
    """Strip any key material / bearer token from an error message."""
    for env in _PROVIDER_ENV.get(provider, []):
        val = os.environ.get(env, "")
        if val and val in msg:
            msg = msg.replace(val, "***")
    msg = re.sub(r"sk-[A-Za-z0-9]{6,}", "sk-***", msg)
    msg = re.sub(r"Bearer [A-Za-z0-9._-]+", "Bearer ***", msg)
    msg = re.sub(r"x-api-key[=: ]+[A-Za-z0-9._-]+", "x-api-key=***", msg)
    return msg[:300]


async def _live_check(provider: str, model: str) -> tuple[str, str | None]:
    try:
        p = _get_provider(provider)
        cfg = LLMConfig(
            provider=provider,
            model=model,
            max_tokens=4,
            temperature=0.0,
            timeout_s=6,
            max_retries=0,
            rag_enabled=False,
            memory_enabled=False,
            fallback_enabled=False,
        )
        await asyncio.wait_for(
            p.chat([{"role": "user", "content": "ping"}], config=cfg),
            timeout=9.0,
        )
        return "ok", None
    except asyncio.TimeoutError:
        return "error", "探测超时（>9s），网络不可达或被代理拦截"
    except Exception as e:  # noqa: BLE001 — 诊断需要捕获一切并 sanitize 回显
        return "error", _sanitize(str(e), provider)


def _active_provider() -> tuple[str, str]:
    provider = os.environ.get("YULEOSH_LLM_PROVIDER", "") or "deepseek"
    if provider not in _PROVIDER_DEFAULT_MODEL:
        provider = "deepseek"
    return provider, _PROVIDER_DEFAULT_MODEL[provider]


async def diagnose_llm_providers(live: bool = False) -> dict:
    """Return a structured, key-safe health report for all LLM providers."""
    active_p, active_m = _active_provider()
    providers: list[dict] = []

    for provider in _PROBED_PROVIDERS:
        model = _PROVIDER_DEFAULT_MODEL[provider]
        key_set, preview = _key_status(provider)
        entry: dict = {
            "provider": provider,
            "model": model,
            "key_set": key_set,
            "key_preview": preview,
            "status": "unconfigured",
            "detail": None,
        }
        if not key_set:
            entry["detail"] = "未配置 API Key（请设置对应环境变量）"
        elif not live:
            entry["status"] = "configured"
            entry["detail"] = "已配置 Key，未做在线探测"
        else:
            status, detail = await _live_check(provider, model)
            entry["status"] = status
            entry["detail"] = detail
        providers.append(entry)

    usable = [p for p in providers if p["status"] == "ok"]
    if usable:
        summary = f"{len(usable)} 个 provider 可用：" + "、".join(
            f"{p['provider']}({p['model']})" for p in usable
        )
    elif any(p["key_set"] for p in providers):
        summary = "已配置 Key 但在线探测均失败（余额/鉴权/网络）——请检查 key 或充值"
    else:
        summary = "未配置任何真实 LLM Key，系统将走 mock 兜底"

    return {
        "active_provider": active_p,
        "active_model": active_m,
        "live": live,
        "providers": providers,
        "summary": summary,
    }
