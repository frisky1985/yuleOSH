#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — MMIO 配置审查。

自动化审查嵌入式 MCU 的 MMIO 配置：
- 时钟系统 (HSE/LSE/PLL/RCC)
- GPIO 引脚配置
- NVIC 中断优先级
- DMA 配置一致性

参考: review_bsp.py (pin-mux / 时钟树检测模式)
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

log = logging.getLogger("pipeline.step_handlers.review_mmio")

__all__ = ["step_review_mmio"]

MmioFinding = dict


# ── Source file discovery ────────────────────────────────────────────────


def _find_mmio_sources(project_dir: Path) -> dict[str, list[Path]]:
    """Discover MMIO-related source files grouped by category."""
    categories: dict[str, list[Path]] = {
        "clock_config": [],
        "gpio_config": [],
        "nvic_config": [],
        "dma_config": [],
        "peripheral_config": [],
    }

    # Clock configuration
    for pat in ("**/*clock*.c", "**/*clock*.h", "**/*rcc*.c", "**/*rcc*.h",
                "**/system_stm32*.c", "**/system_stm32*.h"):
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["clock_config"].append(p)

    # GPIO configuration
    for pat in ("**/*gpio*.c", "**/*gpio*.h", "**/*pin_mux*.c", "**/*PinMux*.c"):
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["gpio_config"].append(p)

    # NVIC / interrupt configuration
    for pat in ("**/*nvic*.c", "**/*nvic*.h", "**/*irq*.c", "**/*irq*.h",
                "**/startup_*.s", "**/startup_*.S", "**/*interrupt*.c", "**/*interrupt*.h"):
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["nvic_config"].append(p)

    # DMA configuration
    for pat in ("**/*dma*.c", "**/*dma*.h", "**/*dmamux*.c", "**/*dmamux*.h"):
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["dma_config"].append(p)

    # Peripheral configuration files
    for pat in ("**/*uart*.c", "**/*usart*.c", "**/*spi*.c", "**/*i2c*.c",
                "**/*adc*.c", "**/*timer*.c"):
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["peripheral_config"].append(p)

    # Deduplicate
    for key in categories:
        seen = set()
        unique = []
        for p in categories[key]:
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                unique.append(p)
        categories[key] = unique

    return categories


# ── Clock configuration checks ───────────────────────────────────────────


def _check_clock_config(files: list[Path], project_dir: Path) -> list[MmioFinding]:
    """Review clock system configuration (HSE/LSE/PLL)."""
    findings: list[MmioFinding] = []

    has_hse = False
    has_lse = False
    has_pll = False
    has_rcc_init = False
    has_clock_security = False
    clock_issues: list[str] = []

    for f in files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel = str(Path(f).relative_to(project_dir))

        # Check for HSE configuration
        if re.search(r'HSE_VALUE|RCC_OSCILLATORTYPE_HSE|RCC_HSE', content):
            has_hse = True

        # Check for LSE configuration
        if re.search(r'LSE_VALUE|RCC_OSCILLATORTYPE_LSE|RCC_LSE', content):
            has_lse = True

        # Check for PLL configuration
        if re.search(r'RCC_PLL|PLLM|PLLN|PLLP|PLLQ|PLLR|HAL_RCCEx_PLL', content):
            has_pll = True

        # Check for RCC initialization
        if re.search(r'HAL_RCC_Init|HAL_RCC_ClockConfig|HAL_RCC_OscConfig', content):
            has_rcc_init = True

        # Check for clock security system
        if re.search(r'RCC_CSR|ClockSecuritySystem|CSS_ON|RCC_CR_CSSON', content):
            has_clock_security = True

        # Check PLL parameter plausibility
        pll_matches = re.findall(r'PLLM\s*[=:]\s*(\d+)', content)
        for pm in pll_matches:
            try:
                val = int(pm)
                if val < 1 or val > 63:
                    clock_issues.append(f"PLLM={val} out of typical range (1-63)")
            except ValueError:
                pass

        # Check system clock source
        if re.search(r'SYSCLK.*=.*\|', content) or re.search(r'RCC_CFGR_SW\s*=', content):
            if not re.search(r'RCC_CFGR_SW_PLL|RCC_SYSCLKSOURCE_PLLCLK', content):
                clock_issues.append("System clock not set to PLL (may limit performance)")

    if not has_hse:
        findings.append({
            "severity": "warning",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": "No HSE (High Speed External) oscillator configuration found — using HSI only may reduce accuracy",
        })
    if not has_lse:
        findings.append({
            "severity": "info",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": "No LSE (Low Speed External) oscillator — RTC accuracy may be reduced",
        })
    if not has_pll:
        findings.append({
            "severity": "warning",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": "No PLL configuration found — system may run at reduced clock speed",
        })
    if not has_rcc_init:
        findings.append({
            "severity": "warning",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": "No RCC initialization call found — clock tree may not be configured",
        })
    if not has_clock_security:
        findings.append({
            "severity": "info",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": "Clock Security System (CSS) not detected — consider enabling for safety-critical designs",
        })

    for issue in clock_issues:
        findings.append({
            "severity": "warning",
            "category": "clock",
            "file": "multiple",
            "line": 0,
            "message": issue,
        })

    return findings


# ── GPIO configuration checks ────────────────────────────────────────────


def _check_gpio_config(files: list[Path], project_dir: Path) -> list[MmioFinding]:
    """Review GPIO pin configuration."""
    findings: list[MmioFinding] = []

    gpio_init_count = 0
    has_output = False
    has_input = False
    has_af = False
    has_analog = False
    has_pull = False
    has_speed = False
    has_alternate_function = False

    for f in files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel = str(Path(f).relative_to(project_dir))

        # Count HAL_GPIO_Init calls
        gpio_init_calls = list(re.finditer(r'HAL_GPIO_Init\s*\(', content))
        gpio_init_count += len(gpio_init_calls)

        # Check GPIO modes
        if re.search(r'GPIO_MODE_OUTPUT', content):
            has_output = True
        if re.search(r'GPIO_MODE_INPUT', content):
            has_input = True
        if re.search(r'GPIO_MODE_AF', content):
            has_af = True
        if re.search(r'GPIO_MODE_ANALOG', content):
            has_analog = True

        # Check pull-up/down
        if re.search(r'GPIO_PULLUP|GPIO_PULLDOWN|GPIO_NOPULL', content):
            has_pull = True

        # Check speed settings
        if re.search(r'GPIO_SPEED_FREQ', content):
            has_speed = True

        # Check alternate function mapping
        if re.search(r'GPIO_AF\d+_\w+|HAL_GPIOEx_ConfigPin|GPIO_InitStruct\.Alternate', content):
            has_alternate_function = True

        # Check for uninitialized pins
        gpio_init_pins: set[str] = set()
        # Find all GPIOx patterns in HAL_GPIO_Init calls
        for m in gpio_init_calls:
            # Try to find the GPIO port within the surrounding context (~5 lines)
            ctx_start = max(0, m.start() - 200)
            ctx = content[ctx_start:m.end() + 100]
            port_m = re.search(r'GPIO([A-Z])\b', ctx[m.start() - ctx_start:])
            if port_m:
                gpio_init_pins.add(f"GPIO{port_m.group(1)}")

        if gpio_init_pins:
            findings.append({
                "severity": "info",
                "category": "gpio",
                "file": rel,
                "line": gpio_init_calls[0].start() if gpio_init_calls else 0,
                "message": f"GPIO initialized ports: {', '.join(sorted(gpio_init_pins))}",
            })

        # Check pin conflicts
        pin_assignments: dict[str, list[tuple[str, int]]] = {}  # pin -> [(file, line)]
        for m in re.finditer(r'HAL_GPIO_WritePin\s*\(\s*(\w+)\s*,\s*(\w+_Pin)\s*', content):
            port = m.group(1)
            pin = m.group(2)
            key = f"{port}_{pin}"
            if key not in pin_assignments:
                pin_assignments[key] = []
            pin_assignments[key].append((rel, content[:m.start()].count("\n") + 1))

        if len(pin_assignments) > 0:
            findings.append({
                "severity": "info",
                "category": "gpio",
                "file": rel,
                "line": 0,
                "message": f"GPIO pin writes detected: {len(pin_assignments)} pin(s) configured",
            })

    if gpio_init_count == 0:
        findings.append({
            "severity": "info",
            "category": "gpio",
            "file": "multiple",
            "line": 0,
            "message": "No HAL_GPIO_Init calls found — GPIO may be configured via CubeMX defaults",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "gpio",
            "file": "multiple",
            "line": 0,
            "message": f"Total HAL_GPIO_Init calls: {gpio_init_count}",
        })

    if not has_pull:
        findings.append({
            "severity": "info",
            "category": "gpio",
            "file": "multiple",
            "line": 0,
            "message": "No GPIO pull-up/down configuration detected — pins may float",
        })

    return findings


# ── NVIC configuration checks ────────────────────────────────────────────


def _check_nvic_config(files: list[Path], project_dir: Path) -> list[MmioFinding]:
    """Review NVIC (Nested Vectored Interrupt Controller) configuration."""
    findings: list[MmioFinding] = []

    nvic_priority_count = 0
    has_grouping = False
    has_enabled_irq = False
    priorities: list[tuple[str, int, str]] = []  # (file, line, priority)
    irq_names: list[str] = []

    for f in files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel = str(Path(f).relative_to(project_dir))

        # Check NVIC priority grouping
        if re.search(r'HAL_NVIC_SetPriorityGrouping|NVIC_SetPriorityGrouping|NVIC_PRIORITYGROUP', content):
            has_grouping = True

        # Check NVIC enable
        if re.search(r'HAL_NVIC_EnableIRQ|NVIC_EnableIRQ', content):
            has_enabled_irq = True

        # Check priority settings
        priority_matches = list(re.finditer(
            r'HAL_NVIC_SetPriority\s*\((\w+),\s*(\d+),\s*(\d+)',
            content,
        ))
        for m in priority_matches:
            irq = m.group(1)
            preempt = int(m.group(2))
            sub = int(m.group(3))
            nvic_priority_count += 1
            priorities.append((rel, content[:m.start()].count("\n") + 1, f"{preempt}/{sub}"))
            irq_names.append(irq)

        # List ISR handlers from startup file
        if f.suffix in (".s", ".S"):
            for m in re.finditer(r'\.word\s+(\w+Handler)', content, re.IGNORECASE):
                handler = m.group(1)
                irq_names.append(handler)

    if not has_grouping:
        findings.append({
            "severity": "warning",
            "category": "nvic",
            "file": "multiple",
            "line": 0,
            "message": "NVIC priority grouping not configured — interrupt priorities may be undefined",
        })

    if not has_enabled_irq:
        findings.append({
            "severity": "info",
            "category": "nvic",
            "file": "multiple",
            "line": 0,
            "message": "No NVIC IRQ enables detected — interrupts may not be activated",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "nvic",
            "file": "multiple",
            "line": 0,
            "message": f"NVIC priority settings found: {nvic_priority_count} interrupt(s)",
        })

    # Check priority values for sanity
    for file, line, prio in priorities:
        parts = prio.split("/")
        try:
            preempt = int(parts[0])
            sub = int(parts[1])
            if preempt > 15:
                findings.append({
                    "severity": "warning",
                    "category": "nvic",
                    "file": file,
                    "line": line,
                    "message": f"Suspicious NVIC preempt priority: {preempt} (typical range 0-15)",
                })
            if sub > 15:
                findings.append({
                    "severity": "warning",
                    "category": "nvic",
                    "file": file,
                    "line": line,
                    "message": f"Suspicious NVIC sub priority: {sub} (typical range 0-15)",
                })
        except ValueError:
            pass

    # Unique IRQ handlers
    unique_irqs = set(irq_names)
    if unique_irqs:
        findings.append({
            "severity": "info",
            "category": "nvic",
            "file": "multiple",
            "line": 0,
            "message": f"Unique interrupt handlers: {len(unique_irqs)} ({', '.join(sorted(unique_irqs)[:10])})",
        })

    return findings


# ── DMA configuration checks ─────────────────────────────────────────────


def _check_dma_config(files: list[Path], project_dir: Path) -> list[MmioFinding]:
    """Review DMA configuration."""
    findings: list[MmioFinding] = []

    dma_init_count = 0
    has_dma = False
    has_stream = False
    has_circular = False
    has_m2m = False
    has_m2p = False
    has_p2m = False
    has_priority = False
    has_irq = False
    dma_channels: set[str] = set()

    for f in files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel = str(Path(f).relative_to(project_dir))

        # Check DMA initialization
        if re.search(r'HAL_DMA_Init|HAL_DMAEx_Init|HAL_DMA_Start|HAL_DMA_Start_IT', content):
            has_dma = True
            dma_init_matches = list(re.finditer(r'HAL_DMA_Init\s*\((&?\w+|hdma\d+)', content))
            dma_init_count += len(dma_init_matches)

        # Check stream/channel configuration
        if re.search(r'DMA_Stream|DMA_Channel|hdam|hdma\b', content):
            has_stream = True

        # Check DMA mode
        if re.search(r'DMA_CIRCULAR|DMA_NORMAL', content):
            has_circular = True
        if re.search(r'DMA_MEMORY_TO_MEMORY|DMA_M2M', content):
            has_m2m = True
        if re.search(r'DMA_MEMORY_TO_PERIPH|DMA_M2P', content):
            has_m2p = True
        if re.search(r'DMA_PERIPH_TO_MEMORY|DMA_P2M', content):
            has_p2m = True

        # Check DMA priority
        if re.search(r'DMA_PRIORITY', content):
            has_priority = True

        # Check DMA interrupt
        if re.search(r'DMA_IT_TC|DMA_IT_TE|DMA_IT_HT|__HAL_DMA_ENABLE_IT', content):
            has_irq = True

        # Track channels
        channel_matches = re.findall(r'DMA_CHANNEL_(\d+)', content)
        for ch in channel_matches:
            dma_channels.add(ch)

    if not has_dma:
        findings.append({
            "severity": "info",
            "category": "dma",
            "file": "multiple",
            "line": 0,
            "message": "No DMA configuration detected — all data transfers use CPU polling",
        })
    else:
        details = []
        if dma_init_count > 0:
            details.append(f"{dma_init_count} DMA init(s)")
        if dma_channels:
            details.append(f"channels: {', '.join(sorted(dma_channels))}")
        if has_circular:
            details.append("circular mode")
        if has_irq:
            details.append("interrupt-driven")
        details_str = ", ".join(details)
        findings.append({
            "severity": "info" if has_dma else "warning",
            "category": "dma",
            "file": "multiple",
            "line": 0,
            "message": f"DMA configured: {details_str}" if details_str else "DMA detected",
        })

    if not has_priority:
        findings.append({
            "severity": "info",
            "category": "dma",
            "file": "multiple",
            "line": 0,
            "message": "No DMA priority configuration — defaults may cause arbitration issues",
        })

    return findings


# ── Cross-configuration consistency checks ───────────────────────────────


def _check_mmio_consistency(
    categories: dict[str, list[Path]],
    project_dir: Path,
) -> list[MmioFinding]:
    """Cross-check MMIO configuration across subsystems for consistency."""
    findings: list[MmioFinding] = []

    # Check if peripherals exist but DMA is not configured for them
    has_dma = bool(categories["dma_config"])
    peripheral_requires_dma = ["adc", "spi", "usart", "i2c"]

    if has_dma:
        dma_files_content = ""
        for f in categories["dma_config"]:
            try:
                dma_files_content += f.read_text(errors="replace")
            except OSError:
                continue

        for f in categories["peripheral_config"]:
            rel = str(Path(f).relative_to(project_dir))
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue

            # Check if this peripheral has DMA enabled
            for ptype in peripheral_requires_dma:
                if ptype in f.name.lower():
                    if not re.search(r'DMA', content):
                        findings.append({
                            "severity": "info",
                            "category": "consistency",
                            "file": rel,
                            "line": 0,
                            "message": f"DMA not configured for {f.stem} — consider DMA for high-throughput {ptype.upper()} traffic",
                        })

    # Check if clock is configured for all peripherals
    clock_files_content = ""
    for f in categories["clock_config"]:
        try:
            clock_files_content += f.read_text(errors="replace")
        except OSError:
            continue

    # Check for HAL_PPP_MspInit patterns (peripheral-specific HAL init)
    for cat_name, cat_files in categories.items():
        if cat_name in ("clock_config",):
            continue
        for f in cat_files:
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue
            # Check if HAL_XXX_MspInit is present
            msp_inits = re.findall(r'HAL_(\w+)_MspInit', content)
            for mi in msp_inits:
                findings.append({
                    "severity": "info",
                    "category": "consistency",
                    "file": str(Path(f).relative_to(project_dir)),
                    "line": 0,
                    "message": f"HAL_{mi}_MspInit found — MSP init for {mi} configured",
                })

    return findings


# ── Build unified report ─────────────────────────────────────────────────


def _build_mmio_report(project_dir: Path) -> dict:
    """Run all MMIO checks and return unified report."""
    categories = _find_mmio_sources(project_dir)
    log.info("MMIO review: found categories %s", {k: len(v) for k, v in categories.items()})

    all_findings: list[MmioFinding] = []

    # Clock checks
    all_findings.extend(_check_clock_config(categories["clock_config"], project_dir))

    # GPIO checks
    all_findings.extend(_check_gpio_config(categories["gpio_config"], project_dir))

    # NVIC checks
    all_findings.extend(_check_nvic_config(categories["nvic_config"], project_dir))

    # DMA checks
    all_findings.extend(_check_dma_config(categories["dma_config"], project_dir))

    # Consistency cross-checks
    all_findings.extend(_check_mmio_consistency(categories, project_dir))

    # Count by severity
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for f in all_findings:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "categories": {k: len(v) for k, v in categories.items()},
            "total_findings": len(all_findings),
            "severity_counts": severity_counts,
        },
        "findings": all_findings,
    }

    return report


# ── Render to markdown ───────────────────────────────────────────────────


def _render_mmio_report(report: dict) -> str:
    """Render MMIO review report as markdown."""
    lines = [
        "# MMIO 配置审查报告",
        "",
        f"*生成时间: {report.get('generated_at', 'unknown')}*",
        "",
        "## 摘要",
        "",
        "| 类别 | 文件数 |",
        "|:-----|-------:|",
    ]

    for cat_name, count in report["summary"]["categories"].items():
        cat_label = {
            "clock_config": "时钟系统",
            "gpio_config": "GPIO 配置",
            "nvic_config": "NVIC 中断",
            "dma_config": "DMA 配置",
            "peripheral_config": "外设配置",
        }.get(cat_name, cat_name)
        lines.append(f"| {cat_label} | {count} |")

    lines.extend([
        "",
        "| 指标 | 值 |",
        "|:-----|----:|",
        f"| 发现总数 | {report['summary']['total_findings']} |",
        f"| 🔴 Error | {report['summary']['severity_counts'].get('error', 0)} |",
        f"| 🟡 Warning | {report['summary']['severity_counts'].get('warning', 0)} |",
        f"| 🔵 Info | {report['summary']['severity_counts'].get('info', 0)} |",
        "",
    ])

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


def step_review_mmio(session: PipelineSession) -> str:
    """Pipeline step handler for MMIO configuration review.

    Scans the project for MMIO configuration files and generates
    a structured review of clock, GPIO, NVIC, and DMA setups.
    """
    print("  🔍 [小克] MMIO 配置审查...")

    spec_path = Path(session.spec_path)
    project_dir = spec_path.parent

    try:
        report = _build_mmio_report(project_dir)

        # Save JSON report
        out_path = session.session_dir / "review-mmio.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))

        # Render markdown summary
        markdown = _render_mmio_report(report)

        print(f"    ✅ MMIO 审查完成 — {report['summary']['total_findings']} 个发现")
        severity = report["summary"]["severity_counts"]
        print(f"       {severity.get('error', 0)} errors, "
              f"{severity.get('warning', 0)} warnings, "
              f"{severity.get('info', 0)} infos")

        return str(out_path)

    except Exception as e:
        log.error("MMIO review failed: %s", e)
        raise PipelineStepError(f"MMIO configuration review failed: {e}")
