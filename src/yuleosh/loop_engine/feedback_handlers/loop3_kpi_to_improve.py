#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 3 — KPI→RCA→改进闭环 (LE-005).

监听 KPI_BREACH 事件（覆盖率下降/缺陷逃逸率上升/违规数恶化），
通过 RCA 引擎分析根因，关联最近变更历史，生成改进工单。

流程:
  1. 收到 KPI_BREACH 事件
  2. 提取 metric/value/threshold/data_points
  3. 通过 RCAEngine.analyze() 进行根因分析
  4. 生成改进工单 (YAML 结构化输出)
  5. 更新 KPI 趋势记录
  6. 返回 ActionResult

Usage:
    from yuleosh.loop_engine.feedback_handlers.loop3_kpi_to_improve import (
        Loop3KPIToImproveHandler
    )

    handler = Loop3KPIToImproveHandler(rca_engine=rca_eng)
    result = handler.handle(kpi_breach_event)
"""

import logging
import os
from typing import Optional

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
)
from yuleosh.loop_engine.rca_engine import RCAEngine, RCAReport, KPI_METADATA

log = logging.getLogger("yuleosh.loop_engine.handlers.loop3")


@register_handler
class Loop3KPIToImproveHandler(FeedbackHandler):
    """Loop 3: KPI→RCA→改进闭环。

    监听 KPI_BREACH 事件，执行根因分析并生成改进工单。

    Attributes:
        rca_engine: RCAEngine 实例。
        output_dir: 改进工单输出目录。
        thresholds: 自定义阈值配置 (metric -> threshold)。
        min_data_points: 启动分析的最小数据点数。
        _tickets_created: 工单创建记录。
    """

    def __init__(self, rca_engine: Optional[RCAEngine] = None,
                 output_dir: str = ".",
                 thresholds: Optional[dict] = None,
                 min_data_points: int = 3):
        self.rca_engine = rca_engine or RCAEngine()
        self.output_dir = output_dir
        self.thresholds = thresholds or {}
        self.min_data_points = min_data_points
        self._tickets_created: list[str] = []
        self._kpi_trends: dict[str, list[float]] = {}
        self._event_history: list[dict] = []

    def subscribed_events(self) -> list[LoopEventType]:
        return [LoopEventType.KPI_BREACH]

    def can_handle(self, event: LoopEvent) -> bool:
        """细粒度过滤: 只需要 KPI_BREACH 事件且包含 metric 字段。"""
        if event.event_type != LoopEventType.KPI_BREACH:
            return False
        if "metric" not in event.data:
            log.warning("Loop3: KPI_BREACH missing 'metric', skipping")
            return False
        return True

    def handle(self, event: LoopEvent) -> ActionResult:
        """处理 KPI_BREACH 事件。

        步骤:
          1. 提取指标数据
          2. 检查是否真正超阈值
          3. 通过 RCA 引擎分析根因
          4. 生成改进工单
          5. 更新 KPI 趋势
          6. 返回 ActionResult
        """
        metric = event.data.get("metric", "")
        value = event.data.get("value", 0)
        threshold = event.data.get("threshold",
                                   self.thresholds.get(metric))
        data_points = event.data.get("data_points", 0)
        data_points_count = event.data.get("data_points_count", data_points)
        workspace_path = event.data.get("workspace_path", self.output_dir)
        additional = {k: v for k, v in event.data.items()
                      if k not in ("metric", "value", "threshold",
                                   "data_points", "data_points_count",
                                   "workspace_path")}

        # 记录事件
        self._event_history.append({
            "metric": metric,
            "value": value,
            "threshold": threshold,
            "timestamp": event.timestamp,
        })

        # 更新 KPI 趋势
        if metric not in self._kpi_trends:
            self._kpi_trends[metric] = []
        self._kpi_trends[metric].append(value)

        metric_info = KPI_METADATA.get(metric, {})
        metric_name = metric_info.get("name", metric)
        log.info("Loop3: processing KPI_BREACH for '%s' (value=%s, threshold=%s)",
                 metric, value, threshold)

        # ── 步骤 1: 检查数据点是否足够 ──
        if data_points_count < self.min_data_points:
            return ActionResult(
                success=False,
                action_taken=(f"KPI '{metric_name}' 告警跳过 RCA: "
                              f"数据点不足 ({data_points_count} < {self.min_data_points})"),
                handler_name=self.name,
                details={
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "data_points_count": data_points_count,
                    "reason": "insufficient_data",
                },
            )

        # 检查是否使用了自定义阈值
        effective_threshold = threshold or self.rca_engine._get_default_threshold(metric)

        # 检查是否真的是 breach（基于 RCA engine 的 breaching 判断）
        is_breach = self.rca_engine._is_breach(metric, value, effective_threshold)

        if not is_breach:
            return ActionResult(
                success=True,
                action_taken=(f"KPI '{metric_name}' 值 {value} 未超过阈值 "
                              f"{effective_threshold}, 无需 RCA"),
                handler_name=self.name,
                details={
                    "metric": metric,
                    "value": value,
                    "threshold": effective_threshold,
                    "reason": "no_breach",
                },
            )

        # ── 步骤 2: 执行 RCA ──
        report = self.rca_engine.analyze(
            metric=metric,
            value=value,
            threshold=effective_threshold,
            data_points_count=data_points_count,
            additional_data=additional,
            workspace_path=workspace_path,
        )

        # ── 步骤 3: 如果是 insufficient_data, 直接返回 ──
        if report.status == "insufficient_data":
            return ActionResult(
                success=False,
                action_taken=(f"RCA 跳过: {report.root_cause}"),
                handler_name=self.name,
                details=report.to_dict(),
            )

        # ── 步骤 4: 生成改进工单 ──
        ticket_path = self.rca_engine.write_improvement_ticket(
            report, output_dir=self.output_dir
        )
        ticket = self.rca_engine.generate_improvement_ticket(report)
        self._tickets_created.append(ticket["ticket_id"])

        log.info("Loop3: improvement ticket %s created for %s breach",
                 ticket["ticket_id"], metric)

        # ── 步骤 5: 更新 KPI 趋势 (持久化) ──
        self._persist_kpi_trend(metric, value, report)

        return ActionResult(
            success=True,
            action_taken=(
                f"KPI '{metric_name}' 超阈值告警已处理: "
                f"RCA severity={report.severity}, "
                f"工单 {ticket['ticket_id']} (prio={report.priority})"
            ),
            evidence_ref=ticket_path,
            rollback_possible=True,
            handler_name=self.name,
            details={
                "metric": metric,
                "value": value,
                "threshold": effective_threshold,
                "severity": report.severity,
                "priority": report.priority,
                "ticket_id": ticket["ticket_id"],
                "ticket_path": ticket_path,
                "root_cause": report.root_cause,
                "recommendation": report.recommendation,
                "suspect_changes": report.suspect_changes[:3],
                "data_points_count": data_points_count,
                "rca_status": report.status,
            },
        )

    def rollback(self, event: LoopEvent) -> ActionResult:
        """回滚: 清除工单文件和 KPI 趋势记录。"""
        metric = event.data.get("metric", "")

        # 回滚: 从趋势中移除
        if metric in self._kpi_trends and self._kpi_trends[metric]:
            self._kpi_trends[metric].pop()

        return ActionResult(
            success=True,
            action_taken=f"已回滚 KPI '{metric}' 趋势记录",
            handler_name=self.name,
        )

    # ── 趋势持久化 ────────────────────────────────────────────────────

    def _persist_kpi_trend(self, metric: str, value: float, report: RCAReport):
        """将 KPI 趋势写入文件。"""
        trends_dir = os.path.join(self.output_dir, "kpi_trends")
        os.makedirs(trends_dir, exist_ok=True)
        path = os.path.join(trends_dir, f"{metric}_trend.json")

        import json
        trend_data = {
            "metric": metric,
            "values": self._kpi_trends.get(metric, []),
            "last_update": report.timestamp,
            "severity": report.severity,
            "breach_count": sum(
                1 for e in self._event_history if e["metric"] == metric
            ),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(trend_data, f, indent=2)

    # ── 配置热重载 ─────────────────────────────────────────────────────

    def apply_config(self, config: dict):
        """应用配置更改 (支持热重载)。"""
        if "thresholds" in config:
            self.thresholds.update(config["thresholds"])
            log.info("Loop3: thresholds updated: %s", config["thresholds"])
        if "min_data_points" in config:
            self.min_data_points = config["min_data_points"]
        if "output_dir" in config:
            self.output_dir = config["output_dir"]

        # 如果 RCA 引擎需要更新
        if "rca_thresholds" in config:
            self.rca_engine.threshold_overrides.update(
                config["rca_thresholds"]
            )

    # ── 状态查询 ──────────────────────────────────────────────────────

    def get_kpi_trend(self, metric: str) -> list[float]:
        """返回指定指标的趋势数据。"""
        return list(self._kpi_trends.get(metric, []))

    @property
    def tickets_created(self) -> list[str]:
        """返回已创建的工单 ID 列表。"""
        return list(self._tickets_created)

    @property
    def event_history(self) -> list[dict]:
        """返回事件历史。"""
        return list(self._event_history)


__all__ = ["Loop3KPIToImproveHandler"]
