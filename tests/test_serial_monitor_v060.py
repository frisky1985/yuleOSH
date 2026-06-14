# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for SerialMonitor base class and PipeSerialMonitor edge cases (v0.6.0).
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
    PipeSerialMonitor,
    SerialMonitor,
    SerialMonitorTimeout,
)


class TestSerialMonitorBaseClass:
    """Test SerialMonitor base class methods directly."""

    def _make(self):
        mon = SerialMonitor(port="/dev/null", baud=115200)
        mon._captured = ["line1\n", "line2\n", "PATTERN_FOUND\n", "line4\n"]
        mon._lock = threading.Lock()
        mon._open_time = time.monotonic()
        mon._stop_event = threading.Event()
        mon._pyserial_mod = mock.MagicMock()
        return mon

    def test_captured_log_concat(self):
        assert "PATTERN_FOUND" in self._make().captured_log

    def test_captured_log_empty(self):
        mon = SerialMonitor(port="/dev/null", baud=115200)
        mon._lock = threading.Lock()
        mon._captured = []
        assert mon.captured_log == ""

    def test_assert_text_present_ok(self):
        assert self._make().assert_text_present("PATTERN_FOUND") is True

    def test_assert_text_present_missing(self):
        assert self._make().assert_text_present("MISSING") is False

    def test_assert_text_absent_ok(self):
        assert self._make().assert_text_absent("MISSING") is True

    def test_assert_text_absent_fail(self):
        assert self._make().assert_text_absent("PATTERN_FOUND") is False

    def test_clear(self):
        mon = self._make()
        mon.clear()
        assert mon.captured_log == ""

    def test_read_until_match(self):
        mon = self._make()
        result = mon.read_until("PATTERN_FOUND", timeout=1)
        assert "PATTERN_FOUND" in result

    def test_expect_match_existing(self):
        assert self._make().expect("PATTERN_FOUND", timeout=0.5) == "PATTERN_FOUND"

    def test_expect_timeout(self):
        with pytest.raises(SerialMonitorTimeout):
            self._make().expect("NEVER", timeout=0.2)

    def test_expect_fail_fast_false(self):
        r = self._make().expect("NEVER", timeout=0.2, fail_fast=False)
        assert r == ""

    def test_expect_regex_match(self):
        r = self._make().expect(r"PATTERN_\w+", timeout=1, regex=True)
        assert r == "PATTERN_FOUND"

    def test_expect_regex_no_match(self):
        mon = self._make()
        mon._captured = ["abc123\n"]
        with pytest.raises(SerialMonitorTimeout):
            mon.expect(r"\d{6}", timeout=0.2, regex=True)

    def test_expect_all_sequential(self):
        mon = self._make()
        mon._captured = ["A\n", "B\n", "C\n"]
        assert mon.expect_all(["A", "B"], timeout=2) == ["A", "B"]

    def test_expect_all_empty(self):
        assert self._make().expect_all([], timeout=1) == []

    def test_wait_silent(self):
        assert self._make().wait_silent(duration=0.1) is True

    def test_close_clean(self):
        mon = self._make()
        mon._serial = mock.MagicMock()
        mon._capture_thread = None
        mon.close()

    def test_close_double(self):
        mon = self._make()
        mon._serial = mock.MagicMock()
        mon._capture_thread = None
        mon.close()
        mon.close()

    def test_close_serial_error(self):
        mon = self._make()
        mon._serial = mock.MagicMock()
        mon._serial.close.side_effect = OSError("port error")
        mon._capture_thread = None
        mon.close()


class TestPipeSerialMonitorEdgeV060:
    """Test PipeSerialMonitor edge cases."""

    def test_close_pipe_error(self):
        pipe = io.StringIO("data\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        pipe.close = mock.MagicMock(side_effect=OSError("IO"))
        mon.close()

    def test_expect_all_pipe(self):
        pipe = io.StringIO("A\nB\nC\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        time.sleep(0.3)
        results = mon.expect_all(["A", "B", "C"], timeout=3)
        assert len(results) == 3
        mon.close()

    def test_is_streaming_active(self):
        pipe = io.StringIO("data\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        assert mon.is_streaming is True
        mon.close()

    def test_is_streaming_after_close(self):
        pipe = io.StringIO("data\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        mon.close()
        time.sleep(0.1)
        assert mon.is_streaming is False

    def test_expect_regex_pipe(self):
        pipe = io.StringIO("Temperature: 42\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        time.sleep(0.3)
        assert mon.expect(r"\d+", timeout=3, regex=True) == "42"
        mon.close()

    def test_expect_regex_no_match_pipe(self):
        pipe = io.StringIO("abc\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        time.sleep(0.2)
        with pytest.raises(SerialMonitorTimeout):
            mon.expect(r"\d{10}", timeout=0.3, regex=True)
        mon.close()

    def test_expect_fail_fast_pipe(self):
        pipe = io.StringIO("abc\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        time.sleep(0.2)
        assert mon.expect("NONEXISTENT", timeout=0.3, fail_fast=False) == ""
        mon.close()

    def test_captured_log_pipe(self):
        pipe = io.StringIO("Hello\nWorld\n")
        mon = PipeSerialMonitor(pipe=pipe, timeout=5)
        time.sleep(0.3)
        assert "Hello" in mon.captured_log
        assert "World" in mon.captured_log
        mon.close()
