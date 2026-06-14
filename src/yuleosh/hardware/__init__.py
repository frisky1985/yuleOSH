#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
hardware — 硬件在环（HIL）引擎

Pipeline Step 6: Code → Compile → Flash → Monitor → Debug → Iterate

提供完整的AI驱动的嵌入式硬件部署与调试管道，支持：
  - 多协议刷写（OpenOCD / JLink / esptool.py）
  - 串口实时监视与日志捕获
  - AI辅助的故障分析与根因定位
  - Pipeline集成

Usage::

    from hardware import HardwareDeployer

    deployer = HardwareDeployer(flasher="openocd", config={...})
    deployer.flash("firmware.elf")
    deployer.monitor(port="/dev/ttyUSB0")
    report = deployer.analyze()

"""

from .flasher import OpenOCDFlasher, JLinkFlasher, ESPToolFlasher
from .monitor import SerialMonitor
from .debugger import AIDebugger, DebugReport

import logging

log = logging.getLogger("hardware")


class HardwareDeployer:
    """AI驱动的嵌入式硬件部署与调试引擎。

    将 刷写 → 监视 → 分析 封装为统一的启动 API，
    适用于 Pipeline Step 6 的 Code → Compile → Flash → Monitor → Debug → Iterate 循环。

    Parameters
    ----------
    flasher : str
        刷写器类型，支持 ``"openocd"`` / ``"jlink"`` / ``"esptool"``。
    config : dict
        传递给具体刷写器的配置参数。
    port : str, optional
        串口设备路径（例如 ``"/dev/ttyUSB0"``）。
    baud : int
        串口波特率，默认 115200。
    """

    def __init__(
        self,
        flasher: str = "openocd",
        config: dict | None = None,
        port: str | None = None,
        baud: int = 115200,
    ):
        self.config = config or {}
        self.port = port
        self.baud = baud

        # 选择刷写器
        flasher_class = {
            "openocd": OpenOCDFlasher,
            "jlink": JLinkFlasher,
            "esptool": ESPToolFlasher,
        }.get(flasher.lower())
        if flasher_class is None:
            raise ValueError(
                f"Unknown flasher {flasher!r}. Supported: openocd, jlink, esptool"
            )
        self._flasher = flasher_class(self.config)

        # 监视器（延迟创建）
        self._monitor: SerialMonitor | None = None
        self._monitor_running: bool = False

        self._last_report: DebugReport | None = None

    # ---- 刷写 -----------------------------------------------------------

    def flash(self, binary_path: str) -> bool:
        """编译好的二进制文件刷写到目标硬件。"""
        log.info("Flashing %s ...", binary_path)
        ok = self._flasher.flash(binary_path)
        if not ok:
            log.error("Flash failed for %s", binary_path)
        return ok

    def verify(self, binary_path: str) -> bool:
        """验证刷写内容是否与源文件一致。"""
        log.info("Verifying %s ...", binary_path)
        return self._flasher.verify(binary_path)

    # ---- 监视 -----------------------------------------------------------

    def monitor(self, port: str | None = None, baud: int | None = None) -> "HardwareDeployer":
        """启动串口监视器（后台线程）。"""
        port = port or self.port
        if not port:
            raise ValueError("Serial port is required. Set `.port` or pass `port=`.")
        baud = baud or self.baud

        self._monitor = SerialMonitor(port, baud)
        self._monitor.start()
        self._monitor_running = True
        log.info("Serial monitor started on %s @ %d baud", port, baud)
        return self

    def stop_monitor(self):
        """停止串口监视器。"""
        if self._monitor and self._monitor_running:
            self._monitor.stop()
            self._monitor_running = False

    def get_log(self) -> list[str]:
        """获取监视器捕获的串口日志行。"""
        if self._monitor:
            return self._monitor.get_log()
        return []

    def wait_for_output(self, s: str, timeout: int = 10) -> bool:
        """等待串口出现特定字符串。"""
        if not self._monitor:
            raise RuntimeError("Monitor not started. Call .monitor() first.")
        return self._monitor.wait_for_string(s, timeout)

    # ---- 分析 -----------------------------------------------------------

    def analyze(self, gdb_output: str | None = None) -> DebugReport:
        """分析串口日志并生成调试报告。

        Parameters
        ----------
        gdb_output : str, optional
            可选的 GDB 回溯输出，用于寄存器/栈分析。
        """
        log_data = self.get_log()
        debugger = AIDebugger()
        report = debugger.analyze_log(log_data)

        if gdb_output:
            regs = debugger.check_registers(gdb_output)
            report.registers = regs

        self._last_report = report
        return report

    def suggest_fix(self, error: str, code: str) -> str:
        """根据错误信息和代码建议修复方案。"""
        return AIDebugger().suggest_fix(error, code)

    # ---- 状态 -----------------------------------------------------------

    @property
    def last_report(self) -> DebugReport | None:
        return self._last_report

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop_monitor()

    def __repr__(self) -> str:
        return (
            f"<HardwareDeployer flasher={self._flasher.__class__.__name__} "
            f"port={self.port}>"
        )
