# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — Flash Abstraction Layer (FAL) v0.5.0.

Provides a unified interface for flashing firmware to target hardware
using OpenOCD, J-Link, pyOCD, or other backends.

The ``FlashRunner`` auto-detects available flash tools on the system and
delegates to the appropriate backend. Users can also specify a preferred
tool explicitly.

Usage::

    # Auto-detect available flash tool
    runner = FlashRunner(target="stm32f4")
    result = runner.flash("build/firmware.elf")
    print(result)

    # Explicit tool selection
    runner = FlashRunner(target="stm32f4", tool="jlink")
    result = runner.flash("build/firmware.elf")
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .target_config import TargetConfig

log = logging.getLogger("cross.flash")


# ---------------------------------------------------------------------------
# Result and error types
# ---------------------------------------------------------------------------


@dataclass
class FlashResult:
    """Result of a flash operation.

    Attributes
    ----------
    passed : bool
        ``True`` if flashing succeeded.
    log : str
        Full stdout/stderr output from the flash tool.
    tool : str
        The flash tool used (e.g. ``"openocd"``, ``"jlink"``).
    elapsed : float
        Wall-clock duration in seconds.
    error : str | None
        Error message on failure.
    """

    passed: bool = True
    log: str = ""
    tool: str = ""
    elapsed: float = 0.0
    error: str | None = None


class FlashError(RuntimeError):
    """Raised when no suitable flash tool is available, or when a
    flash operation fails irrecoverably."""
    pass


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class FlashTool(ABC):
    """Abstract base for all flash tool implementations.

    Subclasses must implement :meth:`name` and :meth:`write`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier (e.g. ``"openocd"``, ``"jlink"``)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this tool is installed on the system."""
        ...

    @abstractmethod
    def write(self, firmware: str, config: TargetConfig) -> FlashResult:
        """Flash *firmware* to the target described by *config*.

        Parameters
        ----------
        firmware : str
            Path to the firmware file (``.elf``, ``.hex``, or ``.bin``).
        config : TargetConfig
            Target board configuration (must have flash-related fields).

        Returns
        -------
        FlashResult
        """
        ...

    @abstractmethod
    def erase(self, config: TargetConfig) -> FlashResult:
        """Erase the target device flash memory.

        Parameters
        ----------
        config : TargetConfig
            Target board configuration.

        Returns
        -------
        FlashResult
        """
        ...

    def verify(self, firmware: str, config: TargetConfig) -> FlashResult:
        """Verify the flashed firmware matches the source file.

        Default implementation delegates to :meth:`write` with a verify
        flag if supported by the tool, otherwise returns a best-effort
        result.
        """
        return FlashResult(
            passed=False,
            log="Verify not supported by this tool",
            tool=self.name,
            error="Verify not supported",
        )


# ---------------------------------------------------------------------------
# OpenOCD Runner
# ---------------------------------------------------------------------------


class OpenOCDRunner(FlashTool):
    """Flash runner using OpenOCD (Open On-Chip Debugger).

    OpenOCD is the most widely-supported open-source debug tool,
    covering ST-Link, J-Link, FTDI, CMSIS-DAP, and many other
    debug probe interfaces.
    """

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

        # Build command: -f <config> -c "program <firmware> <address> verify exit"
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
        """Verify flash contents against the firmware file."""
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


# ---------------------------------------------------------------------------
# J-Link Runner
# ---------------------------------------------------------------------------


class JLinkRunner(FlashTool):
    """Flash runner using SEGGER J-Link Commander.

    J-Link is the industry-standard debug probe for ARM Cortex-M
    devices, offering the highest flash speed (up to 50 MHz SWO).
    """

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
        """Build a J-Link Commander script for flashing or erasing."""
        device = "STM32F407VG"  # default fallback
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


# ---------------------------------------------------------------------------
# pyOCD Runner
# ---------------------------------------------------------------------------


class PyOCDRunner(FlashTool):
    """Flash runner using pyOCD (Python-based CMSIS-DAP debugger).

    pyOCD is a pure-Python debug probe that supports CMSIS-DAP
    adapters (including DAPLink, ST-Link, and J-Link in CMSIS-DAP
    mode). It is the easiest to install (``pip install pyocd``) and
    works on all platforms.
    """

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

        target = "stm32f407vg"  # default fallback

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


# ---------------------------------------------------------------------------
# Auto-detection registry
# ---------------------------------------------------------------------------

_BUILTIN_TOOLS: list[type[FlashTool]] = [
    OpenOCDRunner,
    JLinkRunner,
    PyOCDRunner,
]


def _discover_tools(preferred: str | None = None) -> list[FlashTool]:
    """Discover available flash tools, optionally preferring one.

    Returns a list of tool instances sorted by availability and
    preference order: OpenOCD > JLink > pyOCD.
    """
    tools: list[FlashTool] = []

    for tool_cls in _BUILTIN_TOOLS:
        instance = tool_cls()
        if preferred and instance.name == preferred:
            # Put preferred tool first
            tools.insert(0, instance)
        elif instance.is_available():
            tools.append(instance)

    return tools


# ---------------------------------------------------------------------------
# FlashRunner: main public interface
# ---------------------------------------------------------------------------


class FlashRunner:
    """Unified firmware flashing interface.

    Auto-detects available flash tools and provides a unified
    ``flash()``, ``erase()``, and ``verify()`` API.

    Parameters
    ----------
    target : str or TargetConfig
        Target board name (e.g. ``"stm32f4"``) or a ``TargetConfig``
        instance.
    tool : str, optional
        Preferred flash tool (``"openocd"``, ``"jlink"``, ``"pyocd"``).
        If not specified, auto-detect from available tools.
    base_dir : str, optional
        Project base directory for YAML target resolution.

    Raises
    ------
    FlashError
        If no flash tool is available, or if the target configuration
        cannot be found.
    """

    def __init__(
        self,
        target: str | TargetConfig,
        tool: str | None = None,
        base_dir: str | None = None,
    ):
        # Resolve target config
        if isinstance(target, str):
            self.config = load_target_config_safe(target, base_dir)
        else:
            self.config = target

        # Resolve tool
        self._tools = _discover_tools(preferred=tool)

        if not self._tools:
            tools_str = ", ".join(t().name for t in _BUILTIN_TOOLS)
            raise FlashError(
                f"No flash tool available. Checked: {tools_str}. "
                f"Install openocd, JLinkExe, or pyocd."
            )

        self._active_tool: FlashTool = self._tools[0]
        log.info(
            "FlashRunner ready: target=%s tool=%s",
            self.config.name, self._active_tool.name,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tool_name(self) -> str:
        """Name of the active flash tool."""
        return self._active_tool.name

    @property
    def available_tools(self) -> list[str]:
        """Names of all available flash tools."""
        return [t.name for t in self._tools]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def flash(self, firmware: str) -> FlashResult:
        """Flash *firmware* to the target.

        Parameters
        ----------
        firmware : str
            Path to the firmware file (``.elf``, ``.hex``, or ``.bin``).

        Returns
        -------
        FlashResult
        """
        if not os.path.isfile(firmware):
            return FlashResult(
                passed=False,
                tool=self._active_tool.name,
                error=f"Firmware file not found: {firmware}",
            )

        result = self._active_tool.write(firmware, self.config)
        if not result.passed and len(self._tools) > 1:
            # Try fallback tools
            for tool in self._tools[1:]:
                log.info("Falling back to %s for flash", tool.name)
                result = tool.write(firmware, self.config)
                if result.passed:
                    self._active_tool = tool
                    break

        return result

    def erase(self) -> FlashResult:
        """Erase all flash memory on the target.

        Returns
        -------
        FlashResult
        """
        result = self._active_tool.erase(self.config)
        return result

    def verify(self, firmware: str) -> FlashResult:
        """Verify flashed firmware.

        Parameters
        ----------
        firmware : str
            Source firmware file to verify against.

        Returns
        -------
        FlashResult
        """
        result = self._active_tool.verify(firmware, self.config)
        return result


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def flash_firmware(
    target: str | TargetConfig,
    firmware: str,
    tool: str | None = None,
) -> FlashResult:
    """One-shot convenience function for flashing firmware.

    Usage::

        result = flash_firmware("stm32f4", "build/firmware.elf")
        print(result)
    """
    runner = FlashRunner(target=target, tool=tool)
    return runner.flash(firmware)


def detect_hardware() -> list[dict[str, Any]]:
    """Detect connected debug probes and target boards.

    Scans for OpenOCD, J-Link, and pyOCD compatible hardware.

    Returns
    -------
    list[dict]
        Each dict contains ``tool``, ``description``, and ``serial`` fields.
    """
    detected: list[dict[str, Any]] = []

    # pyOCD probe detection (most informative)
    try:
        import pyocd  # noqa: F401
        from pyocd.core.helpers import ConnectHelper

        probes = ConnectHelper.get_all_connected_probes()
        for probe in probes:
            detected.append({
                "tool": "pyocd",
                "description": str(probe),
                "serial": probe.unique_id or "unknown",
            })
    except ImportError:
        pass
    except Exception as exc:
        log.debug("pyOCD probe detection: %s", exc)

    # J-Link probe detection via JLinkExe
    if shutil.which("JLinkExe"):
        try:
            result = subprocess.run(
                ["JLinkExe", "-DeviceInfo", "-USB", "0"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout:
                for line in result.stdout.split("\n"):
                    if "Serial" in line or "Device" in line:
                        detected.append({
                            "tool": "jlink",
                            "description": line.strip(),
                            "serial": "unknown",
                        })
        except Exception as e:
            logging.getLogger("cross.flash").warning("Flash tool check failed: %s", e)
            pass

    return detected


# Import load_target_config with safe fallback
def load_target_config_safe(name: str, base_dir: str | None = None) -> TargetConfig:
    """Load a target config, with a helpful error if the target doesn't exist."""
    from .target_config import load_target_config, discover_targets

    try:
        return load_target_config(name, base_dir=base_dir)
    except FileNotFoundError:
        available = discover_targets(base_dir=base_dir)
        avail_str = ", ".join(sorted(available.keys())) if available else "(none)"
        raise FlashError(
            f"Target '{name}' not found. Available targets: {avail_str}"
        )
