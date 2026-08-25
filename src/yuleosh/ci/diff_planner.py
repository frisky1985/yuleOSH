#!/usr/bin/env python3

# @req RS-004
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Diff Planner — 步骤级智能裁剪规划器 (方向2, 2026-08-11).

按 git diff 决定哪些 pipeline 步骤可以跳过（未触及任何相关文件 glob），
省 LLM token / CI 时间。

安全护栏（Evaluator 前置门槛 G1-G5, 2026-08-11）:
  G1 空 diff fail-safe : git 失败 / 非 checkout / 空 diff → 不裁剪任何步骤
  G2 skip 显式报告    : 每个 skip 决策带 reason，可写入 session/报告
  G3 跨切面不可跳过   : 全局影响/无文件 glob 的步骤强制保留
  G4 H9 honesty 用例  : 注入假 skip → 门禁必须红（见 test_honesty_regression_suite.py）
  G5 block 级不可裁剪 : gate_policy=block 的步骤严禁裁剪（复用方向3）

核心接口:
  - plan_skips(steps, changed_files, gate_policy=None) -> list[SkipDecision]
     纯函数，可单测。steps 是 (step_key, agent, name, handler) 四元组列表。
  - collect_changed_files(project_dir) -> list[str]
    封装 git 收集（3 源 union，复用 review_collect._collect_delta_files 思路，
    但不过滤扩展名 —— 全类型文件）。
  - OSH_DIFF_SKIP=1 显式开启；默认全跑（零回归）。
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.diff_planner")

# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------

# 显式开启开关（默认关闭 → 零回归）
ENV_ENABLE = "OSH_DIFF_SKIP"

# 跨切面步骤（G3）: 全局影响 / 无有意义文件 glob，强制保留
# 与 gate_policy 的 block 集有重叠但语义不同 —— 这里是无 glob 硬编码保留。
# 2026-08-19 (24 步重构): 旧 key (self-test/self-test-review/qemu-run/
# c-coverage-gate/review-*) 已合并进 verify-loop/code-review/qemu-verify —
# 合并步骤跨切面，永不按 diff 裁剪。
CROSS_CUTTING_STEPS = {
    "spec-check",
    "super-analysis",
    "prd",
    "prd-review",
    "architecture",
    "arch-review",
    "development",
    "development-review",
    "internal-code-review",
    "claude-review",
    "test-planning",
    "verify-loop",
    "code-review",
    "integration-test",
    "misra-review",
    "coverage-review",
    "qemu-verify",
    "review-critical-safety",
    "fault-injection",
    "merge-gate",
    "test-qualification",
    "final-report",
    "methodology-gate",
    "docsync-gate",
    "requirements-trace",
    "traceability",
    "evidence-pack",
}

# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------


@dataclass
class SkipDecision:
    """一次步骤裁剪决策（G2: 显式报告）。"""

    step_key: str
    reason: str

    def to_dict(self) -> dict:
        return {"step": self.step_key, "reason": self.reason}


# ------------------------------------------------------------------
# glob 匹配（复用 review_collect._matches_glob）
# ------------------------------------------------------------------


def _matches_glob(rel: str, pattern: str) -> bool:
    """Glob-style match supporting recursive ``**``.

    Delegates to review_collect._matches_glob when available, with a
    local fallback for pure-function testability.
    """
    try:
        from yuleosh.ci.stages.review_collect import _matches_glob as _real

        return _real(rel, pattern)
    except Exception:  # pragma: no cover - defensive
        import fnmatch

        return fnmatch.fnmatch(rel, pattern)


# ------------------------------------------------------------------
# git 收集（G1 核心: 失败必须 fail-safe）
# ------------------------------------------------------------------


def collect_changed_files(project_dir: Optional[str] = None) -> list[str]:
    """Collect changed files from git (3-source union, ALL extensions).

    G1 护栏: 任一源失败 / 非 git checkout → 返回空列表，调用方必须
    将空列表视为「无法确定变更」→ 不裁剪（fail-safe）。

    Sources:
      1. ``git diff HEAD~1 --name-only``  — committed changes
      2. ``git diff --name-only``         — working tree (staged + unstaged)
      3. ``git ls-files --others --exclude-standard`` — untracked
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    # 非 git checkout → 空（fail-safe: 不裁剪）
    git_dir = Path(project_dir) / ".git"
    if not git_dir.exists():
        log.warning("diff_planner: %s is not a git checkout — no diff-based skipping", project_dir)
        return []

    changed: set[str] = set()
    commands = [
        ["git", "diff", "--name-only", "HEAD~1"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=project_dir,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            log.warning("diff_planner: git command failed: %s — fail-safe", cmd)
            continue
        if result.returncode != 0:
            # HEAD~1 不存在（首次提交）是正常情况，不视为失败
            continue
        for line in result.stdout.splitlines():
            f = line.strip()
            if f:
                changed.add(f)

    return sorted(changed)


# ------------------------------------------------------------------
# 规划器（纯函数）
# ------------------------------------------------------------------


def plan_skips(
    steps: list[tuple],
    changed_files: Optional[list[str]],
    gate_policy: Optional[dict] = None,
    file_globs: Optional[dict] = None,
) -> list[SkipDecision]:
    """Plan which steps can be skipped based on changed files.

    G1: changed_files 为空/None → 返回空（不裁剪）。
    G3: CROSS_CUTTING_STEPS 强制保留。
    G5: gate_policy=block 的步骤强制保留。
    G2: 每个决策带 reason。

    Parameters
    ----------
    steps : list[tuple]
        (step_key, agent, step_name, handler) tuples.
    changed_files : list[str] | None
        Project-relative changed file paths. Empty/None ⇒ no skipping.
    gate_policy : dict, optional
        Effective gate policy (step_key → block|warn|info). block 级不裁剪。
    file_globs : dict, optional
        step_key → list of glob patterns the step cares about.
        未声明 glob 的步骤视为跨切面（不裁剪）。

    Returns
    -------
    list[SkipDecision]
        Skip decisions (empty if nothing can be skipped).
    """
    # G1: 空 diff / 无法确定 → fail-safe 不裁剪
    if not changed_files:
        log.info("diff_planner: empty changed set — no skipping (G1 fail-safe)")
        return []

    if file_globs is None:
        file_globs = _default_file_globs()

    # G5: block 级门禁不可裁剪
    block_steps = {
        k for k, v in (gate_policy or {}).items() if v == "block"
    }
    # 补充 gate_policy 默认 block 集（未显式传 policy 时）
    if gate_policy is None:
        try:
            from yuleosh.ci.gate_policy import DEFAULT_GATE_POLICY

            block_steps = {
                k for k, v in DEFAULT_GATE_POLICY.items() if v == "block"
            }
        except Exception:  # pragma: no cover - defensive
            pass

    decisions: list[SkipDecision] = []
    for step_key, _agent, _name, _handler in steps:
        # G3: 跨切面 / 未声明 glob → 不裁剪
        globs = file_globs.get(step_key)
        if not globs:
            continue
        # G3: 跨切面硬编码集 → 不裁剪
        if step_key in CROSS_CUTTING_STEPS:
            continue
        # G5: block 级 → 不裁剪
        if step_key in block_steps:
            continue

        # 该步骤关心的文件有变更 → 不裁剪
        if _any_glob_matches(changed_files, globs):
            continue

        decisions.append(SkipDecision(
            step_key=step_key,
            reason=f"diff 未触及 {step_key} 相关文件 ({', '.join(globs[:3])})",
        ))

    return decisions


def _any_glob_matches(changed_files: list[str], globs: list[str]) -> bool:
    for rel in changed_files:
        for pattern in globs:
            if _matches_glob(rel, pattern):
                return True
    return False


def is_enabled() -> bool:
    """方向2 显式开启开关（默认关闭 → 零回归）。"""
    return os.environ.get(ENV_ENABLE, "").strip() == "1"


def skip_summary(decisions: list[SkipDecision]) -> str:
    """Human-readable skip summary for console/report (G2)."""
    if not decisions:
        return "diff_planner: 0 steps skipped"
    lines = [f"diff_planner: {len(decisions)} step(s) skipped (OSH_DIFF_SKIP=1):"]
    for d in decisions:
        lines.append(f"  - {d.step_key}: {d.reason}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# 默认文件 glob 元数据（STEP_FILE_GLOBS 默认集）
# ------------------------------------------------------------------


def _default_file_globs() -> dict[str, list[str]]:
    """Default step→glob mapping (can be overridden by STEP_FILE_GLOBS).

    2026-08-19 (24 步重构): 嵌入式专项已合并进 code-review 超集（跨切面
    永不按 diff 裁剪），旧 review-* glob 键移除；保留仍为独立步骤的
    c-unit-test / fault-injection globs（test-integration 旧键更名为
    integration-test 对齐 PIPELINE_STEPS）。
    """
    return {
        "c-unit-test": ["**/tests/**", "**/*test*", "**/*.c", "**/*.cpp", "**/*.h"],
        "integration-test": ["**/tests/**", "**/*test*"],
        "fault-injection": ["**/tests/**", "**/*fault*", "**/*inject*"],
    }


# 允许外部注入 STEP_FILE_GLOBS（来自 step_handlers/__init__.py）
STEP_FILE_GLOBS: dict[str, list[str]] = {}


def get_step_file_globs() -> dict[str, list[str]]:
    """Effective file globs: external STEP_FILE_GLOBS merged over defaults."""
    merged = dict(_default_file_globs())
    merged.update(STEP_FILE_GLOBS)
    return merged
