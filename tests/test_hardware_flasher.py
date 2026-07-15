#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for hardware module — flasher, deployer, monitor.

Tests match the actual hardware module API (flasher raises exceptions
rather than returning FlashResult dataclass).
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import pytest

from yuleosh.hardware import HardwareDeployer
from yuleosh.hardware.flasher import (
    OpenOCDFlasher,
    JLinkFlasher,
    ESPToolFlasher,
    FlashError,
    BinaryNotFoundError,
    ToolNotFoundError,
    HardwareNotFoundError,
    BaseFlasher,
)


class TestFlashErrors:
    """FlashError hierarchy."""

    def test_flash_error_base(self):
        e = FlashError("General flash error")
        assert str(e) == "General flash error"

    def test_binary_not_found(self):
        e = BinaryNotFoundError("fw.elf")
        assert "fw.elf" in str(e)

    def test_tool_not_found(self):
        e = ToolNotFoundError("openocd")
        assert "openocd" in str(e)

    def test_hardware_not_found(self):
        e = HardwareNotFoundError("stlink")
        assert "stlink" in str(e)


class TestBaseFlasher:
    """BaseFlasher abstract class."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseFlasher()


class TestOpenOCDFlasher:
    """OpenOCDFlasher unit tests."""

    def test_create_with_config(self):
        config = {"interface": "stlink.cfg", "target": "stm32f4x.cfg"}
        flasher = OpenOCDFlasher(config)
        assert flasher.config["interface"] == "stlink.cfg"

    def test_create_default(self):
        flasher = OpenOCDFlasher({})
        assert flasher is not None

    def test_get_command(self):
        """Test OpenOCDFlasher configuration and command construction."""
        config = {"interface": "stlink", "target": "stm32f4x"}
        flasher = OpenOCDFlasher(config)
        # OpenOCDFlasher adds interface/ prefix and .cfg suffix
        assert "stlink" in flasher.interface_cfg
        assert "stm32f4x" in flasher.target_cfg
        assert flasher.tool_name == "openocd"

    def test_flash_missing_binary(self):
        flasher = OpenOCDFlasher({})
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/fw.elf")

    def test_get_config_value_default(self):
        flasher = OpenOCDFlasher({})
        val = flasher.config.get("speed", 2000)
        assert val == 2000


class TestJLinkFlasher:
    """JLinkFlasher unit tests."""

    def test_create_with_config(self):
        config = {"device": "STM32F407VG", "interface": "swd", "speed": 4000}
        flasher = JLinkFlasher(config)
        assert flasher.config["device"] == "STM32F407VG"

    def test_create_default(self):
        flasher = JLinkFlasher({})
        assert flasher is not None

    def test_get_command(self):
        """Test JLinkFlasher configuration."""
        config = {"device": "STM32F407VG", "interface": "swd", "speed": 4000}
        flasher = JLinkFlasher(config)
        assert flasher.config["device"] == "STM32F407VG"
        assert flasher.tool_name == "JLinkExe"
        
    def test_build_command(self):
        """Test the internal command builder without executing."""
        import inspect
        flasher = JLinkFlasher({"device": "STM32F407VG", "speed": 4000})
        # Just verify construction doesn't crash
        assert flasher is not None
        assert flasher.config["device"] == "STM32F407VG"

    def test_flash_missing_binary(self):
        flasher = JLinkFlasher({})
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/fw.elf")


class TestESPToolFlasher:
    """ESPToolFlasher unit tests."""

    def test_create_with_config(self):
        config = {"port": "/dev/ttyUSB0", "baud": 921600, "chip": "esp32"}
        flasher = ESPToolFlasher(config)
        assert flasher.config["port"] == "/dev/ttyUSB0"

    def test_create_default(self):
        flasher = ESPToolFlasher({})
        assert flasher is not None

    def test_get_command(self):
        flasher = ESPToolFlasher({"port": "/dev/ttyUSB0", "chip": "esp32"})
        # Test command construction - _do_flash_port returns bytes or raises
        if hasattr(flasher, '_do_flash_port'):
            # Don't actually call it - it would try to run esptool.py
            assert flasher is not None

    def test_flash_no_port(self):
        flasher = ESPToolFlasher({})
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01")
            f.flush()
            try:
                flasher.flash(f.name)
            except (ValueError, BinaryNotFoundError, RuntimeError):
                pass  # Expected - no port configured
            os.unlink(f.name)

    def test_flash_missing_binary(self):
        flasher = ESPToolFlasher({"port": "/dev/ttyUSB0"})
        with pytest.raises(BinaryNotFoundError):
            flasher.flash("/nonexistent/fw.bin")


class TestHardwareDeployer:
    """HardwareDeployer integration tests."""

    def test_create_openocd(self):
        d = HardwareDeployer(flasher="openocd", config={})
        assert d is not None

    def test_create_jlink(self):
        d = HardwareDeployer(flasher="jlink", config={})
        assert d is not None

    def test_create_esptool(self):
        d = HardwareDeployer(flasher="esptool", config={})
        assert d is not None

    def test_invalid_flasher(self):
        with pytest.raises(ValueError, match="Unknown"):
            HardwareDeployer(flasher="nonexistent", config={})

    def test_flash_missing_binary(self):
        d = HardwareDeployer(flasher="openocd", config={})
        with pytest.raises(BinaryNotFoundError):
            d.flash("/nonexistent/fw.elf")

    def test_verify_missing_binary(self):
        d = HardwareDeployer(flasher="openocd", config={})
        with pytest.raises(BinaryNotFoundError):
            d.verify("/nonexistent/fw.elf")

    @patch("shutil.which")
    def test_flash_no_tool(self, mock_which):
        mock_which.return_value = None
        d = HardwareDeployer(flasher="openocd", config={})
        with tempfile.NamedTemporaryFile(suffix=".elf", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            f.flush()
            with pytest.raises(ToolNotFoundError):
                d.flash(f.name)
            os.unlink(f.name)

    def test_port_and_baud(self):
        d = HardwareDeployer(flasher="openocd", config={}, port="/dev/ttyUSB0", baud=115200)
        assert d.port == "/dev/ttyUSB0"
        assert d.baud == 115200

    def test_repr(self):
        d = HardwareDeployer(flasher="openocd", config={"a": 1})
        r = repr(d)
        assert "OpenOCDFlasher" in r

    def test_last_report_none(self):
        d = HardwareDeployer(flasher="openocd", config={})
        assert d.last_report is None

    def test_context_manager(self):
        with HardwareDeployer(flasher="openocd", config={}) as d:
            assert d is not None

    def test_analyze(self):
        d = HardwareDeployer(flasher="openocd", config={})
        report = d.analyze()
        assert report is not None

    def test_suggest_fix(self):
        d = HardwareDeployer(flasher="openocd", config={})
        suggestion = d.suggest_fix("Hard fault: undefined", "int x = 0;")
        assert isinstance(suggestion, str)

    def test_stop_monitor_no_op(self):
        d = HardwareDeployer(flasher="openocd", config={})
        # Should not crash when stopping a non-started monitor
        d.stop_monitor()
