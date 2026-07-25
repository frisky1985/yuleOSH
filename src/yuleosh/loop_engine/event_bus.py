#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH EventBus v2.1 — 系统级事件总线 (LE-001) 生产加固版 (I4)。

扩展 KG events.py 的 EventBus，提供:
  - 事件类型枚举 (LoopEventType)
  - Pub/Sub + 路由 + 优先级队列
  - 去重 (dedup) · 持久化到 Store
  - 异步处理 + 重试机制
  - 事件来源验证 (HMAC-SHA256, P2)
  - 速率限制 (Token Bucket, P2)
  - 死信队列 (P3)
  - 审计日志增强 (P3)

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

    # 来源签名 (HMAC-SHA256)
    loop_bus.emit_signed(LoopEventType.CI_FAILURE, source="ci.runner",
                          data={...}, secret="my-secret")
"""

import enum
import hashlib
import hmac
import json
import logging
import os
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
# 前向声明 (避免循环依赖)
# ═══════════════════════════════════════════════════════════════════════

# ChainConfig / ChainContext 在 chain.py 中定义。
# 在 SystemEventBus 中使用时延迟导入。
_ChainConfig = None
_ChainContext = None


def _get_chain_classes():
    """延迟加载 ChainConfig 和 ChainContext (避免循环导入)。"""
    global _ChainConfig, _ChainContext
    if _ChainConfig is None:
        from yuleosh.loop_engine.chain import ChainConfig, ChainContext
        _ChainConfig = ChainConfig
        _ChainContext = ChainContext
    return _ChainConfig, _ChainContext


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

    # ── Chain / Done 事件 (Loop Chaining, I5) ──
    LOOP1_DONE = "loop1.done"
    """Loop 1 (Defect→Requirement) 完成事件。"""

    LOOP2_DONE = "loop2.done"
    """Loop 2 (Field→FMEA) 完成事件。"""

    LOOP3_DONE = "loop3.done"
    """Loop 3 (KPI→Improvement) 完成事件。"""

    LOOP4_CONFIDENCE_UP = "loop4.confidence_up"
    """Loop 4 置信度上升事件。"""


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
        source_fingerprint: 来源签名字段 (HMAC-SHA256, I4)。
        signature: 签名值 (HMAC-SHA256, I4)。
        handler_results: handler 执行结果列表 (I4 审计)。
        rollback_status: 回滚状态 (I4 审计)。
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
    source_fingerprint: str = ""
    signature: str = ""
    handler_results: list[dict] = field(default_factory=list)
    rollback_status: str = ""

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
            "source_fingerprint": self.source_fingerprint,
            "signature": self.signature,
            "handler_results": self.handler_results,
            "rollback_status": self.rollback_status,
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
            source_fingerprint=d.get("source_fingerprint", ""),
            signature=d.get("signature", ""),
            handler_results=d.get("handler_results", []),
            rollback_status=d.get("rollback_status", ""),
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
# 事件来源验证 — HMAC-SHA256 (I4, P2)
# ═══════════════════════════════════════════════════════════════════════

class SourceValidator:
    """事件来源验证器。

    功能:
        - 基于 HMAC-SHA256 的签名生成与验证
        - 可通过环境变量或参数配置签名密钥
        - 支持来源白名单
        - 可启用/禁用验证

    Usage:
        validator = SourceValidator(secret="my-secret")
        signature = validator.sign(event_id, source)
        is_valid = validator.verify(event_id, source, signature)
    """

    def __init__(self, secret: str = "", enabled: bool = True,
                 whitelist: Optional[list[str]] = None,
                 auto_whitelist: bool = False):
        self._secret = secret or os.environ.get(
            "YULEOSH_EVENT_SOURCE_SECRET", ""
        )
        self._enabled = enabled
        self._whitelist = set(whitelist or [])
        # auto_whitelist: 未配置白名单时是否自动信任所有来源
        self._auto_whitelist_enabled = auto_whitelist
        # 动态白名单: 失败后自动加入白名单的来源
        self._auto_whitelist: set[str] = set()
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        with self._lock:
            self._enabled = enabled

    def set_secret(self, secret: str):
        with self._lock:
            self._secret = secret

    def add_to_whitelist(self, source: str):
        with self._lock:
            self._whitelist.add(source)

    def remove_from_whitelist(self, source: str):
        with self._lock:
            self._whitelist.discard(source)
            self._auto_whitelist.discard(source)

    def set_auto_whitelist(self, enabled: bool):
        """设置是否自动白名单（无白名单时信任所有来源）。"""
        with self._lock:
            self._auto_whitelist_enabled = enabled

    @property
    def auto_whitelist_enabled(self) -> bool:
        with self._lock:
            return self._auto_whitelist_enabled

    def is_whitelisted(self, source: str) -> bool:
        with self._lock:
            return source in self._whitelist or source in self._auto_whitelist

    def whitelist(self) -> list[str]:
        with self._lock:
            return sorted(self._whitelist) + sorted(self._auto_whitelist)

    def sign(self, event_id: str, source: str) -> str:
        """生成 HMAC-SHA256 签名。

        Args:
            event_id: 事件唯一 ID。
            source: 事件来源。

        Returns:
            Hex 编码的签名值。
        """
        if not self._secret:
            return ""
        msg = f"{event_id}:{source}".encode("utf-8")
        return hmac.new(
            self._secret.encode("utf-8"), msg, hashlib.sha256
        ).hexdigest()

    def verify(self, event_id: str, source: str,
               signature: str) -> tuple[bool, str]:
        """验证事件来源签名或白名单。

        Args:
            event_id: 事件唯一 ID。
            source: 事件来源。
            signature: 签名值。

        Returns:
            (is_valid, reason) 元组。
        """
        with self._lock:
            if not self._enabled:
                return True, "validation disabled"

            # 白名单检查
            if source in self._whitelist or source in self._auto_whitelist:
                return True, "source whitelisted"

            # auto_whitelist 启用且无显式白名单 → 自动信任所有来源
            if self._auto_whitelist_enabled and not self._whitelist:
                return True, "auto whitelisted (all sources trusted)"

            # 无签名密钥且不在白名单 — 取决于配置
            if not self._secret:
                return False, "no signing secret configured and auto_whitelist disabled"

            # HMAC 验证
            expected = self.sign(event_id, source)
            if hmac.compare_digest(expected, signature):
                return True, "hmac signature valid"

            return False, "hmac signature mismatch"

    def validate_source(self, event: LoopEvent) -> tuple[bool, str]:
        """验证事件来源 — 供 EventBus 内部调用。

        Args:
            event: LoopEvent 实例。

        Returns:
            (is_valid, reason) 元组。
        """
        return self.verify(event.event_id, event.source, event.signature)


# ═══════════════════════════════════════════════════════════════════════
# 速率限制 — Token Bucket (I4, P2)
# ═══════════════════════════════════════════════════════════════════════

class TokenBucket:
    """Token Bucket 速率限制器。

    每个事件类型有独立的 bucket，以配置的速率持续补充 token。
    超限事件进入死信队列。

    Usage:
        limiter = TokenBucket(default_rate=10.0)
        allowed, wait = limiter.check("ci.failure")
        if allowed:
            limiter.consume("ci.failure")
    """

    def __init__(self, default_rate: float = 50.0,
                 default_burst: int = 100,
                 per_type_rates: Optional[dict[str, float]] = None):
        """
        Args:
            default_rate: 默认事件速率 (events/sec)。
            default_burst: 默认突发容量。
            per_type_rates: 每事件类型覆盖速率。
        """
        self._default_rate = default_rate
        self._default_burst = default_burst
        self._per_type_rates: dict[str, float] = dict(per_type_rates or {})
        self._buckets: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        with self._lock:
            self._enabled = enabled

    def set_rate(self, event_type: str, rate: float):
        """设置某事件类型的速率。"""
        self._per_type_rates[event_type] = rate

    def _get_bucket(self, event_type: str) -> dict:
        """获取或初始化指定事件类型的 bucket。"""
        with self._lock:
            if event_type not in self._buckets:
                rate = self._per_type_rates.get(event_type, self._default_rate)
                burst = int(max(rate * 2, self._default_burst))
                self._buckets[event_type] = {
                    "tokens": float(burst),
                    "rate": rate,
                    "burst": burst,
                    "last_refill": time.time(),
                    "dropped": 0,
                }
            return self._buckets[event_type]

    def _refill(self, bucket: dict):
        """补充 token。"""
        now = time.time()
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(
            bucket["burst"],
            bucket["tokens"] + elapsed * bucket["rate"]
        )
        bucket["last_refill"] = now

    def check(self, event_type: str) -> tuple[bool, float]:
        """检查是否允许通过。

        Args:
            event_type: 事件类型字符串。

        Returns:
            (allowed, wait_seconds): allowed 为 False 时 wait 为建议等待时间。
        """
        if not self._enabled:
            return True, 0.0

        with self._lock:
            bucket = self._get_bucket(event_type)
            self._refill(bucket)

            if bucket["tokens"] >= 1.0:
                return True, 0.0
            else:
                wait = (1.0 - bucket["tokens"]) / max(bucket["rate"], 0.001)
                return False, max(0.0, wait)

    def consume(self, event_type: str) -> bool:
        """消费一个 token。

        Returns:
            True 如果成功消费，False 如果超限。
        """
        allowed, _ = self.check(event_type)
        if allowed:
            with self._lock:
                bucket = self._get_bucket(event_type)
                bucket["tokens"] = max(0.0, bucket["tokens"] - 1.0)
            return True
        else:
            with self._lock:
                bucket = self._get_bucket(event_type)
                bucket["dropped"] += 1
            return False

    def stats(self) -> dict:
        """返回速率限制统计。"""
        with self._lock:
            return {
                "enabled": self._enabled,
                "default_rate": self._default_rate,
                "default_burst": self._default_burst,
                "buckets": {
                    k: {
                        "tokens": round(v["tokens"], 2),
                        "rate": v["rate"],
                        "burst": v["burst"],
                        "dropped": v["dropped"],
                    }
                    for k, v in self._buckets.items()
                },
            }


# ═══════════════════════════════════════════════════════════════════════
# 死信队列 (I4, P3)
# ═══════════════════════════════════════════════════════════════════════

class DeadLetterQueue:
    """死信队列 — 存储超限/验证失败的事件。

    功能:
        - 内存存储 + 可选持久化到 Store
        - 配置重试策略 (max_retries, backoff_factor)
        - 支持 list/retry/clear 操作
        - 自动记录死信原因和入队时间
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0,
                 store=None, persist_path: Optional[str] = None,
                 max_queue: int = 5000):
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._store = store
        self._queue: list[dict] = []  # in-memory dead letter store
        self._max_queue = max_queue
        self._lock = threading.RLock()

        # ── 持久化路径 ──
        self._persist_path = persist_path
        if self._persist_path is None:
            _home = os.environ.get("OSH_HOME", ".")
            self._persist_path = os.path.join(
                _home, ".yuleosh", "loop", "dead_letter_queue.json"
            )
        elif self._persist_path == "":
            # 空字符串 = 禁用持久化
            self._persist_path = None
        if self._persist_path:
            self._load_from_disk()

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def backoff_factor(self) -> float:
        return self._backoff_factor

    @property
    def max_queue(self) -> int:
        return self._max_queue

    def enqueue(self, event: LoopEvent, reason: str):
        """将事件加入死信队列。

        Args:
            event: 失败的事件。
            reason: 失败原因描述。
        """
        entry = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "source": event.source,
            "data": event.data,
            "priority": event.priority,
            "dedup_key": event.dedup_key,
            "timestamp": event.timestamp,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "failure_reason": reason,
            "retry_count": 0,
            "max_retries": self._max_retries,
        }

        with self._lock:
            self._queue.append(entry)
            if len(self._queue) > self._max_queue:
                self._queue = self._queue[-self._max_queue:]

        # 持久化到 Store (如已配置)
        if self._store is not None:
            try:
                self._store.insert("dead_letter_events", entry)
            except Exception as e:
                log.warning("DeadLetterQueue: persist error: %s", e)

        log.warning("DeadLetterQueue: enqueued %s (%s) reason=%s",
                    event.event_id[:8], event.event_type.value, reason)

        self._persist_to_disk()

    def list(self, limit: int = 50) -> list[dict]:
        """列出死信队列内容。

        Args:
            limit: 最大返回条目数。

        Returns:
            死信事件字典列表。
        """
        with self._lock:
            return list(self._queue[-limit:])

    def retry_all(self, retry_callback: Optional[Callable[[dict], Any]] = None
                  ) -> tuple[int, int]:
        """重试所有死信事件。

        Args:
            retry_callback: 重试回调函数。为 None 时只计数。

        Returns:
            (success_count, fail_count)
        """
        survived: list[dict] = []
        success_count = 0
        fail_count = 0

        with self._lock:
            entries = list(self._queue)
            self._queue.clear()

        for entry in entries:
            entry["retry_count"] += 1
            if retry_callback is not None:
                try:
                    retry_callback(entry)
                    success_count += 1
                    continue
                except Exception as e:
                    log.warning("DeadLetterQueue: retry failed for %s: %s",
                                entry["event_id"][:8], e)

            if entry["retry_count"] < entry.get("max_retries", self._max_retries):
                survived.append(entry)
                fail_count += 1
            else:
                log.warning("DeadLetterQueue: retry exhausted for %s",
                            entry["event_id"][:8])
                fail_count += 1

        with self._lock:
            self._queue.extend(survived)
            self._persist_to_disk()

        return success_count, fail_count

    def clear(self) -> int:
        """清空死信队列。

        Returns:
            清空的条目数。
        """
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            self._persist_to_disk()
        return count

    def count(self) -> int:
        """返回死信队列当前长度。"""
        with self._lock:
            return len(self._queue)

    def _persist_to_disk(self):
        """将死信队列持久化到磁盘 JSON 文件。"""
        if not self._persist_path:
            return
        try:
            path = self._persist_path
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._queue, f, indent=2, default=str)
        except Exception as e:
            log.warning("DeadLetterQueue: persist to disk error: %s", e)

    def _load_from_disk(self):
        """从磁盘 JSON 文件加载死信队列。"""
        try:
            path = self._persist_path
            if path and os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._queue = data
                    log.info("DeadLetterQueue: loaded %d entries from %s",
                             len(data), path)
        except Exception as e:
            log.warning("DeadLetterQueue: load from disk error: %s", e)

    @property
    def persist_path(self) -> Optional[str]:
        return self._persist_path

    def stats(self) -> dict:
        """返回死信队列统计。"""
        with self._lock:
            return {
                "count": len(self._queue),
                "max_retries": self._max_retries,
                "backoff_factor": self._backoff_factor,
                "store_configured": self._store is not None,
                "persist_path": self._persist_path,
                "persist_exists": bool(self._persist_path and os.path.exists(self._persist_path)),
            }


# ═══════════════════════════════════════════════════════════════════════
# 审计日志 (I4, P3)
# ═══════════════════════════════════════════════════════════════════════

class AuditLog:
    """审计日志 — 记录完整的事件处理历史。

    字段:
        event_id, type, source, fingerprint, priority,
        timestamp, retry_count, handler_results, rollback_status
    """

    def __init__(self, store=None, max_entries: int = 5000):
        self._store = store
        self._entries: list[dict] = []
        self._max_entries = max_entries
        self._lock = threading.RLock()

    def record(self, event: LoopEvent,
               handler_results: Optional[list[dict]] = None,
               rollback_status: str = ""):
        """记录审计条目。

        Args:
            event: 已处理的事件。
            handler_results: handler 执行结果列表。
            rollback_status: 回滚状态描述。
        """
        now = datetime.now(timezone.utc)
        recorded_at = now.isoformat()
        duration_ms = self._compute_duration_ms(event.timestamp, recorded_at)
        entry = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "action": "completed",
            "source": event.source,
            "source_fingerprint": event.source_fingerprint or "",
            "signature": event.signature,
            "priority": event.priority,
            "timestamp": event.timestamp,
            "retry_count": event.retry_count,
            "handler_results": handler_results or event.handler_results,
            "rollback_status": rollback_status or event.rollback_status,
            "data_summary": json.dumps(event.data, sort_keys=True)[:500],
            "duration_ms": duration_ms,
            "recorded_at": recorded_at,
        }

        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

        # 持久化到 Store (如已配置)
        if self._store is not None:
            try:
                self._store.insert("audit_log", entry)
            except Exception as e:
                log.warning("AuditLog: persist error: %s", e)

    def list(self, limit: int = 50,
             event_type: Optional[str] = None,
             since: Optional[str] = None,
             until: Optional[str] = None,
             handler: Optional[str] = None) -> list[dict]:
        """列出审计日志。

        Args:
            limit: 最大返回条目数。
            event_type: 事件类型过滤 (None=全部)。
            since: ISO 8601 起始时间 (None=不限制)。
            until: ISO 8601 截止时间 (None=不限制)。

        Returns:
            匹配条件的审计条目列表。
        """
        with self._lock:
            result = list(self._entries)

        # 过滤事件类型
        if event_type:
            result = [e for e in result if e["event_type"] == event_type]

        # 过滤时间范围
        if since:
            result = [e for e in result if e.get("timestamp", "") >= since]
        if until:
            result = [e for e in result if e.get("timestamp", "") <= until]

        # 过滤 handler 名称
        if handler:
            filtered = []
            for e in result:
                hr = e.get("handler_results", [])
                top_handler = e.get("handler_id", "")
                if top_handler == handler:
                    filtered.append(e)
                    continue
                for r in hr:
                    if r.get("handler", "") == handler:
                        filtered.append(e)
                        break
            result = filtered

        return result[-limit:] if limit >= 0 else result

    def query(self, event_id: str) -> Optional[dict]:
        """根据 event_id 查询审计条目。"""
        with self._lock:
            for entry in reversed(self._entries):
                if entry["event_id"] == event_id:
                    return dict(entry)
        return None

    def clear(self):
        """清空审计日志。"""
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict:
        """返回审计日志统计。"""
        with self._lock:
            return {
                "total_records": len(self._entries),
                "max_entries": self._max_entries,
                "store_configured": self._store is not None,
            }

    def record_action(self, action: str, actor: str = "system",
                       handler_id: str = "",
                       result: str = "success",
                       details: Optional[dict] = None,
                       duration_ms: float = 0.0,
                       journal_id: str = "",
                       restored_entities: Optional[list] = None):
        """记录非事件触发的审计条目（如配置变更、回滚）。

        Args:
            action: 操作名称 (如 "config_changed", "rollback").
            actor: 操作执行者.
            handler_id: handler 标识.
            result: 操作结果 ("success" / "failure").
            details: 操作详情.
            duration_ms: 操作耗时 (毫秒).
            journal_id: 关联的 journal ID (回滚时使用).
            restored_entities: 恢复的实体列表.
        """
        import uuid as _uuid
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "event_id": str(_uuid.uuid4()),
            "event_type": "manual",
            "action": action,
            "source": actor,
            "handler_id": handler_id or actor,
            "timestamp": now,
            "recorded_at": now,
            "duration_ms": duration_ms,
            "result": result,
            "handler_results": [{
                "handler": handler_id or actor,
                "status": result,
            }],
            "rollback_status": "",
            "data_summary": json.dumps(details or {}, sort_keys=True)[:500],
        }
        if journal_id:
            entry["journal_id"] = journal_id
        if restored_entities:
            entry["restored_entities"] = restored_entities

        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

        if self._store is not None:
            try:
                self._store.insert("audit_log", entry)
            except Exception as e:
                log.warning("AuditLog: persist error: %s", e)

    def _compute_duration_ms(self, start_timestamp: str, end_timestamp: str) -> float:
        """计算两个 ISO 时间戳之间的毫秒差。"""
        try:
            start = datetime.fromisoformat(start_timestamp)
            end = datetime.fromisoformat(end_timestamp)
            return max(0.0, (end - start).total_seconds() * 1000.0)
        except Exception:
            return 0.0

    def by_type(self) -> dict[str, int]:
        """按事件类型统计。"""
        with self._lock:
            counts: dict[str, int] = {}
            for entry in self._entries:
                et = entry["event_type"]
                counts[et] = counts.get(et, 0) + 1
            return counts


# ═══════════════════════════════════════════════════════════════════════
# EventQueuePersistence — 事件持久化 (ACC-005, ACC-008)
# ═══════════════════════════════════════════════════════════════════════
# EventQueuePersistence — 持久化 + 崩溃后自动恢复 (ACC-005, ACC-008)
# ═══════════════════════════════════════════════════════════════════════

class EventQueuePersistence:
    """事件队列持久化 — 崩溃后自动恢复未消费的事件。

    功能:
        - 将事件持久化到磁盘 JSON 文件
        - 启动时自动加载未消费事件
        - 幂等性: 避免重复投递已处理的事件
        - 并发安全的文件操作

    存储路径:
        {base_path}/pending_events.json — 未消费事件队列
        {base_path}/processed_events.json — 已处理事件 ID 追踪

    Usage:
        persist = EventQueuePersistence()
        persist.save_event(event)
        persist.mark_processed(event_id)
        recovered = persist.recover_unconsumed()
    """

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            _home = os.environ.get("OSH_HOME", "/tmp")
            base_path = os.path.join(_home, ".yuleosh", "loop")
        self._base_path = base_path
        self._pending_path = os.path.join(base_path, "pending_events.json")
        self._processed_path = os.path.join(base_path, "processed_events.json")
        self._lock = threading.RLock()

        os.makedirs(base_path, exist_ok=True)

        self._processed_ids: set[str] = set()
        self._load_processed_ids()

    @property
    def base_path(self) -> str:
        return self._base_path

    def save_event(self, event: LoopEvent):
        """持久化保存一个事件到 pending 队列。"""
        with self._lock:
            if event.event_id in self._processed_ids:
                log.debug("EventQueuePersistence: event %s already processed, skipping",
                          event.event_id[:8])
                return
            pending = self._load_pending()
            existing_ids = {e["event_id"] for e in pending}
            if event.event_id in existing_ids:
                return
            pending.append(event.to_dict())
            self._save_pending(pending)

    def mark_processed(self, event_id: str):
        """标记事件为已处理。"""
        with self._lock:
            self._processed_ids.add(event_id)
            self._save_processed_ids()
            pending = self._load_pending()
            pending = [e for e in pending if e["event_id"] != event_id]
            self._save_pending(pending)

    def mark_batch_processed(self, event_ids: list[str]):
        """批量标记事件为已处理。"""
        with self._lock:
            for eid in event_ids:
                self._processed_ids.add(eid)
            self._save_processed_ids()
            pending = self._load_pending()
            ids_set = set(event_ids)
            pending = [e for e in pending if e["event_id"] not in ids_set]
            self._save_pending(pending)

    def recover_unconsumed(self) -> list[LoopEvent]:
        """恢复未消费的事件。

        从 pending 队列中读取未被标记为已处理的事件。

        Returns:
            未消费的 LoopEvent 列表 (按时间戳排序)。
        """
        with self._lock:
            pending = self._load_pending()
            unconsumed: list[LoopEvent] = []
            remaining: list[dict] = []

            for entry in pending:
                eid = entry.get("event_id", "")
                if eid and eid in self._processed_ids:
                    continue
                try:
                    event = LoopEvent.from_dict(entry)
                    event.retry_count = 0
                    unconsumed.append(event)
                    remaining.append(entry)
                except Exception as exc:
                    log.warning("EventQueuePersistence: skip invalid event %s: %s",
                                eid[:8] if eid else "?", exc)

            unconsumed.sort(key=lambda e: e.timestamp)
            self._save_pending(remaining)

            if unconsumed:
                log.info("EventQueuePersistence: recovered %d unconsumed event(s)",
                         len(unconsumed))
            return unconsumed

    def has_pending(self) -> bool:
        """检查是否有未消费事件。"""
        pending = self._load_pending()
        for entry in pending:
            if entry.get("event_id", "") not in self._processed_ids:
                return True
        return False

    def pending_count(self) -> int:
        """返回未消费事件计数。"""
        pending = self._load_pending()
        return sum(1 for e in pending
                   if e.get("event_id", "") not in self._processed_ids)

    def clear(self):
        """清空所有持久化数据。"""
        with self._lock:
            self._processed_ids.clear()
            self._save_pending([])
            self._save_processed_ids()

    def stats(self) -> dict:
        """返回持久化统计。"""
        pending = self._load_pending()
        return {
            "base_path": self._base_path,
            "pending_count": len(pending),
            "unconsumed_count": self.pending_count(),
            "processed_ids_count": len(self._processed_ids),
        }

    def _load_pending(self) -> list[dict]:
        try:
            if os.path.exists(self._pending_path):
                with open(self._pending_path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("EventQueuePersistence: load pending error: %s", e)
        return []

    def _save_pending(self, events: list[dict]):
        try:
            with open(self._pending_path, "w") as f:
                json.dump(events, f, indent=2, default=str)
        except OSError as e:
            log.warning("EventQueuePersistence: save pending error: %s", e)

    def _load_processed_ids(self):
        try:
            if os.path.exists(self._processed_path):
                with open(self._processed_path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._processed_ids = set(data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("EventQueuePersistence: load processed ids error: %s", e)

    def _save_processed_ids(self):
        try:
            with open(self._processed_path, "w") as f:
                json.dump(sorted(self._processed_ids), f, indent=2)
        except OSError as e:
            log.warning("EventQueuePersistence: save processed ids error: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# CoalescingGroup — 聚合窗口分组 (ACC-106, ACC-406)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CoalescingGroup:
    """聚合窗口内的事件分组。

    Attributes:
        group_key: 分组键 (通常是目标实体 ID)。
        event_type: 事件类型。
        events: 窗口内的原始事件列表。
        window_start: 窗口开启时间戳。
        pending: 是否仍在等待窗口关闭。
    """
    group_key: str = ""
    event_type: Optional[LoopEventType] = None
    events: list[LoopEvent] = field(default_factory=list)
    window_start: float = 0.0
    pending: bool = True

    def add_event(self, event: LoopEvent):
        """向分组添加事件。"""
        self.events.append(event)

    def to_dict(self) -> dict:
        return {
            "group_key": self.group_key,
            "event_type": self.event_type.value if self.event_type else "",
            "event_count": len(self.events),
            "window_start": self.window_start,
            "pending": self.pending,
        }


# ═══════════════════════════════════════════════════════════════════════
# CoalescingManager — 时间窗口聚合管理器 (ACC-106, ACC-406)
# ═══════════════════════════════════════════════════════════════════════

class CoalescingManager:
    """时间窗口聚合管理器。

    允许多个事件在可配置的时间窗口内聚合为单个动作。
    用于:
        - Loop 1: 30s 窗口内多个测试失败映射到同一需求时合并 spec-delta
        - Loop 4: 60s 窗口内多条预测验证到达时聚合置信度调整

    Usage:
        mgr = CoalescingManager()
        mgr.set_window(LoopEventType.CI_FAILURE, 30.0)
        grouped, is_ready = mgr.add_event(event, group_key="RS-001")
        if is_ready:
            aggregated_event = mgr.flush(group_key)
    """

    def __init__(self):
        self._windows: dict[LoopEventType, float] = {}
        self._groups: dict[str, CoalescingGroup] = {}
        self._lock = threading.RLock()

    def set_window(self, event_type: LoopEventType, window_seconds: float):
        """设置某事件类型的聚合窗口时间。"""
        with self._lock:
            self._windows[event_type] = window_seconds

    def get_window(self, event_type: LoopEventType) -> float:
        """获取某事件类型的聚合窗口时间。"""
        with self._lock:
            return self._windows.get(event_type, 0.0)

    def remove_window(self, event_type: LoopEventType):
        """移除某事件类型的聚合窗口。"""
        with self._lock:
            self._windows.pop(event_type, None)

    def get_group_key(self, event: LoopEvent) -> Optional[str]:
        """获取事件的聚合分组键。"""
        data = event.data or {}
        if event.event_type == LoopEventType.CI_FAILURE:
            return data.get("req_id") or data.get("requirement_id")
        if event.event_type in (LoopEventType.TEST_RESULT, LoopEventType.KG_LOW_CONFIDENCE):
            return data.get("entity_id") or data.get("edge_id")
        if event.event_type == LoopEventType.FIELD_DEFECT:
            return data.get("swc")
        return None

    def add_event(self, event: LoopEvent,
                  group_key: Optional[str] = None) -> tuple[Optional[str], bool]:
        """向聚合窗口添加事件。

        Returns:
            (group_key, is_ready): 窗口是否已关闭可以提交聚合结果。
        """
        if group_key is None:
            group_key = self.get_group_key(event)
        if group_key is None:
            return None, True

        with self._lock:
            window = self._windows.get(event.event_type, 0.0)
            if window <= 0:
                return group_key, True

            if group_key not in self._groups:
                self._groups[group_key] = CoalescingGroup(
                    group_key=group_key,
                    event_type=event.event_type,
                    window_start=time.time(),
                )

            group = self._groups[group_key]
            group.add_event(event)

            elapsed = time.time() - group.window_start
            if elapsed >= window:
                return group_key, True

            return group_key, False

    def flush(self, group_key: str) -> Optional[CoalescingGroup]:
        """刷新 (提取并移除) 一个聚合分组。"""
        with self._lock:
            return self._groups.pop(group_key, None)

    def flush_by_event_type(self, event_type: LoopEventType) -> list[CoalescingGroup]:
        """刷新某事件类型的所有已就绪分组。"""
        window = self.get_window(event_type)
        ready: list[CoalescingGroup] = []
        with self._lock:
            keys_to_remove: list[str] = []
            for gk, group in self._groups.items():
                if group.event_type != event_type:
                    continue
                elapsed = time.time() - group.window_start
                if elapsed >= window:
                    ready.append(group)
                    keys_to_remove.append(gk)

            for gk in keys_to_remove:
                del self._groups[gk]

        return ready

    def cancel_group(self, group_key: str):
        """取消一个聚合分组。"""
        with self._lock:
            self._groups.pop(group_key, None)

    def clear(self):
        """清除所有聚合分组。"""
        with self._lock:
            self._groups.clear()

    def active_groups(self) -> dict[str, dict]:
        """返回当前活跃的聚合分组信息。"""
        with self._lock:
            return {k: v.to_dict() for k, v in self._groups.items()}

    def stats(self) -> dict:
        """返回聚合管理器统计。"""
        with self._lock:
            return {
                "active_groups": len(self._groups),
                "windows": {k.value: v for k, v in self._windows.items()},
                "groups": self.active_groups(),
            }


@dataclass
# ═══════════════════════════════════════════════════════════════════════
# System EventBus
# ═══════════════════════════════════════════════════════════════════════

class SystemEventBus:
    """系统级事件总线 (LE-001) — 生产加固版 (I4)。

    功能:
        - Pub/Sub: on() / off() / emit()
        - 优先级队列: 按 priority 排序执行
        - 去重: 基于 dedup_key，可配置去重窗口
        - 持久化: persist_to_store() 将事件持久化
        - 异步处理: 线程池后台执行
        - 重试: 失败自动重试 (可达 max_retries 次)
        - 统计: stats() 查看事件处理统计
        - 来源验证: HMAC-SHA256 (配置化, I4)
        - 速率限制: Token Bucket (配置化, I4)
        - 死信队列: 超限/验证失败事件入 DLQ (I4)
        - 审计日志: 完整处理历史 (I4)

    线程安全: 全部操作持有 threading.RLock。
    """

    def __init__(self, dedup_window_seconds: float = 300.0,
                 store=None, max_workers: int = 4,
                 # I4 生产加固配置
                 source_validation_enabled: bool = True,
                 source_secret: str = "",
                 source_whitelist: Optional[list[str]] = None,
                 source_auto_whitelist: bool = False,
                 rate_limit_enabled: bool = True,
                 rate_limit_default: float = 50.0,
                 rate_limit_default_burst: int = 100,
                 rate_limit_per_type: Optional[dict[str, float]] = None,
                 dead_letter_max_retries: int = 3,
                 dead_letter_backoff: float = 2.0,
                 dead_letter_max_queue: int = 5000,
                 audit_log_max_entries: int = 5000,
                 # EventQueuePersistence — 持久化路径 (ACC-005, ACC-008)
                 persistence_base_path: Optional[str] = None,
                 persistence_enabled: bool = False,
                 # Coalescing windows — 时间窗口聚合 (ACC-106, ACC-406, 默认禁用)
                 loop1_coalescing_window: float = 0.0,
                 loop4_coalescing_window: float = 0.0):
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
            "total_rate_limited": 0,
            "total_source_rejected": 0,
            "total_dead_letter": 0,
            "total_recovered": 0,
            "total_coalesced": 0,
            "by_type": defaultdict(int),
        }
        self._store = store  # 可选的持久化后端
        self._worker_thread: Optional[threading.Thread] = None
        self._work_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._running = False
        self._max_workers = max_workers

        # ── I4: 来源验证 ──
        self._source_validator = SourceValidator(
            secret=source_secret,
            enabled=source_validation_enabled,
            whitelist=source_whitelist,
            auto_whitelist=source_auto_whitelist,
        )

        # ── I4: 速率限制 ──
        self._rate_limiter = TokenBucket(
            default_rate=rate_limit_default,
            default_burst=rate_limit_default_burst,
            per_type_rates=rate_limit_per_type,
        )
        self._rate_limiter.set_enabled(rate_limit_enabled)

        # ── I4: 死信队列 ──
        self._dead_letter = DeadLetterQueue(
            max_retries=dead_letter_max_retries,
            backoff_factor=dead_letter_backoff,
            max_queue=dead_letter_max_queue,
            store=store,
            persist_path=os.path.join(
                os.environ.get("OSH_HOME", "."),
                ".yuleosh", "loop", "dead_letter_queue.json"
            ),
        )

        # ── I5: Loop Chaining ──
        self._chain_config = None
        self._chain_context: Optional["_ChainContext"] = None

        # ── I4: 审计日志 ──
        self._audit_log = AuditLog(store=store, max_entries=audit_log_max_entries)

        # ── ACC-005, ACC-008: EventQueuePersistence — 事件持久化 + 崩溃自动恢复 ──
        self._persistence_enabled = persistence_enabled
        if persistence_enabled:
            self._persistence = EventQueuePersistence(
                base_path=persistence_base_path
            )
            log.info("EventBus: EventQueuePersistence initialized at %s",
                     self._persistence.base_path)

            # 崩溃后自动恢复未消费的事件
            recovered = self._persistence.recover_unconsumed()
            if recovered:
                log.info("EventBus: recovering %d unconsumed event(s) from crash",
                         len(recovered))
                for idx, recovered_event in enumerate(recovered):
                    self._work_queue.put((recovered_event.priority, idx, recovered_event))
                    with self._lock:
                        self._stats["total_recovered"] += 1

                # 启动 worker 线程处理恢复的事件
                if not self._running:
                    self._running = True
                    self._worker_thread = threading.Thread(
                        target=self._worker_loop, daemon=True
                    )
        else:
            self._persistence = EventQueuePersistence(
                base_path=persistence_base_path or "/tmp/yuleosh-loop"
            )

        # ── ACC-106, ACC-406: CoalescingManager — 时间窗口聚合 ──
        self._coalescing = CoalescingManager()
        if loop1_coalescing_window > 0:
            self._coalescing.set_window(
                LoopEventType.CI_FAILURE, loop1_coalescing_window
            )
            log.info("EventBus: Loop 1 coalescing window = %ss",
                     loop1_coalescing_window)
        if loop4_coalescing_window > 0:
            self._coalescing.set_window(
                LoopEventType.TEST_RESULT, loop4_coalescing_window
            )
            self._coalescing.set_window(
                LoopEventType.KG_LOW_CONFIDENCE, loop4_coalescing_window
            )
            log.info("EventBus: Loop 4 coalescing window = %ss",
                     loop4_coalescing_window)

    # ── I4 组件访问 (只读) ──────────────────────────────────────────

    @property
    def source_validator(self) -> SourceValidator:
        return self._source_validator

    @property
    def rate_limiter(self) -> TokenBucket:
        return self._rate_limiter

    @property
    def dead_letter(self) -> DeadLetterQueue:
        return self._dead_letter

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def persistence(self) -> EventQueuePersistence:
        """事件持久化队列 (ACC-005, ACC-008)."""
        return self._persistence

    @property
    def coalescing(self) -> CoalescingManager:
        """时间窗口聚合管理器 (ACC-106, ACC-406)."""
        return self._coalescing

    @property
    def persistence_enabled(self) -> bool:
        return self._persistence_enabled

    # ── I5: Chain Config ───────────────────────────────────────────────

    @property
    def chain_config(self):
        """获取链式触发配置。

        默认使用 chain.default_chain_config。
        """
        if self._chain_config is None:
            from yuleosh.loop_engine.chain import default_chain_config
            self._chain_config = default_chain_config
        return self._chain_config

    @chain_config.setter
    def chain_config(self, config):
        """设置链式触发配置。

        Args:
            config: ChainConfig 实例或 None (重置为默认)。
        """
        self._chain_config = config

    @property
    def chain_enabled(self) -> bool:
        """链式触发是否已启用 (有规则配置)。"""
        cc = self._chain_config
        if cc is None:
            return False
        return len(cc.list_rules()) > 0

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
          2. 来源验证 (如启用)
          3. 速率限制检查 (如启用)
          4. 去重检查 (可选)
          5. 持久化到 Store (如已配置)
          6. 查找匹配订阅
          7. 按优先级排序执行
          8. 记录审计日志
          9. 记录历史
          10. 返回事件

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
        return self._emit_event(event)

    def _emit_event(self, event: LoopEvent) -> LoopEvent:
        """处理已构建的事件 (emit 的内部实现)。

        Args:
            event: 已构建的 LoopEvent 实例 (可能含预置签名)。

        Returns:
            已处理的事件对象。
        """
        with self._lock:
            self._stats["total_emitted"] += 1
            self._stats["by_type"][event.event_type.value] += 1

        # ── 来源验证 (I4) ──
        valid, reason = self._source_validator.validate_source(event)
        if not valid:
            with self._lock:
                self._stats["total_source_rejected"] += 1
            self._dead_letter.enqueue(event, f"source_validation_failed: {reason}")
            with self._lock:
                self._stats["total_dead_letter"] += 1
            log.warning("EventBus: source validation failed for '%s': %s",
                        event.event_id[:8], reason)
            self._record_audit(event, [{"handler": "_validation",
                                        "status": "rejected",
                                        "reason": reason}],
                               rollback_status="n/a")
            return event

        # ── 速率限制 (I4) ──
        if not self._rate_limiter.consume(event.event_type.value):
            with self._lock:
                self._stats["total_rate_limited"] += 1
            self._dead_letter.enqueue(event, "rate_limited")
            with self._lock:
                self._stats["total_dead_letter"] += 1
            log.warning("EventBus: rate limited '%s' (type=%s)",
                        event.event_id[:8], event.event_type.value)
            self._record_audit(event, [{"handler": "_rate_limiter",
                                        "status": "rejected",
                                        "reason": "rate_limited"}],
                               rollback_status="n/a")
            return event

        # ── 去重 ──
        if self._is_duplicate(event):
            with self._lock:
                self._stats["total_deduped"] += 1
            log.debug("EventBus: deduped %s", event.dedup_key)
            return event

        # ── ACC-106, ACC-406: 聚合窗口检查 ──
        group_key, is_ready = self._coalescing.add_event(event)
        if group_key is not None and not is_ready:
            # 事件被聚合窗口捕获，不立即处理
            # 持久化事件以便崩溃恢复
            if self._persistence_enabled:
                self._persistence.save_event(event)
            log.debug("EventBus: coalesced '%s' into group '%s' (waiting for window close)",
                      event.event_type.value, group_key)
            self._append_history(event)
            return event

        # ── 持久化 (事件队列) ──
        if self._persistence_enabled:
            self._persistence.save_event(event)

        # ── Store 持久化 ──
        if self._store is not None:
            self._persist_event(event)

        # ── 查找匹配订阅 ──
        with self._lock:
            matching = list(self._subscriptions.get(event.event_type, []))
            matching += list(self._subscriptions.get(
                LoopEventType.TEST_RESULT, []))  # wildcard-like

        # 去重: 当 event == TEST_RESULT 时, 订阅者同时出现在两个列表中
        seen_ids = set()
        deduped = []
        for s in matching:
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                deduped.append(s)
        matching = deduped

        # 只匹配满足 priority_filter 的订阅
        matching = [s for s in matching
                    if s.priority_filter is None
                    or event.priority <= s.priority_filter]

        if not matching:
            log.debug("EventBus: '%s' emitted (no matching subscribers, %d subs total)",
                      event.event_type.value, sum(len(v) for v in self._subscriptions.values()))
            self._append_history(event)
            return event

        # ── 按优先级排序执行 ──
        matching.sort(key=lambda s: (s.priority_filter or 0))

        handler_results: list[dict] = []

        for sub in matching:
            handler_name = getattr(sub.callback, '__name__', 'anonymous')
            result = {"handler": handler_name,
                      "status": "success"}
            try:
                sub.callback(event)
                with self._lock:
                    self._stats["total_handled"] += 1
            except Exception as e:
                result["status"] = "failed"
                result["error"] = str(e)
                with self._lock:
                    self._stats["total_failed"] += 1
                # 自动重试
                if event.retry_count < event.max_retries:
                    event.retry_count += 1
                    with self._lock:
                        self._stats["total_retried"] += 1
                    log.warning("EventBus: callback error for '%s' (retry %d/%d): %s",
                                event.event_type.value, event.retry_count,
                                event.max_retries, e)
                    result["retry"] = event.retry_count
                    # 异步重试
                    self._schedule_retry(event, sub)
                else:
                    log.error("EventBus: callback exhausted for '%s': %s",
                              event.event_type.value, e)
                    result["status"] = "exhausted"
                    # 加入死信队列
                    self._dead_letter.enqueue(
                        event, f"handler_exhausted: {e}"
                    )

            handler_results.append(result)

            # one-shot: 自动取消
            if sub.one_shot:
                self.off(sub.id)

        # ── ACC-005, ACC-008: 已处理 → 标记持久化完成 ──
        all_success = all(
            r.get("status") == "success"
            for r in handler_results
        )
        if self._persistence_enabled and all_success:
            self._persistence.mark_processed(event.event_id)

        # ── 审计日志 (I4) ──
        event.handler_results = handler_results
        event.rollback_status = self._compute_rollback_status(handler_results)
        self._record_audit(event, handler_results, event.rollback_status)

        self._append_history(event)

        # ── I5: Loop Chaining — 链式触发 ──
        self._trigger_chained_events(event, handler_results)

        return event

    def emit_signed(self, event_type: LoopEventType,
                    source: str = "system",
                    data: Optional[dict] = None,
                    priority: int = 5,
                    dedup_key: Optional[str] = None,
                    secret: str = "") -> LoopEvent:
        """发布带 HMAC 签名的事件。

        用于可信来源发送签名事件。

        Args:
            event_type: 事件类型。
            source: 来源描述。
            data: 事件载荷。
            priority: 优先级。
            dedup_key: 自定义去重键。
            secret: 签名密钥 (如不传则使用 validator 的密钥)。

        Returns:
            完成的事件对象。
        """
        event = LoopEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            priority=priority,
            dedup_key=dedup_key,
        )

        # 使用 bus 的 validator 签名 (确保验证时能匹配)
        if secret:
            # 设置 secret 以正确签名和后续验证
            self._source_validator.set_secret(secret)
            event.signature = self._source_validator.sign(event.event_id, source)
            event.source_fingerprint = hashlib.sha256(
                secret.encode()
            ).hexdigest()[:8]
        else:
            event.signature = self._source_validator.sign(event.event_id, source)
            event.source_fingerprint = "configured"

        # 使用 _emit_event 处理 (保留签名一致)
        return self._emit_event(event)

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
        self._work_queue.put((event.priority, 0, event))

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
                _, _, event = self._work_queue.get(timeout=1.0)
                self.emit(event.event_type, source=event.source,
                          data=event.data, priority=event.priority,
                          dedup_key=event.dedup_key)
            except queue.Empty:
                continue
            except Exception:
                log.exception("EventBus: worker error")
        self._running = False

    # ── I5: Loop Chaining — 链式触发 ─────────────────────────────────

    def _trigger_chained_events(self, event: LoopEvent,
                                 handler_results: list[dict]):
        """处理完成后的链式触发检查。

        在 handler 执行完成后调用。检查 chain_config 是否有匹配的
        链式规则。如果有，发出相应的目标事件。

        防循环:
          - max_chain_depth: 超过深度自动终止
          - 同一事件链中不重复执行相同 handler
          - 同一事件链中不重复发出相同事件类型

        Args:
            event: 刚处理完毕的事件。
            handler_results: handler 执行结果列表。
        """
        ChainConfig, ChainContext = _get_chain_classes()

        # 只在 handler 全部成功时链式触发 (部分失败时也触发, 但记录)
        all_failed = all(
            r.get("status") in ("failed", "exhausted")
            for r in handler_results
        )
        if all_failed and handler_results:
            log.debug("EventBus: all handlers failed for '%s', skipping chain",
                      event.event_type.value)
            return

        cc = self._chain_config
        if cc is None:
            return

        # 获取链式规则的目标
        event_type_str = event.event_type.value
        targets = cc.get_targets(event_type_str)
        if not targets:
            return

        log.debug("EventBus: chain triggered for '%s' -> %d target(s)",
                  event_type_str, len(targets))

        # 获取或初始化 ChainContext
        chain_ctx = self._chain_context
        if chain_ctx is None:
            # 初始链式触发: 标记当前事件的 event_type 和 handlers 为已访问
            chain_ctx = ChainContext(
                root_event_id=event.event_id,
                max_depth=cc.max_depth,
            )
            chain_ctx.visited_events.add(event_type_str)
            for hr in handler_results:
                hname = hr.get("handler", "")
                if hname:
                    chain_ctx.visited_handlers.add(hname)

        # 检查深度和重复
        for target_handler in targets:
            target_event = cc.get_event_for_handler(target_handler)
            if target_event is None:
                log.warning("EventBus: no event mapping for handler '%s', skipping",
                            target_handler)
                continue

            target_event_str = target_event.value

            # 防循环检查
            if not chain_ctx.can_chain(target_handler, target_event_str):
                continue

            # 标记已访问
            child_ctx = chain_ctx.child_context(target_handler, target_event_str)
            self._chain_context = child_ctx

            # 构造链式触发事件数据
            chain_data = {
                **event.data,
                "_chain_root_event_id": chain_ctx.root_event_id,
                "_chain_depth": child_ctx.depth,
                "_chain_trigger": event_type_str,
                "_chain_target": target_handler,
            }

            log.info("EventBus: chain triggering '%s' -> '%s' (depth=%d/%d)",
                     event_type_str, target_event_str,
                     child_ctx.depth, cc.max_depth)

            # 发出目标事件 (跳过来源验证和速率限制以加速链式触发)
            try:
                chain_event = LoopEvent(
                    event_type=target_event,
                    source="loop_engine.chain",
                    data=chain_data,
                    priority=event.priority,
                )
                self._emit_event(chain_event)
            except Exception as e:
                log.error("EventBus: chain trigger error '%s' -> '%s': %s",
                          event_type_str, target_event_str, e)

        # 清理当前链上下文 (防止泄漏到新的事件链)
        self._chain_context = None

    def set_chain_max_depth(self, max_depth: int):
        """设置链式触发的最大深度。

        Args:
            max_depth: 最大深度 (≥ 1)。
        """
        ChainConfig, _ = _get_chain_classes()
        self.chain_config.max_depth = max_depth

    def clear_chain_context(self):
        """清除链式触发上下文 (重置 visit 记录)。

        用于测试或手动重置。
        """
        self._chain_context = None

    # ── ACC-005, ACC-008: EventQueuePersistence 管理 ─────────────────

    def set_persistence_base_path(self, base_path: str):
        """设置持久化基路径。

        Args:
            base_path: 持久化目录路径。
        """
        self._persistence = EventQueuePersistence(base_path=base_path)

    def set_persistence_enabled(self, enabled: bool):
        """启用/禁用事件持久化。"""
        self._persistence_enabled = enabled

    def recover_from_crash(self) -> int:
        """手动触发出崩溃恢复 — 重新入队未消费事件。

        Returns:
            恢复的事件数量。
        """
        if not self._persistence_enabled:
            log.warning("EventBus: persistence disabled, skipping recovery")
            return 0

        recovered = self._persistence.recover_unconsumed()
        count = 0
        for idx, event in enumerate(recovered):
            self._work_queue.put((event.priority, idx, event))
            with self._lock:
                self._stats["total_recovered"] += 1
                self._stats["total_emitted"] += 1
                self._stats["by_type"][event.event_type.value] += 1
            count += 1

        # 启动 worker 线程 (如需要)
        if count > 0 and not self._running:
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()

        return count

    # ── ACC-106, ACC-406: Coalescing 管理 ─────────────────────────

    def set_loop1_coalescing_window(self, window_seconds: float):
        """设置 Loop 1 聚合窗口 (CI_FAILURE 事件的 spec-delta 合并)。

        Args:
            window_seconds: 窗口秒数 (<=0 禁用)。
        """
        if window_seconds > 0:
            self._coalescing.set_window(
                LoopEventType.CI_FAILURE, window_seconds
            )
        else:
            self._coalescing.remove_window(LoopEventType.CI_FAILURE)

    def set_loop4_coalescing_window(self, window_seconds: float):
        """设置 Loop 4 聚合窗口 (置信度调整的合并)。

        Args:
            window_seconds: 窗口秒数 (<=0 禁用)。
        """
        if window_seconds > 0:
            self._coalescing.set_window(
                LoopEventType.TEST_RESULT, window_seconds
            )
            self._coalescing.set_window(
                LoopEventType.KG_LOW_CONFIDENCE, window_seconds
            )
        else:
            self._coalescing.remove_window(LoopEventType.TEST_RESULT)
            self._coalescing.remove_window(LoopEventType.KG_LOW_CONFIDENCE)

    def flush_loop1_coalesced(self) -> list[CoalescingGroup]:
        """刷新 Loop 1 已就绪的聚合分组。

        返回已就绪的分组列表，调用方应针对每个分组生成
        单一的聚合 spec-delta。

        Returns:
            已就绪的 CoalescingGroup 列表。
        """
        with self._lock:
            self._stats["total_coalesced"] += 1
        return self._coalescing.flush_by_event_type(LoopEventType.CI_FAILURE)

    def flush_loop4_coalesced(self) -> list[CoalescingGroup]:
        """刷新 Loop 4 已就绪的聚合分组。

        返回已就绪的分组列表，调用方应针对每个分组应用
        单一的聚合置信度调整。

        Returns:
            已就绪的 CoalescingGroup 列表。
        """
        with self._lock:
            self._stats["total_coalesced"] += 1
        return self._coalescing.flush_by_event_type(LoopEventType.TEST_RESULT)

    def clear_coalescing(self):
        """清除所有活跃的聚合分组。"""
        self._coalescing.clear()

    def active_coalescing_groups(self) -> dict[str, dict]:
        """返回当前活跃的聚合分组。"""
        return self._coalescing.active_groups()

    # ── 来源验证 (I4) ──────────────────────────────────────────────

    def set_source_secret(self, secret: str):
        """设置来源验证签名密钥。"""
        self._source_validator.set_secret(secret)

    def set_source_validation(self, enabled: bool):
        """启用/禁用来源验证。"""
        self._source_validator.set_enabled(enabled)

    def add_source_whitelist(self, source: str):
        """添加来源白名单。"""
        self._source_validator.add_to_whitelist(source)

    def set_source_auto_whitelist(self, enabled: bool):
        """设置自动白名单模式。"""
        self._source_validator.set_auto_whitelist(enabled)

    def remove_source_whitelist(self, source: str):
        """移除来源白名单。"""
        self._source_validator.remove_from_whitelist(source)

    # ── 速率限制 (I4) ──────────────────────────────────────────────

    def set_rate_limit(self, enabled: bool):
        """启用/禁用速率限制。"""
        self._rate_limiter.set_enabled(enabled)

    def set_rate_limit_for_type(self, event_type: str, rate: float):
        """设置某事件类型的速率限制。"""
        self._rate_limiter.set_rate(event_type, rate)

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
        """设置持久化后端。

        同步更新 Store 引用到子组件 (死信队列、审计日志)。
        """
        self._store = store
        self._dead_letter = DeadLetterQueue(
            max_retries=self._dead_letter.max_retries,
            backoff_factor=self._dead_letter.backoff_factor,
            max_queue=self._dead_letter.max_queue,
            store=store,
            persist_path=self._dead_letter.persist_path,
        )
        self._audit_log = AuditLog(store=store,
                                   max_entries=self._audit_log.stats()["max_entries"])

    def _persist_event(self, event: LoopEvent):
        """增强持久化 — 完整审计字段 (I4)。"""
        try:
            self._store.insert("loop_events", {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "source": event.source,
                "source_fingerprint": event.source_fingerprint,
                "signature": event.signature,
                "data": json.dumps(event.data),
                "priority": event.priority,
                "dedup_key": event.dedup_key,
                "timestamp": event.timestamp,
                "retry_count": event.retry_count,
                "max_retries": event.max_retries,
                "handler_results": json.dumps(event.handler_results),
                "rollback_status": event.rollback_status,
            })
        except Exception as e:
            log.warning("EventBus: persist error: %s", e)

    def _record_audit(self, event: LoopEvent,
                      handler_results: list[dict],
                      rollback_status: str):
        """记录审计日志。"""
        event.handler_results = handler_results
        event.rollback_status = rollback_status
        self._audit_log.record(event, handler_results, rollback_status)

    def _compute_rollback_status(self, handler_results: list[dict]) -> str:
        """计算回滚状态。"""
        failed = sum(1 for r in handler_results
                     if r.get("status") in ("failed", "exhausted"))
        if failed == 0:
            return "no_rollback_needed"
        elif failed < len(handler_results):
            return "partial_rollback"
        else:
            return "full_rollback"

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
                    # 重试耗尽 — 加入死信队列
                    self._dead_letter.enqueue(
                        event, f"retry_exhausted: {e2}"
                    )

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
        """返回事件总线统计信息 (含 I4/I5 增强字段)。"""
        with self._lock:
            base = dict(self._stats)
            base["rate_limiter"] = self._rate_limiter.stats()
            base["dead_letter"] = self._dead_letter.stats()
            base["audit"] = self._audit_log.stats()
            base["source_validator"] = {
                "enabled": self._source_validator.enabled,
                "has_secret": bool(self._source_validator._secret),
                "whitelist": self._source_validator.whitelist(),
                "auto_whitelist": self._source_validator.auto_whitelist_enabled,
            }
            # I5: Loop Chaining
            cc = self._chain_config
            if cc is not None:
                from yuleosh.loop_engine.chain import ChainConfig
                if isinstance(cc, ChainConfig):
                    base["chain"] = {
                        "max_depth": cc.max_depth,
                        "active_rules": len(cc.list_rules()),
                        "rules": cc.list_rules(),
                    }
                else:
                    base["chain"] = {"enabled": True}
            else:
                base["chain"] = {"enabled": False}
            # ACC-005, ACC-008: 持久化统计
            base["persistence"] = self._persistence.stats()
            # ACC-106, ACC-406: 聚合窗口统计
            base["coalescing"] = self._coalescing.stats()
            return base

    def active_subscriptions(self) -> dict[str, int]:
        """返回活跃订阅计数 (按事件类型)。"""
        with self._lock:
            return {k.value: len(v) for k, v in self._subscriptions.items()}


# ── 全局单例 ──────────────────────────────────────────────────────────

loop_bus = SystemEventBus(persistence_enabled=False)
"""全局 Loop 系统事件总线实例 (持久化禁用, 按需配置)。"""

# ═══════════════════════════════════════════════════════════════════════
# __all__
# ═══════════════════════════════════════════════════════════════════════

__all__ = [
    "LoopEventType",
    "LoopEvent",
    "Subscription",
    "SourceValidator",
    "TokenBucket",
    "DeadLetterQueue",
    "AuditLog",
    "EventQueuePersistence",
    "CoalescingGroup",
    "CoalescingManager",
    "SystemEventBus",
    "loop_bus",
]
