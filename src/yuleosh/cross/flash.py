"""
yuleOSH — Flash Abstraction Layer (FAL) v0.5.0.

Backwards-compatible re-export module.  Backend runners (OpenOCD, JLink,
pyOCD) live in sub-modules; ``FlashTool`` / ``FlashResult`` / ``FlashError``
come from ``base``.  This module keeps ``FlashRunner``, convenience helpers,
and all public exports for test-mock compatibility.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base import FlashResult, FlashError, FlashTool
from .openocd import OpenOCDRunner
from .jlink import JLinkRunner
from .pyocd import PyOCDRunner
from .target_config import TargetConfig

log = logging.getLogger("cross.flash")


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_BUILTIN_TOOLS: list[type[FlashTool]] = [
    OpenOCDRunner,
    JLinkRunner,
    PyOCDRunner,
]


def _discover_tools(preferred: str | None = None) -> list[FlashTool]:
    """Discover available flash tools, optionally preferring one."""
    tools: list[FlashTool] = []

    for tool_cls in _BUILTIN_TOOLS:
        instance = tool_cls()
        if preferred and instance.name == preferred:
            tools.insert(0, instance)
        elif instance.is_available():
            tools.append(instance)

    return tools


# ---------------------------------------------------------------------------
# FlashRunner: main public interface
# ---------------------------------------------------------------------------


class FlashRunner:
    """Unified firmware flashing interface."""

    def __init__(
        self,
        target: str | TargetConfig,
        tool: str | None = None,
        base_dir: str | None = None,
    ):
        if isinstance(target, str):
            self.config = load_target_config_safe(target, base_dir)
        else:
            self.config = target

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

    @property
    def tool_name(self) -> str:
        return self._active_tool.name

    @property
    def available_tools(self) -> list[str]:
        return [t.name for t in self._tools]

    def flash(self, firmware: str) -> FlashResult:
        if not os.path.isfile(firmware):
            return FlashResult(
                passed=False,
                tool=self._active_tool.name,
                error=f"Firmware file not found: {firmware}",
            )

        result = self._active_tool.write(firmware, self.config)
        if not result.passed and len(self._tools) > 1:
            for tool in self._tools[1:]:
                log.info("Falling back to %s for flash", tool.name)
                result = tool.write(firmware, self.config)
                if result.passed:
                    self._active_tool = tool
                    break

        return result

    def erase(self) -> FlashResult:
        return self._active_tool.erase(self.config)

    def verify(self, firmware: str) -> FlashResult:
        return self._active_tool.verify(firmware, self.config)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def flash_firmware(
    target: str | TargetConfig,
    firmware: str,
    tool: str | None = None,
) -> FlashResult:
    """One-shot convenience function for flashing firmware."""
    runner = FlashRunner(target=target, tool=tool)
    return runner.flash(firmware)


def detect_hardware() -> list[dict[str, Any]]:
    """Detect connected debug probes and target boards."""
    detected: list[dict[str, Any]] = []

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

    return detected


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
