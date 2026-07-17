#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Root Cause Analysis (RCA) Engine — Loop 3 的核心分析组件。

职责:
  - 接收 KPI 阈值告警 (覆盖率下降、缺陷逃逸率上升、违规数恶化)
  - 关联最近变更历史 (通过 git log 或内存记录)
  - 追溯 KG 中相关的知识条目
  - 识别嫌疑变更
  - 生成结构化 RCA 报告 (root_cause / impact / recommendation)

Usage:
    from yuleosh.loop_engine.rca_engine import RCAEngine

    engine = RCAEngine()
    report = engine.analyze(metric="coverage_percent", value=45, threshold=60,
                            workspace_path="/path/to/project")
"""

import logging
import os
import re
import subprocess
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("yuleosh.loop_engine.rca_engine")

SEVERITY_LEVELS = ["low", "medium", "high", "critical"]


@dataclass
class RCAReport:
    """RCA 分析报告。

    Attributes:
        metric: 触发分析的指标名称。
        current_value: 当前指标值。
        threshold: 阈值。
        root_cause: 根因描述。
        causal_factors: 贡献因素列表。
        affected_areas: 受影响区域。
        severity: 严重度 (low/medium/high/critical)。
        suspect_changes: 嫌疑变更列表 (commit hash, author, message)。
        recommendation: 推荐改进措施。
        priority: 优先级 (P0-P4)。
        data_points_count: 参与分析的数据点数量。
        timestamp: 分析时间戳。
        additional_details: 额外详情。
        status: 分析状态 (completed/insufficient_data/no_suspects)。
    """
    metric: str
    current_value: float
    threshold: float
    root_cause: str = ""
    causal_factors: list[str] = field(default_factory=list)
    affected_areas: list[str] = field(default_factory=list)
    severity: str = "medium"
    suspect_changes: list[dict] = field(default_factory=list)
    recommendation: str = ""
    priority: str = "P2"
    data_points_count: int = 0
    timestamp: str = ""
    additional_details: dict = field(default_factory=dict)
    status: str = "completed"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "root_cause": self.root_cause,
            "causal_factors": self.causal_factors,
            "affected_areas": self.affected_areas,
            "severity": self.severity,
            "suspect_changes": self.suspect_changes,
            "recommendation": self.recommendation,
            "priority": self.priority,
            "data_points_count": self.data_points_count,
            "timestamp": self.timestamp,
            "additional_details": self.additional_details,
            "status": self.status,
        }

    def to_yaml(self) -> str:
        """生成 YAML 格式的报告 (手工编写 YAML 子集)。"""
        lines = [
            "---",
            f"rca_report:",
            f"  metric: {self.metric}",
            f"  current_value: {self.current_value}",
            f"  threshold: {self.threshold}",
            f"  status: {self.status}",
            f"  severity: {self.severity}",
            f"  priority: {self.priority}",
            f"  root_cause: >",
            f"    {self.root_cause}",
            f"  data_points_count: {self.data_points_count}",
            f"  timestamp: {self.timestamp}",
        ]
        if self.causal_factors:
            lines.append("  causal_factors:")
            for factor in self.causal_factors:
                lines.append(f"    - {factor}")
        if self.affected_areas:
            lines.append("  affected_areas:")
            for area in self.affected_areas:
                lines.append(f"    - {area}")
        if self.suspect_changes:
            lines.append("  suspect_changes:")
            for change in self.suspect_changes:
                lines.append(f"    - commit: {change.get('commit', '')[:12]}")
                lines.append(f"      author: {change.get('author', 'unknown')}")
                lines.append(f"      message: {change.get('message', '')[:80]}")
        if self.recommendation:
            lines.append(f"  recommendation: >")
            lines.append(f"    {self.recommendation}")
        lines.append("...")
        return "\n".join(lines)

    def __repr__(self):
        return f"<RCAReport {self.metric} sev={self.severity} status={self.status}>"


# ═══════════════════════════════════════════════════════════════════════
# KPI 指标定义
# ═══════════════════════════════════════════════════════════════════════

KPI_METADATA = {
    "coverage_percent": {
        "name": "测试覆盖率",
        "direction": "down",  # 下降触发告警
        "default_threshold": 60.0,
        "default_priority": "P1",
        "description": "自动化测试行覆盖率百分比",
    },
    "defect_escape_rate": {
        "name": "缺陷逃逸率",
        "direction": "up",   # 上升触发告警
        "default_threshold": 5.0,
        "default_priority": "P1",
        "description": "现场缺陷 / 测试缺陷比率",
    },
    "misra_violations": {
        "name": "MISRA 违规数",
        "direction": "up",
        "default_threshold": 100,
        "default_priority": "P2",
        "description": "MISRA 规则违规总数",
    },
    "review_findings_open": {
        "name": "未关闭审查发现",
        "direction": "up",
        "default_threshold": 20,
        "default_priority": "P2",
        "description": "打开的代码审查发现项数",
    },
    "build_failure_rate": {
        "name": "构建失败率",
        "direction": "up",
        "default_threshold": 10.0,
        "default_priority": "P1",
        "description": "最近30天构建失败百分比",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# RCA Engine
# ═══════════════════════════════════════════════════════════════════════

class RCAEngine:
    """根因分析引擎。

    分析 KPI 阈值告警，关联变更历史，识别嫌疑变更，生成 RCA 报告。

    Attributes:
        threshold_overrides: 自定义阈值覆盖。
        git_log_limit: 分析的 git 提交数上限。
        kg_store: 可选的 KG 存储后端 (用于追溯知识关联)。
        kg_articles: 内存中的 KG 知识条目 (没有 kg_store 时使用)。
        change_history: 内存中的变更历史记录。
    """

    def __init__(self, kg_store=None, threshold_overrides: Optional[dict] = None,
                 git_log_limit: int = 50):
        self.kg_store = kg_store
        self.threshold_overrides = threshold_overrides or {}
        self.git_log_limit = git_log_limit
        self._kg_articles: list[dict] = []
        self._change_history: list[dict] = []

    # ── 分析入口 ──────────────────────────────────────────────────────

    def analyze(self, metric: str, value: float, threshold: Optional[float] = None,
                data_points_count: int = 0,
                additional_data: Optional[dict] = None,
                workspace_path: Optional[str] = None) -> RCAReport:
        """执行根因分析。

        Args:
            metric: 告警指标名称。
            value: 当前指标值。
            threshold: 阈值 (None 则使用默认值)。
            data_points_count: 历史数据点数量 (用于判断分析可行性)。
            additional_data: 额外事件数据。
            workspace_path: 项目路径 (用于 git log 分析)。

        Returns:
            RCAReport 分析报告。
        """
        effective_threshold = threshold or self._get_default_threshold(metric)
        is_breach = self._is_breach(metric, value, effective_threshold)

        if data_points_count < 3:
            return RCAReport(
                metric=metric,
                current_value=value,
                threshold=effective_threshold,
                status="insufficient_data",
                root_cause="数据点不足 (需要 ≥ 3 个数据点进行趋势分析)",
                data_points_count=data_points_count,
                priority=self._get_priority(metric),
            )

        if not is_breach:
            return RCAReport(
                metric=metric,
                current_value=value,
                threshold=effective_threshold,
                status="no_breach",
                root_cause=f"指标 {metric} 值 {value} 未超过阈值 {effective_threshold}",
                data_points_count=data_points_count,
                priority=self._get_priority(metric),
            )

        # ── 正式分析: 收集证据 ──
        suspect_changes = self._find_suspect_changes(metric, workspace_path)
        kg_factors = self._query_kg_factors(metric, value)
        affected_areas = self._determine_affected_areas(metric, kg_factors)

        sev = self._compute_severity(metric, value, effective_threshold)
        prio = self._compute_priority(sev, metric)
        root_cause = self._generate_root_cause(metric, value, effective_threshold,
                                                suspect_changes, kg_factors)
        recommendation = self._generate_recommendation(metric, root_cause, sev)

        report = RCAReport(
            metric=metric,
            current_value=value,
            threshold=effective_threshold,
            status="completed",
            severity=sev,
            priority=prio,
            root_cause=root_cause,
            causal_factors=self._extract_causal_factors(suspect_changes, kg_factors),
            affected_areas=affected_areas,
            suspect_changes=suspect_changes,
            recommendation=recommendation,
            data_points_count=data_points_count,
            additional_details={
                "is_breach": True,
                "deviation": abs(value - effective_threshold),
                "kg_articles_found": len(kg_factors),
                "suspect_changes_found": len(suspect_changes),
            },
        )

        log.info("RCA: %s breaching %.2f → severity=%s, %d suspects",
                 metric, value, sev, len(suspect_changes))
        return report

    # ── 嫌疑变更分析 ─────────────────────────────────────────────────

    def _find_suspect_changes(self, metric: str,
                               workspace_path: Optional[str] = None) -> list[dict]:
        """查找最近可能导致指标恶化的变更。

        优先使用 git log，降级使用内存记录。
        """
        changes = []

        # 尝试从 git log 获取
        if workspace_path and os.path.isdir(os.path.join(workspace_path, ".git")):
            changes = self._read_git_log(workspace_path)

        # 如果有内存记录，合并
        if self._change_history:
            changes = self._merge_changes(changes, self._change_history)

        # 关联指标关键字
        relevant_keywords = self._get_relevant_keywords(metric)
        filtered = [c for c in changes
                    if any(kw in (c.get("message", "") + " " + c.get("files", ""))
                           for kw in relevant_keywords)
                    or not relevant_keywords]  # 无关键字则返回所有

        return filtered[:self.git_log_limit]

    def _read_git_log(self, workspace_path: str) -> list[dict]:
        """执行 git log 命令获取最近变更。"""
        try:
            result = subprocess.run(
                ["git", "log", f"--max-count={self.git_log_limit}",
                 "--pretty=format:%H||%an||%ad||%s",
                 "--date=short"],
                capture_output=True, text=True,
                cwd=workspace_path, timeout=10,
            )
            if result.returncode == 0:
                changes = []
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("||", 3)
                    if len(parts) >= 4:
                        changes.append({
                            "commit": parts[0],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3],
                        })
                    elif len(parts) == 3:
                        changes.append({
                            "commit": parts[0],
                            "author": parts[1],
                            "date": parts[2],
                            "message": "",
                        })
                return changes
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            log.warning("RCA: git log error: %s", e)

        return []

    def _merge_changes(self, git_changes: list[dict],
                       memory_changes: list[dict]) -> list[dict]:
        """合并 git log 和内存记录，去重。"""
        seen_commits = {c.get("commit", "") for c in git_changes}
        merged = list(git_changes)
        for mc in memory_changes:
            if mc.get("commit", "") not in seen_commits:
                merged.append(mc)
                seen_commits.add(mc.get("commit", ""))
        return merged

    # ── KG 回溯 ───────────────────────────────────────────────────────

    def _query_kg_factors(self, metric: str, value: float) -> list[dict]:
        """通过 KG 查询与指标相关的知识条目。

        查找可能影响该指标的知识条目，例如已知问题、技术债等。
        """
        factors = []

        # 从 KG Store 查询
        if self.kg_store is not None:
            try:
                keywords = self._get_relevant_keywords(metric)
                for kw in keywords:
                    # 尝试用不同的 KG 查询接口
                    if hasattr(self.kg_store, "search"):
                        results, _ = self.kg_store.search(kw, limit=10)
                        for article in results:
                            factors.append({
                                "source": "kg_store",
                                "type": "knowledge_article",
                                "title": getattr(article, "title", ""),
                                "content_snippet": getattr(article, "content", "")[:200],
                                "relevance_keyword": kw,
                            })
            except Exception as e:
                log.warning("RCA: KG query error: %s", e)

        # 从内存记录查询
        for article in self._kg_articles:
            title = article.get("title", "")
            content = article.get("content", "")
            for kw in self._get_relevant_keywords(metric):
                if kw.lower() in (title + content).lower():
                    factors.append({
                        "source": "memory",
                        "type": "article",
                        "title": title,
                        "content_snippet": content[:200],
                        "relevance_keyword": kw,
                    })
                    break

        return factors

    # ── 严重度与优先级 ─────────────────────────────────────────────────

    def _compute_severity(self, metric: str, value: float,
                           threshold: float) -> str:
        """根据偏离程度计算严重度。"""
        if threshold == 0:
            return "medium"

        deviation_pct = abs(value - threshold) / threshold

        if deviation_pct > 0.5:
            return "critical"
        elif deviation_pct > 0.3:
            return "high"
        elif deviation_pct > 0.1:
            return "medium"
        else:
            return "low"

    def _compute_priority(self, severity: str, metric: str) -> str:
        """根据严重度和指标类型计算优先级。"""
        # P1 for critical/high in safety-related metrics
        safety_metrics = {"coverage_percent", "defect_escape_rate"}
        if severity in ("critical", "high") or metric in safety_metrics:
            if severity == "critical":
                return "P0"
            return "P1"
        elif severity == "medium":
            return "P2"
        else:
            return "P3"

    # ── 根因生成 ───────────────────────────────────────────────────────

    def _generate_root_cause(self, metric: str, value: float,
                               threshold: float,
                               suspect_changes: list[dict],
                               kg_factors: list[dict]) -> str:
        """综合分析生成根因描述。"""
        metric_info = KPI_METADATA.get(metric, {})
        metric_name = metric_info.get("name", metric)

        parts = [f"KPI 指标 '{metric_name}' 超阈值告警 (当前值={value}, 阈值={threshold})"]

        if suspect_changes:
            top = suspect_changes[:3]
            commits_str = "; ".join(
                f"{c.get('commit', '')[:8]} by {c.get('author', '?')}: {c.get('message', '')[:60]}"
                for c in top
            )
            parts.append(f"嫌疑变更 ({len(suspect_changes)} 个): {commits_str}")

        if kg_factors:
            kg_titles = [f.get("title", "unknown") for f in kg_factors[:3]]
            parts.append(f"KG 关联因素: {', '.join(kg_titles)}")

        deviation = abs(value - threshold)
        direction = metric_info.get("direction", "up")
        if direction == "down":
            parts.append(f"指标值下降 {deviation} (要求 ≥ {threshold})")
        else:
            parts.append(f"指标值上升 {deviation} (要求 ≤ {threshold})")

        return "; ".join(parts)

    def _generate_recommendation(self, metric: str, root_cause: str,
                                   severity: str) -> str:
        """生成改进建议。"""
        metric_info = KPI_METADATA.get(metric, {})

        recommendations = {
            "coverage_percent": (
                "1) 识别未覆盖模块并添加单元测试; "
                "2) 对关键路径增加集成测试; "
                "3) 在 CI 中设置覆盖门禁"
            ),
            "defect_escape_rate": (
                "1) 增强测试用例覆盖率; "
                "2) 增加边界条件和异常路径测试; "
                "3) 引入开发者测试 (TDD) 实践"
            ),
            "misra_violations": (
                "1) 运行 MISRA 检查并修复高严重度违规; "
                "2) 在 CI pipeline 中添加 MISRA 检查; "
                "3) 对新增代码强制执行 MISRA 合规"
            ),
            "review_findings_open": (
                "1) 设定审查发现关闭 SLA (如 48h); "
                "2) 分配责任人跟进; "
                "3) 每周审查会议推进关闭"
            ),
            "build_failure_rate": (
                "1) 检查最近合并的变更; "
                "2) 确保 CI pipeline 预提交验证; "
                "3) 设置构建失败自动回滚"
            ),
        }

        base = recommendations.get(metric, (
            f"1) 分析 '{metric}' 恶化根因; "
            "2) 制定改进计划; "
            "3) 设置跟踪指标"
        ))

        if severity in ("high", "critical"):
            base = "[紧急] " + base + "; 4) 在 24h 内启动根因回顾会议"

        return base

    # ── 辅助方法 ───────────────────────────────────────────────────────

    def _is_breach(self, metric: str, value: float, threshold: float) -> bool:
        """判断是否触发阈值告警。"""
        metric_info = KPI_METADATA.get(metric, {})
        direction = metric_info.get("direction", "up")

        if direction == "down":
            return value < threshold
        else:
            return value > threshold

    def _get_default_threshold(self, metric: str) -> float:
        """获取指标的默认阈值 (允许自定义覆盖)。"""
        if metric in self.threshold_overrides:
            return self.threshold_overrides[metric]
        info = KPI_METADATA.get(metric, {})
        return info.get("default_threshold", 0.0)

    def _get_priority(self, metric: str) -> str:
        """获取指标的默认优先级。"""
        info = KPI_METADATA.get(metric, {})
        return info.get("default_priority", "P2")

    def _get_relevant_keywords(self, metric: str) -> list[str]:
        """获取与指标相关的搜索关键字。"""
        keywords = {
            "coverage_percent": ["coverage", "test", "unittest", "test_case", "覆盖率"],
            "defect_escape_rate": ["defect", "bug", "fix", "escape", "缺陷", "bugfix"],
            "misra_violations": ["misra", "violation", "coding_standard", "合规"],
            "review_findings_open": ["review", "finding", "code_review", "审查"],
            "build_failure_rate": ["build", "compile", "ci", "pipeline", "构建"],
        }
        return keywords.get(metric, [metric])

    def _determine_affected_areas(self, metric: str,
                                   kg_factors: list[dict]) -> list[str]:
        """确定受影响的区域。"""
        areas = set()

        metric_area_map = {
            "coverage_percent": ["测试", "质量保证"],
            "defect_escape_rate": ["测试", "缺陷管理", "质量保证"],
            "misra_violations": ["代码质量", "静态分析"],
            "review_findings_open": ["代码审查", "过程改进"],
            "build_failure_rate": ["构建系统", "CI/CD"],
        }

        for area in metric_area_map.get(metric, ["通用"]):
            areas.add(area)

        for factor in kg_factors:
            tags = factor.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    areas.add(str(tag))

        return sorted(areas)

    def _extract_causal_factors(self, suspect_changes: list[dict],
                                 kg_factors: list[dict]) -> list[str]:
        """提取因果因素描述列表。"""
        factors = []

        for change in suspect_changes[:5]:
            msg = change.get("message", "")[:80]
            author = change.get("author", "unknown")
            commit_short = change.get("commit", "")[:8]
            factors.append(f"提交 {commit_short} by {author}: {msg}")

        for factor in kg_factors[:3]:
            title = factor.get("title", "")
            if title:
                factors.append(f"KG 条目: {title}")

        return factors

    # ── 改进工单生成 ───────────────────────────────────────────────────

    def generate_improvement_ticket(self, report: RCAReport) -> dict:
        """从 RCA 报告生成改进工单。

        Returns:
            YAML 兼容的改进工单字典。
        """
        ticket = {
            "ticket_id": f"IMP-{report.timestamp[:10]}-{report.metric[:8]}",
            "problem_description": report.root_cause[:500],
            "root_cause": report.root_cause[:300],
            "recommended_actions": report.recommendation,
            "priority": report.priority,
            "severity": report.severity,
            "metric": report.metric,
            "current_value": report.current_value,
            "threshold": report.threshold,
            "deadline": self._compute_deadline(report.priority),
            "assigned_to": "",
            "status": "open",
            "created_at": report.timestamp,
            "tags": ["loop3", "kpi_improvement", f"sev_{report.severity}", report.metric],
        }
        return ticket

    def write_improvement_ticket(self, report: RCAReport, output_dir: str = ".") -> str:
        """将改进工单写入 YAML 文件。

        Args:
            report: RCA 报告。
            output_dir: 输出目录。

        Returns:
            写入的文件路径。
        """
        ticket = self.generate_improvement_ticket(report)

        tickets_dir = os.path.join(output_dir, "improvement_tickets")
        os.makedirs(tickets_dir, exist_ok=True)

        filepath = os.path.join(tickets_dir, f"{ticket['ticket_id']}.yaml")

        yaml_lines = [
            "---",
            "improvement_ticket:",
            f"  ticket_id: \"{ticket['ticket_id']}\"",
            f"  status: {ticket['status']}",
            f"  priority: {ticket['priority']}",
            f"  severity: {ticket['severity']}",
            f"  metric: {ticket['metric']}",
            f"  current_value: {ticket['current_value']}",
            f"  threshold: {ticket['threshold']}",
            f"  deadline: {ticket['deadline']}",
            f"  assigned_to: \"{ticket['assigned_to']}\"",
            f"  created_at: {ticket['created_at']}",
            f"  problem_description: >",
            f"    {ticket['problem_description']}",
            f"  root_cause: >",
            f"    {ticket['root_cause']}",
            f"  recommended_actions: >",
            f"    {ticket['recommended_actions']}",
            f"  tags:",
        ]
        for tag in ticket["tags"]:
            yaml_lines.append(f"    - {tag}")
        yaml_lines.append("...\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(yaml_lines))

        log.info("RCA: improvement ticket written to %s", filepath)
        return filepath

    def _compute_deadline(self, priority: str) -> str:
        """根据优先级计算截止日期。"""
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        if priority == "P0":
            deadline = now + timedelta(hours=24)
        elif priority == "P1":
            deadline = now + timedelta(days=3)
        elif priority == "P2":
            deadline = now + timedelta(days=7)
        elif priority == "P3":
            deadline = now + timedelta(days=14)
        else:
            deadline = now + timedelta(days=30)

        return deadline.isoformat()

    # ── 变更历史注入 (用于测试) ────────────────────────────────────────

    def inject_change_history(self, changes: list[dict]):
        """注入变更历史 (用于测试)。"""
        self._change_history = changes

    def inject_kg_articles(self, articles: list[dict]):
        """注入 KG 知识条目 (用于测试)。"""
        self._kg_articles = articles


__all__ = [
    "RCAEngine",
    "RCAReport",
    "KPI_METADATA",
]
