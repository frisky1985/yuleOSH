# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for pipeline/step_handlers/review_misra_ci.py — coverage target ≥50%."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Mini PipelineSession backed by a temp dir."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    from yuleosh.pipeline.session import PipelineSession
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\n")
    session = PipelineSession("test-misra", str(spec_file))
    session.session_dir = tmp_path / "sessions" / "test-misra"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


# ===================================================================
# _read_misra_report
# ===================================================================


class TestReadMisraReport:
    def test_no_report(self, tmp_path):
        """GIVEN no MISRA report WHEN reading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_report
        result = _read_misra_report(tmp_path)
        assert result is None

    def test_valid_report(self, tmp_path):
        """GIVEN valid MISRA report WHEN reading THEN returns parsed data."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_report
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report = {"summary": {"total_violations": 10}, "groups": {}}
        (report_dir / "misra-report.json").write_text(json.dumps(report))
        result = _read_misra_report(tmp_path)
        assert result["summary"]["total_violations"] == 10

    def test_corrupted_report(self, tmp_path, caplog):
        """GIVEN corrupted report WHEN reading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_report
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "misra-report.json").write_text("not json")
        result = _read_misra_report(tmp_path)
        assert result is None


# ===================================================================
# _read_misra_trend
# ===================================================================


class TestReadMisraTrend:
    def test_no_trend_file(self, tmp_path):
        """GIVEN no trend file WHEN reading trend THEN returns empty."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_trend
        result = _read_misra_trend(tmp_path)
        assert result == []

    def test_with_entries(self, tmp_path):
        """GIVEN trend file with entries WHEN reading THEN returns recent first."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_trend
        trend = tmp_path / ".yuleosh" / "reports" / "misra-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {"ts": "2025-01-01", "total_violations": 10},
            {"ts": "2025-01-02", "total_violations": 5},
        ]
        lines = "\n".join(json.dumps(e) for e in entries) + "\n"
        trend.write_text(lines)
        result = _read_misra_trend(tmp_path)
        assert len(result) == 2
        assert result[0]["total_violations"] == 5  # most recent first

    def test_limited_to_max(self, tmp_path):
        """GIVEN more entries than max WHEN reading THEN limits."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _read_misra_trend
        trend = tmp_path / ".yuleosh" / "reports" / "misra-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        lines = "\n".join(json.dumps({"ts": f"2025-01-{i+1:02d}"}) for i in range(25)) + "\n"
        trend.write_text(lines)
        result = _read_misra_trend(tmp_path, max_entries=10)
        assert len(result) == 10


# ===================================================================
# _compute_trend
# ===================================================================


class TestComputeTrend:
    def test_first_run(self):
        """GIVEN no previous report WHEN computing trend THEN direction is first_run."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _compute_trend
        current = {"summary": {"total_violations": 10}}
        result = _compute_trend(current, None)
        assert result["direction"] == "first_run"
        assert result["delta"] == 0

    def test_direction_up(self):
        """GIVEN violations increased WHEN computing trend THEN direction up."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _compute_trend
        current = {"summary": {"total_violations": 15}, "violations_raw": []}
        previous = {"summary": {"total_violations": 10}, "violations_raw": []}
        result = _compute_trend(current, previous)
        assert result["direction"] == "up"
        assert result["delta"] == 5

    def test_direction_down(self):
        """GIVEN violations decreased WHEN computing trend THEN direction down."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _compute_trend
        current = {"summary": {"total_violations": 5}, "violations_raw": []}
        previous = {"summary": {"total_violations": 10}, "violations_raw": []}
        result = _compute_trend(current, previous)
        assert result["direction"] == "down"
        assert result["delta"] == -5

    def test_direction_same(self):
        """GIVEN violations unchanged WHEN computing trend THEN direction same."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _compute_trend
        current = {"summary": {"total_violations": 10}, "violations_raw": []}
        previous = {"summary": {"total_violations": 10}, "violations_raw": []}
        result = _compute_trend(current, previous)
        assert result["direction"] == "same"


# ===================================================================
# _classify_violations
# ===================================================================


class TestClassifyViolations:
    def test_empty_groups(self):
        """GIVEN no groups WHEN classifying THEN returns empty."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _classify_violations
        result = _classify_violations({"groups": {}})
        assert result == []

    def test_classifies_priority(self):
        """GIVEN groups with various severities WHEN classifying THEN assigns priority."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _classify_violations
        report = {
            "groups": {
                "R1": {"severity_category": "required", "count": 3, "title": "Rule 1", "files": []},
                "A1": {"severity_category": "advisory", "count": 2, "title": "Adv 1", "files": []},
            }
        }
        result = _classify_violations(report)
        assert len(result) == 2
        r1 = [c for c in result if c["rule_id"] == "R1"][0]
        assert r1["priority"] == 1
        assert r1["needs_deviation"] is True
        a1 = [c for c in result if c["rule_id"] == "A1"][0]
        assert a1["priority"] == 2

    def test_sorted_by_priority(self):
        """GIVEN multiple groups WHEN classifying THEN sorted by priority then count desc."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _classify_violations
        report = {
            "groups": {
                "R1": {"severity_category": "advisory", "count": 1, "title": "", "files": []},
                "R2": {"severity_category": "required", "count": 5, "title": "", "files": []},
            }
        }
        result = _classify_violations(report)
        assert result[0]["rule_id"] == "R2"  # priority 1 comes first


# ===================================================================
# _generate_fix_recommendations
# ===================================================================


class TestGenerateFixRecommendations:
    def test_no_violations(self):
        """GIVEN no classified violations WHEN generating recommendations THEN says none."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _generate_fix_recommendations
        result = _generate_fix_recommendations([], {"direction": "same"}, 0)
        assert any("No actionable" in r for r in result)

    def test_p1_recommendation(self):
        """GIVEN P1 violations WHEN generating THEN includes fix recommendation."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _generate_fix_recommendations
        classified = [
            {"rule_id": "R1", "priority": 1, "count": 2, "severity": "required",
             "needs_deviation": True, "title": "Test", "files": []},
        ]
        result = _generate_fix_recommendations(classified, {"direction": "up", "delta": 2}, 2)
        assert any("PRIORITY 1" in r for r in result)
        assert any("increased" in r for r in result)

    def test_deviation_recommendation(self):
        """GIVEN violations needing deviation WHEN generating THEN includes deviation note."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _generate_fix_recommendations
        classified = [
            {"rule_id": "R1", "priority": 1, "count": 2, "severity": "required",
             "needs_deviation": True, "title": "", "files": []},
        ]
        result = _generate_fix_recommendations(classified, {"direction": "same"}, 2)
        assert any("Deviation required" in r for r in result)


# ===================================================================
# _check_for_regression_violations
# ===================================================================


class TestCheckForRegressionViolations:
    def test_insufficient_history(self):
        """GIVEN less than 2 trend entries WHEN checking regression THEN returns empty."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _check_for_regression_violations
        result = _check_for_regression_violations({"summary": {"total_violations": 10}}, [{}])
        assert result == []

    def test_regression_detected(self):
        """GIVEN violations increased WHEN checking regression THEN flags regression."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _check_for_regression_violations
        current = {"summary": {"total_violations": 15}}
        trend = [{"total_violations": 10}, {"total_violations": 15}]
        result = _check_for_regression_violations(current, trend)
        assert len(result) >= 1

    def test_improvement_detected(self):
        """GIVEN violations decreased WHEN checking regression THEN flags improvement."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import _check_for_regression_violations
        current = {"summary": {"total_violations": 5}}
        trend = [{"total_violations": 10}, {"total_violations": 5}]
        result = _check_for_regression_violations(current, trend)
        assert any(f["type"] == "improvement" for f in result)


# ===================================================================
# step_review_misra_ci
# ===================================================================


class TestStepReviewMisraCi:
    def test_no_report(self, tmp_session):
        """GIVEN no MISRA report WHEN step runs THEN returns skipped status."""
        from yuleosh.pipeline.step_handlers.review_misra_ci import step_review_misra_ci
        result = step_review_misra_ci(tmp_session)
        assert result is not None
        review_path = tmp_session.session_dir / "misra-review.json"
        assert review_path.exists()
        data = json.loads(review_path.read_text())
        assert data["status"] == "skipped"

    def test_with_report(self, tmp_session, tmp_path, monkeypatch):
        """GIVEN MISRA report exists WHEN step runs THEN analyzes violations."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_misra_ci import step_review_misra_ci
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "misra-report.json").write_text(json.dumps({
            "summary": {"total_violations": 5, "total_rules_violated": 2, "unique_files": ["a.c"], "severity_counts": {"error": 3}},
            "groups": {
                "R1": {"severity_category": "required", "count": 3, "title": "Rule 1", "files": ["a.c"]},
                "A1": {"severity_category": "advisory", "count": 2, "title": "Adv 1", "files": ["b.c"]},
            },
            "violations_raw": [],
        }))
        result = step_review_misra_ci(tmp_session)
        assert result is not None
        data = json.loads(tmp_session.session_dir.joinpath("misra-review.json").read_text())
        assert "summary" in data
        assert "trend_analysis" in data
        assert "recommendations" in data
        assert data["status"] == "failed"  # required violations present

    def test_output_keys(self, tmp_session, tmp_path, monkeypatch):
        """GIVEN step runs with report WHEN checking output THEN correct structure."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_misra_ci import step_review_misra_ci
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "misra-report.json").write_text(json.dumps({
            "summary": {"total_violations": 0, "severity_counts": {}},
            "groups": {},
            "violations_raw": [],
        }))
        step_review_misra_ci(tmp_session)
        data = json.loads(tmp_session.session_dir.joinpath("misra-review.json").read_text())
        assert data["status"] == "passed"
