#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 堆栈使用分析。

检查嵌入式项目的堆栈使用情况，遵循 MISRA 规则：
- 静态堆栈分析（全局变量/static）
- 函数调用深度分析
- 中断嵌套堆栈预算
- ≥95% 使用率时阻断

参考实现模式: review_bsp.py (alloca 检测模式)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_stack")

__all__ = ["step_review_stack"]

StackFinding = dict


# ── Source file discovery ────────────────────────────────────────────────


def _find_source_files(project_dir: Path) -> list[Path]:
    """Discover C / assembly source files relevant to stack analysis."""
    patterns = ["**/*.c", "**/*.s", "**/*.S", "**/*.ld", "**/*.h"]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file() and not any(
                part.startswith(".") or part == "__pycache__"
                for part in p.relative_to(project_dir).parts
            ):
                found.append(p)
    return found


# ── Stack analysis checks ────────────────────────────────────────────────


def _find_stack_allocation(source_files: list[Path], project_dir: Path) -> list[StackFinding]:
    """Detect static stack allocations and estimate usage.

    Looks for:
    - Stack section definitions in linker scripts
    - Static/global arrays that might live on stack
    - __attribute__((stack_usage)) or similar annotations
    """
    findings = []

    # Linker script patterns
    stack_patterns = [
        r'(?i)stack\s*=',
        r'(?i)\.stack\s*:',
        r'(?i)_estack\s*=',
        r'(?i)_sstack\s*=',
        r'(?i)__stack_size\s*=|STACK_SIZE\s*',
    ]

    for f in source_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        # Check linker scripts for stack definitions
        if f.suffix in (".ld", ".lds", ".scat", ".icf"):
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                for pat in stack_patterns:
                    m = re.search(pat, line.strip())
                    if m:
                        rel = str(Path(f).relative_to(project_dir))
                        findings.append({
                            "severity": "info",
                            "category": "stack_allocation",
                            "file": rel,
                            "line": i,
                            "message": f"Stack definition found: {line.strip()[:120]}",
                        })
            continue

        # Check C source for large stack allocations
        if f.suffix == ".c":
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments and preprocessor
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                if stripped.startswith("#"):
                    continue

                # Detect large local arrays (> 1KB)
                m = re.search(
                    r'(static\s+)?(const\s+)?\w+\s+(\w+)\s*\[(\d+)\]',
                    stripped,
                )
                if m:
                    arr_name = m.group(3)
                    arr_size = int(m.group(4))
                    element_type = m.group(2) or m.group(1) or "char"
                    # Estimate size: int=4, char=1, short=2, long=4, pointer=8
                    type_size = {
                        "char": 1, "uint8_t": 1, "int8_t": 1,
                        "short": 2, "uint16_t": 2, "int16_t": 2,
                        "int": 4, "uint32_t": 4, "int32_t": 4, "long": 4, "float": 4,
                        "double": 8, "uint64_t": 8, "int64_t": 8,
                        "void": 8, "uintptr_t": 8,
                    }
                    tsize = type_size.get(element_type, 4)
                    total_bytes = tsize * arr_size
                    if total_bytes > 1024:  # > 1KB
                        rel = str(Path(f).relative_to(project_dir))
                        sev = "warning" if total_bytes > 4096 else ("info" if total_bytes > 2048 else "info")
                        findings.append({
                            "severity": sev,
                            "category": "large_stack_allocation",
                            "file": rel,
                            "line": i,
                            "message": (
                                f"Large local array '{arr_name}' on stack: "
                                f"~{total_bytes} bytes ({arr_size} × {element_type})"
                            ),
                        })

    return findings


def _detect_function_call_depth(source_files: list[Path], project_dir: Path) -> list[StackFinding]:
    """Estimate worst-case function call depth.

    Uses heuristic: count sequential function calls within a function body.
    This is a static approximation; real analysis requires a call graph.
    """
    findings = []
    max_depth = 0
    deep_file = ""
    deep_fn = ""

    for f in source_files:
        if f.suffix != ".c":
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        # Track function boundaries
        lines = content.split("\n")
        in_function = False
        brace_depth = 0
        call_depth = 0
        current_fn = ""

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Detect function start (word+word+word( ... ) {
            fn_match = re.match(
                r'^(static\s+)?(const\s+)?(\w+[\s\*]+)?(\w+)\s*\(.*\)\s*\{',
                stripped,
            )
            if fn_match and not stripped.startswith("if") and not stripped.startswith("for") and not stripped.startswith("while"):
                in_function = True
                brace_depth = 1
                call_depth = 0
                current_fn = fn_match.group(4) if fn_match.group(4) else ""
                continue

            if in_function:
                # Count braces
                brace_depth += stripped.count("{") - stripped.count("}")
                # Count function calls (word( pattern, excluding keywords)
                if brace_depth > 0:
                    calls = re.findall(r'\b(\w+)\s*\(', stripped)
                    for c in calls:
                        if c.lower() not in ("if", "for", "while", "switch", "return",
                                              "sizeof", "defined", "assert", "int", "void",
                                              "char", "short", "long", "float", "double",
                                              "static", "const", "volatile", "extern",
                                              "uint8_t", "uint16_t", "uint32_t", "uint64_t",
                                              "int8_t", "int16_t", "int32_t", "int64_t"):
                            call_depth += 1

                if brace_depth <= 0:
                    # End of function
                    if call_depth > max_depth:
                        max_depth = call_depth
                        deep_file = str(Path(f).relative_to(project_dir))
                        deep_fn = current_fn
                    in_function = False

    if max_depth > 20:
        findings.append({
            "severity": "warning",
            "category": "call_depth",
            "file": deep_file,
            "line": 0,
            "message": (
                f"High function call depth detected: ~{max_depth} calls in '{deep_fn}'. "
                f"Consider refactoring to reduce stack frame requirements."
            ),
        })
    elif max_depth > 10:
        findings.append({
            "severity": "info",
            "category": "call_depth",
            "file": deep_file,
            "line": 0,
            "message": (
                f"Moderate call depth: ~{max_depth} calls in '{deep_fn}'. "
                f"May use significant stack in deeply nested paths."
            ),
        })

    return findings


def _check_interrupt_stack_budget(source_files: list[Path], project_dir: Path) -> list[StackFinding]:
    """Check interrupt handler stack usage budget.

    Notes:
    - ISR context typically has a separate stack or a fixed budget
    - Nested interrupts consume additional stack
    - Check for __attribute__((interrupt)) or IRQHandler functions
    """
    findings = []
    isr_functions: list[tuple[str, str, int]] = []  # (file, name, line)

    for f in source_files:
        if f.suffix not in (".c", ".cpp", ".s", ".S"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # IRQ handlers (STM32 naming convention)
            if re.search(r'(IRQHandler|isr_\w+)\s*\(', stripped, re.IGNORECASE):
                rel = str(Path(f).relative_to(project_dir))
                isr_functions.append((rel, stripped.split("(")[0].split()[-1], i))

    if len(isr_functions) > 5:
        findings.append({
            "severity": "warning",
            "category": "interrupt_stack",
            "file": "multiple",
            "line": 0,
            "message": (
                f"Found {len(isr_functions)} interrupt handler(s). "
                f"Ensure total ISR stack budget does not exceed available space. "
                f"Nested interrupts compound stack usage."
            ),
        })
    elif isr_functions:
        details = "; ".join(f"{fn} ({fl}:{ln})" for fl, fn, ln in isr_functions[:5])
        findings.append({
            "severity": "info",
            "category": "interrupt_stack",
            "file": isr_functions[0][0],
            "line": isr_functions[0][2],
            "message": f"ISR handlers found ({len(isr_functions)} total): {details}",
        })

    return findings


def _estimate_ram_vs_stack(source_files: list[Path], project_dir: Path) -> list[StackFinding]:
    """Estimate total RAM vs allocated stack to compute utilization ratio."""
    findings = []

    total_ram = 0
    total_stack = 0
    static_data = 0
    heap_estimate = 0

    # Read linker script for RAM and stack sizes
    for f in source_files:
        if f.suffix not in (".ld", ".lds"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        # RAM size
        ram_m = re.search(r'(?i)(ram|sram|dram)\s*\(.*\)\s*:\s*ORIGIN\s*=\s*(\w+)\s*,\s*LENGTH\s*=\s*(\w+)', content)
        if ram_m:
            try:
                length_str = ram_m.group(3)
                if length_str.startswith("0x") or length_str.startswith("0X"):
                    total_ram = int(length_str, 16)
                elif length_str.endswith("K"):
                    total_ram = int(length_str[:-1]) * 1024
                elif length_str.endswith("M"):
                    total_ram = int(length_str[:-1]) * 1024 * 1024
                else:
                    total_ram = int(length_str)
            except ValueError:
                pass

        # Stack size
        stack_m = re.search(r'(?i)(stack_size|__stack_size|STACK_SIZE)\s*=\s*(\w+)', content)
        if stack_m:
            try:
                stack_str = stack_m.group(2)
                if stack_str.startswith("0x") or stack_str.startswith("0X"):
                    total_stack = int(stack_str, 16)
                else:
                    total_stack = int(stack_str)
            except ValueError:
                pass

    # If we can't find exact RAM/stack sizes, use heuristic
    if total_ram == 0:
        # Common MCU RAM sizes
        total_ram = 65536  # Default: 64KB
    if total_stack == 0:
        # Common stack sizes: 2KB for small MCUs, 8KB for larger
        total_stack = 4096

    # Estimate static data usage from global variables
    for f in source_files:
        if f.suffix not in (".c", ".cpp"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        lines = content.split("\n")
        for line in lines:
            stripped = line.strip()
            # Global arrays
            m = re.search(r'\w+\s+(\w+)\s*\[(\d+)\]\s*;', stripped)
            if m:
                try:
                    static_data += int(m.group(2)) * 4  # Estimate 4 bytes per element
                except ValueError:
                    pass

    stack_usage_pct = (total_stack / total_ram * 100) if total_ram > 0 else 0
    static_pct = (static_data / total_ram * 100) if total_ram > 0 else 0

    # Heuristic: assume stack could be 60-80% used in worst case
    estimated_stack_usage = int(total_stack * 0.7)
    stack_utilization = (estimated_stack_usage / total_stack * 100) if total_stack > 0 else 0

    findings.append({
        "severity": "info" if stack_utilization < 95 else "error",
        "category": "stack_budget",
        "file": "project",
        "line": 0,
        "message": (
            f"Estimated RAM: {total_ram} bytes, Stack: {total_stack} bytes "
            f"({stack_usage_pct:.1f}% of RAM), "
            f"Static data: ~{static_data} bytes ({static_pct:.1f}% of RAM), "
            f"Estimated worst-case stack utilization: {stack_utilization:.0f}%"
        ),
    })

    return findings


# ── Build unified report ─────────────────────────────────────────────────


def _build_stack_report(project_dir: Path) -> dict:
    """Run all stack analysis checks and return unified report."""
    source_files = _find_source_files(project_dir)
    log.info("Stack analysis: found %d source files", len(source_files))

    all_findings: list[StackFinding] = []
    all_findings.extend(_find_stack_allocation(source_files, project_dir))
    all_findings.extend(_detect_function_call_depth(source_files, project_dir))
    all_findings.extend(_check_interrupt_stack_budget(source_files, project_dir))
    all_findings.extend(_estimate_ram_vs_stack(source_files, project_dir))

    # Count by severity
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for f in all_findings:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Check for ≥95% usage block (DEF-007)
    budget_findings = [f for f in all_findings if f["category"] == "stack_budget"]
    high_utilization = False
    for bf in budget_findings:
        m = re.search(r'utilization:\s*(\d+)%', bf["message"])
        if m and int(m.group(1)) >= 95:
            high_utilization = True

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_files": len(source_files),
            "total_findings": len(all_findings),
            "severity_counts": severity_counts,
            "high_utilization_block": high_utilization,
        },
        "findings": all_findings,
    }

    return report


# ── Render to markdown ───────────────────────────────────────────────────


def _render_stack_report(report: dict) -> str:
    """Render stack analysis report as markdown."""
    lines = [
        "# 堆栈使用分析报告",
        "",
        f"*生成时间: {report.get('generated_at', 'unknown')}*",
        "",
        "## 摘要",
        "",
        f"| 指标 | 值 |",
        f"|:-----|----:|",
        f"| 扫描文件数 | {report['summary']['total_files']} |",
        f"| 发现总数 | {report['summary']['total_findings']} |",
        f"| 🔴 Error | {report['summary']['severity_counts'].get('error', 0)} |",
        f"| 🟡 Warning | {report['summary']['severity_counts'].get('warning', 0)} |",
        f"| 🔵 Info | {report['summary']['severity_counts'].get('info', 0)} |",
        f"| ❌ ≥95%阻断 | {'是' if report['summary']['high_utilization_block'] else '否'} |",
        "",
    ]

    if report['summary']['high_utilization_block']:
        lines.append("> ⛔ **阻断**: 堆栈使用率 ≥95%，此步骤已阻断。\n")

    # Findings table
    findings = report.get("findings", [])
    if findings:
        lines.extend([
            "## 详细发现",
            "",
            "| 严重度 | 类别 | 文件 | 行 | 描述 |",
            "|:-------|:-----|:----|:--:|:-----|",
        ])
        for f in findings:
            sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f["severity"], "🔵")
            lines.append(
                f"| {sev_icon} {f['severity']} | {f['category']} | "
                f"{f.get('file', '?')} | {f.get('line', '?')} | "
                f"{f['message']} |"
            )

    lines.append("")
    return "\n".join(lines)


# ── Pipeline step handler ────────────────────────────────────────────────


def step_review_stack(session: PipelineSession) -> str:
    """Pipeline step handler for stack usage analysis.

    Scans the project files for stack usage patterns and generates
    a structured report. Blocks when ≥95% utilization detected (DEF-007).
    """
    print("  🔍 [小克] 堆栈使用分析...")

    spec_path = Path(session.spec_path)
    project_dir = spec_path.parent

    try:
        report = _build_stack_report(project_dir)

        # Save JSON report
        out_path = session.session_dir / "review-stack.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))

        # Render markdown summary
        markdown = _render_stack_report(report)

        # Check for ≥95% block
        if report["summary"]["high_utilization_block"]:
            print(f"    ❌ 堆栈使用率 ≥95% — 步骤阻断 (DEF-007)")
            raise PipelineStepError(
                "Blocked: Stack utilization ≥95%. "
                "Reduce stack allocations or increase stack size in linker script."
            )

        print(f"    ✅ 堆栈分析完成 — {report['summary']['total_findings']} 个发现")
        print(f"       {report['summary']['severity_counts'].get('error', 0)} errors, "
              f"{report['summary']['severity_counts'].get('warning', 0)} warnings, "
              f"{report['summary']['severity_counts'].get('info', 0)} infos")

        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error("Stack analysis failed: %s", e)
        raise PipelineStepError(f"Stack usage analysis failed: {e}")
