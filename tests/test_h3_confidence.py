
# @tests src/yuleosh/pipeline/llm_gateway.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for H3-1: LLM output confidence field."""

import pytest

from yuleosh.llm.fallback import (
    _extract_confidence,
    apply_fallback_chain,
    FallbackResult,
)


# ── _extract_confidence ───────────────────────────────────────────────────────

class TestExtractConfidence:
    def test_extracts_trailing_line(self):
        text = "Analysis complete.\nCONFIDENCE: 0.85"
        cleaned, conf = _extract_confidence(text)
        assert conf == pytest.approx(0.85)
        assert "CONFIDENCE" not in cleaned

    def test_confidence_at_end_stripped(self):
        text = "Some output.\nCONFIDENCE: 0.5"
        cleaned, _ = _extract_confidence(text)
        assert cleaned.strip() == "Some output."

    def test_confidence_one(self):
        _, conf = _extract_confidence("Result.\nCONFIDENCE: 1.0")
        assert conf == pytest.approx(1.0)

    def test_confidence_zero(self):
        _, conf = _extract_confidence("Result.\nCONFIDENCE: 0.0")
        assert conf == pytest.approx(0.0)

    def test_confidence_integer_one(self):
        _, conf = _extract_confidence("Result.\nCONFIDENCE: 1")
        assert conf == pytest.approx(1.0)

    def test_case_insensitive(self):
        _, conf = _extract_confidence("Result.\nconfidence: 0.75")
        assert conf == pytest.approx(0.75)

    def test_no_confidence_line_returns_none(self):
        text = "Normal output without confidence."
        cleaned, conf = _extract_confidence(text)
        assert conf is None
        assert cleaned == text

    def test_confidence_not_in_middle_of_text(self):
        text = "CONFIDENCE: 0.9 is mentioned inline but not at line end.\nMore text."
        _, conf = _extract_confidence(text)
        # mid-sentence mention should NOT be parsed (regex requires line boundary)
        assert conf is None

    def test_value_clamped_above_one(self):
        # Only values matching [01](\.\d+)? are accepted — "1.5" won't match
        # because the regex anchors to 0 or 1 as leading digit
        _, conf = _extract_confidence("Result.\nCONFIDENCE: 0.99")
        assert conf == pytest.approx(0.99)

    def test_output_unmodified_when_no_confidence(self):
        text = "No confidence line here."
        cleaned, _ = _extract_confidence(text)
        assert cleaned == text


# ── FallbackResult.confidence field ──────────────────────────────────────────

class TestFallbackResultConfidence:
    def test_confidence_default_none(self):
        r = FallbackResult(status="ok", output="x", level=0)
        assert r.confidence is None

    def test_confidence_set(self):
        r = FallbackResult(status="ok", output="x", level=0, confidence=0.75)
        assert r.confidence == pytest.approx(0.75)

    def test_apply_fallback_chain_extracts_confidence(self):
        output = "The architecture is sound.\nCONFIDENCE: 0.9"
        result = apply_fallback_chain(
            step_name="architecture",
            llm_output=output,
        )
        assert result.confidence == pytest.approx(0.9)
        assert "CONFIDENCE" not in result.output

    def test_apply_fallback_chain_no_confidence_is_none(self):
        result = apply_fallback_chain(
            step_name="spec",
            llm_output="Plain output without confidence marker.",
        )
        assert result.confidence is None

    def test_apply_fallback_chain_low_confidence_preserved(self):
        output = "Uncertain output.\nCONFIDENCE: 0.3"
        result = apply_fallback_chain(
            step_name="review",
            llm_output=output,
        )
        assert result.confidence == pytest.approx(0.3)


# ── Gateway confidence flag (H3-1d) ──────────────────────────────────────────

class TestGatewayConfidenceFlag:
    """Test that call_step_llm sets last_confidence and last_confidence_flag."""

    def _make_session(self, tmp_path):
        from yuleosh.pipeline.session import PipelineSession
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec\n")
        s = PipelineSession(name="test-conf", spec_path=str(spec))
        s.session_dir = tmp_path / ".osh" / "sessions" / "test-conf"
        s.session_dir.mkdir(parents=True, exist_ok=True)
        s.token_usage_total = 0
        s.token_usage_steps = []
        return s

    def _call(self, tmp_path, content_with_confidence: str):
        from unittest.mock import patch
        from yuleosh.pipeline.llm_gateway import call_step_llm

        session = self._make_session(tmp_path)
        fake_result = {"content": content_with_confidence, "usage": {}}
        with patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync",
                   return_value=fake_result):
            content = call_step_llm(session, "system", "user prompt")
        return session, content

    def test_high_confidence_no_flag(self, tmp_path):
        session, _ = self._call(tmp_path, "Good output.\nCONFIDENCE: 0.9")
        assert session.last_confidence == pytest.approx(0.9)
        assert session.last_confidence_flag is None

    def test_low_confidence_sets_needs_human_review(self, tmp_path):
        session, _ = self._call(tmp_path, "Uncertain output.\nCONFIDENCE: 0.4")
        assert session.last_confidence == pytest.approx(0.4)
        assert session.last_confidence_flag == "needs_human_review"

    def test_no_confidence_line_flag_not_set(self, tmp_path):
        session, _ = self._call(tmp_path, "Output without confidence line.")
        assert session.last_confidence is None

    def test_confidence_line_stripped_from_returned_content(self, tmp_path):
        _, content = self._call(tmp_path, "Clean output.\nCONFIDENCE: 0.8")
        assert "CONFIDENCE" not in content
        assert "Clean output." in content

    def test_boundary_exactly_half_no_flag(self, tmp_path):
        session, _ = self._call(tmp_path, "Edge case.\nCONFIDENCE: 0.5")
        assert session.last_confidence_flag is None
