"""
yuleOSH — pyOCD flash backend.

Provides the ``PyOCDRunner`` class for flashing firmware via pyOCD.
"""

import logging
import os
import shutil
import subprocess
import time

from .base import FlashResult, FlashError, FlashTool
from .target_config import TargetConfig

log = logging.getLogger("cross.flash")


class PyOCDRunner(FlashTool):
    """Flash runner using pyOCD (Python-based CMSIS-DAP debugger)."""

    @property
    def name(self) -> str:
        return "pyocd"

    def is_available(self) -> bool:
        try:
            import pyocd  # noqa: F401
            return True
        except ImportError:
            return shutil.which("pyocd") is not None

    def write(self, firmware: str, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        target = "stm32f407vg"
        if config.flash_pyocd:
            target = config.flash_pyocd.get("target", target)

        firmware_abs = os.path.abspath(firmware)
        pyocd_bin = shutil.which("pyocd") or "pyocd"

        cmd = [
            pyocd_bin, "flash",
            "-t", target,
            firmware_abs,
        ]

        log.info("pyOCD flash: target=%s firmware=%s", target, firmware_abs)

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
                log="pyOCD timed out after 60s",
                elapsed=time.monotonic() - t0,
                error="Timeout",
            )

        elapsed = time.monotonic() - t0
        combined = result.stdout + "\n" + result.stderr
        passed = result.returncode == 0

        return FlashResult(
            passed=passed,
            log=combined.strip(),
            tool=self.name,
            elapsed=elapsed,
            error=None if passed else f"pyOCD exit code {result.returncode}",
        )

    def erase(self, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        target = "stm32f407vg"
        if config.flash_pyocd:
            target = config.flash_pyocd.get("target", target)

        pyocd_bin = shutil.which("pyocd") or "pyocd"
        cmd = [pyocd_bin, "erase", "-t", target, "--chip"]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
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
