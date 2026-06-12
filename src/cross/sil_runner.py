# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — QEMU SIL (Software-in-the-Loop) Runner.

Handles the lifecycle of a QEMU system emulation process, captures serial
output, and executes expect-like test scripts against the running target.

Typical usage::

    cfg = load_target_config("stm32f4")
    cfg.elf = "build/hello-arm.elf"

    runner = QemuSilRunner(cfg)
    script = '\\n'.join([
        'expect:Hello from yuleOSH cross-compilation test!',
        'expect:Architecture: ARM',
    ])
    result = runner.run(test_script=script)
    assert result.passed
    print(result.log[:500])  # Captured serial output
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import IO, Any

from .sil_assert import SerialAssert, run_expect_script
from .target_config import TargetConfig

log = logging.getLogger("sil.runner")


# ---------------------------------------------------------------------------
# QEMU version constants
# ---------------------------------------------------------------------------

MIN_QEMU_VERSION: tuple[int, int, int] = (8, 2, 0)
"""Minimum required QEMU version (8.2.0)."""

MAX_QEMU_VERSION: tuple[int, int, int] = (8, 3, 0)
"""Maximum supported QEMU version (exclusive upper bound for 8.2.x LTS)."""

RECOMMENDED_QEMU_VERSION: str = "8.2.x"
"""Recommended QEMU version string for user-facing messages."""

_QEMU_VERSION_RE = re.compile(r"version\s+(\d+)\.(\d+)\.(\d+)")


def parse_qemu_version(version_output: str) -> tuple[int, int, int]:
    """Parse a QEMU version triple from ``--version`` output.

    Parameters
    ----------
    version_output : str
        Raw stdout from ``qemu-system-arm --version``.

    Returns
    -------
    tuple[int, int, int]
        ``(major, minor, patch)`` parsed from the first version string.

    Raises
    ------
    RuntimeError
        If no version string can be extracted.
    """
    m = _QEMU_VERSION_RE.search(version_output)
    if not m:
        raise RuntimeError(
            f"Cannot parse QEMU version from output: {version_output!r}"
        )
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ---------------------------------------------------------------------------
# Result data
# ---------------------------------------------------------------------------


@dataclass
class SilResult:
    """Result of a single SIL test run.

    Attributes
    ----------
    passed : bool
        ``True`` when all assertions passed; ``False`` on failure,
        timeout, or runner error.
    log : str
        Full captured serial output text.
    coverage : dict[str, Any]
        Optional coverage metadata (may be empty for QEMU mode).
    elapsed : float
        Wall-clock duration of the run in seconds.
    assertion_failures : list[str]
        Descriptions of any failed assertions.
    error : str | None
        Runner error message (e.g. QEMU not found, process crash).
    """

    passed: bool = True
    log: str = ""
    coverage: dict[str, Any] = field(default_factory=dict)
    elapsed: float = 0.0
    assertion_failures: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# QEMU SIL Runner
# ---------------------------------------------------------------------------


class QemuSilRunner:
    """Run a binary on QEMU and verify serial output.

    Parameters
    ----------
    config : TargetConfig
        Target configuration loaded from YAML. Must have ``elf`` set.

    Raises
    ------
    ValueError
        If ``config.elf`` is not set.
    RuntimeError
        If the required QEMU binary is not found in ``PATH``.
    """

    def __init__(self, config: TargetConfig):
        if not config.elf:
            raise ValueError(
                "TargetConfig.elf must be set before creating QemuSilRunner. "
                "Example: config.elf = 'build/hello-arm.elf'"
            )
        self.config = config
        self._qemu_bin = config._qemu_binary()

        # Validate QEMU binary exists
        if not shutil.which(self._qemu_bin):
            raise RuntimeError(
                f"QEMU binary '{self._qemu_bin}' not found in PATH. "
                f"Install QEMU system emulator for {config.arch}. "
                f"(e.g. 'brew install qemu' on macOS, "
                f"'apt install qemu-system-arm' on Debian/Ubuntu)"
            )

        # Validate QEMU version meets minimum requirement
        self._check_qemu_version()

        self._timeout = config.default_timeout
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------
    # Version check
    # ------------------------------------------------------------------

    def _check_qemu_version(self) -> None:
        """Verify the installed QEMU version meets the minimum requirement.

        Calls ``{qemu_bin} --version`` and parses the version string.
        Raises ``RuntimeError`` if:

        - The installed version is older than MIN_QEMU_VERSION.
        - The installed version is newer than MAX_QEMU_VERSION.
        - The version string cannot be parsed.
        """
        try:
            result = subprocess.run(
                [self._qemu_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"QEMU binary '{self._qemu_bin}' not found — "
                f"version check failed."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"QEMU version check timed out for '{self._qemu_bin}'."
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"'{self._qemu_bin} --version' exited with code "
                f"{result.returncode}: {result.stderr}"
            )

        try:
            version = parse_qemu_version(result.stdout)
        except RuntimeError as e:
            raise RuntimeError(
                f"{e} — ensure {self._qemu_bin} is a valid QEMU binary."
            )

        if version < MIN_QEMU_VERSION:
            raise RuntimeError(
                f"QEMU version {'.'.join(str(v) for v in version)} is too old. "
                f"Minimum required: "
                f"{'.'.join(str(v) for v in MIN_QEMU_VERSION)}. "
                f"Recommended: {RECOMMENDED_QEMU_VERSION} LTS."
            )

        if version >= MAX_QEMU_VERSION:
            log.warning(
                "QEMU version %s exceeds recommended range %s LTS — "
                "may still work but not officially tested.",
                ".".join(str(v) for v in version),
                RECOMMENDED_QEMU_VERSION,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        test_script: str = "",
        *,
        timeout: float | None = None,
        expect_pattern: str | None = None,
    ) -> SilResult:
        """Execute the test: boot QEMU, capture serial, run assertions.

        Parameters
        ----------
        test_script : str
            Multi-line expect script (see :func:`run_expect_script`).
            Ignored if ``expect_pattern`` is provided.
        timeout : float, optional
            Override the default timeout from config.
        expect_pattern : str, optional
            Convenience: single pattern to ``expect()``. When provided,
            *test_script* is ignored.

        Returns
        -------
        SilResult
            Test result with log, passed flag, and any failures.
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        t0 = time.monotonic()

        try:
            result = self._do_run(test_script, expect_pattern, effective_timeout)
        except Exception as exc:
            log.exception("Unexpected SIL runner error")
            result = SilResult(
                passed=False,
                log=self._captured_log() or "",
                elapsed=time.monotonic() - t0,
                error=f"Unexpected error: {exc}",
            )

        result.elapsed = time.monotonic() - t0
        return result

    # ------------------------------------------------------------------
    # Internal: run lifecycle
    # ------------------------------------------------------------------

    def _do_run(
        self,
        test_script: str,
        expect_pattern: str | None,
        timeout: float,
    ) -> SilResult:
        cmd = self.config.build_qemu_cmd()
        log.info("Starting QEMU: %s", " ".join(cmd))
        log.debug("QEMU CWD: %s", os.getcwd())

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered for streaming
        )

        assert self._process.stdout is not None

        # Attach serial assertion engine
        serial_timeout = min(timeout, 30.0)
        with SerialAssert.stream(
            pipe=self._process.stdout,
            timeout=serial_timeout,
        ) as serial:

            # Option A: simple expect pattern
            if expect_pattern:
                return self._run_simple_expect(serial, expect_pattern, timeout)

            # Option B: full expect script (or wait for QEMU to finish)
            failures: list[str] = []
            try:
                if test_script.strip():
                    run_expect_script(serial, test_script)
                else:
                    # No script: wait for QEMU to exit or timeout
                    self._wait_for_exit(timeout, serial)
            except AssertionError as ae:
                failures.append(str(ae))
            except Exception as exc:
                failures.append(f"Script execution error: {exc}")

            # Graceful shutdown
            passed = len(failures) == 0
            log_text = serial.captured_log

            self._terminate(timeout)

            return SilResult(
                passed=passed,
                log=log_text,
                assertion_failures=failures,
            )

    def _run_simple_expect(
        self,
        serial: SerialAssert,
        pattern: str,
        timeout: float,
    ) -> SilResult:
        """Handle the convenience ``expect_pattern`` argument."""
        failure: str | None = None
        try:
            serial.expect(pattern, timeout=timeout)
        except AssertionError as ae:
            failure = str(ae)

        log_text = serial.captured_log
        self._terminate(timeout)

        return SilResult(
            passed=failure is None,
            log=log_text,
            assertion_failures=[failure] if failure else [],
            error=failure,
        )

    # ------------------------------------------------------------------
    # Process management
    # ------------------------------------------------------------------

    def _wait_for_exit(self, timeout: float, serial: SerialAssert) -> None:
        """Wait for the QEMU process to exit within *timeout* seconds,
        draining serial output."""
        assert self._process is not None
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            ret = self._process.poll()
            if ret is not None:
                log.debug("QEMU exited with code %d", ret)
                return
            time.sleep(0.05)

        # Timeout — terminate
        log.warning("QEMU did not exit within %.1fs — terminating", timeout)
        self._terminate(5.0)

    def _terminate(self, grace_period: float = 5.0) -> None:
        """Send SIGTERM then SIGKILL to the QEMU process."""
        if self._process is None:
            return

        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=grace_period)
                log.debug("QEMU terminated gracefully")
            except subprocess.TimeoutExpired:
                log.warning("QEMU did not respond to SIGTERM — sending SIGKILL")
                self._process.kill()
                self._process.wait(timeout=5.0)
        except OSError:
            pass  # Process already gone
        finally:
            self._process = None

    def _captured_log(self) -> str | None:
        """Read any remaining buffered output (best-effort)."""
        if self._process and self._process.stdout:
            try:
                remaining = self._process.stdout.read()
                return remaining if remaining else None
            except OSError:
                pass
        return None

    # ------------------------------------------------------------------
    # Coverage extraction (stub for future implementation)
    # ------------------------------------------------------------------

    def _extract_coverage(self) -> dict[str, Any]:
        """Extract code coverage data from the QEMU process.

        Currently returns an empty dict. Future versions may parse
        QEMU's ``-gdb`` or ``-semihosting`` output for trace data.
        """
        return {}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def sil_test(
    config: TargetConfig,
    *,
    expect_pattern: str | None = None,
    test_script: str = "",
    timeout: float | None = None,
) -> SilResult:
    """One-shot convenience function for running a SIL test.

    Usage::

        cfg = load_target_config("stm32f4")
        cfg.elf = "build/hello-arm.elf"

        result = sil_test(cfg, expect_pattern="Hello World")
        assert result.passed
        print(result.log)
    """
    runner = QemuSilRunner(config)
    return runner.run(
        test_script=test_script,
        expect_pattern=expect_pattern,
        timeout=timeout,
    )
