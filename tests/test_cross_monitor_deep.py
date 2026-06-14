"""Deep tests for cross.serial_monitor — SerialMonitor, PipeSerialMonitor."""

import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from yuleosh.cross.serial_monitor import (
    SerialMonitor,
    SerialMonitorResult,
    SerialMonitorTimeout,
    PipeSerialMonitor,
)


class TestSerialMonitorResult:
    def test_defaults(self):
        r = SerialMonitorResult()
        assert r.passed is True
        assert r.log == ""
        assert r.elapsed == 0.0
        assert r.assertion_failures == []


class TestSerialMonitorTimeout:
    def test_is_assertion_error(self):
        assert issubclass(SerialMonitorTimeout, AssertionError)

    def test_can_raise(self):
        with pytest.raises(SerialMonitorTimeout):
            raise SerialMonitorTimeout("timeout")


class TestSerialMonitorInit:
    def test_defaults(self):
        m = SerialMonitor(port="/dev/ttyACM0")
        assert m.port == "/dev/ttyACM0"
        assert m.baud == 115200
        assert m.timeout == 5.0
        assert m.encoding == "utf-8"
        assert m._serial is None
        assert m._captured == []

    def test_is_open_false_initially(self):
        m = SerialMonitor("/dev/ttyACM0")
        assert m.is_open is False

    def test_captured_log_empty_initially(self):
        m = SerialMonitor("/dev/ttyACM0")
        assert m.captured_log == ""


class TestSerialMonitorLifecycle:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_open(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m.open()
        assert m.is_open is True
        assert m._capture_thread is not None
        m.close()

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_open_already_open(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m.open()
        m.open()  # second open should be no-op
        mock_port.assert_called_once()
        m.close()

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_context_manager(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        with SerialMonitor("/dev/ttyACM0") as m:
            assert m.is_open
        assert m.is_open is False

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_close_handles_exception(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.close.side_effect = Exception("close error")
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m.open()
        m.close()  # should not raise
        assert m._serial is None

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_close_already_closed(self, mock_import, mock_port):
        m = SerialMonitor("/dev/ttyACM0")
        m.close()  # should not raise


class TestSerialMonitorImport:
    def test_import_pyserial_success(self):
        m = SerialMonitor("/dev/ttyACM0")
        m._import_pyserial()
        assert m._pyserial_mod is not None

    def test_import_pyserial_cached(self):
        m = SerialMonitor("/dev/ttyACM0")
        m._pyserial_mod = "already_loaded"
        m._import_pyserial()
        assert m._pyserial_mod == "already_loaded"

    def test_import_pyserial_fails(self):
        m = SerialMonitor("/dev/ttyACM0")
        import builtins
        orig = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "serial":
                raise ImportError("No module named serial")
            return orig(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="pyserial is required"):
                m._import_pyserial()


class TestSerialMonitorOpenPort:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_open_port_success(self, mock_import):
        m = SerialMonitor("/dev/ttyACM0")
        m._pyserial_mod = MagicMock()
        mock_serial_instance = MagicMock()
        m._pyserial_mod.Serial.return_value = mock_serial_instance
        result = m._open_port()
        assert result == mock_serial_instance
        m._pyserial_mod.Serial.assert_called_once_with(
            port="/dev/ttyACM0", baudrate=115200, timeout=5.0, write_timeout=5.0
        )

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_open_port_failure(self, mock_import):
        m = SerialMonitor("/dev/ttyACM0")
        m._pyserial_mod = MagicMock()
        m._pyserial_mod.Serial.side_effect = PermissionError("Access denied")
        with pytest.raises(RuntimeError, match="Cannot open"):
            m._open_port()


class TestSerialMonitorCapture:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_read_line(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.return_value = b"Hello\r\n"
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m._serial = mock_serial
        text = m._read_line()
        assert text == "Hello\r\n"

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_capture_loop_adds_data(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 1
        mock_serial.readline.side_effect = [b"line1\n", b"line2\n"]
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m._serial = mock_serial
        m._stop_event = MagicMock()
        m._stop_event.is_set.side_effect = [False, False, True]
        m._capture_loop()
        assert "line1" in m.captured_log

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_capture_loop_no_data(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m._serial = mock_serial
        m._stop_event = MagicMock()
        m._stop_event.is_set.side_effect = [False, True]
        m._capture_loop()  # should not raise

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_capture_loop_exception_breaks(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 1
        mock_serial.readline.side_effect = Exception("read error")
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        m._serial = mock_serial
        m._stop_event = MagicMock()
        m._stop_event.is_set.side_effect = [False, True]
        m._capture_loop()  # should not raise

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_clear(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("some data")
        assert m.captured_log == "some data"
        m.clear()
        assert m.captured_log == ""


class TestSerialMonitorExpect:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_expect_found(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Boot OK\n")
            m._captured.append("Test PASSED\n")
        result = m.expect("Test PASSED", timeout=1)
        assert result == "Test PASSED"

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_expect_not_found_timeout(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with pytest.raises(SerialMonitorTimeout):
            m.expect("NONEXISTENT", timeout=0.5)

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_expect_not_found_no_fail_fast(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        result = m.expect("NONEXISTENT", timeout=0.5, fail_fast=False)
        assert result == ""

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_expect_with_regex(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("ERROR code 0x1234\n")
        result = m.expect(r"ERROR code 0x[0-9a-fA-F]+", timeout=1, regex=True)
        assert "ERROR code 0x1234" in result

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_expect_all(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Step 1\nStep 2\nStep 3\n")
        results = m.expect_all(["Step 1", "Step 3"], timeout=1)
        assert len(results) == 2

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_assert_text_present(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Hello World\n")
        assert m.assert_text_present("Hello") is True
        assert m.assert_text_present("Goodbye") is False

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_assert_text_absent(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Hello\n")
        assert m.assert_text_absent("Goodbye") is True
        assert m.assert_text_absent("Hello") is False


class TestSerialMonitorReadUntil:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_read_until_found(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Before marker END after")
        result = m.read_until("END", timeout=1)
        assert result == "Before marker END"

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_read_until_not_found(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with pytest.raises(SerialMonitorTimeout):
            m.read_until("NONEXISTENT", timeout=0.5)

    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_read_until_exclude_marker(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        with m._lock:
            m._captured.append("Before END after")
        result = m.read_until("END", timeout=1, include_marker=False)
        assert result == "Before "


class TestSerialMonitorWaitSilent:
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._open_port")
    @patch("yuleosh.cross.serial_monitor.SerialMonitor._import_pyserial")
    def test_wait_silent_returns_early(self, mock_import, mock_port):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_port.return_value = mock_serial
        m = SerialMonitor("/dev/ttyACM0")
        result = m.wait_silent(duration=0.05)
        assert isinstance(result, bool)


class TestPipeSerialMonitor:
    def test_init(self):
        mock_pipe = MagicMock()
        ps = PipeSerialMonitor(pipe=mock_pipe, timeout=5.0)

    def test_is_streaming_initial(self):
        mock_pipe = MagicMock()
        ps = PipeSerialMonitor(pipe=mock_pipe)
        assert ps.is_streaming is True

    def test_close_stops_streaming(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        ps.close()
        assert ps.is_streaming is False

    def test_context_manager(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        with PipeSerialMonitor(pipe=mock_pipe) as ps:
            assert ps.is_streaming
        assert ps.is_streaming is False

    def test_captured_log_initial(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        assert ps.captured_log == ""

    def test_expect_in_log(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        with ps._lock:
            ps._captured.append("Hello World\n")
        result = ps.expect("Hello", timeout=1)
        assert result == "Hello"

    def test_expect_not_found(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        with pytest.raises(SerialMonitorTimeout):
            ps.expect("NONEXISTENT", timeout=0.5)

    def test_expect_with_regex(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        with ps._lock:
            ps._captured.append("Value: 0x1234\n")
        result = ps.expect(r"0x[0-9a-f]+", timeout=1, regex=True)
        assert "0x1234" in result

    def test_expect_no_fail_fast(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        result = ps.expect("NONEXISTENT", timeout=0.5, fail_fast=False)
        assert result == ""

    def test_expect_all(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        ps = PipeSerialMonitor(pipe=mock_pipe)
        with ps._lock:
            ps._captured.append("A\nB\nC\n")
        results = ps.expect_all(["A", "C"], timeout=1)
        assert len(results) == 2

    def test_close_pipe_exception(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.return_value = iter([])
        mock_pipe.close.side_effect = Exception("close error")
        ps = PipeSerialMonitor(pipe=mock_pipe)
        ps.close()  # should not raise

    def test_capture_loop_stops_on_stop_event(self):
        mock_pipe = MagicMock()
        mock_pipe.__iter__.side_effect = ValueError("pipe closed")
        ps = PipeSerialMonitor(pipe=mock_pipe)
        # Thread may exit quickly due to exception; just ensure close doesn't hang
        ps.close()
