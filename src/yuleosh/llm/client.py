#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH LLM Client — OpenAI-compatible API client.

Reads configuration from environment variables:
  LLM_API_KEY          (fallback: DEEPSEEK_API_KEY → OPENAI_API_KEY)
  LLM_BASE_URL         (default: https://api.deepseek.com)
  LLM_MODEL            (default: deepseek-chat)
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error

log = logging.getLogger("llm.client")


def _resolve_env() -> tuple[str, str, str]:
    """Resolve API key, base URL, and model from environment."""
    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    return api_key, base_url, model


def _build_payload(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> bytes:
    """Build the JSON request body for a chat completion."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    return json.dumps(body).encode("utf-8")


def _build_request(url: str, api_key: str, payload: bytes) -> urllib.request.Request:
    """Build a urllib Request with standard headers."""
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    return req


def _do_request(req: urllib.request.Request, timeout: int = 60) -> dict:
    """Execute the HTTP request and parse the JSON response.

    Returns the parsed response dict from the API.
    Raises RuntimeError on HTTP errors or malformed responses.
    """
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
            detail = json.loads(body)
            msg = detail.get("error", {}).get("message", str(exc))
        except Exception:
            msg = f"HTTP {exc.code}: {body.decode('utf-8', errors='replace')[:500] or str(exc)}"
        raise RuntimeError(f"LLM API error: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM API connection error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM API returned invalid JSON: {e}")


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 60,
    retries: int = 3,
) -> dict:
    """Send a chat completion request to the LLM API.

    Args:
        system_prompt: System-level instructions for the LLM.
        user_prompt: The user message / query.
        temperature: Sampling temperature (default: 0.3).
        max_tokens: Maximum tokens in the response (default: 4096).
        timeout: HTTP request timeout in seconds (default: 60).
        retries: Number of retry attempts on failure (default: 3).

    Returns:
        dict with keys:
            "content" (str)  — the LLM's response text.
            "model" (str)    — the model identifier used.
            "usage" (dict)   — token usage info (prompt_tokens,
                                completion_tokens, total_tokens).

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    api_key, base_url, model = _resolve_env()

    if not api_key:
        raise RuntimeError(
            "No LLM API key found. Set LLM_API_KEY, DEEPSEEK_API_KEY, "
            "or OPENAI_API_KEY environment variable."
        )

    url = f"{base_url}/v1/chat/completions"
    payload = _build_payload(system_prompt, user_prompt, model, temperature, max_tokens)
    req = _build_request(url, api_key, payload)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            log.info(
                "LLM request: model=%s, system_len=%d, user_len=%d (attempt %d/%d)",
                model, len(system_prompt), len(user_prompt), attempt, retries,
            )
            data = _do_request(req, timeout=timeout)

            if "choices" not in data or not data["choices"]:
                raise RuntimeError(f"Unexpected API response structure: {json.dumps(data)[:300]}")

            choice = data["choices"][0]
            content = choice.get("message", {}).get("content", "")

            if content is None:
                # Some APIs return null content for refusal/finish_reason
                finish_reason = choice.get("finish_reason", "unknown")
                content = f"[LLM refused to respond, finish_reason={finish_reason}]"

            return {
                "content": content,
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
            }

        except RuntimeError as e:
            last_error = e
            if attempt < retries:
                backoff = 1.0 * (2 ** (attempt - 1))
                log.warning(
                    "LLM attempt %d/%d failed: %s. Retrying in %.1fs…",
                    attempt, retries, e, backoff,
                )
                time.sleep(backoff)
            else:
                log.error("LLM all %d attempts failed: %s", retries, e)
                raise

    # Should not be reached, but safety net:
    raise RuntimeError(f"LLM request failed after {retries} retries: {last_error}")
