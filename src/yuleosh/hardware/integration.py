#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
integration — Pipeline 集成（Step 6 for yuleOSH Pipeline）

将 ``HardwareDeployer`` 包装为 ``HardwareStep``，融入 yuleOSH Pipeline
的 Step 6 工作流：

  1. 编译（复用现有 pipeline 编译步骤）
  2. 刷写（调用 flasher）
  3. 监视（调用 monitor，超时或检测到特定输出）
  4. 分析（调用 AI debugger）
  5. 报告

Usage::

    step = HardwareStep(config={
        "flasher": "openocd",
        "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
        "port": "/dev/ttyUSB0",
        "baud": 115200,
        "monitor_timeout": 30,
        "wait_for": "Boot OK",
    })
    result = step.execute(context)
    print(result.report.summary())

"""

import dataclasses
import json
import logging
import os
import time

from .debugger import DebugReport
from .flasher import FlashError, BinaryNotFoundError, ToolNotFoundError, HardwareNotFoundError
from .monitor import SerialMonitor

log = logging.getLogger("hardware.integration")


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class StepResult:
    """Pipeline Step 6 的执行结果。

    Attributes
    ----------
    success : bool
        整个步骤是否成功。
    flash_ok : bool
        刷写是否成功。
    monitor_ok : bool
        监视是否成功（捕获到预期输出或正常超时）。
    report : DebugReport | None
        调试分析报告。
    artifacts : dict
        生成的工件路径。
    error : str | None
        错误信息。
    duration_ms : int
        执行耗时（毫秒）。
    """

    success: bool = False
    flash_ok: bool = False
    monitor_ok: bool = False
    report: DebugReport | None = None
    artifacts: dict = dataclasses.field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        if self.report:
            d["report"] = self.report.to_dict()
        else:
            d["report"] = None
        return d

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"Hardware Step {'✅ PASS' if self.success else '❌ FAIL'} "
            f"({self.duration_ms}ms)",
            "=" * 60,
            f"  Flash : {'✅' if self.flash_ok else '❌'}",
            f"  Monitor: {'✅' if self.monitor_ok else '❌'}",
        ]
        if self.report:
            lines.append(f"  Debug  : [{self.report.severity.upper()}] {self.report.error_type}")
            if self.report.error:
                lines.append(f"           {self.report.error[:120]}")
        if self.error:
            lines.append(f"  Error  : {self.error}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()


# ---------------------------------------------------------------------------
# Pipeline Step
# ---------------------------------------------------------------------------

class HardwareStepError(RuntimeError):
    """HardwareStep 执行过程中的错误。"""


class HardwareStep:
    """Pipeline Step 6 — 硬件部署与调试。

    必须放入 yuleOSH Pipeline 中作为 Step 6 使用。

    Config 参数
    -----------
    flasher : str
        刷写器类型（``"openocd"`` / ``"jlink"`` / ``"esptool"``）。
    flasher_config : dict
        传递给刷写器的配置。
    port : str
        串口设备路径。
    baud : int
        串口波特率，默认 115200。
    monitor_timeout : int
        监视超时秒数，默认 30。
    wait_for : str, optional
        等待串口输出的特定字符串。如果设置，监视器会在检测到该
        字符串后自动停止（而非等待超时）。
    max_retries : int
        刷写失败重试次数，默认 2。
    retry_delay : int
        重试间隔秒数，默认 3。
    binary_path : str
        固件文件路径（由 Pipeline 前序步骤编译产生）。
    output_dir : str
        工件输出目录，默认 ``"artifacts/hardware"``。
    """

    step_key = "hardware"
    agent = "HardwareStep"
    description = "Code → Compile → Flash → Monitor → Debug → Iterate"
    output_filename = "hardware-result.json"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    # ---- Pipeline 集成接口 -----------------------------------------------

    def execute(self, context: dict | None = None) -> StepResult:
        """执行 Hardware Step。

        Parameters
        ----------
        context : dict, optional
            Pipeline 上下文，包含前序步骤的产物路径等信息。
            如果提供了 ``"binary_path"`` 键，将自动使用。

        Returns
        -------
        StepResult
        """
        start = time.monotonic()
        context = context or {}

        # 读取配置（context 覆盖 config）
        flasher = context.get("flasher") or self.config.get("flasher", "openocd")
        flasher_config = context.get("flasher_config") or self.config.get("flasher_config", {})
        port = context.get("port") or self.config.get("port", "/dev/ttyUSB0")
        baud = context.get("baud") or self.config.get("baud", 115200)
        monitor_timeout = context.get("monitor_timeout") or self.config.get("monitor_timeout", 30)
        wait_for = context.get("wait_for") or self.config.get("wait_for")
        max_retries = context.get("max_retries") or self.config.get("max_retries", 2)
        retry_delay = context.get("retry_delay") or self.config.get("retry_delay", 3)

        # 二进制文件路径（前序步骤产物）
        binary_path = (
            context.get("binary_path")
            or self.config.get("binary_path")
            or self._find_artifact(context)
        )

        if not binary_path:
            # 非阻塞：没有产物时给出提示而非报错
            result = StepResult(
                success=True,
                flash_ok=False,
                monitor_ok=False,
                report=DebugReport(
                    error="No binary artifact found; hardware step skipped",
                    severity="info",
                    error_type="skipped",
                ),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            log.info("Hardware step skipped (no binary artifact)")
            return result

        # 输出目录
        output_dir = self.config.get("output_dir", "artifacts/hardware")
        os.makedirs(output_dir, exist_ok=True)

        # ---- 执行 --------------------------------------------------------

        try:
            self._check_binary(binary_path)
            # 延迟导入避免循环引用
            from . import HardwareDeployer
            deployer = HardwareDeployer(
                flasher=flasher,
                config=flasher_config,
                port=port,
                baud=baud,
            )

            # 1. 刷写（带重试）
            flash_ok = False
            for attempt in range(max_retries + 1):
                try:
                    flash_ok = deployer.flash(binary_path)
                    if flash_ok:
                        log.info("Flash succeeded on attempt %d/%d", attempt + 1, max_retries + 1)
                        break
                except (FlashError, BinaryNotFoundError, ToolNotFoundError, HardwareNotFoundError) as exc:
                    log.warning(
                        "Flash attempt %d/%d failed: %s",
                        attempt + 1, max_retries + 1, exc,
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay)

            if not flash_ok:
                result = StepResult(
                    success=False,
                    flash_ok=False,
                    error=f"Flash failed after {max_retries + 1} attempts",
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                self._write_result(output_dir, result)
                return result

            # 2. 验证（可选）
            try:
                deployer.verify(binary_path)
            except Exception as exc:
                log.warning("Verify failed (non-fatal): %s", exc)

            # 3. 监视
            monitor_ok = True
            deployer.monitor(port=port, baud=baud)
            try:
                if wait_for:
                    log.info("Waiting for '%s' (timeout=%ds)...", wait_for, monitor_timeout)
                    found = deployer.wait_for_output(wait_for, timeout=monitor_timeout)
                    if found:
                        log.info("Expected output detected: '%s'", wait_for)
                    else:
                        log.warning("Timeout waiting for '%s'", wait_for)
                    monitor_ok = found
                else:
                    # 无特定等待字符串：等待超时
                    log.info("Monitoring for %ds (no wait target)...", monitor_timeout)
                    time.sleep(monitor_timeout)
            finally:
                deployer.stop_monitor()

            # 4. 分析
            report = deployer.analyze()

            # 5. 收集工件
            artifacts = {
                "binary": binary_path,
                "log": "\n".join(deployer.get_log()),
                "report": report.to_dict(),
                "report_path": os.path.abspath(os.path.join(output_dir, "debug-report.json")),
            }

            # 保存报告
            report_path = artifacts["report_path"]
            with open(report_path, "w") as f:
                json.dump(report.to_dict(), f, indent=2)
            log.info("Debug report saved to %s", report_path)

            result = StepResult(
                success=True,
                flash_ok=True,
                monitor_ok=monitor_ok,
                report=report,
                artifacts=artifacts,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

            self._write_result(output_dir, result)
            return result

        except Exception as exc:
            log.error("Hardware step failed: %s", exc, exc_info=True)
            result = StepResult(
                success=False,
                error=str(exc),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            self._write_result(output_dir, result)
            return result

    # ---- 辅助方法 --------------------------------------------------------

    @staticmethod
    def _check_binary(binary_path: str):
        if not os.path.isfile(binary_path):
            raise BinaryNotFoundError(
                f"Binary not found at: {binary_path}\n"
                f"  Did the previous pipeline step produce output?"
            )

    @staticmethod
    def _find_artifact(context: dict) -> str | None:
        """在 context 中查找前序步骤生成的固件文件。"""
        # 常见的 pipeline artifact 路径 key
        artifact_keys = [
            "firmware_path",
            "output_path",
            "artifact_path",
            "compile_output",
            "binary",
        ]
        for key in artifact_keys:
            val = context.get(key)
            if val and isinstance(val, str) and os.path.isfile(val):
                return val
        return None

    @staticmethod
    def _write_result(output_dir: str, result: StepResult):
        result_path = os.path.join(output_dir, "hardware-result.json")
        try:
            with open(result_path, "w") as f:
                result_dict = result.to_dict()
                # 移除大量原始日志数据以节省空间
                if result_dict.get("report") and result_dict["report"].get("raw_logs"):
                    result_dict["report"]["raw_logs"] = (
                        result_dict["report"]["raw_logs"][:20]
                        + [f"... ({len(result_dict['report']['raw_logs'])} total lines)"]
                    )
                json.dump(result_dict, f, indent=2)
        except Exception as exc:
            log.warning("Failed to write result file: %s", exc)
