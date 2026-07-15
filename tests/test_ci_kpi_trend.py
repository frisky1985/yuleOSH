"""Tests for ci/kpi/trend.py."""
import json
import tempfile
from pathlib import Path

from yuleosh.ci.kpi.trend import _get_misra_trend_avg, _get_coverage_trend_avg


def _write_trend_file(tmpdir, filename, entries):
    trend_dir = Path(tmpdir) / ".yuleosh" / "reports"
    trend_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) + "\n" for e in entries]
    (trend_dir / filename).write_text("".join(lines))


class TestGetMisraTrendAvg:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = _get_misra_trend_avg(td, days=28)
            assert result == {}

    def test_single_entry(self):
        with tempfile.TemporaryDirectory() as td:
            _write_trend_file(td, "misra-trend.jsonl", [
                {"total_violations": 10, "required": 3, "advisory": 5, "timestamp": "2026-07-01T00:00:00"}
            ])
            result = _get_misra_trend_avg(td, days=28)
            assert result["avg_total_violations"] == 10.0
            assert result["avg_required"] == 3.0
            assert result["entry_count"] == 1

    def test_multiple_entries(self):
        with tempfile.TemporaryDirectory() as td:
            _write_trend_file(td, "misra-trend.jsonl", [
                {"total_violations": 10, "required": 3, "advisory": 5, "timestamp": "2026-07-01T00:00:00"},
                {"total_violations": 20, "required": 6, "advisory": 10, "timestamp": "2026-07-10T00:00:00"},
            ])
            result = _get_misra_trend_avg(td, days=28)
            assert result["avg_total_violations"] == 15.0
            assert result["entry_count"] == 2

    def test_min_max(self):
        with tempfile.TemporaryDirectory() as td:
            _write_trend_file(td, "misra-trend.jsonl", [
                {"total_violations": 5, "required": 1, "advisory": 2, "timestamp": "2026-07-01T00:00:00"},
                {"total_violations": 25, "required": 8, "advisory": 12, "timestamp": "2026-07-10T00:00:00"},
            ])
            result = _get_misra_trend_avg(td, days=28)
            assert result["min_total_violations"] == 5
            assert result["max_total_violations"] == 25


class TestGetCoverageTrendAvg:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = _get_coverage_trend_avg(td, days=28)
            assert result == {}

    def test_single_entry(self):
        with tempfile.TemporaryDirectory() as td:
            _write_trend_file(td, "coverage-trend.jsonl", [{
                "c": {"line_rate": 60.0, "branch_rate": 50.0},
                "python": {"line_rate": 80.0, "branch_rate": 70.0},
                "timestamp": "2026-07-01T00:00:00",
            }])
            result = _get_coverage_trend_avg(td, days=28)
            assert result["avg_c_line_rate"] == 60.0
            assert result["avg_c_branch_rate"] == 50.0
            assert result["avg_py_line_rate"] == 80.0
            assert result["avg_py_branch_rate"] == 70.0

    def test_missing_coverage_keys(self):
        with tempfile.TemporaryDirectory() as td:
            _write_trend_file(td, "coverage-trend.jsonl", [{
                "c": {},
                "python": {},
                "timestamp": "2026-07-01T00:00:00",
            }])
            result = _get_coverage_trend_avg(td, days=28)
            assert result["avg_c_line_rate"] == 0.0

    def test_bad_json_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            f = trend_dir / "coverage-trend.jsonl"
            f.write_text("not-json\n" + json.dumps({
                "c": {"line_rate": 75.0, "branch_rate": 65.0},
                "python": {"line_rate": 85.0, "branch_rate": 75.0},
                "timestamp": "2026-07-01T00:00:00",
            }) + "\n")
            result = _get_coverage_trend_avg(td, days=28)
            assert result["avg_c_line_rate"] == 75.0
