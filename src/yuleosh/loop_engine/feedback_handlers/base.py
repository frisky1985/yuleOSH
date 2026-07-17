#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
FeedbackHandler 基类 — 反馈回路抽象接口 (LE-002)。

每个 Loop (反馈回路) 实现一个 FeedbackHandler 子类：
  - can_handle(event): 判断是否可处理该事件
  - handle(event) -> ActionResult: 处理事件
  - rollback(event): 回滚操作

Decorator:
  - @register_handler 自动将 handler 注册到全局注册表

Usage:
    from yuleosh.loop_engine.feedback_handlers.base import (
        FeedbackHandler, ActionResult, register_handler
    )

    @register_handler
    class MyLoopHandler(FeedbackHandler):
        def subscribed_events(self):
            return [LoopEventType.CI_FAILURE]

        def handle(self, event) -> ActionResult:
            ...  # 核心逻辑
            return ActionResult(success=True, action_taken="...")
"""

import abc
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType

log = logging.getLogger("yuleosh.loop_engine.handlers")


# ═══════════════════════════════════════════════════════════════════════
# ActionResult
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ActionResult:
    """反馈回路处理结果。

    Attributes:
        success: 处理是否成功。
        action_taken: 执行的操作描述。
        evidence_ref: 证据引用路径或 URL。
        rollback_possible: 是否可以回滚。
        details: 额外的处理详情字典。
    """
    success: bool = True
    action_taken: str = ""
    evidence_ref: Optional[str] = None
    rollback_possible: bool = False
    details: dict = field(default_factory=dict)
    handler_name: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action_taken": self.action_taken,
            "evidence_ref": self.evidence_ref,
            "rollback_possible": self.rollback_possible,
            "details": self.details,
            "handler_name": self.handler_name,
            "timestamp": self.timestamp,
        }

    def __bool__(self):
        return self.success


# ═══════════════════════════════════════════════════════════════════════
# FeedbackHandler 抽象基类
# ═══════════════════════════════════════════════════════════════════════

class FeedbackHandler(abc.ABC):
    """反馈回路处理器抽象基类。

    子类必须实现的方法:
      - subscribed_events() -> list[LoopEventType]
      - handle(event) -> ActionResult

    可选实现的方法:
      - can_handle(event) -> bool
      - rollback(event) -> ActionResult
      - name() -> str
    """

    @abc.abstractmethod
    def subscribed_events(self) -> list[LoopEventType]:
        """返回此 handler 关注的事件类型列表。"""
        ...

    @abc.abstractmethod
    def handle(self, event: LoopEvent) -> ActionResult:
        """处理事件并返回处理结果。

        Args:
            event: 要处理的 LoopEvent。

        Returns:
            ActionResult 包含处理结果和证据引用。
        """
        ...

    def can_handle(self, event: LoopEvent) -> bool:
        """判断此 handler 是否可以处理该事件。

        默认实现: 检查 event_type 是否在 subscribed_events() 中。
        子类可以覆盖以添加更细粒度的过滤。
        """
        return event.event_type in self.subscribed_events()

    def rollback(self, event: LoopEvent) -> ActionResult:
        """回滚由 handle() 执行的操作。

        默认实现返回不可回滚。
        子类应覆盖以提供实际的回滚逻辑。

        Args:
            event: 要回滚的原始事件。

        Returns:
            ActionResult 表示回滚结果。
        """
        return ActionResult(
            success=False,
            action_taken="rollback not implemented",
            rollback_possible=False,
            handler_name=self.name,
        )

    @property
    def name(self) -> str:
        """返回 handler 名称。"""
        return self.__class__.__name__

    def __repr__(self):
        return f"<{self.name} events={[e.value for e in self.subscribed_events()]}>"


# ═══════════════════════════════════════════════════════════════════════
# 全局注册表
# ═══════════════════════════════════════════════════════════════════════

_handler_registry: dict[str, type[FeedbackHandler]] = {}


def register_handler(cls: type[FeedbackHandler]) -> type[FeedbackHandler]:
    """装饰器: 自动将 FeedbackHandler 子类注册到全局注册表。

    用于类定义上:
        @register_handler
        class MyLoop(FeedbackHandler):
            ...

    可以在运行时通过 get_registered_handlers() 获取所有已注册 handler。
    """
    if not issubclass(cls, FeedbackHandler):
        raise TypeError(f"{cls.__name__} must subclass FeedbackHandler")

    name = cls.__name__
    _handler_registry[name] = cls
    log.debug("Registered feedback handler: %s", name)
    return cls


def get_registered_handlers() -> dict[str, type[FeedbackHandler]]:
    """返回所有已注册的 FeedbackHandler 类。"""
    return dict(_handler_registry)


def unregister_handler(name: str):
    """取消注册 handler (用于测试)。"""
    _handler_registry.pop(name, None)


def clear_registry():
    """清除所有注册 (用于测试)。"""
    _handler_registry.clear()
