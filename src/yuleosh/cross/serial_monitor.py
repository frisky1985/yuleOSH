# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — Serial Monitor for Hardware-in-the-Loop (HIL) Testing.

Provides a cross-platform serial port monitor with expect-like pattern
matching, log capture, and timeout support.

Supports both physical serial ports (via ``pyserial``) and pipe-based
virtual serial (for QEMU integration).

Typical usage::

    monitor = SerialMonitor(port="/dev/ttyACM0", baud=115200)
    monitor.open()
    monitor.expect("Boot Complete", timeout=30)
    monitor.expect("Test Passed", timeout=10)
    captured = monitor.captured_log
    monitor.close()
"""

from __future__ import annotations

import datetime
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import IO, Any, Callable, Optional

log = logging.getLogger("serial.monitor")


# ---------------------------------------------------------------------------
# Result data
# ---------------------------------------------------------------------------


@dataclass
class SerialMonitorResult:
    """Result of a serial monitor session.

    Attributes
    ----------
    passed : bool
        All assertions passed.
    log : str
        Full captured serial log.
    elapsed : float
        Session duration in seconds.
    assertion_failures : list[str]
        Descriptions of any failed assertions / timeouts.
    """

    passed: bool = True
    log: str = ""
    elapsed: float = 0.0
    assertion_failures: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SerialMonitor
# ---------------------------------------------------------------------------


class SerialMonitor:
    """Cross-platform serial port monitor with expect-like pattern matching.

    Parameters
    ----------
    port : str
        Serial port name (e.g. ``/dev/ttyACM0``, ``COM3``).
    baud : int
        Baud rate (default **115200**).
    timeout : float
        Default read timeout in seconds (default **5.0**).
    encoding : str
        Character encoding (default **"utf-8"**, with error replacement).
    """

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        timeout: float = 5.0,
        encoding: str = "utf-8",
    ):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.encoding = encoding

        self._serial: Any | None = None
        self._captured: list[str] = []
        self._lock = threading.Lock()
        self._capture_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._open_time: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def captured_log(self) -> str:
        """Return all captured serial output as a single string."""
        with self._lock:
            return "".join(self._captured)

    @property
    def is_open(self) -> bool:
        """``True`` if the serial port is currently open."""
        return self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port and start background capture.

        Raises
        ------
        RuntimeError
            If ``pyserial`` is not installed, or the port cannot be opened.
        """
        if self.is_open:
            return

        self._import_pyserial()
        self._serial = self._open_port()

        self._open_time = time.monotonic()
        self._stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name=f"serial-{self.port}",
            daemon=True,
        )
        self._capture_thread.start()
        log.info("Serial monitor opened: %s @ %d baud", self.port, self.baud)

    def _import_pyserial(self) -> None:
        """Import the pyserial library. Raises RuntimeError if unavailable."""
        if getattr(self, "_pyserial_mod", None) is not None:
            return
        try:
            import serial  # type: ignore[import-untyped]
            self._pyserial_mod = serial
        except ImportError:
            raise RuntimeError(
                "pyserial is required for SerialMonitor. "
                "Install it: pip install pyserial"
            )

    def _open_port(self) -> Any:
        """Open the configured serial port. Returns a pyserial.Serial instance."""
        if not hasattr(self, "_pyserial_mod") or self._pyserial_mod is None:
            self._import_pyserial()
        try:
            return self._pyserial_mod.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Cannot open serial port '{self.port}': {exc}"
            ) from exc

    def close(self) -> None:
        """Stop background capture and close the serial port."""
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=5.0)
            self._capture_thread = None
        if self._serial:
            try:
                self._serial.close()
            except Exception as e:
                import logging; logging.getLogger("__name__").warning("%s", e)
                log.exception("Error closing serial port %s", self.port)
            self._serial = None
        log.info("Serial monitor closed: %s", self.port)

    def __enter__(self) -> SerialMonitor:
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Background capture
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        """Background thread: continuously read lines from serial port."""
        assert self._serial is not None
        while not self._stop_event.is_set():
            try:
                if self._serial.in_waiting > 0:
                    text = self._read_line()
                    with self._lock:
                        self._captured.append(text)
                else:
                    # No data — brief sleep to avoid busy-wait
                    self._stop_event.wait(timeout=0.05)
            except Exception as exc:
                log.debug("Serial read error: %s", exc)
                break

    def _read_line(self) -> str:
        """Read and decode a single line from the serial port.

        Returns
        -------
        str
            The decoded text line.
        """
        assert self._serial is not None
        raw = self._serial.readline()
        return raw.decode(self.encoding, errors="replace")

    # ------------------------------------------------------------------
    # Expect / assert API
    # ------------------------------------------------------------------

    def expect(
        self,
        pattern: str,
        timeout: float | None = None,
        *,
        regex: bool = False,
        fail_fast: bool = True,
    ) -> str:
        """Wait until *pattern* appears in the captured log.

        Parameters
        ----------
        pattern : str
            Text (or regex) to search for.
        timeout : float, optional
            Maximum wait time in seconds. Defaults to ``self.timeout``.
        regex : bool
            If ``True``, treat *pattern* as a regular expression.
        fail_fast : bool
            If ``True`` (default), raise on timeout. If ``False``, return
            empty string and continue.

        Returns
        -------
        str
            The matched text line, or empty string if timed out
            with *fail_fast* = ``False``.

        Raises
        ------
        SerialMonitorTimeout
            If *pattern* is not found within *timeout* and *fail_fast*
            is ``True``.
        """
        effective_timeout = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + effective_timeout

        if regex:
            compiled = re.compile(pattern)
        else:
            compiled = None

        while time.monotonic() < deadline:
            log_snapshot = self.captured_log
            if compiled:
                match = compiled.search(log_snapshot)
                if match:
                    return match.group(0)
            else:
                if pattern in log_snapshot:
                    return pattern
            time.sleep(0.05)

        if fail_fast:
            elapsed = time.monotonic() - (deadline - effective_timeout)
            raise SerialMonitorTimeout(
                f"Pattern {pattern!r} not found within {effective_timeout}s "
                f"(elapsed: {elapsed:.1f}s, captured: {len(log_snapshot)} chars)"
            )
        return ""

    def expect_all(
        self,
        patterns: list[str],
        timeout: float | None = None,
    ) -> list[str]:
        """Expect multiple patterns in sequence.

        Each pattern is expected in order. Returns a list of matched results.
        """
        results: list[str] = []
        for pattern in patterns:
            result = self.expect(pattern, timeout=timeout)
            results.append(result)
        return results

    def assert_text_present(self, text: str) -> bool:
        """Check if *text* already appears in the captured log (non-blocking).

        Returns
        -------
        bool
        """
        return text in self.captured_log

    def assert_text_absent(self, text: str) -> bool:
        """Check if *text* is NOT in the captured log (non-blocking).

        Returns
        -------
        bool
        """
        return text not in self.captured_log

    def read_until(
        self,
        marker: str,
        timeout: float | None = None,
        include_marker: bool = True,
    ) -> str:
        """Read captured log until *marker* appears.

        Returns text up to (and optionally including) the marker.
        """
        effective_timeout = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + effective_timeout

        while time.monotonic() < deadline:
            log_snapshot = self.captured_log
            idx = log_snapshot.find(marker)
            if idx != -1:
                end = idx + len(marker) if include_marker else idx
                return log_snapshot[:end]
            time.sleep(0.05)

        raise SerialMonitorTimeout(
            f"Marker {marker!r} not found within {effective_timeout}s"
        )

    def clear(self) -> None:
        """Clear the captured log buffer."""
        with self._lock:
            self._captured.clear()

    def wait_silent(self, duration: float = 0.5) -> bool:
        """Wait until no new data arrives for *duration* seconds.

        Useful for ensuring a device has finished printing output.
        """
        before = len(self.captured_log)
        time.sleep(duration)
        after = len(self.captured_log)
        return before == after


# ---------------------------------------------------------------------------
# Pipe-backed SerialMonitor (for QEMU or test use)
# ---------------------------------------------------------------------------


class PipeSerialMonitor:
    """Serial monitor backed by an in-process pipe (StringIO / subprocess pipe).

    Useful for testing and for QEMU integration where serial output is
    captured from a pipe rather than a physical port.

    Parameters
    ----------
    pipe : IO[str]
        A text-mode readable pipe (e.g. ``subprocess.Popen.stdout``).
    timeout : float
        Default read timeout (default **5.0**).
    """

    def __init__(self, pipe: IO[str], timeout: float = 5.0):
        self._pipe = pipe
        self._captured: list[str] = []
        self._lock = threading.Lock()
        self._capture_stop = threading.Event()
        self._timeout = timeout

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="pipe-serial-monitor",
            daemon=True,
        )
        self._capture_thread.start()

    def _capture_loop(self) -> None:
        """Read lines from pipe until closed or stopped."""
        try:
            for line in self._pipe:
                if self._capture_stop.is_set():
                    break
                with self._lock:
                    self._captured.append(line)
        except (ValueError, OSError):
            pass  # Pipe closed

    @property
    def captured_log(self) -> str:
        with self._lock:
            return "".join(self._captured)

    @property
    def is_streaming(self) -> bool:
        return not self._capture_stop.is_set()

    def close(self) -> None:
        self._capture_stop.set()
        if hasattr(self._pipe, "close"):
            try:
                self._pipe.close()
            except Exception as e:
                import logging; logging.getLogger("__name__").warning("%s", e)
                pass
        self._capture_thread.join(timeout=5.0)

    def __enter__(self) -> PipeSerialMonitor:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def expect(
        self,
        pattern: str,
        timeout: float | None = None,
        *,
        regex: bool = False,
        fail_fast: bool = True,
    ) -> str:
        """Same API as :meth:`SerialMonitor.expect`."""
        effective_timeout = timeout if timeout is not None else self._timeout
        deadline = time.monotonic() + effective_timeout

        if regex:
            compiled = re.compile(pattern)
        else:
            compiled = None

        while time.monotonic() < deadline:
            log_snapshot = self.captured_log
            if compiled:
                match = compiled.search(log_snapshot)
                if match:
                    return match.group(0)
            else:
                if pattern in log_snapshot:
                    return pattern
            time.sleep(0.05)

        if fail_fast:
            elapsed = time.monotonic() - (deadline - effective_timeout)
            raise SerialMonitorTimeout(
                f"Pattern {pattern!r} not found within {effective_timeout}s "
                f"(elapsed: {elapsed:.1f}s, captured: {len(log_snapshot)} chars)"
            )
        return ""

    def expect_all(
        self,
        patterns: list[str],
        timeout: float | None = None,
    ) -> list[str]:
        """Expect multiple patterns in sequence.

        Each pattern is expected in order. Returns a list of matched results.
        """
        results: list[str] = []
        for pattern in patterns:
            result = self.expect(pattern, timeout=timeout)
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class SerialMonitorTimeout(AssertionError):
    """Raised when a serial pattern is not matched within the timeout."""
    pass
