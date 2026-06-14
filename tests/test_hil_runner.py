# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for the HIL (Hardware-in-the-Loop) Test Runner v0.5.0.

Tests cover:
- ``HilTestRunner`` initialization and configuration
- Full run lifecycle (flash → serial → assert)
- Shortcut methods (flash_and_expect, flash_and_boot)
- Error handling (flash failure, serial timeout, firmware missing)
- Test script execution
"""

import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.cross.hil_runner import (
    HilTestRunner,
    HilTestResult,
    hil_test,
)
from yuleosh.cross.flash import FlashResult, FlashError, FlashRunner
from yuleosh.cross.target_config import TargetConfig
from yuleosh.cross.serial_monitor import SerialMonitorTimeout


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def arm_target_config() -> TargetConfig:
    """A TargetConfig with flash fields populated."""
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
def fake_firmware(tmp_path) -> str:
    """Create a temporary fake firmware file."""
    fw = tmp_path / "firmware.elf"
    fw.write_text("FAKE_FIRMWARE_BINARY")
    return str(fw)


# ===================================================================
# HilTestResult tests
# ===================================================================


class TestHilTestResult:
    """GIVEN a HilTestResult dataclass WHEN used THEN fields correct."""

    def test_defaults(self):
        """WHEN default constructor THEN passed=True."""
        result = HilTestResult()
        assert result.passed is True
        assert result.flash_result is None
        assert result.boot_log == ""
        assert result.error is None
        assert result.phase_timings == {}

    def test_phases_alias(self):
        """WHEN phases property THEN returns phase_timings."""
        result = HilTestResult(phase_timings={"flash": 2.5, "serial": 1.0})
        assert result.phases == result.phase_timings
        assert result.phases["flash"] == 2.5


# ===================================================================
# HilTestRunner initialization
# ===================================================================


class TestHilTestRunnerInit:
    """GIVEN a HilTestRunner WHEN initialized THEN configured correctly."""

    def test_init_with_config(self, arm_target_config):
        """WHEN TargetConfig object THEN stored."""
        runner = HilTestRunner(target=arm_target_config)
        assert runner.config.name == "stm32f4"
        assert runner.serial_port == "/dev/ttyACM0"

    def test_init_with_string_target(self, arm_target_config):
        """WHEN string target name THEN resolved via flash.load_target_config_safe."""
        with mock.patch.object(FlashRunner, "__init__", return_value=None):
            with mock.patch(
                "cross.flash.load_target_config_safe",
                return_value=arm_target_config,
            ) as mock_load:
                runner = HilTestRunner(target="stm32f4")
                assert runner.config.name == "stm32f4"
                mock_load.assert_called_once_with("stm32f4", base_dir=None)

    def test_init_custom_serial_port(self, arm_target_config):
        """WHEN custom serial port provided THEN used."""
        runner = HilTestRunner(
            target=arm_target_config,
            serial_port="/dev/ttyUSB0",
        )
        assert runner.serial_port == "/dev/ttyUSB0"


# ===================================================================
# HilTestRunner.run — full lifecycle
# ===================================================================


class TestHilTestRunnerRun:
    """GIVEN a HilTestRunner WHEN run() is called THEN full lifecycle."""

    def test_run_success_flash_skip(self):
        """WHEN skip_flash=True AND expect pattern matched THEN passed."""
        # No real hardware — test with mocked path
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(
            target=cfg,
            serial_port="/dev/null",
            flash_delay=0,
        )

        # Mock the serial monitor to return "Test PASSED"
        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "Boot OK\nTest PASSED\nDone\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                expect_pattern="Test PASSED",
                timeout=5,
                skip_flash=True,
            )

        assert result.passed is True
        assert "Test PASSED" in result.boot_log

    def test_run_pattern_not_found(self):
        """WHEN expect pattern not found THEN failed."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(
            target=cfg,
            serial_port="/dev/null",
            flash_delay=0,
        )

        # Mock serial to always timeout
        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["__enter__", "__exit__"])
            mock_serial.__enter__.side_effect = SerialMonitorTimeout(
                "Pattern 'FAIL' not found"
            )
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                expect_pattern="NotFoundPattern",
                timeout=1,
                skip_flash=True,
            )

        assert result.passed is False
        assert result.error is not None

    def test_run_firmware_not_found(self):
        """WHEN firmware file doesn't exist THEN returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, flash_delay=0)
        result = runner.run(
            firmware="/nonexistent/firmware.elf",
            expect_pattern="OK",
            timeout=5,
        )

        assert result.passed is False
        assert "not found" in result.error.lower()

    @mock.patch.object(FlashRunner, "__init__", return_value=None)
    def test_run_flash_failure(self, mock_fr_init):
        """WHEN flash fails THEN returns failure."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, flash_delay=0)

        # Create a real firmware file so the file-check passes
        import tempfile
        fw_file = tempfile.NamedTemporaryFile(suffix=".elf", delete=False)
        fw_file.write(b"test")
        fw_file.close()

        try:
            # Replace the flash_runner property BEFORE it's accessed
            mock_fr = mock.MagicMock()
            mock_fr.flash.return_value = FlashResult(
                passed=False,
                tool="openocd",
                error="Cannot connect to target",
            )
            runner._flash_runner = mock_fr

            result = runner.run(
                firmware=fw_file.name,
                expect_pattern="OK",
                timeout=5,
            )

            assert result.passed is False
            assert result.flash_result is not None
            assert result.flash_result.passed is False
        finally:
            os.unlink(fw_file.name)

    def test_run_with_multiple_patterns(self):
        """WHEN expect_patterns list provided THEN checked in order."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "expect_all", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "Boot\nReady\nDone\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                expect_patterns=["Boot", "Ready", "Done"],
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True
        # expect_all should have been called
        assert mock_serial.expect_all.called or mock_serial.expect.called


# ===================================================================
# Shortcut methods
# ===================================================================


class TestHilShortcuts:
    """GIVEN shortcut methods WHEN called THEN delegate to run()."""

    def test_flash_and_expect(self):
        """WHEN flash_and_expect called THEN runs flash + expect."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        # Mock the full run method
        with mock.patch.object(HilTestRunner, "run") as mock_run:
            mock_run.return_value = HilTestResult(passed=True)

            runner = HilTestRunner(target=cfg, flash_delay=0)
            result = runner.flash_and_expect(
                firmware="fw.elf",
                pattern="Test PASSED",
                timeout=30,
            )

        assert result.passed is True
        mock_run.assert_called_once_with(
            firmware="fw.elf",
            expect_pattern="Test PASSED",
            timeout=30,
        )

    def test_skip_flash_test(self):
        """WHEN skip_flash_test called THEN runs with skip_flash=True."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        with mock.patch.object(HilTestRunner, "run") as mock_run:
            mock_run.return_value = HilTestResult(passed=True)

            runner = HilTestRunner(target=cfg)
            result = runner.skip_flash_test(pattern="OK", timeout=10)

        assert result.passed is True
        mock_run.assert_called_once_with(
            firmware="",
            expect_pattern="OK",
            timeout=10,
            skip_flash=True,
        )


# ===================================================================
# Test script execution
# ===================================================================


class TestHilTestScript:
    """GIVEN a test script WHEN executed THEN directives processed."""

    def test_expect_script(self):
        """WHEN script with expect directives THEN all processed."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "expect_all", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "Step1\nStep2\nDone\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="expect:Step1\nexpect:Step2\nexpect:Done",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True

    def test_script_with_assert(self):
        """WHEN script with assert: THEN non-blocking check."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=[
                "expect", "expect_all", "assert_text_present",
                "assert_text_absent", "read_until", "captured_log",
                "__enter__", "__exit__",
            ])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "PASSED\n"
            mock_serial.assert_text_present.return_value = True
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="assert:PASSED",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True

    def test_script_with_assert_not(self):
        """WHEN script with assert_not: THEN checks absent."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=[
                "expect", "expect_all", "assert_text_present",
                "assert_text_absent", "read_until", "captured_log",
                "__enter__", "__exit__",
            ])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "OK\n"
            mock_serial.assert_text_present.side_effect = lambda t: t != "ERROR"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="assert_not:ERROR",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True

    def test_script_with_wait(self):
        """WHEN script with wait: THEN sleeps."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "Done\n"
            mock_serial_cls.return_value = mock_serial

            t0 = time.monotonic()
            result = runner.run(
                firmware="dummy.elf",
                test_script="wait:0.2\nexpect:Done",
                timeout=10,
                skip_flash=True,
            )
            elapsed = time.monotonic() - t0

        assert result.passed is True
        assert elapsed >= 0.15  # Should have waited ~0.2s

    def test_script_with_read_until(self):
        """WHEN script with read_until: THEN calls read_until."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "read_until", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "Header\nBody\nEnd\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="read_until:Body",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True
        mock_serial.read_until.assert_called_once_with("Body", timeout=10)

    def test_script_with_expect_re(self):
        """WHEN script with expect_re: THEN regex matching."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "ERROR: code 42\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="expect_re:ERROR:.*42",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True

    def test_script_comments_ignored(self):
        """WHEN script has comments THEN ignored."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        runner = HilTestRunner(target=cfg, serial_port="/dev/null", flash_delay=0)

        with mock.patch("cross.hil_runner.SerialMonitor") as mock_serial_cls:
            mock_serial = mock.MagicMock(spec=["expect", "captured_log", "__enter__", "__exit__"])
            mock_serial.__enter__.return_value = mock_serial
            mock_serial.captured_log = "OK\n"
            mock_serial_cls.return_value = mock_serial

            result = runner.run(
                firmware="dummy.elf",
                test_script="# comment\nexpect:OK\n# another comment",
                timeout=10,
                skip_flash=True,
            )

        assert result.passed is True


# ===================================================================
# Convenience function
# ===================================================================


class TestHilTestConvenience:
    """GIVEN hil_test convenience function WHEN called THEN works."""

    def test_one_shot(self):
        """WHEN called with minimum args THEN returns HilTestResult."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )

        with mock.patch("cross.hil_runner.HilTestRunner") as mock_runner_cls:
            mock_runner = mock.MagicMock(spec=HilTestRunner)
            mock_runner.run.return_value = HilTestResult(passed=True)
            mock_runner_cls.return_value = mock_runner

            result = hil_test(
                target=cfg,
                firmware="fw.elf",
                expect_pattern="OK",
            )

        assert isinstance(result, HilTestResult)
        assert result.passed is True


# ===================================================================
# Edge cases
# ===================================================================


class TestHilEdgeCases:
    """GIVEN edge case scenarios WHEN handled THEN graceful."""

    def test_flash_runner_not_available(self):
        """WHEN no flash tool available AND flash needed THEN ..."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        # Create a real firmware file
        import tempfile
        fw_file = tempfile.NamedTemporaryFile(suffix=".elf", delete=False)
        fw_file.write(b"test")
        fw_file.close()

        try:
            runner = HilTestRunner(target=cfg, flash_delay=0)

            # Mock flash_runner property to raise FlashError
            with mock.patch.object(
                runner.__class__, "flash_runner",
                mock.PropertyMock(side_effect=FlashError("No flash tool available")),
            ):
                result = runner.run(
                    firmware=fw_file.name,
                    expect_pattern="OK",
                    skip_flash=False,
                )
        finally:
            os.unlink(fw_file.name)

        # Should handle gracefully
        assert not result.passed if hasattr(result, "passed") else True
