#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for cross/ and hardware/ modules (Phase 2.5)."""

import os
import tempfile
import pytest


# ══════════════════════════════════════════════════════════════════════
# CROSS: serial_monitor
# ══════════════════════════════════════════════════════════════════════

class TestCrossSerialMonitor:
    def test_init(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        sm = SerialMonitor("COM1", baud=9600, timeout=2.0)
        assert sm.port == "COM1" and sm.baud == 9600

    def test_captured_log_empty(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        assert SerialMonitor("COM1").captured_log == ""

    def test_is_open_false(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        assert SerialMonitor("COM1").is_open is False

    def test_close_no_port(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        SerialMonitor("COM1").close()

    def test_assert_text_present_empty(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        assert SerialMonitor("COM1").assert_text_present("x") is False

    def test_clear(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        SerialMonitor("COM1").clear()

    def test_wait_silent(self):
        from yuleosh.cross.serial_monitor import SerialMonitor
        assert SerialMonitor("COM1").wait_silent(duration=0.01) is True


class TestCrossPipeSerialMonitor:
    def test_init(self):
        from yuleosh.cross.serial_monitor import PipeSerialMonitor
        import io
        sm = PipeSerialMonitor(io.StringIO(), timeout=5.0)
        assert sm._timeout == 5.0

    def test_captured_log_empty(self):
        from yuleosh.cross.serial_monitor import PipeSerialMonitor
        import io
        assert PipeSerialMonitor(io.StringIO()).captured_log == ""

    def test_close(self):
        from yuleosh.cross.serial_monitor import PipeSerialMonitor
        import io
        PipeSerialMonitor(io.StringIO()).close()


# ══════════════════════════════════════════════════════════════════════
# CROSS: sil_runner
# ══════════════════════════════════════════════════════════════════════

class TestCrossSilRunner:
    def test_parse_qemu_version(self):
        from yuleosh.cross.sil_runner import parse_qemu_version
        assert parse_qemu_version("QEMU emulator version 7.2.0") == (7, 2, 0)

    def test_parse_qemu_version_invalid_raises(self):
        from yuleosh.cross.sil_runner import parse_qemu_version
        with pytest.raises(RuntimeError):
            parse_qemu_version("")


# ══════════════════════════════════════════════════════════════════════
# CROSS: target_config
# ══════════════════════════════════════════════════════════════════════

class TestCrossTargetConfig:
    def _make(self, **kw):
        from yuleosh.cross.target_config import TargetConfig
        d = dict(name="t", mcu="cortex-m4", arch="arm",
                 qemu_machine="mb", qemu_cpu="cortex-m4", qemu_serial="stdio")
        d.update(kw)
        return TargetConfig(**d)

    def test_is_arm_true(self):
        assert self._make(arch="arm").is_arm is True

    def test_is_arm_false(self):
        assert self._make(arch="riscv").is_arm is False

    def test_is_riscv_true(self):
        assert self._make(arch="riscv").is_riscv is True

    def test_build_qemu_cmd(self):
        tc = self._make(qemu_machine="lm3s6965evb", qemu_cpu="cortex-m3",
                        elf="test.elf")
        assert "qemu-system-arm" in " ".join(tc.build_qemu_cmd())

    def test_repr(self):
        r = repr(self._make(name="test-arm"))
        assert "test-arm" in r

    def test_pop_key_exists(self):
        from yuleosh.cross.target_config import _pop
        d = {"k": "v"}
        assert _pop(d, "k", "ctx") == "v"
        assert "k" not in d

    def test_pop_key_missing(self):
        from yuleosh.cross.target_config import _pop
        with pytest.raises(ValueError):
            _pop({}, "miss", "ctx")



    def test_discover_targets_empty(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as d:
            assert isinstance(discover_targets(base_dir=d), dict)


# ══════════════════════════════════════════════════════════════════════
# HARDWARE: HardwareDeployer
# ══════════════════════════════════════════════════════════════════════

class TestHWDeployer:
    def test_init_default(self):
        from yuleosh.hardware import HardwareDeployer
        d = HardwareDeployer()
        assert "OpenOCDFlasher" in d._flasher.__class__.__name__

    def test_init_unknown(self):
        from yuleosh.hardware import HardwareDeployer
        with pytest.raises(ValueError, match="Unknown flasher"):
            HardwareDeployer(flasher="unknown")

    def test_init_jlink(self):
        from yuleosh.hardware import HardwareDeployer
        assert "JLinkFlasher" in HardwareDeployer(flasher="jlink")._flasher.__class__.__name__

    def test_init_esptool(self):
        from yuleosh.hardware import HardwareDeployer
        assert "ESPToolFlasher" in HardwareDeployer(flasher="esptool")._flasher.__class__.__name__

    def test_flash_missing_raises(self):
        from yuleosh.hardware import HardwareDeployer
        from yuleosh.hardware.flasher import BinaryNotFoundError
        with pytest.raises(BinaryNotFoundError):
            HardwareDeployer().flash("/nope.bin")

    def test_verify_missing_raises(self):
        from yuleosh.hardware import HardwareDeployer
        from yuleosh.hardware.flasher import BinaryNotFoundError
        with pytest.raises(BinaryNotFoundError):
            HardwareDeployer().verify("/nope.bin")

    def test_get_log_no_monitor(self):
        from yuleosh.hardware import HardwareDeployer
        assert HardwareDeployer().get_log() == []

    def test_monitor_no_port(self):
        from yuleosh.hardware import HardwareDeployer
        with pytest.raises(ValueError):
            HardwareDeployer(port=None).monitor()

    def test_last_report_none(self):
        from yuleosh.hardware import HardwareDeployer
        assert HardwareDeployer().last_report is None

    def test_stop_monitor_noop(self):
        from yuleosh.hardware import HardwareDeployer
        HardwareDeployer().stop_monitor()

    def test_repr(self):
        from yuleosh.hardware import HardwareDeployer
        assert "HardwareDeployer" in repr(HardwareDeployer())

    def test_analyze_empty(self):
        from yuleosh.hardware import HardwareDeployer
        assert HardwareDeployer(port="/dev/ttyUSB0").analyze(gdb_output="") is not None


# ══════════════════════════════════════════════════════════════════════
# HARDWARE: debugger
# ══════════════════════════════════════════════════════════════════════

class TestHWDebugger:
    def test_analyze_empty(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert AIDebugger().analyze_log([]) is not None

    def test_analyze_with_crash(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert AIDebugger().analyze_log(["HardFault at 0x8000"]) is not None

    def test_suggest_fix(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert len(AIDebugger().suggest_fix("Null", "int *p=NULL;")) > 0

    def test_check_registers(self):
        from yuleosh.hardware.debugger import AIDebugger
        r = AIDebugger.check_registers("r0 0x0 0\npc 0x8000 0x8000\n")
        assert r["registers"].get("r0") == "0x0"

    def test_check_registers_empty(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert AIDebugger.check_registers("")["registers"] == {}

    def test_extract_stack_trace(self):
        from yuleosh.hardware.debugger import AIDebugger
        t = AIDebugger._extract_stack_trace(["l", "Stack trace:", "#0 0x1234"])
        assert len(t) > 0

    def test_extract_stack_trace_none(self):
        from yuleosh.hardware.debugger import AIDebugger
        assert AIDebugger._extract_stack_trace(["normal"]) == []


class TestHWDebugReport:
    def test_defaults(self):
        from yuleosh.hardware.debugger import DebugReport
        r = DebugReport()
        assert r.error == "" and r.severity == "info"

    def test_to_dict(self):
        from yuleosh.hardware.debugger import DebugReport
        d = DebugReport(error="E1", error_type="hardfault").to_dict()
        assert d["error_type"] == "hardfault"

    def test_summary(self):
        from yuleosh.hardware.debugger import DebugReport
        s = DebugReport(error="E", error_type="T").summary()
        assert "E" in s

    def test_repr(self):
        from yuleosh.hardware.debugger import DebugReport
        assert "DebugReport" in repr(DebugReport(error="E"))


# ══════════════════════════════════════════════════════════════════════
# HARDWARE: monitor
# ══════════════════════════════════════════════════════════════════════

class TestHWMonitor:
    def test_init(self):
        from yuleosh.hardware.monitor import SerialMonitor
        assert SerialMonitor("/dev/ttyUSB0").port == "/dev/ttyUSB0"

    def test_is_running_false(self):
        from yuleosh.hardware.monitor import SerialMonitor
        assert SerialMonitor("/dev/ttyUSB0").is_running is False

    def test_get_log_empty(self):
        from yuleosh.hardware.monitor import SerialMonitor
        assert SerialMonitor("/dev/ttyUSB0").get_log() == []

    def test_clear_log(self):
        from yuleosh.hardware.monitor import SerialMonitor
        sm = SerialMonitor("/dev/ttyUSB0")
        sm.clear_log()
        assert sm.get_log() == []

    def test_repr(self):
        from yuleosh.hardware.monitor import SerialMonitor
        assert "ttyUSB0" in repr(SerialMonitor("/dev/ttyUSB0"))

    def test_mock_serial(self):
        from yuleosh.hardware.monitor import _MockSerial
        ms = _MockSerial("/dev/ttyUSB0")
        assert ms.is_open is True
        ms.inject("data")
        assert ms.readline() == b"data\n"
        ms.close()
        assert ms.is_open is False


# ══════════════════════════════════════════════════════════════════════
# HARDWARE: flasher
# ══════════════════════════════════════════════════════════════════════

class TestHWOpenOCDFlasher:
    def test_brew(self):
        from yuleosh.hardware.flasher import OpenOCDFlasher
        assert OpenOCDFlasher._brew_package_name() == "openocd"


class TestHWESPToolFlasher:
    def test_brew(self):
        from yuleosh.hardware.flasher import ESPToolFlasher
        assert "esptool" in ESPToolFlasher._brew_package_name().lower()

    def test_check_binary_missing(self):
        from yuleosh.hardware.flasher import ESPToolFlasher, BinaryNotFoundError
        with pytest.raises(BinaryNotFoundError):
            ESPToolFlasher({})._check_binary("/nope.bin")

    def test_check_port_missing(self):
        from yuleosh.hardware.flasher import ESPToolFlasher, HardwareNotFoundError
        with pytest.raises(HardwareNotFoundError):
            ESPToolFlasher({})._check_port("/nonexistent/port")

    def test_repr(self):
        from yuleosh.hardware.flasher import ESPToolFlasher
        assert "ESPToolFlasher" in repr(ESPToolFlasher({}))


# ══════════════════════════════════════════════════════════════════════
# HARDWARE: integration
# ══════════════════════════════════════════════════════════════════════

class TestHWIntegration:
    def test_step_result_default(self):
        from yuleosh.hardware.integration import StepResult
        assert StepResult(success=True).success is True

    def test_step_result_to_dict(self):
        from yuleosh.hardware.integration import StepResult
        assert StepResult(success=False).to_dict()["success"] is False

    def test_step_result_summary_pass(self):
        from yuleosh.hardware.integration import StepResult
        assert "PASS" in StepResult(success=True).summary()

    def test_step_result_summary_fail(self):
        from yuleosh.hardware.integration import StepResult
        s = StepResult(success=False, error="fail").summary()
        assert "FAIL" in s

    def test_step_result_str(self):
        from yuleosh.hardware.integration import StepResult
        assert str(StepResult(success=True)) == StepResult(success=True).summary()

    def test_hardware_step_init(self):
        from yuleosh.hardware.integration import HardwareStep
        step = HardwareStep(config={"flasher": "openocd"})
        assert step.config["flasher"] == "openocd"
