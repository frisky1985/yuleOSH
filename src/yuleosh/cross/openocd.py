"""
yuleOSH — OpenOCD flash backend.

Provides the ``OpenOCDRunner`` class for flashing firmware via OpenOCD.
"""

import logging
import os
import shutil
import subprocess
import time

from .base import FlashResult, FlashError, FlashTool
from .target_config import TargetConfig

log = logging.getLogger("cross.flash")


class OpenOCDRunner(FlashTool):
    """Flash runner using OpenOCD (Open On-Chip Debugger)."""

    @property
    def name(self) -> str:
        return "openocd"

    def is_available(self) -> bool:
        return shutil.which("openocd") is not None

    def write(self, firmware: str, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        if not config.flash_openocd:
            return FlashResult(
                passed=False,
                tool=self.name,
                error=f"Target '{config.name}' has no OpenOCD config defined",
                elapsed=time.monotonic() - t0,
            )

        openocd_cfg = config.flash_openocd
        firmware_abs = os.path.abspath(firmware)
        openocd_bin = shutil.which("openocd") or "openocd"

        cmd = [
            openocd_bin,
            "-f", openocd_cfg,
            "-c", f"program {firmware_abs} 0x08000000 verify exit",
        ]

        log.info("OpenOCD flash: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return FlashResult(
                passed=False,
                tool=self.name,
                log="OpenOCD timed out after 60s",
                elapsed=time.monotonic() - t0,
                error="Timeout",
            )
        except FileNotFoundError:
            return FlashResult(
                passed=False,
                tool=self.name,
                log="OpenOCD binary not found",
                elapsed=time.monotonic() - t0,
                error="Binary not found",
            )

        elapsed = time.monotonic() - t0
        combined = result.stdout + "\n" + result.stderr
        passed = result.returncode == 0

        return FlashResult(
            passed=passed,
            log=combined.strip(),
            tool=self.name,
            elapsed=elapsed,
            error=None if passed else f"OpenOCD exit code {result.returncode}",
        )

    def erase(self, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        if not config.flash_openocd:
            return FlashResult(
                passed=False,
                tool=self.name,
                error=f"Target '{config.name}' has no OpenOCD config defined",
                elapsed=time.monotonic() - t0,
            )

        openocd_bin = shutil.which("openocd") or "openocd"
        cmd = [
            openocd_bin,
            "-f", config.flash_openocd,
            "-c", "init",
            "-c", "reset halt",
            "-c", "flash erase_sector 0 0 last",
            "-c", "exit",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return FlashResult(
                passed=False, tool=self.name,
                log="Erase timed out", elapsed=time.monotonic() - t0,
                error="Timeout",
            )

        elapsed = time.monotonic() - t0
        passed = result.returncode == 0
        return FlashResult(
            passed=passed,
            log=(result.stdout + "\n" + result.stderr).strip(),
            tool=self.name,
            elapsed=elapsed,
        )

    def verify(self, firmware: str, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        if not config.flash_openocd:
            return FlashResult(
                passed=False, tool=self.name,
                error=f"Target '{config.name}' has no OpenOCD config",
                elapsed=time.monotonic() - t0,
            )

        openocd_bin = shutil.which("openocd") or "openocd"
        firmware_abs = os.path.abspath(firmware)
        cmd = [
            openocd_bin,
            "-f", config.flash_openocd,
            "-c", f"verify_image {firmware_abs} 0x08000000",
            "-c", "exit",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return FlashResult(
                passed=False, tool=self.name,
                log="Verify timed out", elapsed=time.monotonic() - t0,
                error="Timeout",
            )

        elapsed = time.monotonic() - t0
        passed = result.returncode == 0
        return FlashResult(
            passed=passed,
            log=(result.stdout + "\n" + result.stderr).strip(),
            tool=self.name,
            elapsed=elapsed,
            error=None if passed else "Verify failed — firmware mismatch",
        )
