"""Tests for the in-process realtime event bus (yuleosh.realtime).

These tests exercise the publish/subscribe handshake, the SSE frame
rendering, and the at-least-once replay-by-id reconnection helper.

The bus is the spine of the engineer-lifecycle live feed
(/api/v1/events/stream), so regressions here break the dashboard
left-rail badges and the per-step stage board live updates.
"""

import json
import time

import pytest

from yuleosh.realtime import (
    EVENT_BUS,
    EventBus,
    LLMCallContext,
    RealtimeEvent,
    emit_pipeline_checkpoint,
    emit_pipeline_file_produced,
    emit_pipeline_llm_call,
    emit_pipeline_run_done,
    emit_pipeline_stage_end,
    emit_pipeline_stage_start,
    get_current_llm_call_context,
    reset_current_llm_call_context,
    set_current_llm_call_context,
)


@pytest.fixture
def _bus():
    """Each test gets a fresh EventBus (process-global state is reset)."""
    # Avoid cross-test leakage from EVENT_BUS.publish() during a previous test.
    EVENT_BUS._subs.clear()
    EVENT_BUS._history.clear()
    EVENT_BUS._next_id = 1
    return EVENT_BUS


class TestEventBusBasics:
    """Publish/subscribe ring + history + replay handshake."""

    def test_publish_returns_monotonic_id(self, _bus):
        a = _bus.publish("pipeline", {"k": 1})
        b = _bus.publish("pipeline", {"k": 2})
        assert a is not None and b is not None
        assert b > a

    def test_history_increments_until_maxlen(self, _bus):
        for i in range(50):
            _bus.publish("topic", {"i": i})
        # bus retains up to its deque maxlen (default 2000)
        assert len(_bus._history) == 50
        assert _bus.stats()["next_id"] == 51

    def test_subscribe_with_topic_filter_receives_matching(self, _bus):
        sub = _bus.subscribe({"pipeline"})
        _bus.publish("pipeline", {"a": 1})
        _bus.publish("coverage", {"b": 2})
        _bus.publish("pipeline", {"c": 3})
        received = []
        while not sub.queue.empty():
            received.append(sub.queue.get_nowait())
        assert len(received) == 2
        assert all(e.topic == "pipeline" for e in received)

    def test_subscribe_with_no_topics_receives_all(self, _bus):
        sub = _bus.subscribe()  # topics=None → all
        _bus.publish("pipeline", {"a": 1})
        _bus.publish("evidence", {"b": 2})
        assert sub.queue.qsize() == 2

    def test_unsubscribe_marks_inactive_and_clears(self, _bus):
        sub = _bus.subscribe({"pipeline"})
        assert len(_bus._subs) == 1
        _bus.unsubscribe(sub)
        assert len(_bus._subs) == 0
        assert sub.alive is False

    def test_publish_async_swallowed_exception(self, _bus, monkeypatch):
        """publisher 异常不影响业务线程 (best-effort)."""
        def boom(*a, **kw): raise RuntimeError("event-bus down")
        monkeypatch.setattr(_bus, "publish", boom)
        # should not raise
        _bus.publish_async("pipeline", {"x": 1})


class TestSseFrameRendering:
    """``RealtimeEvent.to_sse_frame`` shape — front-end EventSource contract."""

    def test_frame_format(self):
        e = RealtimeEvent(id=42, topic="pipeline", ts=123.456,
                           payload={"kind": "stage_start", "step_index": 3})
        frame = e.to_sse_frame()
        # SSE convention: id:, event:, data: lines, separated by blank line
        assert frame.startswith("id: 42\nevent: pipeline\ndata: ")
        assert frame.endswith("\n\n")
        body = frame.split("data: ", 1)[1].split("\n\n", 1)[0]
        parsed = json.loads(body)
        assert parsed["id"] == 42
        assert parsed["topic"] == "pipeline"
        assert parsed["payload"]["kind"] == "stage_start"

    def test_frame_escapes_utf8(self):
        e = RealtimeEvent(id=1, topic="t", ts=0,
                           payload={"text": "项目需求 / Spec"})
        body = e.to_sse_frame().split("data: ", 1)[1].split("\n\n", 1)[0]
        assert "项目需求" in body


class TestReplay:
    """Reconnect with ``since_id`` should re-deliver missed events."""

    def test_replay_returns_only_id_greater_than_since(self, _bus):
        # populate history
        for i in range(10):
            _bus.publish("pipeline", {"i": i})
        # subscribe + ask for id > 5
        sub = _bus.subscribe({"pipeline"})
        sent = _bus.replay_history(sub, since_id=5)
        # 10 events published → ids 1..10; ids > 5 are 6,7,8,9,10 → 5 entries
        assert sent == 5
        replayed = [sub.queue.get_nowait() for _ in range(5)]
        assert [e.id for e in replayed] == [6, 7, 8, 9, 10]


class TestEmitHelpers:
    """The five top-level emit_* helpers produce well-formed payloads."""

    def test_emit_stage_start(self):
        eid = emit_pipeline_stage_start(
            run_id="r1", project_dir="/p", step_index=2,
            step_key="prd", step_title="产品需求", agent="Hermes",
        )
        assert eid is not None
        evt = EVENT_BUS._history[-1]
        assert evt.topic == "pipeline"
        assert evt.payload["kind"] == "stage_start"
        assert evt.payload["step_key"] == "prd"

    def test_emit_file_produced(self):
        emit_pipeline_file_produced(
            run_id="r1", project_dir="/p",
            file_path="architecture.md", category="md", size_bytes=1024,
        )
        evt = EVENT_BUS._history[-1]
        assert evt.payload["kind"] == "file_produced"
        assert evt.payload["file_path"] == "architecture.md"

    def test_emit_run_done(self):
        emit_pipeline_run_done(run_id="r1", project_dir="/p",
                                status="completed", summary={"x": 1})
        evt = EVENT_BUS._history[-1]
        assert evt.payload["kind"] == "run_done"

    def test_emit_checkpoint(self):
        emit_pipeline_checkpoint(run_id="r1", project_dir="/p",
                                  status="completed", progress_pct=100.0)
        evt = EVENT_BUS._history[-1]
        assert evt.payload["kind"] == "checkpoint"
        assert evt.payload["progress_pct"] == 100.0

    def test_emit_stage_end(self):
        emit_pipeline_stage_end(run_id="r1", project_dir="/p",
                                 step_index=3, step_key="x", step_title="t",
                                 status="completed", duration_ms=1200)
        evt = EVENT_BUS._history[-1]
        assert evt.payload["kind"] == "stage_end"
        assert evt.payload["duration_ms"] == 1200

    def test_emit_llm_call(self):
        # Stage-6 (2026-09-05): 单次 LLM 调用的 token 用量
        eid = emit_pipeline_llm_call(
            run_id="r1", project_dir="/p",
            step_key="prd", step_index=2,
            model="deepseek-v4", provider="deepseek",
            prompt_tokens=128, completion_tokens=512,
            cost_usd=0.005, duration_ms=2300,
        )
        assert eid is not None
        evt = EVENT_BUS._history[-1]
        assert evt.topic == "pipeline"
        assert evt.payload["kind"] == "llm_call"
        assert evt.payload["total_tokens"] == 640  # prompt + completion
        assert evt.payload["step_key"] == "prd"
        assert evt.payload["cost_usd"] == 0.005


class TestLLMCallContext:
    """Stage-6 (2026-09-05): ContextVar 承载的「当前 step 的 LLM 调用上下文」。

    编排器在跑某 step 前 set, finally 里 reset; 低层 LLMClient 读它决定
    要不要 emit pipeline.llm_call 以及关联到哪个 run/step。默认 None 保证
    非 pipeline 场景（脚本 / CLI / 单测）不污染 SSE 流。
    """

    def test_default_is_none(self):
        assert get_current_llm_call_context() is None

    def test_set_and_reset(self):
        token = set_current_llm_call_context(LLMCallContext(
            run_id="r1", project_dir="/p", step_key="prd", step_index=2,
        ))
        try:
            ctx = get_current_llm_call_context()
            assert ctx is not None
            assert ctx.run_id == "r1"
            assert ctx.project_dir == "/p"
            assert ctx.step_key == "prd"
            assert ctx.step_index == 2
        finally:
            reset_current_llm_call_context(token)
        assert get_current_llm_call_context() is None

    def test_thread_isolation(self):
        """并行组的 worker 线程各自独立, 互不串扰。"""
        import threading

        seen: dict[str, object] = {}

        def worker(name: str, rid: str) -> None:
            token = set_current_llm_call_context(LLMCallContext(
                run_id=rid, project_dir=f"/{name}", step_key=name, step_index=1,
            ))
            try:
                time.sleep(0.02)
                ctx = get_current_llm_call_context()
                seen[name] = None if ctx is None else ctx.run_id
            finally:
                reset_current_llm_call_context(token)

        ts = [
            threading.Thread(target=worker, args=("a", "run-a")),
            threading.Thread(target=worker, args=("b", "run-b")),
        ]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert seen == {"a": "run-a", "b": "run-b"}
        # 主线程不受子线程 set 的影响
        assert get_current_llm_call_context() is None
