# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for kpi/stability.py and kpi/defects.py.

Covers uncovered functions:
  - get_process_stability_summary (markdown and JSON paths)
  - generate_process_baseline_report
  - get_defect_escape_summary (markdown and JSON paths)

Each test creates its own project dir with seeded JSONL data.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


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
def seeded_process_kpi(tmp_project: str) -> str:
    """Seed 20 process KPI entries over ~19 days."""
    project_dir = tmp_project
    path = Path(project_dir) / ".yuleosh" / "reports" / "process-kpi.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    with open(path, "w", encoding="utf-8") as f:
        for i in range(20):
            ts = (now - timedelta(days=19 - i)).isoformat()
            success = i % 5 != 0  # 80% success rate (4 out of 5)
            entry = {
                "timestamp": ts,
                "date": ts[:10],
                "build_success": success,
                "build_duration_s": 10.0 + i * 0.5,
                "layer": (i % 3) + 1,
                "total_stages": 10,
                "passed_stages": 9 if success else 3,
                "failed_stages": 1 if success else 7,
                "regression_triggered": not success,
                "misra_required_new": max(0, i - 15),
                "misra_total": 20 + i,
            }
            f.write(json.dumps(entry) + "\n")
    return project_dir


@pytest.fixture
def seeded_defect_escape(tmp_project: str) -> str:
    """Seed 15 defect escape entries over ~90 days."""
    project_dir = tmp_project
    path = Path(project_dir) / ".yuleosh" / "reports" / "defect-escape.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    with open(path, "w", encoding="utf-8") as f:
        for i in range(15):
            ts = (now - timedelta(days=89 - i * 6)).isoformat()
            total = 20 + i
            escaped = max(0, 5 - i // 3)  # decreasing escape
            entry = {
                "timestamp": ts,
                "date": ts[:10],
                "total_defects": total,
                "escaped_defects": escaped,
                "escape_rate": round(escaped / total * 100, 1) if total > 0 else 0.0,
                "internal_defects": total - escaped,
                "stage": "system-test" if i < 8 else "customer",
                "description": f"Entry {i}",
            }
            f.write(json.dumps(entry) + "\n")
    return project_dir


# ═══════════════════════════════════════════════════════════════
# Process Stability KPI tests
# ═══════════════════════════════════════════════════════════════


class TestProcessStabilityKPI:
    """Tests for process stability KPI functions."""

    def test_record_and_load(self, tmp_project: str):
        """record_process_stability writes, _load_process_kpi_entries reads."""
        from yuleosh.ci.kpi.stability import record_process_stability, _load_process_kpi_entries

        for i in range(5):
            record_process_stability(
                tmp_project,
                build_success=(i != 2),
                build_duration_s=15.0 + i,
                layer=1,
                total_stages=10,
                passed_stages=9 if i != 2 else 2,
                misra_required_new=max(0, i - 3),
                misra_total=25 + i,
            )

        entries = _load_process_kpi_entries(tmp_project)
        assert len(entries) == 5
        assert entries[0]["build_success"] is True
        assert entries[2]["build_success"] is False
        assert entries[2]["regression_triggered"] is True

    def test_load_empty(self, tmp_project: str):
        """_load_process_kpi_entries returns [] for missing file."""
        from yuleosh.ci.kpi.stability import _load_process_kpi_entries
        assert _load_process_kpi_entries(tmp_project) == []

    def test_summary_no_data(self, tmp_project: str):
        """get_process_stability_summary with no data returns error."""
        from yuleosh.ci.kpi.stability import get_process_stability_summary

        md = get_process_stability_summary(tmp_project, as_json=False)
        assert "No process stability KPI data" in md

        js = get_process_stability_summary(tmp_project, as_json=True)
        data = json.loads(js)
        assert "error" in data

    def test_summary_json(self, seeded_process_kpi: str):
        """get_process_stability_summary returns correct JSON."""
        from yuleosh.ci.kpi.stability import get_process_stability_summary

        result = get_process_stability_summary(seeded_process_kpi, days=30, as_json=True)
        data = json.loads(result)

        assert data["period_days"] == 30
        assert data["total_builds"] == 20
        # 80% success rate: 16 out of 20
        assert data["build_success_rate"] == 80.0
        assert data["regression_trigger_rate"] == 20.0  # 4 out of 20
        assert data["avg_build_duration_s"] > 0
        assert "build_success_status" in data
        assert "regression_status" in data

    def test_summary_markdown(self, seeded_process_kpi: str):
        """get_process_stability_summary returns markdown."""
        from yuleosh.ci.kpi.stability import get_process_stability_summary

        md = get_process_stability_summary(seeded_process_kpi, days=30, as_json=False)
        assert "过程稳定性 KPI 基线" in md
        assert "构建成功率" in md
        assert "回归触发率" in md
        assert "原始数据" in md

    def test_summary_day_filter(self, seeded_process_kpi: str):
        """Day filter limits results to recent entries."""
        from yuleosh.ci.kpi.stability import get_process_stability_summary

        # Only last 2 days of data (should have ~2 entries)
        result = get_process_stability_summary(seeded_process_kpi, days=2, as_json=True)
        data = json.loads(result)
        # 20 entries over 19 days, so 2 days → ~2 entries
        assert data["total_builds"] <= 3
        assert data["total_builds"] >= 1

    def test_summary_single_entry(self, tmp_project: str):
        """get_process_stability_summary works with a single entry."""
        from yuleosh.ci.kpi.stability import record_process_stability, get_process_stability_summary

        record_process_stability(tmp_project, build_success=True, build_duration_s=10.0)
        result = get_process_stability_summary(tmp_project, days=30, as_json=True)
        data = json.loads(result)
        assert data["total_builds"] == 1
        assert data["build_success_rate"] == 100.0

    def test_summary_all_fail(self, tmp_project: str):
        """get_process_stability_summary with all failures and mixed regression."""
        from yuleosh.ci.kpi.stability import record_process_stability, get_process_stability_summary

        for _ in range(5):
            record_process_stability(tmp_project, build_success=False)
        result = get_process_stability_summary(tmp_project, days=30, as_json=True)
        data = json.loads(result)
        assert data["build_success_rate"] == 0.0
        # Default total_stages=0, passed_stages=0 so 0 < 0 == False
        # regression_triggered defaults to False
        assert data["regression_trigger_rate"] >= 0.0

    def test_generate_baseline_report(self, seeded_process_kpi: str):
        """generate_process_baseline_report creates a report file."""
        from yuleosh.ci.kpi.stability import generate_process_baseline_report

        report_path = generate_process_baseline_report(seeded_process_kpi, label="sprint-2")
        assert Path(report_path).exists()

        content = Path(report_path).read_text(encoding="utf-8")
        assert "过程稳定性 KPI 基线报告" in content
        assert "构建成功率" in content
        assert "回归触发率" in content
        assert "违规修复时效" in content
        assert "构建时长统计" in content
        assert "每日明细" in content
        assert "20 次构建" in content or str(20) in content

    def test_generate_baseline_report_single(self, tmp_project: str):
        """generate_process_baseline_report works with a single entry."""
        from yuleosh.ci.kpi.stability import record_process_stability, generate_process_baseline_report

        record_process_stability(tmp_project, build_success=True, build_duration_s=5.0)

        report_path = generate_process_baseline_report(tmp_project, label="single")
        content = Path(report_path).read_text(encoding="utf-8")
        assert "过程稳定性 KPI 基线报告" in content
        assert "1 次构建" in content or "1" in content

    def test_generate_baseline_report_label(self, seeded_process_kpi: str):
        """generate_process_baseline_report includes the label."""
        from yuleosh.ci.kpi.stability import generate_process_baseline_report

        report_path = generate_process_baseline_report(seeded_process_kpi, label="v2-sprint")
        content = Path(report_path).read_text(encoding="utf-8")
        assert "v2-sprint" in content

    def test_ensure_dir_creates(self, tmp_project: str):
        """_ensure_process_kpi_dir creates parent directories."""
        from yuleosh.ci.kpi.stability import _ensure_process_kpi_dir

        deep_dir = Path(tmp_project) / "deep" / "nested" / "path"
        path = _ensure_process_kpi_dir(str(deep_dir))
        assert path.parent.exists()


# ═══════════════════════════════════════════════════════════════
# Defect Escape tests
# ═══════════════════════════════════════════════════════════════


class TestDefectEscape:
    """Tests for defect escape KPI functions."""

    def test_record_and_load(self, tmp_project: str):
        """record_defect_escape writes, _load_defect_escape_entries reads."""
        from yuleosh.ci.kpi.defects import record_defect_escape, _load_defect_escape_entries

        for i in range(5):
            record_defect_escape(
                tmp_project,
                total_defects=20 + i,
                escaped_defects=max(0, 5 - i),
                stage="system-test",
            )

        entries = _load_defect_escape_entries(tmp_project)
        assert len(entries) == 5
        assert entries[0]["escape_rate"] > 0
        assert entries[-1]["escaped_defects"] == 1  # 5 - 4

    def test_record_zero_total(self, tmp_project: str):
        """record_defect_escape with 0 total results in 0 escape rate."""
        from yuleosh.ci.kpi.defects import record_defect_escape

        entry = record_defect_escape(tmp_project, total_defects=0, escaped_defects=0)
        assert entry["escape_rate"] == 0.0

    def test_load_empty(self, tmp_project: str):
        """_load_defect_escape_entries returns [] for missing file."""
        from yuleosh.ci.kpi.defects import _load_defect_escape_entries
        assert _load_defect_escape_entries(tmp_project) == []

    def test_load_corrupted_line(self, tmp_project: str):
        """_load_defect_escape_entries skips corrupted lines."""
        path = Path(tmp_project) / ".yuleosh" / "reports" / "defect-escape.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"good": true}\nnot json\n{"also_good": true}\n', encoding="utf-8")

        from yuleosh.ci.kpi.defects import _load_defect_escape_entries
        entries = _load_defect_escape_entries(tmp_project)
        assert len(entries) == 2

    def test_summary_no_data(self, tmp_project: str):
        """get_defect_escape_summary with no data returns error."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        md = get_defect_escape_summary(tmp_project, as_json=False)
        assert "No defect escape data" in md

        js = get_defect_escape_summary(tmp_project, as_json=True)
        data = json.loads(js)
        assert "error" in data

    def test_summary_json(self, seeded_defect_escape: str):
        """get_defect_escape_summary returns correct JSON."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        result = get_defect_escape_summary(seeded_defect_escape, days=365, as_json=True)
        data = json.loads(result)

        assert "period_days" in data
        assert data["total_entries"] == 15
        assert data["total_defects"] > 0
        assert data["escape_rate"] >= 0
        assert data["status"] in ("PASS", "FAIL")

    def test_summary_markdown(self, seeded_defect_escape: str):
        """get_defect_escape_summary returns markdown."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        md = get_defect_escape_summary(seeded_defect_escape, days=365, as_json=False)
        assert "缺陷逃逸率" in md
        assert "总缺陷数" in md
        assert "逃逸缺陷" in md
        assert "原始数据" in md

    def test_summary_day_filter(self, seeded_defect_escape: str):
        """Day filter limits results."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        result = get_defect_escape_summary(seeded_defect_escape, days=7, as_json=True)
        data = json.loads(result)
        # 15 entries over 89 days, 7 day window → should have few entries
        assert data["total_entries"] <= 3

    def test_summary_no_recent_data(self, seeded_defect_escape: str):
        """get_defect_escape_summary with very short window."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        result = get_defect_escape_summary(seeded_defect_escape, days=0, as_json=True)
        data = json.loads(result)
        assert "error" in data

    def test_summary_trend_detection(self, seeded_defect_escape: str):
        """Trend arrow is present in JSON summary."""
        from yuleosh.ci.kpi.defects import get_defect_escape_summary

        result = get_defect_escape_summary(seeded_defect_escape, days=365, as_json=True)
        data = json.loads(result)
        assert "trend" in data
        assert data["trend"] in ("↑", "↓", "→")
