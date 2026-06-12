# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH cross-layer modules.

Provides SIL simulation, flash abstraction, and hardware-in-the-loop (HIL)
testing capabilities for embedded targets.
"""

from .target_config import TargetConfig, load_target_config, discover_targets
from .sil_assert import SerialAssert, SilAssertionError, ExpectScriptError, run_expect_script
from .sil_runner import QemuSilRunner, SilResult, sil_test
from .flash import (
    FlashRunner,
    FlashTool,
    FlashResult,
    FlashError,
    OpenOCDRunner,
    JLinkRunner,
    PyOCDRunner,
    flash_firmware,
    detect_hardware,
    load_target_config_safe,
)
from .serial_monitor import (
    SerialMonitor,
    PipeSerialMonitor,
    SerialMonitorTimeout,
    SerialMonitorResult,
)
from .hil_runner import HilTestRunner, HilTestResult, hil_test

__all__ = [
    # target config
    "TargetConfig",
    "load_target_config",
    "discover_targets",
    # SIL
    "SerialAssert",
    "SilAssertionError",
    "ExpectScriptError",
    "run_expect_script",
    "QemuSilRunner",
    "SilResult",
    "sil_test",
    # Flash
    "FlashRunner",
    "FlashTool",
    "FlashResult",
    "FlashError",
    "OpenOCDRunner",
    "JLinkRunner",
    "PyOCDRunner",
    "flash_firmware",
    "detect_hardware",
    "load_target_config_safe",
    # Serial Monitor
    "SerialMonitor",
    "PipeSerialMonitor",
    "SerialMonitorTimeout",
    "SerialMonitorResult",
    # HIL
    "HilTestRunner",
    "HilTestResult",
    "hil_test",
]
