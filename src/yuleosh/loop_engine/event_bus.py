#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH EventBus v2 — 系统级事件总线 (LE-001)。

扩展 KG events.py 的 EventBus，提供:
  - 事件类型枚举 (LoopEventType)
  - Pub/Sub + 路由 + 优先级队列
  - 去重 (dedup) · 持久化到 Store
  - 异步处理 + 重试机制

向后兼容：
  - 不修改 yuleosh.knowledge_graph.events
  - kg_events 仍可作为轻量级 KG 事件总线使用
  - loop_bus 是独立的系统级事件总线

Usage:
    from yuleosh.loop_engine.event_bus import loop_bus, LoopEventType

    # Subscribe
    loop_bus.on(LoopEventType.CI_FAILURE, my_handler)

    # Emit
    loop_bus.emit(LoopEventType.CI_FAILURE, source="ci.runner", data={
        "test_name": "test_brake_light",
        "error": "AssertionError: expected True, got False",
    })
"""

import enum
import hashlib
import json
import logging
import queue
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

log = logging.getLogger("yuleosh.loop_engine.event_bus")


# ═══════════════════════════════════════════════════════════════════════
# Event Types
# ═══════════════════════════════════════════════════════════════════════

class LoopEventType(str, enum.Enum):
    """系统级 Loop 事件类型枚举。

    覆盖 LE-001 到 LE-006 定义的所有事件源。
    """
    CI_FAILURE = "ci.failure"
    """CI 测试失败事件 — 触发 Loop 1 (Defect→Requirement)。"""

    REVIEW_FINDING = "review.finding"
    """代码审查发现 — 触发需求/设计的 re-review。"""

    KPI_BREACH = "kpi.breach"
    """KPI 阈值告警 — 触发 Loop 3 (KPI→Improvement)。"""

    FIELD_DEFECT = "field.defect"
    """现场缺陷报告 — 触发 Loop 2 (Field→FMEA)。"""

    KG_LOW_CONFIDENCE = "kg.low_confidence"
    """KG 低置信度边缘 — 触发 Loop 4 (KG Self-Evolution)。"""

    TEST_RESULT = "test.result"
    """通用测试结果事件 — 用于 CI 报告聚合。"""

    SPEC_CHANGE = "spec.change"
    """需求规格变更事件 — 用于影响分析链传播。"""


# ═══════════════════════════════════════════════════════════════════════
# Event Data Model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LoopEvent:
    """系统级事件数据模型。

    Attributes:
        event_type: 事件类型 (LoopEventType 成员)。
        source: 事件来源描述 (e.g. "ci.runner", "kg.reporter")。
        data: 事件载荷字典。
        priority: 优先级 (0=最高, 越大越低), 默认 5。
        dedup_key: 去重键 (None 则自动基于事件类型+数据生成)。
        event_id: 唯一事件 ID (自动生成)。
        timestamp: 创建时间戳。
        retry_count: 当前重试次数。
        max_retries: 最大重试次数。
    """
    event_type: LoopEventType
    source: str = "system"
    data: dict = field(default_factory=dict)
    priority: int = 5
    dedup_key: str | None = None
    event_id: str = ""
    timestamp: str = ""
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.dedup_key is None:
            raw = f"{self.event_type.value}:{json.dumps(self.data, sort_keys=True)}"
            self.dedup_key = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "data": self.data,
            "priority": self.priority,
            "dedup_key": self.dedup_key,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoopEvent":
        return cls(
            event_type=LoopEventType(d["event_type"]),
            source=d.get("source", "system"),
            data=d.get("data", {}),
            priority=d.get("priority", 5),
            dedup_key=d.get("dedup_key"),
            event_id=d.get("event_id", ""),
            timestamp=d.get("timestamp", ""),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
        )

    def __repr__(self):
        return (f"<LoopEvent {self.event_type.value} "
                f"id={self.event_id[:8]} "
                f"prio={self.priority} "
                f"retry={self.retry_count}>")


# ═══════════════════════════════════════════════════════════════════════
# Subscription
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Subscription:
    """订阅记录。"""
    id: str
    event_type: LoopEventType
    callback: Callable[[LoopEvent], Any]
    priority_filter: Optional[int] = None  # None = accept all
    one_shot: bool = False
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.id:
            self.id = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════
# System EventBus
# ═══════════════════════════════════════════════════════════════════════

class SystemEventBus:
    """系统级事件总线 (LE-001)。

    功能:
        - Pub/Sub: on() / off() / emit()
        - 优先级队列: 按 priority 排序执行
        - 去重: 基于 dedup_key，可配置去重窗口
        - 持久化: persist_to_store() 将事件持久化
        - 异步处理: 线程池后台执行
        - 重试: 失败自动重试 (可达 max_retries 次)
        - 统计: stats() 查看事件处理统计

    线程安全: 全部操作持有 threading.RLock。
    """

    def __init__(self, dedup_window_seconds: float = 300.0,
                 store=None, max_workers: int = 4):
        self._lock = threading.RLock()
        self._lock_emit = threading.Lock()
        self._subscriptions: dict[LoopEventType, list[Subscription]] = defaultdict(list)
        self._callbacks: dict[str, Callable] = {}  # sub_id -> callback
        self._history: list[LoopEvent] = []
        self._max_history = 2000
        self._dedup_window = dedup_window_seconds
        self._dedup_seen: dict[str, float] = {}  # dedup_key -> timestamp
        self._stats: dict = {
            "total_emitted": 0,
            "total_handled": 0,
            "total_failed": 0,
            "total_retried": 0,
            "total_deduped": 0,
            "by_type": defaultdict(int),
        }
        self._store = store  # 可选的持久化后端
        self._worker_thread: Optional[threading.Thread] = None
        self._work_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = False
        self._max_workers = max_workers

    # ── Subscription ──────────────────────────────────────────────────

    def on(self, event_type: LoopEventType,
           callback: Callable[[LoopEvent], Any],
           priority_filter: Optional[int] = None,
           one_shot: bool = False) -> str:
        """订阅事件类型。

        Args:
            event_type: 事件类型。
            callback: 处理函数, 接收 LoopEvent 参数。
            priority_filter: 仅处理 priority <= 此值的事件 (None=全部)。
            one_shot: 仅处理一次后自动取消。

        Returns:
            订阅 ID (可用于 off())。
        """
        if not callable(callback):
            raise TypeError("callback must be callable")

        sub = Subscription(
            id=str(uuid.uuid4()),
            event_type=event_type,
            callback=callback,
            priority_filter=priority_filter,
            one_shot=one_shot,
        )
        with self._lock:
            self._subscriptions[event_type].append(sub)
            self._callbacks[sub.id] = callback

        log.debug("EventBus: subscribed '%s' -> %s (filter=%s, once=%s)",
                  event_type.value, sub.id[:8], priority_filter, one_shot)
        return sub.id

    def off(self, sub_id: str):
        """取消订阅。"""
        with self._lock:
            for event_type, subs in self._subscriptions.items():
                self._subscriptions[event_type] = [s for s in subs if s.id != sub_id]
            self._callbacks.pop(sub_id, None)
        log.debug("EventBus: unsubscribed %s", sub_id[:8])

    def clear(self):
        """清除所有订阅。"""
        with self._lock:
            self._subscriptions.clear()
            self._callbacks.clear()

    # ── Emit ──────────────────────────────────────────────────────────

    def emit(self, event_type: LoopEventType,
             source: str = "system",
             data: Optional[dict] = None,
             priority: int = 5,
             dedup_key: Optional[str] = None) -> LoopEvent:
        """发布事件到总线。

        步骤:
          1. 构造 LoopEvent
          2. 去重检查 (可选)
          3. 持久化到 Store (如已配置)
          4. 查找匹配订阅
          5. 按优先级排序执行
          6. 记录历史
          7. 返回事件

        Args:
            event_type: 事件类型。
            source: 来源描述。
            data: 事件载荷。
            priority: 优先级 (0=最高)。
            dedup_key: 自定义去重键 (None=自动生成)。

        Returns:
            已完成的事件对象。
        """
        event = LoopEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=priority,
            dedup_key=dedup_key,
        )

        with self._lock:
            self._stats["total_emitted"] += 1
            self._stats["by_type"][event_type.value] += 1

        # ── 去重 ──
        if self._is_duplicate(event):
            with self._lock:
                self._stats["total_deduped"] += 1
            log.debug("EventBus: deduped %s", event.dedup_key)
            return event

        # ── 持久化 ──
        if self._store is not None:
            self._persist_event(event)

        # ── 查找匹配订阅 ──
        with self._lock:
            matching = list(self._subscriptions.get(event_type, []))
            matching += list(self._subscriptions.get(
                LoopEventType.TEST_RESULT, []))  # wildcard-like

        # 只匹配满足 priority_filter 的订阅
        matching = [s for s in matching
                    if s.priority_filter is None
                    or event.priority <= s.priority_filter]

        if not matching:
            log.debug("EventBus: '%s' emitted (no matching subscribers, %d subs total)",
                      event_type.value, sum(len(v) for v in self._subscriptions.values()))
            self._append_history(event)
            return event

        # ── 按优先级排序执行 ──
        matching.sort(key=lambda s: (s.priority_filter or 0))

        for sub in matching:
            try:
                sub.callback(event)
                with self._lock:
                    self._stats["total_handled"] += 1
            except Exception as e:
                with self._lock:
                    self._stats["total_failed"] += 1
                # 自动重试
                if event.retry_count < event.max_retries:
                    event.retry_count += 1
                    with self._lock:
                        self._stats["total_retried"] += 1
                    log.warning("EventBus: callback error for '%s' (retry %d/%d): %s",
                                event_type.value, event.retry_count,
                                event.max_retries, e)
                    # 异步重试
                    self._schedule_retry(event, sub)
                else:
                    log.error("EventBus: callback exhausted for '%s': %s",
                              event_type.value, e)

            # one-shot: 自动取消
            if sub.one_shot:
                self.off(sub.id)

        self._append_history(event)
        return event

    def emit_async(self, event_type: LoopEventType,
                   source: str = "system",
                   data: Optional[dict] = None,
                   priority: int = 5,
                   dedup_key: Optional[str] = None):
        """异步发布事件（后台线程处理）。"""
        event = LoopEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=priority,
            dedup_key=dedup_key,
        )
        self._work_queue.put((event.priority, event))

        # 启动 worker 线程（如果需要）
        if not self._running:
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()

    def _worker_loop(self):
        """后台 worker 循环 — 处理异步事件队列。"""
        while self._running:
            try:
                _, event = self._work_queue.get(timeout=1.0)
                self.emit(event.event_type, source=event.source,
                          data=event.data, priority=event.priority,
                          dedup_key=event.dedup_key)
            except queue.Empty:
                continue
            except Exception:
                log.exception("EventBus: worker error")
        self._running = False

    # ── 去重 ─────────────────────────────────────────────────────────

    def _is_duplicate(self, event: LoopEvent) -> bool:
        """检查事件是否在去重窗口内已存在。"""
        now = time.time()
        with self._lock:
            seen = self._dedup_seen.get(event.dedup_key, 0.0)
            if seen > 0 and (now - seen) < self._dedup_window:
                return True
            self._dedup_seen[event.dedup_key] = now
            # 清理过期键
            stale = [k for k, v in self._dedup_seen.items()
                     if (now - v) > self._dedup_window * 2]
            for k in stale:
                del self._dedup_seen[k]
        return False

    # ── 持久化 ────────────────────────────────────────────────────────

    def set_store(self, store):
        """设置持久化后端。"""
        self._store = store

    def _persist_event(self, event: LoopEvent):
        """将事件持久化到 Store。"""
        try:
            self._store.insert("loop_events", {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "source": event.source,
                "data": json.dumps(event.data),
                "priority": event.priority,
                "dedup_key": event.dedup_key,
                "timestamp": event.timestamp,
                "retry_count": event.retry_count,
                "max_retries": event.max_retries,
            })
        except Exception as e:
            log.warning("EventBus: persist error: %s", e)

    # ── 重试 ─────────────────────────────────────────────────────────

    def _schedule_retry(self, event: LoopEvent, sub: Subscription):
        """安排重试 (延迟 1s)。"""
        def retry():
            time.sleep(1)
            try:
                sub.callback(event)
                with self._lock:
                    self._stats["total_handled"] += 1
            except Exception as e2:
                with self._lock:
                    self._stats["total_failed"] += 1
                if event.retry_count < event.max_retries:
                    event.retry_count += 1
                    with self._lock:
                        self._stats["total_retried"] += 1
                    self._schedule_retry(event, sub)
                else:
                    log.error("EventBus: retry exhausted for '%s' on retry %d: %s",
                              event.event_type.value, event.retry_count, e2)

        t = threading.Thread(target=retry, daemon=True)
        t.start()

    # ── 历史 ──────────────────────────────────────────────────────────

    def _append_history(self, event: LoopEvent):
        """追加事件到历史记录。"""
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def history(self, event_type: Optional[LoopEventType] = None,
                limit: int = 50) -> list[dict]:
        """返回事件历史。"""
        with self._lock:
            if event_type:
                filtered = [e for e in self._history
                            if e.event_type == event_type]
            else:
                filtered = list(self._history)
        return [e.to_dict() for e in filtered[-limit:]]

    def clear_history(self):
        """清除事件历史。"""
        with self._lock:
            self._history.clear()

    # ── 状态查询 ──────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回事件总线统计信息。"""
        with self._lock:
            return dict(self._stats)

    def active_subscriptions(self) -> dict[str, int]:
        """返回活跃订阅计数 (按事件类型)。"""
        with self._lock:
            return {k.value: len(v) for k, v in self._subscriptions.items()}


# ── 全局单例 ──────────────────────────────────────────────────────────

loop_bus = SystemEventBus()
"""全局 Loop 系统事件总线实例。"""
