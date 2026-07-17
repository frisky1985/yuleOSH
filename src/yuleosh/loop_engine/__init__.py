#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Loop Engineering — 系统级反馈闭环引擎。

提供 EventBus v2（系统级事件总线）、FeedbackHandler 框架、
四个反馈回路，以及统一的 CLI 入口。

使用方式:
    from yuleosh.loop_engine import LoopEngine
    engine = LoopEngine()
    engine.start()

CLI:
    yuleosh loop status
    yuleosh loop run loop1_defect_to_req
    yuleosh loop config
"""

import logging

from yuleosh.loop_engine.event_bus import (
    SystemEventBus,
    LoopEventType,
    LoopEvent,
    loop_bus,
)
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
    get_registered_handlers,
)
from yuleosh.loop_engine.spec_delta_gen import SpecDeltaGenerator, SpecDelta

log = logging.getLogger("yuleosh.loop_engine")


class LoopEngine:
    """Loop Engineering 引擎 — 编排事件总线与反馈回路。

    职责:
        - 初始化系统级 EventBus
        - 自动加载并注册所有 FeedbackHandler
        - 提供 start/stop 生命周期管理
    """

    def __init__(self, event_bus: SystemEventBus | None = None):
        self.event_bus = event_bus or loop_bus
        self._handlers: dict[str, FeedbackHandler] = {}
        self._running = False
        self._handler_refs: list = []  # subscription refs for cleanup

    def register_handler(self, handler: FeedbackHandler):
        """注册一个 FeedbackHandler 并订阅其监听的事件。"""
        name = handler.__class__.__name__
        self._handlers[name] = handler

        for event_type in handler.subscribed_events():
            def _make_callback(h=handler):
                return lambda event: h.handle(event)
            ref = self.event_bus.on(event_type, _make_callback())
            self._handler_refs.append(ref)

        log.info("LoopEngine: registered handler '%s' for events %s",
                 name, handler.subscribed_events())

    def start(self):
        """启动 Loop Engine — 自动加载所有已注册的 FeedbackHandler。"""
        self._running = True
        log.info("LoopEngine: started with %d handler(s)", len(self._handlers))
        return self

    def stop(self):
        """停止 Loop Engine。"""
        self._running = False
        for ref in self._handler_refs:
            try:
                self.event_bus.off(ref)
            except Exception:
                pass
        self._handler_refs.clear()
        log.info("LoopEngine: stopped")

    def run_loop_once(self, loop_name: str, **kwargs):
        """手动触发指定 loop（用于 CLI 或测试）。

        Args:
            loop_name: Handler 类名或注册名。
            **kwargs: 事件数据参数。
        """
        handler = self._handlers.get(loop_name)
        if handler is None:
            raise ValueError(f"Loop handler '{loop_name}' not registered. "
                             f"Available: {list(self._handlers.keys())}")

        # 构建模拟事件
        event = LoopEvent(
            event_type=handler.subscribed_events()[0],
            source="cli",
            data=kwargs,
        )
        return handler.handle(event)

    @property
    def status(self) -> dict:
        """获取当前引擎状态。"""
        return {
            "running": self._running,
            "handlers": {
                name: {
                    "subscribed_events": [e.value for e in h.subscribed_events()],
                    "can_handle": True,
                }
                for name, h in self._handlers.items()
            },
            "event_bus_stats": self.event_bus.stats(),
        }


__all__ = [
    "LoopEngine",
    "SystemEventBus", "loop_bus", "LoopEventType", "LoopEvent",
    "FeedbackHandler", "ActionResult", "register_handler", "get_registered_handlers",
    "SpecDeltaGenerator", "SpecDelta",
]
