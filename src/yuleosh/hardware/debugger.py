#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
debugger — AI 驱动的调试分析器

分析串口输出 + GDB 回溯 → 定位根因。

支持：
  - 日志错误模式识别（HardFault、stack overflow、assert 等）
  - 寄存器状态解析
  - AI 辅助修复建议（基于规则 + LLM 可选）

Usage::

    from hardware.debugger import AIDebugger, DebugReport

    debugger = AIDebugger()
    report = debugger.analyze_log(["Boot OK", "HardFault at 0x08001234"])
    fix = debugger.suggest_fix(report.error, code_source)

"""

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger("hardware.debugger")


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

@dataclass
class DebugReport:
    """调试分析报告。

    Attributes
    ----------
    error : str
        检测到的主要错误描述。
    severity : str
        严重等级: ``"critical"`` / ``"error"`` / ``"warning"`` / ``"info"``。
    error_type : str
        错误类型（如 ``"hardfault"``, ``"assert_fail"``, ``"stack_overflow"``）。
    registers : dict
        GDB 中提取的寄存器值。
    stack_trace : list[str]
        提取的栈回溯行。
    raw_logs : list[str]
        原始日志（截断至 200 行）。
    suggestions : list[str]
        诊断建议。
    matched_rules : list[str]
        匹配到的错误检测规则。
    """

    error: str = ""
    severity: str = "info"
    error_type: str = "unknown"
    registers: dict = field(default_factory=dict)
    stack_trace: list[str] = field(default_factory=list)
    raw_logs: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "error": self.error,
            "severity": self.severity,
            "error_type": self.error_type,
            "registers": self.registers,
            "stack_trace": self.stack_trace,
            "raw_logs": self.raw_logs[:50],  # 报告只包含前 50 行
            "suggestions": self.suggestions,
            "matched_rules": self.matched_rules,
        }

    def summary(self) -> str:
        lines = [
            f"[{self.severity.upper()}] {self.error_type}: {self.error}",
        ]
        if self.registers:
            lines.append(f"  Registers: {self.registers}")
        if self.stack_trace:
            lines.append("  Stack trace:")
            for frame in self.stack_trace[:10]:
                lines.append(f"    {frame}")
        if self.suggestions:
            lines.append("  Suggestions:")
            for s in self.suggestions:
                lines.append(f"    - {s}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 错误模式规则
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, str, str, str, list[str]]] = [
    # (error_type, severity, pattern, description, suggestions)
    (
        "hardfault",
        "critical",
        r"HardFault|hard fault|UsageFault|BusFault|MemManage",
        "HardFault 异常 — 通常由非法内存访问、对齐错误或栈溢出触发",
        [
            "检查空指针解引用",
            "检查数组越界访问",
            "检查栈大小是否充足（链接脚本中的 Stack_Size）",
            "检查是否在中断中调用不安全的函数",
            "使用 GDB 'bt' 查看回溯，'info registers' 查看寄存器",
        ],
    ),
    (
        "assert_fail",
        "critical",
        r"assert.*failed|Assertion.*failed|ASSERT|assert_failed",
        "断言失败 — 运行时条件未满足",
        [
            "检查断言条件中的变量值",
            "确认初始化顺序是否正确",
            "添加日志输出相关变量以便调试",
        ],
    ),
    (
        "stack_overflow",
        "error",
        r"stack overflow|Stack Overflow|malloc.*failed|out of memory",
        "栈溢出或内存分配失败",
        [
            "增大链接脚本中的 Stack_Size / Heap_Size",
            "检查递归调用深度",
            "检查是否有大数组在栈上分配",
            "改用动态分配或全局数组",
        ],
    ),
    (
        "wdt_reset",
        "warning",
        r"watchdog|WDT|IWDG|WWDG|reset.*by.*watchdog",
        "看门狗复位 — 主循环未及时喂狗",
        [
            "检查主循环执行周期是否过长",
            "确认看门狗超时配置是否合理",
            "在长时间操作前添加看门狗喂狗调用",
        ],
    ),
    (
        "div_zero",
        "error",
        r"divide by zero|division by zero|DivisionByZero",
        "除零错误",
        [
            "检查除法运算前是否有除数判断",
            "检查移位操作中移位数是否过大",
        ],
    ),
    (
        "fault_isr",
        "warning",
        r"Default_Handler|Fault_IRQHandler|unhandled interrupt",
        "未处理的中断/异常 — 中断向量表可能未正确配置",
        [
            "检查所有使能的中断是否有对应的 ISR",
            "检查中断向量表地址设置是否正确",
            "使用 SCB->VTOR 确认向量表位置",
        ],
    ),
    (
        "boot_fail",
        "error",
        r"Boot.*fail|Failed to boot|Startup.*error|Init.*failed",
        "启动初始化失败",
        [
            "检查硬件初始化顺序",
            "确认时钟配置是否正确",
            "检查外设初始化是否有依赖关系未满足",
        ],
    ),
    (
        "timeout",
        "warning",
        r"timeout|timed? ?out|Timeout",
        "操作超时",
        [
            "检查外设是否正常工作",
            "检查总线时钟配置",
            "确认等待循环的条件是否可能永远无法满足",
        ],
    ),
    (
        "general_error",
        "error",
        r"Error:|error:|FAIL|failed|ERROR",
        "通用错误",
        [
            "查看错误前的日志上下文",
            "检查外围设备状态寄存器",
        ],
    ),
]


# ---------------------------------------------------------------------------
# AI 调试器
# ---------------------------------------------------------------------------

class AIDebugger:
    """AI 驱动的调试分析器。

    通过规则匹配和启发式分析识别嵌入式系统中的常见错误模式。
    LLM 集成可选，默认基于规则引擎运行。
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client  # 可选 LLM 客户端用于增强分析
        self._patterns = _ERROR_PATTERNS

    # ---- 日志分析 --------------------------------------------------------

    def analyze_log(self, log_lines: list[str]) -> DebugReport:
        """分析串口日志，生成调试报告。

        Parameters
        ----------
        log_lines : list[str]
            串口日志行列表（通常来自 ``SerialMonitor.get_log()``）。

        Returns
        -------
        DebugReport
            结构化的调试分析报告。
        """
        report = DebugReport(raw_logs=log_lines)

        for line in log_lines:
            for err_type, severity, pattern, desc, suggestions in self._patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # 优先级：保留更严重的错误
                    severity_rank = {
                        "critical": 3, "error": 2, "warning": 1, "info": 0,
                    }
                    existing_rank = severity_rank.get(report.severity, 0)
                    new_rank = severity_rank.get(severity, 0)

                    if new_rank > existing_rank:
                        report.error = line
                        report.severity = severity
                        report.error_type = err_type
                        report.suggestions = suggestions
                    elif new_rank == existing_rank:
                        # 同等级追加
                        report.matched_rules.append(
                            f"{err_type}: {desc} (matched: {line!r})"
                        )
                        if suggestions:
                            report.suggestions.extend(suggestions)
                    else:
                        report.matched_rules.append(
                            f"{err_type}: {desc} (matched: {line!r})"
                        )

        # 如果没有匹配到错误，标记为 info
        if not report.error_type or report.error_type == "unknown":
            # 尝试提取潜在问题
            self._heuristic_scan(log_lines, report)
        else:
            # 去重建议
            report.suggestions = list(dict.fromkeys(report.suggestions))

        # 提取可能的栈回溯
        report.stack_trace = self._extract_stack_trace(log_lines)

        if report.error:
            log.info(
                "Debug analysis: [%s] %s — %s",
                report.severity.upper(),
                report.error_type,
                report.error[:120],
            )

        return report

    def _heuristic_scan(self, log_lines: list[str], report: DebugReport):
        """启发式扫描 — 无显式错误时检查异常模式。"""
        # 检查是否有正常的启动日志
        has_boot = any(
            "Boot" in line or "boot" in line or "Starting" in line or "Init" in line
            for line in log_lines
        )
        has_ok = any("OK" in line or "ok" in line or "done" in line for line in log_lines)

        if not log_lines or not has_boot:
            report.error_type = "no_boot_output"
            report.severity = "warning"
            report.error = "No boot initialization messages detected in serial output"
            report.suggestions = [
                "检查硬件连接和供电",
                "确认刷写的固件是否正确",
                "检查串口波特率配置是否匹配",
                "检查 bootloader 是否正确跳转到应用程序",
            ]
        elif not has_ok and has_boot:
            report.error_type = "incomplete_boot"
            report.severity = "warning"
            report.error = "Boot started but no completion signal detected"
            report.suggestions = [
                "检查初始化流程中是否有阻塞",
                "检查外设配置是否有误",
                "启用更详细的启动日志",
            ]

    @staticmethod
    def _extract_stack_trace(log_lines: list[str]) -> list[str]:
        """从日志中提取 GDB 风格的栈回溯。"""
        trace = []
        in_trace = False
        for line in log_lines:
            if re.search(r"(HardFault|backtrace|Stack Trace|#\d+)\s", line, re.IGNORECASE):
                in_trace = True
            if in_trace:
                trace.append(line)
                if "#   " in line and "??" in line:
                    continue
                if in_trace and len(trace) > 30:
                    break
        return trace

    # ---- 修复建议 --------------------------------------------------------

    def suggest_fix(self, error: str, code: str) -> str:
        """根据错误和源代码给出修复建议。

        优先使用规则匹配，如果配置了 LLM 客户端则调用 LLM 增强。

        Parameters
        ----------
        error : str
            错误信息。
        code : str
            相关源代码片段。

        Returns
        -------
        str
            修复建议文本。
        """
        # 1. 规则匹配
        for err_type, severity, pattern, desc, suggestions in self._patterns:
            if re.search(pattern, error, re.IGNORECASE):
                rule_advice = "\n".join(f"- {s}" for s in suggestions)
                result = (
                    f"### 检测到: {desc}\n"
                    f"**类型**: {err_type} | **严重等级**: {severity}\n\n"
                    f"**规则建议**:\n{rule_advice}\n\n"
                    f"**错误原文**:\n```\n{error}\n```"
                )

                # 2. 如果有 LLM，调用 LLM 增强
                if self.llm:
                    try:
                        llm_suggestion = self._call_llm(error, code)
                        result += f"\n\n**LLM 分析**:\n{llm_suggestion}"
                    except Exception as exc:
                        log.warning("LLM fix suggestion failed: %s", exc)

                return result

        # 无规则匹配时的通用建议
        return (
            f"### 无法自动识别错误模式\n\n"
            f"**错误原文**:\n```\n{error}\n```\n\n"
            f"**通用排查建议**:\n"
            f"- 查看完整日志上下文\n"
            f"- 检查最近的代码变更\n"
            f"- 使用 GDB 远程调试\n"
            f"- 添加更多调试日志输出"
        )

    def _call_llm(self, error: str, code: str) -> str:
        """调用可选的 LLM 客户端进行增强分析。"""
        if hasattr(self.llm, "complete"):
            prompt = (
                f"你是一个嵌入式系统调试专家。\n\n"
                f"用户遇到以下错误：\n```\n{error}\n```\n\n"
                f"相关源代码：\n```\n{code}\n```\n\n"
                f"请分析根因并提供修复建议。"
            )
            result = self.llm.complete(prompt)
            return result if isinstance(result, str) else str(result)
        return "(LLM analysis not available)"

    # ---- 寄存器分析 ------------------------------------------------------

    @staticmethod
    def check_registers(gdb_output: str) -> dict:
        """解析 GDB ``info registers`` 输出。

        识别常见的异常寄存器状态。

        Parameters
        ----------
        gdb_output : str
            GDB 命令的输出（如 ``info registers``）。

        Returns
        -------
        dict
            ``{"registers": {...}, "flags": [...], "suspicious": [...]}``
        """
        registers = {}
        flags = []
        suspicious = []

        # 解析寄存器行：r0             0x0      0
        reg_pattern = re.compile(
            r"^([a-z0-9_]+)\s+(0x[0-9a-fA-F]+)\s+.*", re.MULTILINE
        )
        for match in reg_pattern.finditer(gdb_output):
            name, value = match.group(1), match.group(2)
            registers[name] = value

            # 检测可疑值
            val_int = int(value, 16) if value.startswith("0x") else 0
            if name in ("pc", "lr") and val_int == 0:
                suspicious.append(f"{name}=0x0 — 可能为空指针调用")
            if name == "sp" and val_int < 0x20000000:
                suspicious.append(f"SP=0x{val_int:08X} — 栈指针超出 SRAM 范围")

        # 检测异常标志
        if "xpsr" in registers:
            xpsr = int(registers["xpsr"], 16)
            if xpsr & 0x100:  # IPSR 非零 → 在中断中
                ipsr = xpsr & 0x1FF
                flags.append(f"Exception active: IRQ#{ipsr}")

        return {
            "registers": registers,
            "flags": flags,
            "suspicious": suspicious,
        }

    def __repr__(self) -> str:
        return "<AIDebugger llm={}>".format(
            "enabled" if self.llm else "rules-only"
        )
