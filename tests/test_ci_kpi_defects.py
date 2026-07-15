"""Tests for ci/kpi/defects.py."""
import json
import tempfile
from pathlib import Path

from yuleosh.ci.kpi.defects import (
    _ensure_defect_escape_dir, record_defect_escape,
    _load_defect_escape_entries, get_defect_escape_summary,
)


class TestEnsureDefectEscapeDir:
    def test_creates_parent_dir(self):
        with tempfile.TemporaryDirectory() as td:
            path = _ensure_defect_escape_dir(td)
            assert path.parent.exists()
            assert path.name == "defect-escape.jsonl"

    def test_returns_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = _ensure_defect_escape_dir(td)
            assert isinstance(path, Path)


class TestRecordDefectEscape:
    def test_records_entry(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_defect_escape(td, total_defects=100, escaped_defects=10,
                                          stage="system-test", description="bug-123")
            assert entry["total_defects"] == 100
            assert entry["escaped_defects"] == 10
            assert entry["escape_rate"] == 10.0
            assert entry["stage"] == "system-test"
            assert entry["date"] is not None

    def test_zero_total_no_division_error(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_defect_escape(td, total_defects=0, escaped_defects=0)
            assert entry["escape_rate"] == 0.0

    def test_escape_rate_calculation(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_defect_escape(td, 200, 50)
            assert entry["escape_rate"] == 25.0

    def test_writes_to_file(self):
        with tempfile.TemporaryDirectory() as td:
            record_defect_escape(td, 100, 5)
            file_path = Path(td) / ".yuleosh" / "reports" / "defect-escape.jsonl"
            assert file_path.exists()
            content = file_path.read_text()
            assert "escape_rate" in content


class TestLoadDefectEscapeEntries:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            assert _load_defect_escape_entries(td) == []

    def test_returns_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            record_defect_escape(td, 100, 10)
            entries = _load_defect_escape_entries(td)
            assert len(entries) == 1
            assert entries[0]["total_defects"] == 100

    def test_skips_bad_json(self):
        with tempfile.TemporaryDirectory() as td:
            file_path = Path(td) / ".yuleosh" / "reports" / "defect-escape.jsonl"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("bad-json\n")
            entries = _load_defect_escape_entries(td)
            assert entries == []


class TestGetDefectEscapeSummary:
    def test_no_data(self):
        with tempfile.TemporaryDirectory() as td:
            summary = get_defect_escape_summary(td, days=90)
            assert "No defect escape data" in summary

    def test_no_data_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            result = get_defect_escape_summary(td, days=90, as_json=True)
            data = json.loads(result)
            assert "error" in data

    def test_with_data_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            record_defect_escape(td, 100, 10, stage="system-test")
            summary = get_defect_escape_summary(td, days=90)
            assert "缺陷逃逸率" in summary
            assert "system-test" in summary

    def test_with_data_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            record_defect_escape(td, 200, 30, stage="customer")
            result = get_defect_escape_summary(td, days=90, as_json=True)
            data = json.loads(result)
            assert data["escape_rate"] == 15.0
