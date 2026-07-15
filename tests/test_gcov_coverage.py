# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ci/gcov_coverage.py — coverage target ≥60%."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# parse_lcov_output
# ===================================================================


class TestParseLcovOutput:
    def test_file_not_found(self, tmp_path):
        """GIVEN non-existent lcov file WHEN parsing THEN returns default data."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        result = parse_lcov_output(str(tmp_path / "nonexistent.info"))
        assert result["line_rate"] == 0.0
        assert result["files"] == []

    def test_empty_file(self, tmp_path):
        """GIVEN empty lcov file WHEN parsing THEN returns zeros."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        lcov = tmp_path / "coverage.info"
        lcov.write_text("")
        result = parse_lcov_output(str(lcov))
        assert result["line_rate"] == 0.0

    def test_single_file(self, tmp_path):
        """GIVEN lcov with one source file WHEN parsing THEN returns per-file data."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        lcov = tmp_path / "coverage.info"
        lcov.write_text(
            "SF:src/main.c\nDA:1,1\nDA:2,0\nDA:3,1\n"
            "FNF:2\nFNH:1\nBRF:2\nBRH:1\nend_of_record\n"
        )
        result = parse_lcov_output(str(lcov))
        assert len(result["files"]) == 1
        assert result["files"][0]["file"] == "src/main.c"
        assert result["files"][0]["lines"]["found"] == 3
        assert result["files"][0]["lines"]["hit"] == 2
        assert result["line_rate"] == pytest.approx(2 / 3)
        assert result["branch_rate"] == 0.5

    def test_multiple_files(self, tmp_path):
        """GIVEN lcov with multiple source files WHEN parsing THEN returns all."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        lcov = tmp_path / "coverage.info"
        lcov.write_text(
            "SF:a.c\nDA:1,1\nFNF:1\nFNH:1\nend_of_record\n"
            "SF:b.c\nDA:1,0\nFNF:1\nFNH:0\nend_of_record\n"
        )
        result = parse_lcov_output(str(lcov))
        assert len(result["files"]) == 2

    def test_missing_via_regex(self, tmp_path):
        """GIVEN DA line with count 0 WHEN parsing THEN marks as missing."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        lcov = tmp_path / "coverage.info"
        lcov.write_text("SF:test.c\nDA:10,0\nDA:20,3\nend_of_record\n")
        result = parse_lcov_output(str(lcov))
        assert result["files"][0]["lines"]["hit"] == 1
        assert result["files"][0]["lines"]["found"] == 2

    def test_no_totals_with_no_files(self, tmp_path):
        """GIVEN lcov with SF but no DA/FN data WHEN parsing THEN handles gracefully."""
        from yuleosh.ci.gcov_coverage import parse_lcov_output
        lcov = tmp_path / "coverage.info"
        lcov.write_text("SF:test.c\nend_of_record\n")
        result = parse_lcov_output(str(lcov))
        assert len(result["files"]) == 1
        assert result["files"][0]["lines"]["found"] == 0


# ===================================================================
# run_gcov_coverage
# ===================================================================


class TestRunGcovCoverage:
    def test_no_build_dir(self, tmp_path):
        """GIVEN non-existent build dir WHEN running THEN returns error."""
        from yuleosh.ci.gcov_coverage import run_gcov_coverage
        result = run_gcov_coverage(build_dir=str(tmp_path / "nonexistent"))
        assert result["success"] is False
        assert "Build directory not found" in result["error"]

    def test_lcov_not_installed(self, tmp_path):
        """GIVEN no lcov command WHEN running THEN returns error."""
        from yuleosh.ci.gcov_coverage import run_gcov_coverage
        with mock.patch("yuleosh.ci.gcov_coverage.subprocess.run",
                        side_effect=FileNotFoundError("lcov not found")):
            result = run_gcov_coverage(build_dir=str(tmp_path))
            assert result["success"] is False
            assert "not installed" in result["error"]

    def test_lcov_timeout(self, tmp_path):
        """GIVEN lcov times out WHEN running THEN returns timeout error."""
        from yuleosh.ci.gcov_coverage import run_gcov_coverage
        with mock.patch("yuleosh.ci.gcov_coverage.subprocess.run",
                        side_effect=mock.MagicMock(side_effect=Exception("timed out"))):
            with mock.patch("yuleosh.ci.gcov_coverage.Path.is_dir", return_value=True):
                result = run_gcov_coverage(build_dir=str(tmp_path))
                assert result["success"] is False

    def test_successful_run(self, tmp_path):
        """GIVEN lcov succeeds WHEN running THEN returns success."""
        from yuleosh.ci.gcov_coverage import run_gcov_coverage
        mock_run = mock.MagicMock()
        lcov_file = tmp_path / "coverage.info"
        lcov_file.write_text("SF:test.c\nend_of_record\n")
        filtered_file = tmp_path / "coverage-filtered.info"

        def fake_run(args, **kwargs):
            if "--output-file" in str(args):
                idx = args.index("--output-file") + 1
                out = Path(args[idx])
                out.write_text("SF:test.c\nend_of_record\n")
            result = mock.MagicMock()
            result.stdout = ""
            result.stderr = ""
            return result

        with mock.patch("yuleosh.ci.gcov_coverage.subprocess.run", side_effect=fake_run):
            result = run_gcov_coverage(build_dir=str(tmp_path))
            assert result["success"] is True


# ===================================================================
# generate_c_coverage_report
# ===================================================================


class TestGenerateCCoverageReport:
    def test_generation_failure(self, tmp_path):
        """GIVEN lcov failure WHEN generating report THEN returns empty string."""
        from yuleosh.ci.gcov_coverage import generate_c_coverage_report
        with mock.patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                        return_value={"success": False, "error": "lcov failed"}):
            result = generate_c_coverage_report(build_dir=str(tmp_path))
            assert result == ""

    def test_successful_generation(self, tmp_path):
        """GIVEN lcov succeeds WHEN generating report THEN returns JSON path."""
        from yuleosh.ci.gcov_coverage import generate_c_coverage_report
        lcov_file = tmp_path / "coverage.info"
        lcov_file.write_text("SF:a.c\nDA:1,1\nFNF:1\nFNH:1\nend_of_record\n")

        with mock.patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                        return_value={
                            "success": True,
                            "lcov_file": str(lcov_file),
                            "html_dir": str(tmp_path / "html"),
                        }):
            result = generate_c_coverage_report(build_dir=str(tmp_path))
            assert result
            assert result.endswith(".json")

    def test_with_fail_under_gate(self, tmp_path):
        """GIVEN fail_under threshold WHEN generating report THEN includes gate data."""
        from yuleosh.ci.gcov_coverage import generate_c_coverage_report
        lcov_file = tmp_path / "coverage.info"
        lcov_file.write_text("SF:a.c\nDA:1,1\nDA:2,1\nFNF:1\nFNH:1\nend_of_record\n")

        with mock.patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                        return_value={
                            "success": True,
                            "lcov_file": str(lcov_file),
                            "html_dir": "",
                        }):
            path = generate_c_coverage_report(build_dir=str(tmp_path), fail_under=80.0)
            assert path
            with open(path) as f:
                data = json.load(f)
            assert data["gate_passed"] is True
            assert len(data["gate_details"]) == 1

    def test_with_fail_under_branch(self, tmp_path):
        """GIVEN branch fail_under threshold WHEN generating THEN includes branch gate."""
        from yuleosh.ci.gcov_coverage import generate_c_coverage_report
        lcov_file = tmp_path / "coverage.info"
        lcov_file.write_text("SF:a.c\nDA:1,1\nDA:2,0\nFNF:1\nFNH:1\nend_of_record\n")

        with mock.patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                        return_value={
                            "success": True,
                            "lcov_file": str(lcov_file),
                            "html_dir": "",
                        }):
            path = generate_c_coverage_report(
                build_dir=str(tmp_path), fail_under=60.0, fail_under_branch=50.0
            )
            assert path
            with open(path) as f:
                data = json.load(f)
            assert data["total_files"] == 1
            assert data["line_rate"] > 0


# ===================================================================
# CLI main
# ===================================================================


class TestMain:
    def test_cli_entry_main(self):
        """GIVEN main function WHEN called THEN prints failure message."""
        from yuleosh.ci.gcov_coverage import main
        with mock.patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                        return_value=""):
            with mock.patch("argparse.ArgumentParser.parse_args",
                            return_value=mock.MagicMock(
                                build_dir=".", src_dir="src",
                                fail_under=None, fail_under_branch=None,
                            )):
                with pytest.raises(SystemExit) as excinfo:
                    main()
                assert excinfo.value.code == 1
