"""Deep tests for hardware.integration — HardwareStep, StepResult."""

import pytest
from unittest.mock import MagicMock, patch, mock_open

from yuleosh.hardware.integration import StepResult, HardwareStep, HardwareStepError
from yuleosh.hardware.debugger import DebugReport


class TestStepResult:
    def test_defaults(self):
        r = StepResult()
        assert r.success is False
        assert r.flash_ok is False
        assert r.monitor_ok is False
        assert r.report is None
        assert r.artifacts == {}
        assert r.error is None
        assert r.duration_ms == 0

    def test_to_dict_with_report(self):
        r = StepResult(success=True, report=DebugReport(error="test", severity="error"))
        d = r.to_dict()
        assert d["success"] is True
        assert d["report"]["error"] == "test"
        assert d["report"]["severity"] == "error"

    def test_to_dict_without_report(self):
        r = StepResult(success=False, error="fail")
        d = r.to_dict()
        assert d["report"] is None
        assert d["error"] == "fail"

    def test_summary_success(self):
        r = StepResult(success=True, flash_ok=True, monitor_ok=True, duration_ms=500)
        s = r.summary()
        assert "PASS" in s
        assert "500ms" in s

    def test_summary_failure(self):
        r = StepResult(success=False, error="Flash failed")
        s = r.summary()
        assert "FAIL" in s
        assert "Flash failed" in s

    def test_summary_with_report(self):
        report = DebugReport(error="HardFault", severity="critical", error_type="hardfault")
        r = StepResult(success=True, report=report)
        s = r.summary()
        assert "[CRITICAL]" in s
        assert "hardfault" in s

    def test_str(self):
        r = StepResult(success=True, duration_ms=100)
        assert str(r) == r.summary()


class TestHardwareStepInit:
    def test_init_no_config(self):
        step = HardwareStep()
        assert step.config == {}

    def test_init_with_config(self):
        step = HardwareStep(config={"flasher": "openocd", "port": "/dev/ttyUSB0"})
        assert step.config["flasher"] == "openocd"

    def test_step_key(self):
        assert HardwareStep.step_key == "hardware"

    def test_agent_name(self):
        assert HardwareStep.agent == "HardwareStep"


class TestHardwareStepExecute:
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_no_binary_returns_skipped(self, mock_file, mock_json, mock_deployer, mock_mkdir):
        step = HardwareStep(config={})
        result = step.execute(context={})
        assert result.success is True
        assert result.flash_ok is False
        assert result.report is not None
        assert "skipped" in result.report.error_type

    @patch("yuleosh.hardware.integration.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_flash_success(self, mock_file, mock_json, mock_deployer_cls, mock_mkdir, mock_isfile):
        mock_deployer = MagicMock()
        mock_deployer.flash.return_value = True
        mock_deployer.verify.return_value = True
        mock_deployer.wait_for_output.return_value = True
        mock_deployer.get_log.return_value = ["Boot OK"]
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"error": ""}
        mock_deployer.analyze.return_value = mock_report
        mock_deployer_cls.return_value = mock_deployer

        step = HardwareStep(config={
            "binary_path": "/tmp/firmware.elf",
            "flasher": "openocd",
            "wait_for": "Boot OK",
        })
        result = step.execute(context={})
        assert result.success is True
        assert result.flash_ok is True
        mock_deployer.flash.assert_called_once()

    @patch("yuleosh.hardware.integration.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_flash_retry_then_fail(self, mock_file, mock_json, mock_deployer_cls, mock_mkdir, mock_isfile):
        mock_deployer = MagicMock()
        from yuleosh.hardware.flasher import FlashError
        mock_deployer.flash.side_effect = FlashError("Connection lost")
        mock_deployer_cls.return_value = mock_deployer

        step = HardwareStep(config={
            "binary_path": "/tmp/firmware.elf",
            "flasher": "openocd",
            "max_retries": 1,
            "retry_delay": 0.01,
        })
        result = step.execute(context={})
        assert result.success is False
        assert result.flash_ok is False
        assert "Flash failed" in result.error

    @patch("yuleosh.hardware.integration.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_context_overrides_config(self, mock_file, mock_json, mock_deployer_cls, mock_mkdir, mock_isfile):
        mock_deployer = MagicMock()
        mock_deployer.flash.return_value = True
        mock_deployer.verify.return_value = True
        mock_deployer.wait_for_output.return_value = True
        mock_deployer.get_log.return_value = []
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"error": ""}
        mock_deployer.analyze.return_value = mock_report
        mock_deployer_cls.return_value = mock_deployer

        step = HardwareStep(config={"flasher": "openocd", "port": "/dev/ttyUSB0"})
        result = step.execute(context={
            "binary_path": "/tmp/fw.elf",
            "port": "/dev/ttyS1",
            "wait_for": "Ready",
        })
        # deployer should have been created with context values
        mock_deployer_cls.assert_called_once()
        _, kwargs = mock_deployer_cls.call_args
        assert kwargs.get("port") == "/dev/ttyS1"
        assert result.success is True

    @patch("yuleosh.hardware.integration.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_unexpected_exception(self, mock_file, mock_json, mock_deployer_cls, mock_mkdir, mock_isfile):
        mock_deployer = MagicMock()
        mock_deployer.flash.side_effect = RuntimeError("Unexpected crash")
        mock_deployer_cls.return_value = mock_deployer

        step = HardwareStep(config={"binary_path": "/tmp/fw.elf"})
        result = step.execute(context={})
        assert result.success is False
        assert result.error is not None

    @patch("yuleosh.hardware.integration.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.integration.os.makedirs")
    @patch("yuleosh.hardware.HardwareDeployer")
    @patch("yuleosh.hardware.integration.json.dump")
    @patch("builtins.open", new_callable=mock_open)
    def test_execute_no_wait_for_just_timeout(self, mock_file, mock_json, mock_deployer_cls, mock_mkdir, mock_isfile):
        mock_deployer = MagicMock()
        mock_deployer.flash.return_value = True
        mock_deployer.get_log.return_value = ["some output"]
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"error": ""}
        mock_deployer.analyze.return_value = mock_report
        mock_deployer_cls.return_value = mock_deployer

        step = HardwareStep(config={
            "binary_path": "/tmp/fw.elf",
            "monitor_timeout": 0.01,
        })
        result = step.execute(context={})
        # Without wait_for, monitor just sleeps
        assert result.success is True


class TestHardwareStepUtils:
    def test_check_binary_exists(self):
        with patch("os.path.isfile", return_value=True):
            HardwareStep._check_binary("/tmp/test.elf")  # should not raise

    def test_check_binary_not_exists(self):
        from yuleosh.hardware.flasher import BinaryNotFoundError
        with patch("os.path.isfile", return_value=False):
            with pytest.raises(BinaryNotFoundError):
                HardwareStep._check_binary("/tmp/nope.elf")

    def test_find_artifact_found(self):
        context = {"firmware_path": "/tmp/fw.elf"}
        with patch("os.path.isfile", return_value=True):
            result = HardwareStep._find_artifact(context)
        assert result == "/tmp/fw.elf"

    def test_find_artifact_none(self):
        result = HardwareStep._find_artifact({})
        assert result is None

    def test_find_artifact_not_a_file(self):
        context = {"binary": "/tmp/fw.elf"}
        with patch("os.path.isfile", return_value=False):
            result = HardwareStep._find_artifact(context)
        assert result is None

    def test_write_result(self):
        import os, json, tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = StepResult(success=True, duration_ms=100)
            HardwareStep._write_result(tmpdir, result)
            result_path = os.path.join(tmpdir, "hardware-result.json")
            assert os.path.isfile(result_path)
            with open(result_path) as f:
                data = json.load(f)
            assert data["success"] is True

    def test_write_result_with_report_and_logs_truncated(self):
        import os, json, tempfile
        report = DebugReport(
            raw_logs=[f"line {i}" for i in range(100)]
        )
        result = StepResult(success=True, report=report)
        with tempfile.TemporaryDirectory() as tmpdir:
            HardwareStep._write_result(tmpdir, result)
            result_path = os.path.join(tmpdir, "hardware-result.json")
            with open(result_path) as f:
                data = json.load(f)
            assert "total lines" in data["report"]["raw_logs"][-1]


class TestHardwareStepError:
    def test_error_is_runtime_error(self):
        assert issubclass(HardwareStepError, RuntimeError)

    def test_error_can_be_raised(self):
        with pytest.raises(HardwareStepError):
            raise HardwareStepError("test error")
