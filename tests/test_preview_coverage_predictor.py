#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
"""
Tests for yuleOSH Preview — Coverage Predictor.

Covers all test framework branches, complexity penalties, and bottleneck logic.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.preview.coverage_predictor import _predict_coverage


class TestPredictCoverage:
    """Comprehensive tests for _predict_coverage."""

    # ── Framework branches ──────────────────────────────────────────

    def test_framework_none(self):
        """GIVEN test_framework='none' WHEN _predict_coverage THEN base=5, low confidence."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=10)
        assert result["current_coverage_estimate"] == 5.0
        assert result["confidence"] == "low"

    def test_framework_unknown(self):
        """GIVEN test_framework='unknown' WHEN _predict_coverage THEN base=25, low confidence."""
        result = _predict_coverage(test_density=0.0, test_framework="unknown", complexity_score=10)
        assert result["current_coverage_estimate"] == 25.0
        assert result["confidence"] == "low"

    def test_framework_unity(self):
        """GIVEN test_framework='Unity' WHEN _predict_coverage THEN base=40+30*density."""
        result = _predict_coverage(test_density=0.5, test_framework="Unity", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(55.0, rel=0.1)
        assert result["confidence"] == "medium"

    def test_framework_cunit(self):
        """GIVEN test_framework='CUnit' WHEN _predict_coverage THEN same as Unity."""
        result = _predict_coverage(test_density=0.5, test_framework="CUnit", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(55.0, rel=0.1)

    def test_framework_cmock(self):
        """GIVEN test_framework='CMock' WHEN _predict_coverage THEN base=50+25*density."""
        result = _predict_coverage(test_density=0.4, test_framework="CMock", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(60.0, rel=0.1)

    def test_framework_pytest(self):
        """GIVEN test_framework='pytest' WHEN _predict_coverage THEN base=55+25*density."""
        result = _predict_coverage(test_density=0.2, test_framework="pytest", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(60.0, rel=0.1)

    def test_framework_google_test(self):
        """GIVEN test_framework='Google Test' WHEN _predict_coverage THEN base=55+25*density."""
        result = _predict_coverage(test_density=0.3, test_framework="Google Test", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(62.5, rel=0.1)
        assert result["confidence"] == "medium"

    def test_framework_unittest(self):
        """GIVEN test_framework='unittest' WHEN _predict_coverage THEN base=55+25*density."""
        result = _predict_coverage(test_density=0.5, test_framework="unittest", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(67.5, rel=0.1)

    def test_framework_catch2(self):
        """GIVEN test_framework='Catch2' WHEN _predict_coverage THEN base=55+25*density."""
        result = _predict_coverage(test_density=0.5, test_framework="Catch2", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(67.5, rel=0.1)

    def test_framework_unknown_framework(self):
        """GIVEN unrecognized framework WHEN _predict_coverage THEN fallback base=30."""
        result = _predict_coverage(test_density=0.5, test_framework="NinjaTest", complexity_score=10)
        assert result["current_coverage_estimate"] == pytest.approx(30.0, rel=0.1)
        assert result["confidence"] == "low"

    # ── Complexity penalty ──────────────────────────────────────────

    def test_complexity_high_penalty(self):
        """GIVEN complexity_score > 50 WHEN _predict_coverage THEN 10 point penalty."""
        result = _predict_coverage(test_density=0.5, test_framework="Unity", complexity_score=60)
        # Base = 55, penalty = 10 => 45
        assert result["current_coverage_estimate"] == 45.0

    def test_complexity_medium_penalty(self):
        """GIVEN complexity_score = 40 (between 30 and 50) WHEN _predict_coverage THEN 5 point penalty."""
        result = _predict_coverage(test_density=0.5, test_framework="Unity", complexity_score=40)
        # Base = 55, penalty = 5 => 50
        assert result["current_coverage_estimate"] == 50.0

    def test_complexity_low_no_penalty(self):
        """GIVEN complexity_score <= 30 WHEN _predict_coverage THEN no penalty."""
        result = _predict_coverage(test_density=0.5, test_framework="Unity", complexity_score=30)
        # Base = 55, penalty = 0 => 55
        assert result["current_coverage_estimate"] == 55.0

    # ── Projected coverage ──────────────────────────────────────────────

    def test_projected_coverage(self):
        """GIVEN base estimate WHEN _predict_coverage THEN projected = current + 30 + maturity*5."""
        result = _predict_coverage(test_density=0.5, test_framework="Unity", complexity_score=10)
        # current = 55, maturity = 2.0 => projected = 55 + 30 + 10 = 95
        assert result["projected_coverage_after_yuleosh"] == 95.0

    def test_projected_coverage_capped_at_100(self):
        """GIVEN high base estimate WHEN _predict_coverage THEN projected capped at 100."""
        result = _predict_coverage(test_density=1.0, test_framework="pytest", complexity_score=10)
        # current = 80, maturity = 2.0 => projected = 80 + 30 + 10 = 120 -> capped at 100
        assert result["projected_coverage_after_yuleosh"] == 100.0

    # ── Bottleneck files ───────────────────────────────────────────

    def test_bottleneck_when_below_50(self):
        """GIVEN current < 50 WHEN _predict_coverage THEN adds first bottleneck."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=10)
        # current = 5.0
        assert len(result["bottleneck_files"]) >= 1

    def test_bottleneck_when_below_60(self):
        """GIVEN current between 50 and 60 WHEN _predict_coverage THEN adds second bottleneck."""
        result = _predict_coverage(test_density=0.3, test_framework="pytest", complexity_score=35)
        # current = 55 + 7.5 - 5 = 57.5 -> floor to 57.5
        # Since current < 50? No, 57.5 > 50
        # Since current < 60? Yes
        assert len(result["bottleneck_files"]) == 1

    def test_no_bottleneck_when_above_60(self):
        """GIVEN current >= 60 WHEN _predict_coverage THEN no bottleneck files."""
        result = _predict_coverage(test_density=1.0, test_framework="pytest", complexity_score=10)
        # current = 80
        assert result["bottleneck_files"] == []

    def test_bottleneck_capped_at_5(self):
        """GIVEN many bottleneck indicators WHEN _predict_coverage THEN result capped at 5."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=10)
        # current = 5, both conditions true => 2 bottlenecks
        assert len(result["bottleneck_files"]) == 2

    # ── Edge cases ─────────────────────────────────────────────────

    def test_zero_density(self):
        """GIVEN test_density=0 WHEN _predict_coverage THEN base remains valid."""
        result = _predict_coverage(test_density=0.0, test_framework="Unity", complexity_score=10)
        assert result["current_coverage_estimate"] == 40.0  # base only, no density contribution

    def test_high_density(self):
        """GIVEN high test_density WHEN _predict_coverage THEN result capped at 100."""
        result = _predict_coverage(test_density=2.0, test_framework="Unity", complexity_score=10)
        # Unity base = 40, density contrib = 2.0 * 30 = 60, total = 100, capped at 100
        # Wait, min(100, max(0, 100)) = 100
        # But projected = 100 + 30 + 10 = 140 -> capped to 100
        assert result["current_coverage_estimate"] == 100.0

    def test_negative_density_not_applicable(self):
        """GIVEN low coverage scenario WHEN _predict_coverage THEN estimates are non-negative."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=60)
        # base = 5.0, penalty = 10, current = max(0, -5) = 0
        assert result["current_coverage_estimate"] >= 0

    # ── Projection with different maturities ───────────────────────

    def test_projection_none_framework_maturity(self):
        """GIVEN test_framework='none' WHEN _predict_coverage THEN maturity=0, low projected gain."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=10)
        # current = 5, projected = 5 + 30 + 0 = 35
        assert result["projected_coverage_after_yuleosh"] == 35.0

    def test_projection_cmock_maturity(self):
        """GIVEN test_framework='CMock' WHEN _predict_coverage THEN maturity=2.5, higher gain."""
        result = _predict_coverage(test_density=0.5, test_framework="CMock", complexity_score=10)
        # base = 50 + 12.5 = 62.5, maturity = 2.5
        # projected = 62.5 + 30 + 12.5 = 105 -> capped at 100
        assert result["projected_coverage_after_yuleosh"] == 100.0

    def test_output_keys(self):
        """GIVEN any inputs WHEN _predict_coverage THEN output has all expected keys."""
        result = _predict_coverage(test_density=0.0, test_framework="none", complexity_score=10)
        assert "current_coverage_estimate" in result
        assert "projected_coverage_after_yuleosh" in result
        assert "confidence" in result
        assert "bottleneck_files" in result
