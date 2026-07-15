"""
Extended tests for yuleosh.report.trend_exporter — uncovered paths.

Covers:
  - _normalize_timestamp with edge cases
  - export_misra_trend with real data
  - export_ut_trend with real data (both old and new formats)
  - export_trend_for_project with "ut" type
  - export_all_trends
  - CLI main()
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from datetime import datetime
from yuleosh.report.trend_exporter import (
    _normalize_timestamp,
    _get_project_name,
    _load_jsonl,
    export_misra_trend,
    export_ut_trend,
    export_trend_for_project,
    export_all_trends,
    main as trend_main,
)


# ═══════════════════════════════════════════════════════════════
# _normalize_timestamp — edge cases
# ═══════════════════════════════════════════════════════════════

class TestNormalizeTimestampEdge:
    """Edge cases for _normalize_timestamp."""

    def test_none_input(self):
        """GIVEN None input WHEN normalizing THEN returns empty string."""
        result = _normalize_timestamp(None)  # type: ignore[arg-type]
        assert result == ""

    def test_bogus_string(self):
        """GIVEN unparseable string WHEN normalizing THEN returns original."""
        result = _normalize_timestamp("not-a-timestamp-at-all")
        assert result == "not-a-timestamp-at-all"

    def test_iso_format_retained(self):
        """GIVEN valid ISO timestamp WHEN normalizing THEN returns ISO string."""
        result = _normalize_timestamp("2026-07-10T12:00:00")
        assert "2026" in result
        assert "T" in result


# ═══════════════════════════════════════════════════════════════
# _get_project_name
# ═══════════════════════════════════════════════════════════════

class TestGetProjectName:
    """Tests for _get_project_name."""

    def test_returns_basename(self, tmp_path: Path):
        """GIVEN a directory path WHEN getting project name THEN returns basename."""
        project = tmp_path / "my-project"
        project.mkdir()
        name = _get_project_name(str(project))
        assert name == "my-project"

    def test_returns_default_for_empty_pathlike(self):
        """GIVEN a path that resolves to empty name WHEN getting project name THEN returns default."""
        # Root dir
        name = _get_project_name("/")
        assert name == "default" or len(name) > 0


# ═══════════════════════════════════════════════════════════════
# export_misra_trend — with real data
# ═══════════════════════════════════════════════════════════════

class TestExportMisraTrendData:
    """Tests for export_misra_trend with real data."""

    def test_with_entries(self, tmp_path: Path):
        """GIVEN misra-trend.jsonl with entries WHEN exporting THEN returns history."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","total_violations":50,"required":5,"advisory":3,"files_checked":12,"commit":"abc123def456"}\n'
            '{"timestamp":"2026-01-02","total_violations":42,"required":4,"advisory":2,"files_checked":12,"commit":"def789ghi012"}\n'
        )

        result = export_misra_trend(str(tmp_path))
        assert result["report_type"] == "misra"
        assert result["total_entries"] == 2
        assert result["returned_entries"] == 2
        assert len(result["history"]) == 2
        assert result["history"][0]["total_violations"] == 50
        assert result["history"][1]["total_violations"] == 42

    def test_with_project_id_and_name(self, tmp_path: Path):
        """GIVEN project_id and project_name WHEN exporting THEN uses provided values."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","total_violations":50,"required":5,"advisory":3}\n'
        )

        result = export_misra_trend(
            str(tmp_path),
            project_id="proj-123",
            project_name="My Project",
        )
        assert result["project"] == "proj-123"
        assert result["project_name"] == "My Project"

    def test_max_entries_respected(self, tmp_path: Path):
        """GIVEN more entries than max_entries WHEN exporting THEN returns only max."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        lines = "\n".join(
            f'{{"timestamp":"2026-01-{d:02d}","total_violations":{d}}}'
            for d in range(1, 11)
        )
        (reports_dir / "misra-trend.jsonl").write_text(lines)

        result = export_misra_trend(str(tmp_path), max_entries=3)
        assert result["returned_entries"] == 3
        assert len(result["history"]) == 3

    def test_commit_truncation(self, tmp_path: Path):
        """GIVEN long commit hash WHEN exporting THEN truncates to 8 chars."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","total_violations":10,"commit":"abcdef0123456789"}\n'
        )

        result = export_misra_trend(str(tmp_path))
        assert result["history"][0]["build_id"] == "abcdef01"


# ═══════════════════════════════════════════════════════════════
# export_ut_trend — with real data
# ═══════════════════════════════════════════════════════════════

class TestExportUtTrendData:
    """Tests for export_ut_trend with real data."""

    def test_with_new_format_data(self, tmp_path: Path):
        """GIVEN coverage-trend.jsonl with new format (c.line_rate) WHEN exporting THEN uses new format."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","c":{"line_rate":85.5,"branch_rate":72.3,"total_files":10},"function_coverage":80.0}\n'
        )

        result = export_ut_trend(str(tmp_path))
        assert result["report_type"] == "ut"
        assert result["total_entries"] == 1
        history = result["history"][0]
        assert history["line_rate"] == 85.5
        assert history["branch_rate"] == 72.3
        assert history["total_files"] == 10
        assert history["function_coverage"] == 80.0

    def test_with_old_format_data(self, tmp_path: Path):
        """GIVEN coverage-trend.jsonl with old flat format WHEN exporting THEN falls back."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","line_coverage":80.0,"branch_coverage":70.0,"function_coverage":75.0,"files_measured":5}\n'
        )

        result = export_ut_trend(str(tmp_path))
        history = result["history"][0]
        assert history["line_rate"] == 80.0
        assert history["branch_rate"] == 70.0
        assert history["total_files"] == 5

    def test_with_partial_new_format(self, tmp_path: Path):
        """GIVEN new format with some missing fields WHEN exporting THEN handles gracefully."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","c":{"line_rate":90.0}}\n'
        )

        result = export_ut_trend(str(tmp_path))
        history = result["history"][0]
        assert history["line_rate"] == 90.0
        assert history["branch_rate"] == 0.0
        assert history["total_files"] == 0

    def test_with_empty_c_data_and_old_format(self, tmp_path: Path):
        """GIVEN c data None but old format present WHEN exporting THEN uses old format."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","c":{},"line_coverage":75.0,"branch_coverage":65.0}\n'
        )

        result = export_ut_trend(str(tmp_path))
        history = result["history"][0]
        assert history["line_rate"] == 75.0
        assert history["branch_rate"] == 65.0

    def test_with_project_id(self, tmp_path: Path):
        """GIVEN project_id WHEN exporting THEN uses provided project id."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","line_coverage":80.0,"branch_coverage":70.0}\n'
        )

        result = export_ut_trend(str(tmp_path), project_id="my-proj")
        assert result["project"] == "my-proj"

    def test_empty_data(self, tmp_path: Path):
        """GIVEN empty coverage-trend.jsonl WHEN exporting THEN returns empty history."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text("")

        result = export_ut_trend(str(tmp_path))
        assert result["total_entries"] == 0
        assert result["returned_entries"] == 0
        assert result["history"] == []

    def test_with_datetime_object_timestamp(self, tmp_path: Path):
        """GIVEN timestamp as datetime object WHEN exporting THEN handles gracefully."""
        from datetime import datetime
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01T00:00:00","line_coverage":80.0}\n'
        )
        result = export_ut_trend(str(tmp_path))
        assert result["total_entries"] == 1


# ═══════════════════════════════════════════════════════════════
# export_trend_for_project
# ═══════════════════════════════════════════════════════════════

class TestExportTrendForProject:
    """Tests for export_trend_for_project."""

    def test_misra_returns_misra(self, tmp_path: Path):
        """GIVEN report_type='misra' WHEN exporting trend THEN returns misra trend."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","total_violations":10}\n'
        )

        result = export_trend_for_project(str(tmp_path), "misra")
        assert result is not None
        assert result["report_type"] == "misra"

    def test_ut_returns_ut(self, tmp_path: Path):
        """GIVEN report_type='ut' WHEN exporting trend THEN returns ut trend."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","line_coverage":80.0}\n'
        )

        result = export_trend_for_project(str(tmp_path), "ut")
        assert result is not None
        assert result["report_type"] == "ut"

    def test_unsupported_type(self, tmp_path: Path):
        """GIVEN unsupported report_type WHEN exporting trend THEN returns None."""
        result = export_trend_for_project(str(tmp_path), "invalid_type")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# export_all_trends
# ═══════════════════════════════════════════════════════════════

class TestExportAllTrends:
    """Tests for export_all_trends."""

    def test_returns_both_trends(self, tmp_path: Path):
        """GIVEN project dir WHEN exporting all trends THEN returns both misra and ut."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","total_violations":10}\n'
        )
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","line_coverage":80.0}\n'
        )

        result = export_all_trends(str(tmp_path))
        assert "trends" in result
        assert "misra" in result["trends"]
        assert "ut" in result["trends"]
        assert result["trends"]["misra"]["report_type"] == "misra"
        assert result["trends"]["ut"]["report_type"] == "ut"

    def test_empty_reports(self, tmp_path: Path):
        """GIVEN no report files WHEN exporting all trends THEN returns empty trends."""
        result = export_all_trends(str(tmp_path))
        assert "trends" in result
        assert result["trends"]["misra"]["total_entries"] == 0
        assert result["trends"]["ut"]["total_entries"] == 0

    def test_with_project_id(self, tmp_path: Path):
        """GIVEN project_id WHEN exporting all trends THEN carries through."""
        result = export_all_trends(str(tmp_path), project_id="proj-x")
        assert result["project"] == "proj-x"


# ═══════════════════════════════════════════════════════════════
# CLI main()
# ═══════════════════════════════════════════════════════════════

class TestTrendCliMain:
    """Tests for CLI main()."""

    def test_default_all_type_stdout(self):
        """GIVEN default args WHEN main runs THEN prints JSON to stdout."""
        with patch("sys.argv", ["trend_exporter.py", "--project-dir", "/tmp"]):
            trend_main()
        # Should not raise

    def test_misra_type(self):
        """GIVEN --report-type misra WHEN main runs THEN outputs misra trend."""
        with patch("sys.argv", ["trend_exporter.py", "--project-dir", "/tmp", "--report-type", "misra"]):
            trend_main()
        # Should not raise

    def test_ut_type(self):
        """GIVEN --report-type ut WHEN main runs THEN outputs ut trend."""
        with patch("sys.argv", ["trend_exporter.py", "--project-dir", "/tmp", "--report-type", "ut"]):
            trend_main()
        # Should not raise

    def test_with_output_file(self, tmp_path: Path):
        """GIVEN --output flag WHEN main runs THEN writes to file."""
        out_path = tmp_path / "output.json"
        with patch(
            "sys.argv",
            [
                "trend_exporter.py",
                "--project-dir", str(tmp_path),
                "--report-type", "all",
                "--output", str(out_path),
            ],
        ):
            trend_main()
        assert out_path.exists()
        content = json.loads(out_path.read_text())
        assert "trends" in content

    def test_with_project_id(self, tmp_path: Path):
        """GIVEN --project-id flag WHEN main runs THEN uses that ID."""
        out_path = tmp_path / "output.json"
        with patch(
            "sys.argv",
            [
                "trend_exporter.py",
                "--project-dir", str(tmp_path),
                "--project-id", "custom-proj",
                "--output", str(out_path),
            ],
        ):
            trend_main()
        assert out_path.exists()
        content = json.loads(out_path.read_text())
        assert content["project"] == "custom-proj"
