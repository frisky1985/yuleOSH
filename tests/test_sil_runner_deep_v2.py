"""Deep tests for cross.sil_runner — QemuSilRunner, SilResult, parse_qemu_version."""

import os
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from yuleosh.cross.sil_runner import (
    QemuSilRunner, SilResult, parse_qemu_version,
    MIN_QEMU_VERSION, MAX_QEMU_VERSION, RECOMMENDED_QEMU_VERSION,
    sil_test,
)


class TestConstants:
    def test_min_version(self):
        assert MIN_QEMU_VERSION == (8, 2, 0)

    def test_max_version(self):
        assert MAX_QEMU_VERSION == (8, 3, 0)

    def test_recommended(self):
        assert RECOMMENDED_QEMU_VERSION == "8.2.x"


class TestParseQemuVersion:
    def test_parse_standard(self):
        output = "QEMU emulator version 8.2.0 (v8.2.0)\nCopyright ..."
        v = parse_qemu_version(output)
        assert v == (8, 2, 0)

    def test_parse_9_1(self):
        output = "QEMU emulator version 9.1.0\n"
        v = parse_qemu_version(output)
        assert v == (9, 1, 0)

    def test_parse_dev_version(self):
        output = "QEMU emulator version 7.2.0 (deb7.2.0)\n"
        v = parse_qemu_version(output)
        assert v == (7, 2, 0)

    def test_parse_no_match(self):
        with pytest.raises(RuntimeError, match="Cannot parse"):
            parse_qemu_version("No version info here")


class TestSilResult:
    def test_defaults(self):
        r = SilResult()
        assert r.passed is True
        assert r.log == ""
        assert r.coverage == {}
        assert r.elapsed == 0.0
        assert r.assertion_failures == []
        assert r.error is None

    def test_custom(self):
        r = SilResult(passed=False, log="error log", error="QEMU not found")
        assert r.passed is False
        assert r.error == "QEMU not found"


class TestQemuSilRunnerInit:
    def test_init_no_elf_raises(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        with pytest.raises(ValueError, match="elf"):
            QemuSilRunner(cfg)

    def test_init_qemu_not_found(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        with patch("yuleosh.cross.sil_runner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="not found in PATH"):
                QemuSilRunner(cfg)

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_init_ok(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)
        assert runner._qemu_bin == "qemu-system-arm"
        assert runner._timeout == 30


class TestQemuSilRunnerVersionCheck:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_version_too_old(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 7.0.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        with pytest.raises(RuntimeError, match="too old"):
            QemuSilRunner(cfg)

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_version_newer_than_max(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 9.0.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        # Newer than max should warn but not raise
        runner = QemuSilRunner(cfg)
        assert runner is not None

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_version_check_timeout(self, mock_run, mock_which):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("qemu", 10)

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        with pytest.raises(RuntimeError, match="timed out"):
            QemuSilRunner(cfg)

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_version_check_bad_exit_code(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        with pytest.raises(RuntimeError, match="exited with code"):
            QemuSilRunner(cfg)


class TestQemuSilRunnerRun:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    @patch("yuleosh.cross.sil_runner.subprocess.Popen")
    def test_run_simple_expect_success(self, mock_popen_cls, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.read.return_value = "Test PASSED\n"
        mock_popen_cls.return_value = mock_process

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        # Mock SerialAssert to make expect work
        with patch("yuleosh.cross.sil_runner.SerialAssert") as mock_sa_cls:
            mock_sa = MagicMock()
            mock_sa.captured_log = "Test PASSED\n"
            mock_sa_cls.stream.return_value.__enter__.return_value = mock_sa

            result = runner.run(expect_pattern="Test PASSED", timeout=5)
            assert result.passed is True
            mock_sa.expect.assert_called_once_with("Test PASSED", timeout=5)

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    @patch("yuleosh.cross.sil_runner.subprocess.Popen")
    def test_run_simple_expect_failure(self, mock_popen_cls, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_popen_cls.return_value = mock_process

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        with patch("yuleosh.cross.sil_runner.SerialAssert") as mock_sa_cls:
            mock_sa = MagicMock()
            mock_sa.captured_log = ""
            mock_sa.expect.side_effect = AssertionError("Pattern not found")
            mock_sa_cls.stream.return_value.__enter__.return_value = mock_sa

            result = runner.run(expect_pattern="NONEXISTENT", timeout=3)
            assert result.passed is False
            assert result.error is not None

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    @patch("yuleosh.cross.sil_runner.subprocess.Popen")
    def test_run_with_test_script(self, mock_popen_cls, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_popen_cls.return_value = mock_process

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        with patch("yuleosh.cross.sil_runner.SerialAssert") as mock_sa_cls:
            mock_sa = MagicMock()
            mock_sa.captured_log = "Hello\nWorld\n"
            mock_sa_cls.stream.return_value.__enter__.return_value = mock_sa

            with patch("yuleosh.cross.sil_runner.run_expect_script") as mock_res:
                result = runner.run(test_script="expect:Hello\n")
                assert result is not None

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    @patch("yuleosh.cross.sil_runner.subprocess.Popen")
    def test_run_no_script_waits_for_exit(self, mock_popen_cls, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        mock_process = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.poll.side_effect = [None, None, 0]
        mock_popen_cls.return_value = mock_process

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        with patch("yuleosh.cross.sil_runner.SerialAssert") as mock_sa_cls:
            mock_sa = MagicMock()
            mock_sa.captured_log = ""
            mock_sa_cls.stream.return_value.__enter__.return_value = mock_sa

            result = runner.run(test_script="", timeout=1)
            assert result is not None


class TestQemuSilRunnerTerminate:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_terminate_graceful(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        runner._process = mock_proc
        runner._terminate(0.5)
        mock_proc.terminate.assert_called_once()

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_terminate_kill_on_timeout(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_proc = MagicMock()
        from subprocess import TimeoutExpired
        # First wait() raises, second wait() (after kill) succeeds
        mock_proc.wait.side_effect = [TimeoutExpired("qemu", 0.5), 0]
        runner._process = mock_proc
        runner._terminate(0.5)
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.QemuSilRunner._check_qemu_version")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_terminate_none(self, mock_run, mock_check_qemu, mock_which):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)
        runner._process = None
        runner._terminate()  # should not raise

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.QemuSilRunner._check_qemu_version")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_terminate_os_error(self, mock_run, mock_check_qemu, mock_which):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("No such process")
        runner._process = mock_proc
        runner._terminate()  # should not raise

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.QemuSilRunner._check_qemu_version")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_terminate_sets_process_none(self, mock_run, mock_check_qemu, mock_which):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        runner._process = mock_proc
        runner._terminate()
        assert runner._process is None


class TestQemuSilRunnerWaitForExit:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_wait_for_exit_returns(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 0]
        runner._process = mock_process
        mock_serial = MagicMock()
        runner._wait_for_exit(1, mock_serial)
        assert mock_process.poll.call_count == 2

    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_wait_for_exit_timeout(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        runner._process = mock_process
        mock_serial = MagicMock()

        with patch.object(runner, '_terminate') as mock_term:
            runner._wait_for_exit(0.5, mock_serial)
            mock_term.assert_called_once_with(5.0)


class TestQemuSilRunnerCapturedLog:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_captured_log(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read.return_value = "remaining output"
        runner._process = mock_proc
        log = runner._captured_log()
        assert log == "remaining output"


class TestQemuSilRunnerExtractCoverage:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_extract_coverage_empty(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)
        assert runner._extract_coverage() == {}


class TestQemuSilRunnerUnexpectedError:
    @patch("yuleosh.cross.sil_runner.shutil.which", return_value="/usr/bin/qemu-system-arm")
    @patch("yuleosh.cross.sil_runner.subprocess.run")
    def test_run_catches_exception(self, mock_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        mock_run.return_value = mock_result

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        cfg.elf = "build/fw.elf"
        runner = QemuSilRunner(cfg)

        with patch.object(runner, '_do_run', side_effect=Exception("Unexpected crash")):
            result = runner.run(timeout=1)
            assert result.passed is False
            assert "Unexpected error" in result.error


class TestSilTest:
    @patch("yuleosh.cross.sil_runner.QemuSilRunner")
    def test_sil_test_convenience(self, mock_runner_cls):
        mock_runner = MagicMock()
        mock_result = SilResult(passed=True)
        mock_runner.run.return_value = mock_result
        mock_runner_cls.return_value = mock_runner

        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig("test", "stm32f4", "arm", "lm3s6965evb", "cortex-m3", "stdio")
        result = sil_test(cfg, expect_pattern="Hello")
        assert result.passed is True
        mock_runner.run.assert_called_once()
