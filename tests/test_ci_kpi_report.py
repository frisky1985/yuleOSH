"""Tests for ci/kpi/report.py."""
import json
import tempfile
from pathlib import Path

from yuleosh.ci.kpi.report import kpi_status, kpi_baseline_save, kpi_baseline_compare


def _write_misra_trend(tmpdir, entries):
    d = Path(tmpdir) / ".yuleosh" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) + "\n" for e in entries]
    (d / "misra-trend.jsonl").write_text("".join(lines))


def _write_coverage_trend(tmpdir, entries):
    d = Path(tmpdir) / ".yuleosh" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) + "\n" for e in entries]
    (d / "coverage-trend.jsonl").write_text("".join(lines))


def _write_process_kpi(tmpdir, entries):
    d = Path(tmpdir) / ".yuleosh" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) + "\n" for e in entries]
    (d / "process-kpi.jsonl").write_text("".join(lines))


def _write_defect_escape(tmpdir, entries):
    d = Path(tmpdir) / ".yuleosh" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) + "\n" for e in entries]
    (d / "defect-escape.jsonl").write_text("".join(lines))


class TestKpiStatus:
    def test_empty_no_data(self):
        with tempfile.TemporaryDirectory() as td:
            result = kpi_status(td)
            assert "KPI Dashboard" in result

    def test_empty_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            result = kpi_status(td, as_json=True)
            data = json.loads(result)
            assert "entries" in data
            assert "thresholds" in data

    def test_with_misra_data(self):
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5,
                 "files_checked": 20, "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            result = kpi_status(td, as_json=True)
            data = json.loads(result)
            entries = data["entries"]
            misra_entries = [e for e in entries if e["metric"].startswith("misra")]
            assert len(misra_entries) > 0

    def test_with_full_data(self):
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5, "timestamp": "2026-07-01T00:00:00"}
            ])
            _write_coverage_trend(td, [
                {"c": {"line_rate": 75.0, "branch_rate": 65.0},
                 "python": {"line_rate": 85.0, "branch_rate": 75.0},
                 "timestamp": "2026-07-01T00:00:00"}
            ])
            _write_process_kpi(td, [
                {"build_success": True, "build_duration_s": 30.0, "layer": 1,
                 "total_stages": 10, "passed_stages": 10,
                 "regression_triggered": False, "misra_required_new": 0,
                 "timestamp": "2026-07-01T00:00:00", "date": "2026-07-01"}
            ])
            result = kpi_status(td, as_json=True)
            data = json.loads(result)
            assert len(data["entries"]) >= 3

    def test_custom_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5, "timestamp": "2026-07-01T00:00:00"}
            ])
            result = kpi_status(td, as_json=True, thresholds={"misra_total_violations": 5})
            data = json.loads(result)
            assert data["thresholds"]["misra_total_violations"] == 5


class TestKpiBaselineSave:
    def test_saves_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            baseline = kpi_baseline_save(td, label="sprint-12")
            assert baseline["label"] == "sprint-12"
            assert "baseline_id" in baseline
            bl_path = Path(td) / ".yuleosh" / "kpi-baseline.json"
            assert bl_path.exists()

    def test_baseline_structure(self):
        with tempfile.TemporaryDirectory() as td:
            baseline = kpi_baseline_save(td)
            assert "snapshot" in baseline
            assert "misra" in baseline["snapshot"]
            assert "coverage" in baseline["snapshot"]
            assert "thresholds" in baseline


class TestKpiBaselineCompare:
    def test_no_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            result = kpi_baseline_compare(td)
            assert "No KPI baseline" in result

    def test_no_baseline_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            result = kpi_baseline_compare(td, as_json=True)
            data = json.loads(result)
            assert "error" in data

    def test_with_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            kpi_baseline_save(td, label="baseline-1")
            result = kpi_baseline_compare(td)
            assert "KPI 基线对比" in result

    def test_with_baseline_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            kpi_baseline_save(td, label="bl-1")
            result = kpi_baseline_compare(td, as_json=True)
            data = json.loads(result)
            assert "comparisons" in data
            assert data["baseline_label"] == "bl-1"
