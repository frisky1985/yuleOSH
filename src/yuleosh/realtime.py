# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH 进程内实时事件总线（single-process pub/sub）.

背景：
  yuleOSH 后端在 /dashboard 是 ``ThreadingHTTPServer``（单进程多线程）。
  多 worker 部署前无需 redis/kafka 这种外部 broker，进程内 ``queue.Queue``
  + RLock 已经能保证线程安全 + 单进程订阅扇出。本模块把这个能力封闭成
  通用事件总线，供 SSE 端点（``GET /api/v1/events/stream``）和慢任务
  发射点（pipeline / evidence / gap / coverage / misra）共用。

不变量：
  * 事件按 ``id`` 单调递增；订阅者可带 ``since_id`` 重连补齐（at-least-once
    in-process: 重叠事件会重复派发，订阅端需自行 dedup key）。
  * ``publish`` 永不抛出 —— 业务链路上事件总线是 best-effort 装饰层，主流程
    不能因订阅异常中断（订阅 callback 抛错会被 ``logger.debug`` 捕获）。
  * ``shutdown=False`` 时订阅队列容量默认 1024；超出时被丢掉最早的、不会
    阻塞 publisher。订阅者跟不上时，丢失事件由下次 reconnect 用 ``since_id``
    从持久层重放（未来扩到 checkpoint_state / pipeline_runs 表读历史）。

线程模型：
  * 单进程内存（``threading.RLock`` 守护所有 list/set/queue mutation）。
  * 跨 SSE 流的心跳 / keep-alive 由订阅端驱动（每 N 秒一帧 ": keep-alive"），
    发布端只关心 ``_next_id`` 自增与广播。
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Any, Callable, Iterable

log = logging.getLogger("yuleosh.realtime")


@dataclass
class RealtimeEvent:
    """单条事件。

    ``id`` 在总线内单调递增；``topic`` 用于订阅过滤 + 前端分类；``payload``
    是业务自由扩展字段（建议保持 JSON-friendly）。
    """
    id: int
    topic: str
    ts: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_sse_frame(self) -> str:
        """渲染成 ``data: {...}\\n\\n`` SSE 帧（事件用 ``id`` + ``event`` 字段便于前端溯源）。"""
        import json
        body = {
            "id": self.id,
            "ts": self.ts,
            "topic": self.topic,
            "payload": self.payload,
        }
        return f"id: {self.id}\nevent: {self.topic}\ndata: {json.dumps(body, ensure_ascii=False, default=str)}\n\n"


class _Subscription:
    """单个 SSE 流的订阅句柄（线程间通过 Queue 跨线程派发事件）。

    持有：
      * ``queue``：订阅者循环阻塞读；publisher 写入。
      * ``topics``：白名单（``None`` 表示订阅所有 topic）。
      * ``alive``：订阅者主动 disconnect 时置 False，publisher 据此跳过。
    """

    __slots__ = ("queue", "topics", "alive", "created_at")

    def __init__(self, topics: set[str] | None, queue_maxsize: int = 1024):
        self.queue: Queue = Queue(maxsize=queue_maxsize)
        self.topics: set[str] | None = topics
        self.alive: bool = True
        self.created_at: float = time.time()


class EventBus:
    """进程内事件总线（单例见 ``EVENT_BUS``）。

    典型用法：

        bus = EVENT_BUS
        sub = bus.subscribe(topics={"pipeline"})
        ...
        bus.publish("pipeline", {"kind": "stage_start", ...})
        ...
        for ev in bus.iter_events(sub):
            handler.send_sse(ev)   # 阻塞直到新事件 / 心跳 / 订阅终止
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._next_id: int = 1
        # 缓存最近 N 条事件（默认 2000），订阅 reconnect 带 since_id 可补齐。
        self._history: deque[RealtimeEvent] = deque(maxlen=2000)
        self._subs: set[_Subscription] = set()

    # ── publish 路径（业务侧调用） ──────────────────────────────

    def publish(self, topic: str, payload: dict | None = None) -> int | None:
        """发布事件到所有匹配订阅者（best-effort，失败仅 debug）。

        Returns:
            新事件的 ``id``，无人订阅时仍返回 id（保证 since_id 可用）。
        """
        evt = self._make_event(topic, payload or {})
        with self._lock:
            self._history.append(evt)
            subs = list(self._subs)
        # 在锁外派发，避免慢订阅阻塞 publisher。
        for sub in subs:
            self._enqueue(sub, evt)
        log.debug("realtime.publish topic=%s id=%s subs=%d", topic, evt.id, len(subs))
        return evt.id

    def publish_async(self, topic: str, payload: dict | None = None) -> None:
        """Fire-and-forget：异常吞掉（业务线程调用方不应感知事件层失败）。"""
        try:
            self.publish(topic, payload)
        except Exception as e:  # noqa: BLE001 — 故意吞掉，事件层不影响主流程
            log.debug("realtime.publish_async swallowed: %s", e)

    # ── subscribe 路径（SSE handler 调用） ──────────────────────

    def subscribe(self, topics: Iterable[str] | None = None, queue_maxsize: int = 1024) -> _Subscription:
        """建立订阅。``topics=None`` 表示订阅所有 topic。"""
        sub = _Subscription(set(topics) if topics is not None else None, queue_maxsize)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscription) -> None:
        """解除订阅并标记 ``alive=False``（publisher 立即跳过）。"""
        sub.alive = False
        with self._lock:
            self._subs.discard(sub)
        # 推一个 sentinel，便于订阅者循环立刻跳出。
        try:
            sub.queue.put_nowait(None)
        except Exception:  # noqa: BLE001 — 队列满不影响 unsubscribe
            pass

    def replay_history(self, sub: _Subscription, since_id: int = 0) -> int:
        """把 ``id > since_id`` 的缓存历史入队（订阅 reconnect 重放）。"""
        sent = 0
        with self._lock:
            events = [e for e in self._history if e.id > since_id]
        for evt in events:
            if self._enqueue(sub, evt):
                sent += 1
            else:
                break
        return sent

    # ── helpers ───────────────────────────────────────────────

    def _make_event(self, topic: str, payload: dict) -> RealtimeEvent:
        with self._lock:
            eid = self._next_id
            self._next_id += 1
        return RealtimeEvent(id=eid, topic=str(topic), ts=time.time(), payload=dict(payload))

    def _enqueue(self, sub: _Subscription, evt: RealtimeEvent) -> bool:
        if not sub.alive:
            return False
        if sub.topics is not None and evt.topic not in sub.topics:
            return True  # 跳过但不视为失败（订阅端按 topic 过滤是常态）
        try:
            sub.queue.put_nowait(evt)
            return True
        except Exception:  # noqa: BLE001 — 队列满视为订阅者跟不上，丢该条
            log.debug("subscription queue full: dropping event id=%s topic=%s", evt.id, evt.topic)
            return False

    # ── 诊断 / 测试 ──────────────────────────────────────────

    def stats(self) -> dict:
        """返回总线状态（健康卡片 / 测试断言使用）。"""
        with self._lock:
            return {
                "subs": len(self._subs),
                "history_size": len(self._history),
                "next_id": self._next_id,
            }


# 进程级单例（``ThreadingHTTPServer`` 单进程，多线程安全）。
EVENT_BUS = EventBus()


# ─── 当前调用上下文（Stage-6, 2026-09-05） ─────────────────────────────────
# LLMClient 等低层模块**不感知** pipeline run_id, 但需要把 llm_call 事件
# 关联到具体的 run + step 以便前端按 run 累计 token。解决: 编排器在跑某
# step 时把上下文塞进 ContextVar, LLMClient 读 ContextVar 并 emit 即可。
# ContextVar 线程安全 + 异步安全 (asyncio task 内独立); step handler 嵌套
# 调用不串扰。
_LLMCallContext = contextvars.ContextVar(
    "yuleosh_llm_call_ctx",
    default=None,  # type: ignore[arg-type]
)


@dataclass
class LLMCallContext:
    """当前 pipeline step 的 LLM 调用上下文 (低层模块用)."""

    run_id: str
    project_dir: str
    step_key: str = ""
    step_index: int = -1


def set_current_llm_call_context(ctx: LLMCallContext | None) -> object:
    """设置当前 LLM 调用上下文; 返回 token 用于 reset。"""
    return _LLMCallContext.set(ctx)


def reset_current_llm_call_context(token: object) -> None:
    """还原上下文 (与 set_current_llm_call_context 配对)。"""
    _LLMCallContext.reset(token)  # type: ignore[arg-type]


def get_current_llm_call_context() -> LLMCallContext | None:
    """读取当前 LLM 调用上下文; 没有时返回 None (低层调用不应该 emit)。"""
    return _LLMCallContext.get()


# ─── 便捷发射器（业务代码直接 ``emit_pipeline_stage_start(...)``） ─────────


def emit_pipeline_stage_start(*, run_id: str, project_dir: str, step_index: int,
                              step_key: str, step_title: str, agent: str = "") -> int | None:
    """``topic=pipeline`` + ``kind=stage_start`` —— 某 step 进入。"""
    return EVENT_BUS.publish("pipeline", {
        "kind": "stage_start",
        "run_id": run_id,
        "project_dir": project_dir,
        "step_index": step_index,
        "step_key": step_key,
        "step_title": step_title,
        "agent": agent,
    })


def emit_pipeline_stage_end(*, run_id: str, project_dir: str, step_index: int,
                            step_key: str, step_title: str, status: str,
                            duration_ms: int | None = None) -> int | None:
    """``topic=pipeline`` + ``kind=stage_end`` —— 某 step 退出。"""
    return EVENT_BUS.publish("pipeline", {
        "kind": "stage_end",
        "run_id": run_id,
        "project_dir": project_dir,
        "step_index": step_index,
        "step_key": step_key,
        "step_title": step_title,
        "status": status,
        "duration_ms": duration_ms,
    })


def emit_pipeline_file_produced(*, run_id: str, project_dir: str, file_path: str,
                                category: str = "aspice_md", size_bytes: int = 0) -> int | None:
    """``topic=pipeline`` + ``kind=file_produced`` —— 文档证据落盘。"""
    return EVENT_BUS.publish("pipeline", {
        "kind": "file_produced",
        "run_id": run_id,
        "project_dir": project_dir,
        "file_path": file_path,
        "category": category,
        "size_bytes": size_bytes,
    })


def emit_pipeline_run_done(*, run_id: str, project_dir: str, status: str,
                           summary: dict | None = None) -> int | None:
    """``topic=pipeline`` + ``kind=run_done`` —— run 终态。"""
    return EVENT_BUS.publish("pipeline", {
        "kind": "run_done",
        "run_id": run_id,
        "project_dir": project_dir,
        "status": status,
        "summary": summary or {},
    })


def emit_pipeline_checkpoint(*, run_id: str, project_dir: str, status: str,
                            progress_pct: float = 0.0) -> int | None:
    """``topic=pipeline`` + ``kind=checkpoint`` —— 增量回写看板（含 rerun/retry）。"""
    return EVENT_BUS.publish("pipeline", {
        "kind": "checkpoint",
        "run_id": run_id,
        "project_dir": project_dir,
        "status": status,
        "progress_pct": progress_pct,
    })


def emit_pipeline_llm_call(*, run_id: str, project_dir: str,
                            step_key: str, step_index: int,
                            model: str, provider: str,
                            prompt_tokens: int, completion_tokens: int,
                            cost_usd: float = 0.0,
                            duration_ms: int = 0) -> int | None:
    """``topic=pipeline`` + ``kind=llm_call`` —— 一次 LLM 调用的 token 用量。

    Stage-6 (2026-09-05): 让前端实时看到 LLM token 用量与累计成本, 便于
    工程师在长跑阶段里观察「卡在哪个 step / token 花了多少」。
    """
    return EVENT_BUS.publish("pipeline", {
        "kind": "llm_call",
        "run_id": run_id,
        "project_dir": project_dir,
        "step_key": step_key,
        "step_index": step_index,
        "model": model,
        "provider": provider,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
    })


__all__ = [
    "RealtimeEvent",
    "EventBus",
    "EVENT_BUS",
    "emit_pipeline_stage_start",
    "emit_pipeline_stage_end",
    "emit_pipeline_file_produced",
    "emit_pipeline_run_done",
    "emit_pipeline_checkpoint",
    "emit_pipeline_llm_call",
]
