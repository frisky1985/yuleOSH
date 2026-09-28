# @tests src/yuleosh/llm/streaming.py, src/yuleosh/llm/client.py, src/yuleosh/realtime.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for token-level LLM streaming (SSE → llm_delta realtime frames).

Covers the full chain added for the dashboard「LLM 实时输出」panel:

- pure parsing: ``iter_sse_data`` / ``parse_openai_chunk`` / ``is_local_endpoint``
- ``DeltaCoalescer`` merge/throttle semantics
- ``StepStreamEmitter`` frame sequence (reset → chunks → done, retry=attempt+1)
- ``emit_pipeline_llm_delta`` ephemeral publish (not replayed into history)
- ``emitter_for_current_step`` ContextVar gating (no ctx → no streaming)
- ``stream_chat_response`` aggregation + usage fallback + empty-stream error
- DeepSeekProvider opt-in streaming branch (body stream/stream_options)
- legacy ``chat_completion``: auto-wire inside pipeline ctx, degrade-to-non-
  streaming when the endpoint ignores/fails SSE, full-content push on degrade
- OpenAIProvider opt-in streaming branch (P0-1: stream=true 曾必现 JSON 解析失败)
- OllamaProvider native NDJSON streaming (P0-2: stream 曾写死 False 永不出 delta)
- chat_completion failure path closes emitter (P1-3: 失败曾让前端永久转圈)
- LLMClient auto-wire uses a config **copy** (R1: 显式 stream=True 被硬编码还原丢弃;
  R2: 并发复用同一 LLMConfig 实例时相互清空 on_chunk)

All network I/O is mocked — no real calls (AC9).
"""

import asyncio
import json
import os
import time
from unittest import mock

import pytest

from yuleosh.llm.client import LLMClient, _pipeline_emitter, _stream_legacy_chat, chat_completion
from yuleosh.llm.providers.base import LLMConfig, LLMResponse
from yuleosh.llm.providers.deepseek import DeepSeekProvider
from yuleosh.llm.providers.ollama import OllamaProvider
from yuleosh.llm.providers.openai import OpenAIProvider
from yuleosh.llm.streaming import (
    DeltaCoalescer,
    StepStreamEmitter,
    emitter_for_current_step,
    estimate_token_usage,
    is_local_endpoint,
    iter_sse_data,
    parse_openai_chunk,
    stream_chat_response,
)
from yuleosh.realtime import (
    EVENT_BUS,
    LLMCallContext,
    emit_pipeline_llm_delta,
    reset_current_llm_call_context,
    set_current_llm_call_context,
)


@pytest.fixture
def _bus():
    """Fresh bus state + drain helper (same pattern as test_realtime.py)."""
    EVENT_BUS._subs.clear()
    EVENT_BUS._history.clear()
    EVENT_BUS._next_id = 1

    def drain(sub):
        out = []
        while not sub.queue.empty():
            out.append(sub.queue.get_nowait())
        return out

    return drain


def _sse_lines(*payloads: str) -> list[bytes]:
    """Build raw SSE response lines; appends the [DONE] terminator."""
    lines = [f"data: {p}\n".encode() for p in payloads]
    lines.append(b"data: [DONE]\n")
    return lines


def _sse_ctx(lines: list[bytes]):
    """urlopen mock context manager yielding ``lines`` when iterated."""
    fake_resp = mock.MagicMock()
    fake_resp.__iter__.return_value = iter(lines)
    fake_ctx = mock.MagicMock()
    fake_ctx.__enter__.return_value = fake_resp
    fake_ctx.__exit__.return_value = False
    return fake_ctx


def _json_ctx(body: dict):
    """urlopen mock context manager for the non-streaming JSON path.

    Also iterable: an endpoint that ignores ``stream: true`` returns plain
    JSON — iterated line-by-line it yields one raw (non ``data:``) line,
    which ``iter_sse_data`` skips → zero deltas → degrade path.
    """
    raw = json.dumps(body).encode()
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = raw
    fake_resp.__iter__.return_value = iter([raw])
    fake_ctx = mock.MagicMock()
    fake_ctx.__enter__.return_value = fake_resp
    fake_ctx.__exit__.return_value = False
    return fake_ctx


class _FlakyResp:
    """Iterable response: yields SSE lines, then raises ``exc`` at exhaustion."""

    def __init__(self, lines: list[bytes], exc: Exception):
        self._it = iter(lines)
        self._exc = exc

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise self._exc


def _flaky_sse_ctx(lines: list[bytes], exc: Exception):
    """urlopen mock whose response breaks mid-stream (after yielding ``lines``)."""
    fake_ctx = mock.MagicMock()
    fake_ctx.__enter__.return_value = _FlakyResp(lines, exc)
    fake_ctx.__exit__.return_value = False
    return fake_ctx


def _http_error(code: int = 500):
    import urllib.error

    return urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs={}, fp=None)


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------


class TestSseParsing:
    def test_iter_skips_comments_and_empty_lines(self):
        lines = [b": heartbeat\n", b"\n", b"data: {\"a\":1}\n", b"  \n"]
        assert list(iter_sse_data(lines)) == ['{"a":1}']

    def test_iter_stops_at_done_marker(self):
        lines = ["data: one\n", "data: [DONE]\n", "data: two\n"]
        assert list(iter_sse_data(lines)) == ["one"]

    def test_iter_ignores_non_data_lines(self):
        lines = ["event: message\n", "data: ok\n", "foo: bar\n"]
        assert list(iter_sse_data(lines)) == ["ok"]

    def test_parse_normal_delta(self):
        payload = json.dumps({"choices": [{"delta": {"content": "Hi"}}]})
        text, usage = parse_openai_chunk(payload)
        assert text == "Hi"
        assert usage is None

    def test_parse_usage_only_frame(self):
        payload = json.dumps({"choices": [], "usage": {"prompt_tokens": 3}})
        text, usage = parse_openai_chunk(payload)
        assert text == ""
        assert usage == {"prompt_tokens": 3}

    def test_parse_garbage_returns_empty(self):
        assert parse_openai_chunk("not json") == ("", None)
        assert parse_openai_chunk("[1,2]") == ("", None)

    def test_is_local_endpoint(self):
        assert is_local_endpoint("http://localhost:11434/v1")
        assert is_local_endpoint("http://127.0.0.1:8080")
        assert is_local_endpoint("http://0.0.0.0:9000")
        assert is_local_endpoint("http://[::1]:11434")
        assert is_local_endpoint("https://my-ollama.example.com")
        assert not is_local_endpoint("https://api.deepseek.com")
        assert not is_local_endpoint("https://api.openai.com")


# ---------------------------------------------------------------------------
# DeltaCoalescer
# ---------------------------------------------------------------------------


class TestDeltaCoalescer:
    def test_flush_at_min_chars(self):
        flushed = []
        c = DeltaCoalescer(flushed.append, min_chars=5, max_interval_s=999)
        c.add("ab")
        assert flushed == []
        c.add("cd")  # buf 4 < 5 → still buffered
        assert flushed == []
        c.add("efg")  # buf 7 ≥ 5 → flush all
        assert flushed == ["abcdefg"]

    def test_flush_on_interval(self):
        flushed = []
        c = DeltaCoalescer(flushed.append, min_chars=10**6, max_interval_s=0.05)
        c.add("x")
        time.sleep(0.08)
        c.add("y")  # elapsed ≥ max_interval → flush
        assert flushed == ["xy"]

    def test_flush_forces_pending_buffer(self):
        flushed = []
        c = DeltaCoalescer(flushed.append, min_chars=10**6, max_interval_s=999)
        c.add("tail")
        c.flush()
        assert flushed == ["tail"]
        c.flush()  # empty buffer → no-op
        assert flushed == ["tail"]

    def test_reset_drops_buffer(self):
        flushed = []
        c = DeltaCoalescer(flushed.append, min_chars=10**6, max_interval_s=999)
        c.add("stale")
        c.reset()
        c.flush()
        assert flushed == []

    def test_add_empty_is_noop(self):
        flushed = []
        c = DeltaCoalescer(flushed.append)
        c.add("")
        c.flush()
        assert flushed == []


# ---------------------------------------------------------------------------
# StepStreamEmitter → llm_delta frames
# ---------------------------------------------------------------------------


class TestStepStreamEmitter:
    def _emitter(self, **kw):
        return StepStreamEmitter(
            run_id="r1", project_dir="/p", step_key="prd", step_index=2,
            model="deepseek-chat", provider="deepseek",
            min_chars=kw.pop("min_chars", 1),
            max_interval_s=kw.pop("max_interval_s", 999),
            **kw,
        )

    def test_frame_sequence_reset_chunk_done(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        em = self._emitter()
        em.on_stream_start()
        em.on_chunk("hello")
        em.on_chunk(" world")
        assert not em.is_closed
        em.close()
        assert em.is_closed

        frames = [e.payload for e in _bus(sub)]
        kinds = [(f["kind"], f["reset"], f["done"]) for f in frames]
        assert kinds == [
            ("llm_delta", True, False),   # stream_start
            ("llm_delta", False, False),  # chunk 1
            ("llm_delta", False, False),  # chunk 2
            ("llm_delta", False, True),   # done
        ]
        assert frames[0]["attempt"] == 1
        assert frames[0]["text"] == ""
        # seq 单调递增, total_chars 累计
        assert (frames[1]["seq"], frames[1]["total_chars"]) == (1, 5)
        assert (frames[2]["seq"], frames[2]["total_chars"]) == (2, 11)
        assert frames[3]["seq"] == 2  # done 沿用最后 seq
        assert frames[3]["text"] == ""
        # 公共字段
        for f in frames:
            assert f["run_id"] == "r1"
            assert f["step_key"] == "prd"
            assert f["step_index"] == 2
            assert f["model"] == "deepseek-chat"
            assert f["provider"] == "deepseek"

    def test_retry_increments_attempt_and_resets_counters(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        em = self._emitter()
        em.on_stream_start()
        em.on_chunk("ab")           # seq=1, total=2
        em.on_stream_start()        # provider 重试/回退
        em.on_chunk("c")            # seq=2, total=1 (重新累计)
        em.close()

        frames = [e.payload for e in _bus(sub)]
        assert frames[0]["attempt"] == 1 and frames[0]["reset"] is True
        # frames[1] = "ab" chunk; frames[2] = 第二次 on_stream_start 的 reset
        assert frames[2]["attempt"] == 2 and frames[2]["reset"] is True
        assert frames[3]["attempt"] == 2
        assert frames[3]["reset"] is False
        assert frames[3]["total_chars"] == 1
        # seq 跨 attempt 仍单调（前端按 (attempt, seq) 去重）
        assert frames[3]["seq"] > frames[1]["seq"]

    def test_close_is_idempotent_and_blocks_chunks(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        em = self._emitter()
        em.on_stream_start()
        em.on_chunk("x")
        em.close()
        em.close()  # 幂等
        em.on_chunk("ignored")
        em.on_chunk_delta("ignored-alias")
        frames = [e.payload for e in _bus(sub)]
        assert len(frames) == 3  # reset + chunk + done（无多余帧）
        assert em.is_closed

    def test_chunks_below_threshold_coalesce_until_close(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        em = self._emitter(min_chars=100)
        em.on_stream_start()
        em.on_chunk("a")
        em.on_chunk("b")
        assert _bus(sub)[-1].payload["reset"] is True  # 只有 reset 帧
        em.close()  # 终刷
        frames = [e.payload for e in _bus(sub)]
        assert frames[-2]["text"] == "ab"  # 合并为一块刷出
        assert frames[-1]["done"] is True


# ---------------------------------------------------------------------------
# emit_pipeline_llm_delta — ephemeral 语义
# ---------------------------------------------------------------------------


class TestEmitLlmDeltaEphemeral:
    def test_delivered_but_not_in_history(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        eid = emit_pipeline_llm_delta(
            run_id="r1", project_dir="/p", step_key="prd", step_index=2,
            text="hi", seq=1, total_chars=2, attempt=1,
        )
        assert eid is not None
        delivered = _bus(sub)
        assert len(delivered) == 1
        assert delivered[0].payload["kind"] == "llm_delta"
        assert delivered[0].payload["text"] == "hi"
        # ephemeral → 不进 replay 历史（高频帧不挤出 stage_start 等关键事件）
        assert len(EVENT_BUS._history) == 0

    def test_swallows_bus_failure(self, _bus, monkeypatch):
        def boom(*a, **kw): raise RuntimeError("bus down")
        monkeypatch.setattr(EVENT_BUS, "publish", boom)
        # 事件层失败绝不打断 LLM 主流程
        emit_pipeline_llm_delta(
            run_id="r1", project_dir="/p", step_key="prd", step_index=2,
            text="hi", seq=1,
        )


# ---------------------------------------------------------------------------
# emitter_for_current_step — ContextVar 门控
# ---------------------------------------------------------------------------


class TestEmitterForCurrentStep:
    def test_no_context_returns_none(self):
        assert emitter_for_current_step() is None

    def test_context_builds_emitter(self):
        token = set_current_llm_call_context(LLMCallContext(
            run_id="run-x", project_dir="/proj", step_key="arch", step_index=5,
        ))
        try:
            em = emitter_for_current_step(model="m", provider="deepseek")
        finally:
            reset_current_llm_call_context(token)
        assert isinstance(em, StepStreamEmitter)
        assert em.run_id == "run-x"
        assert em.project_dir == "/proj"
        assert em.step_key == "arch"
        assert em.step_index == 5
        assert em.model == "m" and em.provider == "deepseek"

    def test_pipeline_emitter_helper_reads_env(self):
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat",
                                          "YULEOSH_LLM_PROVIDER": "deepseek"}):
            token = set_current_llm_call_context(LLMCallContext(
                run_id="r", project_dir="/p", step_key="k", step_index=0,
            ))
            try:
                em = _pipeline_emitter()
            finally:
                reset_current_llm_call_context(token)
        assert em is not None
        assert em.model == "deepseek-chat"
        assert em.provider == "deepseek"


# ---------------------------------------------------------------------------
# stream_chat_response — provider 共用的流式聚合
# ---------------------------------------------------------------------------


class TestStreamChatResponse:
    def _run(self, lines, **kw):
        chunks, started = [], []
        resp = stream_chat_response(
            url="https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": "Bearer sk"},
            body={"model": "m", "stream": True},
            messages=[{"role": "user", "content": "hi"}],
            timeout_s=30, max_retries=1,
            provider="deepseek", api_model="deepseek-chat",
            on_chunk=chunks.append,
            on_stream_start=lambda: started.append(True),
            **kw,
        )
        return resp, chunks, started

    def test_success_accumulates_content_and_usage(self):
        lines = _sse_lines(
            json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
            json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
            json.dumps({"choices": [], "usage": {
                "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}),
        )
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=_sse_ctx(lines))):
            resp, chunks, started = self._run(lines)
        assert started == [True]           # on_stream_start 首字节前触发
        assert chunks == ["Hel", "lo"]
        assert resp.content == "Hello"
        assert resp.model == "deepseek-chat"
        assert resp.provider == "deepseek"
        assert resp.token_usage == {"prompt": 10, "completion": 5, "total": 15}

    def test_missing_usage_frame_estimates_fallback(self):
        lines = _sse_lines(json.dumps({"choices": [{"delta": {"content": "abc"}}]}))
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=_sse_ctx(lines))):
            resp, chunks, _ = self._run(lines)
        assert resp.content == "abc"
        est = estimate_token_usage([{"role": "user", "content": "hi"}], "abc")
        assert resp.token_usage["prompt"] == est["prompt_tokens"]
        assert resp.token_usage["completion"] == est["completion_tokens"]

    def test_empty_stream_raises(self):
        # 只有 usage 帧、无 content → 上层降级非流式重试
        lines = _sse_lines(json.dumps({"choices": [], "usage": {"total_tokens": 1}}))
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=_sse_ctx(lines))):
            with pytest.raises(RuntimeError, match="未返回任何内容"):
                self._run(lines)

    def test_midstream_failure_raises_not_silent(self):
        # 首帧成功后断流 → RuntimeError（半截输出绝不静默当成功）
        lines = [b'data: {"choices":[{"delta":{"content":"partial"}}]}\n']  # 无 [DONE]
        flaky = _flaky_sse_ctx(lines, _http_error(500))
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=flaky)):
            with mock.patch("time.sleep"):
                with pytest.raises(RuntimeError, match="mid-stream"):
                    stream_chat_response(
                        url="https://x", headers={}, body={"stream": True},
                        messages=[], timeout_s=1, max_retries=2,
                        provider="deepseek", api_model="m",
                        on_chunk=lambda t: None,
                    )


# ---------------------------------------------------------------------------
# DeepSeekProvider opt-in streaming
# ---------------------------------------------------------------------------


class TestDeepSeekStreaming:
    def test_default_body_unchanged_no_stream_options(self):
        """GIVEN stream=False WHEN chat THEN body 与旧实现字面一致（回归守卫）。"""
        mock_urlopen = mock.MagicMock(return_value=_json_ctx({
            "model": "deepseek-chat",
            "choices": [{"message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }))
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(DeepSeekProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(max_retries=1),
                ))
        assert resp.content == "ok"
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is False
        assert "stream_options" not in body  # 非流式绝不携带云端扩展字段

    def test_streaming_branch_sends_sse_and_invokes_callbacks(self):
        lines = _sse_lines(
            json.dumps({"choices": [{"delta": {"content": "产品"}}]}),
            json.dumps({"choices": [{"delta": {"content": "需求"}}]}),
            json.dumps({"choices": [], "usage": {
                "prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8}}),
        )
        chunks, started = [], []
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(DeepSeekProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(
                        max_retries=1,
                        stream=True,
                        on_chunk=chunks.append,
                        on_stream_start=lambda: started.append(True),
                    ),
                ))
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert started == [True]
        assert chunks == ["产品", "需求"]
        assert resp.content == "产品需求"
        assert resp.token_usage == {"prompt": 4, "completion": 4, "total": 8}

    def test_streaming_local_endpoint_omits_stream_options(self):
        lines = _sse_lines(json.dumps({"choices": [{"delta": {"content": "hi"}}]}))
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        with mock.patch.dict(os.environ, {
            "LLM_API_KEY": "ollama", "LLM_BASE_URL": "http://localhost:11434/v1",
        }):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(DeepSeekProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="deepseek-r1:7b", max_retries=1,
                                     stream=True, on_chunk=lambda t: None),
                ))
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert "stream_options" not in body  # 自建端点未必支持
        assert resp.content == "hi"


# ---------------------------------------------------------------------------
# LLMClient.call — 自动接流 / 调用方 on_chunk 优先 / config 还原
# ---------------------------------------------------------------------------


class TestLLMClientAutoWire:
    @pytest.fixture(autouse=True)
    def _clean(self):
        LLMClient.reset()
        yield
        LLMClient.reset()

    def _fake_fallback(self, seen: dict):
        async def fake(msgs, config, skip_primary_reason=None):
            seen["stream"] = getattr(config, "stream", None)
            seen["on_chunk"] = getattr(config, "on_chunk", None)
            seen["on_stream_start"] = getattr(config, "on_stream_start", None)
            if seen["on_chunk"]:
                if callable(seen["on_stream_start"]):
                    seen["on_stream_start"]()
                seen["on_chunk"]("tok")
            return LLMResponse(content="ok", model=config.model,
                               provider=config.provider,
                               token_usage={"prompt": 0, "completion": 0, "total": 0})
        return fake

    def test_no_context_no_streaming(self):
        seen = {}
        cfg = LLMConfig(provider="deepseek")
        with mock.patch("yuleosh.llm.client.call_with_fallback", self._fake_fallback(seen)):
            resp = asyncio.run(LLMClient.call("hi", config=cfg))
        assert resp.content == "ok"
        assert seen["stream"] is not True      # 纯非流式，行为不变
        assert seen["on_chunk"] is None

    def test_context_enables_streaming_and_restores_config(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        seen = {}
        cfg = LLMConfig(provider="deepseek")
        token = set_current_llm_call_context(LLMCallContext(
            run_id="r9", project_dir="/pp", step_key="ut", step_index=1,
        ))
        try:
            with mock.patch("yuleosh.llm.client.call_with_fallback", self._fake_fallback(seen)):
                resp = asyncio.run(LLMClient.call("hi", config=cfg))
        finally:
            reset_current_llm_call_context(token)
        assert resp.content == "ok"
        # 调用期间 config 被注入流式回调
        assert seen["stream"] is True
        assert callable(seen["on_chunk"])
        assert callable(seen["on_stream_start"])
        # finally 里还原 —— 调用方复用的 LLMConfig 不被污染
        assert cfg.stream is False
        assert cfg.on_chunk is None
        assert cfg.on_stream_start is None
        # 帧序列：reset → chunk → done（done 由 LLMClient 关闭 emitter 触发）。
        # 总线上还有 LLMClient 发的 llm_call 成本事件，只取 llm_delta 帧。
        deltas = [f.payload for f in _bus(sub) if f.payload.get("kind") == "llm_delta"]
        frames = [(f["reset"], f["done"], f["text"]) for f in deltas]
        assert frames == [(True, False, ""), (False, False, "tok"), (False, True, "")]

    def test_caller_supplied_on_chunk_wins(self):
        """显式提供 on_chunk 的调用方（如 provider 直调）保留控制权，不自动接流。"""
        seen = {}
        mine = []
        cfg = LLMConfig(provider="deepseek", stream=True, on_chunk=mine.append)
        with mock.patch("yuleosh.llm.client.call_with_fallback", self._fake_fallback(seen)):
            asyncio.run(LLMClient.call("hi", config=cfg))
        assert seen["on_chunk"] == mine.append  # 未被 emitter 覆盖
        assert mine == ["tok"]

    def test_caller_stream_flag_survives_auto_wire(self, _bus):
        """R1 回归：自动接流不得改写调用方实例。

        旧实现直接改 ``resolved_config``，``finally`` 里又硬编码还原成
        ``stream=False / on_chunk=None / on_stream_start=None`` —— 调用方显式
        传入的 ``stream=True`` 与 ``on_stream_start`` 被静默丢弃。
        """
        EVENT_BUS.subscribe({"pipeline"})
        seen = {}
        started = []
        stream_start_cb = started.append   # 绑定一次，供 is 比较（每次访问是新对象）
        cfg = LLMConfig(
            provider="deepseek", stream=True, on_stream_start=stream_start_cb
        )
        token = set_current_llm_call_context(LLMCallContext(
            run_id="r10", project_dir="/pp", step_key="ut", step_index=1,
        ))
        try:
            with mock.patch("yuleosh.llm.client.call_with_fallback", self._fake_fallback(seen)):
                resp = asyncio.run(LLMClient.call("hi", config=cfg))
        finally:
            reset_current_llm_call_context(token)
        assert resp.content == "ok"
        assert seen["stream"] is True              # 本次调用确实走了流式
        assert callable(seen["on_chunk"])          # 用的是本轮流式回调
        # 调用方实例全程只读：原值原样保留（旧实现被 finally 置 False/None）
        assert cfg.stream is True
        assert cfg.on_chunk is None
        assert cfg.on_stream_start is stream_start_cb

    def test_concurrent_calls_share_config_without_clobbering(self, _bus):
        """R2 回归：并发复用同一 ``LLMConfig`` 实例时互不清空流式回调。

        旧实现把 emitter 回调写进调用方实例 —— 先返回者的 ``finally`` 会把
        ``on_chunk`` 清掉，后返回者剩余 delta 全丢。副本方案下各次调用持有
        自己的配置副本，互不影响。
        """
        EVENT_BUS.subscribe({"pipeline"})
        a_entered = asyncio.Event()
        b_entered = asyncio.Event()
        a_finished = asyncio.Event()
        deltas_b: list[str] = []

        def _resp(tag: str, config: LLMConfig) -> LLMResponse:
            return LLMResponse(
                content=tag, model=config.model, provider=config.provider,
                token_usage={"prompt": 0, "completion": 0, "total": 0},
            )

        async def fake(msgs, config, skip_primary_reason=None):
            tag = msgs[-1]["content"]
            if tag == "A":
                a_entered.set()
                await b_entered.wait()
                return _resp(tag, config)
            b_entered.set()
            await a_finished.wait()   # A 已返回 → A 的 finally 已执行
            if config.on_chunk is not None:
                config.on_chunk("tok-B")
                deltas_b.append("tok-B")
            return _resp(tag, config)

        cfg = LLMConfig(provider="deepseek")
        token = set_current_llm_call_context(LLMCallContext(
            run_id="r11", project_dir="/pp", step_key="ut", step_index=1,
        ))

        async def scenario():
            task_a = asyncio.create_task(LLMClient.call("A", config=cfg))
            await a_entered.wait()
            task_b = asyncio.create_task(LLMClient.call("B", config=cfg))
            await b_entered.wait()
            await task_a
            a_finished.set()
            await task_b

        try:
            with mock.patch("yuleosh.llm.client.call_with_fallback", fake):
                asyncio.run(scenario())
        finally:
            reset_current_llm_call_context(token)

        assert deltas_b == ["tok-B"]          # B 的 delta 未被 A 的清理吞掉
        assert cfg.stream is False            # 调用方实例始终未被写入
        assert cfg.on_chunk is None
        assert cfg.on_stream_start is None


# ---------------------------------------------------------------------------
# legacy chat_completion — pipeline ctx 自动流式 + 降级语义
# ---------------------------------------------------------------------------


@pytest.fixture
def _ctx():
    token = set_current_llm_call_context(LLMCallContext(
        run_id="rc", project_dir="/pc", step_key="prd", step_index=3,
    ))
    yield
    reset_current_llm_call_context(token)


class TestChatCompletionStreaming:
    def test_no_context_pure_non_streaming(self, _bus):
        """无 ctx：emitter 为 None，旧 urllib 路径零行为变化。"""
        sub = EVENT_BUS.subscribe({"pipeline"})
        body = {
            "model": "deepseek-chat",
            "choices": [{"message": {"role": "assistant", "content": "legacy"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        mock_urlopen = mock.MagicMock(return_value=_json_ctx(body))
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                out = chat_completion("sys", "user", retries=1)
        assert out["content"] == "legacy"
        req_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert req_body["stream"] is False
        assert _bus(sub) == []  # 无任何 llm_delta 帧

    def test_context_streaming_success(self, _bus, _ctx):
        sub = EVENT_BUS.subscribe({"pipeline"})
        lines = _sse_lines(
            json.dumps({"choices": [{"delta": {"content": "架构"}}]}),
            json.dumps({"choices": [{"delta": {"content": "设计"}}]}),
        )
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                out = chat_completion("sys", "user", retries=1)
        assert out["content"] == "架构设计"
        req_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert req_body["stream"] is True
        assert req_body["stream_options"] == {"include_usage": True}
        # 事件序列: reset → chunk → chunk → done（min_chars=160 阈值下
        # 两段 delta 合并为一块; 这里用 close 终刷, 块数由 coalescer 决定，
        # 只断言首尾与内容完整）
        frames = [f.payload for f in _bus(sub)]
        assert frames[0]["reset"] is True and frames[0]["attempt"] == 1
        # reset 帧回填本次调用实际解析的 model/provider（env 未设时不为空）
        assert frames[0]["model"] == "deepseek-chat"
        assert frames[0]["provider"] == "deepseek"
        assert frames[-1]["done"] is True
        text = "".join(f["text"] for f in frames if not f["reset"] and not f["done"])
        assert text == "架构设计"

    def test_degrade_to_non_streaming_pushes_full_content(self, _bus, _ctx):
        """SSE 首帧前失败（端点不支持流）→ 非流式重试一次，整段补发。"""
        sub = EVENT_BUS.subscribe({"pipeline"})
        body = {
            "model": "deepseek-chat",
            "choices": [{"message": {"role": "assistant", "content": "full-answer"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        }
        mock_urlopen = mock.MagicMock(side_effect=[_http_error(400), _json_ctx(body)])
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with mock.patch("time.sleep"):
                    out = chat_completion("sys", "user", retries=1)
        assert out["content"] == "full-answer"
        assert mock_urlopen.call_count == 2
        # 第二跳（非流式）请求体 stream=False
        req_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert req_body["stream"] is False
        # 面板不至只收到空 reset/done：整段内容一次性补发
        frames = [f.payload for f in _bus(sub)]
        assert frames[0]["reset"] is True
        assert frames[-1]["done"] is True
        text = "".join(f["text"] for f in frames if not f["reset"] and not f["done"])
        assert text == "full-answer"

    def test_midstream_failure_raises(self, _bus, _ctx):
        """已收到 delta 后断流 → 诚实失败，绝不把半截输出当成功。"""
        lines = [b'data: {"choices":[{"delta":{"content":"half"}}]}\n']  # 无 [DONE]
        flaky = _flaky_sse_ctx(lines, _http_error(500))
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=flaky)):
                with mock.patch("time.sleep"):
                    with pytest.raises(RuntimeError):
                        chat_completion("sys", "user", retries=1)


class TestStreamLegacyChat:
    def _emitter(self):
        return StepStreamEmitter(
            run_id="r", project_dir="/p", step_key="k", step_index=0,
            min_chars=1, max_interval_s=999,
        )

    def test_success_returns_legacy_dict_and_closes(self, _bus):
        sub = EVENT_BUS.subscribe({"pipeline"})
        # 内容足够长，estimate_token_usage 的 char/4 启发式给出非零值
        long_text = "ok " * 20
        lines = _sse_lines(json.dumps({"choices": [{"delta": {"content": long_text}}]}))
        em = self._emitter()
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=_sse_ctx(lines))):
            out = _stream_legacy_chat(
                url="https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": "Bearer sk"},
                body={"model": "m", "messages": [], "stream": False},
                timeout=30, retries=1, model="deepseek-chat", emitter=em,
            )
        assert out is not None
        assert out["content"] == long_text
        assert out["model"] == "deepseek-chat"
        assert "usage" in out and out["usage"]["total_tokens"] > 0
        assert em.is_closed
        frames = [f.payload for f in _bus(sub)]
        assert frames[-1]["done"] is True

    def test_local_endpoint_omits_stream_options(self):
        lines = _sse_lines(json.dumps({"choices": [{"delta": {"content": "x"}}]}))
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        em = self._emitter()
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            out = _stream_legacy_chat(
                url="http://localhost:11434/v1/chat/completions",
                headers={}, body={"model": "m", "messages": []},
                timeout=30, retries=1, model="m", emitter=em,
            )
        req_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert req_body["stream"] is True
        assert "stream_options" not in req_body
        assert out["content"] == "x"

    def test_zero_delta_returns_none_for_degrade(self, _bus):
        """端点忽略 stream=true（零 delta）→ 返回 None 让调用方非流式重试。"""
        sub = EVENT_BUS.subscribe({"pipeline"})
        # 非 SSE 的普通 JSON 响应（很多端点会忽略 stream 字段直接回完整 JSON）
        body = {
            "choices": [{"message": {"role": "assistant", "content": "plain"},
                         "finish_reason": "stop"}],
        }
        em = self._emitter()
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=_json_ctx(body))):
            out = _stream_legacy_chat(
                url="https://api.deepseek.com/v1/chat/completions",
                headers={}, body={"model": "m", "messages": []},
                timeout=30, retries=1, model="m", emitter=em,
            )
        assert out is None
        assert not em.is_closed  # 保持打开，成功后由调用方补发


# ---------------------------------------------------------------------------
# OpenAIProvider opt-in streaming (P0-1: stream=true 曾必现 JSON 解析失败)
# ---------------------------------------------------------------------------


class TestOpenAIStreaming:
    def test_default_body_unchanged_no_stream_options(self):
        """GIVEN stream=False WHEN chat THEN body 与旧实现字面一致（回归守卫）。"""
        mock_urlopen = mock.MagicMock(return_value=_json_ctx({
            "model": "gpt-4o",
            "choices": [{"message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(OpenAIProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="gpt-4o", provider="openai", max_retries=1),
                ))
        assert resp.content == "ok"
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is False
        assert "stream_options" not in body  # 非流式绝不携带云端扩展字段

    def test_streaming_branch_sends_sse_and_invokes_callbacks(self):
        """P0-1 回归：body 带 stream=true 时必须走 SSE 流读而非 json.loads 整段。"""
        lines = _sse_lines(
            json.dumps({"choices": [{"delta": {"content": "产品"}}]}),
            json.dumps({"choices": [{"delta": {"content": "需求"}}]}),
            json.dumps({"choices": [], "usage": {
                "prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8}}),
        )
        chunks, started = [], []
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(OpenAIProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="gpt-4o", provider="openai", max_retries=1,
                                     stream=True, on_chunk=chunks.append,
                                     on_stream_start=lambda: started.append(True)),
                ))
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert started == [True]
        assert chunks == ["产品", "需求"]
        assert resp.content == "产品需求"
        assert resp.token_usage == {"prompt": 4, "completion": 4, "total": 8}

    def test_streaming_local_endpoint_omits_stream_options(self):
        lines = _sse_lines(json.dumps({"choices": [{"delta": {"content": "hi"}}]}))
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "ollama", "LLM_BASE_URL": "http://localhost:11434/v1",
        }):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                resp = asyncio.run(OpenAIProvider().chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="deepseek-r1:7b", provider="openai",
                                     max_retries=1, stream=True,
                                     on_chunk=lambda t: None),
                ))
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert "stream_options" not in body  # 自建端点未必支持
        assert resp.content == "hi"


# ---------------------------------------------------------------------------
# OllamaProvider native NDJSON streaming (P0-2: stream 曾写死 False)
# ---------------------------------------------------------------------------


def _ndjson_lines(*frames: dict) -> list[bytes]:
    """Build Ollama /api/chat stream=true NDJSON response lines."""
    return [(json.dumps(f) + "\n").encode() for f in frames]


def _ollama_frame(content: str, done: bool = False) -> dict:
    frame = {"model": "m", "message": {"role": "assistant", "content": content}}
    if done:
        frame["done"] = True
        frame["prompt_eval_count"] = 10
        frame["eval_count"] = 5
    else:
        frame["done"] = False
    return frame


class TestOllamaStreaming:
    def _provider(self) -> OllamaProvider:
        prov = OllamaProvider(base_url="http://127.0.0.1:11434")
        # 模型探测不打真实网络
        mock.patch.object(prov, "_list_models", return_value=["qwen2.5-coder:7b"]).start()
        return prov

    def test_default_body_unchanged_stream_false_with_num_ctx(self):
        """GIVEN stream=False WHEN chat THEN stream 字面 False 且 num_ctx 仍透传。"""
        mock_urlopen = mock.MagicMock(return_value=_json_ctx({
            "model": "qwen2.5-coder:7b",
            "message": {"role": "assistant", "content": "ok"},
            "done": True,
            "prompt_eval_count": 3,
            "eval_count": 2,
        }))
        prov = self._provider()
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            resp = asyncio.run(prov.chat(
                messages=[{"role": "user", "content": "hi"}],
                config=LLMConfig(model="qwen2.5-coder:7b", max_retries=1),
            ))
        assert resp.content == "ok"
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is False
        assert body["options"]["num_ctx"] == 32768  # 长输入防 exceed_context_size_error

    def test_streaming_chat_emits_deltas_and_uses_done_frame_usage(self):
        """P0-2 回归：stream=True 时逐行解析 NDJSON，delta 直推 on_chunk。"""
        lines = _ndjson_lines(
            _ollama_frame("Hel"),
            _ollama_frame("lo"),
            _ollama_frame("", done=True),
        )
        chunks, started = [], []
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        prov = self._provider()
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            resp = asyncio.run(prov.chat(
                messages=[{"role": "user", "content": "hi"}],
                config=LLMConfig(model="qwen2.5-coder:7b", max_retries=1,
                                 stream=True, on_chunk=chunks.append,
                                 on_stream_start=lambda: started.append(True)),
            ))
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert body["options"]["num_ctx"] == 32768  # 方案 A：num_ctx 不丢
        assert started == [True]          # on_stream_start 首 delta 前触发
        assert chunks == ["Hel", "lo"]    # 前端逐字增长
        assert resp.content == "Hello"
        assert resp.token_usage == {"prompt": 10, "completion": 5, "total": 15}
        assert resp.cost == 0.0

    def test_streaming_chat_sync_returns_legacy_dict(self):
        """chat_sync 与 chat 是同一条流式路径，别只改一个。"""
        lines = _ndjson_lines(
            _ollama_frame("本地"),
            _ollama_frame("模型", done=True),
        )
        chunks = []
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        prov = self._provider()
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            out = prov.chat_sync(
                messages=[{"role": "user", "content": "hi"}],
                config=LLMConfig(model="qwen2.5-coder:7b", max_retries=1,
                                 stream=True, on_chunk=chunks.append),
            )
        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["stream"] is True
        assert chunks == ["本地", "模型"]
        assert out["content"] == "本地模型"
        assert out["usage"] == {"prompt_tokens": 10, "completion_tokens": 5,
                                "total_tokens": 15}

    def test_midstream_failure_raises_not_silent(self):
        """已收 delta 后断流 → 诚实失败，绝不把半截输出当成功。"""
        lines = [json.dumps(_ollama_frame("partial")).encode()]
        flaky = _flaky_sse_ctx(lines, _http_error(500))
        prov = self._provider()
        with mock.patch("urllib.request.urlopen", mock.MagicMock(return_value=flaky)):
            with mock.patch("time.sleep"):
                with pytest.raises(RuntimeError, match="流式请求失败"):
                    asyncio.run(prov.chat(
                        messages=[{"role": "user", "content": "hi"}],
                        config=LLMConfig(model="qwen2.5-coder:7b", max_retries=2,
                                         stream=True, on_chunk=lambda t: None),
                    ))

    def test_zero_content_raises_for_fallback(self):
        """零内容（模型拒答/空输出）→ 抛错交由 provider_fallback 降级。"""
        lines = _ndjson_lines(_ollama_frame("", done=True))
        mock_urlopen = mock.MagicMock(return_value=_sse_ctx(lines))
        prov = self._provider()
        with mock.patch("urllib.request.urlopen", mock_urlopen):
            with pytest.raises(RuntimeError, match="流式请求失败"):
                asyncio.run(prov.chat(
                    messages=[{"role": "user", "content": "hi"}],
                    config=LLMConfig(model="qwen2.5-coder:7b", max_retries=1,
                                     stream=True, on_chunk=lambda t: None),
                ))


# ---------------------------------------------------------------------------
# chat_completion failure path — emitter 兜底关闭 (P1-3: 失败曾让前端永久转圈)
# ---------------------------------------------------------------------------


class TestChatCompletionEmitterClose:
    def test_provider_error_still_closes_emitter_with_done_frame(self, _bus, _ctx):
        """P1-3 回归：Provider 抛错时前端仍收到 done 帧，「流式输出中」不残留。"""
        sub = EVENT_BUS.subscribe({"pipeline"})
        mock_urlopen = mock.MagicMock(side_effect=_http_error(500))
        with mock.patch.dict(os.environ, {
            "LLM_API_KEY": "sk-test",
            "YULEOSH_LLM_UNIFIED": "",
            "YULEOSH_LLM_LOCAL_FALLBACK": "0",  # 关掉本地兜底，让原始错误直接抛出
        }):
            with mock.patch("urllib.request.urlopen", mock_urlopen):
                with mock.patch("time.sleep"):
                    with pytest.raises(RuntimeError, match="LLM request failed"):
                        chat_completion("sys", "user", retries=1)
        frames = [f.payload for f in _bus(sub) if f.payload.get("kind") == "llm_delta"]
        assert frames[0]["reset"] is True   # 流式尝试已发出 reset
        assert frames[-1]["done"] is True   # 失败路径兜底 close → done 帧
        # 除 reset/done 外无残留 chunk 帧（首帧前即失败，无 delta）
        assert all(f["reset"] or f["done"] for f in frames)
