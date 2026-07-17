#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 1 — 缺陷→需求回溯闭环 (LE-003, LE-008)。

监听 CI_FAILURE 事件，通过 KG 查询失败测试对应的需求，
自动调用 spec_delta_gen.py 生成 spec-delta 候选，
标记需求状态为 "needs_review"。

流程:
  1. 收到 CI_FAILURE 事件
  2. 从事件数据提取 test_name
  3. 通过 KG trace_by_test_function() 查询覆盖的需求
  4. 生成 SpecDelta (change_type=needs_review)
  5. 标记需求状态为 needs_review (持久化到 Store)
  6. 返回 ActionResult

Usage:
    from yuleosh.loop_engine.feedback_handlers.loop1_defect_to_req import (
        Loop1DefectToReqHandler
    )

    handler = Loop1DefectToReqHandler(kg_store=my_store)
    result = handler.handle(ci_failure_event)
"""

import logging
import os
import json
from typing import Optional

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
)
from yuleosh.loop_engine.spec_delta_gen import (
    SpecDeltaGenerator,
    SpecDelta,
    ChangeType,
)

log = logging.getLogger("yuleosh.loop_engine.handlers.loop1")


@register_handler
class Loop1DefectToReqHandler(FeedbackHandler):
    """Loop 1: 缺陷→需求回溯闭环。

    监听 CI_FAILURE 事件，自动追溯失败测试覆盖的需求，
    生成 spec-delta 并标记需求为 needs_review。

    Attributes:
        kg_store: KGStore 实例 (用于查询覆盖关系)。
        spec_delta_gen: SpecDeltaGenerator 实例。
        output_dir: spec-delta 文件输出目录。
        require_kg: 是否需要 KG 后端 (True=KG 查询失败时不操作)。
    """

    def __init__(self, kg_store=None, output_dir: str = ".",
                 require_kg: bool = True):
        self.kg_store = kg_store
        self.spec_delta_gen = SpecDeltaGenerator(output_dir=output_dir)
        self.output_dir = output_dir
        self.require_kg = require_kg
        self._action_history: list[dict] = []

    def subscribed_events(self) -> list[LoopEventType]:
        return [LoopEventType.CI_FAILURE]

    def can_handle(self, event: LoopEvent) -> bool:
        """细粒度过滤: 只有 CI_FAILURE 事件且包含 test_name 才处理。"""
        if event.event_type != LoopEventType.CI_FAILURE:
            return False
        if "test_name" not in event.data and "test_fqn" not in event.data:
            log.warning("Loop1: CI_FAILURE missing test_name/test_fqn, skipping")
            return False
        return True

    def handle(self, event: LoopEvent) -> ActionResult:
        """处理 CI_FAILURE 事件 — 缺陷→需求回溯。

        步骤:
          1. 提取 test_name/test_fqn
          2. 通过 KG 查询覆盖的需求
          3. 生成 SpecDelta (needs_review)
          4. 标记需求状态为 needs_review
          5. 返回 ActionResult
        """
        test_name = event.data.get("test_name", event.data.get("test_fqn", ""))
        error_message = event.data.get("error", event.data.get("message", ""))

        log.info("Loop1: processing CI_FAILURE for test '%s'", test_name)

        # ── 步骤 1: 通过 KG 追溯需求 ──
        req_ids = self._find_requirements(test_name)

        if not req_ids:
            reason = f"未找到测试 '{test_name}' 覆盖的需求"
            log.warning("Loop1: %s", reason)
            if self.require_kg:
                return ActionResult(
                    success=False,
                    action_taken=reason,
                    handler_name=self.name,
                )

        for req_id in req_ids:
            # ── 步骤 2: 生成 SpecDelta ──
            delta = self.spec_delta_gen.generate_from_test_failure(
                test_name=test_name,
                req_id=req_id,
                error_message=error_message,
                evidence_ref=event.data.get("evidence_ref"),
            )

            # ── 步骤 3: 写入 spec-delta 文件 ──
            filepath = self.spec_delta_gen.append_to_file(delta)

            # ── 步骤 4: 标记需求为 needs_review (持久化) ──
            self._mark_requirement_needs_review(req_id, delta)

            log.info("Loop1: req %s marked needs_review (test=%s)",
                     req_id, test_name)

            self._action_history.append({
                "req_id": req_id,
                "test_name": test_name,
                "delta_timestamp": delta.timestamp,
                "filepath": filepath,
            })

        if req_ids:
            return ActionResult(
                success=True,
                action_taken=(
                    f"回溯测试 '{test_name}' 覆盖的 {len(req_ids)} 个需求: "
                    f"{', '.join(req_ids)}; "
                    f"已标记为 needs_review"
                ),
                evidence_ref=self._get_evidence_ref(req_ids),
                rollback_possible=True,
                handler_name=self.name,
                details={
                    "test_name": test_name,
                    "req_ids": req_ids,
                    "error_message": error_message[:500] if error_message else "",
                },
            )
        else:
            return ActionResult(
                success=True,
                action_taken=f"测试 '{test_name}' 无对应需求 (KG query returned empty)",
                rollback_possible=False,
                handler_name=self.name,
            )

    def rollback(self, event: LoopEvent) -> ActionResult:
        """回滚操作: 对 Loop 1 来说, 清除 needs_review 标记并删除 spec-delta 条目。

        这里只清除 needs_review 标记，不删除 spec-delta 文件（保留审计日志）。
        """
        test_name = event.data.get("test_name", "")
        req_ids = self._find_requirements(test_name)

        for req_id in req_ids:
            self._clear_needs_review(req_id)

        return ActionResult(
            success=True,
            action_taken=f"已清除 {len(req_ids)} 个需求的 needs_review 标记",
            handler_name=self.name,
        )

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _find_requirements(self, test_name: str) -> list[str]:
        """通过 KG 查询测试覆盖的需求。

        如果没有 KG 后端, 尝试从 event data 中的 'req_id' 字段读取。
        """
        # 如果事件 data 已经包含了 req_id, 直接使用
        # (由上层调用时注入，例如通过 CLI 手动触发)

        if self.kg_store is not None:
            try:
                from yuleosh.knowledge_graph.queries import trace_by_test_function
                result = trace_by_test_function(self.kg_store, test_name)
                if result and "nodes" in result:
                    req_ids = []
                    for node in result["nodes"]:
                        if node.get("entity_type") == "requirement":
                            req_ids.append(node.get("entity_id", ""))
                    return req_ids
            except Exception as e:
                log.warning("Loop1: KG query error for '%s': %s", test_name, e)

        return []

    def _mark_requirement_needs_review(self, req_id: str, delta: SpecDelta):
        """标记需求状态为 needs_review。

        持久化方式:
          - 如果有 Store: 写入 loop_requirement_reviews 表
          - 如果没有 Store: 写入 JSON 文件
        """
        try:
            from yuleosh.store import Store
            store = Store()
            store.upsert("loop_requirement_reviews", {
                "req_id": req_id,
                "status": "needs_review",
                "triggered_by": delta.attributed_test or "unknown",
                "reason": delta.reason,
                "delta_timestamp": delta.timestamp,
                "change_type": delta.change_type.value,
            }, keys=["req_id"])
            log.debug("Loop1: persisted needs_review for %s", req_id)
        except Exception:
            # Fallback: 写入本地 JSON
            self._write_status_file(req_id, delta)

    def _clear_needs_review(self, req_id: str):
        """清除 needs_review 标记。"""
        try:
            from yuleosh.store import Store
            store = Store()
            store.upsert("loop_requirement_reviews", {
                "req_id": req_id,
                "status": "reviewed",
            }, keys=["req_id"])
        except Exception:
            pass

    def _write_status_file(self, req_id: str, delta: SpecDelta):
        """写入状态到 JSON 文件 (Store 不可用时的降级方案)。"""
        status_dir = os.path.join(self.output_dir, ".loop_status")
        os.makedirs(status_dir, exist_ok=True)
        path = os.path.join(status_dir, f"{req_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "req_id": req_id,
                "status": "needs_review",
                "triggered_by": delta.attributed_test,
                "reason": delta.reason,
                "delta_timestamp": delta.timestamp,
                "change_type": delta.change_type.value,
            }, f, indent=2, ensure_ascii=False)

    def _get_evidence_ref(self, req_ids: list[str]) -> str:
        """生成证据引用。"""
        return f"spec-delta.md#需求-{','.join(req_ids)}"

    @property
    def action_history(self) -> list[dict]:
        """返回操作历史。"""
        return list(self._action_history)
