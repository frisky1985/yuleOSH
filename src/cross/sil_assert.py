# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — SIL serial assertion engine.

Provides expect-like pattern matching on captured serial output from
QEMU or other emulated targets.

Usage::

    from sil_assert import SerialAssert

    # From collected log
    serial = SerialAssert(log_text="Hello World\\n")
    serial.expect("Hello World")                  # passes
    serial.expect("ERROR:", timeout=5)             # fails → SilAssertionError
    serial.read_until("Test Complete")             # returns text before match

    # Streaming mode (attached to a pipe)
    with SerialAssert.stream(pipe=process.stdout) as serial:
        serial.expect("Starting\\n")
        serial.read_until("Done")
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable, TextIO

log = logging.getLogger("sil.assert")


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class SilAssertionError(AssertionError):
    """Raised when a serial assertion fails (timeout or no match)."""

    def __init__(self, pattern: str, timeout: float, log_snippet: str):
        self.pattern = pattern
        self.timeout = timeout
        self.log_snippet = log_snippet
        super().__init__(
            f"Serial assertion FAILED: expected pattern {pattern!r} "
            f"not found within {timeout:.1f}s. "
            f"Last {len(log_snippet)} chars of log: {log_snippet!r}"
        )


# ---------------------------------------------------------------------------
# Serial Assertion Engine
# ---------------------------------------------------------------------------


class SerialAssert:
    """Expect-like assertion engine for emulated serial output.

    Supports both pre-collected logs and streaming (pipe-based) capture.

    Parameters
    ----------
    log_text : str, optional
        Pre-captured serial output text. Used for offline assertions.
    pipe : TextIO, optional
        An open readable stream (e.g. ``process.stdout``) for live capture.
    timeout : float, optional
        Default timeout in seconds for all ``expect()`` / ``read_until()``
        calls (default **10.0**).
    max_log_size : int
        Maximum characters retained in the internal buffer (default **1048576**).
        Oldest bytes are discarded when exceeded.
    """

    def __init__(
        self,
        log_text: str | None = None,
        pipe: TextIO | None = None,
        timeout: float = 10.0,
        max_log_size: int = 1_048_576,
    ):
        self._log_chunks: list[str] = []
        self._max_log_size = max_log_size
        self._default_timeout = timeout

        self._pipe = pipe
        self._capture_thread: threading.Thread | None = None
        self._capture_stop = threading.Event()
        self._lock = threading.Lock()

        if log_text is not None:
            self._append(log_text)
        if pipe is not None:
            self._start_capture()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def captured_log(self) -> str:
        """Full captured serial output so far."""
        with self._lock:
            return "".join(self._log_chunks)

    @property
    def is_streaming(self) -> bool:
        return self._pipe is not None

    # ------------------------------------------------------------------
    # Expect / Read-Until
    # ------------------------------------------------------------------

    def expect(
        self,
        pattern: str,
        timeout: float | None = None,
        *,
        regex: bool = False,
        fail_fast: bool = True,
    ) -> str:
        """Wait for *pattern* to appear in serial output.

        Parameters
        ----------
        pattern : str
            Text (or regex) to search for.
        timeout : float, optional
            Max wait seconds. Falls back to instance default.
        regex : bool
            If ``True``, treat *pattern* as a regular expression.
        fail_fast : bool
            If ``True`` (default), raise ``SilAssertionError`` immediately
            on timeout. Otherwise returns ``""`` silently.

        Returns
        -------
        str
            The full captured log at the point of match (or ``""`` if
            timeout and ``fail_fast=False``).

        Raises
        ------
        SilAssertionError
            If *pattern* is not found before timeout and ``fail_fast=True``.
        """
        effective_timeout = self._default_timeout if timeout is None else timeout

        deadline = time.monotonic() + effective_timeout
        while time.monotonic() < deadline:
            result = self._search(pattern, regex)
            if result is not None:
                return result
            if self._pipe is None and not self.is_streaming:
                # No new data is coming — one final check then bail
                result = self._search(pattern, regex)
                if result is not None:
                    return result
                break
            time.sleep(0.01)  # 10ms polling

        # Final check in case we just missed data
        result = self._search(pattern, regex)
        if result is not None:
            return result

        snippet = self.captured_log[-200:]
        if fail_fast:
            raise SilAssertionError(pattern, effective_timeout, snippet)
        log.warning(
            "Serial expect timeout: pattern=%r, timeout=%.1f, log_snippet=%r",
            pattern, effective_timeout, snippet,
        )
        return ""

    def read_until(
        self,
        marker: str,
        timeout: float | None = None,
        *,
        regex: bool = False,
        include_marker: bool = False,
    ) -> str:
        """Read serial output until *marker* is found, returning the
        text before (or including) the marker.

        Parameters
        ----------
        marker : str
            Boundary text to stop at.
        timeout : float, optional
            Max wait seconds.
        regex : bool
            Treat *marker* as a regex pattern.
        include_marker : bool
            Include the marker in the returned text.

        Returns
        -------
        str
            Text from the beginning of captured output up to (and
            optionally including) the marker.

        Raises
        ------
        SilAssertionError
            If *marker* is not found before timeout.
        """
        # First wait for the marker to appear
        self.expect(marker, timeout=timeout, regex=regex)
        # Now extract everything up to the match
        with self._lock:
            full = "".join(self._log_chunks)
        if regex:
            m = re.search(marker, full)
            if m is None:
                return full  # shouldn't happen since expect() passed
            end = m.end() if include_marker else m.start()
        else:
            idx = full.find(marker)
            if idx == -1:
                return full
            end = idx + len(marker) if include_marker else idx
        return full[:end]

    # ------------------------------------------------------------------
    # Context manager for streaming
    # ------------------------------------------------------------------

    @classmethod
    def stream(
        cls,
        pipe: TextIO,
        timeout: float = 10.0,
        max_log_size: int = 1_048_576,
    ) -> "SerialAssert":
        """Create a streaming :class:`SerialAssert` attached to *pipe*.
        Use via ``with`` block for automatic cleanup."""
        return cls(pipe=pipe, timeout=timeout, max_log_size=max_log_size)

    def close(self) -> None:
        """Stop the capture thread if running."""
        self._capture_stop.set()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2)

    def __enter__(self) -> "SerialAssert":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_capture(self) -> None:
        """Launch a background thread to read from the pipe."""
        self._capture_stop.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )
        self._capture_thread.start()

    def _capture_loop(self) -> None:
        """Read lines from the pipe until stopped."""
        assert self._pipe is not None
        try:
            while not self._capture_stop.is_set():
                line = self._pipe.readline()
                if not line:
                    # EOF — pipe closed
                    break
                self._append(line)
        except (ValueError, OSError) as e:
            log.debug("Serial capture pipe error: %s", e)

    def _append(self, text: str) -> None:
        with self._lock:
            self._log_chunks.append(text)
            total = sum(len(c) for c in self._log_chunks)
            if total > self._max_log_size:
                # Drop oldest chunks until under limit
                dropped: list[str] = []
                while self._log_chunks and total > self._max_log_size:
                    old = self._log_chunks.pop(0)
                    dropped.append(old)
                    total -= len(old)
                log.debug("Dropped %d bytes from serial log (max=%d)",
                          sum(len(d) for d in dropped), self._max_log_size)

    def _search(self, pattern: str, regex: bool = False) -> str | None:
        """Search current log for *pattern*.

        Returns the full captured log on match, or ``None``.
        """
        with self._lock:
            full = "".join(self._log_chunks)

        if regex:
            m = re.search(pattern, full)
            return full if m else None
        else:
            return full if pattern in full else None


# ---------------------------------------------------------------------------
# Expect script parser
# ---------------------------------------------------------------------------

# Supported directives:
#   expect:<text>             — wait for exact text match
#   expect_re:<regex>         — wait for regex match
#   read_until:<marker>       — capture output up to marker
#   wait:<seconds>            — sleep
#   assert<text>              — assert text appears (no wait)


class ExpectScriptError(Exception):
    """Raised when an expect script directive is malformed."""


def run_expect_script(serial: SerialAssert, script: str) -> list[str]:
    """Execute a simple expect-style *script* against *serial*.

    The script is a newline-separated sequence of directives::

        expect:Hello World
        expect_re:ERROR:\\\\d+
        read_until:Test Complete
        wait:2.5
        assert:Passed

    Parameters
    ----------
    serial : SerialAssert
        Active serial assertion handle.
    script : str
        Multi-line expect script.

    Returns
    -------
    list[str]
        Outputs from ``read_until`` directives (empty strings otherwise).

    Raises
    ------
    SilAssertionError
        If an ``expect:``, ``expect_re:``, or ``assert:`` pattern fails.
    ExpectScriptError
        If a directive is malformed.
    """
    results: list[str] = []
    for line_no, raw_line in enumerate(script.strip().split("\n"), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            directive, _, arg = line.partition(":")
            arg = arg.strip()
            directive = directive.strip().lower()

            if directive == "expect":
                serial.expect(arg, fail_fast=True)

            elif directive == "expect_re":
                serial.expect(arg, regex=True, fail_fast=True)

            elif directive == "read_until":
                result = serial.read_until(arg)
                results.append(result)

            elif directive == "wait":
                try:
                    duration = float(arg)
                except ValueError:
                    raise ExpectScriptError(
                        f"Line {line_no}: 'wait' expects a float, got {arg!r}"
                    )
                time.sleep(duration)

            elif directive == "assert":
                if arg not in serial.captured_log:
                    raise SilAssertionError(
                        arg, 0.0, serial.captured_log[-200:]
                    )

            elif directive:
                log.debug("Unknown expect directive at line %d: %s", line_no, directive)

        except SilAssertionError:
            raise  # re-raise
        except ExpectScriptError:
            raise
        except Exception as e:
            raise ExpectScriptError(f"Line {line_no}: {e}") from e

    return results
