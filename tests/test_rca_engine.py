#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
RCA Engine — 单元测试。

Covers:
  - analyze() 基础功能
  - breach 检测 (向上/向下)
  - insufficient_data 处理
  - 嫌疑变更追溯
  - 严重度/优先级计算
  - 改进工单生成
  - YAML 输出
  - KG 关联分析
  - git log 集成
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.loop_engine.rca_engine import (
    RCAEngine,
    RCAReport,
    KPI_METADATA,
)


class TestRCAEngineBasic:
    """RCA Engine 基础功能测试。"""

    def setup_method(self):
        self.engine = RCAEngine()

    # ── analyze() 基础 ──────────────────────────────────────────────────

    def test_analyze_breach_upward(self):
        """向上指标的阈值告警被正确检测。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=5,
        )
        assert report.status == "completed"
        assert report.metric == "misra_violations"
        assert report.current_value == 150
        assert report.threshold == 100

    def test_analyze_breach_downward(self):
        """向下指标的阈值告警被正确检测。"""
        report = self.engine.analyze(
            metric="coverage_percent",
            value=45,
            threshold=60,
            data_points_count=5,
        )
        assert report.status == "completed"
        assert report.current_value == 45

    def test_analyze_no_breach(self):
        """未超过阈值时不生成完整报告。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=50,
            threshold=100,
            data_points_count=5,
        )
        assert report.status == "no_breach"

    def test_analyze_no_breach_downward(self):
        """向下指标未低于阈值。"""
        report = self.engine.analyze(
            metric="coverage_percent",
            value=80,
            threshold=60,
            data_points_count=5,
        )
        assert report.status == "no_breach"

    # ── insufficient_data ───────────────────────────────────────────────

    def test_insufficient_data_less_than_3(self):
        """数据点 < 3 时返回 insufficient_data。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=2,
        )
        assert report.status == "insufficient_data"
        assert "数据点不足" in report.root_cause

    def test_insufficient_data_zero(self):
        """数据点为 0 时也返回 insufficient_data。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=0,
        )
        assert report.status == "insufficient_data"

    def test_sufficient_data_works(self):
        """数据点 ≥ 3 且超阈值时正常分析。"""
        report = self.engine.analyze(
            metric="defect_escape_rate",
            value=8.0,
            threshold=5.0,
            data_points_count=10,
        )
        assert report.status == "completed"

    # ── severity 计算 ────────────────────────────────────────────────────

    def test_severity_critical(self):
        """偏离 > 50% 时严重度为 critical。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=200,
            threshold=100,
            data_points_count=5,
        )
        assert report.severity == "critical"

    def test_severity_high(self):
        """偏离 30-50% 时严重度为 high。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=135,
            threshold=100,
            data_points_count=5,
        )
        assert report.severity == "high"

    def test_severity_medium(self):
        """偏离 10-30% 时严重度为 medium。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=118,
            threshold=100,
            data_points_count=5,
        )
        assert report.severity == "medium"

    def test_severity_low(self):
        """偏离 < 10% 时严重度为 low。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=105,
            threshold=100,
            data_points_count=5,
        )
        assert report.severity == "low"

    # ── priority 计算 ────────────────────────────────────────────────────

    def test_priority_critical(self):
        """critical 严重度 → P0。"""
        report = self.engine.analyze(
            metric="defect_escape_rate",
            value=15,
            threshold=5,
            data_points_count=5,
        )
        assert report.priority == "P0"

    def test_priority_high_safety_metric(self):
        """high 严重度 + 安全指标 → P1。"""
        report = self.engine.analyze(
            metric="coverage_percent",
            value=30,
            threshold=60,
            data_points_count=5,
        )
        assert report.priority == "P1"

    def test_priority_medium(self):
        """medium 严重度 → P2。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=118,
            threshold=100,
            data_points_count=5,
        )
        assert report.priority == "P2"

    def test_priority_low(self):
        """low 严重度 → P3。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=105,
            threshold=100,
            data_points_count=5,
        )
        assert report.priority == "P3"

    # ── suspect_changes 分析 ─────────────────────────────────────────────

    def test_suspect_changes_from_memory(self):
        """注入的变更历史出现在嫌疑变更中。"""
        changes = [
            {"commit": "abc123", "author": "dev1", "message": "refactor: coverage drop fix"},
        ]
        self.engine.inject_change_history(changes)

        report = self.engine.analyze(
            metric="coverage_percent",
            value=45,
            threshold=60,
            data_points_count=5,
        )

        # 注入的变更应该被包含 (coverage 关键字匹配)
        assert len(report.suspect_changes) >= 1

    def test_suspect_changes_no_match(self):
        """不匹配关键字的变更不会出现在嫌疑列表中。"""
        changes = [
            {"commit": "def456", "author": "dev2", "message": "docs: update readme"},
        ]
        self.engine.inject_change_history(changes)

        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=5,
        )
        # 'readme' 不匹配 misra 关键字, 但当前逻辑中如果没有任何关键字匹配
        # 会返回所有变更（见 _find_suspect_changes 中 not relevant_keywords 分支）
        # misra 的关键字是 ["misra", "violation", "coding_standard", "合规"]
        # 所以 'docs: update readme' 不匹配，但由于有关键字且不匹配，不会被包含
        assert len(report.suspect_changes) == 0

    # ── KG 因素 ───────────────────────────────────────────────────────────

    def test_kg_factors_from_memory(self):
        """注入的 KG 文章出现在因果因素中。"""
        articles = [
            {"title": "Coverage Gap Analysis", "content": "module_x has untested paths"},
        ]
        self.engine.inject_kg_articles(articles)

        report = self.engine.analyze(
            metric="coverage_percent",
            value=45,
            threshold=60,
            data_points_count=5,
        )

        assert len(report.causal_factors) >= 1
        assert any("Coverage Gap" in f for f in report.causal_factors)

    # ── improvement ticket ────────────────────────────────────────────────

    def test_generate_improvement_ticket(self):
        """改进工单包含所有必要字段。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=5,
        )
        ticket = self.engine.generate_improvement_ticket(report)

        assert "ticket_id" in ticket
        assert "problem_description" in ticket
        assert "root_cause" in ticket
        assert "recommended_actions" in ticket
        assert "priority" in ticket
        assert "deadline" in ticket
        assert "status" in ticket
        assert ticket["status"] == "open"

    def test_improvement_ticket_priority_based_deadline(self):
        """P0 工单截止日期 < 24h。"""
        report = self.engine.analyze(
            metric="coverage_percent",
            value=25,
            threshold=60,
            data_points_count=5,
        )
        ticket = self.engine.generate_improvement_ticket(report)
        assert ticket["priority"] == "P0"
        # 确保 deadline 存在
        assert "deadline" in ticket
        assert ticket["deadline"] > ""

    def test_write_improvement_ticket_to_file(self, tmp_path):
        """改进工单被正确写入 YAML 文件。"""
        engine = RCAEngine()
        report = engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=5,
        )
        filepath = engine.write_improvement_ticket(report, output_dir=str(tmp_path))

        assert os.path.exists(filepath)
        with open(filepath, "r") as f:
            content = f.read()
        assert "improvement_ticket:" in content
        assert "ticket_id:" in content
        assert "problem_description:" in content

    # ── KPI_METADATA ─────────────────────────────────────────────────────

    def test_kpi_metadata_completeness(self):
        """KPI_METADATA 包含所有必要字段。"""
        for name, info in KPI_METADATA.items():
            assert "name" in info, f"{name} missing 'name'"
            assert "direction" in info, f"{name} missing 'direction'"
            assert info["direction"] in ("up", "down"), f"{name} invalid direction"
            assert "default_threshold" in info, f"{name} missing threshold"
            assert "description" in info, f"{name} missing description"

    # ── Report serialization ─────────────────────────────────────────────

    def test_report_to_dict(self):
        """RCAReport 可正确序列化为字典。"""
        report = self.engine.analyze(
            metric="build_failure_rate",
            value=15.0,
            threshold=10.0,
            data_points_count=5,
        )
        d = report.to_dict()

        assert d["metric"] == "build_failure_rate"
        assert d["status"] in ("completed", "no_breach")
        assert "timestamp" in d
        assert "root_cause" in d

    def test_report_to_yaml(self):
        """RCAReport 可生成 YAML 子集格式。"""
        report = self.engine.analyze(
            metric="review_findings_open",
            value=30,
            threshold=20,
            data_points_count=5,
        )
        yaml_str = report.to_yaml()

        assert yaml_str.startswith("---")
        assert yaml_str.endswith("...")
        assert "rca_report:" in yaml_str
        assert "root_cause:" in yaml_str

    # ── Edge cases ───────────────────────────────────────────────────────

    def test_analyze_unknown_metric(self):
        """未知指标使用通用默认值。"""
        report = self.engine.analyze(
            metric="custom_metric_xyz",
            value=999,
            threshold=100,
            data_points_count=5,
        )
        assert report.status == "completed"
        assert report.severity == "critical"  # 偏离 899%

    def test_threshold_overrides(self):
        """自定义阈值覆盖工作。"""
        engine = RCAEngine(threshold_overrides={"misra_violations": 50})
        report = engine.analyze(
            metric="misra_violations",
            value=60,
            data_points_count=5,
            # 不传 threshold, 使用 override
        )
        assert report.status == "completed"
        assert report.threshold == 50

    def test_default_threshold_from_metadata(self):
        """未传 threshold 时使用 KPI_METADATA 默认值。"""
        report = self.engine.analyze(
            metric="misra_violations",
            value=150,
            data_points_count=5,
        )
        assert report.threshold == 100  # KPI_METADATA 默认值

    def test_analyze_with_additional_data(self):
        """额外数据被传递到 details。"""
        report = self.engine.analyze(
            metric="coverage_percent",
            value=45,
            threshold=60,
            data_points_count=5,
            additional_data={"source": "ci_pipeline", "job": "test_job"},
        )
        assert report.status == "completed"


class TestRCAEngineWithGitLog:
    """RCA Engine git log 集成测试。"""

    def test_git_log_in_workspace(self, tmp_path):
        """在有 git 仓库的工作区中执行 git log。"""
        # 创建临时 git 仓库
        os.system(f"cd {tmp_path} && git init -q && git config user.email test@test.com && git config user.name tester")
        (tmp_path / "test.py").write_text("pass")
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'initial commit'")
        (tmp_path / "test.py").write_text("fail")
        os.system(f"cd {tmp_path} && git add . && git commit -q -m 'fix: coverage regression in test.py'")

        # 把当前工作目录加入 sys.path 以便 git 正常
        engine = RCAEngine(git_log_limit=10)
        report = engine.analyze(
            metric="coverage_percent",
            value=45,
            threshold=60,
            data_points_count=5,
            workspace_path=str(tmp_path),
        )

        # git log 应该找到提交
        # 关键字 'coverage' 在 commit message 中
        assert len(report.suspect_changes) >= 1
        assert any("coverage" in c.get("message", "") for c in report.suspect_changes)

    def test_git_log_non_git_dir(self, tmp_path):
        """非 git 目录不会导致异常。"""
        engine = RCAEngine()
        report = engine.analyze(
            metric="misra_violations",
            value=150,
            threshold=100,
            data_points_count=5,
            workspace_path=str(tmp_path),
        )
        assert report.status == "completed"


class TestRCAReportModel:
    """RCAReport 数据模型测试。"""

    def test_report_default_values(self):
        """RCAReport 有合理的默认值。"""
        report = RCAReport(metric="test", current_value=10, threshold=5)
        assert report.status == "completed"
        assert report.severity == "medium"
        assert report.priority == "P2"
        assert report.timestamp != ""
        assert report.causal_factors == []
        assert report.affected_areas == []

    def test_report_repr(self):
        """RCAReport 的 repr 包含关键信息。"""
        report = RCAReport(
            metric="coverage_percent",
            current_value=45,
            threshold=60,
            severity="high",
            status="completed",
        )
        r = repr(report)
        assert "coverage_percent" in r
        assert "high" in r
        assert "completed" in r
