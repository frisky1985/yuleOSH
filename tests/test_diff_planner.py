#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Diff Planner 单元测试 (方向2, 2026-08-11).

覆盖 Evaluator 前置门槛:
  G1 空 diff fail-safe
  G2 skip 显式报告
  G3 跨切面步骤不可跳过
  G5 block 级步骤不可裁剪
  纯函数 plan_skips + collect_changed_files 非 git checkout fail-safe
"""

import os
import sys
from pathlib import Path

import pytest

from yuleosh.ci.diff_planner import (
    CROSS_CUTTING_STEPS,
    SkipDecision,
    collect_changed_files,
    is_enabled,
    plan_skips,
    skip_summary,
)

# (step_key, agent, name, handler) 四元组 mock
# r22 (2026-08-19): 嵌入式专项已合并进 code-review 超集（跨切面永不按 diff
# 裁剪），旧 review-linker/review-startup/review-rtos/review-memory 不再是
# 独立步骤 —— 与 _default_file_globs / PIPELINE_STEPS 保持一致。
MOCK_STEPS = [
    ("spec-check", "小明", "合规检查", lambda s: ""),
    ("code-review", "小克", "集成审查 + 嵌入式专项 (合并超集)", lambda s: ""),
    ("review-critical-safety", "小明", "P0 GATE", lambda s: ""),
    ("merge-gate", "小仓", "CM Gate", lambda s: ""),
    ("final-report", "小明", "最终报告", lambda s: ""),
    ("c-unit-test", "小克", "C 单元测试", lambda s: ""),
    ("integration-test", "小克", "接口集成测试", lambda s: ""),
    ("fault-injection", "小克", "故障注入测试", lambda s: ""),
]

# 默认 glob 由 diff_planner._default_file_globs 提供；测试用其内置集
from yuleosh.ci.diff_planner import _default_file_globs  # noqa: E402

DEFAULT_GLOBS = _default_file_globs()


class TestPlanSkipsG1:
    """G1: 空 diff fail-safe。"""

    def test_empty_changed_no_skips(self):
        """changed=[] → 无任何裁剪。"""
        decisions = plan_skips(MOCK_STEPS, [], gate_policy={}, file_globs=DEFAULT_GLOBS)
        assert decisions == []

    def test_none_changed_no_skips(self):
        decisions = plan_skips(MOCK_STEPS, None, gate_policy={}, file_globs=DEFAULT_GLOBS)
        assert decisions == []


class TestPlanSkipsG2:
    """G2: skip 显式报告（带 reason）。"""

    def test_skip_decision_has_reason(self):
        """裁剪决策带 reason，可序列化。"""
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        for d in decisions:
            assert isinstance(d, SkipDecision)
            assert d.step_key
            assert d.reason
            assert "未触及" in d.reason or "跳过" in d.reason or "diff" in d.reason

    def test_skip_summary_lists_steps(self):
        """skip_summary 显式列出被裁剪步骤（G2 报告）。"""
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        summary = skip_summary(decisions)
        assert "skipped" in summary
        for d in decisions:
            assert d.step_key in summary


class TestPlanSkipsG3:
    """G3: 跨切面步骤不可跳过。"""

    def test_cross_cutting_never_skipped(self):
        """final-report / merge-gate / spec-check 永不裁剪。"""
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        for step in ["spec-check", "final-report", "merge-gate", "review-critical-safety"]:
            assert step not in skipped, f"跨切面步骤 {step} 被裁剪！"

    def test_cross_cutting_set_defined(self):
        """CROSS_CUTTING_STEPS 非空且含关键步骤。"""
        assert "final-report" in CROSS_CUTTING_STEPS
        assert "merge-gate" in CROSS_CUTTING_STEPS
        assert "review-critical-safety" in CROSS_CUTTING_STEPS


class TestPlanSkipsG5:
    """G5: block 级步骤不可裁剪。"""

    def test_block_gate_never_skipped(self):
        """gate_policy=block 的步骤即使 glob 不匹配也不裁剪。"""
        policy = {"c-unit-test": "block"}
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy=policy, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        assert "c-unit-test" not in skipped

    def test_default_block_policy_respected(self):
        """未传 policy 时使用 DEFAULT_GATE_POLICY 的 block 集。"""
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy=None, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        # merge-gate / review-critical-safety 在默认 block 集
        assert "merge-gate" not in skipped
        assert "review-critical-safety" not in skipped


class TestPlanSkipsBehavior:
    """正常裁剪行为。"""

    def test_linker_script_change_keeps_code_review(self):
        """变更 linker 脚本 → code-review（合并超集）保留。"""
        decisions = plan_skips(
            MOCK_STEPS, ["linker/STM32.ld"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        assert "code-review" not in skipped

    def test_src_change_keeps_cross_cutting_steps(self):
        """变更 src/main.c → r22 后嵌入式专项全并入跨切面集，永不按 diff 裁剪。"""
        decisions = plan_skips(
            MOCK_STEPS, ["src/main.c"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        # r22: 嵌入式专项已合并进 code-review 超集（跨切面，永不裁剪）
        assert "code-review" not in skipped
        # integration-test / fault-injection 也在 CROSS_CUTTING_STEPS → 不裁剪
        assert "integration-test" not in skipped
        assert "fault-injection" not in skipped
        # c-unit-test glob 含 *.c → main.c 匹配 → 保留
        assert "c-unit-test" not in skipped

    def test_docs_change_skips_c_unit_test(self):
        """变更 docs/*.md → c-unit-test glob 不匹配 → 被裁剪（裁剪机制仍生效）。"""
        decisions = plan_skips(
            MOCK_STEPS, ["docs/readme.md"], gate_policy={}, file_globs=DEFAULT_GLOBS
        )
        skipped = {d.step_key for d in decisions}
        assert "c-unit-test" in skipped
        # 跨切面步骤仍不裁剪
        assert "code-review" not in skipped

    def test_no_glob_step_not_skipped(self):
        """未声明 glob 的步骤 → 不裁剪（视为跨切面）。"""
        steps = [("custom-step", "X", "自定义", lambda s: "")]
        decisions = plan_skips(steps, ["src/main.c"], gate_policy={}, file_globs={})
        assert decisions == []


class TestCollectChangedFiles:
    """collect_changed_files G1 fail-safe。"""

    def test_non_git_dir_returns_empty(self, tmp_path):
        """非 git checkout → 空列表（fail-safe 不裁剪）。"""
        assert collect_changed_files(str(tmp_path)) == []

    def test_git_dir_returns_list(self):
        """git checkout → 返回列表（可能为空）。"""
        files = collect_changed_files(".")
        assert isinstance(files, list)


class TestIsEnabled:
    """OSH_DIFF_SKIP 开关。"""

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("OSH_DIFF_SKIP", raising=False)
        assert is_enabled() is False

    def test_enabled_with_env(self, monkeypatch):
        monkeypatch.setenv("OSH_DIFF_SKIP", "1")
        assert is_enabled() is True

    def test_disabled_with_env_0(self, monkeypatch):
        monkeypatch.setenv("OSH_DIFF_SKIP", "0")
        assert is_enabled() is False
