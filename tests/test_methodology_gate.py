#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for the Methodology Gate (L2) — .yuleosh/agents/METHODOLOGY.md 契约门禁。

验证 run_methodology_gate 的六维检查行为:
- §1 grilling 对齐  (hard) — spec 含决策记录 → pass; 缺 → fail
- §2 统一语言      (hard) — CONTEXT.md 纯术语表 → pass; 缺/含实现 → fail
- §3 双轴评审      (soft) — 报告含 Standards+Spec → pass; 缺 → warning
- §4 调试回路      (soft) — 调试报告含复现 → pass; 缺 → warning
- §5 垂直切片      (soft) — plan 含 Blocked by → pass; 缺 → warning
- §6 交接纪律      (soft) — handoff 含建议技能+引用 → pass; 缺 → warning
"""

import sys
from pathlib import Path

import pytest

from yuleosh.ci.stages.methodology_gate import (
    CHECKS,
    run_methodology_gate,
    _check_grilling,
    _check_domain_model,
    _check_two_axis_review,
    _check_tight_loop,
    _check_vertical_slices,
    _check_handoff,
)


class FakeCI:
    def __init__(self):
        self.stages = []

    def add_stage(self, name, status, msg=""):
        self.stages.append((name, status, msg))


@pytest.fixture
def proj(tmp_path):
    """A project tree that passes every methodology check."""
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec v1.0.0\n\n## 9. 决策记录（Grilling/对齐沉淀）\n\n- **决策（X-1）**: 采用 A 方案。\n",
        encoding="utf-8",
    )
    (tmp_path / "CONTEXT.md").write_text(
        "# CONTEXT.md — 术语表\n\n- **Module** — 有接口和实现的东西。\n",
        encoding="utf-8",
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "review.md").write_text(
        "# Review\n\n## Standards\n- 符合规范\n\n## Spec\n- 忠实实现\n",
        encoding="utf-8",
    )
    (tmp_path / "reports" / "rca.md").write_text(
        "# RCA\n\n复现步骤: 1. 启动 2. 触发\n",
        encoding="utf-8",
    )
    (tmp_path / ".osh" / "plans").mkdir(parents=True)
    (tmp_path / ".osh" / "plans" / "plan.md").write_text(
        "# Plan\n\n## Ticket 01\n**Blocked by:** None — can start immediately\n",
        encoding="utf-8",
    )
    (tmp_path / "handoff.md").write_text(
        "# Handoff\n\nsuggested skills: tdd\n参考 [spec](.osh/specs/v1.0.0/spec.md)\n",
        encoding="utf-8",
    )
    return tmp_path


# ── 单维检查 ──


def test_grilling_pass_with_decision_log(proj):
    ok, msg = _check_grilling(str(proj))
    assert ok
    assert "决策记录" in msg


def test_grilling_fail_without_log(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "spec.md").write_text("# Spec\n\nSHALL do X\n", encoding="utf-8")
    ok, _ = _check_grilling(str(tmp_path))
    assert not ok


def test_domain_model_pass(proj):
    ok, msg = _check_domain_model(str(proj))
    assert ok
    assert "纯术语表" in msg


def test_domain_model_fail_when_missing(tmp_path):
    ok, _ = _check_domain_model(str(tmp_path))
    assert not ok


def test_domain_model_fail_with_impl_details(tmp_path):
    (tmp_path / "CONTEXT.md").write_text("# CONTEXT\n\ndef foo():\n    pass\n", encoding="utf-8")
    ok, _ = _check_domain_model(str(tmp_path))
    assert not ok


def test_two_axis_pass(proj):
    ok, _ = _check_two_axis_review(str(proj))
    assert ok


def test_tight_loop_pass(proj):
    ok, _ = _check_tight_loop(str(proj))
    assert ok


def test_vertical_slices_pass(proj):
    ok, _ = _check_vertical_slices(str(proj))
    assert ok


def test_handoff_pass(proj):
    ok, _ = _check_handoff(str(proj))
    assert ok


# ── 聚合门禁 ──


def test_gate_passes_on_compliant_project(proj):
    ci = FakeCI()
    ok = run_methodology_gate(str(proj), ci)
    assert ok
    # no hard failures
    assert not any(status == "failed" for _, status, _ in ci.stages)


def test_gate_blocks_on_missing_context(tmp_path):
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec\n\n## 9. 决策记录\n\n- 决策\n", encoding="utf-8"
    )
    ci = FakeCI()
    ok = run_methodology_gate(str(tmp_path), ci)
    assert not ok
    assert any(name == "methodology-domain-model" and status == "failed"
               for name, status, _ in ci.stages)


def test_gate_skips_non_methodology_project(tmp_path):
    """无 spec/CONTEXT/.yuleosh 的临时项目 → 门禁跳过，不阻断。"""
    (tmp_path / ".yuleosh").mkdir()
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text("ci:\n  layers: [1]\n", encoding="utf-8")
    ci = FakeCI()
    ok = run_methodology_gate(str(tmp_path), ci)
    assert ok
    assert any(name == "methodology-gate" and status == "skipped"
               for name, status, _ in ci.stages)


def test_gate_hard_checks_are_defined():
    """The two hard checks (grilling, domain-model) must always be present."""
    assert CHECKS["grilling-alignment"][1] == "hard"
    assert CHECKS["domain-model"][1] == "hard"


def test_gate_has_six_dimensions():
    assert set(CHECKS.keys()) == {
        "grilling-alignment",
        "domain-model",
        "two-axis-review",
        "tight-loop-debug",
        "vertical-slices",
        "handoff",
    }
