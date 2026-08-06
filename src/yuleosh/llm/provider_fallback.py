# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/provider_fallback.py — Provider-level fallback chain.

When ``LLMClient.call`` fails at the *transport* layer (connection error,
timeout, 5xx, rate limit, budget overrun), the call automatically degrades
to the next available provider instead of returning an error immediately.

This is COMPLEMENTARY to ``yuleosh.llm.fallback`` (the 5-level *output
validation* fallback: raw → schema → content → semantic → template →
abort). That module validates LLM output content; this module handles
provider availability. Do not mix the two.

Chain semantics::

    DEFAULT_FALLBACK_ORDER = ("deepseek", "anthropic", "openai", "mock")

    chain = [configured_provider] + [p for p in order if p != configured_provider]

The configured provider (via explicit ``LLMConfig.provider`` or the
``YULEOSH_LLM_PROVIDER`` env) is always tried first; the rest follow in
fixed order unless overridden by ``YULEOSH_LLM_FALLBACK_ORDER`` (comma
separated) or ``LLMConfig.fallback_order``.

Degradation rules:
    - Degrade on:  connection errors, timeouts, HTTP 5xx, HTTP 429
      (rate limit), budget overrun.
    - Do NOT degrade on: HTTP 4xx business errors (e.g. invalid API key —
      a fallback provider would fail the same way), or when the caller
      explicitly disables fallback (``fallback_enabled=False``).
    - Skeleton providers (``is_skeleton = True``, e.g. anthropic/openai
      reservation stubs) are skipped WITHOUT being called; providers with
      no API key configured are skipped; ``mock`` is always available and
      is the final safety net.

Every degradation is recorded to ``.osh/logs/provider_fallback_events.jsonl``
via ``CostLogger.log_fallback_event``.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from yuleosh.llm.cost import CostLogger
from yuleosh.llm.providers.base import AbstractProvider, LLMConfig, LLMResponse

log = logging.getLogger("llm.provider_fallback")

# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

VALID_PROVIDERS: tuple = ("deepseek", "anthropic", "openai", "mock")

DEFAULT_FALLBACK_ORDER: tuple = ("deepseek", "anthropic", "openai", "mock")

# Provider → env var(s) that indicate an API key is configured.
PROVIDER_KEY_ENVS: dict[str, tuple] = {
    "deepseek": ("DEEPSEEK_API_KEY", "LLM_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "mock": (),
}

# HTTP status codes that mean "retry a different provider".
_DEGRADE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})

# Messages that indicate a budget-related failure (degrade to cheaper).
_BUDGET_MARKERS = ("budget", "超预算", "预算")


# ═══════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FallbackEvent:
    """A single provider degradation event (for audit logging)."""

    from_provider: str
    to_provider: str
    reason: str  # connection_error | timeout | http_5xx | rate_limit | budget_exceeded | not_available | skeleton | no_key
    duration_s: float = 0.0
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Configuration resolution
# ═══════════════════════════════════════════════════════════════════════


def fallback_enabled(config: LLMConfig | None = None) -> bool:
    """Whether provider fallback is enabled.

    Priority: ``LLMConfig.fallback_enabled`` (explicit) > ``YULEOSH_LLM_FALLBACK_ENABLED`` env
    (default True). Env parsing accepts true/1/yes/on (case-insensitive) and
    false/0/no/off; anything else falls back to the default True.
    """
    if config is not None:
        return bool(config.fallback_enabled)

    raw = os.environ.get("YULEOSH_LLM_FALLBACK_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _parse_order(raw: str) -> list[str]:
    """Parse a comma-separated provider order, validating names."""
    order = [p.strip().lower() for p in raw.split(",") if p.strip()]
    for p in order:
        if p not in VALID_PROVIDERS:
            raise ValueError(
                f"YULEOSH_LLM_FALLBACK_ORDER 必须包含合法 provider 名 "
                f"{list(VALID_PROVIDERS)} 之一，当前值: '{p}'"
            )
    return order


def resolve_fallback_order(config: LLMConfig | None = None) -> list[str]:
    """Resolve the ordered fallback chain.

    The configured provider is always placed first; the remaining providers
    follow the user-supplied order (``LLMConfig.fallback_order``, else the
    ``YULEOSH_LLM_FALLBACK_ORDER`` env) or ``DEFAULT_FALLBACK_ORDER``.

    Raises:
        ValueError: if a user-supplied order contains an unknown provider.
    """
    # 1. Determine the primary (starting) provider.
    if config is not None and config.provider:
        primary = config.provider.strip().lower()
    else:
        primary = (os.environ.get("YULEOSH_LLM_PROVIDER") or "deepseek").strip().lower()

    # 2. Determine the follow-up order.
    user_order: list[str] | None = None
    if config is not None and config.fallback_order:
        user_order = [p.strip().lower() for p in config.fallback_order]
        for p in user_order:
            if p not in VALID_PROVIDERS:
                raise ValueError(
                    f"LLMConfig.fallback_order 必须包含合法 provider 名 "
                    f"{list(VALID_PROVIDERS)} 之一，当前值: '{p}'"
                )
    else:
        env_order = os.environ.get("YULEOSH_LLM_FALLBACK_ORDER")
        if env_order is not None and env_order.strip():
            user_order = _parse_order(env_order)

    follow_order = user_order or list(DEFAULT_FALLBACK_ORDER)

    # 3. Build the chain: primary first, then the rest without duplicates.
    # The configured provider is always the first attempt — even when it is
    # a custom/injected provider name (e.g. tests) outside VALID_PROVIDERS.
    chain: list[str] = [primary] if primary else []
    for p in follow_order:
        if p not in chain:
            chain.append(p)
    # mock is always the final safety net — even when the user-supplied
    # order omits it (任务要求：mock 永远可用兜底).
    if "mock" not in chain:
        chain.append("mock")
    return chain


# ═══════════════════════════════════════════════════════════════════════
# Availability & error classification
# ═══════════════════════════════════════════════════════════════════════


def provider_available(provider_name: str, provider: Any) -> bool:
    """Whether a provider can be attempted in the chain.

    - ``mock`` is always available (final safety net).
    - Skeleton providers (``is_skeleton = True``) are skipped WITHOUT being
      called — calling them would raise ``NotImplementedError``.
    - Providers with no API key configured are skipped (nothing to call with).
    """
    name = provider_name.strip().lower()
    if name == "mock":
        return True
    if getattr(provider, "is_skeleton", False):
        return False
    key_envs = PROVIDER_KEY_ENVS.get(name, ())
    if key_envs:
        return any(os.environ.get(env) for env in key_envs)
    return True


def _http_code(exc: BaseException) -> int | None:
    """Extract an HTTP status code from an exception if it carries one."""
    if isinstance(exc, urllib.error.HTTPError):
        return int(getattr(exc, "code", 0) or 0)
    # DeepSeekProvider wraps HTTPError in RuntimeError after retries; the
    # message names the original error (e.g. "HTTP Error 401: Unauthorized").
    msg = str(exc)
    for token in ("HTTP Error", "HTTPError", "status code"):
        idx = msg.find(token)
        if idx != -1:
            digits = ""
            for ch in msg[idx + len(token):]:
                if ch.isdigit():
                    digits += ch
                elif digits:
                    break
            if digits:
                return int(digits)
    return None


def _reason_for_code(code: int) -> str:
    if code == 429:
        return "rate_limit"
    if code >= 500:
        return "http_5xx"
    return "http_4xx"


def is_fallback_eligible(exc: BaseException) -> bool:
    """Whether an exception should trigger provider degradation.

    Degrade:  connection errors, timeouts, HTTP 5xx, HTTP 429 (rate limit),
    budget overrun, missing key / transport-level RuntimeError.
    Do NOT degrade: HTTP 4xx business errors (invalid key etc. — a fallback
    provider would fail the same way), ValueError (config error).
    """
    # HTTP status first — most precise signal.
    code = _http_code(exc)
    if code is not None:
        return code in _DEGRADE_HTTP_CODES

    # Network-level errors → degrade.
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            urllib.error.URLError,
            OSError,
            json.JSONDecodeError,
        ),
    ):
        return True

    # Config errors → never degrade.
    if isinstance(exc, ValueError):
        return False

    # Budget overrun at transport layer → degrade.
    msg = str(exc).lower()
    if any(marker in msg for marker in _BUDGET_MARKERS):
        return True

    # Generic RuntimeError from a provider transport failure → degrade
    # (DeepSeekProvider raises RuntimeError after exhausting retries).
    return isinstance(exc, RuntimeError)


# ═══════════════════════════════════════════════════════════════════════
# Fallback chain execution
# ═══════════════════════════════════════════════════════════════════════


async def call_with_fallback(
    messages: list[dict[str, str]],
    config: LLMConfig,
    provider_factory: Callable[[str], AbstractProvider] | None = None,
    *,
    skip_primary_reason: str | None = None,
) -> LLMResponse:
    """Call a provider with an automatic degradation chain.

    Args:
        messages: Chat messages (already assembled by LLMClient).
        config: Resolved per-call configuration.
        provider_factory: Callable(name) → provider instance. Defaults to
            ``yuleosh.llm.client._get_provider`` (lazy import to avoid
            circular import at module load).
        skip_primary_reason: When set (e.g. ``"budget_exceeded"``), the
            primary provider is skipped without being called and a fallback
            event with this reason is recorded (used when the token budget
            pre-check already failed for the primary provider).

    Returns:
        The first successful LLMResponse, or an LLMResponse carrying the
        error of the last failed attempt (with ``provider`` set to the
        primary provider and ``error`` describing the failure).
    """
    if provider_factory is None:
        from yuleosh.llm.client import _get_provider

        provider_factory = _get_provider

    if not fallback_enabled(config):
        # Explicit single-provider mode — legacy behaviour (failures are
        # returned as LLMResponse.error, matching LLMClient's pre-fallback
        # contract).
        provider = provider_factory(config.provider)
        try:
            response = await provider.chat(messages, config)
            return response
        except Exception as exc:  # noqa: BLE001 — single-provider mode
            log.error("provider_fallback: 单 provider 模式调用失败: %s", exc)
            return LLMResponse(
                content="",
                model=config.model,
                provider=config.provider,
                token_usage={},
                cost=0.0,
                error=str(exc),
            )

    chain = resolve_fallback_order(config)

    last_error: BaseException | None = None
    last_error_provider: str | None = None
    events: list[FallbackEvent] = []

    start_idx = 0
    if skip_primary_reason is not None and chain:
        events.append(
            FallbackEvent(
                from_provider=chain[0],
                to_provider=chain[1] if len(chain) > 1 else "(none)",
                reason=skip_primary_reason,
                duration_s=0.0,
            )
        )
        log.warning(
            "provider_fallback: 跳过主 provider %s (%s)",
            chain[0],
            skip_primary_reason,
        )
        start_idx = 1

    for idx in range(start_idx, len(chain)):
        name = chain[idx]
        try:
            provider = provider_factory(name)
        except Exception as exc:  # noqa: BLE001 — unknown provider in chain
            log.warning("provider_fallback: 无法实例化 provider '%s': %s", name, exc)
            last_error = exc
            last_error_provider = name
            continue

        if not provider_available(name, provider):
            reason = (
                "skeleton"
                if getattr(provider, "is_skeleton", False)
                else "no_key"
            )
            log.info("provider_fallback: 跳过 %s (%s)", name, reason)
            events.append(
                FallbackEvent(
                    from_provider=last_error_provider or config.provider,
                    to_provider=name,
                    reason=reason,
                    duration_s=0.0,
                )
            )
            continue

        start = time.time()
        try:
            response = await provider.chat(messages, config)
            response.duration_s = time.time() - start
            # Audit the final provider actually used.
            if response.provider != config.provider and events:
                log.warning(
                    "provider_fallback: 降级 %s → %s (%s, %.2fs)",
                    config.provider,
                    response.provider,
                    events[0].reason,
                    response.duration_s,
                )
            _flush_events(events)
            return response
        except Exception as exc:  # noqa: BLE001 — provider errors are classified below
            duration = time.time() - start
            last_error = exc
            last_error_provider = name

            if not is_fallback_eligible(exc):
                # Business error (e.g. 4xx invalid key) — degrading won't help.
                log.error(
                    "provider_fallback: %s 失败且不可降级 (%s): %s",
                    name,
                    type(exc).__name__,
                    exc,
                )
                events.append(
                    FallbackEvent(
                        from_provider=name,
                        to_provider="(abort)",
                        reason="non_degradable",
                        duration_s=duration,
                        error=str(exc),
                    )
                )
                break

            reason = _classify_reason(exc)
            log.warning(
                "provider_fallback: %s 失败，降级到下一个 (%s): %s",
                name,
                reason,
                exc,
            )
            next_name = chain[idx + 1] if idx + 1 < len(chain) else "(none)"
            events.append(
                FallbackEvent(
                    from_provider=name,
                    to_provider=next_name,
                    reason=reason,
                    duration_s=duration,
                    error=str(exc),
                )
            )

    # Chain exhausted — record events and return the last failure.
    _flush_events(events)
    return LLMResponse(
        content="",
        model=config.model,
        provider=config.provider,
        token_usage={},
        cost=0.0,
        error=(
            f"All providers failed: {last_error}"
            if last_error is not None
            else "No providers available in fallback chain"
        ),
    )


def _classify_reason(exc: BaseException) -> str:
    """Map an exception to a fallback reason string."""
    code = _http_code(exc)
    if code is not None:
        return _reason_for_code(code)
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, (ConnectionError, urllib.error.URLError, OSError)):
        return "connection_error"
    msg = str(exc).lower()
    if any(marker in msg for marker in _BUDGET_MARKERS):
        return "budget_exceeded"
    return "transport_error"


def _flush_events(events: list[FallbackEvent]) -> None:
    """Write all recorded fallback events to the audit log (best-effort)."""
    if not events:
        return
    for ev in events:
        try:
            CostLogger.log_fallback_event(
                from_provider=ev.from_provider,
                to_provider=ev.to_provider,
                reason=ev.reason,
                duration_s=ev.duration_s,
                error=ev.error,
            )
        except Exception as exc:  # noqa: BLE001 — logging must never break calls
            log.warning("provider_fallback: 审计日志写入失败: %s", exc)
