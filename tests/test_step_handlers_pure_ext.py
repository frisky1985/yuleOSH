# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for pure utility functions in pipeline/step_handlers/ — no LLM, no subprocess.

Covers:
  - test_c_unit.py:  _parse_unity_counts, _parse_ceedling_counts
  - test_integration.py:  _parse_test_counts
  - review_arch.py:  _build_arch_review_prompt
  - review_code.py:  _build_code_review_prompt
"""

import pytest

from yuleosh.pipeline.step_handlers.test_c_unit import (
    _parse_unity_counts,
    _parse_ceedling_counts,
)
from yuleosh.pipeline.step_handlers.test_integration import (
    _parse_test_counts,
)
from yuleosh.pipeline.step_handlers.review_arch import (
    _build_arch_review_prompt,
)
from yuleosh.pipeline.step_handlers.review_code import (
    _build_code_review_prompt,
)


# ══════════════════════════════════════════════════════════════════════════
# test_c_unit.py: _parse_unity_counts
# ══════════════════════════════════════════════════════════════════════════

class TestParseUnityCounts:
    def test_empty_output(self):
        assert _parse_unity_counts("") == (0, 0)
        assert _parse_unity_counts(None) == (0, 0)

    def test_single_pass(self):
        output = "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
        assert _parse_unity_counts(output) == (1, 0)

    def test_single_fail(self):
        output = "FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n"
        assert _parse_unity_counts(output) == (0, 1)

    def test_mixed_results(self):
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n"
        )
        passed, failed = _parse_unity_counts(output)
        assert passed == 2
        assert failed == 1

    def test_summary_line_only(self):
        """Should parse summary line when no per-test lines."""
        output = "3 Tests 1 Failures 0 Ignored"
        assert _parse_unity_counts(output) == (2, 1)

    def test_summary_with_per_test(self):
        """Per-test lines take priority over summary."""
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "2 Tests 0 Failures\n"
        )
        passed, failed = _parse_unity_counts(output)
        assert passed == 1
        assert failed == 0

    def test_no_matches(self):
        output = "random text\nwith no matches\n"
        assert _parse_unity_counts(output) == (0, 0)

    def test_all_ok(self):
        output = (
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
            "OK (1 test, 1 assertion, 0 failed, 0 ignored)\n"
        )
        assert _parse_unity_counts(output) == (3, 0)

    def test_all_fail(self):
        output = (
            "FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n"
            "FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n"
        )
        assert _parse_unity_counts(output) == (0, 2)


# ══════════════════════════════════════════════════════════════════════════
# test_c_unit.py: _parse_ceedling_counts
# ══════════════════════════════════════════════════════════════════════════

class TestParseCeedlingCounts:
    def test_empty_output(self):
        assert _parse_ceedling_counts("") == (0, 0)
        assert _parse_ceedling_counts(None) == (0, 0)

    def test_all_pass(self):
        output = (
            "--------------------\n"
            "TEST OUTPUT SUMMARY\n"
            "--------------------\n"
            "Passed: 5\n"
            "Failed: 0\n"
        )
        assert _parse_ceedling_counts(output) == (5, 0)

    def test_some_failed(self):
        output = (
            "Passed: 3\n"
            "Failed: 2\n"
        )
        assert _parse_ceedling_counts(output) == (3, 2)

    def test_no_summary_fallback_to_fail_keywords(self):
        """Fallback to FAILED/PASSED keywords when summary is missing."""
        output = (
            "  PASSED\n"
            "  PASSED\n"
            "  FAILED\n"
        )
        assert _parse_ceedling_counts(output) == (2, 1)

    def test_no_matches(self):
        assert _parse_ceedling_counts("random output") == (0, 0)

    def test_mixed(self):
        output = (
            "Passed: 10\n"
            "Failed: 3\n"
            "  PASSED\n"
            "  FAILED\n"
        )
        # Summary takes priority (10, 3)
        passed, failed = _parse_ceedling_counts(output)
        assert passed == 10
        assert failed == 3


# ══════════════════════════════════════════════════════════════════════════
# test_integration.py: _parse_test_counts
# ══════════════════════════════════════════════════════════════════════════

class TestParseTestCounts:
    def test_empty_output(self):
        assert _parse_test_counts("", "pytest") == (0, 0)
        assert _parse_test_counts(None, "pytest") == (0, 0)

    def test_pytest_all_pass(self):
        output = "3 passed, 0 failed, 1 skipped in 0.5s"
        assert _parse_test_counts(output, "pytest") == (3, 0)

    def test_pytest_some_failed(self):
        output = "5 passed, 2 failed, 3 skipped in 1.2s"
        assert _parse_test_counts(output, "pytest") == (5, 2)

    def test_pytest_no_skipped(self):
        output = "1 passed, 0 failed in 0.1s"
        assert _parse_test_counts(output, "pytest") == (1, 0)

    def test_pytest_all_failed(self):
        output = "0 passed, 4 failed in 0.3s"
        assert _parse_test_counts(output, "pytest") == (0, 4)

    def test_go_all_pass(self):
        output = "ok  github.com/example/pkg1\nok  github.com/example/pkg2"
        assert _parse_test_counts(output, "go") == (2, 0)

    def test_go_some_failed(self):
        output = (
            "ok  github.com/example/pkg1\n"
            "FAIL github.com/example/pkg2\n"
            "FAIL github.com/example/pkg3\n"
        )
        assert _parse_test_counts(output, "go") == (1, 2)

    def test_go_all_failed(self):
        output = "FAIL github.com/example/pkg1\nFAIL github.com/example/pkg2"
        assert _parse_test_counts(output, "go") == (0, 2)

    def test_unknown_runner(self):
        """Unknown runner returns (0, 0)."""
        assert _parse_test_counts("some output", "unknown-runner") == (0, 0)

    def test_no_run_matches(self):
        output = "random text without test results"
        assert _parse_test_counts(output, "pytest") == (0, 0)


# ══════════════════════════════════════════════════════════════════════════
# review_arch.py: _build_arch_review_prompt
# ══════════════════════════════════════════════════════════════════════════

class TestBuildArchReviewPrompt:
    def test_returns_tuple_of_two_strings(self):
        result = _build_arch_review_prompt(
            spec_content="# Spec\nModule X does Y.",
            spec_name="test-spec.md",
            architecture_content="# Architecture\nModule X has Z.",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        system_prompt, user_prompt = result
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)

    def test_system_prompt_contains_key_elements(self):
        system_prompt, _ = _build_arch_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
        )
        assert "architect" in system_prompt.lower()
        assert "functional requirements" in system_prompt
        assert "non-functional" in system_prompt
        assert "PASS/FAIL/RETRY" in system_prompt

    def test_user_prompt_contains_spec_and_arch(self):
        _, user_prompt = _build_arch_review_prompt(
            spec_content="SPEC_CONTENT_HERE",
            spec_name="my-spec.md",
            architecture_content="ARCH_CONTENT_HERE",
        )
        assert "my-spec.md" in user_prompt
        assert "SPEC_CONTENT_HERE" in user_prompt
        assert "ARCH_CONTENT_HERE" in user_prompt

    def test_large_content_is_truncated(self):
        """Spec and arch content should be truncated to 8000 chars."""
        big_content = "x" * 20000
        _, user_prompt = _build_arch_review_prompt(
            spec_content=big_content,
            spec_name="big-spec.md",
            architecture_content=big_content,
        )
        # The truncation is at 8000 inside the ``` block
        assert "x" * 8000 in user_prompt


# ══════════════════════════════════════════════════════════════════════════
# review_code.py: _build_code_review_prompt
# ══════════════════════════════════════════════════════════════════════════

class TestBuildCodeReviewPrompt:
    def test_returns_tuple_of_two_strings(self):
        result = _build_code_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
            dev_plan_content="dev plan",
            source_files=[],
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        system_prompt, user_prompt = result
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)

    def test_system_prompt_contains_key_elements(self):
        system_prompt, _ = _build_code_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
            dev_plan_content="plan",
            source_files=[],
        )
        assert "senior developer" in system_prompt.lower()
        assert "Architecture consistency" in system_prompt
        assert "Error handling" in system_prompt
        assert "Dead code" in system_prompt
        assert "Test blind spots" in system_prompt

    def test_user_prompt_with_source_files(self):
        """Source file list should be included in user prompt."""
        source_files = [
            {"path": "src/main.py", "lines": 50, "content": "print('hello')"},
            {"path": "src/utils.py", "lines": 30, "content": "def util(): pass"},
        ]
        _, user_prompt = _build_code_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
            dev_plan_content="plan",
            source_files=source_files,
        )
        assert "src/main.py" in user_prompt
        assert "src/utils.py" in user_prompt
        assert "(50 lines)" in user_prompt
        assert "(30 lines)" in user_prompt

    def test_no_source_files(self):
        _, user_prompt = _build_code_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
            dev_plan_content="plan",
            source_files=[],
        )
        assert "Source Files (0 total)" in user_prompt

    def test_dev_plan_in_user_prompt(self):
        _, user_prompt = _build_code_review_prompt(
            spec_content="spec",
            spec_name="s.md",
            architecture_content="arch",
            dev_plan_content="My Development Plan Here",
            source_files=[],
        )
        assert "My Development Plan Here" in user_prompt
