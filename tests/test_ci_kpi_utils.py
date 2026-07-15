"""Tests for ci/kpi/utils.py."""
import json
import os
import tempfile
from pathlib import Path

from yuleosh.ci.kpi.utils import (
    _ensure_dir, _load_latest_misra_entry, _load_latest_coverage_entry,
    _parse_ts, _load_baseline, DEFAULT_THRESHOLDS,
)


class TestDefaults:
    def test_thresholds_have_expected_keys(self):
        assert "misra_total_violations" in DEFAULT_THRESHOLDS
        assert "c_line_coverage_pct" in DEFAULT_THRESHOLDS
        assert "build_success_rate_pct" in DEFAULT_THRESHOLDS
        assert "defect_escape_rate_pct" in DEFAULT_THRESHOLDS
        assert DEFAULT_THRESHOLDS["misra_total_violations"] == 50


class TestEnsureDir:
    def test_creates_dot_yuleosh(self):
        with tempfile.TemporaryDirectory() as td:
            path = _ensure_dir(td)
            assert path.exists()
            assert path.name == ".yuleosh"

    def test_returns_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = _ensure_dir(td)
            assert isinstance(path, Path)


class TestParseTs:
    def test_valid_iso(self):
        dt = _parse_ts("2026-01-15T10:30:00")
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15

    def test_valid_iso_with_tz(self):
        dt = _parse_ts("2026-01-15T10:30:00+08:00")
        assert dt.year == 2026

    def test_invalid(self):
        dt = _parse_ts("not-a-date")
        assert dt.year == 1970


class TestLoadLatestMisraEntry:
    def test_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            result = _load_latest_misra_entry(td)
            assert result == {}

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "misra-trend.jsonl").write_text("")
            result = _load_latest_misra_entry(td)
            assert result == {}

    def test_single_entry(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"total_violations": 10, "required": 3})
            (trend_dir / "misra-trend.jsonl").write_text(entry + "\n")
            result = _load_latest_misra_entry(td)
            assert result.get("total_violations") == 10

    def test_multiple_entries_returns_last(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            lines = (
                json.dumps({"total_violations": 20, "required": 5}) + "\n"
                + json.dumps({"total_violations": 15, "required": 3}) + "\n"
            )
            (trend_dir / "misra-trend.jsonl").write_text(lines)
            result = _load_latest_misra_entry(td)
            assert result.get("total_violations") == 15


class TestLoadLatestCoverageEntry:
    def test_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            result = _load_latest_coverage_entry(td)
            assert result == {}

    def test_single_entry(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            entry = json.dumps({"c": {"line_rate": 60.0}, "python": {"line_rate": 80.0}})
            (trend_dir / "coverage-trend.jsonl").write_text(entry + "\n")
            result = _load_latest_coverage_entry(td)
            assert result.get("c", {}).get("line_rate") == 60.0

    def test_bad_json_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "coverage-trend.jsonl").write_text(
                json.dumps({"c": {"line_rate": 70.0}}) + "\n"
                + "bad-json-line\n"
                + json.dumps({"c": {"line_rate": 80.0}}) + "\n"
            )
            result = _load_latest_coverage_entry(td)
            assert result.get("c", {}).get("line_rate") == 80.0


class TestLoadBaseline:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            assert _load_baseline(td) is None

    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as td:
            base = {"baseline_id": "bl-001", "label": "sprint-12"}
            bl_path = Path(td) / ".yuleosh" / "kpi-baseline.json"
            bl_path.parent.mkdir(parents=True, exist_ok=True)
            bl_path.write_text(json.dumps(base))
            result = _load_baseline(td)
            assert result["baseline_id"] == "bl-001"

    def test_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            bl_path = Path(td) / ".yuleosh" / "kpi-baseline.json"
            bl_path.parent.mkdir(parents=True, exist_ok=True)
            bl_path.write_text("not-json")
            result = _load_baseline(td)
            assert result is None
