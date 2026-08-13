# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Unit tests for PRD section-coverage guard in step_hermes_prd (2026-08-13).

Covers:
  - _check_prd_section_coverage: spec section (SR-XXX/SW-XXX) extraction
    and missing detection against PRD content
  - _prd_retry_prompt: retry prompt carries the missing section list
  - step_hermes_prd retry flow: missing sections → bounded retry (≤2),
    exhausted → best-effort PRD + prd-coverage-gap.json sidecar
"""

import json
from unittest import mock

import pytest

from yuleosh.pipeline.step_handlers.analysis import (
    _check_prd_section_coverage,
    _prd_retry_prompt,
    step_hermes_prd,
)

SPEC_WITH_SECTIONS = (
    "### SR-001: 硬件抽象\n"
    "- The system SHALL provide a HAL abstraction layer\n"
    "### SW-004: 防夹检测\n"
    "- The system SHALL detect pinch\n"
    "### Scenario: 手动下降\n"
    "- GIVEN ...\n"
)

PRD_COVERS_ALL = (
    "### 4.1 硬件抽象层 (SR-001)\n"
    "| FR-001 | 提供 HAL 抽象层 | P0 |\n"
    "### 4.7 防夹检测 (SW-004)\n"
    "| FR-020 | 检测防夹 | P0 |\n"
)

PRD_MISSING_ONE = (
    "### 4.1 硬件抽象层 (SR-001)\n"
    "| FR-001 | 提供 HAL 抽象层 | P0 |\n"
    # SW-004 missing entirely
)


# ===================================================================
# _check_prd_section_coverage
# ===================================================================

class TestCheckPrdSectionCoverage:
    def test_all_covered_returns_empty(self):
        assert _check_prd_section_coverage(SPEC_WITH_SECTIONS, PRD_COVERS_ALL) == []

    def test_missing_section_detected(self):
        missing = _check_prd_section_coverage(SPEC_WITH_SECTIONS, PRD_MISSING_ONE)
        assert missing == ["SW-004"]

    def test_empty_prd_returns_empty(self):
        # Guard against crashes; caller treats [] as "nothing missing"
        assert _check_prd_section_coverage(SPEC_WITH_SECTIONS, "") == []

    def test_empty_spec_returns_empty(self):
        assert _check_prd_section_coverage("", PRD_COVERS_ALL) == []

    def test_scenario_heading_not_requirement_section(self):
        # `### Scenario:` must not be counted as a requirement section
        spec = "### Scenario: 手动下降\n- GIVEN ...\n"
        assert _check_prd_section_coverage(spec, "anything") == []

    def test_case_insensitive_coverage(self):
        prd = "### 4.1 硬件抽象层 (sr-001)\n"
        assert _check_prd_section_coverage(SPEC_WITH_SECTIONS, prd) == ["SW-004"]


# ===================================================================
# _prd_retry_prompt
# ===================================================================

class TestPrdRetryPrompt:
    def test_carries_missing_sections(self):
        prompt = _prd_retry_prompt("base prompt", ["SW-004", "SW-008"])
        assert "SW-004" in prompt
        assert "SW-008" in prompt
        assert "base prompt" in prompt
        assert "Coverage feedback" in prompt

    def test_empty_missing_list_still_valid(self):
        prompt = _prd_retry_prompt("base", [])
        assert "base" in prompt


# ===================================================================
# step_hermes_prd retry flow
# ===================================================================

def _mk_session(tmp_path, spec_text: str):
    from yuleosh.pipeline.session import PipelineSession

    spec_file = tmp_path / "spec.md"
    spec_file.write_text(spec_text)
    return PipelineSession("test-prd-guard", str(spec_file))


def _llm_result(content: str):
    return {
        "content": content,
        "model": "mock",
        "usage": {"total_tokens": 50, "prompt_tokens": 30, "completion_tokens": 20},
    }


class TestStepHermesPrdRetry:
    def test_success_no_retry_when_covered(self, tmp_path):
        """PRD covers all sections → single LLM call, no gap report."""
        session = _mk_session(tmp_path, SPEC_WITH_SECTIONS)
        with mock.patch("yuleosh.pipeline.step_handlers.analysis._parse_spec") as mock_parse:
            mock_parse.return_value = {"requirements": [], "scenarios": []}
            with mock.patch("yuleosh.pipeline.step_handlers.analysis._call_llm") as mock_llm:
                mock_llm.return_value = _llm_result(PRD_COVERS_ALL)
                result = step_hermes_prd(session)
        assert result is not None
        assert mock_llm.call_count == 1
        assert not (session.session_dir / "prd-coverage-gap.json").exists()
        assert (session.session_dir / "prd.md").exists()

    def test_retry_until_covered(self, tmp_path):
        """First PRD missing SW-004, retry covers it → 2 LLM calls, no gap."""
        session = _mk_session(tmp_path, SPEC_WITH_SECTIONS)
        calls = {"n": 0}

        def _side_effect(session_, system, user, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _llm_result(PRD_MISSING_ONE)
            return _llm_result(PRD_COVERS_ALL)

        with mock.patch("yuleosh.pipeline.step_handlers.analysis._parse_spec") as mock_parse:
            mock_parse.return_value = {"requirements": [], "scenarios": []}
            with mock.patch("yuleosh.pipeline.step_handlers.analysis._call_llm") as mock_llm:
                mock_llm.side_effect = _side_effect
                result = step_hermes_prd(session)
        assert result is not None
        assert mock_llm.call_count == 2
        assert not (session.session_dir / "prd-coverage-gap.json").exists()

    def test_retry_exhausted_writes_gap_report(self, tmp_path):
        """PRD keeps missing SW-004 after 2 retries → best-effort write + gap report."""
        session = _mk_session(tmp_path, SPEC_WITH_SECTIONS)
        with mock.patch("yuleosh.pipeline.step_handlers.analysis._parse_spec") as mock_parse:
            mock_parse.return_value = {"requirements": [], "scenarios": []}
            with mock.patch("yuleosh.pipeline.step_handlers.analysis._call_llm") as mock_llm:
                mock_llm.return_value = _llm_result(PRD_MISSING_ONE)
                result = step_hermes_prd(session)
        assert result is not None
        # 1 original + 2 retries = 3 calls max
        assert mock_llm.call_count == 3
        gap_path = session.session_dir / "prd-coverage-gap.json"
        assert gap_path.exists()
        data = json.loads(gap_path.read_text())
        assert data["status"] == "partial"
        assert data["missing_spec_sections"] == ["SW-004"]
        assert (session.session_dir / "prd.md").exists()  # best effort still written

    def test_llm_failure_raises(self, tmp_path):
        """LLM failure still raises PipelineStepError (no silent pass)."""
        session = _mk_session(tmp_path, SPEC_WITH_SECTIONS)
        with mock.patch("yuleosh.pipeline.step_handlers.analysis._parse_spec") as mock_parse:
            mock_parse.return_value = {"requirements": [], "scenarios": []}
            with mock.patch("yuleosh.pipeline.step_handlers.analysis._call_llm") as mock_llm:
                mock_llm.side_effect = Exception("LLM API unavailable")
                from yuleosh.pipeline.session import PipelineStepError
                with pytest.raises(PipelineStepError):
                    step_hermes_prd(session)
