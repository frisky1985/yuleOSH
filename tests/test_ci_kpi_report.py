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

    def test_with_bad_process_kpi_json_returns_ok(self):
        """Cover process_data exception handler (lines 89-90)."""
        with tempfile.TemporaryDirectory() as td:
            # Write invalid JSON to process-kpi.jsonl
            d = Path(td) / ".yuleosh" / "reports"
            d.mkdir(parents=True, exist_ok=True)
            (d / "process-kpi.jsonl").write_text("not-valid-json\n")
            result = kpi_status(td, as_json=True)
            data = json.loads(result)
            # Should not crash — process_data should be {}
            assert "entries" in data

    def test_markdown_format_with_misra_violations(self):
        """Test markdown rendering with misra data above threshold."""
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 60, "required": 10, "advisory": 25,
                 "files_checked": 20, "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            result = kpi_status(td, as_json=False)
            assert "❌ FAIL" in result

    def test_markdown_with_coverage_and_process_data(self):
        """Test markdown rendering with full data including trend sections."""
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5,
                 "timestamp": "2026-07-01T00:00:00"}
            ])
            _write_coverage_trend(td, [
                {"c": {"line_rate": 80.0, "branch_rate": 70.0},
                 "python": {"line_rate": 90.0, "branch_rate": 80.0},
                 "timestamp": "2026-07-01T00:00:00"}
            ])
            result = kpi_status(td, as_json=False)
            assert "KPI Dashboard" in result
            assert "MISRA" in result
            assert "覆盖率" in result


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

    def test_baseline_with_misra_and_coverage_data(self):
        """Save baseline with misra and coverage data present."""
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5,
                 "files_checked": 20, "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            _write_coverage_trend(td, [
                {"c": {"line_rate": 75.0, "branch_rate": 65.0},
                 "python": {"line_rate": 85.0, "branch_rate": 75.0},
                 "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            baseline = kpi_baseline_save(td, label="sprint-13")
            assert baseline["snapshot"]["misra"]["total_violations"] == 10
            assert baseline["snapshot"]["coverage"]["c_line_rate"] == 75.0

    def test_baseline_with_process_and_defect_escape(self):
        """Save baseline with process stability and defect escape data."""
        with tempfile.TemporaryDirectory() as td:
            _write_process_kpi(td, [
                {"build_success": True, "build_duration_s": 30.0, "layer": 1,
                 "total_stages": 10, "passed_stages": 10, "regression_triggered": False,
                 "misra_required_new": 0, "timestamp": "2026-07-01T00:00:00", "date": "2026-07-01"}
            ])
            baseline = kpi_baseline_save(td, label="with-process")
            assert baseline["process_stability_28d"]["total_builds"] == 1


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

    def test_baseline_compare_with_worse_metrics(self):
        """Cover the worse_count > 0 branch in baseline_compare."""
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5,
                 "files_checked": 20, "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            _write_coverage_trend(td, [
                {"c": {"line_rate": 75.0, "branch_rate": 65.0},
                 "python": {"line_rate": 85.0, "branch_rate": 75.0},
                 "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            kpi_baseline_save(td, label="baseline")
            # Now make current data worse
            _write_misra_trend(td, [
                {"total_violations": 30, "required": 8, "advisory": 15,
                 "files_checked": 20, "commit": "def456", "timestamp": "2026-07-15T00:00:00"}
            ])
            _write_coverage_trend(td, [
                {"c": {"line_rate": 60.0, "branch_rate": 50.0},
                 "python": {"line_rate": 70.0, "branch_rate": 60.0},
                 "commit": "def456", "timestamp": "2026-07-15T00:00:00"}
            ])
            result = kpi_baseline_compare(td)
            assert "项指标恶化" in result

    def test_markdown_with_improved_metrics(self):
        """Cover the else branch (worse_count == 0)."""
        with tempfile.TemporaryDirectory() as td:
            _write_misra_trend(td, [
                {"total_violations": 30, "required": 8, "advisory": 15,
                 "files_checked": 20, "commit": "abc123", "timestamp": "2026-07-01T00:00:00"}
            ])
            kpi_baseline_save(td, label="baseline")
            _write_misra_trend(td, [
                {"total_violations": 10, "required": 2, "advisory": 5,
                 "files_checked": 20, "commit": "def456", "timestamp": "2026-07-15T00:00:00"}
            ])
            result = kpi_baseline_compare(td)
            assert "所有指标相较基线持平或改善" in result
