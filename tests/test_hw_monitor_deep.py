"""Deep tests for hardware.monitor — SerialMonitor, _MockSerial."""

import threading
import time
import pytest
from unittest.mock import MagicMock, patch

from yuleosh.hardware.monitor import SerialMonitor, SerialMonitorError, PortNotFoundError, _MockSerial


class TestMockSerial:
    def test_init(self):
        ms = _MockSerial("/dev/ttyUSB0")
        assert ms.port == "/dev/ttyUSB0"
        assert ms._closed is False
        assert ms._injected == []

    def test_readline_empty(self):
        ms = _MockSerial("/dev/ttyUSB0")
        data = ms.readline()
        assert data == b""

    def test_readline_injected(self):
        ms = _MockSerial("/dev/ttyUSB0")
        ms.inject("Hello")
        data = ms.readline()
        assert data == b"Hello\n"

    def test_inject_multiple(self):
        ms = _MockSerial("/dev/ttyUSB0")
        ms.inject("first")
        ms.inject("second")
        assert ms.readline() == b"first\n"
        assert ms.readline() == b"second\n"

    def test_close(self):
        ms = _MockSerial("/dev/ttyUSB0")
        ms.close()
        assert ms._closed is True

    def test_is_open(self):
        ms = _MockSerial("/dev/ttyUSB0")
        assert ms.is_open is True
        ms.close()
        assert ms.is_open is False


class TestSerialMonitorInit:
    def test_defaults(self):
        m = SerialMonitor("/dev/ttyUSB0")
        assert m.port == "/dev/ttyUSB0"
        assert m.baud == 115200
        assert m.timeout == 1.0
        assert m._thread is None
        assert not m._running.is_set()
        assert m._serial is None

    def test_custom_params(self):
        m = SerialMonitor("/dev/ttyS0", baud=9600, timeout=0.5)
        assert m.port == "/dev/ttyS0"
        assert m.baud == 9600
        assert m.timeout == 0.5

    def test_is_running_false_initially(self):
        m = SerialMonitor("/dev/ttyUSB0")
        assert m.is_running is False

    def test_repr(self):
        m = SerialMonitor("/dev/ttyUSB0")
        assert "SerialMonitor" in repr(m)
        assert "/dev/ttyUSB0" in repr(m)


class TestSerialMonitorLifecycle:
    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_start_starts_thread(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        t = m.start()
        assert isinstance(t, threading.Thread)
        assert m._running.is_set()
        assert m._thread is not None
        m.stop()

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_start_already_running(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        t1 = m.start()
        t2 = m.start()
        assert t1 is t2  # same thread
        m.stop()

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_stop_clears_state(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        m.start()
        m.stop()
        assert not m._running.is_set()

    def test_context_manager(self):
        with patch("yuleosh.hardware.monitor.SerialMonitor._open_serial"):
            with SerialMonitor("/dev/ttyUSB0") as m:
                assert m.is_running
            assert not m.is_running

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_get_log_initial_empty(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        assert m.get_log() == []

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_clear_log(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        import threading
        with m._lock:
            m._log.append("test")
        assert len(m.get_log()) == 1
        m.clear_log()
        assert m.get_log() == []


class TestSerialMonitorOpenSerial:
    def test_open_serial_pyserial_installed(self):
        m = SerialMonitor("/dev/ttyUSB0")
        with patch("serial.Serial") as mock_serial:
            m._open_serial()
            assert m._serial is not None
            mock_serial.assert_called_once_with(
                port="/dev/ttyUSB0", baudrate=115200, timeout=1.0
            )

    def test_open_serial_import_error(self):
        m = SerialMonitor("/dev/ttyUSB0")
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "serial" or name.startswith("serial."):
                raise ImportError("No module named serial")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            m._open_serial()
            assert isinstance(m._serial, _MockSerial)

    def test_open_serial_file_not_found(self):
        m = SerialMonitor("/dev/ttyUSB0")
        with patch("serial.Serial") as mock_serial:
            mock_serial.side_effect = FileNotFoundError("No such file")
            with pytest.raises(PortNotFoundError):
                m._open_serial()

    def test_open_serial_permission_error(self):
        m = SerialMonitor("/dev/ttyUSB0")
        with patch("serial.Serial") as mock_serial:
            mock_serial.side_effect = PermissionError("Permission denied")
            with pytest.raises(PortNotFoundError) as exc:
                m._open_serial()
            assert "Permission denied" in str(exc.value) or "chmod" in str(exc.value)

    def test_open_serial_other_oserror(self):
        m = SerialMonitor("/dev/ttyUSB0")
        with patch("serial.Serial") as mock_serial:
            mock_serial.side_effect = OSError("Device busy")
            with pytest.raises(PortNotFoundError) as exc:
                m._open_serial()
            assert "Device busy" in str(exc.value)


class TestSerialMonitorWaitForString:
    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_wait_for_string_found(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        with m._lock:
            m._log.append("Boot OK")
        assert m.wait_for_string("Boot OK", timeout=1) is True

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_wait_for_string_not_found_timeout(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        t0 = time.monotonic()
        result = m.wait_for_string("NONEXISTENT", timeout=0.5)
        assert result is False
        assert time.monotonic() - t0 >= 0.45

    @patch("yuleosh.hardware.monitor.SerialMonitor._open_serial")
    def test_search_log(self, mock_open):
        m = SerialMonitor("/dev/ttyUSB0")
        with m._lock:
            m._log.append("line1")
            m._log.append("line2")
        assert m._search_log("line2") is True
        assert m._search_log("line3") is False


class TestSerialMonitorCloseSerial:
    def test_close_serial_handles_exception(self):
        m = SerialMonitor("/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.close.side_effect = Exception("close error")
        m._serial = mock_serial
        m._close_serial()  # should not raise

    def test_close_serial_none(self):
        m = SerialMonitor("/dev/ttyUSB0")
        m._close_serial()  # should not raise

    def test_close_serial_sets_none(self):
        m = SerialMonitor("/dev/ttyUSB0")
        m._serial = MagicMock()
        m._close_serial()
        assert m._serial is None


class TestSerialMonitorReadLine:
    def test_read_line_none_serial(self):
        m = SerialMonitor("/dev/ttyUSB0")
        assert m._read_line() is None

    def test_read_line_success(self):
        m = SerialMonitor("/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.readline.return_value = b"Hello\r\n"
        m._serial = mock_serial
        result = m._read_line()
        assert result == "Hello\r\n"

    def test_read_line_decode_error(self):
        m = SerialMonitor("/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.readline.return_value = b"\xff\xfe"
        m._serial = mock_serial
        result = m._read_line()
        assert isinstance(result, str)

    def test_read_line_empty(self):
        m = SerialMonitor("/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.readline.return_value = b""
        m._serial = mock_serial
        result = m._read_line()
        assert result is None

    def test_read_line_exception(self):
        m = SerialMonitor("/dev/ttyUSB0")
        mock_serial = MagicMock()
        mock_serial.readline.side_effect = Exception("read error")
        m._serial = mock_serial
        assert m._read_line() is None


class TestSerialMonitorErrorTypes:
    def test_base_error(self):
        assert issubclass(SerialMonitorError, RuntimeError)

    def test_port_not_found(self):
        assert issubclass(PortNotFoundError, SerialMonitorError)

    def test_port_not_found_can_raise(self):
        with pytest.raises(PortNotFoundError):
            raise PortNotFoundError("port not found")
