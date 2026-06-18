"""
yuleOSH — J-Link flash backend.

Provides the ``JLinkRunner`` class for flashing firmware via SEGGER
J-Link Commander.
"""

import logging
import os
import shutil
import subprocess
import time

from .base import FlashResult, FlashError, FlashTool
from .target_config import TargetConfig

log = logging.getLogger("cross.flash")


class JLinkRunner(FlashTool):
    """Flash runner using SEGGER J-Link Commander."""

    @property
    def name(self) -> str:
        return "jlink"

    def is_available(self) -> bool:
        return shutil.which("JLinkExe") is not None

    def _build_script(
        self,
        firmware: str,
        config: TargetConfig,
        action: str = "flash",
    ) -> str:
        device = "STM32F407VG"
        interface = "SWD"
        speed = 4000

        if config.flash_jlink:
            device = config.flash_jlink.get("device", device)
            interface = config.flash_jlink.get("interface", interface)
            speed = config.flash_jlink.get("speed", speed)

        firmware_abs = os.path.abspath(firmware)

        if action == "erase":
            return f"""
device {device}
interface {interface}
speed {speed}
erase
exit
"""

        return f"""
device {device}
interface {interface}
speed {speed}
loadfile {firmware_abs}
r
g
exit
"""

    def write(self, firmware: str, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        if not config.flash_jlink:
            return FlashResult(
                passed=False,
                tool=self.name,
                error=f"Target '{config.name}' has no J-Link config defined",
                elapsed=time.monotonic() - t0,
            )

        script = self._build_script(firmware, config)
        jlink_bin = shutil.which("JLinkExe") or "JLinkExe"

        log.info("J-Link flash: device=%s", config.flash_jlink.get("device", "?"))

        try:
            result = subprocess.run(
                [jlink_bin, "-CommanderScript", "-"],
                input=script,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return FlashResult(
                passed=False, tool=self.name,
                log="J-Link timed out after 60s",
                elapsed=time.monotonic() - t0,
                error="Timeout",
            )

        elapsed = time.monotonic() - t0
        combined = result.stdout + "\n" + result.stderr
        passed = "ERROR" not in result.stdout.upper() and result.returncode == 0

        return FlashResult(
            passed=passed,
            log=combined.strip(),
            tool=self.name,
            elapsed=elapsed,
            error=None if passed else f"J-Link error (exit {result.returncode})",
        )

    def erase(self, config: TargetConfig) -> FlashResult:
        t0 = time.monotonic()

        if not config.flash_jlink:
            return FlashResult(
                passed=False, tool=self.name,
                error=f"Target '{config.name}' has no J-Link config",
                elapsed=time.monotonic() - t0,
            )

        script = self._build_script("", config, action="erase")
        jlink_bin = shutil.which("JLinkExe") or "JLinkExe"

        try:
            result = subprocess.run(
                [jlink_bin, "-CommanderScript", "-"],
                input=script, capture_output=True, text=True, timeout=60,
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
