"""Tests for pipeline/step_handlers/fault_inject.py — Fault Injection Stage."""
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from yuleosh.pipeline.step_handlers.fault_inject import (
    FaultInjectStage, FaultInjectReport, FaultInjectTestResult,
    step_fault_injection, SYSTEM_FAULT_TESTS, TASK_FAULT_TESTS,
    COMM_FAULT_TESTS, SENSOR_FAULT_TESTS,
)


class TestFaultInjectTestResult:
    def test_dataclass_defaults(self):
        r = FaultInjectTestResult(test_id="TC-01", name="NullPointer",
                                    category="system", status="PASSED",
                                    expected="PASSED")
        assert r.duration_ms == 0
        assert r.details == ""


class TestFaultInjectReport:
    def test_defaults(self):
        r = FaultInjectReport()
        assert r.total == 0
        assert r.passed == 0
        assert r.failed == 0
        assert r.results == []

    def test_to_dict(self):
        r = FaultInjectReport(timestamp="now", total=5, passed=3,
                               failed=1, skipped=1, build_ok=True,
                               target_connected=False)
        d = r.to_dict()
        assert d["total"] == 5
        assert d["passed"] == 3


class TestFaultConstants:
    def test_system_fault_test_count(self):
        assert len(SYSTEM_FAULT_TESTS) == 9

    def test_task_fault_test_count(self):
        assert len(TASK_FAULT_TESTS) == 15

    def test_comm_fault_test_count(self):
        assert len(COMM_FAULT_TESTS) == 5

    def test_sensor_fault_test_count(self):
        assert len(SENSOR_FAULT_TESTS) == 3


class TestFaultInjectStageInit:
    def test_default_init(self):
        stage = FaultInjectStage()
        assert stage.test_categories == ["system", "task"]

    def test_custom_categories(self):
        stage = FaultInjectStage(test_categories=["system", "task", "comm", "sensor"])
        assert len(stage.test_categories) == 4

    def test_custom_build_dir(self):
        stage = FaultInjectStage(build_dir="/tmp/build")
        assert str(stage.build_dir) == "/tmp/build"


class TestFaultInjectBuildFirmware:
    def test_build_success(self):
        stage = FaultInjectStage()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = stage.build_test_firmware("/tmp/project")
            assert result is True
            assert mock_run.call_count >= 2

    def test_build_cmake_not_found(self):
        stage = FaultInjectStage()
        with patch("subprocess.run", side_effect=FileNotFoundError("cmake not found")):
            result = stage.build_test_firmware("/tmp/project")
            assert result is False

    def test_build_failure(self):
        import subprocess
        stage = FaultInjectStage()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["cmake"], stderr="error msg")
            result = stage.build_test_firmware("/tmp/project")
            assert result is False


class TestFaultInjectConnectTarget:
    def test_serial_port_exists(self):
        with tempfile.TemporaryDirectory() as td:
            port = Path(td) / "ttyUSB0"
            port.write_text("")
            stage = FaultInjectStage(serial_port=str(port), injector_type="serial")
            assert stage.connect_target() is True

    def test_serial_not_found(self):
        stage = FaultInjectStage(serial_port="/nonexistent/port", injector_type="serial")
        assert stage.connect_target() is False

    def test_uds_with_target(self):
        stage = FaultInjectStage(target="com0", injector_type="uds")
        assert stage.connect_target() is True

    def test_uds_no_target(self):
        stage = FaultInjectStage(target=None, injector_type="uds")
        assert stage.connect_target() is False

    def test_unknown_injector(self):
        stage = FaultInjectStage(injector_type="unknown")
        assert stage.connect_target() is False


class TestFaultInjectRunTests:
    def test_run_all_categories(self):
        stage = FaultInjectStage(test_categories=["system", "task", "comm", "sensor"])
        with patch.object(stage, "build_test_firmware", return_value=True):
            with patch.object(stage, "connect_target", return_value=True):
                report = stage.run_tests()
        assert report.total == (9 + 15 + 5 + 3)
        # One system test (TC-06 MPUViolation) has expected='SKIP*' and gets status='SKIP'
        assert report.passed == (9 + 15 + 5 + 3) - 1  # one is SKIP

    def test_run_system_only(self):
        stage = FaultInjectStage(test_categories=["system"])
        with patch.object(stage, "build_test_firmware", return_value=True):
            with patch.object(stage, "connect_target", return_value=True):
                report = stage.run_tests()
        assert report.total == 9

    def test_run_task_only(self):
        stage = FaultInjectStage(test_categories=["task"])
        with patch.object(stage, "build_test_firmware", return_value=True):
            with patch.object(stage, "connect_target", return_value=True):
                report = stage.run_tests()
        assert report.total == 15

    def test_report_summary(self):
        stage = FaultInjectStage(test_categories=["system"])
        with patch.object(stage, "build_test_firmware", return_value=True):
            with patch.object(stage, "connect_target", return_value=True):
                report = stage.run_tests()
        assert "Total:" in report.summary
        assert report.build_ok is True


class TestFaultInjectGenerateReport:
    def test_generates_markdown(self):
        stage = FaultInjectStage()
        report = FaultInjectReport(timestamp="now", total=3, passed=2, failed=1)
        report.results = [
            FaultInjectTestResult("TC-01", "NullPointer", "system", "PASSED", "PASSED"),
            FaultInjectTestResult("TC-02", "DivByZero", "system", "FAILED", "PASSED"),
            FaultInjectTestResult("TF-01", "DKI_Main:NullHandle", "task", "SIMULATED", "PASSED"),
        ]
        with tempfile.TemporaryDirectory() as td:
            path = stage.generate_report(report, str(Path(td) / "report.md"))
            content = Path(path).read_text()
            assert "A66-T" in content
            assert "TC-01" in content
            assert "TF-01" in content

    def test_report_legend(self):
        stage = FaultInjectStage()
        report = FaultInjectReport()
        with tempfile.TemporaryDirectory() as td:
            path = stage.generate_report(report, str(Path(td) / "report.md"))
            content = Path(path).read_text()
            assert "Legend" in content
            assert "SIMULATED" in content


class TestStepFaultInjection:
    def test_step_function(self):
        session = MagicMock()
        session.build_dir = "build"
        session.target_name = None
        session.serial_port = None
        session.fault_inject_categories = ["system"]
        session.session_dir = "/tmp"
        session.artifacts = {}

        with patch.object(FaultInjectStage, "build_test_firmware", return_value=True):
            with patch.object(FaultInjectStage, "connect_target", return_value=True):
                result = step_fault_injection(session)
        assert result is not None
        assert result.endswith("fault-injection-report.md")

    def test_step_defaults(self):
        session = MagicMock()
        session.build_dir = "build"
        session.session_dir = "/tmp"
        session.artifacts = {}

        with patch.object(FaultInjectStage, "build_test_firmware", return_value=True):
            with patch.object(FaultInjectStage, "connect_target", return_value=True):
                result = step_fault_injection(session)
        assert result is not None
