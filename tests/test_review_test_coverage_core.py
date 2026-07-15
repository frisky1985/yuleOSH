# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for review_test_coverage.py — coverage target ≥50%."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Mini PipelineSession backed by a temp dir."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    from yuleosh.pipeline.session import PipelineSession
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\n")
    session = PipelineSession("test-cov-review", str(spec_file))
    session.session_dir = tmp_path / "sessions" / "test-cov-review"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


# ===================================================================
# _find_latest_ci_result
# ===================================================================


class TestFindLatestCiResult:
    def test_no_ci_dir(self, tmp_path):
        """GIVEN no CI directory WHEN finding result THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _find_latest_ci_result
        result = _find_latest_ci_result(tmp_path)
        assert result is None

    def test_finds_latest_json(self, tmp_path):
        """GIVEN CI dir with JSON files WHEN finding latest THEN returns most recent."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _find_latest_ci_result
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        older = ci_dir / "layer1-001.json"
        older.write_text(json.dumps({"timestamp": "2025-01-01", "stages": []}))
        newer = ci_dir / "layer1-002.json"
        newer.write_text(json.dumps({"timestamp": "2025-06-01", "stages": []}))
        result = _find_latest_ci_result(tmp_path)
        assert result is not None
        assert result["timestamp"] == "2025-06-01"

    def test_corrupted_json(self, tmp_path, caplog):
        """GIVEN corrupted JSON file WHEN finding THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _find_latest_ci_result
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "layer1-bad.json").write_text("not json")
        result = _find_latest_ci_result(tmp_path)
        assert result is None


# ===================================================================
# _load_coverage_data
# ===================================================================


class TestLoadCoverageData:
    def test_no_file(self, tmp_path):
        """GIVEN no coverage file WHEN loading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _load_coverage_data
        result = _load_coverage_data(tmp_path)
        assert result is None

    def test_loads_json(self, tmp_path):
        """GIVEN valid coverage.json WHEN loading THEN returns parsed data."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _load_coverage_data
        cov_dir = tmp_path / ".yuleosh" / "reports"
        cov_dir.mkdir(parents=True, exist_ok=True)
        cov_file = cov_dir / "coverage.json"
        cov_file.write_text(json.dumps({"line_rate_percent": 80.0}))
        result = _load_coverage_data(tmp_path)
        assert result is not None
        assert result["line_rate_percent"] == 80.0

    def test_skips_dot_coverage(self, tmp_path):
        """GIVEN .coverage file WHEN loading THEN skips it."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _load_coverage_data
        cov_file = tmp_path / ".coverage"
        cov_file.write_text("some data")
        result = _load_coverage_data(tmp_path)
        assert result is None


# ===================================================================
# _read_coverage_xml
# ===================================================================


class TestReadCoverageXml:
    def test_no_file(self, tmp_path):
        """GIVEN no coverage.xml WHEN reading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _read_coverage_xml
        result = _read_coverage_xml(tmp_path)
        assert result is None

    def test_valid_xml(self, tmp_path):
        """GIVEN valid coverage.xml WHEN reading THEN parses rates."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _read_coverage_xml
        cov_dir = tmp_path / ".yuleosh" / "reports"
        cov_dir.mkdir(parents=True, exist_ok=True)
        xml_file = cov_dir / "coverage.xml"
        xml_file.write_text(
            '<?xml version="1.0"?>\n'
            '<coverage line-rate="0.85" branch-rate="0.70">\n'
            '  <packages>\n'
            '    <package name="src.module" line-rate="0.75">\n'
            '    </package>\n'
            '  </packages>\n'
            '</coverage>\n'
        )
        result = _read_coverage_xml(tmp_path)
        assert result is not None
        assert result["line_rate_percent"] == 85.0
        assert result["branch_rate_percent"] == 70.0
        assert len(result["packages"]) == 1

    def test_bad_xml(self, tmp_path, caplog):
        """GIVEN malformed XML WHEN reading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _read_coverage_xml
        xml_file = tmp_path / "coverage.xml"
        xml_file.write_text("not xml")
        result = _read_coverage_xml(tmp_path)
        assert result is None


# ===================================================================
# _assess_module_risk
# ===================================================================


class TestAssessModuleRisk:
    def test_no_data(self):
        """GIVEN no coverage data WHEN assessing risk THEN returns empty list."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _assess_module_risk
        result = _assess_module_risk(None, None)
        assert result == []

    def test_high_risk_modules(self):
        """GIVEN packages with low coverage WHEN assessing THEN flags high risk."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _assess_module_risk
        coverage = {"packages": [{"name": "src.risky", "line_rate": 0.3}]}
        result = _assess_module_risk({}, coverage)
        assert len(result) == 1
        assert result[0]["risk_level"] == "high"

    def test_critical_risk_from_files(self):
        """GIVEN coverage JSON with files below 30% WHEN assessing THEN flags critical."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _assess_module_risk
        coverage = {"files": {"src/danger.py": {"executed_lines": [1], "missing_lines": [2, 3, 4]}}}
        result = _assess_module_risk(None, coverage)
        assert len(result) == 1
        assert result[0]["risk_level"] == "critical"

    def test_medium_risk(self):
        """GIVEN packages between 50-70% coverage WHEN assessing THEN medium risk."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _assess_module_risk
        coverage = {"packages": [{"name": "src.ok", "line_rate": 0.6}]}
        result = _assess_module_risk(None, coverage)
        assert len(result) == 1
        assert result[0]["risk_level"] == "medium"


# ===================================================================
# _check_test_regression
# ===================================================================


class TestCheckTestRegression:
    def test_no_ci_result(self):
        """GIVEN no CI result WHEN checking regression THEN returns empty list."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _check_test_regression
        result = _check_test_regression(None, None)
        assert result == []

    def test_no_failure_no_regression(self):
        """GIVEN passing tests WHEN checking THEN returns empty."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _check_test_regression
        ci_result = {"stages": [{"name": "unit-tests", "status": "passed"}]}
        result = _check_test_regression(ci_result, None)
        assert result == []

    def test_new_regression_detected(self):
        """GIVEN current failed, prev passed WHEN checking THEN flags regression."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _check_test_regression
        current = {"stages": [{"name": "unit-tests", "status": "failed", "detail": "New failure"}]}
        previous = {"stages": [{"name": "unit-tests", "status": "passed"}]}
        result = _check_test_regression(current, previous)
        assert len(result) == 1
        assert result[0]["is_regression"] is True

    def test_pre_existing_failure(self):
        """GIVEN same failure as previous WHEN checking THEN marks not regression."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _check_test_regression
        current = {"stages": [{"name": "unit-tests", "status": "failed", "detail": "Same error"}]}
        previous = {"stages": [{"name": "unit-tests", "status": "failed", "detail": "Same error"}]}
        result = _check_test_regression(current, previous)
        assert len(result) == 1
        assert result[0]["is_regression"] is False


# ===================================================================
# _read_coverage_thresholds
# ===================================================================


class TestReadCoverageThresholds:
    def test_defaults(self, tmp_path):
        """GIVEN no CI config WHEN reading thresholds THEN returns defaults."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _read_coverage_thresholds
        result = _read_coverage_thresholds(tmp_path)
        assert isinstance(result["line"], (int, float))
        assert isinstance(result["condition"], (int, float))

    def test_with_ci_config_error(self, tmp_path):
        """GIVEN CI config throws exception WHEN reading thresholds THEN returns defaults."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import _read_coverage_thresholds
        with mock.patch("yuleosh.ci.config._get_ci_config",
                        side_effect=Exception("config not available")):
            result = _read_coverage_thresholds(tmp_path)
            assert isinstance(result["line"], (int, float))
            assert isinstance(result["condition"], (int, float))


# ===================================================================
# step_review_test_coverage (main entry)
# ===================================================================


class TestStepReviewTestCoverage:
    def test_basic_invocation(self, tmp_session):
        """GIVEN valid session WHEN step runs THEN returns output path."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import step_review_test_coverage
        result = step_review_test_coverage(tmp_session)
        assert result is not None
        assert str(tmp_session.session_dir / "coverage-review.json") == result

    def test_output_json(self, tmp_session):
        """GIVEN step runs WHEN checking output THEN JSON has expected keys."""
        from yuleosh.pipeline.step_handlers.review_test_coverage import step_review_test_coverage
        step_review_test_coverage(tmp_session)
        review_path = tmp_session.session_dir / "coverage-review.json"
        assert review_path.exists()
        data = json.loads(review_path.read_text())
        assert "session" in data
        assert "reviewer" in data
        assert "status" in data
        assert "summary" in data
        assert "recommendations" in data
        assert data["reviewer"] == "小马"

    def test_with_ci_result(self, tmp_session, tmp_path, monkeypatch):
        """GIVEN CI result exists WHEN step runs THEN includes coverage analysis."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_test_coverage import step_review_test_coverage
        # Create CI result
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        ci_file = ci_dir / "layer1-001.json"
        ci_file.write_text(json.dumps({
            "stages": [{"name": "unit-tests", "status": "passed"}],
            "coverage": {"line_coverage": 85.0, "condition_coverage": 70.0},
        }))
        result = step_review_test_coverage(tmp_session)
        assert result is not None

    def test_with_failures(self, tmp_session, tmp_path, monkeypatch):
        """GIVEN CI result with failures WHEN step runs THEN status is failed."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_test_coverage import step_review_test_coverage
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        ci_file = ci_dir / "layer1-001.json"
        ci_file.write_text(json.dumps({
            "stages": [{"name": "unit-tests", "status": "failed", "detail": "5 tests failed"}],
            "coverage": {"line_coverage": 60.0, "condition_coverage": 40.0},
        }))
        result = step_review_test_coverage(tmp_session)
        data = json.loads(tmp_session.session_dir.joinpath("coverage-review.json").read_text())
        assert data["status"] == "failed"
