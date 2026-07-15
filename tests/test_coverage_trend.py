# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ci/coverage_trend.py — coverage target ≥50%. """

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# _ensure_trend_dir
# ===================================================================


class TestEnsureTrendDir:
    def test_creates_parent(self, tmp_path):
        """GIVEN project dir without .yuleosh/reports WHEN ensuring dir THEN creates it."""
        from yuleosh.ci.coverage_trend import _ensure_trend_dir
        result = _ensure_trend_dir(str(tmp_path))
        assert "coverage-trend.jsonl" in str(result)
        assert result.parent.exists()
        # File not created yet, only the directory


# ===================================================================
# _load_json_report
# ===================================================================


class TestLoadJsonReport:
    def test_file_not_found(self, tmp_path):
        """GIVEN non-existent file WHEN loading THEN returns None."""
        from yuleosh.ci.coverage_trend import _load_json_report
        result = _load_json_report(str(tmp_path), "nonexistent.json")
        assert result is None

    def test_valid_json(self, tmp_path):
        """GIVEN valid JSON file WHEN loading THEN returns parsed data."""
        from yuleosh.ci.coverage_trend import _load_json_report
        data = {"line_rate": 85.0, "branch_rate": 70.0}
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        result = _load_json_report(str(tmp_path), "test.json")
        assert result == data

    def test_corrupted_json(self, tmp_path, caplog):
        """GIVEN corrupted JSON WHEN loading THEN returns None."""
        from yuleosh.ci.coverage_trend import _load_json_report
        path = tmp_path / "bad.json"
        path.write_text("not json")
        result = _load_json_report(str(tmp_path), "bad.json")
        assert result is None


# ===================================================================
# _get_c_coverage / _get_py_coverage
# ===================================================================


class TestGetCCoverage:
    def test_no_report(self, tmp_path):
        """GIVEN no c-coverage.json WHEN getting C coverage THEN returns None metrics."""
        from yuleosh.ci.coverage_trend import _get_c_coverage
        result = _get_c_coverage(str(tmp_path))
        assert result["line_rate"] is None
        assert result["branch_rate"] is None

    def test_with_report(self, tmp_path):
        """GIVEN c-coverage.json exists WHEN getting THEN returns metrics."""
        from yuleosh.ci.coverage_trend import _get_c_coverage
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "c-coverage.json").write_text(
            json.dumps({"line_rate": 75.0, "branch_rate": 60.0, "total_files": 10})
        )
        result = _get_c_coverage(str(tmp_path))
        assert result["line_rate"] == 75.0
        assert result["branch_rate"] == 60.0
        assert result["total_files"] == 10


class TestGetPyCoverage:
    def test_no_report(self, tmp_path):
        """GIVEN no coverage.json WHEN getting Python coverage THEN returns None."""
        from yuleosh.ci.coverage_trend import _get_py_coverage
        result = _get_py_coverage(str(tmp_path))
        assert result["line_rate"] is None

    def test_with_yuleosh_report(self, tmp_path):
        """GIVEN .yuleosh/reports/coverage.json WHEN getting THEN returns data."""
        from yuleosh.ci.coverage_trend import _get_py_coverage
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "coverage.json").write_text(
            json.dumps({"line_rate": 90.0, "branch_rate": 80.0})
        )
        result = _get_py_coverage(str(tmp_path))
        assert result["line_rate"] == 90.0

    def test_with_osh_ci_report(self, tmp_path):
        """GIVEN .osh/ci/coverage.json WHEN getting THEN returns data."""
        from yuleosh.ci.coverage_trend import _get_py_coverage
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "coverage.json").write_text(
            json.dumps({"line_rate": 85.0, "branch_rate": 70.0})
        )
        result = _get_py_coverage(str(tmp_path))
        assert result["line_rate"] == 85.0

    def test_with_coverage_dir_report(self, tmp_path):
        """GIVEN coverage/coverage.json WHEN getting THEN returns data."""
        from yuleosh.ci.coverage_trend import _get_py_coverage
        cov_dir = tmp_path / "coverage"
        cov_dir.mkdir(parents=True, exist_ok=True)
        (cov_dir / "coverage.json").write_text(
            json.dumps({"totals": {"percent_covered": 88.0, "percent_covered_branches": 78.0}})
        )
        result = _get_py_coverage(str(tmp_path))
        assert result["line_rate"] == 88.0


# ===================================================================
# _get_git_commit
# ===================================================================


class TestGetGitCommit:
    def test_not_git_repo(self, tmp_path):
        """GIVEN non-git directory WHEN getting commit THEN returns empty string."""
        from yuleosh.ci.coverage_trend import _get_git_commit
        result = _get_git_commit(str(tmp_path))
        assert result == ""


# ===================================================================
# record_coverage
# ===================================================================


class TestRecordCoverage:
    def test_records_entry(self, tmp_path):
        """GIVEN valid project dir WHEN recording coverage THEN writes JSONL entry."""
        from yuleosh.ci.coverage_trend import record_coverage
        record_coverage(str(tmp_path))
        trend_file = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        assert trend_file.exists()
        lines = trend_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "timestamp" in entry
        assert "c" in entry
        assert "python" in entry
        assert "commit" in entry


# ===================================================================
# show_coverage_trend
# ===================================================================


class TestShowCoverageTrend:
    def test_no_data(self, tmp_path):
        """GIVEN no trend data WHEN showing THEN returns error message."""
        from yuleosh.ci.coverage_trend import show_coverage_trend
        result = show_coverage_trend(str(tmp_path))
        assert "No coverage trend data" in result

    def test_with_data(self, tmp_path):
        """GIVEN trend data exists WHEN showing THEN returns markdown table."""
        from yuleosh.ci.coverage_trend import show_coverage_trend
        from datetime import datetime, timedelta
        trend_file = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "commit": "abc123",
            "c": {"line_rate": 75.0, "branch_rate": 60.0},
            "python": {"line_rate": 85.0, "branch_rate": 70.0},
        }
        trend_file.write_text(json.dumps(entry) + "\n")
        result = show_coverage_trend(str(tmp_path), days=365)
        assert "75.0" in result

    def test_as_json(self, tmp_path):
        """GIVEN as_json=True WHEN showing THEN returns JSON."""
        from yuleosh.ci.coverage_trend import show_coverage_trend
        from datetime import datetime
        trend_file = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend_file.parent.mkdir(parents=True, exist_ok=True)
        trend_file.write_text(json.dumps({"timestamp": datetime.now().isoformat()}) + "\n")
        result = show_coverage_trend(str(tmp_path), as_json=True, days=365)
        data = json.loads(result)
        assert "entries" in data

    def test_day_filter(self, tmp_path):
        """GIVEN days filter WHEN showing THEN filters old entries."""
        from yuleosh.ci.coverage_trend import show_coverage_trend
        trend_file = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend_file.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timedelta
        old = datetime.now() - timedelta(days=60)
        trend_file.write_text(
            json.dumps({"timestamp": old.isoformat()}) + "\n"
        )
        result = show_coverage_trend(str(tmp_path), days=30)
        assert "No coverage entries within" in result


# ===================================================================
# _parse_timestamp
# ===================================================================


class TestParseTimestamp:
    def test_valid_iso(self):
        """GIVEN valid ISO timestamp WHEN parsing THEN returns datetime."""
        from yuleosh.ci.coverage_trend import _parse_timestamp
        from datetime import datetime
        result = _parse_timestamp("2025-06-01T12:00:00")
        assert result.year == 2025
        assert result.month == 6

    def test_invalid_timestamp(self):
        """GIVEN invalid timestamp WHEN parsing THEN returns epoch."""
        from yuleosh.ci.coverage_trend import _parse_timestamp
        from datetime import datetime
        result = _parse_timestamp("bad-timestamp")
        assert result.year == 1970

    def test_with_timezone(self):
        """GIVEN timestamp with timezone WHEN parsing THEN strips tz."""
        from yuleosh.ci.coverage_trend import _parse_timestamp
        result = _parse_timestamp("2025-06-01T12:00:00+08:00")
        assert result.tzinfo is None


# ===================================================================
# check_coverage_regression
# ===================================================================


class TestCheckCoverageRegression:
    def test_no_data(self, tmp_path):
        """GIVEN no trend file WHEN checking regression THEN returns warning."""
        from yuleosh.ci.coverage_trend import check_coverage_regression
        result = check_coverage_regression(str(tmp_path))
        assert result["status"] == "warning"
        assert result["regression"] is False

    def test_insufficient_data(self, tmp_path):
        """GIVEN only 1 entry WHEN checking THEN returns insufficient data."""
        from yuleosh.ci.coverage_trend import check_coverage_regression
        trend = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        trend.write_text(json.dumps({"timestamp": "2025-01-01", "c": {"line_rate": 80.0}}) + "\n")
        result = check_coverage_regression(str(tmp_path))
        assert result["status"] == "warning"
        assert "insufficient_data" in str(result["alerts"])

    def test_no_regression(self, tmp_path):
        """GIVEN stable coverage WHEN checking THEN no regression."""
        from yuleosh.ci.coverage_trend import check_coverage_regression
        trend = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        # Write all lines at once
        entries = [
            {"timestamp": "2025-01-01", "c": {"line_rate": 80.0, "branch_rate": 70.0},
             "python": {"line_rate": 85.0, "branch_rate": 75.0}},
            {"timestamp": "2025-01-02", "c": {"line_rate": 79.0, "branch_rate": 69.0},
             "python": {"line_rate": 84.0, "branch_rate": 74.0}},
        ]
        lines = "\n".join(json.dumps(e) for e in entries) + "\n"
        trend.write_text(lines)
        result = check_coverage_regression(str(tmp_path))
        assert result["status"] == "passed"

    def test_c_line_regression(self, tmp_path):
        """GIVEN C line coverage drops WHEN checking THEN flags regression."""
        from yuleosh.ci.coverage_trend import check_coverage_regression
        trend = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {"timestamp": "2025-01-01", "c": {"line_rate": 80.0, "branch_rate": 70.0},
             "python": {"line_rate": 85.0, "branch_rate": 75.0}},
            {"timestamp": "2025-01-02", "c": {"line_rate": 60.0, "branch_rate": 70.0},
             "python": {"line_rate": 85.0, "branch_rate": 75.0}},
        ]
        lines = "\n".join(json.dumps(e) for e in entries) + "\n"
        trend.write_text(lines)
        result = check_coverage_regression(str(tmp_path), line_drop_threshold=5.0)
        assert result["regression"] is True
        assert len(result["alerts"]) >= 1

    def test_py_branch_regression(self, tmp_path):
        """GIVEN Python branch coverage drops WHEN checking THEN flags regression."""
        from yuleosh.ci.coverage_trend import check_coverage_regression
        trend = tmp_path / ".yuleosh" / "reports" / "coverage-trend.jsonl"
        trend.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {"timestamp": "2025-01-01", "c": {"line_rate": 80.0, "branch_rate": 70.0},
             "python": {"line_rate": 85.0, "branch_rate": 75.0}},
            {"timestamp": "2025-01-02", "c": {"line_rate": 80.0, "branch_rate": 70.0},
             "python": {"line_rate": 85.0, "branch_rate": 50.0}},
        ]
        lines = "\n".join(json.dumps(e) for e in entries) + "\n"
        trend.write_text(lines)
        result = check_coverage_regression(str(tmp_path), branch_drop_threshold=5.0)
        assert result["regression"] is True
        py_alerts = [a for a in result["alerts"] if "py_branch" in a["type"]]
        assert len(py_alerts) >= 1
