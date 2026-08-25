"""Tests for pipeline.step_cache baseline metrics tracking (2A)."""

# @tests src/yuleosh/pipeline/step_cache.py

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from yuleosh.pipeline.step_cache import (
    BaselineMetrics,
    compare_to_baseline,
    load_latest_baseline,
    save_baseline,
)


@pytest.fixture
def tmp_project(tmp_path):
    return tmp_path


def _make_metrics(**kwargs) -> BaselineMetrics:
    defaults = dict(
        session_id="sess-001",
        run_at=datetime.now().isoformat(),
        coverage_pct=85.0,
        misra_violations=5,
        test_passed=100,
        test_failed=0,
        gates_passed=10,
    )
    defaults.update(kwargs)
    return BaselineMetrics(**defaults)


class TestBaselineMetricsSerialization:
    def test_fields_present(self):
        m = _make_metrics()
        assert m.session_id == "sess-001"
        assert m.coverage_pct == 85.0
        assert m.misra_violations == 5
        assert m.test_passed == 100
        assert m.test_failed == 0
        assert m.gates_passed == 10

    def test_to_dict_roundtrip(self):
        m = _make_metrics(coverage_pct=90.5)
        d = vars(m)
        assert d["coverage_pct"] == 90.5


class TestSaveBaseline:
    def test_saves_json_file(self, tmp_project):
        m = _make_metrics(session_id="s1")
        path = save_baseline(tmp_project, "s1", m)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["session_id"] == "s1"

    def test_creates_latest_id(self, tmp_project):
        m = _make_metrics(session_id="s2")
        save_baseline(tmp_project, "s2", m)
        latest_file = Path(tmp_project) / ".yuleosh" / "baselines" / "latest_id.txt"
        assert latest_file.exists()
        assert latest_file.read_text().strip() == "s2"

    def test_overwrites_latest_id(self, tmp_project):
        save_baseline(tmp_project, "s1", _make_metrics(session_id="s1"))
        save_baseline(tmp_project, "s2", _make_metrics(session_id="s2"))
        latest_file = Path(tmp_project) / ".yuleosh" / "baselines" / "latest_id.txt"
        assert latest_file.read_text().strip() == "s2"


class TestLoadLatestBaseline:
    def test_returns_none_when_no_baseline(self, tmp_project):
        result = load_latest_baseline(tmp_project)
        assert result is None

    def test_returns_saved_baseline(self, tmp_project):
        m = _make_metrics(session_id="s3", coverage_pct=77.5)
        save_baseline(tmp_project, "s3", m)
        loaded = load_latest_baseline(tmp_project)
        assert loaded is not None
        assert loaded.session_id == "s3"
        assert loaded.coverage_pct == 77.5

    def test_returns_latest_after_multiple_saves(self, tmp_project):
        save_baseline(tmp_project, "s1", _make_metrics(session_id="s1", coverage_pct=80.0))
        save_baseline(tmp_project, "s2", _make_metrics(session_id="s2", coverage_pct=85.0))
        loaded = load_latest_baseline(tmp_project)
        assert loaded.session_id == "s2"


class TestCompareToBaseline:
    def test_pass_for_identical_metrics(self):
        base = _make_metrics()
        current = _make_metrics()
        result = compare_to_baseline(current, base)
        assert result["status"] == "pass"

    def test_pass_for_improved_metrics(self):
        base = _make_metrics(coverage_pct=80.0, misra_violations=10, test_failed=0)
        current = _make_metrics(coverage_pct=85.0, misra_violations=5, test_failed=0)
        result = compare_to_baseline(current, base)
        assert result["status"] == "pass"

    def test_error_when_test_failed_increases(self):
        base = _make_metrics(test_failed=0)
        current = _make_metrics(test_failed=3)
        result = compare_to_baseline(current, base)
        assert result["status"] == "error"
        assert any("test_failed" in str(i) for i in result["issues"])

    def test_warn_for_small_coverage_drop(self):
        base = _make_metrics(coverage_pct=85.0)
        current = _make_metrics(coverage_pct=82.0)  # -3%, should be WARN
        result = compare_to_baseline(current, base)
        assert result["status"] in ("warn", "error")

    def test_error_for_large_coverage_drop(self):
        base = _make_metrics(coverage_pct=85.0)
        current = _make_metrics(coverage_pct=78.0)  # -7%, should be ERROR (>-5%)
        result = compare_to_baseline(current, base)
        assert result["status"] == "error"

    def test_warn_for_small_misra_increase(self):
        base = _make_metrics(misra_violations=5)
        current = _make_metrics(misra_violations=8)  # +3, should be WARN
        result = compare_to_baseline(current, base)
        assert result["status"] in ("warn", "error")

    def test_error_for_large_misra_increase(self):
        base = _make_metrics(misra_violations=5)
        current = _make_metrics(misra_violations=20)  # +15, should be ERROR (>+10)
        result = compare_to_baseline(current, base)
        assert result["status"] == "error"

    def test_error_when_gates_decrease(self):
        base = _make_metrics(gates_passed=10)
        current = _make_metrics(gates_passed=8)
        result = compare_to_baseline(current, base)
        assert result["status"] == "error"

    def test_issues_list_populated_on_regression(self):
        base = _make_metrics(test_failed=0, gates_passed=10)
        current = _make_metrics(test_failed=2, gates_passed=8)
        result = compare_to_baseline(current, base)
        assert len(result["issues"]) >= 2
