#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
E08/E09 — KPI 基线采集流程 & 4周数据积累引擎测试

测试套件覆盖:
    - kpi.kpi_status()
    - kpi.kpi_baseline_save() / kpi_baseline_compare()
    - misra_trend.append_entry()
    - coverage_trend.show_coverage_trend()

Run:  python3 -m pytest tests/test_kpi.py -v --tb=short -q
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Ensure src/ is importable
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SRC))


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_project(tmp_path: Path) -> str:
    """Create a temporary project directory with .yuleosh/reports."""
    reports = tmp_path / ".yuleosh" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return str(tmp_path)


@pytest.fixture
def seeded_misra_trend(tmp_project: str) -> str:
    """Write 30 fake MISRA trend entries over ~28 days, return project_dir."""
    project_dir = tmp_project
    path = Path(project_dir) / ".yuleosh" / "reports" / "misra-trend.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    with open(path, "w", encoding="utf-8") as f:
        for i in range(30):
            ts = (now - timedelta(days=29 - i)).isoformat()
            entry = {
                "timestamp": ts,
                "total_violations": 30 - i,
                "required": max(0, 10 - i // 3),
                "advisory": max(0, 15 - i // 2),
                "files_checked": 45 + i,
                "is_delta": False,
                "commit": f"abc{i:04d}",
            }
            f.write(json.dumps(entry) + "\n")
    return project_dir


@pytest.fixture
def seeded_coverage_trend(tmp_project: str) -> str:
    """Write 30 fake coverage trend entries over ~28 days, return project_dir."""
    project_dir = tmp_project
    path = Path(project_dir) / ".yuleosh" / "reports" / "coverage-trend.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    with open(path, "w", encoding="utf-8") as f:
        for i in range(30):
            ts = (now - timedelta(days=29 - i)).isoformat()
            c_line = 70.0 + i * 0.5
            c_branch = 60.0 + i * 0.3
            py_line = 75.0 + i * 0.4
            py_branch = 65.0 + i * 0.3
            entry = {
                "timestamp": ts,
                "commit": f"co{i:04d}",
                "c": {"line_rate": round(c_line, 1), "branch_rate": round(c_branch, 1)},
                "python": {"line_rate": round(py_line, 1), "branch_rate": round(py_branch, 1)},
            }
            f.write(json.dumps(entry) + "\n")
    return project_dir


@pytest.fixture
def seeded_both(seeded_misra_trend: str, seeded_coverage_trend: str) -> str:
    """Return project_dir with both trend files seeded."""
    return seeded_misra_trend  # same temp dir used


# ═══════════════════════════════════════════════════════════════
# 1. misra_trend.append_entry
# ═══════════════════════════════════════════════════════════════


class TestMisraTrendAppendEntry:
    def test_append_and_read(self, tmp_project: str):
        """append_entry writes a JSONL line and show_trend reads it back."""
        from yuleosh.ci.misra_trend import append_entry, show_trend

        append_entry(
            project_dir=tmp_project,
            total_violations=42,
            required=8,
            advisory=5,
            files_checked=50,
            is_delta=False,
            commit="abc123",
        )

        result = show_trend(project_dir=tmp_project, lines=10, as_json=True)
        data = json.loads(result)
        assert data["total_entries"] == 1
        assert data["entries"][0]["total_violations"] == 42
        assert data["entries"][0]["required"] == 8
        assert data["entries"][0]["commit"] == "abc123"

    def test_append_multiple(self, tmp_project: str):
        """Multiple appends create ordered entries."""
        from yuleosh.ci.misra_trend import append_entry, show_trend

        for i in range(5):
            append_entry(tmp_project, total_violations=10 + i, commit=f"c{i:04d}")

        result = show_trend(tmp_project, lines=10, as_json=True)
        data = json.loads(result)
        assert data["total_entries"] == 5
        # Latest entry first in the list (recent[-lines:])
        assert data["entries"][0]["total_violations"] == 10
        assert data["entries"][-1]["total_violations"] == 14

    def test_show_trend_empty(self, tmp_project: str):
        """show_trend on empty file returns meaningful error."""
        from yuleosh.ci.misra_trend import show_trend

        result = show_trend(tmp_project)
        assert "No trend data" in result

    def test_get_violations_per_kloc(self):
        """get_violations_per_kloc calculates density correctly."""
        from yuleosh.ci.misra_trend import get_violations_per_kloc

        assert get_violations_per_kloc(100, 10.0) == 10.0
        assert get_violations_per_kloc(50, 5.2) == 9.62
        assert get_violations_per_kloc(10, 0) == 0.0
        assert get_violations_per_kloc(10, -1) == 0.0


# ═══════════════════════════════════════════════════════════════
# 2. coverage_trend.show_coverage_trend
# ═══════════════════════════════════════════════════════════════


class TestCoverageTrend:
    def test_record_and_show(self, tmp_project: str):
        """record_coverage writes an entry that show_coverage_trend returns."""
        from yuleosh.ci.coverage_trend import record_coverage, show_coverage_trend

        # Create a fake c-coverage.json so record_coverage picks it up
        cov_dir = Path(tmp_project) / ".yuleosh" / "reports"
        cov_dir.mkdir(parents=True, exist_ok=True)
        fake_c_cov = {"line_rate": 85.2, "branch_rate": 72.3, "total_files": 10}
        (cov_dir / "c-coverage.json").write_text(json.dumps(fake_c_cov))

        record_coverage(tmp_project)

        result = show_coverage_trend(tmp_project, days=365, lines=10, as_json=True)
        data = json.loads(result)
        assert data["total_entries"] == 1
        assert data["entries"][0]["c"]["line_rate"] == 85.2

    def test_show_trend_empty(self, tmp_project: str):
        """show_coverage_trend on empty returns meaningful message."""
        from yuleosh.ci.coverage_trend import show_coverage_trend

        result = show_coverage_trend(tmp_project)
        assert "No coverage trend data" in result

    def test_show_trend_day_filter(self, seeded_coverage_trend: str):
        """Day filter returns only recent entries."""
        from yuleosh.ci.coverage_trend import show_coverage_trend

        # 30 entries seeded over 29 days, filter 7 days → ~7-8 entries
        result = show_coverage_trend(seeded_coverage_trend, days=7, as_json=True)
        data = json.loads(result)
        assert 5 <= data["total_entries"] <= 10
        assert data["returned_entries"] <= data["total_entries"]


# ═══════════════════════════════════════════════════════════════
# 3. kpi.kpi_status
# ═══════════════════════════════════════════════════════════════


class TestKpiStatus:
    def test_status_with_no_data(self, tmp_project: str):
        """kpi_status returns gracefully when no trend data exists."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(tmp_project, as_json=True)
        data = json.loads(result)
        assert "entries" in data
        # No MISRA violations should default to 0
        misra_entry = data["entries"][0]
        assert misra_entry["metric"] == "misra_total_violations"
        assert misra_entry["value"] == 0

    def test_status_with_seeded_data(self, seeded_both: str):
        """kpi_status reflects seeded trend data."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(seeded_both, as_json=True)
        data = json.loads(result)
        entries = {e["metric"]: e for e in data["entries"]}

        # Latest MISRA entry: i=29 → total_violations=30-29=1
        assert entries["misra_total_violations"]["value"] == 1
        assert entries["misra_required_violations"]["value"] == 1  # 10 - 29//3 = 1
        assert entries["misra_advisory_violations"]["value"] == 1  # 15 - 29//2 = 1

        # Latest coverage: i=29 → c_line = 70.0 + 29*0.5 = 84.5
        if "c_line_coverage_pct" in entries:
            assert entries["c_line_coverage_pct"]["value"] == 84.5

    def test_status_includes_28d_trend(self, seeded_both: str):
        """kpi_status JSON includes 28-day trend data."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(seeded_both, as_json=True)
        data = json.loads(result)
        trend = data.get("trend_28d", {})
        assert "misra" in trend
        assert "coverage" in trend
        misra_trend = trend["misra"]
        assert "avg_total_violations" in misra_trend
        # 30 entries seeded over 29 days; 28-day window should include 28-29 entries
        assert 28 <= misra_trend["entry_count"] <= 29

    def test_status_markdown_output(self, seeded_both: str):
        """kpi_status returns a markdown table when as_json=False."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(seeded_both, as_json=False)
        assert "KPI Dashboard" in result
        assert "MISRA 总违规" in result
        assert "C Line 覆盖率" in result
        assert "28 天" in result or "趋势" in result

    def test_status_custom_thresholds(self, tmp_project: str):
        """Custom thresholds are reflected in status evaluation."""
        from yuleosh.ci.kpi import kpi_status

        result = kpi_status(tmp_project, as_json=True, thresholds={"misra_total_violations": 10})
        data = json.loads(result)
        assert data["thresholds"]["misra_total_violations"] == 10


# ═══════════════════════════════════════════════════════════════
# 4. kpi.kpi_baseline_save / kpi_baseline_compare
# ═══════════════════════════════════════════════════════════════


class TestKpiBaseline:
    def test_baseline_save_creates_file(self, tmp_project: str):
        """kpi_baseline_save writes a KPI baseline JSON file."""
        from yuleosh.ci.kpi import kpi_baseline_save

        saved = kpi_baseline_save(tmp_project, label="test-baseline")
        assert saved["label"] == "test-baseline"
        assert "baseline_id" in saved
        assert "saved_at" in saved
        assert "snapshot" in saved

        # File exists
        bl_path = Path(tmp_project) / ".yuleosh" / "kpi-baseline.json"
        assert bl_path.exists()
        loaded = json.loads(bl_path.read_text(encoding="utf-8"))
        assert loaded["label"] == "test-baseline"

    def test_baseline_save_captures_seeded_data(self, seeded_both: str):
        """Baseline save captures latest trend values."""
        from yuleosh.ci.kpi import kpi_baseline_save

        saved = kpi_baseline_save(seeded_both)
        snapshot = saved["snapshot"]
        # Latest misra: i=29 → total_violations=1
        assert snapshot["misra"]["total_violations"] == 1

    def test_baseline_compare_no_baseline(self, tmp_project: str):
        """Compare without saved baseline returns helpful message."""
        from yuleosh.ci.kpi import kpi_baseline_compare

        result = kpi_baseline_compare(tmp_project)
        assert "No KPI baseline found" in result

    def test_baseline_compare_with_changes(self, seeded_both: str):
        """Compare detects changes between baseline and current state."""
        from yuleosh.ci.kpi import kpi_baseline_save, kpi_baseline_compare

        # Save baseline
        kpi_baseline_save(seeded_both, label="baseline-v1")

        # Now append new data (simulate improvement)
        from yuleosh.ci.misra_trend import append_entry
        append_entry(seeded_both, total_violations=5, required=1, advisory=2,
                     files_checked=50, commit="newfix")

        compare_md = kpi_baseline_compare(seeded_both, as_json=False)
        assert "KPI 基线对比" in compare_md
        assert "MISRA 总违规" in compare_md

        compare_json = kpi_baseline_compare(seeded_both, as_json=True)
        data = json.loads(compare_json)
        assert "comparisons" in data
        # MISRA total: baseline=1 (latest), current=5 (after append)
        misra_comp = [c for c in data["comparisons"] if c["metric"] == "misra_total_violations"][0]
        assert misra_comp["current"] == 5
        assert misra_comp["baseline"] == 1
        assert misra_comp["diff"] == 4  # 5 - 1

    def test_baseline_compare_json_format(self, seeded_both: str):
        """Compare in JSON format includes all expected fields."""
        from yuleosh.ci.kpi import kpi_baseline_save, kpi_baseline_compare

        kpi_baseline_save(seeded_both, label="v1")
        result = kpi_baseline_compare(seeded_both, as_json=True)
        data = json.loads(result)
        assert "baseline_id" in data
        assert "baseline_label" in data
        assert data["baseline_label"] == "v1"
        assert "comparisons" in data
        assert len(data["comparisons"]) == 7  # 7 metrics


# ═══════════════════════════════════════════════════════════════
# 5. CLI command availability
# ═══════════════════════════════════════════════════════════════


class TestKpiCliCommands:
    def test_cli_has_kpi_commands(self):
        """The CLI module has cmd_kpi_status, cmd_kpi_baseline_save, cmd_kpi_baseline_compare."""
        from yuleosh_cli import cmd_kpi_status, cmd_kpi_baseline_save, cmd_kpi_baseline_compare

        assert callable(cmd_kpi_status)
        assert callable(cmd_kpi_baseline_save)
        assert callable(cmd_kpi_baseline_compare)
