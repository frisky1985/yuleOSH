# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


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

    def test_pipeline_steps_has_10_entries(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(PIPELINE_STEPS) == 10

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
            "spec-check", "super-analysis", "prd", "internal-review",
            "architecture", "development", "test-planning",
            "self-test", "code-review", "final-report",
        ]
        assert keys == expected

    def test_agents(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        agents = {e[1] for e in PIPELINE_STEPS}
        assert agents == {"小明", "Claude", "Hermes"}

    def test_internal_review_is_unresolved_fn(self):
        """step_internal_review and step_claude_test are plain functions."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        for key, _, _, handler in PIPELINE_STEPS:
            if key == "internal-review":
                assert handler is step_internal_review
            if key == "self-test":
                assert handler is step_claude_test

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
        assert len(PIPELINE_STEPS) == 10
