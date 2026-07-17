#!/usr/bin/env python3
"""
Loop Chaining — 链式触发测试 (I5)。

覆盖:
  - ChainConfig 基础功能 (规则增删查)
  - ChainContext 防循环 / 防重复 / 深度保护
  - SystemEventBus 链式触发集成
  - 默认链式规则
  - 循环保护 (A→B→A 应被阻断)
  - 深度保护 (超过 max_chain_depth 自动终止)
  - 配置规则持久化
  - 向后兼容性
"""

import json
import os
import time
import pytest
from unittest.mock import Mock, patch, MagicMock

from yuleosh.loop_engine.event_bus import (
    SystemEventBus,
    LoopEventType,
    LoopEvent,
    loop_bus,
)
from yuleosh.loop_engine.chain import (
    ChainConfig,
    ChainContext,
    default_chain_config,
    HANDLER_EVENT_MAP,
    DEFAULT_CHAIN_RULES,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def clean_bus():
    """创建干净的 EventBus (验证和速率限制关闭)。"""
    return SystemEventBus(
        source_validation_enabled=False,
        rate_limit_enabled=False,
    )


@pytest.fixture
def chain_config():
    """创建空规则的 ChainConfig (无默认规则)。"""
    return ChainConfig(max_depth=5)


@pytest.fixture
def default_config():
    """创建带默认规则的 ChainConfig。"""
    config = ChainConfig(max_depth=5)
    config.load_defaults()
    return config


# ═══════════════════════════════════════════════════════════════════════
# ChainConfig 基础功能
# ═══════════════════════════════════════════════════════════════════════

class TestChainConfigBasics:

    def test_add_rule(self, chain_config):
        """添加链式触发规则。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        targets = chain_config.get_targets("loop1.done")
        assert targets == ["Loop3KPIToImproveHandler"]

    def test_add_multiple_targets(self, chain_config):
        """一个触发事件可以对应多个目标 handler。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        chain_config.add_rule("loop1.done", "Loop4KGSelfEvolveHandler")
        targets = chain_config.get_targets("loop1.done")
        assert len(targets) == 2
        assert "Loop3KPIToImproveHandler" in targets
        assert "Loop4KGSelfEvolveHandler" in targets

    def test_add_duplicate_rule(self, chain_config):
        """重复添加同一规则不应产生重复条目。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        targets = chain_config.get_targets("loop1.done")
        assert len(targets) == 1

    def test_remove_rule(self, chain_config):
        """移除链式触发规则。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        assert chain_config.remove_rule("loop1.done", "Loop3KPIToImproveHandler")
        assert chain_config.get_targets("loop1.done") == []

    def test_remove_nonexistent_rule(self, chain_config):
        """移除不存在的规则应返回 False。"""
        assert not chain_config.remove_rule("nonexistent", "FooHandler")

    def test_has_rule(self, chain_config):
        """检查规则是否存在。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        assert chain_config.has_rule("loop1.done", "Loop3KPIToImproveHandler")
        assert not chain_config.has_rule("loop1.done", "Loop4KGSelfEvolveHandler")

    def test_list_rules(self, chain_config):
        """列出所有规则。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        chain_config.add_rule("loop2.done", "Loop1DefectToReqHandler")
        rules = chain_config.list_rules()
        assert len(rules) == 2
        assert rules["loop1.done"] == ["Loop3KPIToImproveHandler"]
        assert rules["loop2.done"] == ["Loop1DefectToReqHandler"]

    def test_clear_rules(self, chain_config):
        """清除所有规则。"""
        chain_config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        chain_config.add_rule("loop2.done", "Loop1DefectToReqHandler")
        chain_config.clear_rules()
        assert chain_config.list_rules() == {}

    def test_add_invalid_handler_raises(self, chain_config):
        """添加不存在的 handler 名称应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Unknown target handler"):
            chain_config.add_rule("loop1.done", "NonExistentHandler")

    def test_max_depth_default(self):
        """默认 max_depth 应为 5。"""
        config = ChainConfig()
        assert config.max_depth == 5

    def test_max_depth_setter(self, chain_config):
        """max_depth 可设置。"""
        chain_config.max_depth = 10
        assert chain_config.max_depth == 10

    def test_max_depth_minimum(self, chain_config):
        """max_depth 不能 < 1。"""
        with pytest.raises(ValueError):
            chain_config.max_depth = 0

    def test_handler_event_mapping(self, chain_config):
        """handler → 事件映射应正确。"""
        assert chain_config.get_event_for_handler("Loop1DefectToReqHandler") == LoopEventType.CI_FAILURE
        assert chain_config.get_event_for_handler("Loop2FieldToFMEAHandler") == LoopEventType.FIELD_DEFECT
        assert chain_config.get_event_for_handler("Loop3KPIToImproveHandler") == LoopEventType.KPI_BREACH
        assert chain_config.get_event_for_handler("Loop4KGSelfEvolveHandler") == LoopEventType.TEST_RESULT
        assert chain_config.get_event_for_handler("NonExistent") is None

    def test_reverse_handler_event_mapping(self, chain_config):
        """事件 → handler 反向映射。"""
        assert chain_config.get_handler_for_event(LoopEventType.CI_FAILURE) == "Loop1DefectToReqHandler"
        assert chain_config.get_handler_for_event(LoopEventType.KPI_BREACH) == "Loop3KPIToImproveHandler"

    def test_register_custom_handler_event(self, chain_config):
        """注册自定义 handler → 事件映射。"""
        chain_config.register_handler_event("CustomHandler", LoopEventType.SPEC_CHANGE)
        assert chain_config.get_event_for_handler("CustomHandler") == LoopEventType.SPEC_CHANGE


# ═══════════════════════════════════════════════════════════════════════
# 默认链式规则
# ═══════════════════════════════════════════════════════════════════════

class TestDefaultChainRules:

    def test_default_rules_loaded(self, default_config):
        """默认规则应正确加载。"""
        rules = default_config.list_rules()
        assert "loop1.done" in rules
        assert "loop2.done" in rules
        assert "loop4.confidence_up" in rules

    def test_loop1_done_targets(self, default_config):
        """Loop1_Done → Loop 3 KPI 影响分析 + Loop 4 置信度更新。"""
        targets = default_config.get_targets("loop1.done")
        assert "Loop3KPIToImproveHandler" in targets
        assert "Loop4KGSelfEvolveHandler" in targets
        assert len(targets) == 2

    def test_loop2_done_targets(self, default_config):
        """Loop2_Done → Loop 1 标记安全关键需求。"""
        targets = default_config.get_targets("loop2.done")
        assert targets == ["Loop1DefectToReqHandler"]

    def test_loop4_confidence_up_targets(self, default_config):
        """Loop4_ConfidenceUp → Loop 1 关闭 needs_review。"""
        targets = default_config.get_targets("loop4.confidence_up")
        assert targets == ["Loop1DefectToReqHandler"]

    def test_loop3_done_no_targets(self, default_config):
        """Loop3_Done 默认无目标。"""
        targets = default_config.get_targets("loop3.done")
        assert targets == []

    def test_unconfigured_event_no_targets(self, default_config):
        """未配置的事件应返回空列表。"""
        targets = default_config.get_targets("ci.failure")
        assert targets == []

    def test_default_rules_match_spec(self):
        """默认规则应完全匹配规格说明。

        规格:
          - Loop1_Done → Loop 3 KPI + Loop 4 置信度
          - Loop2_Done → Loop 1 安全关键需求
          - Loop4_ConfidenceUp → Loop 1 关闭 needs_review
        """
        assert DEFAULT_CHAIN_RULES == {
            "loop1.done": ["Loop3KPIToImproveHandler", "Loop4KGSelfEvolveHandler"],
            "loop2.done": ["Loop1DefectToReqHandler"],
            "loop4.confidence_up": ["Loop1DefectToReqHandler"],
        }


# ═══════════════════════════════════════════════════════════════════════
# ChainContext 防循环 / 防重复
# ═══════════════════════════════════════════════════════════════════════

class TestChainContext:

    def test_fresh_context_allows_chain(self):
        """全新的 ChainContext 应允许链式触发。"""
        ctx = ChainContext(max_depth=5)
        assert ctx.can_chain("Loop1DefectToReqHandler", "ci.failure")

    def test_visited_handler_blocked(self):
        """已访问过的 handler 不应再次触发。"""
        ctx = ChainContext(max_depth=5)
        ctx.mark_visited("Loop1DefectToReqHandler", "ci.failure")
        assert not ctx.can_chain("Loop1DefectToReqHandler", "kpi.breach")

    def test_visited_event_blocked(self):
        """已发出过的事件类型不应再次发出。"""
        ctx = ChainContext(max_depth=5)
        ctx.mark_visited("HandlerA", "ci.failure")
        assert not ctx.can_chain("HandlerB", "ci.failure")

    def test_different_handler_same_event_blocked(self):
        """即使 handler 不同，相同事件类型也应被阻断。"""
        ctx = ChainContext(max_depth=5)
        ctx.mark_visited("HandlerA", "ci.failure")
        assert not ctx.can_chain("Loop1DefectToReqHandler", "ci.failure")

    def test_depth_limit_blocks(self):
        """超过 max_depth 应阻断。"""
        ctx = ChainContext(max_depth=2)
        ctx.depth = 2
        assert not ctx.can_chain("Loop1DefectToReqHandler", "ci.failure")

    def test_depth_limit_boundary(self):
        """在深度限制内应允许 (depth < max_depth)。"""
        ctx = ChainContext(max_depth=3)
        ctx.depth = 2
        assert ctx.can_chain("Loop1DefectToReqHandler", "ci.failure")

    def test_child_context_inherits_visited(self):
        """子上下文应继承父上下文的 visited 记录。"""
        parent = ChainContext(max_depth=5)
        parent.mark_visited("HandlerA", "ci.failure")
        child = parent.child_context("HandlerB", "kpi.breach")
        # handlerA 和 ci.failure 仍应在 child 中标记为已访问
        assert "HandlerA" in child.visited_handlers
        assert "ci.failure" in child.visited_events
        # 新 handler 和事件也应标记
        assert "HandlerB" in child.visited_handlers
        assert "kpi.breach" in child.visited_events

    def test_child_context_depth_incremented(self):
        """子上下文的 depth 应 = 父 depth + 1。"""
        parent = ChainContext(max_depth=5)
        parent.depth = 2
        child = parent.child_context("Foo", "bar")
        assert child.depth == 3

    def test_circular_chain_detection(self):
        """循环链 (A→B→A) 应被检测阻断。"""
        ctx = ChainContext(max_depth=5)
        # Phase 1: Trigger A
        assert ctx.can_chain("HandlerA", "event.a")
        ctx.mark_visited("HandlerA", "event.a")
        # Phase 2: A → B
        child1 = ctx.child_context("HandlerB", "event.b")
        # B 不应该再次触发 HandlerA (已访问)
        assert not child1.can_chain("HandlerA", "event.a")
        # B 可以触发 HandlerC
        assert child1.can_chain("HandlerC", "event.c")
        # C → A 应被阻断
        child2 = child1.child_context("HandlerC", "event.c")
        assert not child2.can_chain("HandlerA", "event.a")

    def test_to_dict(self):
        """ChainContext.to_dict() 应包含所有字段。"""
        ctx = ChainContext(root_event_id="evt-001", max_depth=5)
        ctx.mark_visited("HandlerA", "event.a")
        d = ctx.to_dict()
        assert d["depth"] == 0
        assert d["max_depth"] == 5
        assert d["root_event_id"] == "evt-001"
        assert "HandlerA" in d["visited_handlers"]
        assert "event.a" in d["visited_events"]


# ═══════════════════════════════════════════════════════════════════════
# ChainConfig 持久化
# ═══════════════════════════════════════════════════════════════════════

class TestChainPersistence:

    def test_to_dict(self, default_config):
        """to_dict() 应正确序列化。"""
        d = default_config.to_dict()
        assert d["max_depth"] == 5
        assert "loop1.done" in d["rules"]
        assert "Loop3KPIToImproveHandler" in d["rules"]["loop1.done"]

    def test_from_dict(self):
        """from_dict() 应正确反序列化。"""
        data = {
            "max_depth": 10,
            "rules": {
                "loop1.done": ["Loop3KPIToImproveHandler"],
                "loop2.done": ["Loop1DefectToReqHandler"],
            },
        }
        config = ChainConfig.from_dict(data)
        assert config.max_depth == 10
        assert config.get_targets("loop1.done") == ["Loop3KPIToImproveHandler"]
        assert config.get_targets("loop2.done") == ["Loop1DefectToReqHandler"]

    def test_save_and_load(self, tmp_path, default_config):
        """save/load 应对称。"""
        path = str(tmp_path / "chain_config.json")
        default_config.save(path)
        assert os.path.exists(path)

        loaded = ChainConfig.load(path)
        assert loaded.max_depth == default_config.max_depth
        assert loaded.list_rules() == default_config.list_rules()

    def test_load_nonexistent_file_returns_defaults(self, tmp_path):
        """加载不存在的文件应返回默认配置。"""
        path = str(tmp_path / "nonexistent.json")
        config = ChainConfig.load(path)
        # 默认应该加载了默认规则
        assert config.max_depth == 5
        assert "loop1.done" in config.list_rules()

    def test_persistence_roundtrip_custom(self, tmp_path):
        """自定义规则 save/load 应完整恢复。"""
        path = str(tmp_path / "custom_chain.json")
        config = ChainConfig(max_depth=7)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        config.add_rule("kpi.breach", "Loop1DefectToReqHandler")
        config.add_rule("field.defect", "Loop4KGSelfEvolveHandler")
        config.save(path)

        loaded = ChainConfig.load(path)
        assert loaded.max_depth == 7
        assert loaded.get_targets("ci.failure") == ["Loop3KPIToImproveHandler"]
        assert loaded.get_targets("kpi.breach") == ["Loop1DefectToReqHandler"]
        assert loaded.get_targets("field.defect") == ["Loop4KGSelfEvolveHandler"]


# ═══════════════════════════════════════════════════════════════════════
# SystemEventBus 链式触发集成
# ═══════════════════════════════════════════════════════════════════════

class TestChainIntegration:

    def test_chain_enabled_with_config(self, clean_bus):
        """设置了 chain_config 后 chain_enabled 应为 True。"""
        config = ChainConfig()
        config.load_defaults()
        clean_bus.chain_config = config
        assert clean_bus.chain_enabled

    def test_chain_disabled_without_config(self, clean_bus):
        """未设置 chain_config 时 chain_enabled 应为 False。"""
        clean_bus._chain_config = None
        assert not clean_bus.chain_enabled

    def test_chain_trigger_after_handler_completes(self, clean_bus):
        """handler 完成后应触发链式规则的目标事件。"""
        config = ChainConfig(max_depth=3)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        # 订阅目标事件 (Loop 3 handler 订阅的事件)
        target_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target_cb)

        # 订阅并执行 Loop 1 handler (对 CI_FAILURE 做处理)
        loop1_cb = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, loop1_cb)

        # 发出 CI_FAILURE → 应触发 Loop1 handler → 链式触发 KPI_BREACH
        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test_name": "test_foo"})

        # 验证 Loop 1 handler 被调用
        loop1_cb.assert_called_once()
        # 验证链式触发目标事件
        target_cb.assert_called_once()
        event = target_cb.call_args[0][0]
        assert event.event_type == LoopEventType.KPI_BREACH
        assert event.source == "loop_engine.chain"

    def test_chain_carries_original_data(self, clean_bus):
        """链式触发事件应继承原始事件数据。"""
        config = ChainConfig(max_depth=3)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        target_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target_cb)

        loop1_cb = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, loop1_cb)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={
            "test_name": "test_brake",
            "error": "AssertionError",
        })

        target_cb.assert_called_once()
        event = target_cb.call_args[0][0]
        assert event.data["test_name"] == "test_brake"
        assert event.data["_chain_trigger"] == "ci.failure"
        assert event.data["_chain_depth"] == 1
        assert event.data["_chain_root_event_id"] is not None
        assert event.data["_chain_target"] == "Loop3KPIToImproveHandler"

    def test_multi_target_chain(self, clean_bus):
        """一个事件可以触发多个目标 handler。"""
        config = ChainConfig(max_depth=3)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        config.add_rule("ci.failure", "Loop4KGSelfEvolveHandler")
        clean_bus.chain_config = config

        target3_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target3_cb)

        # 订阅 REVIEW_FINDING 而不是 TEST_RESULT
        # (TEST_RESULT 有通配符行为, 会收到所有事件)
        target_review_cb = Mock()
        clean_bus.on(LoopEventType.REVIEW_FINDING, target_review_cb)

        # 注册 Loop4 handler 的自定义事件映射
        config.register_handler_event("Loop4KGSelfEvolveHandler",
                                       LoopEventType.REVIEW_FINDING)

        loop1_cb = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, loop1_cb)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "x"})

        loop1_cb.assert_called_once()
        target3_cb.assert_called_once()
        target_review_cb.assert_called_once()

    def test_chain_not_trigger_if_no_matching_rule(self, clean_bus):
        """没有匹配规则时不应触发链式。"""
        config = ChainConfig(max_depth=3)
        config.add_rule("loop1.done", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        target_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target_cb)

        # 发出 CI_FAILURE (没有链式规则直接映射 ci.failure)
        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "x"})

        target_cb.assert_not_called()

    def test_chain_works_with_multiple_rules(self, clean_bus):
        """多条规则应独立生效。"""
        config = ChainConfig(max_depth=5)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        config.add_rule("field.defect", "Loop1DefectToReqHandler")
        clean_bus.chain_config = config

        kpi_cb = Mock()
        ci_calls = [0]
        clean_bus.on(LoopEventType.KPI_BREACH, kpi_cb)

        def track_ci(event):
            ci_calls[0] += 1
        clean_bus.on(LoopEventType.CI_FAILURE, track_ci)

        field_cb = Mock()
        clean_bus.on(LoopEventType.FIELD_DEFECT, field_cb)

        # 触发 ci.failure → 链式到 KPI_BREACH
        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
        kpi_cb.assert_called_once()
        # CI_FAILURE 由 initial emit 触发, 不是链式
        assert ci_calls[0] == 1  # 只有 initial emit 触发

    def test_default_rules_work_in_bus(self, clean_bus):
        """默认链式规则在 EventBus 中应正常工作。"""
        config = ChainConfig(max_depth=5)
        config.load_defaults()
        clean_bus.chain_config = config

        # 订阅可能被链式触发的事件 (不使用 TEST_RESULT, 避免通配符行为)
        kpi_cb = Mock()
        ci_cb = Mock()
        review_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, kpi_cb)
        clean_bus.on(LoopEventType.CI_FAILURE, ci_cb)
        clean_bus.on(LoopEventType.REVIEW_FINDING, review_cb)

        # Loop 1 handler (CI_FAILURE 监听者)
        loop1_cb = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, loop1_cb)

        # 触发 Loop 1
        clean_bus.emit(LoopEventType.CI_FAILURE, data={
            "test_name": "test_brake",
            "error": "fail",
        })

        # Loop 1 handler 被调用
        loop1_cb.assert_called_once()
        # 默认规则是基于 loop1.done 不是 ci.failure, 所以不会链式触发
        kpi_cb.assert_not_called()

    def test_chain_context_passed_in_data(self, clean_bus):
        """链式事件的数据应包含 chain context。"""
        config = ChainConfig(max_depth=5)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        target_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target_cb)

        loop1_cb = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, loop1_cb)

        event = clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "context"})

        target_cb.assert_called_once()
        chain_data = target_cb.call_args[0][0].data
        assert chain_data["_chain_root_event_id"] == event.event_id
        assert chain_data["_chain_depth"] == 1
        assert chain_data["_chain_trigger"] == "ci.failure"


# ═══════════════════════════════════════════════════════════════════════
# 循环保护
# ═══════════════════════════════════════════════════════════════════════

class TestCircularProtection:

    def test_circular_chain_blocked(self, clean_bus):
        """A→B→A 循环应被阻断。"""
        config = ChainConfig(max_depth=5)
        # A (ci.failure) → B (kpi.breach) → A (ci.failure) 循环
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")  # ci.failure → KPI_BREACH
        config.add_rule("kpi.breach", "Loop1DefectToReqHandler")  # kpi.breach → CI_FAILURE
        clean_bus.chain_config = config

        ci_count = [0]
        kpi_count = [0]

        def on_ci(event):
            ci_count[0] += 1

        def on_kpi(event):
            kpi_count[0] += 1

        clean_bus.on(LoopEventType.CI_FAILURE, on_ci)
        clean_bus.on(LoopEventType.KPI_BREACH, on_kpi)

        # 触发 CI_FAILURE
        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "circular"})

        # 应只触发一次 CI (由 emit 触发), 一次 KPI (链式触发)
        # 循环应被阻断: CI → KPI → CI (blocked because CI already visited)
        assert ci_count[0] == 1, f"Expected 1 CI, got {ci_count[0]}"
        assert kpi_count[0] == 1, f"Expected 1 KPI, got {kpi_count[0]}"

    def test_multi_level_circular_chain(self, clean_bus):
        """多层循环链应被阻断。"""
        config = ChainConfig(max_depth=5)
        # A→B→C→A 循环 (使用非 TEST_RESULT, 避免通配符行为)
        config.register_handler_event("Loop4KGSelfEvolveHandler",
                                       LoopEventType.REVIEW_FINDING)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")  # → KPI_BREACH
        config.add_rule("kpi.breach", "Loop4KGSelfEvolveHandler")  # → REVIEW_FINDING
        config.add_rule("review.finding", "Loop1DefectToReqHandler")  # → CI_FAILURE
        clean_bus.chain_config = config

        counts = {"ci": 0, "kpi": 0, "review": 0}

        def on_ci(event):
            counts["ci"] += 1

        def on_kpi(event):
            counts["kpi"] += 1

        def on_review(event):
            counts["review"] += 1

        clean_bus.on(LoopEventType.CI_FAILURE, on_ci)
        clean_bus.on(LoopEventType.KPI_BREACH, on_kpi)
        clean_bus.on(LoopEventType.REVIEW_FINDING, on_review)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "multi-circular"})

        # CI emit 1 → KPI (chain 1) → REVIEW (chain 2) → CI (chain 3, blocked)
        assert counts["ci"] == 1, f"Expected 1 CI, got {counts['ci']}"
        assert counts["kpi"] == 1, f"Expected 1 KPI, got {counts['kpi']}"
        assert counts["review"] == 1, f"Expected 1 REVIEW, got {counts['review']}"

    def test_self_loop_blocked(self, clean_bus):
        """自循环 (A→A) 应被阻断。"""
        config = ChainConfig(max_depth=5)
        # 自己触发自己
        config.add_rule("ci.failure", "Loop1DefectToReqHandler")
        clean_bus.chain_config = config

        ci_count = [0]

        def on_ci(event):
            ci_count[0] += 1

        clean_bus.on(LoopEventType.CI_FAILURE, on_ci)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "self-loop"})

        # 只触发一次
        assert ci_count[0] == 1, f"Expected 1, got {ci_count[0]}"


# ═══════════════════════════════════════════════════════════════════════
# 深度保护
# ═══════════════════════════════════════════════════════════════════════

class TestDepthProtection:

    def test_depth_limit_enforced(self, clean_bus):
        """超过 max_chain_depth 应自动终止。"""
        config = ChainConfig(max_depth=2)
        # 线性链: A→B→C→D (不使用 TEST_RESULT, 避免通配符)
        config.register_handler_event("Loop4KGSelfEvolveHandler",
                                       LoopEventType.REVIEW_FINDING)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")  # → KPI_BREACH (depth 1)
        config.add_rule("kpi.breach", "Loop4KGSelfEvolveHandler")  # → REVIEW_FINDING (depth 2)
        config.add_rule("review.finding", "Loop1DefectToReqHandler")  # → CI_FAILURE (depth 3, blocked)
        clean_bus.chain_config = config

        counts = {"ci": 0, "kpi": 0, "review": 0}

        def on_ci(event):
            counts["ci"] += 1

        def on_kpi(event):
            counts["kpi"] += 1

        def on_review(event):
            counts["review"] += 1

        clean_bus.on(LoopEventType.CI_FAILURE, on_ci)
        clean_bus.on(LoopEventType.KPI_BREACH, on_kpi)
        clean_bus.on(LoopEventType.REVIEW_FINDING, on_review)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "depth-limit"})

        # max_depth=2, so: CI (depth 0) → KPI (depth 1) → REVIEW (depth 2) → CI (depth 3, blocked)
        assert counts["ci"] == 1, f"Expected 1 CI, got {counts['ci']}"
        assert counts["kpi"] == 1, f"Expected 1 KPI, got {counts['kpi']}"
        assert counts["review"] == 1, f"Expected 1 REVIEW, got {counts['review']}"

    def test_depth_limit_customizable(self, clean_bus):
        """max_depth 可自定义。"""
        config = ChainConfig(max_depth=1)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        kpi_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, kpi_cb)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "shallow"})

        # max_depth=1: CI (depth 0) → KPI (depth 1, max_depth reached)
        # Wait, max_depth=1 means depth < 1 for can_chain. Depth starts at 0.
        # In child_context, depth becomes 1. can_chain checks depth >= max_depth.
        # depth=1 >= max_depth=1, so blocked.
        # So KPI should NOT be called.
        kpi_cb.assert_not_called()

    def test_depth_0_no_chaining(self, clean_bus):
        """max_depth=0 时应不允许任何链式触发 (但最小值被 clamp 到 1)。"""
        # max_depth 最小值为 1
        config = ChainConfig(max_depth=1)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        kpi_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, kpi_cb)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "no-chain"})

        # max_depth=1, 链式 depth=1 时拒绝, 所以 KPI 不被触发
        kpi_cb.assert_not_called()

    def test_set_chain_max_depth(self, clean_bus):
        """set_chain_max_depth 方法应生效。"""
        config = ChainConfig(max_depth=5)
        clean_bus.chain_config = config

        clean_bus.set_chain_max_depth(3)
        assert clean_bus.chain_config.max_depth == 3


# ═══════════════════════════════════════════════════════════════════════
# 向后兼容
# ═══════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:

    def test_existing_subscriptions_still_work(self, clean_bus):
        """现有订阅应不受影响。"""
        callback = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, callback)

        config = ChainConfig(max_depth=5)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        kpi_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, kpi_cb)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "compat"})

        # 原始 handler 仍被调用
        callback.assert_called_once()
        # 链式触发也生效
        kpi_cb.assert_called_once()

    def test_existing_stats_still_work(self, clean_bus):
        """现有 stats() 应包含但不受链式影响。"""
        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "a"})
        stats = clean_bus.stats()
        assert stats["total_emitted"] == 1
        # chain 字段应存在
        assert "chain" in stats

    def test_no_chain_config_does_not_break_anything(self, clean_bus):
        """不配置 chain 不应破坏任何功能。"""
        clean_bus._chain_config = None

        callback = Mock()
        clean_bus.on(LoopEventType.CI_FAILURE, callback)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "no-chain-config"})

        callback.assert_called_once()
        assert clean_bus.stats()["total_emitted"] == 1

    def test_old_event_types_unchanged(self):
        """已有事件类型不应被修改。"""
        assert LoopEventType.CI_FAILURE.value == "ci.failure"
        assert LoopEventType.REVIEW_FINDING.value == "review.finding"
        assert LoopEventType.KPI_BREACH.value == "kpi.breach"
        assert LoopEventType.FIELD_DEFECT.value == "field.defect"
        assert LoopEventType.TEST_RESULT.value == "test.result"
        assert LoopEventType.SPEC_CHANGE.value == "spec.change"


# ═══════════════════════════════════════════════════════════════════════
# 集成测试
# ═══════════════════════════════════════════════════════════════════════

class TestChainIntegrationFull:

    def test_full_chain_pipeline(self, clean_bus):
        """完整链式流水线: emit → handler → chain → handler. """
        config = ChainConfig(max_depth=5)
        # 使用 REVIEW_FINDING 替代 TEST_RESULT (避免通配符)
        config.register_handler_event("Loop4KGSelfEvolveHandler",
                                       LoopEventType.REVIEW_FINDING)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        config.add_rule("kpi.breach", "Loop4KGSelfEvolveHandler")
        clean_bus.chain_config = config

        calls = []

        def on_ci(event):
            calls.append("ci")

        def on_kpi(event):
            calls.append("kpi")

        def on_review(event):
            calls.append("review")

        clean_bus.on(LoopEventType.CI_FAILURE, on_ci)
        clean_bus.on(LoopEventType.KPI_BREACH, on_kpi)
        clean_bus.on(LoopEventType.REVIEW_FINDING, on_review)

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "pipeline"})

        # CI → KPI (chain depth 1) → REVIEW (chain depth 2)
        assert calls == ["ci", "kpi", "review"], f"Expected sequence ci,kpi,review; got {calls}"

    def test_stats_contains_chain_info(self, clean_bus):
        """stats() 应包含链式配置信息。"""
        config = ChainConfig(max_depth=5)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        stats = clean_bus.stats()
        assert "chain" in stats
        assert stats["chain"]["max_depth"] == 5
        assert stats["chain"]["active_rules"] == 1

    def test_chain_config_accessible_on_bus(self, clean_bus):
        """EventBus 的 chain_config 应可访问和设置。"""
        assert clean_bus.chain_config is not None
        assert "chain" in clean_bus.stats()

    def test_clear_chain_context(self, clean_bus):
        """clear_chain_context 应重置跟踪。"""
        config = ChainConfig(max_depth=5)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        clean_bus.clear_chain_context()
        assert clean_bus._chain_context is None

    def test_chain_source_is_engine_chain(self, clean_bus):
        """链式触发事件 source 应为 'loop_engine.chain'。"""
        config = ChainConfig(max_depth=3)
        config.add_rule("ci.failure", "Loop3KPIToImproveHandler")
        clean_bus.chain_config = config

        target_cb = Mock()
        clean_bus.on(LoopEventType.KPI_BREACH, target_cb)

        clean_bus.on(LoopEventType.CI_FAILURE, Mock())

        clean_bus.emit(LoopEventType.CI_FAILURE, data={"test": "source_check"})

        target_cb.assert_called_once()
        event = target_cb.call_args[0][0]
        assert event.source == "loop_engine.chain"
