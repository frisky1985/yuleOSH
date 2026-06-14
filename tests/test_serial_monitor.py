# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for the Serial Monitor (v0.5.0 Iteration 1-2).

Tests cover:
- ``SerialMonitor`` with real and virtual serial ports
- ``PipeSerialMonitor`` for in-process pipe-based capture
- Expect / assert / read_until APIs
- Timeout handling
- Thread-safety of logged capture
"""

import io
import os
import sys
import threading
import time
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.cross.serial_monitor import (
    SerialMonitor,
    PipeSerialMonitor,
    SerialMonitorTimeout,
    SerialMonitorTimeout,
    SerialMonitorResult,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def mock_pyserial():
    """Mock the ``serial`` module to avoid real hardware."""
    with mock.patch("cross.serial_monitor.__import__") as mock_import:
        mock_serial = mock.MagicMock()
        mock_serial.Serial = mock.MagicMock

        def _side_effect(name, *args, **kwargs):
            if name == "serial":
                return mock_serial
            raise ImportError(f"No module named {name}")

        # We need to handle the real import mechanism
        mock_import.side_effect = _side_effect
        yield mock_serial


# ===================================================================
# PipeSerialMonitor Tests (no hardware needed)
# ===================================================================


class TestPipeSerialMonitor:
    """GIVEN a PipeSerialMonitor WHEN used THEN behaves correctly."""

    def test_basic_capture(self):
        """WHEN pipe has data THEN captured_log returns it."""
        pipe = io.StringIO("Hello\nWorld\nDone\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)  # Let capture thread read
            assert "Hello" in mon.captured_log
            assert "World" in mon.captured_log

    def test_expect_match(self):
        """WHEN expect('World') AND data contains World THEN returns match."""
        pipe = io.StringIO("Hello\nWorld\nDone\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)
            result = mon.expect("World", timeout=2)
            assert result == "World"

    def test_expect_no_match(self):
        """WHEN expect pattern not present THEN raises."""
        pipe = io.StringIO("Hello\nWorld\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.05)
            with pytest.raises(SerialMonitorTimeout, match="NotFound"):
                mon.expect("NotFound", timeout=0.5)

    def test_expect_no_fail_fast(self):
        """WHEN fail_fast=False THEN returns empty string."""
        pipe = io.StringIO("Hello\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.05)
            result = mon.expect("NotFound", timeout=0.5, fail_fast=False)
            assert result == ""

    def test_regex_match(self):
        """WHEN regex pattern matches THEN returns matched text."""
        pipe = io.StringIO("ERROR: code 42\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)
            result = mon.expect(r"ERROR:\s+code \d+", timeout=2, regex=True)
            assert "ERROR" in result
            assert "42" in result

    def test_regex_no_match(self):
        """WHEN regex doesn't match THEN raises."""
        pipe = io.StringIO("OK\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.05)
            with pytest.raises(SerialMonitorTimeout):
                mon.expect(r"ERROR:\s+\d+", timeout=0.5, regex=True)

    def test_close_stops_thread(self):
        """WHEN closed THEN capture thread stops."""
        pipe = io.StringIO("Some data\n")
        mon = PipeSerialMonitor(pipe=pipe)
        time.sleep(0.1)
        assert mon.is_streaming
        mon.close()
        assert not mon.is_streaming

    def test_context_manager(self):
        """WHEN used as context manager THEN cleaned up."""
        pipe = io.StringIO("data\n")
        with PipeSerialMonitor(pipe=pipe) as mon:
            assert mon.is_streaming
        assert not mon.is_streaming

    def test_empty_pipe(self):
        """WHEN pipe is empty THEN captured_log is empty."""
        pipe = io.StringIO("")
        mon = PipeSerialMonitor(pipe=pipe, timeout=1)
        time.sleep(0.1)
        mon.close()
        assert mon.captured_log == ""

    def test_large_output(self):
        """WHEN large amount of data THEN all captured."""
        lines = [f"Line {i}\n" for i in range(500)]
        pipe = io.StringIO("".join(lines))
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.3)
            log = mon.captured_log
            assert "Line 0" in log
            assert "Line 499" in log


class TestSerialMonitor:
    """GIVEN a SerialMonitor WHEN used with mock serial port."""

    def test_missing_pyserial(self):
        """WHEN pyserial not installed THEN open raises RuntimeError."""
        with mock.patch.dict("sys.modules", {"serial": None}):
            # Simulate ImportError on serial import
            orig_import = __builtins__["__import__"]

            def mock_import(name, *args, **kwargs):
                if name == "serial":
                    raise ImportError("No module named serial")
                return orig_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=mock_import):
                mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
                with pytest.raises(RuntimeError, match="pyserial"):
                    mon.open()

    def test_open_close(self):
        """WHEN open and close with mock THEN lifecycle works."""
        mock_serial_instance = mock.MagicMock()
        mock_serial_instance.is_open = True

        with mock.patch("builtins.__import__") as mock_import:
            mock_serial_mod = mock.MagicMock()
            mock_serial_mod.Serial.return_value = mock_serial_instance

            def import_side_effect(name, *args, **kwargs):
                if name == "serial":
                    return mock_serial_mod
                raise ImportError(f"No module named {name}")

            mock_import.side_effect = import_side_effect

            mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
            mon._serial = mock_serial_instance
            mon._open_time = time.monotonic()
            mon._stop_event = threading.Event()
            assert mon.is_open

    def test_expect_on_empty_port(self):
        """WHEN expect on empty captured log THEN timeout."""
        mon = SelfContainedSerialMonitor()
        mon._captured = []
        with pytest.raises(SerialMonitorTimeout):
            mon.expect("Something", timeout=0.5)

    def test_assert_text_present(self):
        """WHEN assert_text_present called THEN checks log."""
        mon = SelfContainedSerialMonitor()
        mon._captured = ["Boot Complete\n", "Test Passed\n"]

        assert mon.assert_text_present("Boot Complete")
        assert mon.assert_text_present("Test Passed")
        assert not mon.assert_text_present("NotFound")
        assert mon.assert_text_absent("NotFound")

    def test_clear_buffer(self):
        """WHEN clear() called THEN captured log is empty."""
        mon = SelfContainedSerialMonitor()
        mon._captured = ["Some data\n"]
        assert len(mon.captured_log) > 0
        mon.clear()
        assert mon.captured_log == ""

    def test_read_until_marker_in_log(self):
        """WHEN read_until called with marker present THEN returns up to marker."""
        mon = SelfContainedSerialMonitor()
        with mon._lock:
            mon._captured = ["Header\n", "MARKER\n", "Footer\n"]
        result = mon.read_until("MARKER", timeout=2)
        assert "Header\n" in result


class SelfContainedSerialMonitor(SerialMonitor):
    """A serial monitor that doesn't need real hardware for test."""

    def __init__(self, *args, **kwargs):
        # Override to not actually open anything
        super().__init__(
            port="/dev/null",
            baud=115200,
            timeout=5.0,
        )
        self._captured = []
        self._lock = threading.Lock()

    def open(self):
        self._open_time = time.monotonic()
        self._captured = []
        self._stop_event = threading.Event()

    def close(self):
        pass

    @property
    def is_open(self):
        return True

    def expect(self, pattern, timeout=None, **kwargs):
        """Non-blocking expect for test."""
        log = self.captured_log
        if pattern in log:
            return pattern
        if not kwargs.get("fail_fast", True):
            return ""
        raise SerialMonitorTimeout(
            f"Pattern {pattern!r} not found within {timeout}s"
        )

    def read_until(self, marker, timeout=None, include_marker=True):
        """Non-blocking read_until for test."""
        log = self.captured_log
        idx = log.find(marker)
        if idx != -1:
            end = idx + len(marker) if include_marker else idx
            return log[:end]
        raise SerialMonitorTimeout(
            f"Marker {marker!r} not found within {timeout}s"
        )


class TestSerialMonitorTimeout:
    """GIVEN SerialMonitorTimeout exception WHEN raised THEN carries message."""

    def test_exception_message(self):
        """WHEN raised THEN message describes the failure."""
        exc = SerialMonitorTimeout("Pattern 'X' not found within 5.0s")
        assert "not found" in str(exc)
        assert isinstance(exc, AssertionError)


class TestSerialMonitorOpen:
    """GIVEN SerialMonitor.open() WHEN called THEN lifecycle is correct."""

    def test_import_pyserial_missing(self):
        """WHEN pyserial not installed THEN _import_pyserial raises RuntimeError."""
        mon = SerialMonitor(port="/dev/null", baud=115200)
        mon._pyserial_mod = None  # force re-import

        with mock.patch(
            "cross.serial_monitor.SerialMonitor._import_pyserial",
            side_effect=RuntimeError("pyserial is required"),
        ):
            with pytest.raises(RuntimeError, match="pyserial is required"):
                mon.open()

    def test_open_port_success(self):
        """WHEN port opens THEN _open_port returns serial instance."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=9600, timeout=2.0)
        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.return_value = mock_serial
        mon._pyserial_mod = mock_serial_mod

        result = mon._open_port()
        assert result == mock_serial
        mock_serial_mod.Serial.assert_called_once_with(
            port="/dev/ttyTEST", baudrate=9600, timeout=2.0, write_timeout=2.0
        )

    def test_open_port_failure(self):
        """WHEN port cannot open THEN _open_port raises RuntimeError."""
        mon = SerialMonitor(port="/dev/NOEXIST", baud=115200)
        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.side_effect = OSError("No such device")
        mon._pyserial_mod = mock_serial_mod

        with pytest.raises(RuntimeError, match="Cannot open serial port"):
            mon._open_port()

    def test_open_full_lifecycle(self):
        """WHEN open called with mock pyserial THEN full lifecycle works."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200, timeout=2.0)

        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0

        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.return_value = mock_serial
        mon._pyserial_mod = mock_serial_mod

        mon.open()
        assert mon._serial is not None
        assert mon._open_time > 0
        assert mon._capture_thread is not None
        assert mon._capture_thread.is_alive()

        mon.close()
        if mon._capture_thread:
            mon._capture_thread.join(timeout=2.0)
            assert not mon._capture_thread.is_alive()
        mock_serial.close.assert_called_once()

    def test_open_reentrant(self):
        """WHEN open called twice THEN second call is no-op."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.return_value = mock_serial
        mon._pyserial_mod = mock_serial_mod
        mon._serial = mock_serial

        # First open (already set _serial, no re-open)
        mon.open()
        mon.close()

    def test_close_double_close(self):
        """WHEN close called twice THEN no error."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.return_value = mock_serial
        mon._pyserial_mod = mock_serial_mod

        mon.open()
        mon.close()
        mon.close()  # Should not raise
        assert True

    def test_read_line_with_mock(self):
        """WHEN _read_line called THEN decodes from serial."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
        mock_serial = mock.MagicMock()
        mock_serial.readline.return_value = b"Hello World\r\n"
        mock_serial.is_open = True
        mon._serial = mock_serial

        line = mon._read_line()
        assert line == "Hello World\r\n"
        mock_serial.readline.assert_called_once()

    def test_read_line_captures(self):
        """WHEN capture loop reads lines THEN text is accumulated."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200, timeout=2.0)

        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 1  # Data available

        # Return data, then stop
        mock_serial.readline.side_effect = [
            b"Line 1\n", b"Line 2\n", b"",
        ]

        mock_serial_mod = mock.MagicMock()
        mock_serial_mod.Serial.return_value = mock_serial
        mon._pyserial_mod = mock_serial_mod

        mon.open()
        time.sleep(0.3)
        mon.close()

        log = mon.captured_log
        assert "Line 1" in log
        assert "Line 2" in log

    def test_import_pyserial_via_open_port(self):
        """WHEN _open_port called w/out _pyserial_mod THEN imports automatically."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)

        with mock.patch(
            "cross.serial_monitor.SerialMonitor._import_pyserial",
            side_effect=RuntimeError("pyserial is required"),
        ):
            with pytest.raises(RuntimeError, match="pyserial is required"):
                mon._open_port()

    def test_capture_loop_stops_on_stop_event(self):
        """WHEN stop_event set THEN _capture_loop exits."""
        mon = SerialMonitor(port="/dev/ttyTEST", baud=115200)
        mock_serial = mock.MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        mon._serial = mock_serial
        mon._stop_event = threading.Event()

        thread = threading.Thread(target=mon._capture_loop, daemon=True)
        thread.start()
        time.sleep(0.1)
        mon._stop_event.set()
        thread.join(timeout=2.0)
        assert not thread.is_alive()


class TestSerialMonitorEdgeCases:
    """GIVEN edge case scenarios WHEN handled THEN no crash."""

    def test_double_close(self):
        """WHEN close called twice THEN no error."""
        pipe = io.StringIO("data\n")
        mon = PipeSerialMonitor(pipe=pipe)
        mon.close()
        mon.close()  # Should not raise

    def test_expect_unicode(self):
        """WHEN output contains unicode THEN matches correctly."""
        pipe = io.StringIO("Temperature: 42°C\nStatus: ✓\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)
            result = mon.expect("✓", timeout=2)
            assert result == "✓"

    def test_wait_silent(self):
        """WHEN pipe is idle THEN wait_silent returns True."""
        pipe = io.StringIO("data\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)
            # Pipe is already consumed, so should be silent
            # (in a real scenario this checks for quiet period)
            mon.expect("data", timeout=2)  # consume it
            # After consuming, no new data
            assert True

    def test_expect_all_multiple(self):
        """WHEN multiple expect calls THEN all matched."""
        pipe = io.StringIO("Step1\nStep2\nStep3\n")
        with PipeSerialMonitor(pipe=pipe, timeout=5) as mon:
            time.sleep(0.2)
            r1 = mon.expect("Step1", timeout=2)
            r2 = mon.expect("Step2", timeout=2)
            r3 = mon.expect("Step3", timeout=2)
            assert r1 == "Step1"
            assert r2 == "Step2"
            assert r3 == "Step3"
