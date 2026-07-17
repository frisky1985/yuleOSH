#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop Chaining — 链式触发规则引擎 (I5).

提供 ChainConfig 类，定义 Loop 之间的链式触发规则。
与 SystemEventBus 集成，在 handler 执行完成后自动检查并触发下游 Loop。

支持:
  - 规则注册: add_rule(trigger_event, target_loop)
  - 规则查询: get_targets(trigger_event) → list[str]
  - 防循环: max_chain_depth 限制 + 同一事件链中不重复执行相同 handler
  - 规则持久化: save / load

Usage:
    from yuleosh.loop_engine.chain import ChainConfig

    config = ChainConfig()
    config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
    config.add_rule("loop1.done", "Loop4KGSelfEvolveHandler")

    # 与 EventBus 集成
    from yuleosh.loop_engine.event_bus import loop_bus
    loop_bus.chain_config = config
"""

import json
import logging
import os
from typing import Optional

from yuleosh.loop_engine.event_bus import LoopEventType

log = logging.getLogger("yuleosh.loop_engine.chain")


# ═══════════════════════════════════════════════════════════════════════
# 内置 Handler → Event 映射
# ═══════════════════════════════════════════════════════════════════════

# 每个 FeedbackHandler 子类会订阅特定的事件类型。
# 当链式触发需要激活某个 Handler 时，需发出它订阅的事件。
HANDLER_EVENT_MAP: dict[str, LoopEventType] = {
    "Loop1DefectToReqHandler": LoopEventType.CI_FAILURE,
    "Loop2FieldToFMEAHandler": LoopEventType.FIELD_DEFECT,
    "Loop3KPIToImproveHandler": LoopEventType.KPI_BREACH,
    "Loop4KGSelfEvolveHandler": LoopEventType.TEST_RESULT,
}

# 每个 Done 事件的 source 描述
DONE_EVENT_SOURCES: dict[str, str] = {
    "loop1.done": "loop_engine.chain",
    "loop2.done": "loop_engine.chain",
    "loop3.done": "loop_engine.chain",
    "loop4.confidence_up": "loop_engine.chain",
}


# ═══════════════════════════════════════════════════════════════════════
# 默认链式规则
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_CHAIN_RULES: dict[str, list[str]] = {
    # 当 Loop 1 handler 完成 → 触发 Loop 3 检查 KPI + Loop 4 更新置信度
    "loop1.done": [
        "Loop3KPIToImproveHandler",
        "Loop4KGSelfEvolveHandler",
    ],
    # 当 Loop 2 handler 完成 → 触发 Loop 1 标记安全关键需求
    "loop2.done": [
        "Loop1DefectToReqHandler",
    ],
    # 当 Loop 4 置信度上升 → 触发 Loop 1 自动关闭 needs_review
    "loop4.confidence_up": [
        "Loop1DefectToReqHandler",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# ChainContext — 链式上下文 (用于防循环和防重复)
# ═══════════════════════════════════════════════════════════════════════

class ChainContext:
    """链式触发上下文 — 追踪当前链式调用的状态。

    当 EventBus 在一次链式触发中发出多个事件时，
    使用 ChainContext 记录深度和已访问的 handler/event，防止循环。

    Attributes:
        depth: 当前链式触发的深度 (根事件 = 0)。
        visited_handlers: 已触发的 handler 名称集合。
        visited_events: 已发出的事件类型集合。
        max_depth: 最大允许深度。
        root_event_id: 根事件 ID。
    """

    def __init__(self, root_event_id: str = "",
                 max_depth: int = 5):
        self.depth = 0
        self.visited_handlers: set[str] = set()
        self.visited_events: set[str] = set()
        self.max_depth = max_depth
        self.root_event_id = root_event_id

    def can_chain(self, handler_name: str, event_type: str) -> bool:
        """检查是否可以继续链式触发。

        Args:
            handler_name: 目标 handler 名称。
            event_type: 目标事件类型字符串。

        Returns:
            True 如果允许触发，False 如果超过深度或已访问过。
        """
        if self.depth >= self.max_depth:
            log.warning("ChainContext: max depth reached (%d >= %d), "
                        "blocking chain to %s/%s",
                        self.depth, self.max_depth, handler_name, event_type)
            return False

        if handler_name in self.visited_handlers:
            log.debug("ChainContext: handler '%s' already visited, skipping",
                      handler_name)
            return False

        if event_type in self.visited_events:
            log.debug("ChainContext: event '%s' already visited, skipping",
                      event_type)
            return False

        return True

    def mark_visited(self, handler_name: str, event_type: str):
        """标记 handler 和事件已访问。"""
        self.visited_handlers.add(handler_name)
        self.visited_events.add(event_type)

    def child_context(self, handler_name: str, event_type: str) -> "ChainContext":
        """创建子上下文 (深度 +1，继承 visited 记录)。

        Args:
            handler_name: 即将触发的 handler 名称。
            event_type: 即将触发的事件类型。

        Returns:
            新的 ChainContext (depth + 1)。
        """
        child = ChainContext(
            root_event_id=self.root_event_id,
            max_depth=self.max_depth,
        )
        child.depth = self.depth + 1
        child.visited_handlers = set(self.visited_handlers)
        child.visited_events = set(self.visited_events)
        child.visited_handlers.add(handler_name)
        child.visited_events.add(event_type)
        return child

    def to_dict(self) -> dict:
        return {
            "depth": self.depth,
            "max_depth": self.max_depth,
            "root_event_id": self.root_event_id,
            "visited_handlers": list(self.visited_handlers),
            "visited_events": list(self.visited_events),
        }

    def __repr__(self):
        return (f"<ChainContext depth={self.depth}/{self.max_depth} "
                f"root={self.root_event_id[:12]} "
                f"handlers={len(self.visited_handlers)} "
                f"events={len(self.visited_events)}>")


# ═══════════════════════════════════════════════════════════════════════
# ChainConfig
# ═══════════════════════════════════════════════════════════════════════

class ChainConfig:
    """链式触发规则配置。

    定义事件 → handler 的映射关系。当 EventBus 发出一条事件后，
    检查此配置是否有匹配的规则，自动触发下游 handler。

    Attributes:
        max_depth: 链式触发的最大深度 (默认 5)。
        _rules: {trigger_event_str: [target_handler_name]}。
        _handler_event_map: 自定义 handler → 事件映射 (覆盖 HANDLER_EVENT_MAP)。
    """

    def __init__(self, max_depth: int = 5):
        self._max_depth = max_depth
        self._rules: dict[str, list[str]] = {}
        self._handler_event_map: dict[str, LoopEventType] = dict(HANDLER_EVENT_MAP)

    # ── 属性 ──────────────────────────────────────────────────────────

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @max_depth.setter
    def max_depth(self, value: int):
        if value < 1:
            raise ValueError("max_depth must be >= 1")
        self._max_depth = value

    # ── 规则管理 ──────────────────────────────────────────────────────

    def add_rule(self, trigger_event: str, target_loop: str):
        """添加链式触发规则。

        当 EventBus 发出 trigger_event 事件后，自动触发 target_loop handler。

        Args:
            trigger_event: 触发事件类型字符串 (如 "loop1.done")。
            target_loop: 目标 handler 类名 (如 "Loop3KPIToImproveHandler")。

        Raises:
            ValueError: 如果 target_loop 不在 HANDLER_EVENT_MAP 中。
        """
        if target_loop not in self._handler_event_map:
            valid = list(self._handler_event_map.keys())
            raise ValueError(
                f"Unknown target handler '{target_loop}'. "
                f"Valid handlers: {valid}"
            )

        if trigger_event not in self._rules:
            self._rules[trigger_event] = []

        if target_loop not in self._rules[trigger_event]:
            self._rules[trigger_event].append(target_loop)
            log.debug("ChainConfig: added rule '%s' -> '%s'",
                      trigger_event, target_loop)

    def remove_rule(self, trigger_event: str, target_loop: str) -> bool:
        """移除链式触发规则。

        Args:
            trigger_event: 触发事件类型字符串。
            target_loop: 目标 handler 类名。

        Returns:
            True 如果规则存在并移除；False 如果规则不存在。
        """
        if trigger_event in self._rules and target_loop in self._rules[trigger_event]:
            self._rules[trigger_event].remove(target_loop)
            if not self._rules[trigger_event]:
                del self._rules[trigger_event]
            log.debug("ChainConfig: removed rule '%s' -> '%s'",
                      trigger_event, target_loop)
            return True
        return False

    def get_targets(self, trigger_event: str) -> list[str]:
        """获取触发事件对应的所有目标 handler 名称。

        Args:
            trigger_event: 触发事件类型字符串。

        Returns:
            目标 handler 类名列表。如果无匹配规则，返回空列表。
        """
        return list(self._rules.get(trigger_event, []))

    def clear_rules(self):
        """清除所有规则。"""
        self._rules.clear()
        log.debug("ChainConfig: all rules cleared")

    def has_rule(self, trigger_event: str, target_loop: str) -> bool:
        """检查规则是否存在。"""
        return (trigger_event in self._rules
                and target_loop in self._rules[trigger_event])

    def list_rules(self) -> dict[str, list[str]]:
        """列出所有规则。"""
        return {k: list(v) for k, v in self._rules.items()}

    # ── Handler ↔ Event 映射 ──────────────────────────────────────────

    def get_event_for_handler(self, handler_name: str) -> Optional[LoopEventType]:
        """获取激活指定 handler 需要发出的事件类型。

        Args:
            handler_name: handler 类名。

        Returns:
            LoopEventType 或 None (如果未注册)。
        """
        return self._handler_event_map.get(handler_name)

    def get_handler_for_event(self, event_type: LoopEventType) -> Optional[str]:
        """获取订阅指定事件类型的 handler 名称 (反向查找)。

        Args:
            event_type: 事件类型。

        Returns:
            handler 类名或 None。
        """
        for name, et in self._handler_event_map.items():
            if et == event_type:
                return name
        return None

    def register_handler_event(self, handler_name: str,
                                event_type: LoopEventType):
        """注册自定义 handler → 事件映射。

        用于在创建 ChainConfig 后添加自定义 handler 的映射。

        Args:
            handler_name: handler 类名。
            event_type: 该 handler 订阅的事件类型。
        """
        self._handler_event_map[handler_name] = event_type

    # ── 默认规则 ──────────────────────────────────────────────────────

    def load_defaults(self):
        """加载默认链式规则。"""
        for trigger_event, targets in DEFAULT_CHAIN_RULES.items():
            for target in targets:
                self.add_rule(trigger_event, target)
        log.info("ChainConfig: loaded %d default rules",
                 sum(len(v) for v in DEFAULT_CHAIN_RULES.values()))

    # ── 持久化 ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "max_depth": self._max_depth,
            "rules": {k: list(v) for k, v in self._rules.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChainConfig":
        """从字典反序列化。"""
        config = cls(max_depth=data.get("max_depth", 5))
        for trigger_event, targets in data.get("rules", {}).items():
            for target in targets:
                config.add_rule(trigger_event, target)
        return config

    def save(self, path: str):
        """保存到 JSON 文件。

        Args:
            path: 文件路径。
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        log.info("ChainConfig: saved %d rules to %s",
                 sum(len(v) for v in self._rules.values()), path)

    @classmethod
    def load(cls, path: str) -> "ChainConfig":
        """从 JSON 文件加载。

        Args:
            path: 文件路径。

        Returns:
            加载的 ChainConfig 实例；如果文件不存在则返回默认配置。
        """
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = cls.from_dict(data)
            log.info("ChainConfig: loaded %d rules from %s",
                     sum(len(v) for v in config._rules.values()), path)
            return config
        log.info("ChainConfig: no config at %s, using defaults", path)
        config = cls()
        config.load_defaults()
        return config

    def __repr__(self):
        total = sum(len(v) for v in self._rules.values())
        return f"<ChainConfig rules={total} depth={self._max_depth}>"


# ═══════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════

default_chain_config = ChainConfig()
"""默认 ChainConfig 实例 (已加载默认规则)。"""
default_chain_config.load_defaults()


__all__ = [
    "ChainConfig",
    "ChainContext",
    "default_chain_config",
    "HANDLER_EVENT_MAP",
    "DEFAULT_CHAIN_RULES",
]
