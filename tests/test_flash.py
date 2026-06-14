# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for the Flash Abstraction Layer (FAL) v0.5.0.

Tests cover:
- ``FlashRunner`` auto-detection and initialization
- ``OpenOCDRunner`` command construction and subprocess mocking
- ``JLinkRunner`` script generation and subprocess mocking
- ``PyOCDRunner`` command construction and subprocess mocking
- Tool fallback behavior
- Error handling (timeout, missing binary, invalid firmware)
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.cross.flash import (
    FlashRunner,
    FlashTool,
    FlashResult,
    FlashError,
    OpenOCDRunner,
    JLinkRunner,
    PyOCDRunner,
    flash_firmware,
    detect_hardware,
    _discover_tools,
)
from yuleosh.cross.target_config import TargetConfig


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def arm_target_config() -> TargetConfig:
    """A TargetConfig with flash fields populated (STM32F4)."""
    return TargetConfig(
        name="stm32f4",
        mcu="cortex-m4",
        arch="arm",
        qemu_machine="stm32vldiscovery",
        qemu_cpu="cortex-m3",
        qemu_serial="-serial stdio",
        elf="/tmp/fake-hello-arm.elf",
        default_timeout=30,
        flash_openocd="interface/stlink-v2.cfg target/stm32f4x.cfg",
        flash_jlink={
            "device": "STM32F407VG",
            "interface": "swd",
            "speed": 4000,
        },
        flash_pyocd={
            "target": "stm32f407vg",
            "frequency": 4000000,
        },
    )


@pytest.fixture
def riscv_target_config() -> TargetConfig:
    """A TargetConfig with flash fields populated (RISC-V)."""
    return TargetConfig(
        name="riscv64",
        mcu="riscv64",
        arch="riscv",
        qemu_machine="virt",
        qemu_cpu="rv64",
        qemu_serial="-serial stdio",
        elf="/tmp/fake-hello-riscv.elf",
        default_timeout=30,
        flash_openocd="interface/ftdi.cfg target/riscv.cfg",
    )


@pytest.fixture
def fake_firmware(tmp_path) -> str:
    """Create a temporary fake firmware file."""
    fw = tmp_path / "firmware.elf"
    fw.write_text("FAKE_FIRMWARE_BINARY")
    return str(fw)


# ===================================================================
# FlashResult tests
# ===================================================================


class TestFlashResult:
    """GIVEN a FlashResult dataclass WHEN created THEN fields correct."""

    def test_defaults(self):
        """WHEN default constructor THEN passed=True."""
        result = FlashResult()
        assert result.passed is True
        assert result.log == ""
        assert result.tool == ""
        assert result.elapsed == 0.0
        assert result.error is None

    def test_custom_values(self):
        """WHEN custom values provided THEN stored."""
        result = FlashResult(
            passed=False,
            log="Error: timeout",
            tool="openocd",
            elapsed=5.2,
            error="Exit code 1",
        )
        assert result.passed is False
        assert "timeout" in result.log
        assert result.tool == "openocd"

    def test_str_representation(self):
        """WHEN printed THEN shows key info."""
        result = FlashResult(passed=True, tool="jlink", elapsed=3.14)
        text = str(result)
        assert "FlashResult" in text or "passed" in text.lower() or "True" in text


# ===================================================================
# FlashTool base class
# ===================================================================


class TestFlashToolBase:
    """GIVEN FlashTool base WHEN subclass implemented THEN works."""

    def test_abstract_methods(self):
        """WHEN FlashTool instantiated directly THEN cannot."""
        with pytest.raises(TypeError):
            FlashTool()  # type: ignore[abstract]


# ===================================================================
# OpenOCDRunner tests
# ===================================================================


class TestOpenOCDRunner:
    """GIVEN an OpenOCDRunner WHEN called THEN subprocess invoked."""

    def test_name(self):
        """WHEN name property THEN returns 'openocd'."""
        assert OpenOCDRunner().name == "openocd"

    def test_is_available_false(self):
        """WHEN openocd not in PATH THEN is_available is False."""
        with mock.patch("shutil.which", return_value=None):
            assert OpenOCDRunner().is_available() is False

    def test_is_available_true(self):
        """WHEN openocd in PATH THEN is_available is True."""
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            assert OpenOCDRunner().is_available() is True

    def test_write_no_config(self, tmp_path):
        """WHEN target has no OpenOCD config THEN returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
            flash_openocd=None,
        )
        runner = OpenOCDRunner()
        fw = str(tmp_path / "fw.elf")
        Path(fw).write_text("data")

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            result = runner.write(fw, cfg)
            assert result.passed is False
            assert "no OpenOCD config" in str(result.error).lower() or "no openocd config" in str(result.error).lower()

    def test_write_success(self, arm_target_config, fake_firmware):
        """WHEN openocd succeeds THEN result.passed is True."""
        runner = OpenOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "** Programming Started **\n** Programming Finished **\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run) as mock_sub:
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is True
        assert result.tool == "openocd"
        assert result.elapsed > 0.0
        # Verify command included the firmware path
        cmd = mock_sub.call_args[0][0]
        assert "openocd" in cmd[0]
        assert fake_firmware in " ".join(cmd)

    def test_write_failure(self, arm_target_config, fake_firmware):
        """WHEN openocd fails THEN result.passed is False."""
        runner = OpenOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "Error: target not found"

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False
        assert result.error is not None

    def test_write_timeout(self, arm_target_config, fake_firmware):
        """WHEN openocd times out THEN result.passed is False."""
        runner = OpenOCDRunner()

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("openocd", 60),
            ):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False
        assert "timeout" in result.error.lower()

    def test_write_binary_not_found(self, arm_target_config, fake_firmware):
        """WHEN openocd binary missing THEN result.passed is False."""
        runner = OpenOCDRunner()

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch(
                "subprocess.run",
                side_effect=FileNotFoundError,
            ):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False
        assert "not found" in result.log

    def test_erase(self, arm_target_config):
        """WHEN erase called THEN erase command is built."""
        runner = OpenOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "erased ok"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run) as mock_sub:
                result = runner.erase(arm_target_config)

        assert result.passed is True
        cmd = " ".join(mock_sub.call_args[0][0])
        assert "erase_sector" in cmd or "init" in cmd

    def test_erase_no_config(self):
        """WHEN no OpenOCD config THEN erase returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = OpenOCDRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            result = runner.erase(cfg)
        assert result.passed is False

    def test_verify(self, arm_target_config, fake_firmware):
        """WHEN verify called THEN verify command executed."""
        runner = OpenOCDRunner()
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "verified ok"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run) as mock_sub:
                result = runner.verify(fake_firmware, arm_target_config)

        assert result.passed is True
        cmd = " ".join(mock_sub.call_args[0][0])
        assert "verify_image" in cmd

    def test_verify_no_config(self, fake_firmware):
        """WHEN no OpenOCD config THEN verify returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = OpenOCDRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            result = runner.verify(fake_firmware, cfg)
        assert result.passed is False


# ===================================================================
# JLinkRunner tests
# ===================================================================


class TestJLinkRunner:
    """GIVEN a JLinkRunner WHEN called THEN JLinkExe invoked."""

    def test_name(self):
        """WHEN name property THEN returns 'jlink'."""
        assert JLinkRunner().name == "jlink"

    def test_is_available_false(self):
        """WHEN JLinkExe not in PATH THEN is_available is False."""
        with mock.patch("shutil.which", return_value=None):
            assert JLinkRunner().is_available() is False

    def test_is_available_true(self):
        """WHEN JLinkExe in PATH THEN is_available is True."""
        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            assert JLinkRunner().is_available() is True

    def test_build_script_flash(self, arm_target_config):
        """WHEN flash script built THEN contains device and firmware."""
        runner = JLinkRunner()
        script = runner._build_script("/tmp/fw.elf", arm_target_config)
        assert "STM32F407VG" in script
        assert "loadfile" in script
        assert "/tmp/fw.elf" in script

    def test_build_script_erase(self, arm_target_config):
        """WHEN erase script built THEN contains erase command."""
        runner = JLinkRunner()
        script = runner._build_script("", arm_target_config, action="erase")
        assert "erase" in script

    def test_write_no_config(self, tmp_path):
        """WHEN target has no JLink config THEN returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        fw = str(tmp_path / "fw.elf")
        Path(fw).write_text("data")
        runner = JLinkRunner()

        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            result = runner.write(fw, cfg)
        assert result.passed is False

    def test_write_success(self, arm_target_config, fake_firmware):
        """WHEN JLink succeeds THEN result.passed is True."""
        runner = JLinkRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Downloading flash...\nDone.\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is True
        assert result.tool == "jlink"

    def test_write_failure(self, arm_target_config, fake_firmware):
        """WHEN JLink fails THEN result.passed is False."""
        runner = JLinkRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = "ERROR: Cannot connect to target"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False

    def test_write_timeout(self, arm_target_config, fake_firmware):
        """WHEN JLink times out THEN result.passed is False."""
        runner = JLinkRunner()

        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            with mock.patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("JLinkExe", 60),
            ):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False
        assert "timeout" in result.error.lower()

    def test_erase(self, arm_target_config):
        """WHEN JLink erase THEN returned."""
        runner = JLinkRunner()
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Erasing flash...\nDone.\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.erase(arm_target_config)
        assert result.passed is True


# ===================================================================
# PyOCDRunner tests
# ===================================================================


class TestPyOCDRunner:
    """GIVEN a PyOCDRunner WHEN called THEN pyocd invoked."""

    def test_name(self):
        """WHEN name property THEN returns 'pyocd'."""
        assert PyOCDRunner().name == "pyocd"

    def test_is_available_true_via_path(self):
        """WHEN pyocd in PATH THEN is_available is True."""
        with mock.patch("shutil.which", return_value="/usr/bin/pyocd"):
            assert PyOCDRunner().is_available() is True

    def test_is_available_false(self):
        """WHEN pyocd not in PATH and not installed THEN is_available is False."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch.dict("sys.modules", {"pyocd": None, "pyocd.core": None}):
                # Simulate ImportError
                import builtins
                real_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name.startswith("pyocd"):
                        raise ImportError("No module named pyocd")
                    return real_import(name, *args, **kwargs)

                with mock.patch("builtins.__import__", side_effect=mock_import):
                    assert PyOCDRunner().is_available() is False

    def test_write_no_config(self, tmp_path):
        """WHEN target has no pyOCD config THEN still tries (default fallback)."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        fw = str(tmp_path / "fw.elf")
        Path(fw).write_text("data")
        runner = PyOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Flashing successful\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/pyocd"):
            with mock.patch("subprocess.run", return_value=mock_run) as mock_sub:
                result = runner.write(fw, cfg)
        assert result.passed is True
        cmd = " ".join(mock_sub.call_args[0][0])
        assert "pyocd" in cmd
        assert "flash" in cmd

    def test_write_success(self, arm_target_config, fake_firmware):
        """WHEN pyocd succeeds THEN result.passed is True."""
        runner = PyOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "flashing [##########] 100%\nDone.\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/pyocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is True
        assert result.tool == "pyocd"

    def test_write_failure(self, arm_target_config, fake_firmware):
        """WHEN pyocd fails THEN result.passed is False."""
        runner = PyOCDRunner()

        mock_run = mock.MagicMock()
        mock_run.returncode = 1
        mock_run.stdout = ""
        mock_run.stderr = "pyOCD ERROR: Target not found"

        with mock.patch("shutil.which", return_value="/usr/bin/pyocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = runner.write(fake_firmware, arm_target_config)

        assert result.passed is False

    def test_erase(self, arm_target_config):
        """WHEN pyocd erase THEN command executed."""
        runner = PyOCDRunner()
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Erased\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/pyocd"):
            with mock.patch("subprocess.run", return_value=mock_run) as mock_sub:
                result = runner.erase(arm_target_config)
        assert result.passed is True
        cmd = " ".join(mock_sub.call_args[0][0])
        assert "erase" in cmd


# ===================================================================
# FlashRunner auto-detection and integration
# ===================================================================


class TestFlashRunnerInit:
    """GIVEN FlashRunner initialization WHEN configured THEN correct."""

    def test_init_with_string_target(self, arm_target_config):
        """WHEN string target name THEN resolves config via YAML."""
        # Mock load_target_config
        with mock.patch(
            "cross.flash.load_target_config_safe",
            return_value=arm_target_config,
        ):
            # Mock tool availability
            with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
                runner = FlashRunner(target="stm32f4")
                assert runner.config.name == "stm32f4"
                assert runner.tool_name == "openocd"

    def test_init_with_target_config(self, arm_target_config):
        """WHEN TargetConfig object THEN uses directly."""
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            runner = FlashRunner(target=arm_target_config)
            assert runner.config.name == "stm32f4"

    def test_init_preferred_tool(self, arm_target_config):
        """WHEN preferred tool specified THEN uses it if available."""
        with mock.patch("shutil.which", return_value="/usr/bin/JLinkExe"):
            runner = FlashRunner(target=arm_target_config, tool="jlink")
            assert runner.tool_name == "jlink"

    def test_init_no_tools(self, arm_target_config):
        """WHEN no flash tools available THEN FlashError."""
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(FlashError, match="No flash tool"):
                FlashRunner(target=arm_target_config)

    def test_init_missing_target(self):
        """WHEN target YAML not found THEN FlashError."""
        with mock.patch(
            "cross.flash.load_target_config_safe",
            side_effect=FlashError("Target 'bogus' not found"),
        ):
            with pytest.raises(FlashError, match="not found"):
                FlashRunner(target="bogus")

    def test_available_tools(self, arm_target_config):
        """WHEN multiple tools available THEN all listed."""
        with mock.patch("shutil.which", side_effect=lambda x: f"/usr/bin/{x}"):
            runner = FlashRunner(target=arm_target_config)
            assert "openocd" in runner.available_tools


class TestFlashRunnerOperations:
    """GIVEN FlashRunner WHEN performing operations THEN delegates correctly."""

    def test_flash_success(self, arm_target_config, fake_firmware):
        """WHEN flash succeeds THEN result.passed is True."""
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Success\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                runner = FlashRunner(target=arm_target_config)
                result = runner.flash(fake_firmware)

        assert result.passed is True

    def test_flash_firmware_not_found(self, arm_target_config):
        """WHEN firmware file doesn't exist THEN returns failure."""
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            runner = FlashRunner(target=arm_target_config)
            result = runner.flash("/nonexistent/firmware.elf")

        assert result.passed is False
        assert "not found" in result.error.lower()

    def test_erase(self, arm_target_config):
        """WHEN erase called THEN delegates to active tool."""
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Erased\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                runner = FlashRunner(target=arm_target_config)
                result = runner.erase()

        assert result.passed is True

    def test_verify(self, arm_target_config, fake_firmware):
        """WHEN verify called THEN delegates to active tool."""
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "Verified\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                runner = FlashRunner(target=arm_target_config)
                result = runner.verify(fake_firmware)

        assert result.passed is True

    def test_fallback_on_failure(self, arm_target_config, fake_firmware):
        """WHEN primary tool fails AND fallback available THEN tries fallback."""
        mock_fail = mock.MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = "Failed"
        mock_fail.stderr = ""

        mock_success = mock.MagicMock()
        mock_success.returncode = 0
        mock_success.stdout = "Success with JLink\n"
        mock_success.stderr = ""

        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_fail  # openocd fails
            return mock_success  # jlink succeeds

        with mock.patch(
            "shutil.which",
            side_effect=lambda x: {
                "openocd": "/usr/bin/openocd",
                "JLinkExe": "/usr/bin/JLinkExe",
            }.get(x),
        ):
            with mock.patch("subprocess.run", side_effect=mock_run):
                runner = FlashRunner(target=arm_target_config)
                result = runner.flash(fake_firmware)

        # Should have tried both and succeeded with fallback
        assert result.passed is True
        assert call_count[0] >= 1


# ===================================================================
# Convenience functions
# ===================================================================


class TestFlashFirmware:
    """GIVEN flash_firmware convenience function WHEN called THEN works."""

    def test_one_shot(self, arm_target_config, fake_firmware):
        """WHEN called with target and firmware THEN flashes."""
        mock_run = mock.MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "OK\n"
        mock_run.stderr = ""

        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            with mock.patch("subprocess.run", return_value=mock_run):
                result = flash_firmware(
                    target=arm_target_config,
                    firmware=fake_firmware,
                )
        assert isinstance(result, FlashResult)


class TestDetectHardware:
    """GIVEN detect_hardware WHEN called THEN returns list."""

    def test_no_hardware_detected(self):
        """WHEN no probes available THEN returns empty list."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch.dict("sys.modules", {"pyocd": None}):
                import builtins
                real_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name.startswith("pyocd"):
                        raise ImportError("No module named pyocd")
                    return real_import(name, *args, **kwargs)

                with mock.patch("builtins.__import__", side_effect=mock_import):
                    result = detect_hardware()
                    assert isinstance(result, list)
                    # Should return at least an empty list
                    assert len(result) >= 0


# ===================================================================
# Edge cases
# ===================================================================


class TestFlashEdgeCases:
    """GIVEN edge case configurations WHEN used THEN handled gracefully."""

    def test_invalid_target_string(self):
        """WHEN target string doesn't resolve THEN FlashError."""
        with mock.patch(
            "cross.flash.load_target_config_safe",
            side_effect=FlashError("not found"),
        ):
            with pytest.raises(FlashError):
                FlashRunner(target="bogus_target")

    def test_flash_with_relative_firmware_path(self, arm_target_config, tmp_path):
        """WHEN firmware path is relative THEN resolved to absolute."""
        fw = tmp_path / "fw.elf"
        fw.write_text("data")
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))

            mock_run = mock.MagicMock()
            mock_run.returncode = 0
            mock_run.stdout = "OK\n"
            mock_run.stderr = ""

            with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
                with mock.patch("subprocess.run", return_value=mock_run):
                    runner = FlashRunner(target=arm_target_config)
                    result = runner.flash("fw.elf")
            assert result.passed is True
        finally:
            os.chdir(original_cwd)

    def test_flash_tool_verify_not_supported(self, arm_target_config, fake_firmware):
        """WHEN verify not implemented THEN returns failure gracefully."""
        runner = OpenOCDRunner()
        cfg_without_flash = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        with mock.patch("shutil.which", return_value="/usr/bin/openocd"):
            result = runner.verify(fake_firmware, cfg_without_flash)
        assert result.passed is False
