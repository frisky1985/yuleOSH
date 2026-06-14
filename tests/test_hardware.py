#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
test_hardware — 硬件在环模块单元测试

测试覆盖：
  - 刷写器：Mock subprocess 调用，验证命令格式、失败处理、硬件检测
  - 监视器：Mock 串口数据，验证日志捕获、wait_for_string
  - 调试器：规则引擎匹配、寄存器解析
  - 集成：完整的 Flash → Monitor → Analyze 流程
  - 失败重试逻辑
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# 被测试模块
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.hardware import HardwareDeployer
from yuleosh.hardware.flasher import (
    OpenOCDFlasher,
    JLinkFlasher,
    ESPToolFlasher,
    FlashError,
    BinaryNotFoundError,
    ToolNotFoundError,
    HardwareNotFoundError,
)
from yuleosh.hardware.monitor import SerialMonitor, _MockSerial, PortNotFoundError
from yuleosh.hardware.debugger import AIDebugger, DebugReport
from yuleosh.hardware.integration import HardwareStep, StepResult


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def temp_binary():
    """创建临时固件文件。"""
    with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as f:
        f.write(b"\x00\x01\x02\x03")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_bin():
    """创建临时 .bin 文件。"""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"\x00\x01\x02\x03")
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def openocd_config():
    return {
        "interface": "stlink",
        "target": "stm32f4x",
    }


@pytest.fixture
def jlink_config():
    return {
        "device": "STM32F407VG",
        "if": "SWD",
        "speed": 4000,
    }


@pytest.fixture
def esptool_config():
    return {
        "chip": "esp32",
        "baud": 921600,
        "flash_mode": "dio",
        "flash_size": "4MB",
    }


# ===========================================================================
# 工具函数
# ===========================================================================


def _make_mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """创建一个返回 Mock Popen 结果的辅助函数。"""
    def mock_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
    return mock_run


def _patch_subprocess(monkeypatch, returncode=0, stdout="", stderr=""):
    """Patch subprocess.run 返回指定结果。"""
    monkeypatch.setattr(
        subprocess, "run",
        _make_mock_run(returncode, stdout, stderr),
    )


# ===========================================================================
# 1. 刷写器测试
# ===========================================================================


class TestOpenOCDFlasher:
    """OpenOCDFlasher 单元测试。"""

    def test_init_defaults(self):
        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.interface_cfg == "interface/stlink.cfg"
        assert flasher.target_cfg == "target/stm32f4x.cfg"

    def test_init_with_custom_cfg(self):
        flasher = OpenOCDFlasher({
            "interface": "custom",
            "target": "custom",
            "interface_cfg": "my_interface.cfg",
            "target_cfg": "my_target.cfg",
        })
        assert flasher.interface_cfg == "my_interface.cfg"
        assert flasher.target_cfg == "my_target.cfg"

    def test_binary_not_found(self, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/firmware.elf")

    def test_tool_not_found(self, monkeypatch, temp_binary, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        monkeypatch.setattr("shutil.which", lambda x: None)
        with pytest.raises(ToolNotFoundError):
            flasher.flash(temp_binary)

    def test_flash_success(self, monkeypatch, temp_binary, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=0)
        assert flasher.flash(temp_binary) is True

    def test_flash_failure(self, monkeypatch, temp_binary, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")

        def flash_fail_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "--version" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="Error: target not found"
            )

        monkeypatch.setattr(subprocess, "run", flash_fail_run)
        assert flasher.flash(temp_binary) is False

    def test_flash_command_format(self, monkeypatch, temp_binary, openocd_config):
        captured_commands = []

        def capturing_run(cmd, *args, **kwargs):
            captured_commands.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        monkeypatch.setattr(subprocess, "run", capturing_run)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")

        flasher = OpenOCDFlasher(openocd_config)
        flasher.flash(temp_binary)

        # Find the program command (skip detect_cmd)
        flash_cmd = None
        for cmd in captured_commands:
            if "program" in " ".join(cmd):
                flash_cmd = cmd
                break
        assert flash_cmd is not None, f"No flash command in {captured_commands}"
        assert flash_cmd[0] == "openocd"
        assert "-f" in flash_cmd
        assert "interface/stlink.cfg" in flash_cmd
        assert "target/stm32f4x.cfg" in flash_cmd
        assert f"program {temp_binary} verify reset exit" in " ".join(flash_cmd)

    def test_flash_with_extra_args(self, monkeypatch, temp_binary):
        config = {
            "interface": "stlink",
            "target": "stm32f4x",
            "extra_args": ["-c", "adapter speed 1000"],
        }
        flasher = OpenOCDFlasher(config)
        captured_commands = []

        def capturing_run(cmd, *args, **kwargs):
            captured_commands.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        monkeypatch.setattr(subprocess, "run", capturing_run)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")

        flasher.flash(temp_binary)
        # Find the program command
        flash_cmd = None
        for cmd in captured_commands:
            if "program" in " ".join(cmd):
                flash_cmd = cmd
                break
        assert flash_cmd is not None
        cmd_str = " ".join(flash_cmd)
        assert "adapter speed 1000" in cmd_str

    def test_verify(self, monkeypatch, temp_binary, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=0)
        assert flasher.verify(temp_binary) is True

    def test_verify_fail(self, monkeypatch, temp_binary, openocd_config):
        flasher = OpenOCDFlasher(openocd_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=1)
        assert flasher.verify(temp_binary) is False


class TestJLinkFlasher:
    """JLinkFlasher 单元测试。"""

    def test_init(self, jlink_config):
        flasher = JLinkFlasher(jlink_config)
        assert flasher.device == "STM32F407VG"
        assert flasher.interface == "SWD"
        assert flasher.speed == 4000

    def test_binary_not_found(self, jlink_config):
        flasher = JLinkFlasher(jlink_config)
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/firmware.elf")

    def test_flash_success_with_script(self, monkeypatch, temp_binary):
        config = {"device": "STM32F407VG", "script": "flash.jlink"}
        flasher = JLinkFlasher(config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")
        _patch_subprocess(monkeypatch, returncode=0)
        assert flasher.flash(temp_binary) is True

    def test_flash_success_no_script(self, monkeypatch, temp_binary, jlink_config):
        flasher = JLinkFlasher(jlink_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")
        _patch_subprocess(monkeypatch, returncode=0)
        assert flasher.flash(temp_binary) is True

    def test_flash_failure(self, monkeypatch, temp_binary, jlink_config):
        flasher = JLinkFlasher(jlink_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")

        def flash_fail_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "-?" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="JLink connection failed"
            )

        monkeypatch.setattr(subprocess, "run", flash_fail_run)
        assert flasher.flash(temp_binary) is False

    def test_verify_not_supported(self, monkeypatch, temp_binary, jlink_config):
        flasher = JLinkFlasher(jlink_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")
        assert flasher.verify(temp_binary) is False

    def test_verify_with_script(self, monkeypatch, temp_binary):
        config = {"device": "STM32F407VG", "script": "flash.jlink"}
        flasher = JLinkFlasher(config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")
        assert flasher.verify(temp_binary) is False  # Always returns False


class TestESPToolFlasher:
    """ESPToolFlasher 单元测试。"""

    def test_init(self, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        assert flasher.chip == "esp32"
        assert flasher.baud == 921600
        assert flasher.flash_mode == "dio"

    def test_flash_bin_success(self, monkeypatch, temp_bin, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        _patch_subprocess(monkeypatch, returncode=0)

        assert flasher.flash(temp_bin) is True

    def test_flash_elf_warning(self, monkeypatch, temp_binary, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        _patch_subprocess(monkeypatch, returncode=0)

        # .elf 文件会触发警告而非直接刷写
        result = flasher.flash(temp_binary)
        assert result is True

    def test_flash_failure(self, monkeypatch, temp_bin, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        _patch_subprocess(monkeypatch, returncode=1, stderr="A fatal error occurred")

        assert flasher.flash(temp_bin) is False

    def test_binary_not_found(self, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/firmware.bin")

    def test_verify_bin_supported(self, monkeypatch, temp_bin, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(os.path, "exists", lambda p: True)
        _patch_subprocess(monkeypatch, returncode=0)

        assert flasher.verify(temp_bin) is True

    def test_verify_elf_not_supported(self, monkeypatch, temp_binary, esptool_config):
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        assert flasher.verify(temp_binary) is False

    def test_port_detection_macos(self, monkeypatch, temp_bin, esptool_config):
        """macOS 串口检测路径。"""
        flasher = ESPToolFlasher(esptool_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/esptool.py")
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        with pytest.raises(HardwareNotFoundError):
            flasher.flash(temp_bin, port="/dev/ttyUSB0")


# ===========================================================================
# 2. 监视器测试
# ===========================================================================


class TestSerialMonitor:
    """SerialMonitor 单元测试（使用 MockSerial）。"""

    @pytest.fixture
    def monitor(self):
        mon = SerialMonitor("/dev/ttyUSB0", baud=115200)
        # 注入 MockSerial
        mon._serial = _MockSerial("/dev/ttyUSB0")
        return mon

    def test_init(self):
        mon = SerialMonitor("/dev/ttyUSB0", baud=9600)
        assert mon.port == "/dev/ttyUSB0"
        assert mon.baud == 9600
        assert not mon.is_running
        assert mon.get_log() == []

    def test_start_and_stop(self, monitor):
        thread = monitor.start()
        assert monitor.is_running
        assert isinstance(thread, threading.Thread)
        assert thread.name == "SerialMonitor-/dev/ttyUSB0"
        monitor.stop()
        assert not monitor.is_running

    def test_capture_output(self, monitor):
        monitor.start()
        try:
            # 注入测试数据
            monitor._serial.inject("Booting...")
            monitor._serial.inject("Hello from firmware!")
            monitor._serial.inject("Done.")

            time.sleep(0.5)

            logs = monitor.get_log()
            assert "Booting..." in logs
            assert "Hello from firmware!" in logs
            assert "Done." in logs
        finally:
            monitor.stop()

    def test_wait_for_string_found(self, monitor):
        monitor.start()
        try:
            monitor._serial.inject("System Ready")
            assert monitor.wait_for_string("Ready", timeout=5) is True
        finally:
            monitor.stop()

    def test_wait_for_string_timeout(self, monitor):
        monitor.start()
        try:
            # 不注入，直接等待应当超时
            assert monitor.wait_for_string("NeverAppear", timeout=3) is False
        finally:
            monitor.stop()

    def test_wait_for_string_empty_log(self):
        """空日志场景。"""
        mon = SerialMonitor("/dev/ttyUSB0")
        mon._serial = _MockSerial("/dev/ttyUSB0")
        assert mon.wait_for_string("something", timeout=1) is False

    def test_clear_log(self, monitor):
        monitor.start()
        try:
            monitor._serial.inject("data line 1")
            time.sleep(0.3)
            monitor.clear_log()
            assert monitor.get_log() == []
        finally:
            monitor.stop()

    def test_context_manager(self):
        with SerialMonitor("/dev/ttyUSB0") as mon:
            mon._serial = _MockSerial("/dev/ttyUSB0")
            assert mon.is_running
        assert not mon.is_running

    def test_double_start(self, monitor):
        monitor.start()
        thread = monitor.start()  # second start should log warning but return same thread
        assert monitor.is_running
        monitor.stop()

    def test_mock_serial_inject_and_read(self):
        mock_serial = _MockSerial("/dev/ttyUSB0")
        mock_serial.inject("Hello")
        data = mock_serial.readline()
        assert data == b"Hello\n"

    def test_multiple_injections(self):
        mock_serial = _MockSerial("/dev/ttyUSB0")
        for i in range(5):
            mock_serial.inject(f"Line {i}")
        for i in range(5):
            data = mock_serial.readline()
            assert data == f"Line {i}\n".encode("utf-8")

    def test_port_not_found(self, monkeypatch):
        """测试串口不存在时的错误处理。"""
        # 模拟 pyserial import 可用但串口设备不存在
        import builtins
        original_import = builtins.__import__

        class FakeSerial:
            def __init__(self, *args, **kwargs):
                raise FileNotFoundError("No such file: /dev/nonexistent_port_xyz")
            def close(self):
                pass

        def mock_import(name, *args, **kwargs):
            if name == "serial":
                mod = type(sys)("serial")
                mod.Serial = FakeSerial
                return mod
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setattr(os.path, "exists", lambda p: True)

        with pytest.raises(PortNotFoundError):
            SerialMonitor("/dev/nonexistent_port_xyz", 115200).start()


# ===========================================================================
# 3. 调试器测试
# ===========================================================================


class TestDebugReport:
    """DebugReport 单元测试。"""

    def test_empty_report(self):
        report = DebugReport()
        assert report.severity == "info"
        assert report.error_type == "unknown"

    def test_to_dict(self):
        report = DebugReport(
            error="HardFault",
            severity="critical",
            error_type="hardfault",
            suggestions=["Check pointers"],
            matched_rules=["hardfault: HardFault exception"],
        )
        d = report.to_dict()
        assert d["error"] == "HardFault"
        assert d["severity"] == "critical"
        assert d["error_type"] == "hardfault"
        assert d["suggestions"] == ["Check pointers"]

    def test_summary(self):
        report = DebugReport(
            error="Assertion failed: x != NULL",
            severity="critical",
            error_type="assert_fail",
            suggestions=["Check value of x"],
        )
        summary = report.summary()
        assert "CRITICAL" in summary
        assert "assert_fail" in summary
        assert "Check value of x" in summary

    def test_summary_with_registers(self):
        report = DebugReport(
            error="HardFault",
            severity="critical",
            error_type="hardfault",
            registers={"pc": "0x08001234", "lr": "0x08005678"},
        )
        summary = report.summary()
        assert "0x08001234" in summary


class TestAIDebugger:
    """AIDebugger 单元测试。"""

    def test_analyze_clean_log(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Boot OK", "System initialized", "Running"])
        assert report.error == ""
        assert report.severity == "info"

    def test_analyze_hardfault(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Boot OK", "HardFault at 0x08001234"])
        assert report.error_type == "hardfault"
        assert report.severity == "critical"
        assert "HardFault" in report.error
        assert len(report.suggestions) > 0

    def test_analyze_assert_fail(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Assertion failed: x != NULL in main.c:42"])
        assert report.error_type == "assert_fail"
        assert report.severity == "critical"

    def test_analyze_stack_overflow(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["stack overflow detected"])
        assert report.error_type == "stack_overflow"
        assert report.severity == "error"

    def test_analyze_watchdog(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["WDT reset occurred"])
        assert report.error_type == "wdt_reset"
        assert report.severity == "warning"

    def test_analyze_divide_by_zero(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["divide by zero in calc.c"])
        assert report.error_type == "div_zero"
        assert report.severity == "error"

    def test_analyze_default_handler(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Default_Handler called (unhandled interrupt)"])
        assert report.error_type == "fault_isr"
        assert report.severity == "warning"

    def test_analyze_boot_fail(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Failed to boot: SPI init error"])
        assert report.error_type == "boot_fail"
        assert report.severity == "error"

    def test_analyze_timeout(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["I2C timeout waiting for ACK"])
        assert report.error_type == "timeout"
        assert report.severity == "warning"

    def test_analyze_general_error(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Error: Sensor read failed"])
        assert report.error_type == "general_error"
        assert report.severity == "error"

    def test_analyze_no_boot_output(self):
        """空日志或无启动输出的场景。"""
        debugger = AIDebugger()
        report = debugger.analyze_log(["uart noise", "something garbled"])
        # 只有两行且无 Boot/OK 关键字
        assert report.error_type == "no_boot_output"
        assert report.severity == "warning"

    def test_analyze_incomplete_boot(self):
        """有启动消息但无完成信号的场景。"""
        debugger = AIDebugger()
        report = debugger.analyze_log(["Booting system...", "Initializing SPI"])
        assert report.error_type == "incomplete_boot"
        assert report.severity == "warning"

    def test_analyze_multiple_errors_most_severe_wins(self):
        debugger = AIDebugger()
        report = debugger.analyze_log([
            "Error: minor issue",         # general_error (error)
            "HardFault at 0x08001000",    # hardfault (critical)
        ])
        assert report.error_type == "hardfault"
        assert report.severity == "critical"

    def test_analyze_heuristic_scan_empty_log(self):
        """空日志的启发式扫描。"""
        debugger = AIDebugger()
        report = debugger.analyze_log([])
        assert report.error_type == "no_boot_output"
        assert report.severity == "warning"

    def test_suggest_fix_hardfault(self):
        debugger = AIDebugger()
        fix = debugger.suggest_fix("HardFault at 0x08001234", "int *p = NULL; *p = 42;")
        assert "HardFault" in fix
        assert "空指针" in fix or "pointer" in fix or "空指针解引用" in fix

    def test_suggest_fix_unknown(self):
        debugger = AIDebugger()
        fix = debugger.suggest_fix("xyz123-some-novel-bug-without-any-known-pattern", "code")
        assert "无法自动识别" in fix or "unknown" in fix.lower()

    def test_check_registers(self):
        gdb_output = """\
r0             0x0                 0
r1             0x20001000          536879104
pc             0x08001234          134349364
lr             0x08005678          134361720
sp             0x20002000          536887296
xpsr           0x81000000          2164260864
"""
        result = AIDebugger.check_registers(gdb_output)
        assert "registers" in result
        assert result["registers"]["r0"] == "0x0"
        assert result["registers"]["pc"] == "0x08001234"
        assert result["registers"]["sp"] == "0x20002000"
        assert len(result["suspicious"]) >= 0

    def test_check_registers_pc_zero(self):
        gdb_output = """\
pc             0x0                 0
sp             0x20001000          536895488
"""
        result = AIDebugger.check_registers(gdb_output)
        suspicious = result["suspicious"]
        assert any("pc=0x0" in s for s in suspicious)

    def test_check_registers_sp_low(self):
        gdb_output = """\
pc             0x08001000          134350848
sp             0x10000000          268435456
"""
        result = AIDebugger.check_registers(gdb_output)
        suspicious = result["suspicious"]
        assert any("SP" in s and "SRAM" in s for s in suspicious)

    def test_extract_stack_trace(self):
        logs = [
            "Boot OK",
            "HardFault exception",
            "#0  hard_fault_handler (cfsr=0x00020000)",
            "#1  <signal handler called>",
            "#2  main (main.c:42)",
        ]
        debugger = AIDebugger()
        report = debugger.analyze_log(logs)
        assert len(report.stack_trace) > 0


# ===========================================================================
# 4. 集成测试 — HardwareDeployer
# ===========================================================================


class TestHardwareDeployer:
    """HardwareDeployer 集成测试。"""

    def test_init_defaults(self):
        deployer = HardwareDeployer()
        assert deployer._flasher.__class__.__name__ == "OpenOCDFlasher"

    def test_init_with_jlink(self):
        deployer = HardwareDeployer(flasher="jlink", config={"device": "STM32F407VG"})
        assert deployer._flasher.__class__.__name__ == "JLinkFlasher"

    def test_init_with_esptool(self):
        deployer = HardwareDeployer(flasher="esptool", config={"chip": "esp32"})
        assert deployer._flasher.__class__.__name__ == "ESPToolFlasher"

    def test_init_invalid_flasher(self):
        with pytest.raises(ValueError):
            HardwareDeployer(flasher="unknown")

    def test_flash_success(self, monkeypatch, temp_binary):
        deployer = HardwareDeployer(flasher="openocd", config={"interface": "stlink", "target": "stm32f4x"})
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=0)
        assert deployer.flash(temp_binary) is True

    def test_flash_failure(self, monkeypatch, temp_binary):
        deployer = HardwareDeployer(flasher="openocd", config={"interface": "stlink", "target": "stm32f4x"})
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")

        def flash_fail_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "--version" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", flash_fail_run)
        assert deployer.flash(temp_binary) is False

    def test_monitor_and_analyze(self, monkeypatch):
        deployer = HardwareDeployer()
        deployer._flasher._serial = None  # avoid real hardware check

        # 模拟串口
        mock_serial = _MockSerial("/dev/ttyUSB0")
        deployer._monitor = SerialMonitor("/dev/ttyUSB0")
        deployer._monitor._serial = mock_serial
        deployer._monitor.start()

        try:
            mock_serial.inject("Booting...")
            mock_serial.inject("HardFault at 0x08001234")
            time.sleep(0.3)

            # 再注入几行以便 wait_for 能找到
            mock_serial.inject("HardFault at 0x08001234")
            time.sleep(0.3)

            # 分析日志
            report = deployer.analyze()
            assert report.error_type == "hardfault"
            assert report.severity == "critical"
            assert "HardFault" in report.error
        finally:
            deployer.stop_monitor()

    def test_suggest_fix(self):
        deployer = HardwareDeployer()
        fix = deployer.suggest_fix("HardFault", "int *p = NULL; *p = 42;")
        assert fix is not None
        assert len(fix) > 0

    def test_context_manager(self, monkeypatch):
        with HardwareDeployer() as deployer:
            mon = SerialMonitor("/dev/ttyUSB0")
            mon._serial = _MockSerial("/dev/ttyUSB0")
            mon.start()
            deployer._monitor = mon
            deployer._monitor_running = True
            assert mon.is_running
        # On exit via __exit__, monitor should stop
        assert not deployer._monitor.is_running

    def test_repr(self, monkeypatch):
        deployer = HardwareDeployer(flasher="openocd", config={}, port="/dev/ttyUSB0")
        r = repr(deployer)
        assert "OpenOCDFlasher" in r
        assert "/dev/ttyUSB0" in r


# ===========================================================================
# 5. 集成测试 — HardwareStep (Flash → Monitor → Analyze)
# ===========================================================================


class TestHardwareStep:
    """HardwareStep 完整流程集成测试。"""

    def test_step_skipped_no_binary(self):
        """无二进制文件时跳过。"""
        step = HardwareStep()
        result = step.execute({})
        assert result.success is True
        assert result.flash_ok is False
        assert result.report is not None
        assert result.report.error_type == "skipped"

    def test_step_flash_failure(self, monkeypatch, temp_binary):
        """刷写失败场景。"""
        _patch_subprocess(monkeypatch, returncode=1, stderr="Error: cannot connect")
        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
        })
        result = step.execute({})
        assert result.success is False
        assert result.flash_ok is False
        assert "Flash failed" in (result.error or "")

    def test_step_flash_success_no_monitor_target(self, monkeypatch, temp_binary, tmp_path):
        """刷写成功 + 监视无特定等待目标。"""
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=0)
        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
            "monitor_timeout": 1,  # 1秒超时
            "output_dir": str(tmp_path),
        })
        result = step.execute({})
        assert result.success is True
        assert result.flash_ok is True
        assert result.duration_ms > 0

    def test_step_flash_with_retries_exhausted(self, monkeypatch, temp_binary):
        """刷写重试耗尽。"""
        _patch_subprocess(monkeypatch, returncode=1, stderr="Error: timeout")
        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
            "max_retries": 2,
            "retry_delay": 0.1,
        })
        result = step.execute({})
        assert result.success is False
        assert result.flash_ok is False

    def test_step_retry_success_on_second_attempt(self, monkeypatch, temp_binary):
        """第一次失败，重试成功。"""
        flash_attempt_count = [0]

        def retry_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            if "--version" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            if "program" in cmd_str and "reset" in cmd_str:
                # Flash command (has "reset" for flash, verify doesn't)
                flash_attempt_count[0] += 1
                if flash_attempt_count[0] == 1:
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=1, stdout="", stderr="temporary failure"
                )
            # Verify command or successful flash
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", retry_run)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")

        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
            "monitor_timeout": 1,
            "max_retries": 2,
            "retry_delay": 0.1,
        })
        result = step.execute({})
        assert result.success is True
        assert result.flash_ok is True
        assert flash_attempt_count[0] == 2

    def test_step_binary_not_found(self):
        step = HardwareStep(config={
            "binary_path": "/nonexistent/file.elf",
        })
        result = step.execute({})
        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_step_result_summary_format(self):
        result = StepResult(
            success=True,
            flash_ok=True,
            monitor_ok=True,
            report=DebugReport(error="Boot OK", severity="info", error_type="normal"),
            duration_ms=1234,
        )
        summary = result.summary()
        assert "PASS" in summary
        assert "1234ms" in summary
        assert "✅" in summary

    def test_step_result_failure_summary(self):
        result = StepResult(
            success=False,
            flash_ok=False,
            error="Flash failed: timeout",
            duration_ms=5678,
        )
        summary = result.summary()
        assert "FAIL" in summary
        assert "5678ms" in summary

    def test_step_result_to_dict(self, tmp_path):
        result = StepResult(
            success=True,
            flash_ok=True,
            report=DebugReport(error="OK", severity="info", error_type="normal"),
            duration_ms=100,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["flash_ok"] is True
        assert d["report"]["error"] == "OK"
        assert d["report"]["severity"] == "info"


# ===========================================================================
# 6. 边界情况测试
# ===========================================================================


class TestFlasherEdgeCases:
    """刷写器边界情况。"""

    def test_empty_config(self):
        """空配置不应崩溃。"""
        flasher = OpenOCDFlasher({})
        assert flasher.interface_cfg == "interface/.cfg"
        assert flasher.target_cfg == "target/.cfg"

    def test_binary_empty_file(self, monkeypatch):
        """空文件不应导致崩溃。"""
        with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as f:
            path = f.name

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        # 创建模拟命令会调用
        with mock.patch.object(flasher, "_do_flash", return_value=True):
            assert flasher.flash(path) is True

        os.unlink(path)

    def test_flash_timeout(self, monkeypatch, temp_binary):
        """子进程超时场景。"""
        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})

        def timeout_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="openocd", timeout=10)

        monkeypatch.setattr(subprocess, "run", timeout_run)

        with pytest.raises(FlashError, match="timed out"):
            flasher._run(["openocd", "-c", "exit"], timeout=10)

    def test_flash_oserror(self, monkeypatch, temp_binary):
        """子进程 OSError 场景。"""
        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})

        def oserror_run(*args, **kwargs):
            raise OSError("Cannot allocate memory")

        monkeypatch.setattr(subprocess, "run", oserror_run)

        with pytest.raises(FlashError, match="Failed to execute"):
            flasher._run(["openocd", "-c", "exit"])

    def test_jlink_flash_oserror(self, monkeypatch, temp_binary, jlink_config):
        """JLink OSError 场景。"""
        flasher = JLinkFlasher(jlink_config)
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/JLinkExe")

        call_count = [0]
        def oserror(cmd, *args, **kwargs):
            call_count[0] += 1
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            # 让 detect_cmd 成功
            if call_count[0] == 1 and "-?" in cmd_str:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            raise OSError("JLinkExe execution failed")

        monkeypatch.setattr(subprocess, "run", oserror)

        with pytest.raises(FlashError, match="Failed to execute"):
            flasher.flash(temp_binary)


class TestMonitorEdgeCases:
    """监视器边界情况。"""

    def test_stop_without_start(self):
        mon = SerialMonitor("/dev/ttyUSB0")
        mon.stop()  # 不应抛异常

    def test_get_log_without_start(self):
        mon = SerialMonitor("/dev/ttyUSB0")
        assert mon.get_log() == []

    def test_clear_log_without_start(self):
        mon = SerialMonitor("/dev/ttyUSB0")
        mon.clear_log()  # 不应抛异常

    def test_wait_for_string_no_data(self):
        """等待无注入数据应超时返回 False。"""
        mon = SerialMonitor("/dev/ttyUSB0")
        mon._serial = _MockSerial("/dev/ttyUSB0")
        # 不 start，直接 wait
        assert mon.wait_for_string("anything", timeout=1) is False

    def test_mock_serial_close(self):
        mock_serial = _MockSerial("/dev/ttyUSB0")
        assert mock_serial.is_open
        mock_serial.close()
        assert not mock_serial.is_open

    def test_mock_serial_read_empty(self):
        mock_serial = _MockSerial("/dev/ttyUSB0")
        data = mock_serial.readline()
        assert data == b""


class TestDebuggerEdgeCases:
    """调试器边界情况。"""

    def test_empty_gdb_output(self):
        result = AIDebugger.check_registers("")
        assert result["registers"] == {}
        assert result["suspicious"] == []

    def test_garbled_gdb_output(self):
        result = AIDebugger.check_registers("some random text\nmore text\n")
        assert result["registers"] == {}

    def test_llm_analysis_not_available(self):
        debugger = AIDebugger()
        fix = debugger.suggest_fix("Error: XYZ", "code")
        # 没有 LLM 也应返回有意义的建议
        assert fix is not None

    def test_llm_analysis_with_mock_client(self):
        class MockLLM:
            def complete(self, prompt):
                return "LLM analysis: Check your pointers."

        debugger = AIDebugger(llm_client=MockLLM())
        fix = debugger.suggest_fix("HardFault", "int *p = NULL;")
        assert "LLM analysis" in fix

    def test_suggest_fix_specific_error_types(self):
        debugger = AIDebugger()
        for error_type, pattern in [
            ("assert_fail", "Assertion failed: x != NULL"),
            ("stack_overflow", "stack overflow"),
            ("wdt_reset", "watchdog reset"),
            ("div_zero", "divide by zero"),
            ("fault_isr", "Default_Handler"),
            ("boot_fail", "Failed to boot"),
            ("timeout", "I2C timeout"),
        ]:
            fix = debugger.suggest_fix(pattern, "code")
            assert fix is not None
            assert "错误原文" in fix or "Error" in fix

    def test_report_defaults(self):
        report = DebugReport()
        assert report.registers == {}
        assert report.stack_trace == []
        assert report.suggestions == []
        assert report.matched_rules == []


class TestIntegrationEdgeCases:
    """集成边界情况。"""

    def test_hardware_step_exception_handling(self, monkeypatch, temp_binary):
        """集成步骤中异常应被捕获并返回错误结果。"""
        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
        })

        def throw_error(*args, **kwargs):
            raise RuntimeError("Unexpected hardware crash")

        monkeypatch.setattr(HardwareDeployer, "flash", throw_error)

        result = step.execute({})
        assert result.success is False
        assert result.error is not None

    def test_step_find_artifact_from_context(self, temp_binary):
        """从 context 查找二进制产物。"""
        step = HardwareStep()
        path = step._find_artifact({"firmware_path": temp_binary})
        assert path == temp_binary

        # 不应找到不存在的 key
        path2 = step._find_artifact({"some_other_key": temp_binary})
        assert path2 is None

        # 不应找到不存在的文件
        path3 = step._find_artifact({"firmware_path": "/nonexistent.elf"})
        assert path3 is None

    def test_step_writes_result_file(self, monkeypatch, temp_binary, tmp_path):
        """步骤执行后应写入结果文件。"""
        monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/openocd")
        _patch_subprocess(monkeypatch, returncode=0)
        step = HardwareStep(config={
            "flasher": "openocd",
            "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
            "binary_path": temp_binary,
            "monitor_timeout": 1,
            "output_dir": str(tmp_path),
        })
        result = step.execute({})
        result_path = tmp_path / "hardware-result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text())
        assert data["success"] is True
        assert data["flash_ok"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
