"""Deep tests for cross.flash — FlashRunner, OpenOCDRunner, JLinkRunner, etc."""

import time
import pytest
from unittest.mock import MagicMock, patch, mock_open
from yuleosh.cross.flash import (
    FlashResult, FlashError, FlashTool,
    OpenOCDRunner, JLinkRunner, PyOCDRunner,
    FlashRunner, flash_firmware, detect_hardware,
    load_target_config_safe, _discover_tools, _BUILTIN_TOOLS,
)


class TestFlashResult:
    def test_defaults(self):
        r = FlashResult()
        assert r.passed is True
        assert r.log == ""
        assert r.tool == ""
        assert r.elapsed == 0.0
        assert r.error is None

    def test_custom(self):
        r = FlashResult(passed=False, tool="openocd", log="error", error="timeout")
        assert r.passed is False
        assert r.tool == "openocd"


class TestFlashError:
    def test_is_runtime_error(self):
        assert issubclass(FlashError, RuntimeError)

    def test_can_raise(self):
        with pytest.raises(FlashError):
            raise FlashError("test")


class TestOpenOCDRunner:
    def test_name(self):
        r = OpenOCDRunner()
        assert r.name == "openocd"

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_is_available(self, mock_which):
        r = OpenOCDRunner()
        assert r.is_available() is True

    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_is_not_available(self, mock_which):
        r = OpenOCDRunner()
        assert r.is_available() is False

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_write_success(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "programmed ok"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "stm32f4"
        cfg.flash_openocd = "config/stm32f4.cfg"
        runner = OpenOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is True
        assert result.tool == "openocd"

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_write_failure(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: flash failed"
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "stm32f4"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert result.error is not None

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_write_timeout(self, mock_which, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("openocd", 60)

        cfg = MagicMock()
        cfg.name = "stm32f4"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert "Timeout" in result.error

    def test_write_no_config(self):
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = None
        runner = OpenOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert "no OpenOCD config" in result.error

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_erase_success(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is True
        assert result.tool == "openocd"

    def test_erase_no_config(self):
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = None
        runner = OpenOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is False

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_verify_success(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.verify("/tmp/fw.elf", cfg)
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_verify_failure(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.verify("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert "mismatch" in result.error

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_write_binary_not_found_exception(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"

        with patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd"):
            runner = OpenOCDRunner()
            result = runner.write("/tmp/fw.elf", cfg)
            assert result.passed is False
            assert "not found" in result.error


class TestJLinkRunner:
    def test_name(self):
        r = JLinkRunner()
        assert r.name == "jlink"

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_is_available(self, mock_which):
        r = JLinkRunner()
        assert r.is_available() is True

    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_is_not_available(self, mock_which):
        r = JLinkRunner()
        assert r.is_available() is False

    def test_build_script_flash(self):
        cfg = MagicMock()
        cfg.flash_jlink = {"device": "STM32F407VG", "interface": "SWD", "speed": 4000}
        runner = JLinkRunner()
        script = runner._build_script("/tmp/fw.elf", cfg)
        assert "loadfile" in script
        assert "STM32F407VG" in script

    def test_build_script_erase(self):
        cfg = MagicMock()
        cfg.flash_jlink = {"device": "STM32F407VG", "interface": "SWD", "speed": 4000}
        runner = JLinkRunner()
        script = runner._build_script("/tmp/fw.elf", cfg, action="erase")
        assert "erase" in script
        assert "loadfile" not in script

    def test_build_script_no_jlink_config(self):
        cfg = MagicMock()
        cfg.flash_jlink = None
        runner = JLinkRunner()
        script = runner._build_script("/tmp/fw.elf", cfg)
        assert "loadfile" in script
        assert "STM32F407VG" in script  # default fallback

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_write_success(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Flash download complete"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = {"device": "STM32F407VG"}
        runner = JLinkRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_write_failure(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "ERROR: Cannot connect"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = {"device": "STM32F407VG"}
        runner = JLinkRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False

    def test_write_no_config(self):
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = None
        runner = JLinkRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert "no J-Link config" in result.error

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_erase_success(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = {"device": "STM32F407VG"}
        runner = JLinkRunner()
        result = runner.erase(cfg)
        assert result.passed is True

    def test_erase_no_config(self):
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = None
        runner = JLinkRunner()
        result = runner.erase(cfg)
        assert result.passed is False


class TestPyOCDRunner:
    def test_name(self):
        r = PyOCDRunner()
        assert r.name == "pyocd"

    def test_is_available_by_import(self):
        with patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/pyocd"):
            r = PyOCDRunner()
            assert r.is_available() is True

    def test_is_not_available(self):
        with patch("yuleosh.cross.flash.shutil.which", return_value=None):
            with patch("yuleosh.cross.flash.shutil.which", return_value=None):
                with patch.dict("sys.modules", {"pyocd": None}):
                    import sys
                    saved = sys.modules.get("pyocd")
                    sys.modules["pyocd"] = None
                    try:
                        r = PyOCDRunner()
                        assert r.is_available() is False
                    finally:
                        if saved:
                            sys.modules["pyocd"] = saved

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_write_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Flash complete"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_write_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error"
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_write_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("pyocd", 60)

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is False
        assert "Timeout" in result.error

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_write_default_target(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = None
        runner = PyOCDRunner()
        result = runner.write("/tmp/fw.elf", cfg)
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_erase_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    def test_erase_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is False


class TestFlashToolABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            FlashTool()

    def test_verify_default(self):
        class ConcreteTool(FlashTool):
            @property
            def name(self): return "test"
            def is_available(self): return True
            def write(self, f, c): return FlashResult()
            def erase(self, c): return FlashResult()

        tool = ConcreteTool()
        cfg = MagicMock()
        result = tool.verify("fw.elf", cfg)
        assert result.passed is False
        assert "not supported" in result.error


class TestDiscoverTools:
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_discover_openocd(self, mock_which):
        tools = _discover_tools()
        names = [t.name for t in tools]
        assert "openocd" in names

    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_discover_none(self, mock_which):
        with patch.dict("sys.modules", {"pyocd": None}):
            tools = _discover_tools()
            assert len(tools) == 0

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_discover_preferred(self, mock_which):
        tools = _discover_tools(preferred="openocd")
        assert len(tools) >= 1
        assert tools[0].name == "openocd"


class TestFlashRunner:
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.cross.flash.load_target_config_safe")
    def test_init_with_target_name(self, mock_load, mock_which):
        cfg = MagicMock()
        cfg.name = "stm32f4"
        mock_load.return_value = cfg
        runner = FlashRunner(target="stm32f4")
        assert runner.config.name == "stm32f4"

    def test_init_with_target_config(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        with patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd"):
            runner = FlashRunner(target=cfg)
            assert runner.config.name == "test"

    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_init_no_tools(self, mock_which):
        with patch.dict("sys.modules", {"pyocd": None}):
            from yuleosh.cross.flash import _BUILTIN_TOOLS
            cfg = MagicMock()
            cfg.name = "test"
            with pytest.raises(FlashError, match="No flash tool"):
                FlashRunner(target=cfg)

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_tool_name(self, mock_which):
        cfg = MagicMock()
        cfg.name = "test"
        runner = FlashRunner(target=cfg)
        assert runner.tool_name == "openocd"

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_available_tools(self, mock_which):
        cfg = MagicMock()
        cfg.name = "test"
        runner = FlashRunner(target=cfg)
        assert "openocd" in runner.available_tools

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_flash_file_not_found(self, mock_which):
        cfg = MagicMock()
        cfg.name = "test"
        runner = FlashRunner(target=cfg)
        result = runner.flash("/tmp/nonexistent.elf")
        assert result.passed is False
        assert "not found" in result.error

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.cross.flash.os.path.isfile", return_value=True)
    def test_flash_success(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "OK"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = FlashRunner(target=cfg)
        result = runner.flash("/tmp/fw.elf")
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.cross.flash.os.path.isfile", return_value=True)
    def test_erase(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = FlashRunner(target=cfg)
        result = runner.erase()
        assert result.passed is True

    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.cross.flash.os.path.isfile", return_value=True)
    def test_verify(self, mock_isfile, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = FlashRunner(target=cfg)
        result = runner.verify("/tmp/fw.elf")
        assert result.passed is True


class TestFlashFirmware:
    @patch("yuleosh.cross.flash.FlashRunner")
    def test_flash_firmware_convenience(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_result = FlashResult(passed=True)
        mock_runner.flash.return_value = mock_result
        mock_runner_cls.return_value = mock_runner

        result = flash_firmware("stm32f4", "/tmp/fw.elf")
        assert result.passed is True
        mock_runner_cls.assert_called_once()


class TestDetectHardware:
    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_detect_jlink(self, mock_which, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = "Serial Number: 12345\nDevice: STM32F407VG"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        results = detect_hardware()
        assert len(results) >= 1

    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_detect_no_hardware(self, mock_which):
        with patch.dict("sys.modules", {"pyocd": None}):
            results = detect_hardware()
            assert len(results) == 0

    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_detect_jlink_exception_handled(self, mock_which):
        """JLink command failure should be caught gracefully."""
        with patch("yuleosh.cross.flash.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("JLink failed")
            results = detect_hardware()
            # Should not crash, just return partial results
            assert isinstance(results, list)


class TestLoadTargetConfigSafe:
    @patch("yuleosh.cross.target_config.load_target_config")
    def test_load_success(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        result = load_target_config_safe("stm32f4")
        assert result == mock_cfg

    @patch("yuleosh.cross.target_config.load_target_config")
    @patch("yuleosh.cross.target_config.discover_targets")
    def test_load_file_not_found_with_targets(self, mock_discover, mock_load):
        mock_load.side_effect = FileNotFoundError("Not found")
        mock_discover.return_value = {"stm32f4": {}, "stm32g0": {}}
        with pytest.raises(FlashError, match="not found"):
            load_target_config_safe("nonexistent")

    @patch("yuleosh.cross.target_config.load_target_config")
    @patch("yuleosh.cross.target_config.discover_targets")
    def test_load_file_not_found_no_targets(self, mock_discover, mock_load):
        mock_load.side_effect = FileNotFoundError("Not found")
        mock_discover.return_value = {}
        with pytest.raises(FlashError, match="not found"):
            load_target_config_safe("nonexistent")


class TestPyOCDDetectHardware:
    """Test pyOCD hardware detection path (exercises the import path)."""
    @patch("yuleosh.cross.flash.shutil.which", return_value=None)
    def test_pyocd_import_detection(self, mock_which):
        """test that detect_hardware handles pyOCD import errors gracefully."""
        results = detect_hardware()
        assert isinstance(results, list)


class TestOpenOCDVerify:
    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    @patch("yuleosh.cross.flash.os.path.isfile", return_value=True)
    def test_verify_no_config(self, mock_isfile, mock_which, mock_run):
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = None
        runner = OpenOCDRunner()
        result = runner.verify("/tmp/fw.elf", cfg)
        assert result.passed is False


class TestOpenOCDEraseTimeout:
    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/openocd")
    def test_erase_timeout(self, mock_which, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("openocd", 60)
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_openocd = "config.cfg"
        runner = OpenOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is False
        assert "Timed out" in result.log or "Timeout" in result.error


class TestJLinkEraseTimeout:
    @patch("yuleosh.cross.flash.subprocess.run")
    @patch("yuleosh.cross.flash.shutil.which", return_value="/usr/bin/JLinkExe")
    def test_erase_timeout(self, mock_which, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("JLinkExe", 60)
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_jlink = {"device": "STM32F407VG"}
        runner = JLinkRunner()
        result = runner.erase(cfg)
        assert result.passed is False


class TestPyOCDEraseTimeout:
    @patch("yuleosh.cross.flash.subprocess.run")
    def test_erase_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("pyocd", 60)
        cfg = MagicMock()
        cfg.name = "test"
        cfg.flash_pyocd = {"target": "stm32f407vg"}
        runner = PyOCDRunner()
        result = runner.erase(cfg)
        assert result.passed is False
