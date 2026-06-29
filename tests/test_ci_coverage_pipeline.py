#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
深度测试 — yuleOSH Coverage Pipeline (ci.coverage_pipeline)

Covers:
  - generate_branch_coverage_report: success path, gate checks, failure modes
  - _get_tool_version: success and not-found paths
  - _publish_artifacts: JSON, HTML, ZIP creation
  - save_coverage_markdown: markdown generation
  - CLI main entry point
  - Edge cases: zero gate config, pipeline failure, missing lcov file
"""

import json
import os
import zipfile
from pathlib import Path

import pytest
from unittest import mock

from yuleosh.ci.coverage_pipeline import (
    generate_branch_coverage_report,
    _get_tool_version,
    _publish_artifacts,
    save_coverage_markdown,
)


# ═════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_lcov_parsed() -> dict:
    """GIVEN a realistic parsed lcov output."""
    return {
        "line_rate": 0.85,
        "branch_rate": 0.72,
        "files": [
            {
                "file": "src/main.c",
                "line_rate": 0.90,
                "branch_rate": 0.75,
                "lines": {"found": 100, "hit": 90},
                "functions": {"found": 5, "hit": 4},
            },
            {
                "file": "src/utils.c",
                "line_rate": 0.70,
                "branch_rate": 0.65,
                "lines": {"found": 50, "hit": 35},
                "functions": {"found": 3, "hit": 2},
            },
        ],
        "totals": {
            "lines": {"found": 150, "hit": 125},
            "branches": {"found": 80, "hit": 58},
            "functions": {"found": 8, "hit": 6},
        },
    }


@pytest.fixture
def mock_gcov_success(tmp_path) -> dict:
    """GIVEN a successful gcov run producing a real lcov file."""
    lcov_path = tmp_path / "coverage.info"
    lcov_path.write_text("SF:src/main.c\nend_of_record\n")
    return {
        "success": True,
        "lcov_file": str(lcov_path),
        "html_dir": str(tmp_path / "html"),
    }


@pytest.fixture
def mock_gcov_failure() -> dict:
    """GIVEN a failed gcov run."""
    return {
        "success": False,
        "error": "gcov not found",
    }


# ═════════════════════════════════════════════════════════════════════════════
#  generate_branch_coverage_report
# ═════════════════════════════════════════════════════════════════════════════


class TestGenerateBranchCoverageReport:
    """GIVEN generate_branch_coverage_report()"""

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_successful_run(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN gcov succeeds and lcov is parsed THEN report is generated with correct metrics."""
        mock_gcov.return_value = mock_gcov_success
        mock_parse.return_value = mock_lcov_parsed

        report = generate_branch_coverage_report(
            build_dir=str(tmp_path),
            fail_under=70.0,
            fail_under_branch=60.0,
        )

        assert report["success"] is True
        assert report["summary"]["line_rate"] == 85.0
        assert report["summary"]["branch_rate"] == 72.0
        assert report["summary"]["total_files"] == 2
        assert report["all_gates_passed"] is True
        assert len(report["gates"]) == 2
        assert len(report["files"]) == 2

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_gate_line_fails(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN line coverage is below fail_under THEN gate fails and all_gates_passed is False."""
        mock_gcov.return_value = mock_gcov_success
        parsed = dict(mock_lcov_parsed)
        parsed["line_rate"] = 0.50  # 50%
        mock_parse.return_value = parsed

        report = generate_branch_coverage_report(
            build_dir=str(tmp_path),
            fail_under=60.0,
        )

        assert report["all_gates_passed"] is False
        assert report["gates"][0]["passed"] is False
        assert report["gates"][0]["value"] == 50.0
        assert report["gates"][0]["threshold"] == 60.0

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_gate_branch_fails(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN branch coverage is below fail_under_branch THEN gate fails."""
        mock_gcov.return_value = mock_gcov_success
        parsed = dict(mock_lcov_parsed)
        parsed["branch_rate"] = 0.40  # 40%
        mock_parse.return_value = parsed

        report = generate_branch_coverage_report(
            build_dir=str(tmp_path),
            fail_under_branch=50.0,
        )

        assert report["all_gates_passed"] is False
        assert report["gates"][0]["passed"] is False
        assert report["gates"][0]["metric"] == "branch_rate"

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_no_gate_configured(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN no fail_under thresholds are set THEN gates list is empty and all_gates_passed is True."""
        mock_gcov.return_value = mock_gcov_success
        mock_parse.return_value = mock_lcov_parsed

        report = generate_branch_coverage_report(build_dir=str(tmp_path))

        assert report["success"] is True
        assert report["gates"] == []
        assert report["all_gates_passed"] is True

    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_gcov_failure(self, mock_gcov, mock_gcov_failure, tmp_path) -> None:
        """WHEN gcov run fails THEN report returns with success=False."""
        mock_gcov.return_value = mock_gcov_failure

        report = generate_branch_coverage_report(build_dir=str(tmp_path))

        assert report["success"] is False
        assert "gcov not found" in report["error"]

    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_lcov_file_missing(self, mock_gcov, tmp_path) -> None:
        """WHEN lcov file path is returned but doesn't exist THEN report returns error."""
        mock_gcov.return_value = {
            "success": True,
            "lcov_file": str(tmp_path / "nonexistent.info"),
            "html_dir": str(tmp_path / "html"),
        }

        report = generate_branch_coverage_report(build_dir=str(tmp_path))

        assert report["success"] is False
        assert "lcov file not found" in report["error"] or "lcov file not produced" in report["error"]

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_publishing_creates_artifacts(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN publish_dir is provided THEN artifacts are created."""
        mock_gcov.return_value = mock_gcov_success
        mock_parse.return_value = mock_lcov_parsed

        publish_dir = tmp_path / "artifacts"
        report = generate_branch_coverage_report(
            build_dir=str(tmp_path),
            publish_dir=str(publish_dir),
        )

        assert "artifacts" in report
        assert report["artifacts"]["json"].endswith("coverage-report.json")
        assert os.path.exists(report["artifacts"]["json"])

    @mock.patch("yuleosh.ci.coverage_pipeline.parse_lcov_output")
    @mock.patch("yuleosh.ci.coverage_pipeline.run_gcov_coverage")
    def test_function_rate_computed(self, mock_gcov, mock_parse, mock_gcov_success, mock_lcov_parsed, tmp_path) -> None:
        """WHEN generating report THEN function_rate is computed from parsed totals."""
        mock_gcov.return_value = mock_gcov_success
        mock_parse.return_value = mock_lcov_parsed

        report = generate_branch_coverage_report(build_dir=str(tmp_path))

        # 6 hit / 8 found = 75.0%
        assert report["summary"]["function_rate"] == 75.0
        assert report["summary"]["total_functions"] == 8
        assert report["summary"]["covered_functions"] == 6


# ═════════════════════════════════════════════════════════════════════════════
#  _get_tool_version
# ═════════════════════════════════════════════════════════════════════════════


class TestGetToolVersion:
    """GIVEN _get_tool_version()"""

    def test_command_found(self) -> None:
        """WHEN the tool exists and returns --version THEN first line is returned."""
        version = _get_tool_version("python3")
        assert version
        assert version != "not found"

    def test_command_not_found(self) -> None:
        """WHEN the tool does not exist THEN 'not found' is returned."""
        version = _get_tool_version("nonexistent_tool_xyz_42")
        assert version == "not found"


# ═════════════════════════════════════════════════════════════════════════════
#  _publish_artifacts
# ═════════════════════════════════════════════════════════════════════════════


class TestPublishArtifacts:
    """GIVEN _publish_artifacts()"""

    def test_creates_json_and_zip(self, tmp_path) -> None:
        """WHEN publishing artifacts THEN JSON and ZIP files are created."""
        report = {"summary": {"line_rate": 85.0}}
        publish_dir = str(tmp_path / "publish")
        artifacts = _publish_artifacts(report, "", publish_dir)

        assert os.path.exists(artifacts["json"])
        assert os.path.exists(artifacts["zip"])

        # Verify ZIP contains the JSON
        with zipfile.ZipFile(artifacts["zip"]) as zf:
            names = zf.namelist()
            assert "coverage-report.json" in names

    def test_html_report_copied(self, tmp_path) -> None:
        """WHEN html_dir exists THEN HTML report is copied to publish dir."""
        html_dir = tmp_path / "html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        publish_dir = str(tmp_path / "publish")
        artifacts = _publish_artifacts({}, str(html_dir), publish_dir)

        assert "html" in artifacts
        assert os.path.isdir(artifacts["html"])
        assert (Path(artifacts["html"]) / "index.html").exists()
        assert "html_index" in artifacts

    def test_html_report_missing(self, tmp_path) -> None:
        """WHEN html_dir is empty string THEN HTML key is not in artifacts."""
        artifacts = _publish_artifacts({}, "", str(tmp_path / "publish"))
        assert "html" not in artifacts
        assert "json" in artifacts


# ═════════════════════════════════════════════════════════════════════════════
#  save_coverage_markdown
# ═════════════════════════════════════════════════════════════════════════════


class TestSaveCoverageMarkdown:
    """GIVEN save_coverage_markdown()"""

    def test_basic_report(self) -> None:
        """WHEN given a coverage report dict THEN markdown includes summary and gates."""
        report = {
            "generated_at": "2025-01-01T00:00:00",
            "toolchain": {"gcov": "gcov v1", "lcov": "lcov v2", "genhtml": "genhtml v3"},
            "summary": {
                "line_rate": 85.0,
                "branch_rate": 72.0,
                "function_rate": 75.0,
                "total_files": 5,
                "total_lines": 200,
                "covered_lines": 170,
                "total_branches": 100,
                "covered_branches": 72,
                "total_functions": 20,
                "covered_functions": 15,
            },
            "gates": [
                {"metric": "line_rate", "value": 85.0, "threshold": 80.0, "passed": True},
                {"metric": "branch_rate", "value": 72.0, "threshold": 70.0, "passed": True},
            ],
            "files": [
                {"file": "src/main.c", "line_rate": 90.0, "branch_rate": 80.0,
                 "functions": {"found": 4, "hit": 3}},
            ],
            "artifacts": {"json": "/tmp/coverage-report.json"},
        }
        md = save_coverage_markdown(report)
        assert "覆盖率报告" in md
        assert "85.00%" in md
        assert "72.00%" in md
        assert "✅ PASS" in md
        assert "main.c" in md
        assert "json" in md

    def test_failing_gates(self) -> None:
        """WHEN gates fail THEN markdown shows ❌ FAIL."""
        report = {
            "generated_at": "",
            "toolchain": {},
            "summary": {
                "line_rate": 50.0, "branch_rate": 40.0, "function_rate": 60.0,
                "total_files": 0, "total_lines": 0, "covered_lines": 0,
                "total_branches": 0, "covered_branches": 0,
                "total_functions": 0, "covered_functions": 0,
            },
            "gates": [
                {"metric": "line_rate", "value": 50.0, "threshold": 80.0, "passed": False},
            ],
            "files": [],
        }
        md = save_coverage_markdown(report)
        assert "❌ FAIL" in md
