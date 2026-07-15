"""Tests for pipeline/step_handlers/review_misra_ci.py."""
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from yuleosh.pipeline.step_handlers.review_misra_ci import (
    _read_misra_report, _read_misra_trend, _compute_trend,
    _classify_violations, _generate_fix_recommendations,
    _check_for_regression_violations, step_review_misra_ci,
    _PRIORITY_MAP,
)


class TestPriorityMap:
    def test_mapping(self):
        assert _PRIORITY_MAP["required"] == 1
        assert _PRIORITY_MAP["advisory"] == 2
        assert _PRIORITY_MAP["unknown"] == 3


class TestReadMisraReport:
    def test_no_report(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_misra_report(Path(td))
            assert result is None

    def test_valid_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / ".yuleosh" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            data = {"summary": {"total_violations": 10}, "groups": {}}
            (report_dir / "misra-report.json").write_text(json.dumps(data))
            result = _read_misra_report(Path(td))
            assert result["summary"]["total_violations"] == 10

    def test_corrupt_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / ".yuleosh" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "misra-report.json").write_text("not-json")
            result = _read_misra_report(Path(td))
            assert result is None


class TestReadMisraTrend:
    def test_no_trend_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_misra_trend(Path(td))
            assert result == []

    def test_with_entries(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "misra-trend.jsonl").write_text(
                json.dumps({"total_violations": 10}) + "\n"
                + json.dumps({"total_violations": 5}) + "\n"
            )
            result = _read_misra_trend(Path(td))
            assert len(result) == 2
            assert result[0]["total_violations"] == 5  # most recent first

    def test_max_entries(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps({"total_violations": i}) + "\n" for i in range(30)]
            (trend_dir / "misra-trend.jsonl").write_text("".join(lines))
            result = _read_misra_trend(Path(td), max_entries=5)
            assert len(result) == 5

    def test_bad_json_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "misra-trend.jsonl").write_text("bad\n" + json.dumps({"ok": 1}) + "\n")
            result = _read_misra_trend(Path(td))
            assert len(result) == 1


class TestComputeTrend:
    def test_first_run(self):
        trend = _compute_trend({"summary": {"total_violations": 5}}, None)
        assert trend["direction"] == "first_run"

    def test_no_change(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 5}, "violations_raw": []},
            {"summary": {"total_violations": 5}, "violations_raw": []}
        )
        assert trend["direction"] == "same"

    def test_increase(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 10}, "violations_raw": [{"severity": "error"}]},
            {"summary": {"total_violations": 5}, "violations_raw": [{"severity": "error"}]}
        )
        assert trend["direction"] == "up"
        assert trend["delta"] == 5

    def test_decrease(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 3}, "violations_raw": []},
            {"summary": {"total_violations": 10}, "violations_raw": [{"severity": "warning"}]}
        )
        assert trend["direction"] == "down"
        assert trend["delta"] == -7


class TestClassifyViolations:
    def test_empty_groups(self):
        classified = _classify_violations({"groups": {}})
        assert classified == []

    def test_required_violation(self):
        report = {"groups": {
            "R1.1": {
                "severity_category": "Required",
                "count": 3,
                "title": "Test rule",
                "files": ["main.c"],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["priority"] == 1
        assert classified[0]["needs_deviation"] is True

    def test_advisory_violation(self):
        report = {"groups": {
            "A1.1": {
                "severity_category": "Advisory",
                "count": 2,
                "title": "Advisory rule",
                "files": [],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["priority"] == 2

    def test_sort_by_priority(self):
        report = {"groups": {
            "R1": {"severity_category": "Required", "count": 1, "title": "R", "files": []},
            "A1": {"severity_category": "Advisory", "count": 5, "title": "A", "files": []},
        }}
        classified = _classify_violations(report)
        assert classified[0]["rule_id"] == "R1"


class TestGenerateFixRecommendations:
    def test_no_p1_p2(self):
        recs = _generate_fix_recommendations([], {"direction": "same"}, 0)
        assert any("No actionable" in r for r in recs)

    def test_with_p1_violations(self):
        classified = [{"priority": 1, "count": 5, "rule_id": "R1.1",
                        "needs_deviation": True}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 5)
        assert any("PRIORITY 1" in r for r in recs)

    def test_with_p2_violations(self):
        classified = [{"priority": 2, "count": 3, "rule_id": "A1.1",
                        "needs_deviation": False}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 3)
        assert any("PRIORITY 2" in r for r in recs)

    def test_increasing_trend_detected(self):
        recs = _generate_fix_recommendations([], {"direction": "up", "delta": 5}, 5)
        assert any("increased" in r for r in recs)

    def test_decreasing_trend_detected(self):
        recs = _generate_fix_recommendations([], {"direction": "down", "delta": -3}, 2)
        assert any("decreased" in r for r in recs)

    def test_deviation_needed(self):
        classified = [{"priority": 1, "count": 2, "rule_id": "R2.1",
                        "needs_deviation": True}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 2)
        assert any("Deviation" in r for r in recs)


class TestCheckForRegressionViolations:
    def test_few_entries(self):
        result = _check_for_regression_violations({"summary": {"total_violations": 5}}, [])
        assert result == []

    def test_one_entry(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 5}},
            [{"total_violations": 3}]
        )
        assert result == []

    def test_regression_found(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 10}},
            [{"total_violations": 10}, {"total_violations": 5}]
        )
        assert len(result) >= 1
        assert result[0]["type"] == "regression"
        assert result[0]["delta"] == 5

    def test_improvement_found(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 3}},
            [{"total_violations": 3}, {"total_violations": 10}]
        )
        assert len(result) >= 1
        assert result[0]["type"] == "improvement"


class TestStepReviewMisraCi:
    def test_no_report_skips(self):
        session = MagicMock()
        session.name = "test"
        session.session_dir = Path("/tmp")
        with patch("yuleosh.pipeline.step_handlers.review_misra_ci.Path") as mock_path:
            mock_path.return_value = Path("/nonexistent")
            result = step_review_misra_ci(session)
            assert result is not None

    def test_skip_no_misra_data(self):
        session = MagicMock()
        session.name = "test"
        session.session_dir = Path("/tmp")
        with patch.dict("os.environ", {}, clear=True):
            result = step_review_misra_ci(session)
            assert result is not None
