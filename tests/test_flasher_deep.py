"""Deep tests for hardware.flasher — BaseFlasher, OpenOCDFlasher, JLinkFlasher, ESPToolFlasher."""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

from yuleosh.hardware.flasher import (
    BaseFlasher, OpenOCDFlasher, JLinkFlasher, ESPToolFlasher,
    FlashError, BinaryNotFoundError, ToolNotFoundError, HardwareNotFoundError,
)


class TestFlasherExceptions:
    def test_flash_error(self):
        assert issubclass(FlashError, RuntimeError)
        with pytest.raises(FlashError):
            raise FlashError("test")

    def test_binary_not_found(self):
        assert issubclass(BinaryNotFoundError, FlashError)

    def test_tool_not_found(self):
        assert issubclass(ToolNotFoundError, FlashError)

    def test_hardware_not_found(self):
        assert issubclass(HardwareNotFoundError, FlashError)


class TestBaseFlasher:
    def test_abstract_class(self):
        with pytest.raises(TypeError):
            BaseFlasher({"test": "value"})  # can't instantiate ABC

    def test_tool_name_default(self):
        assert BaseFlasher.tool_name == ""
        assert BaseFlasher.detect_cmd is None

    def test_brew_package_default(self):
        assert BaseFlasher._brew_package_name() == "openocd"

    def test_apt_package_default(self):
        assert BaseFlasher._apt_package_name() == "openocd"


class TestOpenOCDFlasher:
    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_success(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.flash("/tmp/firmware.elf") is True

    @patch("yuleosh.hardware.flasher.BaseFlasher._check_hardware")
    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_failure(self, mock_isfile, mock_which, mock_run, mock_hw):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: flash failed"
        mock_run.return_value = mock_result

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.flash("/tmp/firmware.elf") is False

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_verify_success(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.verify("/tmp/firmware.elf") is True

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_verify_failure(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.verify("/tmp/firmware.elf") is False

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_timeout(self, mock_isfile, mock_which, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("openocd", 120)

        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        with pytest.raises(FlashError, match="timed out"):
            flasher.flash("/tmp/firmware.elf")

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    def test_flash_binary_not_found(self, mock_which, mock_run):
        with patch("os.path.isfile", return_value=False):
            flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
            with pytest.raises(BinaryNotFoundError):
                flasher.flash("/tmp/nope.elf")

    def test_tool_not_found(self):
        with patch("yuleosh.hardware.flasher.shutil.which", return_value=None):
            flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
            # _check_tool directly since flash() checks binary first
            with pytest.raises(ToolNotFoundError):
                flasher._check_tool()

    def test_config_resolution_defaults(self):
        flasher = OpenOCDFlasher({})
        assert flasher.interface_cfg == "interface/.cfg"
        assert flasher.target_cfg == "target/.cfg"

    def test_config_with_interface_and_target(self):
        flasher = OpenOCDFlasher({"interface": "stlink", "target": "stm32f4x"})
        assert flasher.interface_cfg == "interface/stlink.cfg"
        assert flasher.target_cfg == "target/stm32f4x.cfg"

    def test_config_custom_cfg_paths(self):
        flasher = OpenOCDFlasher({
            "interface_cfg": "custom/my_intf.cfg",
            "target_cfg": "custom/my_target.cfg",
        })
        assert flasher.interface_cfg == "custom/my_intf.cfg"

    def test_extra_args(self):
        flasher = OpenOCDFlasher({"extra_args": ["-c", "adapter speed 1000"]})
        assert flasher.extra_args == ["-c", "adapter speed 1000"]

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_hardware_check_with_detect_cmd(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        flasher = OpenOCDFlasher({})
        flasher._check_hardware()  # should pass

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_hardware_check_not_detected(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No hardware found"
        mock_run.return_value = mock_result
        flasher = OpenOCDFlasher({})
        with pytest.raises(HardwareNotFoundError):
            flasher._check_hardware()

    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_check_hardware_no_detect_cmd(self, mock_isfile):
        class TestFlasher(BaseFlasher):
            tool_name = "test"
            detect_cmd = None
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        flasher._check_hardware()  # should pass (no-op)

    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_do_verify_default(self, mock_isfile):
        class TestFlasher(BaseFlasher):
            tool_name = "test"
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        assert flasher.verify("/tmp/test.elf") is False


class TestJLinkFlasher:
    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_with_script(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = JLinkFlasher({"script": "flash.jlink"})
        assert flasher.flash("/tmp/firmware.elf") is True

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_with_stdin(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = JLinkFlasher({})
        assert flasher.flash("/tmp/firmware.bin") is True
        # Verify stdin was passed
        assert mock_run.call_args[1].get("input") is not None

    @patch("yuleosh.hardware.flasher.BaseFlasher._check_hardware")
    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_stdin_failure(self, mock_isfile, mock_which, mock_run, mock_hw):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: cannot connect"
        mock_run.return_value = mock_result

        flasher = JLinkFlasher({})
        assert flasher.flash("/tmp/firmware.bin") is False

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_stdin_timeout(self, mock_isfile, mock_which, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("JLinkExe", 120)

        flasher = JLinkFlasher({})
        with pytest.raises(FlashError, match="timed out"):
            flasher.flash("/tmp/firmware.bin")

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_hex_file(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = JLinkFlasher({})
        assert flasher.flash("/tmp/firmware.hex") is True
        assert "loadfile /tmp/firmware.hex" in mock_run.call_args[1]["input"]

    def test_verify_not_supported(self):
        flasher = JLinkFlasher({})
        with patch("os.path.isfile", return_value=True):
            with patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/bin/JLinkExe"):
                result = flasher.verify("/tmp/firmware.elf")
        assert result is False

    def test_default_config(self):
        flasher = JLinkFlasher({})
        assert flasher.device == "STM32F407VG"
        assert flasher.interface == "SWD"
        assert flasher.speed == 4000
        assert flasher.script is None

    def test_custom_config(self):
        flasher = JLinkFlasher({
            "device": "STM32G031",
            "if": "JTAG",
            "speed": 2000,
            "script": "custom.jlink",
        })
        assert flasher.device == "STM32G031"
        assert flasher.interface == "JTAG"
        assert flasher.script == "custom.jlink"


class TestESPToolFlasher:
    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.flasher.os.path.exists", return_value=True)
    def test_flash_bin_success(self, mock_exists, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = ESPToolFlasher({"chip": "esp32"})
        result = flasher.flash("/tmp/firmware.bin", port="/dev/ttyUSB0")
        assert result is True

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.flasher.os.path.exists", return_value=True)
    def test_flash_elf_returns_warning_but_succeeds(self, mock_exists, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = ESPToolFlasher({})
        # .elf uses elf2image path
        result = flasher.flash("/tmp/firmware.elf", port="/dev/ttyUSB0")
        assert result is True

    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_port_not_found_macos(self, mock_isfile, mock_which):
        with patch("sys.platform", "darwin"):
            with patch("os.path.exists", return_value=False):
                flasher = ESPToolFlasher({})
                from yuleosh.hardware.flasher import HardwareNotFoundError
                with pytest.raises(HardwareNotFoundError):
                    flasher.flash("/tmp/firmware.bin", port="/dev/ttyUSB0")

    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    def test_flash_port_not_found_linux(self, mock_isfile, mock_which):
        with patch("sys.platform", "linux"):
            with patch("os.path.exists", return_value=False):
                flasher = ESPToolFlasher({})
                from yuleosh.hardware.flasher import HardwareNotFoundError
                with pytest.raises(HardwareNotFoundError):
                    flasher.flash("/tmp/firmware.bin", port="/dev/ttyUSB0")

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.flasher.os.path.exists", return_value=True)
    def test_verify_bin(self, mock_exists, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        flasher = ESPToolFlasher({})
        result = flasher.verify("/tmp/firmware.bin")
        assert result is True

    @patch("yuleosh.hardware.flasher.subprocess.run")
    @patch("yuleosh.hardware.flasher.shutil.which", return_value="/usr/local/bin/esptool.py")
    @patch("yuleosh.hardware.flasher.os.path.isfile", return_value=True)
    @patch("yuleosh.hardware.flasher.os.path.exists", return_value=True)
    def test_verify_elf_not_supported(self, mock_exists, mock_isfile, mock_which, mock_run):
        flasher = ESPToolFlasher({})
        result = flasher.verify("/tmp/firmware.elf")
        assert result is False

    def test_default_config(self):
        flasher = ESPToolFlasher({})
        assert flasher.chip == "esp32"
        assert flasher.baud == 921600
        assert flasher.flash_mode == "dio"
        assert flasher.flash_size == "4MB"

    def test_custom_config(self):
        flasher = ESPToolFlasher({
            "chip": "esp32c3",
            "baud": 115200,
            "flash_mode": "qio",
            "flash_size": "8MB",
        })
        assert flasher.chip == "esp32c3"

    def test_repr(self):
        flasher = ESPToolFlasher({"chip": "esp32"})
        r = repr(flasher)
        assert "ESPToolFlasher" in r
        assert "esp32" in r


class TestBaseFlasherCheckBinary:
    def test_check_binary_exists(self):
        with patch("os.path.isfile", return_value=True):
            BaseFlasher._check_binary(None, "/tmp/test.elf")
            # No exception = success

    def test_check_binary_not_exists(self):
        with patch("os.path.isfile", return_value=False):
            with pytest.raises(BinaryNotFoundError):
                BaseFlasher._check_binary(None, "/tmp/nope.elf")

    def test_check_tool_not_found(self):
        class TestFlasher(BaseFlasher):
            tool_name = "nonexistent_tool"
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        with patch("shutil.which", return_value=None):
            with pytest.raises(ToolNotFoundError):
                flasher._check_tool()


class TestBaseFlasherRun:
    def test_run_success(self):
        class TestFlasher(BaseFlasher):
            tool_name = "test"
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        with patch("yuleosh.hardware.flasher.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = flasher._run(["test_cmd"])
            assert result.returncode == 0

    def test_run_failure(self):
        class TestFlasher(BaseFlasher):
            tool_name = "test"
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        with patch("yuleosh.hardware.flasher.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            result = flasher._run(["test_cmd"])
            assert result.returncode == 1

    def test_run_os_error(self):
        class TestFlasher(BaseFlasher):
            tool_name = "test"
            def _do_flash(self, *args): return True
        flasher = TestFlasher({})
        with patch("yuleosh.hardware.flasher.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Exec format error")
            with pytest.raises(FlashError, match="Failed to execute"):
                flasher._run(["test_cmd"])
