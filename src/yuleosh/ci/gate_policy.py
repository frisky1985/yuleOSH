#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Gate Policy Matrix — 门禁强度矩阵 (方向3, 2026-08-11).

将 pipeline 步骤 verdict 的处置从「一刀切软失败」显式化为三档门禁强度:

  - block: verdict failed → 中断 pipeline（依赖步骤不再执行，session.status=failed）
  - warn : verdict failed → 标记 failed + 记 errors + 继续（现状行为，默认）
  - info : verdict failed → 仅 stage 记录，不进 errors（纯信息）

同构先例（收拢而非新建）:
  - MisraProfile.block_on（ci/config.py）
  - code_categories[].action / block_on（ci/config.py）
  - is_strict() / is_misra_fail_fast()（ci/config.py）
  - review finding severity（pipeline/step_handlers/*.py）

覆盖机制: `.yuleosh/ci-config.yaml` → `ci.gate_policy: {step_key: block|warn|info}`
合并到默认矩阵，显式覆盖优先。

核心接口:
  - resolve_gate(step_key, policy=None) -> "block" | "warn" | "info"  （纯函数，可单测）
  - load_gate_policy(project_dir) -> dict                            （读配置 + 合并默认）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.gate_policy")

# ------------------------------------------------------------------
# 门禁强度常量
# ------------------------------------------------------------------

GATE_BLOCK = "block"
GATE_WARN = "warn"
GATE_INFO = "info"

VALID_LEVELS = (GATE_BLOCK, GATE_WARN, GATE_INFO)

# 默认档：未显式声明的步骤一律 warn（保持现状「记 errors 但不断链」）
DEFAULT_LEVEL = GATE_WARN

# ------------------------------------------------------------------
# 默认门禁强度矩阵
# ------------------------------------------------------------------
# 设计原则（Evaluator 约束 2026-08-11）:
#   - block: 只给「语义上不可绕过」的关键门禁（P0 GATE / merge gate / 覆盖率 / 合格性）
#   - warn : 其余 review/gate 步骤（保持现状：verdict failed 记 errors 但不断链）
#   - info : 低风险、纯记录步骤
# 注意: 默认矩阵保守（默认 block 给关键门禁），降级（block→warn）必须由
# ci-config.yaml 显式声明 —— 防止安全项目「带病合并」。

DEFAULT_GATE_POLICY: dict[str, str] = {
    # ⛔ P0 关键门禁 — 不可绕过
    "review-critical-safety": GATE_BLOCK,
    "merge-gate": GATE_BLOCK,
    "c-coverage-gate": GATE_BLOCK,
    "coverage-gate": GATE_BLOCK,
    "test-qualification": GATE_BLOCK,
    # 低风险、纯记录
    "spec-check": GATE_INFO,
    "final-report": GATE_INFO,
}


def resolve_gate(step_key: str, policy: Optional[dict] = None) -> str:
    """Resolve the gate strength for a pipeline step.

    Parameters
    ----------
    step_key : str
        Pipeline step key (e.g. ``"review-critical-safety"``).
    policy : dict, optional
        Effective gate policy (default matrix + YAML overrides merged).
        If None, uses the built-in :data:`DEFAULT_GATE_POLICY`.

    Returns
    -------
    str
        One of ``"block"`` | ``"warn"`` | ``"info"``.

    Notes
    -----
    Pure function — no I/O, no config loading. Safe to unit test.
    """
    if not step_key:
        return DEFAULT_LEVEL
    if policy is not None:
        level = policy.get(step_key)
        if level in VALID_LEVELS:
            return level
    return DEFAULT_GATE_POLICY.get(step_key, DEFAULT_LEVEL)


# ------------------------------------------------------------------
# 配置加载
# ------------------------------------------------------------------


def load_gate_policy(project_dir: Optional[str] = None) -> dict:
    """Load effective gate policy for a project.

    Merges the built-in :data:`DEFAULT_GATE_POLICY` with per-project
    overrides from ``.yuleosh/ci-config.yaml`` → ``ci.gate_policy``.

    Returns
    -------
    dict
        Effective policy mapping step_key → level.
    """
    merged = dict(DEFAULT_GATE_POLICY)

    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    cfg_path = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if not cfg_path.exists():
        return merged

    try:
        import yaml  # type: ignore[import-untyped]

        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:  # pragma: no cover - defensive
        log.warning("Cannot load %s for gate policy: %s", cfg_path, e)
        return merged

    ci_block = raw.get("ci", {})
    if not isinstance(ci_block, dict):
        return merged

    overrides = ci_block.get("gate_policy", {})
    if not isinstance(overrides, dict):
        return merged

    for key, level in overrides.items():
        if level in VALID_LEVELS:
            merged[str(key)] = level
        else:
            log.warning(
                "gate_policy: invalid level %r for step %r (must be block|warn|info) — ignored",
                level, key,
            )

    return merged


def describe_gate_policy(policy: dict) -> str:
    """Human-readable summary of a gate policy (for reports/CLI)."""
    counts = {GATE_BLOCK: 0, GATE_WARN: 0, GATE_INFO: 0}
    for level in policy.values():
        if level in counts:
            counts[level] += 1
    return (
        f"gate policy: {counts[GATE_BLOCK]} block / "
        f"{counts[GATE_WARN]} warn / {counts[GATE_INFO]} info "
        f"({len(policy)} steps)"
    )
