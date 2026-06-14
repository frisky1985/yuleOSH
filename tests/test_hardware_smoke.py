"""Smoke tests for yuleosh.hardware — debugger, flasher, integration, monitor.

Tests import, class instantiation, and basic method invocation.
No external dependencies — all subprocess/serial calls mocked.
"""

import os
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, PropertyMock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ======================================================================
# yuleosh.hardware.__init__ — HardwareDeployer
# ======================================================================

class TestHardwareDeployer:
    def test_import(self):
        from yuleosh.hardware import HardwareDeployer
        assert HardwareDeployer is not None

    def test_create_default(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="openocd", config={})
        assert deployer is not None
        assert deployer.port is None

    def test_create_with_port(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="openocd", config={},
                                     port="/dev/ttyUSB0", baud=115200)
        assert deployer.port == "/dev/ttyUSB0"

    def test_create_jlink(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="jlink", config={})
        assert deployer is not None

    def test_create_esptool(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="esptool", config={})
        assert deployer is not None

    def test_create_invalid_flasher(self):
        from yuleosh.hardware import HardwareDeployer
        import pytest
        with pytest.raises(ValueError, match="Unknown flasher"):
            HardwareDeployer(flasher="invalid")

    def test_context_manager(self):
        from yuleosh.hardware import HardwareDeployer
        with HardwareDeployer(flasher="openocd", config={}) as deployer:
            assert deployer is not None

    def test_repr(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="openocd", config={})
        assert "HardwareDeployer" in repr(deployer)

    def test_flash(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="openocd", config={})
        mock_flasher = MagicMock()
        mock_flasher.flash.return_value = True
        deployer._flasher = mock_flasher
        result = deployer.flash("firmware.elf")
        assert result is True

    def test_verify(self):
        from yuleosh.hardware import HardwareDeployer
        deployer = HardwareDeployer(flasher="openocd", config={})
        mock_flasher = MagicMock()
        mock_flasher.verify.return_value = True
        deployer._flasher = mock_flasher
        result = deployer.verify("firmware.elf")
        assert result is True


# ======================================================================
# yuleosh.hardware.debugger — DebugReport, AIDebugger
# ======================================================================

class TestDebugger:
    def test_debug_report_import(self):
        from yuleosh.hardware.debugger import DebugReport
        report = DebugReport()
        assert report is not None

    def test_debug_report_with_data(self):
        from yuleosh.hardware.debugger import DebugReport
        report = DebugReport(
            error="Hard fault",
            severity="critical",
            suggestions=["Check stack"],
        )
        assert report.error == "Hard fault"
        assert len(report.suggestions) == 1

    def test_ai_debugger_import(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert AIDebugger is not None

    def test_ai_debugger_create(self):
        from yuleosh.hardware.debugger import AIDebugger
        debugger = AIDebugger()
        assert debugger is not None


# ======================================================================
# yuleosh.hardware.flasher — BaseFlasher, OpenOCDFlasher, JLinkFlasher, ESPToolFlasher
# ======================================================================

class TestFlasher:
    def test_flash_error(self):
        from yuleosh.hardware.flasher import FlashError
        err = FlashError("error")
        assert "error" in str(err)

    def test_binary_not_found(self):
        from yuleosh.hardware.flasher import BinaryNotFoundError
        err = BinaryNotFoundError("binary.elf not found")
        assert "binary" in str(err)

    def test_tool_not_found(self):
        from yuleosh.hardware.flasher import ToolNotFoundError
        err = ToolNotFoundError("openocd not found")
        assert "openocd" in str(err)

    def test_hardware_not_found(self):
        from yuleosh.hardware.flasher import HardwareNotFoundError
        err = HardwareNotFoundError("no st-link")
        assert "st-link" in str(err)

    def test_openocd_flasher_create(self):
        from yuleosh.hardware.flasher import OpenOCDFlasher
        flasher = OpenOCDFlasher(config={})
        assert flasher is not None

    def test_jlink_flasher_create(self):
        from yuleosh.hardware.flasher import JLinkFlasher
        flasher = JLinkFlasher(config={"device": "STM32F407VG"})
        assert flasher is not None

    def test_esptool_flasher_create(self):
        from yuleosh.hardware.flasher import ESPToolFlasher
        flasher = ESPToolFlasher(config={"port": "/dev/ttyUSB0"})
        assert flasher is not None

    def test_base_flasher_abstract(self):
        from yuleosh.hardware.flasher import BaseFlasher
        import pytest
        with pytest.raises(TypeError):
            BaseFlasher()


# ======================================================================
# yuleosh.hardware.integration — StepResult, HardwareStep, HardwareStepError
# ======================================================================

class TestIntegration:
    def test_step_result_default(self):
        from yuleosh.hardware.integration import StepResult
        result = StepResult()
        assert result.success is False  # defaults to False

    def test_step_result_custom(self):
        from yuleosh.hardware.integration import StepResult
        result = StepResult(success=True, flash_ok=True, monitor_ok=True,
                             duration_ms=1000)
        assert result.success is True
        assert result.flash_ok is True

    def test_hardware_step_error(self):
        from yuleosh.hardware.integration import HardwareStepError
        err = HardwareStepError("step failed")
        assert "step" in str(err)

    def test_hardware_step_create(self):
        from yuleosh.hardware.integration import HardwareStep
        step = HardwareStep(config={"flasher": "openocd"})
        assert step.config["flasher"] == "openocd"

    def test_hardware_step_empty_config(self):
        from yuleosh.hardware.integration import HardwareStep
        step = HardwareStep()
        assert step.config == {}

    def test_hardware_step_step_key(self):
        from yuleosh.hardware.integration import HardwareStep
        assert HardwareStep.step_key == "hardware"
        assert HardwareStep.agent == "HardwareStep"


# ======================================================================
# yuleosh.hardware.monitor — SerialMonitor, SerialMonitorError, PortNotFoundError
# ======================================================================

class TestHardwareMonitor:
    def test_serial_monitor_error(self):
        from yuleosh.hardware.monitor import SerialMonitorError
        err = SerialMonitorError("serial error")
        assert "serial" in str(err)

    def test_port_not_found_error(self):
        from yuleosh.hardware.monitor import PortNotFoundError
        err = PortNotFoundError("/dev/ttyUSB0 not found")
        assert "not found" in str(err)

    def test_serial_monitor_create(self):
        from yuleosh.hardware.monitor import SerialMonitor
        with patch("serial.Serial") as mock_serial:
            mock_instance = MagicMock()
            mock_serial.return_value = mock_instance
            monitor = SerialMonitor(port="/dev/ttyUSB0", baud=115200)
            assert monitor.port == "/dev/ttyUSB0"
            monitor.stop()
