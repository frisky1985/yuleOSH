#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 4 — KG 置信度自进化 (LE-006).

监听 TEST_RESULT / REVIEW_FINDING 事件，对比 KG 预测 vs 实际结果，
动态调整知识图谱中边和节点的置信度。

置信度调整规则:
  - 正确预测 → 置信度提升 (+0.1, 上限 0.95)
  - 错误预测 → 置信度降低 (-0.15, 下限 0.1)
  - 置信度 < 0.3 → 生成 re-review ticket
  - 置信度趋势记录到 KPI 管线

Usage:
    from yuleosh.loop_engine.feedback_handlers.loop4_kg_self_evolve import (
        Loop4KGSelfEvolveHandler
    )

    handler = Loop4KGSelfEvolveHandler(knowledge_store=my_store)
    result = handler.handle(test_result_event)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
)

log = logging.getLogger("yuleosh.loop_engine.handlers.loop4")

# 置信度调整常量
CONFIDENCE_INCREASE = 0.1       # 正确预测时增加
CONFIDENCE_DECREASE = 0.15      # 错误预测时减少
CONFIDENCE_MAX = 0.95           # 置信度上限
CONFIDENCE_MIN = 0.1            # 置信度下限
REVIEW_THRESHOLD = 0.3          # 低于此值触发 re-review
KPI_CONFIDENCE_TREND_KEY = "kg_confidence_trend"


@register_handler
class Loop4KGSelfEvolveHandler(FeedbackHandler):
    """Loop 4: KG 置信度自进化。

    监听 TEST_RESULT / REVIEW_FINDING 事件，动态调整 KG 置信度。

    Attributes:
        knowledge_store: 知识存储后端 (用于持久化置信度)。
        edges: 内存中的 KG 边/节点置信度字典。
        output_dir: 输出目录。
        review_tickets_dir: re-review ticket 输出目录。
        _confidence_history: 置信度变更历史。
        _kpi_confidence_snapshots: KPI 管线用置信度快照。
        review_threshold: 触发审查的置信度阈值。
    """

    def __init__(self, knowledge_store=None, output_dir: str = ".",
                 review_threshold: float = REVIEW_THRESHOLD):
        self.knowledge_store = knowledge_store
        self.output_dir = output_dir
        self.review_threshold = review_threshold

        # 内存中的置信度字典: entity_id -> {"edge_id": ..., "node_id": ..., "confidence": 0.5}
        self._edges: dict[str, dict] = {}
        self._confidence_history: list[dict] = []
        self._kpi_confidence_snapshots: list[dict] = []
        self._review_tickets_created: list[str] = []

    def subscribed_events(self) -> list[LoopEventType]:
        return [LoopEventType.TEST_RESULT, LoopEventType.REVIEW_FINDING]

    def can_handle(self, event: LoopEvent) -> bool:
        """细粒度过滤: 必须包含 entity_id 和 prediction_result。"""
        if "entity_id" not in event.data:
            return False
        if "prediction_result" not in event.data:
            return False
        return True

    def handle(self, event: LoopEvent) -> ActionResult:
        """处理事件 — 调整 KG 置信度。

        步骤:
          1. 提取 entity_id 和 prediction_result
          2. 获取当前置信度 (默认 0.5)
          3. 根据预测正确性调整置信度
          4. 更新持久化存储
          5. 检查是否触发 re-review
          6. 记录 KPI 趋势
          7. 返回 ActionResult
        """
        entity_id = event.data.get("entity_id", "")
        edge_id = event.data.get("edge_id", entity_id)
        prediction_result = event.data.get("prediction_result", "").lower()
        predicted_value = event.data.get("predicted_value", "")
        actual_value = event.data.get("actual_value", "")
        is_correct = prediction_result == "correct" or (
            predicted_value and actual_value and predicted_value == actual_value
        )

        log.info("Loop4: processing event for entity '%s' (result=%s, correct=%s)",
                 entity_id, prediction_result, is_correct)

        # ── 步骤 1: 获取/初始化当前置信度 ──
        current_conf = self._get_confidence(entity_id, edge_id)

        # ── 步骤 2: 调整置信度 ──
        old_conf = current_conf
        if is_correct:
            new_conf = min(current_conf + CONFIDENCE_INCREASE, CONFIDENCE_MAX)
            adjustment = "increased"
        else:
            new_conf = max(current_conf - CONFIDENCE_DECREASE, CONFIDENCE_MIN)
            adjustment = "decreased"

        # ── 步骤 3: 更新置信度 ──
        self._set_confidence(entity_id, edge_id, new_conf)
        self._persist_confidence(entity_id, edge_id, new_conf)

        # ── 步骤 4: 记录变更历史 ──
        change_record = {
            "entity_id": entity_id,
            "edge_id": edge_id,
            "event_type": event.event_type.value,
            "prediction_result": prediction_result,
            "old_confidence": round(old_conf, 4),
            "new_confidence": round(new_conf, 4),
            "adjustment": adjustment,
            "is_correct": is_correct,
            "timestamp": event.timestamp,
        }
        self._confidence_history.append(change_record)

        # ── 步骤 5: 检查是否需要 re-review ──
        review_ticket_id = None
        if new_conf < self.review_threshold:
            review_ticket_id = self._create_review_ticket(
                entity_id=entity_id,
                edge_id=edge_id,
                confidence=new_conf,
                old_confidence=old_conf,
                change_record=change_record,
            )
            log.info("Loop4: re-review ticket created for '%s' (conf=%.3f < %.3f)",
                     entity_id, new_conf, self.review_threshold)

        # ── 步骤 6: 记录 KPI 趋势 ──
        self._record_kpi_snapshot(entity_id, new_conf, is_correct)

        # 构建 details
        details = {
            "entity_id": entity_id,
            "edge_id": edge_id,
            "old_confidence": round(old_conf, 4),
            "new_confidence": round(new_conf, 4),
            "adjustment": adjustment,
            "delta": round(new_conf - old_conf, 4),
            "prediction_result": prediction_result,
            "is_correct": is_correct,
            "below_review_threshold": new_conf < self.review_threshold,
        }
        if review_ticket_id:
            details["review_ticket_id"] = review_ticket_id

        action_taken = (
            f"KG 实体 '{entity_id}' 置信度 {adjustment}: "
            f"{old_conf:.3f} → {new_conf:.3f}"
        )
        if review_ticket_id:
            action_taken += f" (re-review ticket: {review_ticket_id})"
        if new_conf >= CONFIDENCE_MAX:
            action_taken += " [已达上限]"

        return ActionResult(
            success=True,
            action_taken=action_taken,
            evidence_ref=self._get_evidence_ref(entity_id, review_ticket_id),
            rollback_possible=True,
            handler_name=self.name,
            details=details,
        )

    def rollback(self, event: LoopEvent) -> ActionResult:
        """回滚: 恢复前一个置信度值。"""
        entity_id = event.data.get("entity_id", "")
        edge_id = event.data.get("edge_id", entity_id)

        # 从历史中查找上一个置信度
        for record in reversed(self._confidence_history):
            if record["entity_id"] == entity_id:
                old_conf = record["old_confidence"]
                self._set_confidence(entity_id, edge_id, old_conf)
                self._persist_confidence(entity_id, edge_id, old_conf)
                return ActionResult(
                    success=True,
                    action_taken=f"已回滚 KG 实体 '{entity_id}' 置信度至 {old_conf:.3f}",
                    handler_name=self.name,
                    details={"entity_id": entity_id, "restored_confidence": old_conf},
                )

        return ActionResult(
            success=False,
            action_taken=f"找不到 KG 实体 '{entity_id}' 的历史记录, 无法回滚",
            handler_name=self.name,
        )

    # ── 置信度管理 ────────────────────────────────────────────────────

    def _get_confidence(self, entity_id: str, edge_id: str) -> float:
        """获取当前置信度。

        优先从 knowledge_store (KG 数据库) 获取，降级使用内存。
        """
        # 尝试从 knowledge_store 获取
        if self.knowledge_store is not None:
            try:
                article = self.knowledge_store.get(entity_id)
                if article is not None:
                    # 从 confidence 字段获取 (KnowledgeArticle 使用的是 0-100 范围)
                    conf = getattr(article, "confidence", None)
                    if conf is not None:
                        return min(float(conf) / 100.0, CONFIDENCE_MAX)
            except Exception as e:
                log.warning("Loop4: KG store get error for '%s': %s", entity_id, e)

        # 如果 knowledge_store 是 dict-like 的后端
        if self.knowledge_store is not None and hasattr(self.knowledge_store, "get_edge"):
            try:
                edge = self.knowledge_store.get_edge(edge_id)
                if edge and "confidence" in edge:
                    return min(float(edge["confidence"]), CONFIDENCE_MAX)
            except Exception:
                pass

        # 降级到内存
        if edge_id in self._edges:
            min_val = min(self._edges[edge_id].get("confidence", 0.5), CONFIDENCE_MAX)
            return min_val

        # 默认置信度
        return 0.5

    def _set_confidence(self, entity_id: str, edge_id: str, confidence: float):
        """在内存中设置置信度。"""
        if edge_id not in self._edges:
            self._edges[edge_id] = {}
        self._edges[edge_id]["entity_id"] = entity_id
        self._edges[edge_id]["edge_id"] = edge_id
        self._edges[edge_id]["confidence"] = round(confidence, 4)

    def _persist_confidence(self, entity_id: str, edge_id: str, confidence: float):
        """持久化置信度。

        根据 knowledge_store 类型选择写入方式。
        """
        if self.knowledge_store is None:
            return

        try:
            # 尝试作为 KBStore 使用
            if hasattr(self.knowledge_store, "update"):
                updates = {
                    "confidence": int(round(confidence * 100)),  # KBStore 使用 0-100
                    "change_reason": f"Loop4 auto-evolution: confidence={confidence:.3f}",
                }
                self.knowledge_store.update(entity_id, updates)

            # 尝试作为 edge store 使用
            if hasattr(self.knowledge_store, "update_edge_confidence"):
                self.knowledge_store.update_edge_confidence(
                    edge_id, confidence=int(round(confidence * 100))
                )

            log.debug("Loop4: persisted confidence for %s: %.4f", entity_id, confidence)
        except Exception as e:
            log.warning("Loop4: persist error for '%s': %s", entity_id, e)

    # ── Re-review Ticket ────────────────────────────────────────────────

    def _create_review_ticket(self, entity_id: str, edge_id: str,
                               confidence: float, old_confidence: float,
                               change_record: dict) -> str:
        """生成 re-review ticket。

        Returns:
            Ticket ID。
        """
        ticket_id = f"REREV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{edge_id[:8]}"
        self._review_tickets_created.append(ticket_id)

        tickets_dir = os.path.join(self.output_dir, "rereview_tickets")
        os.makedirs(tickets_dir, exist_ok=True)
        filepath = os.path.join(tickets_dir, f"{ticket_id}.json")

        ticket = {
            "ticket_id": ticket_id,
            "type": "kg_confidence_review",
            "entity_id": entity_id,
            "edge_id": edge_id,
            "current_confidence": round(confidence, 4),
            "previous_confidence": round(old_confidence, 4),
            "trigger_reason": (
                f"置信度 {confidence:.3f} 低于审查阈值 {self.review_threshold}, "
                f"源自事件 {change_record.get('event_type', 'unknown')}: "
                f"预测结果={change_record.get('prediction_result', 'unknown')}"
            ),
            "recommended_action": "人工审查该 KG 条目的准确性",
            "priority": "P2",
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "change_history_ref": change_record,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(ticket, f, indent=2, ensure_ascii=False)

        return ticket_id

    # ── KPI 趋势记录 ────────────────────────────────────────────────────

    def _record_kpi_snapshot(self, entity_id: str, confidence: float,
                              is_correct: bool):
        """记录置信度快照到 KPI 管线。"""
        snapshot = {
            "entity_id": entity_id,
            "confidence": round(confidence, 4),
            "is_correct": is_correct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._kpi_confidence_snapshots.append(snapshot)

        # 持久化到文件
        if self.output_dir:
            kpi_dir = os.path.join(self.output_dir, KPI_CONFIDENCE_TREND_KEY)
            os.makedirs(kpi_dir, exist_ok=True)

            # 只保留最近 1000 条
            recent = self._kpi_confidence_snapshots[-1000:]

            filepath = os.path.join(kpi_dir, "confidence_snapshots.jsonl")
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot) + "\n")

    # ── 数据注入 (用于测试) ────────────────────────────────────────────

    def inject_entity(self, entity_id: str, edge_id: str, confidence: float):
        """注入实体置信度 (用于测试)。"""
        self._set_confidence(entity_id, edge_id, confidence)

    def inject_knowledge_store(self, knowledge_store):
        """注入 knowledge_store (用于测试)。"""
        self.knowledge_store = knowledge_store

    # ── 状态查询 ──────────────────────────────────────────────────────

    def get_confidence(self, entity_id: str,
                        edge_id: Optional[str] = None) -> float:
        """获取指定实体的置信度。"""
        eid = edge_id or entity_id
        return self._get_confidence(entity_id, eid)

    @property
    def confidence_history(self) -> list[dict]:
        """返回置信度变更历史。"""
        return list(self._confidence_history)

    @property
    def kpi_snapshots(self) -> list[dict]:
        """返回 KPI 快照。"""
        return list(self._kpi_confidence_snapshots)

    @property
    def review_tickets_created(self) -> list[str]:
        """返回创建的 re-review ticket ID 列表。"""
        return list(self._review_tickets_created)

    def _get_evidence_ref(self, entity_id: str,
                           review_ticket_id: Optional[str] = None) -> str:
        """生成证据引用。"""
        if review_ticket_id:
            return f"rereview_tickets/{review_ticket_id}.json"
        return f"kg_confidence_trend/entity_{entity_id}"


__all__ = ["Loop4KGSelfEvolveHandler"]
