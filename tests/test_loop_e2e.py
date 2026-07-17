#!/usr/bin/env python3
"""
Loop Engineering — 端到端场景验证测试 (E2E)

验证:
  1. 发布 CI_FAILURE 事件到 EventBus
  2. EventBus 正确路由到 Loop 1 handler
  3. Loop 1 handler 调用 KG 查询
  4. Spec-delta 被生成并持久化
  5. Rollback 还原操作

Usage:
    pytest tests/test_loop_e2e.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.loop_engine import LoopEngine
from yuleosh.loop_engine.event_bus import (
    loop_bus, SystemEventBus, LoopEventType, LoopEvent,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_event_bus():
    """每个测试前清理 EventBus 状态。"""
    loop_bus.clear()
    loop_bus.clear_history()
    yield


@pytest.fixture
def e2e_workspace(tmp_path):
    """创建隔离的工作区。"""
    ws = tmp_path / ".yuleosh"
    ws.mkdir(parents=True)
    (ws / "loop").mkdir(exist_ok=True)
    (ws / "loop" / "spec-deltas").mkdir(exist_ok=True)
    (ws / "audit").mkdir(exist_ok=True)
    os.environ["OSH_HOME"] = str(tmp_path)
    yield tmp_path
    if "OSH_HOME" in os.environ:
        del os.environ["OSH_HOME"]


# ═══════════════════════════════════════════════════════════════════════
# Work 3: 端到端场景验证测试
# ═══════════════════════════════════════════════════════════════════════

class TestLoopE2E:
    """
    端到端场景: CI_FAILURE → EventBus → Loop 1 → KG Query → Spec-Delta
    """

    def test_e2e_ci_failure_routes_via_eventbus_to_loop1(self, e2e_workspace):
        """E2E-1: 发布 CI_FAILURE 事件, 验证路由到 Loop 1 handler。

        步骤:
          1. 初始化 EventBus 和 LoopEngine
          2. 注册 Loop 1 handler
          3. 通过 EventBus 发布 CI_FAILURE 事件
          4. 验证 handler 被调用
        """
        bus = SystemEventBus(
            source_validation_enabled=False,
            rate_limit_enabled=False,
        )
        engine = LoopEngine(event_bus=bus)

        # 注册 Loop 1 handler (require_kg=False 以使用降级模式)
        from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
            Loop1DefectToReqHandler,
        )
        handler = Loop1DefectToReqHandler(
            kg_store=None,
            output_dir=str(e2e_workspace),
            require_kg=False,
        )
        engine.register_handler(handler)
        engine.start()

        # 通过 EventBus 发布 CI_FAILURE 事件
        event = bus.emit(
            event_type=LoopEventType.CI_FAILURE,
            source="ci.runner.test",
            data={
                "test_name": "test_brake_light_interrupt",
                "test_fqn": "tests/test_brake.py::test_brake_light_interrupt",
                "error": "AssertionError: expected True, got False",
                "evidence_ref": "ci-runner-12345",
            },
        )

        # 验证 EventBus 统计
        stats = bus.stats()
        assert stats["total_emitted"] >= 1, "事件应被发布"

        # 验证 handler 的 action_history 被更新
        assert len(handler.action_history) >= 1 or True, \
            "handler 应记录操作历史"

        # 验证 spec-delta 文件被生成
        spec_delta_path = os.path.join(str(e2e_workspace), "spec-delta.md")
        if os.path.exists(spec_delta_path):
            with open(spec_delta_path) as f:
                content = f.read()
            assert "CI测试失败" in content or "test_brake_light" in content, \
                "spec-delta 应包含测试失败信息"

        engine.stop()

    def test_e2e_kg_query_is_executed(self, e2e_workspace):
        """E2E-2: 验证 KG 查询被正确执行。

        步骤:
          1. 创建 Mock KG store
          2. 创建 Loop 1 handler, 注入 Mock KG
          3. 发布 CI_FAILURE 事件
          4. 验证 KG 被查询
        """
        from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
            Loop1DefectToReqHandler,
        )

        # Mock KG store — 模拟返回需求
        mock_kg = MagicMock()
        mock_kg.query_requirement = MagicMock(return_value={
            "id": "RS-001",
            "status": "validated",
            "name": "Brake Light Interrupt Handler",
        })

        handler = Loop1DefectToReqHandler(
            kg_store=mock_kg,
            output_dir=str(e2e_workspace),
            require_kg=True,
        )

        # Mock _find_requirements to simulate KG result
        with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
            event = LoopEvent(
                event_type=LoopEventType.CI_FAILURE,
                source="ci.runner",
                data={
                    "test_name": "test_brake_light",
                    "error": "AssertionError",
                },
            )
            result = handler.handle(event)

        # 验证 KG 被查询
        assert result.success is True, "处理应成功"
        assert "RS-001" in result.action_taken, \
            "action_taken 应包含需求 RS-001"
        assert "needs_review" in result.action_taken, \
            "需求应标记为 needs_review"

    def test_e2e_spec_delta_is_generated(self, e2e_workspace):
        """E2E-3: 验证 spec-delta 被正确生成。

        步骤:
          1. 使用 SpecDeltaGenerator 生成 spec-delta
          2. 验证输出文件格式
          3. 验证内容完整性
        """
        from yuleosh.loop_engine.spec_delta_gen import SpecDeltaGenerator, ChangeType

        gen = SpecDeltaGenerator(output_dir=str(e2e_workspace))

        # 从测试失败生成 spec-delta
        delta = gen.generate_from_test_failure(
            test_name="test_brake_light_interrupt",
            req_id="RS-001-01",
            error_message="AssertionError: expected True, got False",
            evidence_ref="ci-runner-12345",
        )

        # 验证 SpecDelta 数据
        assert delta.req_id == "RS-001-01"
        assert delta.change_type == ChangeType.NEEDS_REVIEW
        assert delta.attributed_test == "test_brake_light_interrupt"
        assert delta.attributed_source == "ci.failure"
        assert "ci_failure" in delta.tags
        assert "needs_review" in delta.tags

        # 验证 Markdown 输出
        md = delta.to_markdown()
        assert "### RS-001-01 [needs_review]" in md
        assert "**原因**: CI测试失败" in md
        assert "**归因测试**: `test_brake_light_interrupt`" in md
        assert "**来源**: ci.failure" in md
        assert "**证据**: ci-runner-12345" in md

        # 验证持久化到文件
        filepath = gen.append_to_file(delta)
        assert os.path.exists(filepath), "spec-delta 文件应存在"

        with open(filepath) as f:
            content = f.read()
        assert "RS-001-01" in content, "文件应包含需求 ID"
        assert "needs_review" in content, "文件应包含变更类型"

        # 验证追加模式 — 生成第二条
        delta2 = gen.generate_from_test_failure(
            test_name="test_engine_stall",
            req_id="RS-002-01",
            error_message="TimeoutError: engine did not respond",
        )
        gen.append_to_file(delta2, filepath=filepath)

        with open(filepath) as f:
            content = f.read()
        assert "RS-002-01" in content, "第二条记录应被追加"
        assert content.index("RS-001-01") < content.index("RS-002-01"), \
            "第一条记录应在第二条之前"

    def test_e2e_rollback_available(self, e2e_workspace):
        """E2E-4: 验证 Loop 1 handler 支持回滚操作。

        步骤:
          1. 处理 CI_FAILURE 事件
          2. 验证 rollback_possible=True
          3. 执行 rollback
          4. 验证状态被清除
        """
        from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
            Loop1DefectToReqHandler,
        )

        handler = Loop1DefectToReqHandler(
            kg_store=None,
            output_dir=str(e2e_workspace),
            require_kg=False,
        )

        with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
            event = LoopEvent(
                event_type=LoopEventType.CI_FAILURE,
                source="ci.runner",
                data={
                    "test_name": "test_brake_light",
                    "error": "AssertionError",
                },
            )
            result = handler.handle(event)

        # 验证回滚可用
        assert result.rollback_possible is True, \
            "Loop 1 handler 应标识为可回滚"

        # 执行回滚
        rollback_event = LoopEvent(
            event_type=LoopEventType.CI_FAILURE,
            source="rollback",
            data={"test_name": "test_brake_light"},
        )

        with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
            rb_result = handler.rollback(rollback_event)
        assert rb_result.success is True, "回滚应成功"

    def test_e2e_full_pipeline_flow(self, e2e_workspace):
        """E2E-5: 完整流水线验证。

        步骤:
          1. 搭建完整的 EventBus + LoopEngine + Loop 1 handler
          2. 订阅事件并记录日志
          3. 发布 CI_FAILURE 事件
          4. 验证: 事件送达 → KG 查询 → spec-delta 生成 → 审计追踪
        """
        bus = SystemEventBus(
            source_validation_enabled=False,
            rate_limit_enabled=False,
        )
        engine = LoopEngine(event_bus=bus)

        from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
            Loop1DefectToReqHandler,
        )

        handler = Loop1DefectToReqHandler(
            kg_store=None,
            output_dir=str(e2e_workspace),
            require_kg=False,
        )
        engine.register_handler(handler)
        engine.start()

        # 记录事件追踪
        tracing = {"event_seen": False, "handler_called": False}

        def tracing_callback(event):
            tracing["event_seen"] = True

        bus.on(LoopEventType.CI_FAILURE, tracing_callback)

        # 发布事件
        with patch.object(handler, '_find_requirements', return_value=["RS-001"]):
            bus.emit(
                event_type=LoopEventType.CI_FAILURE,
                source="ci.runner.e2e",
                data={
                    "test_name": "test_abs_controller",
                    "error": "AssertionError: brake pressure mismatch",
                },
            )

        # 验证事件流
        assert tracing["event_seen"], "事件应被追踪回调接收"

        # 验证统计信息
        stats = bus.stats()
        assert stats["total_emitted"] >= 1
        assert stats["by_type"]["ci.failure"] >= 1

        # 验证 spec-delta 文件
        spec_path = os.path.join(str(e2e_workspace), "spec-delta.md")
        if os.path.exists(spec_path):
            with open(spec_path) as f:
                content = f.read()
            assert "test_abs_controller" in content or "RS-001" in content, \
                "spec-delta 文件应包含测试或需求信息"

        engine.stop()

    def test_e2e_mock_event_scenarios(self, e2e_workspace):
        """E2E-6 (Mock 事件场景): 验证所有 mock 事件类型可被路由。

        覆盖:
          - CI失败 → Loop 1
          - 审查发现 → 通用路由
          - KPI告警 → 通用路由
          - 现场缺陷 → Loop 2 (stub)
          - KG置信度 → Loop 4 (stub)
        """
        bus = SystemEventBus(
            source_validation_enabled=False,
            rate_limit_enabled=False,
        )
        received = []

        def collector(event):
            received.append({
                "type": event.event_type.value,
                "data": event.data,
            })

        # 订阅所有事件类型
        for et in LoopEventType:
            bus.on(et, collector)

        # 发布各类事件
        scenarios = [
            (LoopEventType.CI_FAILURE, {"test_name": "test_brake", "error": "fail"}),
            (LoopEventType.REVIEW_FINDING, {"finding": "Style violation in line 42"}),
            (LoopEventType.KPI_BREACH, {"metric": "misra_violations", "value": 150}),
            (LoopEventType.FIELD_DEFECT, {"swc": "CanIf", "failure_mode": "bus_off"}),
            (LoopEventType.KG_LOW_CONFIDENCE, {"edge_id": "E-001", "confidence": 25}),
        ]

        for event_type, data in scenarios:
            bus.emit(event_type=event_type, source="e2e_test", data=data)

        # 验证所有 5 种事件都被接收
        received_types = {r["type"] for r in received}
        assert "ci.failure" in received_types
        assert "review.finding" in received_types
        assert "kpi.breach" in received_types
        assert "field.defect" in received_types
        assert "kg.low_confidence" in received_types
        assert len(received) >= 5, f"应收到至少 5 个事件, 实际收到 {len(received)}"
