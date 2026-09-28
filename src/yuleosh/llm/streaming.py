# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""llm/streaming.py — OpenAI-compatible SSE 流式调用 + delta 合并 + 事件发射。

职责分层：
  * ``iter_sse_data`` / ``parse_openai_chunk`` —— 纯解析（无 IO，易测）；
  * ``stream_request`` —— urllib 流式 POST，逐 data 行回调（供 provider 与
    legacy ``chat_completion`` 共用）；
  * ``DeltaCoalescer`` —— 高频 token 合并节流（≥min_chars 或 ≥max_interval_s
    刷出），保护 EventBus 队列与前端渲染；
  * ``StepStreamEmitter`` —— 把合并后的文本以 ``llm_delta`` 事件发到
    ``EVENT_BUS``（ephemeral，不进 replay 历史）。

开关语义：一切流式都是 **opt-in** —— 只有 ``LLMConfig.stream`` 为 True 且
显式提供 ``on_chunk`` 时才生效；默认路径（stream=False）行为与字节级不变，
既有测试 ``body["stream"] is False`` 断言不受影响。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable, Iterator

log = logging.getLogger("llm.streaming")

# SSE 终止标记（OpenAI / DeepSeek / Ollama 兼容端点统一使用）。
_DONE_MARKER = "[DONE]"

# 合并节流默认阈值：达到任一条件即刷出。
DEFAULT_MIN_CHARS = 160
DEFAULT_MAX_INTERVAL_S = 0.15


# ─── 纯解析（无 IO） ────────────────────────────────────────────────────


def iter_sse_data(lines: Iterable[bytes | str]) -> Iterator[str]:
    """从响应行序列产出 ``data:`` 载荷。

    * 容忍跨 readline 的行分片（调用方逐行喂入即可）；
    * 忽略注释（``:`` 开头）、心跳与空行；
    * 遇 ``[DONE]`` 停止迭代。
    """
    for raw in lines:
        if isinstance(raw, bytes):
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 — 解码失败按垃圾行跳过
                continue
        else:
            line = str(raw)
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        if payload == _DONE_MARKER:
            return
        yield payload


def parse_openai_chunk(payload: str) -> tuple[str, dict | None]:
    """解析单条 OpenAI 兼容 data 载荷 → ``(delta_text, usage_or_None)``。

    兼容形态：
      * 正常增量：``choices[0].delta.content``；
      * 仅 usage 的末帧（``stream_options.include_usage``）：delta 为空；
      * 垃圾/非 JSON 载荷：返回 ``("", None)``，不抛。
    """
    try:
        obj = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return "", None
    if not isinstance(obj, dict):
        return "", None

    usage = obj.get("usage")
    if not isinstance(usage, dict):
        usage = None

    delta_text = ""
    choices = obj.get("choices") or []
    if choices and isinstance(choices[0], dict):
        delta = choices[0].get("delta") or {}
        content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(content, str):
            delta_text = content
    return delta_text, usage


def estimate_token_usage(messages: list[dict[str, str]], content: str) -> dict:
    """无 usage 帧时的兜底估算（OpenAI 风格 dict）。"""
    from yuleosh.llm.token_budget import TokenBudgetChecker

    prompt_text = "\n".join(str(m.get("content") or "") for m in messages)
    prompt_tokens = TokenBudgetChecker.estimate_tokens(prompt_text)
    completion_tokens = TokenBudgetChecker.estimate_tokens(content)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def is_local_endpoint(base_url: str) -> bool:
    """True 当 base_url 指向本机/自建端点（Ollama 等）。

    用于决定是否发送 ``stream_options`` 这类云端扩展 —— 自建端点未必
    支持，宁可少发（缺 usage 时走 ``estimate_token_usage`` 兜底）。
    """
    low = (base_url or "").lower()
    return any(
        tok in low
        for tok in ("localhost", "127.0.0.1", "0.0.0.0", "ollama", "[::1]")
    )


# ─── 流式 HTTP ──────────────────────────────────────────────────────────


def stream_request(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    *,
    timeout_s: int,
    on_data: Callable[[str], None],
    max_retries: int = 1,
    provider: str = "llm",
) -> None:
    """POST JSON（body 须已含 ``"stream": True``）并逐 data 载荷回调。

    重试语义（与 provider_fallback 的"首 delta 前可重试"约定一致）：
      * 首个 data 行之前失败 → 最多 ``max_retries`` 次，指数退避；
      * 已收到数据后失败 → 不再重试，直接 ``RuntimeError``（部分输出不可
        静默当成功；由上层决定 fallback 或标记失败）。

    Raises:
        RuntimeError: 重试耗尽或中途失败，消息含 provider 名。
    """
    payload = json.dumps(body).encode("utf-8")
    received_any = False
    last_error: Exception | None = None

    for attempt in range(1, max(1, int(max_retries)) + 1):
        try:
            req = urllib.request.Request(
                url, data=payload, headers=headers, method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                for data in iter_sse_data(resp):
                    received_any = True
                    on_data(data)
            return
        except Exception as exc:  # noqa: BLE001 — 分类后重抛
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            last_error = exc
            log.warning(
                "%s stream attempt %d/%d failed: %s",
                provider, attempt, max_retries, exc,
            )
            if received_any or attempt >= max(1, int(max_retries)):
                break
            time.sleep(1.0 * (2 ** (attempt - 1)))

    raise RuntimeError(
        f"{provider} streaming request failed"
        + (" mid-stream" if received_any else "")
        + f": {last_error}"
    ) from last_error


def stream_chat_response(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    messages: list[dict[str, str]],
    timeout_s: int,
    max_retries: int,
    provider: str,
    api_model: str,
    on_chunk: Callable[[str], None],
    on_stream_start: Callable[[], None] | None = None,
    estimate_cost: Callable[[int, int], float] | None = None,
) -> Any:
    """同步执行流式请求并汇总为 ``LLMResponse``（provider 共用，走 to_thread）。

    语义：
      * ``body`` 必须已含 ``"stream": True``；
      * ``on_stream_start`` 在首个字节之前触发（重试/回退的复位信号）；
      * 首个 delta 前失败可重试，之后失败抛 ``RuntimeError``（绝不把
        半截输出当成功返回）；
      * 响应无任何内容同样抛错。

    降级责任方：本函数与 provider 层**不做降级** —— 失败一律裸抛
    ``RuntimeError``，由调用方决定后续。两条真实通路：
    ``LLMClient.call`` 经 ``provider_fallback`` 链降级到下一个 provider；
    legacy ``chat_completion`` 在非流式循环里重试一次（见
    ``client._stream_legacy_chat`` 返回 None 的约定）。
    """
    from yuleosh.llm.providers.base import LLMResponse

    if on_stream_start is not None:
        on_stream_start()

    parts: list[str] = []
    usage: dict | None = None

    def _on_data(data: str) -> None:
        nonlocal usage
        text, chunk_usage = parse_openai_chunk(data)
        if chunk_usage is not None:
            usage = chunk_usage
        if text:
            parts.append(text)
            on_chunk(text)

    stream_request(
        url, headers, body,
        timeout_s=timeout_s, on_data=_on_data,
        max_retries=max_retries, provider=provider,
    )

    content = "".join(parts)
    if not content:
        raise RuntimeError(
            f"{provider} provider ({provider}): 流式响应未返回任何内容"
        )

    final_usage = usage if usage is not None else estimate_token_usage(messages, content)
    prompt_tokens = int(final_usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(final_usage.get("completion_tokens", 0) or 0)
    total_tokens = int(
        final_usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
    )
    cost = estimate_cost(prompt_tokens, completion_tokens) if estimate_cost else 0.0

    return LLMResponse(
        content=content,
        model=api_model,
        provider=provider,
        token_usage={
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        cost=cost,
    )


# ─── 合并节流 ───────────────────────────────────────────────────────────


class DeltaCoalescer:
    """把高频 delta 合并成低频块（线程安全）。

    刷出条件（在 ``add`` 时判定）：缓冲 ≥ ``min_chars`` 或距上次刷出
    ≥ ``max_interval_s``；``flush()`` 强制刷出（调用方在 ``close`` 时调用）。
    不用定时器线程 —— 尾部延迟由下一次 add 或 close 覆盖。
    """

    def __init__(
        self,
        on_flush: Callable[[str], None],
        *,
        min_chars: int = DEFAULT_MIN_CHARS,
        max_interval_s: float = DEFAULT_MAX_INTERVAL_S,
    ) -> None:
        self._on_flush = on_flush
        self._min_chars = max(1, int(min_chars))
        self._max_interval_s = max(0.0, float(max_interval_s))
        self._lock = threading.Lock()
        self._buf: list[str] = []
        self._buf_chars = 0
        self._last_flush = time.monotonic()

    def add(self, text: str) -> None:
        if not text:
            return
        chunk = ""
        with self._lock:
            self._buf.append(text)
            self._buf_chars += len(text)
            due = (
                self._buf_chars >= self._min_chars
                or (time.monotonic() - self._last_flush) >= self._max_interval_s
            )
            if due:
                chunk = self._take_locked()
        if chunk:
            self._on_flush(chunk)

    def flush(self) -> None:
        with self._lock:
            chunk = self._take_locked()
        if chunk:
            self._on_flush(chunk)

    def reset(self) -> None:
        """丢弃未刷出缓冲（provider 重试/回退时避免串台）。"""
        with self._lock:
            self._buf = []
            self._buf_chars = 0
            self._last_flush = time.monotonic()

    def _take_locked(self) -> str:
        chunk = "".join(self._buf)
        self._buf = []
        self._buf_chars = 0
        self._last_flush = time.monotonic()
        return chunk


# ─── 事件发射 ───────────────────────────────────────────────────────────


class StepStreamEmitter:
    """把一次 step 内的 LLM 流式输出发为 ``llm_delta`` 事件。

    整帧语义见 ``realtime.emit_pipeline_llm_delta``：
      * ``on_stream_start()``：attempt+1、``reset=True``（前端清屏，用于
        provider 重试/回退后重开）；
      * ``on_chunk(text)``：合并且缓存，达到阈值后发增量帧；
      * ``close()``：终刷 + ``done=True`` 帧（正常/异常终止都要调）。
    """

    def __init__(self, *, run_id: str, project_dir: str, step_key: str,
                 step_index: int = -1, model: str = "", provider: str = "",
                 min_chars: int = DEFAULT_MIN_CHARS,
                 max_interval_s: float = DEFAULT_MAX_INTERVAL_S) -> None:
        self.run_id = run_id
        self.project_dir = project_dir
        self.step_key = step_key
        self.step_index = step_index
        self.model = model
        self.provider = provider

        self._lock = threading.Lock()
        self._seq = 0
        self._total_chars = 0
        self._attempt = 0
        self._closed = False
        self._coalescer = DeltaCoalescer(
            self._emit_chunk, min_chars=min_chars, max_interval_s=max_interval_s,
        )

    # provider 回调（签名即 LLMConfig.on_stream_start / on_chunk）
    def on_stream_start(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._attempt += 1
            attempt = self._attempt
            self._total_chars = 0
        self._coalescer.reset()
        self._publish(text="", attempt=attempt, reset=True, done=False)

    def on_chunk(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            if self._closed:
                return
        self._coalescer.add(text)

    def on_chunk_delta(self, text: str) -> None:
        """兼容别名（provider 端回调名统一走 on_chunk）。"""
        self.on_chunk(text)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._coalescer.flush()
        self._publish(text="", done=True)

    @property
    def is_closed(self) -> bool:
        """True 表示 close() 已调用（此后 on_chunk 静默忽略）。"""
        return self._closed

    # internals
    def _emit_chunk(self, chunk: str) -> None:
        with self._lock:
            self._seq += 1
            self._total_chars += len(chunk)
            seq = self._seq
            total = self._total_chars
            attempt = self._attempt or 1
        self._publish(text=chunk, seq=seq, total_chars=total,
                      attempt=attempt, reset=False, done=False)

    def _publish(self, *, text: str, seq: int | None = None,
                 total_chars: int | None = None, attempt: int | None = None,
                 reset: bool = False, done: bool = False) -> None:
        from yuleosh.realtime import emit_pipeline_llm_delta

        emit_pipeline_llm_delta(
            run_id=self.run_id,
            project_dir=self.project_dir,
            step_key=self.step_key,
            step_index=self.step_index,
            text=text,
            seq=seq if seq is not None else self._seq,
            total_chars=total_chars if total_chars is not None else self._total_chars,
            attempt=attempt if attempt is not None else (self._attempt or 1),
            reset=reset,
            done=done,
            model=self.model,
            provider=self.provider,
        )


def emitter_for_current_step(model: str = "", provider: str = "") -> StepStreamEmitter | None:
    """按当前 ``LLMCallContext`` 创建 emitter；无上下文返回 None。

    无上下文场景（CLI 单测、引擎直调、无 run 的 LLM 调用）保持完全非流式，
    行为与今天一致。
    """
    try:
        from yuleosh.realtime import get_current_llm_call_context
        ctx = get_current_llm_call_context()
    except Exception:  # noqa: BLE001 — 事件层问题绝不影响调用
        return None
    if ctx is None:
        return None
    return StepStreamEmitter(
        run_id=ctx.run_id,
        project_dir=ctx.project_dir,
        step_key=ctx.step_key,
        step_index=ctx.step_index,
        model=model,
        provider=provider,
    )


__all__ = [
    "DEFAULT_MIN_CHARS",
    "DEFAULT_MAX_INTERVAL_S",
    "DeltaCoalescer",
    "StepStreamEmitter",
    "emitter_for_current_step",
    "estimate_token_usage",
    "is_local_endpoint",
    "iter_sse_data",
    "parse_openai_chunk",
    "stream_chat_response",
    "stream_request",
]
