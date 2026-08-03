#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ci/verify_c_coverage_gate.py — C coverage E2E verification (QG-006)."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ===================================================================
# _find_demo_project
# ===================================================================


class TestFindDemoProject:
    """Test finding the demo C project for verification."""

    def test_finds_uart_demo(self, tmp_path):
        """GIVEN project with demos/uart/CMakeLists.txt WHEN finding THEN returns path."""
        from yuleosh.ci.verify_c_coverage_gate import _find_demo_project
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\nproject(demo)\n")
        result = _find_demo_project(tmp_path)
        assert result is not None
        assert str(result) == str(demo_dir)

    def test_fallback_unity(self, tmp_path):
        """GIVEN project without demos but with tests/unity WHEN finding THEN returns unity."""
        from yuleosh.ci.verify_c_coverage_gate import _find_demo_project
        unity_dir = tmp_path / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        result = _find_demo_project(tmp_path)
        assert result is not None
        assert str(result) == str(unity_dir)

    def test_no_demo_project(self, tmp_path):
        """GIVEN project with no demo or unity test dir WHEN finding THEN returns None."""
        from yuleosh.ci.verify_c_coverage_gate import _find_demo_project
        result = _find_demo_project(tmp_path)
        assert result is None


# ===================================================================
# _build_c_demo
# ===================================================================


class TestBuildCDemo:
    """Test building the C demo project."""

    def test_no_c_sources(self, tmp_path):
        """GIVEN demo dir with no .c files WHEN building THEN returns None."""
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        result = _build_c_demo(tmp_path)
        assert result is None

    def test_no_compiler(self, tmp_path):
        """GIVEN no gcc or cc WHEN building THEN returns None."""
        from yuleosh.ci.verify_c_coverage_gate import _build_c_demo
        (tmp_path / "test.c").write_text("int main(void) { return 0; }\n")
        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which", return_value=None):
            result = _build_c_demo(tmp_path)
            assert result is None


# ===================================================================
# _log_p0_alert
# ===================================================================


class TestLogP0Alert:
    """Test P0 alert logging."""

    def test_writes_alert_file(self, tmp_path):
        """GIVEN a P0 alert WHEN logging THEN writes to p0-alerts.jsonl."""
        from yuleosh.ci.verify_c_coverage_gate import _log_p0_alert
        _log_p0_alert(tmp_path, "Test alert", {"key": "value"})
        alert_path = tmp_path / ".yuleosh" / "reports" / "p0-alerts.jsonl"
        assert alert_path.exists()
        content = alert_path.read_text()
        assert "Test alert" in content
        assert "P0" in content
        entry = json.loads(content.strip())
        assert entry["severity"] == "P0"
        assert entry["details"]["key"] == "value"

    def test_creates_report_dir(self, tmp_path):
        """GIVEN no reports dir WHEN logging THEN creates it."""
        from yuleosh.ci.verify_c_coverage_gate import _log_p0_alert
        _log_p0_alert(tmp_path, "Alert")
        assert (tmp_path / ".yuleosh" / "reports").exists()

    def test_appends_multiple(self, tmp_path):
        """GIVEN multiple alerts WHEN logging THEN appends lines."""
        from yuleosh.ci.verify_c_coverage_gate import _log_p0_alert
        _log_p0_alert(tmp_path, "Alert 1")
        _log_p0_alert(tmp_path, "Alert 2")
        alert_path = tmp_path / ".yuleosh" / "reports" / "p0-alerts.jsonl"
        lines = alert_path.read_text().strip().split("\n")
        assert len(lines) == 2


# ===================================================================
# verify_c_coverage_gate
# ===================================================================


class TestVerifyCCoverageGate:
    """Test the main verification pipeline."""

    def test_no_demo_project(self, tmp_path):
        """GIVEN project with no demo WHEN verifying THEN returns report with warnings."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        result = verify_c_coverage_gate(str(tmp_path))
        # success=False because verification didn't complete (no demo project)
        assert result["success"] is False
        assert len(result["warnings"]) > 0
        assert "No demo C project found" in result["warnings"][0]
        assert result["compile_success"] is False

    def test_no_compiler_found(self, tmp_path):
        """GIVEN no compiler WHEN verifying THEN returns compile_success=False."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        # Create a demo dir but no compiler
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\nproject(demo)\n")
        (demo_dir / "main.c").write_text("int main(void) { return 0; }\n")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate.shutil.which", return_value=None):
            result = verify_c_coverage_gate(str(tmp_path))
        assert result["compile_success"] is False

    def test_no_gcda_files(self, tmp_path):
        """GIVEN compilation succeeds but no .gcda WHEN verifying THEN reports 0 gcda files."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        # Create a demo dir with a simple C file
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.10)\nproject(demo)\n"
            "add_executable(demo main.c)\n"
        )
        (demo_dir / "main.c").write_text("int main(void) { return 0; }\n")

        with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo") as mock_build:
            exe_path = tmp_path / "demos" / "uart" / "_build_verify" / "demo"
            exe_path.parent.mkdir(parents=True)
            exe_path.write_text("#!/bin/sh\nexit 0\n")
            exe_path.chmod(0o755)
            mock_build.return_value = exe_path

            with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[]):
                    result = verify_c_coverage_gate(str(tmp_path))

        assert result["compile_success"] is True
        assert result["executable_success"] is True
        assert result["gcda_files_found"] == 0
        assert result["gate_passed"] is None

    def test_with_coverage_data(self, tmp_path):
        """GIVEN full verification pipeline succeeds WHEN verifying THEN returns complete data."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.10)\nproject(demo)\n"
            "add_executable(demo main.c)\n"
        )
        (demo_dir / "main.c").write_text("#include <stdio.h>\nint main(void) { printf(\"hello\"); return 0; }\n")

        exe_path = tmp_path / "demos" / "uart" / "_build_verify" / "demo"
        exe_path.parent.mkdir(parents=True)
        exe_path.write_text("#!/bin/sh\nexit 0\n")
        exe_path.chmod(0o755)

        fake_coverage = {
            "files": [
                {"file": "src/main.c", "line_rate": 0.75},
                {"file": "src/utils.c", "line_rate": 0.50},
            ],
            "totals": {"lines": {"found": 100, "hit": 75}},
            "line_rate": 0.75,
        }

        with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[exe_path]):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage", return_value=fake_coverage):
                        result = verify_c_coverage_gate(str(tmp_path))

        assert result["success"] is True
        assert result["line_rate"] == 75.0
        assert result["gate_passed"] is True
        assert result["gcda_files_found"] == 1

    def test_coverage_below_threshold(self, tmp_path):
        """GIVEN coverage below c_fail_under WHEN verifying THEN gate_passed=False."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.10)\nproject(demo)\n"
            "add_executable(demo main.c)\n"
        )
        (demo_dir / "main.c").write_text("int main(void) { return 0; }\n")

        exe_path = tmp_path / "demos" / "uart" / "_build_verify" / "demo"
        exe_path.parent.mkdir(parents=True)
        exe_path.write_text("#!/bin/sh\nexit 0\n")
        exe_path.chmod(0o755)

        fake_coverage = {
            "files": [
                {"file": "src/main.c", "line_rate": 0.20},
            ],
            "totals": {"lines": {"found": 100, "hit": 20}},
            "line_rate": 0.20,
        }

        with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[exe_path]):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage", return_value=fake_coverage):
                        result = verify_c_coverage_gate(str(tmp_path))

        assert result["success"] is True
        assert result["line_rate"] == 20.0
        assert result["gate_passed"] is False

    def test_writes_report_file(self, tmp_path):
        """GIVEN verification completes WHEN done THEN report JSON is written."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project", return_value=None):
            result = verify_c_coverage_gate(str(tmp_path))
        report_path = tmp_path / ".yuleosh" / "reports" / "c-coverage-gate-verification.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        # Verification ran, but no demo -> success=False
        assert data["success"] is False

    def test_loads_c_fail_under(self, tmp_path):
        """GIVEN ci-config.yaml with custom c_fail_under WHEN verifying THEN uses the value."""
        from yuleosh.ci.verify_c_coverage_gate import _load_c_fail_under, verify_c_coverage_gate
        # Test without config
        assert _load_c_fail_under(tmp_path) == 70
        # Test with mock
        demo_dir = tmp_path / "demos" / "uart"
        demo_dir.mkdir(parents=True)
        (demo_dir / "main.c").write_text("int main(void) { return 0; }\n")
        (demo_dir / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.10)\nproject(demo)\n"
            "add_executable(demo main.c)\n"
        )
        exe_path = tmp_path / "build_verify" / "demo"
        exe_path.parent.mkdir(parents=True)
        exe_path.write_text("#!/bin/sh\nexit 0\n")
        exe_path.chmod(0o755)

        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project", return_value=demo_dir):
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[exe_path]):
                        with mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage", return_value={
                            "files": [{"file": "test.c", "line_rate": 0.0}],
                            "totals": {"lines": {"found": 1, "hit": 0}},
                            "line_rate": 0.0,
                        }):
                            result = verify_c_coverage_gate(str(tmp_path))
        assert result["c_fail_under"] == 70


# ===================================================================
# CLI main
# ===================================================================


class TestMain:
    """Test the CLI entry point by calling verify_c_coverage_gate directly."""

    def test_cli_no_gcda_triggers_p0(self):
        """GIVEN no .gcda data WHEN verify runs THEN p0 alert is written."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project", return_value=mock.MagicMock()):
            exe_path = mock.MagicMock()
            exe_path.parent = mock.MagicMock()
            exe_path.parent.__str__ = mock.MagicMock(return_value="/tmp/build")
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[]):
                        with mock.patch("yuleosh.ci.verify_c_coverage_gate._log_p0_alert") as mock_p0:
                            result = verify_c_coverage_gate("/tmp/proj")
                            assert mock_p0.called
                            assert "No .gcda files" in mock_p0.call_args[0][1]

    def test_cli_gate_failed_output(self):
        """GIVEN coverage below threshold WHEN verify runs THEN gate_passed=False."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project", return_value=mock.MagicMock()):
            exe_path = mock.MagicMock()
            exe_path.parent = mock.MagicMock()
            exe_path.parent.__str__ = mock.MagicMock(return_value="/tmp/build")
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[exe_path]):
                        with mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage",
                                         return_value={"files": [{"file": "main.c", "line_rate": 0.30}],
                                                       "totals": {"lines": {"found": 100, "hit": 30}},
                                                       "line_rate": 0.30}):
                            result = verify_c_coverage_gate("/tmp/proj")
                            assert result["gate_passed"] is False
                            assert result["line_rate"] == 30.0

    def test_cli_success(self):
        """GIVEN coverage above threshold WHEN verify runs THEN gate_passed=True."""
        from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate
        with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_demo_project", return_value=mock.MagicMock()):
            exe_path = mock.MagicMock()
            exe_path.parent = mock.MagicMock()
            exe_path.parent.__str__ = mock.MagicMock(return_value="/tmp/build")
            with mock.patch("yuleosh.ci.verify_c_coverage_gate._build_c_demo", return_value=exe_path):
                with mock.patch("yuleosh.ci.verify_c_coverage_gate._run_demo_executable", return_value=True):
                    with mock.patch("yuleosh.ci.verify_c_coverage_gate._find_gcda_files", return_value=[exe_path]):
                        with mock.patch("yuleosh.ci.verify_c_coverage_gate._parse_gcovr_coverage",
                                         return_value={"files": [{"file": "main.c", "line_rate": 0.85}],
                                                       "totals": {"lines": {"found": 100, "hit": 85}},
                                                       "line_rate": 0.85}):
                            result = verify_c_coverage_gate("/tmp/proj")
                            assert result["gate_passed"] is True
                            assert result["line_rate"] == 85.0
