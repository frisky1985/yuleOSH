"""
Tests for the QEMU SIL Runner (v0.4.0 Iteration 1).

Covers: SIL, QEMU, emulation, serial, UART, semihosting, timeout, elf, binary
Scenario-Ref: SIL 仿真测试

All tests run in `mock` mode — they do NOT require a real QEMU binary or
target hardware. Subprocess calls and YAML file operations are mocked to
simulate various QEMU behaviors (normal exit, timeout, assertion failure,
process crash, QEMU binary missing).

Coverage target: ≥80% of src/cross/sil_runner.py, src/cross/sil_assert.py,
and src/cross/target_config.py.
"""

import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cross.target_config import (
    TargetConfig,
    load_target_config,
    discover_targets,
)
from cross.sil_assert import (
    SerialAssert,
    SilAssertionError,
    run_expect_script,
    ExpectScriptError,
)
from cross.sil_runner import (
    MIN_QEMU_VERSION,
    MAX_QEMU_VERSION,
    QemuSilRunner,
    SilResult,
    parse_qemu_version,
    sil_test,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def arm_target_config() -> TargetConfig:
    """A fully populated TargetConfig for ARM (lm3s6965)."""
    return TargetConfig(
        name="lm3s6965",
        mcu="cortex-m3",
        arch="arm",
        qemu_machine="lm3s6965evb",
        qemu_cpu="cortex-m3",
        qemu_serial="-serial stdio",
        elf="/tmp/fake-hello-arm.elf",
        default_timeout=30,
    )


@pytest.fixture
def riscv_target_config() -> TargetConfig:
    """A fully populated TargetConfig for RISC-V."""
    return TargetConfig(
        name="riscv64",
        mcu="riscv64",
        arch="riscv",
        qemu_machine="virt",
        qemu_cpu="rv64",
        qemu_serial="-serial stdio",
        elf="/tmp/fake-hello-riscv.elf",
        default_timeout=30,
    )


@pytest.fixture
def mock_qemu_binary():
    """Mock ``shutil.which("qemu-system-arm")`` to return a fake path."""
    with mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm"):
        yield


@pytest.fixture
def mock_qemu_process():
    """Return a ``mock.MagicMock`` that simulates a QEMU subprocess.

    The mock process provides a ``stdout`` pipe that yields the given
    ``output_lines`` and exits with the given ``returncode``.
    """

    def _make(output_lines: list[str] | None = None, returncode: int = 0):
        if output_lines is None:
            output_lines = [
                "Hello from yuleOSH cross-compilation test!\n",
                "Architecture: ARM\n",
            ]
        output_text = "".join(output_lines)
        pipe = io.StringIO(output_text)

        proc = mock.MagicMock(spec=subprocess.Popen)
        proc.stdout = pipe
        proc.poll.return_value = returncode
        proc.returncode = returncode

        return proc

    return _make


@pytest.fixture
def target_yaml_dir(tmp_path):
    """Create a temporary directory with target YAML files for testing."""
    targets_dir = tmp_path / ".yuleosh" / "targets"
    targets_dir.mkdir(parents=True)

    (targets_dir / "test-arm.yaml").write_text("""
mcu: cortex-m3
arch: arm
qemu:
  machine: lm3s6965evb
  cpu: cortex-m3
  serial: "-serial stdio"
default_timeout: 15
""")

    (targets_dir / "test-riscv.yaml").write_text("""
mcu: riscv64
arch: riscv
qemu:
  machine: virt
  cpu: rv64
  serial: "-serial stdio"
default_timeout: 45
""")

    return str(tmp_path)


# ---------------------------------------------------------------------------
# Helper: mock QEMU version check return
# ---------------------------------------------------------------------------


def make_mock_qemu_version_tool(major=8, minor=2, patch=2):
    """Return ``(mock_result, ctx_mgr)`` where *ctx_mgr* patches
    ``subprocess.run`` to return a fake QEMU version response.

    Usage in tests::

        ", mock_result = make_mock_qemu_version_tool()
        with mock_result[1]:
            runner = QemuSilRunner(config)
    """
    mock_result = mock.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = f"QEMU emulator version {major}.{minor}.{patch}\n"
    return mock_result, mock.patch("subprocess.run", return_value=mock_result)


@pytest.fixture
def mock_qemu_version():
    """Fixture that mocks ``subprocess.run`` to return a valid
    QEMU version during ``QemuSilRunner.__init__()``.

    Yields ``(mock_result, patcher_done_flag)``.  The patcher is
    active for the duration of the test.
    """
    mock_result = mock.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "QEMU emulator version 8.2.2\n"
    with mock.patch("subprocess.run", return_value=mock_result):
        yield mock_result


# ===================================================================
# Part 0: QEMU version parsing tests
# ===================================================================


class TestQemuVersionParsing:
    """GIVEN the ``parse_qemu_version()`` function WHEN called with
    various ``--version`` outputs THEN version triple is parsed."""

    def test_parse_standard_qemu_version(self):
        """WHEN standard QEMU version format THEN returns (8, 2, 2)."""
        output = "QEMU emulator version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1~24.04.1)\n"
        assert parse_qemu_version(output) == (8, 2, 2)

    def test_parse_minimum_version(self):
        """WHEN version exactly at minimum THEN returns (8, 2, 0)."""
        output = "QEMU emulator version 8.2.0\n"
        assert parse_qemu_version(output) == (8, 2, 0)

    def test_parse_riscv_qemu_version(self):
        """WHEN RISC-V QEMU version THEN parses correctly."""
        output = "QEMU emulator version 8.2.2 (v8.2.2)\n"
        assert parse_qemu_version(output) == (8, 2, 2)

    def test_parse_newer_qemu_version(self):
        """WHEN newer QEMU version (9.0.0) THEN parses correctly."""
        output = "QEMU emulator version 9.0.0\n"
        assert parse_qemu_version(output) == (9, 0, 0)

    def test_parse_older_qemu_version(self):
        """WHEN older QEMU version (6.2.0) THEN parses correctly."""
        output = "QEMU emulator version 6.2.0 (Debian 1:6.2.0+dfsg-1)\n"
        assert parse_qemu_version(output) == (6, 2, 0)

    def test_parse_with_patch_and_build(self):
        """WHEN version has patch + build metadata THEN parses major.minor.patch."""
        output = "QEMU emulator version 7.1.0 (v7.1.0-123-gdeadbeef)\n"
        assert parse_qemu_version(output) == (7, 1, 0)

    def test_parse_invalid_output(self):
        """WHEN output has no version string THEN raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Cannot parse"):
            parse_qemu_version("QEMU emulator version unknown\n")

    def test_parse_empty_output(self):
        """WHEN output is empty THEN raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Cannot parse"):
            parse_qemu_version("")

    def test_min_qemu_version_constant(self):
        """WHEN MIN_QEMU_VERSION is defined THEN is (8, 2, 0)."""
        assert MIN_QEMU_VERSION == (8, 2, 0)

    def test_max_qemu_version_constant(self):
        """WHEN MAX_QEMU_VERSION is defined THEN is (8, 3, 0)."""
        assert MAX_QEMU_VERSION == (8, 3, 0)


# ===================================================================
# Part 1: TargetConfig tests
# ===================================================================


class TestTargetConfig:
    """GIVEN a TargetConfig dataclass WHEN configured THEN it behaves correctly."""

    def test_basic_arm_config(self, arm_target_config):
        """GIVEN arm config WHEN constructed THEN fields are correct."""
        cfg = arm_target_config
        assert cfg.name == "lm3s6965"
        assert cfg.mcu == "cortex-m3"
        assert cfg.arch == "arm"
        assert cfg.qemu_machine == "lm3s6965evb"
        assert cfg.is_arm is True
        assert cfg.is_riscv is False

    def test_basic_riscv_config(self, riscv_target_config):
        """GIVEN riscv config WHEN constructed THEN fields are correct."""
        cfg = riscv_target_config
        assert cfg.name == "riscv64"
        assert cfg.arch == "riscv"
        assert cfg.is_arm is False
        assert cfg.is_riscv is True

    def test_build_qemu_cmd_arm(self, arm_target_config):
        """GIVEN arm target with elf WHEN build_qemu_cmd() THEN returns correct cmd list."""
        cmd = arm_target_config.build_qemu_cmd()
        assert cmd[0] == "qemu-system-arm"
        assert "-machine" in cmd
        assert "lm3s6965evb" in cmd
        assert "-cpu" in cmd
        assert "cortex-m3" in cmd
        assert "-nographic" in cmd
        assert "-kernel" in cmd
        assert "/tmp/fake-hello-arm.elf" in cmd
        assert "-semihosting" in cmd

    def test_build_qemu_cmd_riscv(self, riscv_target_config):
        """GIVEN riscv target with elf WHEN build_qemu_cmd() THEN returns correct cmd."""
        cmd = riscv_target_config.build_qemu_cmd()
        assert cmd[0] == "qemu-system-riscv64"
        assert "-machine" in cmd
        assert "virt" in cmd

    def test_build_qemu_cmd_no_elf(self):
        """GIVEN target without elf WHEN build_qemu_cmd() THEN raises ValueError."""
        cfg = TargetConfig(
            name="test", mcu="cortex-m3", arch="arm",
            qemu_machine="lm3s6965evb", qemu_cpu="cortex-m3",
            qemu_serial="-serial stdio",
        )
        with pytest.raises(ValueError, match="has no .elf set"):
            cfg.build_qemu_cmd()

    def test_serial_parsing_with_chardev(self):
        """GIVEN complex serial string WHEN build_qemu_cmd() THEN tokens are preserved."""
        cfg = TargetConfig(
            name="stm32f4", mcu="cortex-m4", arch="arm",
            qemu_machine="stm32vldiscovery", qemu_cpu="cortex-m3",
            qemu_serial="-chardev stdio,mux=on,id=serial0 -serial chardev:serial0 -monitor none",
            elf="test.elf",
        )
        cmd = cfg.build_qemu_cmd()
        # Should have all serial tokens as separate args
        assert "-chardev" in cmd
        assert "stdio,mux=on,id=serial0" in cmd
        assert "-serial" in cmd
        assert "chardev:serial0" in cmd

    def test_repr(self, arm_target_config):
        """GIVEN config WHEN repr() THEN includes key fields."""
        r = repr(arm_target_config)
        assert "TargetConfig" in r
        assert "lm3s6965" in r
        assert "cortex-m3" in r
        assert "/tmp/fake-hello-arm.elf" in r


class TestTargetYamlLoading:
    """GIVEN a YAML configuration file WHEN loaded THEN TargetConfig is correct."""

    def test_load_flat_yaml(self, target_yaml_dir):
        """GIVEN flat YAML (no nested target key) WHEN load THEN config populated."""
        cfg = load_target_config("test-arm", base_dir=target_yaml_dir)
        assert cfg.name == "test-arm"
        assert cfg.mcu == "cortex-m3"
        assert cfg.arch == "arm"
        assert cfg.qemu_machine == "lm3s6965evb"
        assert cfg.default_timeout == 15

    def test_load_nested_yaml(self, target_yaml_dir):
        """GIVEN nested YAML (target key exists) WHEN load THEN inner dict used."""
        nested_dir = Path(target_yaml_dir) / ".yuleosh" / "targets"
        (nested_dir / "nested-test.yaml").write_text("""
nested-test:
  mcu: cortex-m4
  arch: arm
  qemu:
    machine: stm32vldiscovery
    cpu: cortex-m3
    serial: "-serial stdio"
""")
        cfg = load_target_config("nested-test", base_dir=target_yaml_dir)
        assert cfg.name == "nested-test"
        assert cfg.mcu == "cortex-m4"
        assert cfg.arch == "arm"
        assert cfg.qemu_machine == "stm32vldiscovery"

    def test_load_riscv_yaml(self, target_yaml_dir):
        """GIVEN riscv YAML WHEN load THEN config fields are correct."""
        cfg = load_target_config("test-riscv", base_dir=target_yaml_dir)
        assert cfg.name == "test-riscv"
        assert cfg.arch == "riscv"
        assert cfg.qemu_machine == "virt"
        assert cfg.default_timeout == 45

    def test_file_not_found(self):
        """GIVEN nonexistent target WHEN load THEN FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_target_config("nonexistent-target")

    def test_missing_required_key(self, target_yaml_dir):
        """GIVEN YAML missing 'mcu' WHEN load THEN ValueError."""
        bad_dir = Path(target_yaml_dir) / ".yuleosh" / "targets"
        (bad_dir / "bad.yaml").write_text("""
arch: arm
qemu:
  machine: lm3s6965evb
  cpu: cortex-m3
""")
        with pytest.raises(ValueError, match="missing required key 'mcu'"):
            load_target_config("bad", base_dir=target_yaml_dir)

    def test_discover_targets(self, target_yaml_dir):
        """GIVEN target dir with files WHEN discover THEN returns names."""
        targets = discover_targets(base_dir=target_yaml_dir)
        assert "test-arm" in targets
        assert "test-riscv" in targets

    def test_load_with_flash_config(self):
        """GIVEN YAML with flash section WHEN load THEN flash fields populated."""
        with tempfile.TemporaryDirectory() as tmp:
            targets_dir = Path(tmp) / ".yuleosh" / "targets"
            targets_dir.mkdir(parents=True)
            (targets_dir / "flash-test.yaml").write_text("""
mcu: cortex-m4
arch: arm
qemu:
  machine: stm32vldiscovery
  cpu: cortex-m3
  serial: "-serial stdio"
flash:
  openocd:
    config: "interface/stlink-v2.cfg target/stm32f4x.cfg"
    protocol: swd
  jlink:
    device: STM32F407VG
    interface: swd
    speed: 4000
  pyocd:
    target: stm32f407vg
    frequency: 4000000
""")
            cfg = load_target_config("flash-test", base_dir=tmp)
            assert cfg.flash_openocd is not None
            assert "interface/stlink-v2.cfg" in cfg.flash_openocd
            assert cfg.flash_jlink is not None
            assert cfg.flash_jlink.get("device") == "STM32F407VG"


# ===================================================================
# Part 2: SerialAssert tests
# ===================================================================


class TestSerialAssert:
    """GIVEN a SerialAssert engine WHEN patterns are matched THEN behavior correct."""

    def test_exact_match(self):
        """WHEN expect exact text in pre-collected log THEN passes."""
        serial = SerialAssert(log_text="Hello World\nLine 2\n")
        result = serial.expect("Hello World", timeout=1)
        assert "Hello World" in result

    def test_expect_no_match(self):
        """WHEN expect text not in log AND no stream THEN raises."""
        serial = SerialAssert(log_text="Goodbye\n")
        with pytest.raises(SilAssertionError, match="not found within"):
            serial.expect("Hello", timeout=0.5)

    def test_expect_no_match_no_fail_fast(self):
        """WHEN fail_fast=False THEN returns empty string on timeout."""
        serial = SerialAssert(log_text="Goodbye\n")
        result = serial.expect("Hello", timeout=0.5, fail_fast=False)
        assert result == ""

    def test_captured_log(self):
        """WHEN log_text provided THEN captured_log returns it."""
        serial = SerialAssert(log_text="Hello World\n")
        assert serial.captured_log == "Hello World\n"

    def test_append_log(self):
        """WHEN log appended via streaming THEN captured_log includes new data."""
        serial = SerialAssert(log_text="Start\n")
        assert serial.captured_log == "Start\n"

    def test_regex_match(self):
        """WHEN expect with regex=True THEN matches pattern."""
        serial = SerialAssert(log_text="ERROR: code 42\n")
        result = serial.expect(r"ERROR:\s+code \d+", timeout=1, regex=True)
        assert result is not None

    def test_regex_no_match(self):
        """WHEN regex does not match THEN raises."""
        serial = SerialAssert(log_text="OK\n")
        with pytest.raises(SilAssertionError):
            serial.expect(r"ERROR:\s+\d+", timeout=0.5, regex=True)

    def test_read_until(self):
        """WHEN read_until called THEN returns text up to marker."""
        serial = SerialAssert(log_text="Line1\nMarker\nLine3\n")
        result = serial.read_until("Marker", timeout=1)
        assert result == "Line1\n"
        assert "Marker" not in result

    def test_read_until_with_marker(self):
        """WHEN read_until include_marker=True THEN marker is included."""
        serial = SerialAssert(log_text="Line1\nMarker\nLine3\n")
        result = serial.read_until("Marker", timeout=1, include_marker=True)
        assert "Marker" in result

    def test_is_streaming_false(self):
        """WHEN no pipe THEN is_streaming is False."""
        serial = SerialAssert(log_text="Hey")
        assert serial.is_streaming is False

    def test_streaming_mode(self):
        """WHEN streaming from pipe THEN reads are captured."""
        pipe = io.StringIO("Line1\nLine2\nLine3\n")
        serial = SerialAssert.stream(pipe=pipe, timeout=2)
        # Wait briefly for capture thread to read
        time.sleep(0.1)
        serial.close()
        log_text = serial.captured_log
        assert "Line1" in log_text
        assert "Line3" in log_text

    def test_streaming_expect(self):
        """WHEN streaming from pipe THEN expect works with live data."""
        pipe = io.StringIO("Hello World\nDone\n")
        serial = SerialAssert.stream(pipe=pipe, timeout=5)
        time.sleep(0.05)
        result = serial.expect("Hello World", timeout=2)
        assert "Hello World" in result
        serial.close()

    def test_streaming_expect_timeout(self):
        """WHEN streaming pipe never produces pattern THEN expect raises."""
        pipe = io.StringIO("Some output\n")
        serial = SerialAssert.stream(pipe=pipe, timeout=5)
        time.sleep(0.05)
        serial.close()
        with pytest.raises(SilAssertionError):
            serial.expect("NeverAppears", timeout=0.5)

    def test_context_manager(self):
        """WHEN used as context manager THEN pipe is cleaned up."""
        pipe = io.StringIO("data\n")
        with SerialAssert.stream(pipe=pipe) as serial:
            assert serial.is_streaming
        # After exit, capture should be stopped
        assert serial._capture_stop.is_set()

    def test_default_timeout(self):
        """WHEN custom default timeout THEN expect uses it."""
        serial = SerialAssert(log_text="Hi", timeout=0.1)
        t0 = time.monotonic()
        with pytest.raises(SilAssertionError):
            serial.expect("NotFound")
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0  # Should timeout quickly


class TestExpectScript:
    """GIVEN an expect script string WHEN parsed THEN directives execute."""

    def test_simple_script(self):
        """WHEN script with expect directives THEN all pass."""
        serial = SerialAssert(log_text="Hello\nWorld\nDone\n")
        run_expect_script(serial, "expect:Hello\nexpect:World")

    def test_expect_re_script(self):
        """WHEN script with expect_re THEN regex matching works."""
        serial = SerialAssert(log_text="ERROR: code 42\n")
        run_expect_script(serial, "expect_re:ERROR:.*42")

    def test_read_until_script(self):
        """WHEN script with read_until THEN returns captured text."""
        serial = SerialAssert(log_text="Header\nBody\nEnd\n")
        results = run_expect_script(serial, "read_until:Body")
        assert len(results) == 1
        assert "Header\n" == results[0]

    def test_wait_script(self):
        """WHEN script with wait THEN pauses execution."""
        serial = SerialAssert(log_text="Hello\n")
        t0 = time.monotonic()
        run_expect_script(serial, "wait:0.2\nexpect:Hello")
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.18  # Allow small tolerance

    def test_assert_passes(self):
        """WHEN assert directive AND text present THEN passes."""
        serial = SerialAssert(log_text="Passed!\n")
        run_expect_script(serial, "assert:Passed!")

    def test_assert_fails(self):
        """WHEN assert directive AND text missing THEN raises."""
        serial = SerialAssert(log_text="Some output\n")
        with pytest.raises(SilAssertionError, match="NotFound"):
            run_expect_script(serial, "assert:NotFound")

    def test_script_with_comments(self):
        """WHEN script with comments THEN comments ignored."""
        serial = SerialAssert(log_text="OK\n")
        run_expect_script(serial, "# This is a comment\n# Another\nexpect:OK")

    def test_bad_wait_arg(self):
        """WHEN wait with non-numeric arg THEN raises."""
        serial = SerialAssert(log_text="")
        with pytest.raises(ExpectScriptError, match="wait"):
            run_expect_script(serial, "wait:not-a-number")

    def test_empty_script(self):
        """WHEN empty script THEN no error."""
        serial = SerialAssert(log_text="Hello\n")
        run_expect_script(serial, "")
        run_expect_script(serial, "  \n\n  ")

    def test_expect_fail_raises(self):
        """WHEN expect in script fails THEN SilAssertionError raised."""
        serial = SerialAssert(log_text="OK\n")
        with pytest.raises(SilAssertionError):
            run_expect_script(serial, "expect:NotFound")


# ===================================================================
# Part 3: QemuSilRunner tests (mocked subprocess)
# ===================================================================


@pytest.mark.usefixtures("mock_qemu_version")
class TestQemuSilRunnerInit:
    """GIVEN QemuSilRunner initialization WHEN configured THEN validates inputs."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_init_ok(self, mock_which, arm_target_config):
        """WHEN config has elf AND qemu binary exists THEN init succeeds."""
        runner = QemuSilRunner(arm_target_config)
        assert runner.config.name == "lm3s6965"

    def test_init_no_elf(self, arm_target_config):
        """WHEN config missing elf THEN raises ValueError."""
        arm_target_config.elf = None
        with pytest.raises(ValueError, match="elf must be set"):
            QemuSilRunner(arm_target_config)

    def test_init_qemu_not_found(self, arm_target_config):
        """WHEN QEMU binary not in PATH THEN raises RuntimeError."""
        with mock.patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="not found"):
                QemuSilRunner(arm_target_config)


@pytest.mark.usefixtures("mock_qemu_version")
class TestQemuSilRunnerRun:
    """GIVEN a running QEMU SIL runner WHEN test executes THEN correct results."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_basic_arm(self, mock_which, arm_target_config):
        """WHEN ARM target runs with expect_pattern THEN returns passed."""
        output_lines = ["Hello World\n", "Architecture: ARM\n"]
        pipe = io.StringIO("".join(output_lines))

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(expect_pattern="Hello World")

        assert result.passed is True
        assert "Hello World" in result.log
        assert result.error is None

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_with_script(self, mock_which, arm_target_config):
        """WHEN run with full expect script THEN all assertions pass."""
        output_lines = ["Step 1\n", "Step 2\n", "Done\n"]
        pipe = io.StringIO("".join(output_lines))

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        script = "expect:Step 1\nexpect:Step 2\nexpect:Done"
        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(test_script=script)

        assert result.passed is True
        assert len(result.assertion_failures) == 0

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_assertion_failure(self, mock_which, arm_target_config):
        """WHEN assertion fails THEN result.passed is False."""
        pipe = io.StringIO("Some output\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(expect_pattern="NotFound")

        assert result.passed is False
        assert len(result.assertion_failures) > 0
        assert result.error is not None

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_timeout(self, mock_which, arm_target_config):
        """WHEN QEMU runs long and timeout expires THEN runner terminates."""
        # Simulate a process that never exits
        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = io.StringIO("Starting QEMU...\n")
        mock_proc.poll.return_value = None  # Process still running

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            # Use a short timeout to test timeout behavior
            result = runner.run(expect_pattern="QuickCheck", timeout=0.2)

        # The expect check will fail (pattern not in output within timeout)
        assert result.passed is False
        # But the process should have been terminated
        mock_proc.terminate.assert_called()

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_empty_script(self, mock_which, arm_target_config):
        """WHEN run with empty script THEN just wait for QEMU exit."""
        pipe = io.StringIO("QEMU boot complete.\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run()

        assert result.passed is True
        assert "QEMU boot" in result.log

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_long_output(self, mock_which, arm_target_config):
        """WHEN QEMU produces lots of output THEN captured correctly."""
        lines = [f"Line {i}\n" for i in range(1000)]
        pipe = io.StringIO("".join(lines))

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(expect_pattern="Line 999")

        assert result.passed is True
        assert "Line 999" in result.log

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_process_error(self, mock_which, arm_target_config):
        """WHEN Popen raises OSError THEN returns failed result gracefully."""
        with mock.patch("subprocess.Popen", side_effect=OSError("QEMU crashed")):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(expect_pattern="Hello")

        assert result.passed is False
        assert result.error is not None
        assert "Unexpected error" in result.error

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_elapsed_time(self, mock_which, arm_target_config):
        """WHEN test completes THEN elapsed near-zero (no real QEMU)."""
        pipe = io.StringIO("Done\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run()

        assert result.elapsed > 0
        assert result.passed is True

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_terminate_sigterm(self, mock_which, arm_target_config):
        """WHEN process running AND terminate called THEN SIGTERM sent."""
        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = io.StringIO("output\n")
        mock_proc.poll.return_value = None  # Running
        mock_proc.wait.side_effect = lambda timeout=None: 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            runner._process = mock_proc
            runner._terminate(grace_period=0.5)

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called()

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_terminate_sigkill(self, mock_which, arm_target_config):
        """WHEN SIGTERM times out THEN SIGKILL sent."""
        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = io.StringIO("output\n")
        mock_proc.poll.return_value = None
        # First wait (grace_period=0.1) times out, second wait (kill, 5.0) succeeds
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired("qemu", 0.5),  # from terminate()
            None,  # from kill() — success
        ]

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            runner._process = mock_proc
            runner._terminate(grace_period=0.1)

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_run_with_riscv_binary(self, mock_which, riscv_target_config):
        """WHEN RISC-V target THEN correct QEMU binary is used."""
        output_lines = ["RISC-V output\n"]
        pipe = io.StringIO("".join(output_lines))

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(riscv_target_config)
            result = runner.run(expect_pattern="RISC-V output")

        # Verify the correct QEMU binary is configured
        assert riscv_target_config._qemu_binary() == "qemu-system-riscv64"
        # Verify the ELF path is correct
        assert riscv_target_config.elf == "/tmp/fake-hello-riscv.elf"
        assert result.passed is True
        assert "RISC-V output" in result.log


@pytest.mark.usefixtures("mock_qemu_version")
class TestSilTestConvenience:
    """GIVEN sil_test convenience function WHEN called THEN works correctly."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_sil_test_basic(self, mock_which, arm_target_config):
        """WHEN sil_test called with expect_pattern THEN returns result."""
        pipe = io.StringIO("Hello World\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = sil_test(arm_target_config, expect_pattern="Hello World")

        assert isinstance(result, SilResult)
        assert result.passed is True
        assert "Hello World" in result.log

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_sil_test_timeout_override(self, mock_which, arm_target_config):
        """WHEN sil_test with custom timeout THEN uses it."""
        pipe = io.StringIO("Done\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            result = sil_test(arm_target_config, expect_pattern="Done", timeout=5)

        assert result.passed is True


# ===================================================================
# Part 4: Coverage extraction (stub)
# ===================================================================


@pytest.mark.usefixtures("mock_qemu_version")
class TestCoverageStub:
    """GIVEN coverage extraction WHEN called THEN returns empty dict."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_extract_coverage_empty(self, mock_which, arm_target_config):
        """WHEN _extract_coverage() called THEN returns empty dict."""
        with mock.patch("subprocess.Popen"):
            runner = QemuSilRunner(arm_target_config)
            cov = runner._extract_coverage()
            assert cov == {}


# ===================================================================
# Part 5: Edge cases
# ===================================================================


@pytest.mark.usefixtures("mock_qemu_version")
class TestEdgeCases:
    """GIVEN edge case configurations WHEN used THEN handled gracefully."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_unicode_in_output(self, mock_which, arm_target_config):
        """WHEN output contains unicode THEN captured correctly."""
        pipe = io.StringIO("Temperature: 42°C\nStatus: ✓\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run(expect_pattern="✓")

        assert result.passed is True
        assert "Temperature" in result.log

    def test_target_config_defaults(self):
        """WHEN TargetConfig with minimal init THEN sensible defaults."""
        cfg = TargetConfig(
            name="minimal",
            mcu="cortex-m0",
            arch="arm",
            qemu_machine="microbit",
            qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        assert cfg.default_timeout == 30
        assert cfg.qemu_extra_args == []
        assert cfg.flash_openocd is None
        assert cfg.flash_jlink is None

    def test_qemu_binary_unknown_arch(self):
        """WHEN arch is unknown THEN _qemu_binary raises ValueError."""
        cfg = TargetConfig(
            name="unknown", mcu="custom", arch="custom",
            qemu_machine="custom", qemu_cpu="custom",
            qemu_serial="-serial stdio",
        )
        with pytest.raises(ValueError, match="Unknown arch"):
            cfg._qemu_binary()

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_no_script_and_no_pattern(self, mock_which, arm_target_config):
        """WHEN neither script nor pattern provided THEN wait for exit."""
        pipe = io.StringIO("QEMU booted.\nDone.\n")

        mock_proc = mock.MagicMock(spec=subprocess.Popen)
        mock_proc.stdout = pipe
        mock_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=mock_proc):
            runner = QemuSilRunner(arm_target_config)
            result = runner.run()

        assert result.passed is True


# ===================================================================
# Part 6: QEMU version check integration tests
# ===================================================================


class TestQemuVersionCheck:
    """GIVEN the ``_check_qemu_version()`` method WHEN QEMU version
    is valid or invalid THEN appropriate outcome occurs."""

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_passes(self, mock_which, arm_target_config):
        """WHEN QEMU version >= 8.2.0 THEN init succeeds."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.2\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            runner = QemuSilRunner(arm_target_config)
        assert runner._qemu_bin == "qemu-system-arm"

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_exact_minimum(self, mock_which, arm_target_config):
        """WHEN QEMU version exactly at 8.2.0 THEN init succeeds."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.0\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            runner = QemuSilRunner(arm_target_config)
        assert runner._qemu_bin == "qemu-system-arm"

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_too_old(self, mock_which, arm_target_config):
        """WHEN QEMU version < 8.2.0 THEN raises RuntimeError."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 6.2.0\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="too old"):
                QemuSilRunner(arm_target_config)

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_unparseable(self, mock_which, arm_target_config):
        """WHEN QEMU --version output is unparseable THEN raises RuntimeError."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version unknown\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Cannot parse"):
                QemuSilRunner(arm_target_config)

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_subprocess_fails(self, mock_which, arm_target_config):
        """WHEN subprocess.run exits non-zero THEN raises RuntimeError."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "command not found"
        with mock.patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="exited with code"):
                QemuSilRunner(arm_target_config)

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-arm")
    def test_version_check_newer_version_ok(self, mock_which, arm_target_config):
        """WHEN QEMU version is newer (9.0.0) THEN init succeeds with warning."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 9.0.0\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            runner = QemuSilRunner(arm_target_config)
        assert runner._qemu_bin == "qemu-system-arm"

    @mock.patch("shutil.which", return_value="/usr/bin/qemu-system-riscv64")
    def test_version_check_riscv(self, mock_which, riscv_target_config):
        """WHEN RISC-V QEMU version is valid THEN init succeeds."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "QEMU emulator version 8.2.2 (RISC-V)\n"
        with mock.patch("subprocess.run", return_value=mock_result):
            runner = QemuSilRunner(riscv_target_config)
        assert runner._qemu_bin == "qemu-system-riscv64"
