# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — HIL (Hardware-in-the-Loop) Test Runner v0.5.0.

Orchestrates the full hardware test workflow:
  Flash → Reset → Wait → Capture → Assert

Combines the Flash Abstraction Layer (flash.py) and Serial Monitor
(serial_monitor.py) to provide a unified HIL test API.

Usage::

    runner = HilTestRunner(target="stm32f4")
    result = runner.run(
        firmware="build/firmware.elf",
        expect_pattern="Test PASSED",
        timeout=30,
    )
    assert result.passed
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .flash import FlashResult, FlashRunner, FlashError
from .target_config import TargetConfig
from .serial_monitor import SerialMonitor, SerialMonitorTimeout

log = logging.getLogger("hil.runner")


# ---------------------------------------------------------------------------
# Result data
# ---------------------------------------------------------------------------


@dataclass
class HilTestResult:
    """Result of a single HIL test execution.

    Attributes
    ----------
    passed : bool
        All phases (flash, boot, assertions) succeeded.
    flash_result : FlashResult | None
        Result of the firmware flashing step.
    boot_log : str
        Serial log captured during boot / test execution.
    test_log : str
        Structured test assertion results.
    elapsed : float
        Total wall-clock duration in seconds.
    error : str | None
        Error message on failure.
    phase_timings : dict[str, float]
        Per-phase timing breakdown.
    """

    passed: bool = True
    flash_result: FlashResult | None = None
    boot_log: str = ""
    test_log: str = ""
    elapsed: float = 0.0
    error: str | None = None
    phase_timings: dict[str, float] = field(default_factory=dict)

    @property
    def phases(self) -> dict[str, float]:
        """Alias for phase_timings."""
        return self.phase_timings


# ---------------------------------------------------------------------------
# HIL Test Runner
# ---------------------------------------------------------------------------


class HilTestRunner:
    """Hardware-in-the-Loop test runner.

    Manages the full hardware test lifecycle: flash firmware to target,
    monitor serial output, and verify test assertions.

    Parameters
    ----------
    target : str or TargetConfig
        Target board name or config.
    flash_tool : str, optional
        Preferred flash tool (``"openocd"``, ``"jlink"``, ``"pyocd"``).
    serial_port : str, optional
        Serial port for monitoring. If not specified, auto-detect from
        target config or try common ports.
    baud : int
        Serial baud rate (default **115200**).
    base_dir : str, optional
        Project base directory for YAML target resolution.
    """

    def __init__(
        self,
        target: str | TargetConfig,
        flash_tool: str | None = None,
        serial_port: str | None = None,
        baud: int = 115200,
        flash_delay: float = 1.0,
        base_dir: str | None = None,
    ):
        # Resolve target
        if isinstance(target, TargetConfig):
            self.config = target
        else:
            from .flash import load_target_config_safe
            self.config = load_target_config_safe(target, base_dir=base_dir)

        self.flash_tool = flash_tool
        self.baud = baud
        self.flash_delay = flash_delay

        # Serial port resolution
        if serial_port:
            self.serial_port = serial_port
        elif hasattr(self.config, "serial_port"):
            self.serial_port = self.config.serial_port  # type: ignore[union-attr]
        else:
            # Default to common Linux ports
            self.serial_port = "/dev/ttyACM0"

        self._flash_runner: FlashRunner | None = None

    # ------------------------------------------------------------------
    # Lazy flash runner
    # ------------------------------------------------------------------

    @property
    def flash_runner(self) -> FlashRunner:
        if self._flash_runner is None:
            self._flash_runner = FlashRunner(
                target=self.config,
                tool=self.flash_tool,
            )
        return self._flash_runner

    # ------------------------------------------------------------------
    # Core test execution
    # ------------------------------------------------------------------

    def run(
        self,
        firmware: str,
        *,
        expect_pattern: str | None = None,
        expect_patterns: list[str] | None = None,
        test_script: str | None = None,
        timeout: float = 30.0,
        skip_flash: bool = False,
        serial_port: str | None = None,
    ) -> HilTestResult:
        """Execute a HIL test.

        Steps:
        1. Flash firmware to target (unless *skip_flash*)
        2. Wait for boot
        3. Capture serial output
        4. Execute expect/assert patterns
        5. Return result

        Parameters
        ----------
        firmware : str
            Path to firmware file to flash.
        expect_pattern : str, optional
            Single expected serial output pattern.
        expect_patterns : list[str], optional
            Ordered list of expected serial patterns.
        test_script : str, optional
            Multi-line expect script (lines starting with ``expect:``,
            ``wait:``, ``assert:``).
        timeout : float
            Maximum test duration in seconds (default **30**).
        skip_flash : bool
            If ``True``, skip the flashing step (useful if firmware is
            already loaded).
        serial_port : str, optional
            Override the serial port for this run.

        Returns
        -------
        HilTestResult
        """
        t0 = time.monotonic()
        timings: dict[str, float] = {}

        result = HilTestResult()

        port = serial_port or self.serial_port

        # ------------------------------------------------------------------
        # Phase 1: Flash firmware
        # ------------------------------------------------------------------
        if not skip_flash:
            if not os.path.isfile(firmware):
                return HilTestResult(
                    passed=False,
                    flash_result=FlashResult(
                        passed=False, error=f"Firmware not found: {firmware}",
                    ),
                    elapsed=time.monotonic() - t0,
                    error=f"Firmware file not found: {firmware}",
                    phase_timings={},
                )

            try:
                flash_res = self.flash_runner.flash(firmware)
                timings["flash"] = flash_res.elapsed
                result.flash_result = flash_res
            except FlashError as exc:
                return HilTestResult(
                    passed=False,
                    elapsed=time.monotonic() - t0,
                    error=f"Flash error: {exc}",
                    phase_timings=timings,
                )

            if not flash_res.passed:
                return HilTestResult(
                    passed=False,
                    flash_result=flash_res,
                    boot_log=flash_res.log,
                    elapsed=time.monotonic() - t0,
                    error=f"Flashing failed: {flash_res.error}",
                    phase_timings=timings,
                )

            # Brief delay after flashing before opening serial
            if self.flash_delay > 0:
                time.sleep(self.flash_delay)

        # ------------------------------------------------------------------
        # Phase 2: Open serial + capture
        # ------------------------------------------------------------------
        boot_t0 = time.monotonic()
        try:
            with SerialMonitor(port=port, baud=self.baud, timeout=timeout) as serial:
                # Let device boot
                time.sleep(0.5)

                # Phase 3: Assert patterns
                pattern_t0 = time.monotonic()

                if test_script:
                    self._run_test_script(serial, test_script, timeout)
                elif expect_patterns:
                    for pat in expect_patterns:
                        serial.expect(pat, timeout=timeout / len(expect_patterns))
                elif expect_pattern:
                    serial.expect(expect_pattern, timeout=timeout)
                else:
                    # Wait for timeout to capture output
                    time.sleep(timeout)

                pattern_time = time.monotonic() - pattern_t0
                timings["patterns"] = pattern_time

                boot_log = serial.captured_log
                timings["serial"] = time.monotonic() - boot_t0

                result.boot_log = boot_log
                result.passed = True

        except SerialMonitorTimeout as exc:
            # Pattern not found — capture what we have and fail
            boot_log = f"[TIMEOUT] {exc}\n"
            try:
                with SerialMonitor(port=port, baud=self.baud, timeout=5) as serial:
                    time.sleep(1)
                    boot_log += serial.captured_log
            except Exception as e:
                import logging; logging.getLogger("__name__").warning("%s", e)
                pass

            result.passed = False
            result.boot_log = boot_log
            result.error = str(exc)
            result.phase_timings = timings
            result.elapsed = time.monotonic() - t0
            return result

        except Exception as exc:
            result.passed = False
            result.error = f"HIL test error: {exc}"
            result.phase_timings = timings
            result.elapsed = time.monotonic() - t0
            return result

        # ------------------------------------------------------------------
        # Done
        # ------------------------------------------------------------------
        result.elapsed = time.monotonic() - t0
        result.phase_timings = timings
        return result

    # ------------------------------------------------------------------
    # Shortcut methods
    # ------------------------------------------------------------------

    def flash_and_expect(
        self,
        firmware: str,
        pattern: str,
        timeout: float = 30.0,
    ) -> HilTestResult:
        """Flash firmware and wait for a single expected pattern."""
        return self.run(
            firmware=firmware,
            expect_pattern=pattern,
            timeout=timeout,
        )

    def flash_and_boot(
        self,
        firmware: str,
        timeout: float = 15.0,
    ) -> HilTestResult:
        """Flash firmware and verify the device boots (waits for boot message)."""
        return self.run(
            firmware=firmware,
            expect_patterns=["Boot", "Starting", "Init"],
            timeout=timeout,
        )

    def skip_flash_test(self, pattern: str, timeout: float = 30.0) -> HilTestResult:
        """Run a test without re-flashing (uses already-loaded firmware)."""
        return self.run(
            firmware="",
            expect_pattern=pattern,
            timeout=timeout,
            skip_flash=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_test_script(
        self,
        serial: SerialMonitor,
        script: str,
        default_timeout: float,
    ) -> None:
        """Execute a multi-line expect script against the serial monitor.

        Script directives:
          - ``expect:<text>`` — wait for text
          - ``expect_re:<regex>`` — wait for regex match
          - ``assert:<text>`` — check text is present (non-blocking)
          - ``assert_not:<text>`` — check text absent
          - ``wait:<seconds>`` — sleep
          - ``read_until:<marker>`` — capture until marker
        """
        for line in script.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("expect_re:"):
                _, pattern = line.split(":", 1)
                serial.expect(pattern.strip(), timeout=default_timeout, regex=True)
            elif line.startswith("expect:"):
                _, pattern = line.split(":", 1)
                serial.expect(pattern.strip(), timeout=default_timeout)
            elif line.startswith("assert_not:"):
                _, text = line.split(":", 1)
                if serial.assert_text_present(text.strip()):
                    raise SerialMonitorTimeout(
                        f"Assertion failed: {text!r} found in serial log"
                    )
            elif line.startswith("assert:"):
                _, text = line.split(":", 1)
                if not serial.assert_text_present(text.strip()):
                    raise SerialMonitorTimeout(
                        f"Assertion failed: {text!r} not found in serial log"
                    )
            elif line.startswith("wait:"):
                _, seconds = line.split(":", 1)
                time.sleep(float(seconds.strip()))
            elif line.startswith("read_until:"):
                _, marker = line.split(":", 1)
                serial.read_until(marker.strip(), timeout=default_timeout)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def hil_test(
    target: str | TargetConfig,
    firmware: str,
    *,
    expect_pattern: str | None = None,
    expect_patterns: list[str] | None = None,
    timeout: float = 30.0,
    flash_tool: str | None = None,
    serial_port: str | None = None,
) -> HilTestResult:
    """One-shot HIL test convenience function.

    Usage::

        result = hil_test(
            target="stm32f4",
            firmware="build/firmware.elf",
            expect_pattern="Test PASSED",
        )
        assert result.passed
    """
    runner = HilTestRunner(
        target=target,
        flash_tool=flash_tool,
        serial_port=serial_port,
    )
    return runner.run(
        firmware=firmware,
        expect_pattern=expect_pattern,
        expect_patterns=expect_patterns,
        timeout=timeout,
    )
