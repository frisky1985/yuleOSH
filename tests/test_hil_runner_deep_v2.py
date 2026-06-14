"""Deep tests for cross.hil_runner — HilTestRunner, HilTestResult."""

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from yuleosh.cross.hil_runner import (
    HilTestRunner,
    HilTestResult,
    hil_test,
)


class TestHilTestResult:
    def test_defaults(self):
        r = HilTestResult()
        assert r.passed is True
        assert r.flash_result is None
        assert r.boot_log == ""
        assert r.test_log == ""
        assert r.elapsed == 0.0
        assert r.error is None
        assert r.phase_timings == {}

    def test_phases_alias(self):
        r = HilTestResult()
        r.phase_timings["flash"] = 1.5
        assert r.phases["flash"] == 1.5


class TestHilTestRunnerInit:
    def test_init_with_target_config(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.serial_port = "/dev/ttyAMA0"
        runner = HilTestRunner(target=cfg)
        assert runner.serial_port == "/dev/ttyAMA0"
        assert runner.config.name == "test"

    def test_init_default_port_when_no_serial_on_config(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        runner = HilTestRunner(target=cfg)
        assert runner.serial_port == "/dev/ttyACM0"

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_flash_runner_lazy_init(self, mock_which):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        runner = HilTestRunner(target=cfg)
        assert runner._flash_runner is None
        fr = runner.flash_runner
        assert fr is not None
        assert runner._flash_runner is not None

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_init_with_target_name(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = "/dev/ttyACM0"
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")
        assert runner.serial_port == "/dev/ttyACM0"
        assert runner.baud == 115200

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_init_with_serial_port_override(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4", serial_port="/dev/ttyS0")
        assert runner.serial_port == "/dev/ttyS0"


class TestHilTestRunnerRun:
    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_success(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        mock_serial = MagicMock()
        mock_serial.captured_log = "Boot OK\nTest PASSED\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(
                firmware="/tmp/test_firmware.elf",
                expect_pattern="Test PASSED",
                timeout=10,
            )
        assert result.passed is True
        assert result.flash_result is not None

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_skip_flash(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_serial = MagicMock()
        mock_serial.captured_log = "Test PASSED\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        runner = HilTestRunner(target="stm32f4")
        result = runner.run(
            firmware="/tmp/test.elf",
            skip_flash=True,
            expect_pattern="Test PASSED",
            timeout=5,
        )
        assert result.passed is True
        assert not mock_fr_cls.called

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_firmware_not_found(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        with patch("os.path.isfile", return_value=False):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(
                firmware="/tmp/nonexistent.elf",
                expect_pattern="Test PASSED",
                timeout=5,
            )
        assert result.passed is False
        assert "not found" in result.error.lower()

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_flash_error(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        from yuleosh.cross.flash import FlashError
        mock_fr.flash.side_effect = FlashError("Flash tool not found")
        mock_fr_cls.return_value = mock_fr

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(firmware="/tmp/test.elf", timeout=5)
        assert result.passed is False
        assert "Flash error" in result.error

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_flash_failed_result(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = False
        mock_flash_res.error = "Verification failed"
        mock_flash_res.log = ""
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(firmware="/tmp/test.elf", timeout=5)
        assert result.passed is False
        assert "Flashing failed" in result.error

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_exception_in_serial(self, mock_load, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_serial_cls.return_value.__enter__.side_effect = RuntimeError("Port busy")
        mock_serial_cls.return_value.__exit__.return_value = False

        with patch("yuleosh.cross.hil_runner.FlashRunner") as mock_fr_cls:
            mock_fr = MagicMock()
            mock_flash_res = MagicMock()
            mock_flash_res.passed = True
            mock_flash_res.elapsed = 0.1
            mock_fr.flash.return_value = mock_flash_res
            mock_fr_cls.return_value = mock_fr

            with patch("os.path.isfile", return_value=True):
                runner = HilTestRunner(target="stm32f4")
                result = runner.run(firmware="/tmp/test.elf", timeout=5)
            assert result.passed is False

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_with_expect_patterns(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        mock_serial = MagicMock()
        mock_serial.captured_log = "Boot\nStarting\nTest PASSED\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(
                firmware="/tmp/test.elf",
                expect_patterns=["Boot", "Test PASSED"],
                timeout=10,
            )
        assert result.passed is True

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_with_test_script(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        mock_serial = MagicMock()
        mock_serial.captured_log = ""
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(
                firmware="/tmp/test.elf",
                test_script="expect:Hello",
                timeout=10,
            )
        assert result is not None


class TestHilTestRunnerShortcuts:
    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_flash_and_expect(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        mock_serial = MagicMock()
        mock_serial.captured_log = "Test PASSED\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.flash_and_expect("/tmp/test.elf", "Test PASSED", timeout=10)
        assert result.passed is True

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_flash_and_boot(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        mock_serial = MagicMock()
        mock_serial.captured_log = "Boot OK\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.flash_and_boot("/tmp/test.elf", timeout=10)
        assert result.passed is True

    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_skip_flash_test(self, mock_load, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_serial = MagicMock()
        mock_serial.captured_log = "Boot OK\n"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        runner = HilTestRunner(target="stm32f4")
        result = runner.skip_flash_test("Boot OK", timeout=10)
        assert result.passed is True


class TestHilTestRunnerTestScript:
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_expect(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        script = "expect:Hello\n"
        runner._run_test_script(mock_serial, script, 10.0)
        mock_serial.expect.assert_called_once_with("Hello", timeout=10.0)

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_expect_re(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        script = "expect_re:Hello.*world\n# comment line\nexpect:done"
        runner._run_test_script(mock_serial, script, 10.0)
        assert mock_serial.expect.call_count == 2

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_assert(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        mock_serial._atp = MagicMock(return_value=True)
        setattr(mock_serial, 'assert_text_present', mock_serial._atp)
        script = "assert:Hello"
        runner._run_test_script(mock_serial, script, 10.0)
        mock_serial._atp.assert_called_once_with("Hello")

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_assert_not_found(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        mock_serial._atp = MagicMock(return_value=False)
        setattr(mock_serial, 'assert_text_present', mock_serial._atp)
        script = "assert:Hello"
        with pytest.raises(Exception) as excinfo:
            runner._run_test_script(mock_serial, script, 10.0)
        assert "not found" in str(excinfo.value)

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_assert_not(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        mock_serial._atp = MagicMock(return_value=True)
        setattr(mock_serial, 'assert_text_present', mock_serial._atp)
        script = "assert_not:ERROR"
        with pytest.raises(Exception) as excinfo:
            runner._run_test_script(mock_serial, script, 10.0)
        assert "found" in str(excinfo.value)

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_wait(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        script = "wait:0.01"
        t0 = time.monotonic()
        runner._run_test_script(mock_serial, script, 10.0)
        assert time.monotonic() - t0 >= 0.005

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_read_until(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        script = "read_until:DONE"
        runner._run_test_script(mock_serial, script, 10.0)
        mock_serial.read_until.assert_called_once_with("DONE", timeout=10.0)

    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_run_test_script_empty_line(self, mock_load):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg
        runner = HilTestRunner(target="stm32f4")

        mock_serial = MagicMock()
        script = "\n\n  \n"
        runner._run_test_script(mock_serial, script, 10.0)
        mock_serial.expect.assert_not_called()


class TestHilTestRunnerSerialMonitorTimeout:
    @patch("yuleosh.cross.hil_runner.SerialMonitor")
    @patch("yuleosh.cross.hil_runner.FlashRunner")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_serial_monitor_timeout_handling(self, mock_load, mock_fr_cls, mock_serial_cls):
        mock_cfg = MagicMock()
        mock_cfg.serial_port = None
        mock_load.return_value = mock_cfg

        mock_fr = MagicMock()
        mock_flash_res = MagicMock()
        mock_flash_res.passed = True
        mock_flash_res.elapsed = 0.5
        mock_fr.flash.return_value = mock_flash_res
        mock_fr_cls.return_value = mock_fr

        from yuleosh.cross.serial_monitor import SerialMonitorTimeout
        mock_serial = MagicMock()
        mock_serial.expect.side_effect = SerialMonitorTimeout("Pattern not found in 10s")
        mock_serial.captured_log = "some output"
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        with patch("os.path.isfile", return_value=True):
            runner = HilTestRunner(target="stm32f4")
            result = runner.run(firmware="/tmp/test.elf", expect_pattern="Hello", timeout=10)
        assert result.passed is False


class TestHilTest:
    @patch("yuleosh.cross.hil_runner.HilTestRunner")
    def test_hil_test_convenience(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_result = MagicMock()
        mock_result.passed = True
        mock_runner.run.return_value = mock_result
        mock_runner_cls.return_value = mock_runner

        result = hil_test(
            target="stm32f4",
            firmware="/tmp/test.elf",
            expect_pattern="Test PASSED",
            timeout=10,
        )
        assert result.passed is True
        mock_runner.run.assert_called_once()
