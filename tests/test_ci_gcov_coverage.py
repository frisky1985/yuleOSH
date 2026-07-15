"""Tests for ci/gcov_coverage.py — C/C++ coverage via gcov/lcov."""
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from yuleosh.ci.gcov_coverage import (
    run_gcov_coverage, parse_lcov_output, generate_c_coverage_report,
)


class TestRunGcovCoverage:
    def test_build_dir_not_found(self):
        result = run_gcov_coverage(build_dir="/nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_lcov_not_installed(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run", side_effect=FileNotFoundError("lcov")):
                result = run_gcov_coverage(build_dir=td)
                assert result["success"] is False
                assert "lcov" in result["error"]

    def test_lcov_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run", side_effect=TimeoutError("timeout")):
                result = run_gcov_coverage(build_dir=td)
                assert result["success"] is False

    def test_lcov_success(self):
        with tempfile.TemporaryDirectory() as td:
            # Create a fake coverage.info so the file check passes
            lcov_path = Path(td) / "coverage.info"
            lcov_path.write_text("")
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = run_gcov_coverage(build_dir=td)
                assert result["success"] is True


class TestParseLcovOutput:
    def test_file_not_found(self):
        result = parse_lcov_output("/nonexistent.info")
        assert result["line_rate"] == 0.0
        assert result["files"] == []

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            lcov.write_text("")
            result = parse_lcov_output(str(lcov))
            assert result["line_rate"] == 0.0

    def test_single_file_full_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            content = [
                "SF:src/main.c",
                "DA:1,1",
                "DA:2,1",
                "DA:3,1",
                "FNF:1",
                "FNH:1",
                "BRF:0",
                "BRH:0",
                "end_of_record",
            ]
            lcov.write_text("\n".join(content) + "\n")
            result = parse_lcov_output(str(lcov))
            assert result["line_rate"] == 1.0
            assert len(result["files"]) == 1
            assert result["files"][0]["line_rate"] == 1.0

    def test_single_file_partial_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            content = [
                "SF:src/main.c",
                "DA:1,1",
                "DA:2,0",
                "DA:3,1",
                "DA:4,0",
                "FNF:2",
                "FNH:1",
                "BRF:2",
                "BRH:1",
                "end_of_record",
            ]
            lcov.write_text("\n".join(content) + "\n")
            result = parse_lcov_output(str(lcov))
            assert result["line_rate"] == 0.5  # 2/4
            assert result["branch_rate"] == 0.5  # 1/2

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            content = [
                "SF:src/a.c",
                "DA:1,1",
                "FNF:0",
                "FNH:0",
                "BRF:0",
                "BRH:0",
                "end_of_record",
                "SF:src/b.c",
                "DA:1,1",
                "DA:2,1",
                "FNF:0",
                "FNH:0",
                "BRF:0",
                "BRH:0",
                "end_of_record",
            ]
            lcov.write_text("\n".join(content) + "\n")
            result = parse_lcov_output(str(lcov))
            assert len(result["files"]) == 2
            assert result["totals"]["lines"]["found"] == 3
            assert result["totals"]["lines"]["hit"] == 3

    def test_zero_lines(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            content = [
                "SF:src/empty.c",
                "FNF:0",
                "FNH:0",
                "BRF:0",
                "BRH:0",
                "end_of_record",
            ]
            lcov.write_text("\n".join(content) + "\n")
            result = parse_lcov_output(str(lcov))
            assert result["line_rate"] == 0.0

    def test_with_branches(self):
        with tempfile.TemporaryDirectory() as td:
            lcov = Path(td) / "coverage.info"
            content = [
                "SF:src/test.c",
                "DA:1,5",
                "DA:2,3",
                "FNF:1",
                "FNH:1",
                "BRF:4",
                "BRH:3",
                "end_of_record",
            ]
            lcov.write_text("\n".join(content) + "\n")
            result = parse_lcov_output(str(lcov))
            assert result["line_rate"] == 1.0
            assert result["branch_rate"] == 0.75


class TestGenerateCCoverageReport:
    def test_failed_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                       return_value={"success": False, "error": "mock fail"}):
                path = generate_c_coverage_report(build_dir=td)
                assert path == ""

    def test_with_fail_under_gate(self):
        with tempfile.TemporaryDirectory() as td:
            # Create .yuleosh dir so report_dir is found
            yuleosh_dir = Path(td) / ".yuleosh"
            yuleosh_dir.mkdir()
            lcov_path = Path(td) / "coverage.info"
            lcov_path.write_text("")
            with patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                       return_value={"success": True, "lcov_file": str(lcov_path),
                                      "html_dir": ""}):
                with patch("yuleosh.ci.gcov_coverage.parse_lcov_output",
                           return_value={
                               "line_rate": 0.75,
                               "branch_rate": 0.60,
                               "totals": {"lines": {"found": 100, "hit": 75},
                                          "functions": {"found": 10, "hit": 8},
                                          "branches": {"found": 20, "hit": 12}},
                               "files": [{"file": "main.c", "line_rate": 0.75, "branch_rate": 0.6,
                                          "lines": {"found": 100, "hit": 75},
                                          "functions": {"found": 10, "hit": 8}}],
                           }):
                    path = generate_c_coverage_report(build_dir=str(td), fail_under=80.0)
                    result_path = Path(path)
                    assert result_path.exists()
                    report = json.loads(result_path.read_text())
                    assert report["gate_passed"] is False
                    assert report["gate_details"][0]["metric"] == "line_rate"
                    assert report["line_rate"] == 75.0

    def test_pass_fail_under(self):
        with tempfile.TemporaryDirectory() as td:
            yuleosh_dir = Path(td) / ".yuleosh"
            yuleosh_dir.mkdir()
            lcov_path = Path(td) / "coverage.info"
            lcov_path.write_text("")
            with patch("yuleosh.ci.gcov_coverage.run_gcov_coverage",
                       return_value={"success": True, "lcov_file": str(lcov_path),
                                      "html_dir": ""}):
                with patch("yuleosh.ci.gcov_coverage.parse_lcov_output",
                           return_value={
                               "line_rate": 0.85,
                               "branch_rate": 0.70,
                               "totals": {"lines": {"found": 100, "hit": 85},
                                          "functions": {"found": 10, "hit": 8},
                                          "branches": {"found": 20, "hit": 14}},
                               "files": [],
                           }):
                    path = generate_c_coverage_report(build_dir=str(td), fail_under=80.0)
                    report = json.loads(Path(path).read_text())
                    assert report["gate_passed"] is True
