
# @tests src/yuleosh/pipeline/steps.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Deep coverage tests for step_handlers/__init__.py — branches not covered by
existing tests.

Target: __init__.py — verify PIPELINE_STEPS structure, _resolve_handler
fallback (always uses legacy_fn since Sprint 3 hardcoded
_have_step_classes = False), and re-exports.

Note: __init__.py has _have_step_classes = False (Sprint 3 eliminated
the dual-path). The if _have_step_classes block in _resolve_handler
is dead code.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


class TestHaveStepClassesAlwaysFalse:
    """GIVEN Sprint 3 hardcoded _have_step_classes = False
    THEN the dual-path is eliminated."""

    def test_have_step_classes_always_false(self):
        from yuleosh.pipeline.step_handlers import _have_step_classes
        assert _have_step_classes is False

    def test_resolve_handler_always_returns_legacy(self):
        """GIVEN Sprint 3 simplified _resolve_handler
        WHEN _resolve_handler is called
        THEN it returns legacy_fn (no dual-path logic)."""
        from yuleosh.pipeline.step_handlers import _resolve_handler

        def dummy_fn():
            return "legacy"

        result = _resolve_handler("super-analysis", dummy_fn)
        assert result is dummy_fn

        result = _resolve_handler("nonexistent-step", dummy_fn)
        assert result is dummy_fn


class TestPipelineStepsStructure:
    """PIPELINE_STEPS has correct structure and count."""

    def test_pipeline_steps_minimum_entries(self):
        """注册表数量不写死（单一事实源）；合理下限防误删（r22 合并后 24 步，
        编排层 10 Gate 视图；低于 20 说明步骤被误删导致能力退化）。"""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(PIPELINE_STEPS) >= 20

    def test_each_entry_has_4_elements(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        for entry in PIPELINE_STEPS:
            assert len(entry) == 4

    def test_handlers_are_callable(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        for step_key, agent, desc, handler in PIPELINE_STEPS:
            assert callable(handler), f"{step_key} handler is not callable"

    def test_step_keys(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        keys = [e[0] for e in PIPELINE_STEPS]
        expected = [
            # ── G0 系统层 (SYS.1~SYS.5, M1 头部插入) ──
            "sys-requirements", "sys-architecture", "sys-verification",
            "sys-integration", "sys-validation", "sys-req-review",
            # ── G1 SWE.1 Requirements ──
            "spec-check", "super-analysis", "prd", "prd-review",
            "architecture", "arch-review", "development", "development-review",
            "codegen-deploy",
            "internal-code-review", "claude-review", "test-planning",
            "verify-loop", "c-unit-test", "code-review", "misra-review",
            "integration-test", "qemu-verify", "coverage-review",
            "review-critical-safety", "fault-injection",
            "merge-gate", "test-qualification",
            # ── G11 VAL.1 产品确认 ──
            "val-validation", "val-review",
            # ── G12 MAN.6 测量 ──
            "measurement", "measurement-review",
            # ── G13 MAN.5 风险管理 ──
            "risk-assessment", "risk-review",
            # ── G14 ACQ.4 / G15 REU.2 / G16 PIM.3 ──
            "acq4-monitoring", "acq4-review",
            "reu2-reuse", "reu2-review",
            "pim3-improvement", "pim3-review",
            # ── G17 HWE.1~HWE.4 硬件工程 ──
            "hwe1-requirements", "hwe1-review",
            "hwe2-design", "hwe2-review",
            "hwe3-implementation", "hwe3-review",
            "hwe4-verification", "hwe4-review",
            # ── G18 MLE.1~MLE.4 机器学习工程 ──
            "mle1-requirements", "mle1-review",
            "mle2-approach", "mle2-review",
            "mle3-training", "mle3-review",
            "mle4-evaluation", "mle4-review",
            # ── G19 SUP.1/8/9/10 支持过程 ──
            "sup1-quality", "sup1-review",
            "sup8-config", "sup8-review",
            "sup9-problem", "sup9-review",
            "sup10-change", "sup10-review",
            # ── G20 MAN 管理过程 ──
            "man1-charter", "man1-review",
            "man2-requirements", "man2-review",
            "man3-project", "man3-review",
            "man4-quality", "man4-review",
            # ── G21 ACQ/SPL 采购与供应 ──
            "acq1-preparation", "acq1-review",
            "acq2-selection", "acq2-review",
            "acq3-contract", "acq3-review",
            "spl1-tendering", "spl1-review",
            # ── G22 SUP 扩展支持过程 ──
            "sup2-verification", "sup2-review",
            "sup3-validation", "sup3-review",
            "sup4-joint-review", "sup4-review",
            "sup5-audit", "sup5-review",
            "sup6-evaluation", "sup6-review",
            "sup7-documentation", "sup7-review",
            # ── G23 PIM/REU 组织过程 ──
            "pim1-establishment", "pim1-review",
            "pim2-assessment", "pim2-review",
            "reu1-assets", "reu1-review",
            # ── G24 SPL.2 产品发布 ──
            "spl2-release", "spl2-review", "final-report",
        ]
        assert keys == expected

    def test_agents(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        agents = {e[1] for e in PIPELINE_STEPS}
        # r22 重构: codex-verify 并入 verify-loop(小克)、qemu-run 并入 qemu-verify(小克)、
        # merge-gate 归小仓(CM)；Codex/QEMU 仍注册在 AGENT_ROLES 供子 handler 使用。
        assert agents == {"小明", "Claude", "Hermes", "小克", "小马", "小仓"}

    def test_internal_review_is_unresolved_fn(self):
        """step_internal_review and step_claude_test are plain functions."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.step_handlers.execution import step_claude_test
        from yuleosh.pipeline.step_handlers.review_code import step_review_code

        for key, _, _, handler in PIPELINE_STEPS:
            if key == "internal-code-review":
                # v3.4.0: registry binds step_review_code (the real handler);
                # legacy step_internal_review is kept as a re-export alias.
                assert handler is step_review_code
            if key == "verify-loop":
                # r22 重构: self-test/codex-verify/self-test-review 合并为 verify-loop,
                # 内部顺序调用旧 handler（含 step_claude_test）。
                assert handler is not None and callable(handler)

    def test_unresolved_steps_use_legacy_fns(self):
        """Steps wrapped in _resolve_handler use legacy functions."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch

        for key, _, _, handler in PIPELINE_STEPS:
            if key == "super-analysis":
                assert handler is step_super_analysis
            if key == "architecture":
                assert handler is step_claude_arch


class TestGatesContract:
    """R3 契约守护: GATES ↔ PIPELINE_STEPS 全覆盖/无重复/无悬挂/顺序一致."""

    def test_gates_contract_zero_violations(self):
        from yuleosh.pipeline.gates import GATES, validate_gates_contract
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

        step_keys = [e[0] for e in PIPELINE_STEPS]
        violations = validate_gates_contract(step_keys)
        assert violations == [], f"GATES contract violations: {violations}"

    def test_gates_has_25_entries(self):
        from yuleosh.pipeline.gates import GATES
        assert len(GATES) == 25
        # 首尾 Gate 与 ASPICE 对齐（G0 系统层、SPL.2 产品发布）
        assert GATES[0]["gate"] == "G0"
        assert GATES[0]["name"].startswith("SYS")
        assert GATES[-1]["gate"] == "G24"
        assert GATES[-1]["name"].startswith("SPL.2")

    def test_gate_status_worst_wins(self):
        from yuleosh.pipeline.gates import aggregate_gate_status
        # failed > retry > skipped > passed
        statuses = aggregate_gate_status({
            "spec-check": "passed", "super-analysis": "skipped",
            "prd": "retry", "prd-review": "failed",
        })
        assert statuses["G1"] == "failed"

        statuses2 = aggregate_gate_status({
            "spec-check": "passed", "super-analysis": "passed",
            "prd": "passed", "prd-review": "skipped",
        })
        # worst-wins 顺序 failed > retry > skipped > passed：混入 skipped 时
        # 聚合结果应为 skipped（与测试注释的语义一致），非 passed
        assert statuses2["G1"] == "skipped"

    def test_gate_status_all_skipped(self):
        from yuleosh.pipeline.gates import aggregate_gate_status
        statuses = aggregate_gate_status({
            "spec-check": "skipped", "super-analysis": "skipped",
            "prd": "skipped", "prd-review": "skipped",
        })
        assert statuses["G1"] == "skipped"


class TestModuleReExports:
    """Verify all expected symbols are exported."""

    def test_all_exports_exist(self):
        from yuleosh.pipeline.step_handlers import (
            step_spec_check,
            step_super_analysis,
            step_hermes_prd,
            step_internal_review,
            step_claude_arch,
            step_claude_dev,
            step_test_planning,
            step_claude_test,
            step_hermes_review,
            step_final_report,
            step_sys_requirements,
            step_sys_architecture,
            step_sys_verification,
            step_sys_integration,
            step_sys_validation,
            step_review_sys,
            PIPELINE_STEPS,
            _check_llm_key,
            _resolve_handler,
        )
        assert callable(step_spec_check)
        assert callable(step_super_analysis)
        assert callable(step_hermes_prd)
        assert callable(step_internal_review)
        assert callable(step_claude_arch)
        assert callable(step_claude_dev)
        assert callable(step_test_planning)
        assert callable(step_claude_test)
        assert callable(step_hermes_review)
        assert callable(step_final_report)
        assert callable(step_sys_requirements)
        assert callable(step_sys_architecture)
        assert callable(step_sys_verification)
        assert callable(step_sys_integration)
        assert callable(step_sys_validation)
        assert callable(step_review_sys)
        assert isinstance(PIPELINE_STEPS, list)
        assert callable(_check_llm_key) or _check_llm_key is None
        assert callable(_resolve_handler)

    def test_submodules_reachable(self):
        """Direct submodule imports work."""
        from yuleosh.pipeline.step_handlers import spec as _spec
        assert callable(_spec.step_spec_check)

        from yuleosh.pipeline.step_handlers import analysis as _analysis
        assert callable(_analysis.step_super_analysis)

        from yuleosh.pipeline.step_handlers import execution as _exec
        assert callable(_exec.step_claude_arch)

        from yuleosh.pipeline.step_handlers import review as _review
        assert callable(_review.step_hermes_review)

    def test_run_shim_re_exports(self):
        """Backward-compatible re-exports from run.py work."""
        from yuleosh.pipeline.run import (
            step_spec_check,
            step_super_analysis,
            step_hermes_prd,
            step_internal_review,
            step_claude_arch,
            step_claude_dev,
            step_test_planning,
            step_claude_test,
            step_hermes_review,
            step_final_report,
            PIPELINE_STEPS,
        )
        assert callable(step_spec_check)
        # 数量跟随单一事实源：注册表导出完整（不写死具体数字）
        assert len(PIPELINE_STEPS) >= 20
