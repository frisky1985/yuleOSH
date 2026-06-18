#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 启动代码审查。

检查嵌入式启动代码（startup_*.s / Reset_Handler / system_*.c）：
- Reset_Handler 入口是否存在
- 栈指针初始化（__initial_sp）
- .bss 清零、.data 初始化
- 系统时钟配置
- main() 调用前的处理器状态
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_startup")

__all__ = ["step_review_startup"]

StartupFinding = dict


# ── Static checks ─────────────────────────────────────────────────────────


def _find_startup_files(project_dir: Path) -> list[Path]:
    """Discover startup assembly / C files in the project tree."""
    patterns = [
        "**/startup_*.s", "**/startup_*.S",
        "**/startup_*.c",
        "**/system_*.c", "**/system_*.s", "**/system_*.S",
        "**/*_startup*",
        "**/crt0*", "**/crti*",
    ]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file():
                found.append(p)
    # Deduplicate
    seen = set()
    unique = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def _check_reset_handler(content: str, path: Path) -> list[StartupFinding]:
    """Check for Reset_Handler definition."""
    findings = []
    patterns = [
        r"Reset_Handler\s*(?:PROC|:)",     # ARM assembly
        r"Reset_Handler\s*:",
        r"void\s+Reset_Handler\s*\(",        # C definition
        r"\.word\s+Reset_Handler",           # Vector table entry
        r"Reset_Handler\s*=",                # Assignment
    ]
    if any(re.search(p, content) for p in patterns):
        findings.append({
            "severity": "info",
            "category": "reset_handler",
            "file": str(path),
            "message": "Reset_Handler found",
        })
    else:
        findings.append({
            "severity": "critical",
            "category": "reset_handler",
            "file": str(path),
            "message": "Reset_Handler not found in startup code — system will not boot",
        })
    return findings


def _check_stack_pointer_init(content: str, path: Path) -> list[StartupFinding]:
    """Check for initial stack pointer setup."""
    findings = []
    # __initial_sp or stack top reference
    sp_patterns = [
        r"__initial_sp",
        r"__stack_top",
        r"__StackTop",
        r"StackTop",
        r"__SP_INIT",
        r"ldr\s+(?:sp|r13)\s*[,=]",          # LDR SP, =...
        r"msr\s+msp\s*,",                    # MSR MSP, ...
        r"MOV\s+SP\s*,",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in sp_patterns):
        findings.append({
            "severity": "info",
            "category": "stack_init",
            "file": str(path),
            "message": "Stack pointer initialization found",
        })
    else:
        findings.append({
            "severity": "major",
            "category": "stack_init",
            "file": str(path),
            "message": "No explicit stack pointer (__initial_sp) initialization found — "
                       "may rely on hardware reset default",
        })
    return findings


def _check_bss_zeroing(content: str, path: Path) -> list[StartupFinding]:
    """Check for BSS zero-initialization loop."""
    findings = []
    bss_patterns = [
        r"__bss_start\s*",
        r"__bss_end\s*",
        r"__BSS_START",
        r"__BSS_END",
        r"bss\s+clear",
        r"bss\s+zero",
        r"zerobss",
        r"memset\s*\(.*bss",
        r"sbss\b",                           # Some toolchains (e.g. GCC ARM)
        r"ebss\b",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in bss_patterns):
        findings.append({
            "severity": "info",
            "category": "bss_init",
            "file": str(path),
            "message": "BSS zero-initialization logic found",
        })
    else:
        findings.append({
            "severity": "major",
            "category": "bss_init",
            "file": str(path),
            "message": "No BSS zero-initialization loop detected — uninitialized globals will have undefined values",
        })
    return findings


def _check_data_copy(content: str, path: Path) -> list[StartupFinding]:
    """Check for .data section copy from ROM to RAM."""
    findings = []
    data_patterns = [
        r"__data_start\s*",
        r"__data_end\s*",
        r"__data_load\s*",
        r"__DATA_START",
        r"__DATA_END",
        r"__etext\s*",                       # Load address in LMA region
        r"data\s+copy",
        r"initdata",
        r"memcpy\s*\(.*\bdata\b",
        r"sdata\b",
        r"edata\b",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in data_patterns):
        findings.append({
            "severity": "info",
            "category": "data_init",
            "file": str(path),
            "message": ".data copy from ROM to RAM logic found",
        })
    else:
        findings.append({
            "severity": "major",
            "category": "data_init",
            "file": str(path),
            "message": "No .data copy loop from ROM to RAM detected — initialized variables will be incorrect",
        })
    return findings


def _check_clock_config(content: str, path: Path) -> list[StartupFinding]:
    """Check for system clock / PLL configuration."""
    findings = []
    clock_patterns = [
        r"SystemCoreClock",
        r"SystemInit",
        r"clock_init",
        r"SystemClock_Config",
        r"HAL_Init\s*\(",
        r"RCC_",                              # Reset and Clock Control
        r"PLL",
        r"HSE", r"HSI",
        r"LSE", r"LSI",
        r"MSI",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in clock_patterns):
        findings.append({
            "severity": "info",
            "category": "clock_config",
            "file": str(path),
            "message": "System clock / PLL configuration detected",
        })
    else:
        # It's OK if clock config is in a separate file
        findings.append({
            "severity": "info",
            "category": "clock_config",
            "file": str(path),
            "message": "No clock config in this startup file — may be in a separate system_*.c file",
        })
    return findings


def _check_main_call(content: str, path: Path) -> list[StartupFinding]:
    """Check that main() is eventually called."""
    findings = []
    main_patterns = [
        r"\bbl\s+main\b",                    # ARM BL main
        r"\bBL\s+main\b",
        r"\bb\s+main\b",                     # B main (tail call)
        r"\bcall\s+main\b",
        r"\bmain\s*\(",
        r"__libc_init_array",                # May precede main()
    ]
    if any(re.search(p, content) for p in main_patterns):
        findings.append({
            "severity": "info",
            "category": "main_call",
            "file": str(path),
            "message": "main() call found in startup sequence",
        })
    else:
        findings.append({
            "severity": "minor",
            "category": "main_call",
            "file": str(path),
            "message": "No direct main() call in this file — "
                       "may be invoked via CRT or bootloader chain",
        })
    return findings


def _check_interrupt_state(content: str, path: Path) -> list[StartupFinding]:
    """Check if interrupts are properly managed before main()."""
    findings = []
    # CPSID (disable interrupts) and CPSIE (enable)
    disable_patterns = [
        r"cpsid\s+i",                        # ARM CPSID I
        r"CPSID\s+I",
    ]
    enable_patterns = [
        r"cpsie\s+i",
        r"CPSIE\s+I",
    ]

    has_disable = any(re.search(p, content) for p in disable_patterns)
    has_enable = any(re.search(p, content) for p in enable_patterns)

    if has_disable:
        findings.append({
            "severity": "info",
            "category": "interrupt_state",
            "file": str(path),
            "message": "Interrupts disabled at startup (CPSID I) — best practice",
        })
    elif has_enable:
        findings.append({
            "severity": "info",
            "category": "interrupt_state",
            "file": str(path),
            "message": "Interrupts enabled early in startup — verify this is intentional",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "interrupt_state",
            "file": str(path),
            "message": "No explicit interrupt disable/enable in startup — "
                       "interrupts default to disabled after reset",
        })
    return findings


def _static_startup_review(project_dir: Path) -> list[StartupFinding]:
    """Run all static checks on discovered startup files."""
    all_findings: list[StartupFinding] = []
    files = _find_startup_files(project_dir)

    if not files:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No startup file (startup_*.s / system_*.c / crt0*) found in project tree",
        })
        return all_findings

    for f in files:
        log.info(f"  Checking startup file: {f}")
        try:
            content = f.read_text()
        except OSError as e:
            all_findings.append({
                "severity": "major",
                "category": "io",
                "file": str(f),
                "message": f"Cannot read startup file: {e}",
            })
            continue

        all_findings.extend(_check_reset_handler(content, f))
        all_findings.extend(_check_stack_pointer_init(content, f))
        all_findings.extend(_check_bss_zeroing(content, f))
        all_findings.extend(_check_data_copy(content, f))
        all_findings.extend(_check_clock_config(content, f))
        all_findings.extend(_check_main_call(content, f))
        all_findings.extend(_check_interrupt_state(content, f))

    return all_findings


def _build_startup_review_prompt(
    startup_contents: dict[str, str],
) -> tuple[str, str]:
    """Build prompts for LLM-powered startup code review."""
    system_prompt = (
        "You are an embedded firmware expert reviewing startup code.\n"
        "Analyze the provided startup / system files for:\n"
        "1. Reset_Handler correctness — does it initialize the processor properly?\n"
        "2. Stack pointer — is __initial_sp set from the linker script?\n"
        "3. BSS and DATA initialization — are all global variables correctly initialized?\n"
        "4. Clock configuration — is the system clock set up for the target frequency?\n"
        "5. Does the startup sequence correctly call main()?\n"
        "6. Are interrupts managed safely before the scheduler starts?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## Startup / System Files\n"]
    for path, content in startup_contents.items():
        user_lines.append(f"### {path}\n```\n{content[:6000]}\n```\n")
    user_lines.append(
        "Review the startup code above. "
        "Check for any issues that would prevent proper boot "
        "or C runtime initialization on an MCU target."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_startup(session: PipelineSession) -> str:
    """Step: 小克 — 启动代码审查。

    Discovers and reviews startup / system initialization code.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  ⚡ [小克] 启动代码审查开始...")
        log.info("Running startup code review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static startup checks...")
        static_findings = _static_startup_review(project_dir)
        log.info(f"Static startup review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered startup review...")
        llm_review = ""
        startup_files = _find_startup_files(project_dir)
        if startup_files:
            startup_contents = {}
            for p in startup_files:
                try:
                    startup_contents[str(p)] = p.read_text()
                except OSError:
                    pass
            if startup_contents:
                try:
                    system_prompt, user_prompt = _build_startup_review_prompt(startup_contents)
                    llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                    llm_review = llm_result["content"]
                    usage = llm_result.get("usage", {})
                    session.token_usage_total += usage.get("total_tokens", 0)
                    session.token_usage_steps.append({"step": "review-startup", "usage": usage})
                    log.info(f"LLM startup review: {usage.get('total_tokens', '?')} tokens")
                except Exception as e:
                    log.warning(f"LLM startup review failed (non-fatal): {e}")
                    llm_review = "(LLM-powered review unavailable)"

        # ── Build output report ──
        finding_breakdown = {
            "critical": sum(1 for f in static_findings if f["severity"] == "critical"),
            "major": sum(1 for f in static_findings if f["severity"] == "major"),
            "minor": sum(1 for f in static_findings if f["severity"] == "minor"),
            "info": sum(1 for f in static_findings if f["severity"] == "info"),
        }

        overall_status = "passed"
        if any(f["severity"] == "critical" for f in static_findings):
            overall_status = "failed"
        elif finding_breakdown["major"] > 3:
            overall_status = "retry"

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-startup",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "startup_files_found": [str(p) for p in startup_files],
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "startup-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write startup review: {e}")
            raise PipelineStepError(f"Cannot write startup review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 启动代码审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Startup review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Startup review step failed: {e}")
        raise PipelineStepError(f"Startup review step failed: {e}")
