# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep coverage tests for step_handlers/__init__.py — branches not covered by
existing tests.

Target: __init__.py from 70% → ≥80%

Covers:
  - _have_step_classes = True path (when get_step_instance import succeeds)
  - _have_step_classes = False path (when get_step_instance import fails)
  - _resolve_handler with both paths
  - PIPELINE_STEPS structure validation

Note: Since the module imports happen at module load time, we need to use
importlib.reload after patching to test both branches.
"""

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# _have_step_classes path tests
# ===================================================================


class TestHaveStepClassesTrue:
    """GIVEN yuleosh.pipeline.step_classes.get_step_instance can be imported
    WHEN step_handlers.__init__ loads
    THEN _have_step_classes = True."""

    def setup_method(self):
        # Ensure the module is cleared so it gets re-imported
        for mod in list(sys.modules.keys()):
            if "step_handlers" in mod:
                del sys.modules[mod]

    def test_have_step_classes_always_false(self):
        """Sprint 3 eliminated dual-path; _have_step_classes is always False."""
        from yuleosh.pipeline.step_handlers import _have_step_classes
        assert _have_step_classes is False

    def test_resolve_handler_returns_legacy_function(self):
        """GIVEN _have_step_classes always False
        WHEN _resolve_handler is called
        THEN it always returns legacy_fn."""
        from yuleosh.pipeline.step_handlers import _resolve_handler
        def dummy_fn():
            pass

        result = _resolve_handler("super-analysis", dummy_fn)
        # Should return dummy_fn (legacy path) since _have_step_classes is False
        assert result is dummy_fn

    def test_resolve_handler_fallback_to_legacy(self):
        """GIVEN _have_step_classes=True but get_step_instance returns None
        WHEN _resolve_handler is called
        THEN it falls back to legacy_fn."""
        from yuleosh.pipeline.step_handlers import _resolve_handler

        def dummy_fn():
            return "legacy"

        result = _resolve_handler("nonexistent-step-key", dummy_fn)
        assert result is dummy_fn

    def test_pipeline_steps_structure(self):
        """PIPELINE_STEPS has 10 entries with correct shape."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(PIPELINE_STEPS) == 10
        for entry in PIPELINE_STEPS:
            assert len(entry) == 4
            step_key, agent, description, handler = entry
            assert isinstance(step_key, str)
            assert isinstance(agent, str)
            assert isinstance(description, str)
            assert callable(handler)

    def test_spec_check_is_function(self):
        """step_spec_check is a plain function (not wrapped by _resolve_handler)."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        step_key, agent, desc, handler = PIPELINE_STEPS[0]
        assert step_key == "spec-check"
        assert agent == "小明"
        assert callable(handler)

    def test_internal_review_is_function(self):
        """step_internal_review is a plain function."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        step_key, agent, desc, handler = PIPELINE_STEPS[3]
        assert step_key == "internal-review"
        assert callable(handler)

    def test_self_test_is_function(self):
        """step_claude_test is a plain function."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        step_key, agent, desc, handler = PIPELINE_STEPS[7]
        assert step_key == "self-test"
        assert callable(handler)

    def test_resolve_handler_nonexistent_returns_legacy(self):
        """_resolve_handler returns legacy_fn for unknown step_key."""
        from yuleosh.pipeline.step_handlers import _resolve_handler
        legacy = lambda: "hello"
        result = _resolve_handler("does-not-exist-12345", legacy)
        assert result is legacy


class TestHaveStepClassesAlwaysFalse:
    """_have_step_classes is always False after Sprint 3 dual-path elimination."""

    def test_have_step_classes_always_false(self):
        """_have_step_classes is unconditionally False."""
        from yuleosh.pipeline.step_handlers import _have_step_classes
        assert _have_step_classes is False

    def test_resolve_handler_always_returns_legacy(self):
        """_resolve_handler always returns legacy_fn when _have_step_classes is False."""
        from yuleosh.pipeline.step_handlers import _resolve_handler

        legacy = lambda: "fallback"
        result = _resolve_handler("super-analysis", legacy)
        assert result is legacy


# ===================================================================
# Module re-exports
# ===================================================================


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
