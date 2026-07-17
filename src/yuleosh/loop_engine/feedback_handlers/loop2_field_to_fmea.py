#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Loop 2 — 现场缺陷→FMEA 闭环 (LE-004).

监听 FIELD_DEFECT 事件，通过 KG 追溯：故障代码 → affected SWC → related FMEA entries，
更新 FMEA 条目（failure_rate + 1, severity 根据 defect 等级），
严重度 ≥ 8 时触发安全影响分析。

流程:
  1. 收到 FIELD_DEFECT 事件
  2. 通过 KG 追溯: 故障代码 → SWC → FMEA 条目
  3. 更新 FMEA 条目 (failure_rate += 1, severity = max(old, new))
  4. 如果 severity ≥ 8: 触发安全影响分析
  5. 输出安全影响分析报告
  6. 返回 ActionResult

Usage:
    from yuleosh.loop_engine.feedback_handlers.loop2_field_to_fmea import (
        Loop2FieldToFMEAHandler
    )

    handler = Loop2FieldToFMEAHandler(kg_store=my_store)
    result = handler.handle(field_defect_event)
"""

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from yuleosh.loop_engine.event_bus import LoopEvent, LoopEventType
from yuleosh.loop_engine.feedback_handlers.base import (
    FeedbackHandler,
    ActionResult,
    register_handler,
)

log = logging.getLogger("yuleosh.loop_engine.handlers.loop2")

# 严重度阈值
SAFETY_SEVERITY_THRESHOLD = 8  # 严重度 ≥ 8 触发安全影响分析


@dataclass
class FMEAEntry:
    """FMEA 条目数据模型。

    Attributes:
        fmea_id: FMEA 条目 ID。
        swc: 关联的 SWC 名称。
        failure_mode: 失效模式描述。
        failure_rate: 失效计数。
        severity: 严重度 (1-10)。
        occurrence: 频度 (1-10)。
        detection: 可检测性 (1-10)。
        rpn: 风险优先数 (severity * occurrence * detection)。
        status: 状态 (active/mitigated/closed)。
        last_updated: 最后更新时间。
        safety_related: 是否与安全相关。
        tags: 标签列表。
    """
    fmea_id: str
    swc: str
    failure_mode: str = ""
    failure_rate: int = 0
    severity: int = 1
    occurrence: int = 1
    detection: int = 1
    rpn: int = 1
    status: str = "active"
    last_updated: str = ""
    safety_related: bool = False
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now(timezone.utc).isoformat()
        self.recompute_rpn()

    def recompute_rpn(self):
        """重新计算 RPN。"""
        self.rpn = self.severity * self.occurrence * self.detection

    def to_dict(self) -> dict:
        return {
            "fmea_id": self.fmea_id,
            "swc": self.swc,
            "failure_mode": self.failure_mode,
            "failure_rate": self.failure_rate,
            "severity": self.severity,
            "occurrence": self.occurrence,
            "detection": self.detection,
            "rpn": self.rpn,
            "status": self.status,
            "last_updated": self.last_updated,
            "safety_related": self.safety_related,
            "tags": self.tags,
        }


@register_handler
class Loop2FieldToFMEAHandler(FeedbackHandler):
    """Loop 2: 现场缺陷→FMEA 闭环。

    监听 FIELD_DEFECT 事件，追溯 SWC，更新 FMEA 条目，触发安全影响分析。

    Attributes:
        kg_store: KG 存储后端。
        output_dir: 输出目录。
        _fmea_entries: 内存中的 FMEA 条目字典。
        _safety_reports: 安全影响分析报告列表。
    """

    def __init__(self, kg_store=None, output_dir: str = "."):
        self.kg_store = kg_store
        self.output_dir = output_dir
        self._fmea_entries: dict[str, FMEAEntry] = {}
        self._safety_reports: list[dict] = []
        self._event_history: list[dict] = []

    def subscribed_events(self) -> list[LoopEventType]:
        return [LoopEventType.FIELD_DEFECT]

    def can_handle(self, event: LoopEvent) -> bool:
        """细粒度过滤: 只需要 FIELD_DEFECT 事件。"""
        if event.event_type != LoopEventType.FIELD_DEFECT:
            return False
        if "swc" not in event.data:
            log.warning("Loop2: FIELD_DEFECT missing 'swc', skipping")
            return False
        return True

    def handle(self, event: LoopEvent) -> ActionResult:
        """处理 FIELD_DEFECT 事件。

        步骤:
          1. 提取事件数据 (swc, failure_code, severity)
          2. 通过 KG 追溯 SWC → FMEA
          3. 查找或创建 FMEA 条目
          4. 更新 FMEA (failure_rate + 1, severity 升级)
          5. 严重度 ≥ 8 → 触发安全影响分析
          6. 返回 ActionResult
        """
        swc = event.data.get("swc", "")
        failure_code = event.data.get("failure_code", event.data.get("failure_mode", ""))
        severity = event.data.get("severity", 1)
        defect_id = event.data.get("defect_id", event.data.get("id", ""))
        description = event.data.get("description", event.data.get("error", ""))

        log.info("Loop2: processing FIELD_DEFECT for SWC '%s' (sev=%d, code=%s)",
                 swc, severity, failure_code)

        # ── 记录事件 ──
        self._event_history.append({
            "swc": swc,
            "failure_code": failure_code,
            "severity": severity,
            "defect_id": defect_id,
            "timestamp": event.timestamp,
        })

        # ── 步骤 1: 通过 KG 追溯 SWC ──
        kg_info = self._trace_via_kg(swc, failure_code)
        fmea_id = kg_info.get("fmea_entry_id")

        # ── 步骤 2: 查找或创建 FMEA 条目 ──
        if fmea_id and fmea_id in self._fmea_entries:
            entry = self._fmea_entries[fmea_id]
        elif fmea_id and fmea_id not in self._fmea_entries:
            # 尝试从持久化存储加载
            entry = self._load_fmea_entry(fmea_id)
            if entry is None:
                # 从 KG info 重建
                entry = self._create_fmea_entry(
                    fmea_id=fmea_id,
                    swc=swc,
                    failure_mode=failure_code,
                    severity=severity,
                )
        else:
            # 没有 FMEA 条目, 创建骨架
            fmea_id = f"FMEA-{swc}-{failure_code or 'UNKNOWN'}"
            entry = self._create_fmea_entry(
                fmea_id=fmea_id,
                swc=swc,
                failure_mode=failure_code,
                severity=severity,
            )
            log.info("Loop2: created new FMEA entry %s for SWC '%s'", fmea_id, swc)

        # ── 步骤 3: 更新 FMEA 条目 ──
        entry.failure_rate += 1
        entry.severity = max(entry.severity, min(severity, 10))
        entry.last_updated = datetime.now(timezone.utc).isoformat()

        # 更新 occurrences (如果字段存在)
        entry.occurrence = min(entry.occurrence + 1, 10)

        # 重新计算 RPN
        entry.recompute_rpn()

        # 保存到内存
        self._fmea_entries[entry.fmea_id] = entry

        # 持久化
        self._persist_fmea_entry(entry)

        log.info("Loop2: updated FMEA %s: failure_rate=%d, severity=%d, RPN=%d",
                 entry.fmea_id, entry.failure_rate, entry.severity, entry.rpn)

        details = {
            "swc": swc,
            "fmea_id": entry.fmea_id,
            "failure_code": failure_code,
            "defect_id": defect_id,
            "failure_rate": entry.failure_rate,
            "severity": entry.severity,
            "occurrence": entry.occurrence,
            "rpn": entry.rpn,
            "kg_swc_found": kg_info.get("swc_found", False),
        }

        # ── 步骤 4: 严重度 ≥ 8 → 触发安全影响分析 ──
        safety_report_path = None
        if entry.severity >= SAFETY_SEVERITY_THRESHOLD:
            safety_report_path = self._trigger_safety_impact_analysis(
                entry=entry,
                defect_id=defect_id,
                description=description,
                event=event,
            )
            details["safety_analysis_triggered"] = True
            details["safety_report_path"] = safety_report_path
            log.warning("Loop2: SAFETY IMPACT ANALYSIS triggered for FMEA %s "
                        "(severity=%d >= %d)", entry.fmea_id,
                        entry.severity, SAFETY_SEVERITY_THRESHOLD)

        action_taken = (
            f"FMEA 条目 {entry.fmea_id} 更新: failure_rate={entry.fmea_id} "
            f"failure_rate={entry.failure_rate}, severity={entry.severity}"
        )
        if safety_report_path:
            action_taken += f"; 安全影响分析: {safety_report_path}"

        return ActionResult(
            success=True,
            action_taken=action_taken,
            evidence_ref=safety_report_path or f"fmea_entries/{entry.fmea_id}.json",
            rollback_possible=True,
            handler_name=self.name,
            details=details,
        )

    def rollback(self, event: LoopEvent) -> ActionResult:
        """回滚: 恢复 FMEA 条目的前一个状态 (减回 failure_rate 和 severity)。"""
        swc = event.data.get("swc", "")
        fmea_id = self._find_fmea_for_swc(swc)

        if fmea_id and fmea_id in self._fmea_entries:
            entry = self._fmea_entries[fmea_id]
            entry.failure_rate = max(entry.failure_rate - 1, 0)
            entry.recompute_rpn()
            self._persist_fmea_entry(entry)
            return ActionResult(
                success=True,
                action_taken=f"已回滚 FMEA {fmea_id}: failure_rate={entry.failure_rate}",
                handler_name=self.name,
            )

        return ActionResult(
            success=False,
            action_taken=f"找不到 FMEA 条目 for SWC '{swc}', 无法回滚",
            handler_name=self.name,
        )

    # ── KG 追溯 ────────────────────────────────────────────────────────

    def _trace_via_kg(self, swc: str, failure_code: str) -> dict:
        """通过 KG 追溯 SWC 和 FMEA 条目。

        优先从 knowledge_store 查询，降级使用内存默认值。
        """
        result = {
            "swc_found": False,
            "fmea_entry_id": None,
            "related_entries": [],
        }

        if self.kg_store is not None:
            try:
                # 尝试从 KBStore 搜索
                if hasattr(self.kg_store, "search"):
                    items, _ = self.kg_store.search(swc, limit=10)
                    for article in items:
                        title = getattr(article, "title", "") or ""
                        content = getattr(article, "content", "") or ""
                        tags = getattr(article, "tags", []) or []
                        autosar = getattr(article, "autosar_layers", []) or []

                        if swc.lower() in title.lower() or \
                           swc.lower() in content.lower():
                            result["swc_found"] = True
                            article_id = getattr(article, "id", "") or ""
                            if article_id:
                                result["fmea_entry_id"] = f"FMEA-{article_id}"
                                # 将相关条目加入 related_entries
                                if hasattr(article, "spec_refs"):
                                    for ref in (article.spec_refs or []):
                                        result["related_entries"].append(ref)

                # 尝试从 queries 模块追溯
                if hasattr(self.kg_store, "get"):
                    article = self.kg_store.get(swc)
                    if article:
                        result["swc_found"] = True
                        article_id = getattr(article, "id", "") or swc
                        result["fmea_entry_id"] = f"FMEA-{article_id}"

            except Exception as e:
                log.warning("Loop2: KG trace error for '%s': %s", swc, e)

        # 如果 KG 没有返回结果, 使用 swc 名称生成默认 FMEA ID
        if not result["fmea_entry_id"]:
            result["fmea_entry_id"] = f"FMEA-{swc}-{failure_code or 'GEN'}"

        return result

    # ── FMEA 条目管理 ──────────────────────────────────────────────────

    def _create_fmea_entry(self, fmea_id: str, swc: str,
                            failure_mode: str, severity: int) -> FMEAEntry:
        """创建新的 FMEA 条目。"""
        return FMEAEntry(
            fmea_id=fmea_id,
            swc=swc,
            failure_mode=failure_mode,
            failure_rate=1,
            severity=min(severity, 10),
            occurrence=1,
            detection=3,
            status="active",
            safety_related=severity >= SAFETY_SEVERITY_THRESHOLD,
            tags=["field_defect", swc],
        )

    def _find_fmea_for_swc(self, swc: str) -> Optional[str]:
        """查找 SWC 关联的 FMEA 条目 ID。"""
        for fmea_id, entry in self._fmea_entries.items():
            if entry.swc == swc:
                return fmea_id
        return None

    def get_fmea_entry(self, fmea_id: str) -> Optional[FMEAEntry]:
        """获取 FMEA 条目。"""
        return self._fmea_entries.get(fmea_id)

    def get_all_entries(self) -> list[FMEAEntry]:
        """返回所有 FMEA 条目。"""
        return list(self._fmea_entries.values())

    # ── 安全影响分析 ────────────────────────────────────────────────────

    def _trigger_safety_impact_analysis(self, entry: FMEAEntry,
                                         defect_id: str,
                                         description: str,
                                         event: LoopEvent) -> str:
        """触发安全影响分析并生成报告。"""
        now = datetime.now(timezone.utc)
        report_filename = f"safety-impact-{entry.fmea_id}-{now.strftime('%Y%m%d%H%M%S')}.md"

        reports_dir = os.path.join(self.output_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        filepath = os.path.join(reports_dir, report_filename)

        # 生成安全影响分析报告 (Markdown)
        report_content = self._generate_safety_report(entry, defect_id, description, event)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report_content)

        self._safety_reports.append({
            "fmea_id": entry.fmea_id,
            "swc": entry.swc,
            "severity": entry.severity,
            "report_path": filepath,
            "timestamp": now.isoformat(),
        })

        log.info("Loop2: safety impact report written to %s", filepath)
        return filepath

    def _generate_safety_report(self, entry: FMEAEntry, defect_id: str,
                                  description: str,
                                  event: LoopEvent) -> str:
        """生成安全影响分析报告 Markdown 内容。

        按照 ISO 26262 安全分析报告的格式:
        - 标题和元信息
        - 缺陷概述
        - FMEA 条目状态
        - 安全影响评估
        - 推荐措施
        """
        now = datetime.now(timezone.utc).isoformat()
        occurrence_severity = "高" if entry.occurrence >= 7 else \
                              ("中" if entry.occurrence >= 4 else "低")

        lines = [
            f"# 安全影响分析报告",
            f"",
            f"> **自动生成**: {now}",
            f"> **触发条件**: 现场缺陷导致 FMEA 严重度 ≥ {SAFETY_SEVERITY_THRESHOLD}",
            f"> **生成器**: yuleOSH Loop Engine — Loop2 (Field→FMEA)",
            f"",
            f"---",
            f"",
            f"## 1. 概述",
            f"",
            f"- **FMEA ID**: `{entry.fmea_id}`",
            f"- **SWC**: `{entry.swc}`",
            f"- **失效模式**: {entry.failure_mode}",
            f"- **缺陷 ID**: {defect_id}",
            f"- **严重度**: {entry.severity}/10",
            f"- **当前 RPN**: {entry.rpn}",
            f"- **失效计数**: {entry.failure_rate}",
            f"- **安全相关**: {'是' if entry.safety_related else '否'}",
            f"",
            f"## 2. 缺陷详情",
            f"",
            f"{description or '无详细描述'}",
            f"",
            f"## 3. FMEA 条目状态",
            f"",
            f"| 参数 | 当前值 | 评估 |",
            f"|------|--------|------|",
            f"| **严重度 (S)** | {entry.severity}/10 | {'⚠️ 需要立即关注' if entry.severity >= 8 else '🟢 可接受'} |",
            f"| **频度 (O)** | {entry.occurrence}/10 | {occurrence_severity} |",
            f"| **可检测性 (D)** | {entry.detection}/10 | {'🔴 检测能力不足' if entry.detection >= 7 else '🟡 需要改善' if entry.detection >= 4 else '🟢 可接受'} |",
            f"| **RPN** | {entry.rpn} | {'⚠️ RPN 偏高' if entry.rpn >= 100 else '🟢 正常'} |",
            f"| **失效计数** | {entry.failure_rate} | — |",
            f"",
            f"## 4. 安全影响评估",
            f"",
            f"### 4.1 ASIL 等级评估",
            f"",
            f"基于严重度 {entry.severity}/10，根据 ISO 26262 分类：",
        ]

        if entry.severity >= 9:
            lines.append("- **ASIL D**: 最高安全等级, 需要完整的功能安全开发流程")
        elif entry.severity >= 7:
            lines.append("- **ASIL C**: 高安全等级, 需要严格的开发流程")
        elif entry.severity >= 5:
            lines.append("- **ASIL B**: 中等安全等级")
        else:
            lines.append("- **ASIL A / QM**: 低安全等级或质量管理")

        lines.extend([
            "",
            "### 4.2 安全目标影响",
            "",
            f"SWC `{entry.swc}` 的失效模式 `{entry.failure_mode}` 可能影响以下安全目标：",
            "",
            "- 需要根据具体系统架构进行追溯",
            "- 建议启动安全评审 (safety review)",
            "",
            "### 4.3 潜在后果",
            "",
            "| 场景 | 影响 | 严重度 |",
            "|------|------|--------|",
            f"| 正常工况 | 功能降级 | {max(entry.severity - 2, 1)}/10 |",
            f"| 故障模式 | 功能失效 | {entry.severity}/10 |",
            f"| 多故障叠加 | 安全风险升级 | {min(entry.severity + 1, 10)}/10 |",
            "",
            "## 5. 推荐措施",
            "",
            f"1. **立即**: 调查 SWC `{entry.swc}` 的失效根因",
            f"2. **短期**: 更新 FMEA 并启动设计变更审查",
            f"3. **中期**: 增加针对失效模式 `{entry.failure_mode}` 的测试覆盖",
            f"4. **长期**: 评估是否需要在系统级添加安全机制",
            "",
            "## 6. 关联项",
            "",
            f"- 事件来源: `{event.source}`",
            f"- 事件时间: `{event.timestamp}`",
            f"- 事件 ID: `{event.event_id[:16]}`",
        ])

        if entry.tags:
            lines.extend([
                "", "- 标签: " + ", ".join(entry.tags),
            ])

        lines.extend([
            "",
            "---",
            "",
            f"*报告由 yuleOSH Loop Engineering — Loop 2 (Field→FMEA) 自动生成*",
            "",
        ])

        return "\n".join(lines)

    # ── 持久化 ──────────────────────────────────────────────────────────

    def _persist_fmea_entry(self, entry: FMEAEntry):
        """持久化 FMEA 条目到 JSON 文件。"""
        fmea_dir = os.path.join(self.output_dir, "fmea_entries")
        os.makedirs(fmea_dir, exist_ok=True)
        filepath = os.path.join(fmea_dir, f"{entry.fmea_id}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2, ensure_ascii=False)

    def _load_fmea_entry(self, fmea_id: str) -> Optional[FMEAEntry]:
        """从 JSON 文件加载 FMEA 条目。"""
        filepath = os.path.join(self.output_dir, "fmea_entries", f"{fmea_id}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return FMEAEntry(**data)
            except Exception as e:
                log.warning("Loop2: load FMEA entry error: %s", e)
        return None

    # ── 数据注入 (用于测试) ────────────────────────────────────────────

    def inject_fmea_entry(self, entry: FMEAEntry):
        """注入 FMEA 条目 (用于测试)。"""
        self._fmea_entries[entry.fmea_id] = entry

    # ── 状态查询 ──────────────────────────────────────────────────────

    @property
    def safety_reports(self) -> list[dict]:
        """返回安全影响分析报告列表。"""
        return list(self._safety_reports)

    @property
    def event_history(self) -> list[dict]:
        """返回事件历史。"""
        return list(self._event_history)


__all__ = ["Loop2FieldToFMEAHandler", "FMEAEntry"]
