#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — BSP 板级支持包验证。

检查项:
- board.h / target.h 定义（GPIO/UART/I2C/SPI 引脚映射）
- 时钟树正确性（HSE/LSE/PLL 参数）
- 外设驱动（DMA/ADC/TIMER 初始化顺序）
- HAL 接口一致性
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_bsp")

__all__ = ["step_review_bsp"]

BspFinding = dict


# ── Discovery ─────────────────────────────────────────────────────────────


def _find_bsp_files(project_dir: Path) -> dict[str, list[Path]]:
    """Discover BSP-related files grouped by category."""
    categories = {
        "board_headers": [],
        "hal_config": [],
        "pin_mux": [],
        "clock_config": [],
        "peripheral_config": [],
        "dma_config": [],
    }

    # Board header files
    for p in project_dir.glob("**/board*.h"):
        if p.is_file():
            categories["board_headers"].append(p)
    for p in project_dir.glob("**/target*.h"):
        if p.is_file():
            categories["board_headers"].append(p)
    for p in project_dir.glob("**/BSP/**/*.h"):
        if p.is_file():
            categories["board_headers"].append(p)

    # HAL configuration
    for p in project_dir.glob("**/hal_conf*.h"):
        if p.is_file():
            categories["hal_config"].append(p)
    for p in project_dir.glob("**/stm32*_hal_conf*.h"):
        if p.is_file():
            categories["hal_config"].append(p)

    # Pin mux (CubeMX generated)
    for p in project_dir.glob("**/*pin_mux*.c"):
        if p.is_file():
            categories["pin_mux"].append(p)
    for p in project_dir.glob("**/*PinMux*.c"):
        if p.is_file():
            categories["pin_mux"].append(p)
    for p in project_dir.glob("**/*gpio*.c"):
        if p.is_file():
            categories["pin_mux"].append(p)

    # Clock configuration
    for p in project_dir.glob("**/*clock*.c"):
        if p.is_file():
            categories["clock_config"].append(p)
    for p in project_dir.glob("**/system_stm32*.c"):
        if p.is_file():
            categories["clock_config"].append(p)
    for p in project_dir.glob("**/*rcc*.c"):
        if p.is_file():
            categories["clock_config"].append(p)

    # Peripheral configuration files
    for p in project_dir.glob("**/*uart*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)
    for p in project_dir.glob("**/*usart*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)
    for p in project_dir.glob("**/*spi*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)
    for p in project_dir.glob("**/*i2c*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)
    for p in project_dir.glob("**/*adc*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)
    for p in project_dir.glob("**/*timer*.c"):
        if p.is_file():
            categories["peripheral_config"].append(p)

    # DMA configuration
    for p in project_dir.glob("**/*dma*.c"):
        if p.is_file():
            categories["dma_config"].append(p)
    for p in project_dir.glob("**/*dma*.h"):
        if p.is_file():
            categories["dma_config"].append(p)

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


# ── Static checks: Pin Mux ────────────────────────────────────────────────


def _check_pin_mux_gpio(content: str, path: Path) -> list[BspFinding]:
    """Check GPIO pin configuration for correctness."""
    findings = []

    # Check for HAL_GPIO_Init calls
    gpio_init_calls = list(re.finditer(
        r'HAL_GPIO_Init\s*\(', content))
    if not gpio_init_calls:
        findings.append({
            "severity": "info",
            "category": "pin_mux",
            "file": str(path),
            "message": "No HAL_GPIO_Init calls found — GPIO may be configured elsewhere or via CubeMX",
        })
        return findings

    # Check for GPIO mode settings
    gpio_modes = list(re.finditer(
        r'GPIO_MODE_(INPUT|OUTPUT|AF|ANALOG|IT_[A-Z_]+)', content))
    if not gpio_modes:
        findings.append({
            "severity": "minor",
            "category": "pin_mux",
            "file": str(path),
            "message": f"HAL_GPIO_Init calls ({len(gpio_init_calls)}) found but no GPIO mode specifiers "
                       f"detected — verify initialization structure is complete",
        })
    else:
        modes_found = set(m.group(1) for m in gpio_modes)
        findings.append({
            "severity": "info",
            "category": "pin_mux",
            "file": str(path),
            "message": f"GPIO modes configured: {', '.join(sorted(modes_found))} "
                       f"({len(gpio_init_calls)} init calls)",
        })

    # Check for GPIO pull-up/pull-down config
    pull_configs = list(re.finditer(
        r'GPIO_NOPULL|GPIO_PULLUP|GPIO_PULLDOWN', content))
    if pull_configs:
        pulls_found = set(m.group(0) for m in pull_configs)
        findings.append({
            "severity": "info",
            "category": "pin_mux",
            "file": str(path),
            "message": f"GPIO pull configurations: {', '.join(sorted(pulls_found))}",
        })

    # Check for conflicting alternate function assignments
    af_pattern = re.compile(r'GPIO_AF\d+')
    af_values = af_pattern.findall(content)
    if len(af_values) > 8:
        findings.append({
            "severity": "info",
            "category": "pin_mux",
            "file": str(path),
            "message": f"Multiple AF assignments ({len(af_values)}) — verify no pin conflicts",
        })

    # Check for output speed configuration
    speed_configs = list(re.finditer(
        r'GPIO_SPEED_FREQ_(LOW|MEDIUM|HIGH|VERY_HIGH)', content))
    if not speed_configs:
        findings.append({
            "severity": "minor",
            "category": "pin_mux",
            "file": str(path),
            "message": "No GPIO output speed configuration found — may default to slow speed",
        })

    return findings


def _check_pin_mux_conflicts(content: str, path: Path) -> list[BspFinding]:
    """Check for potential pin mux conflicts by analyzing GPIO_PIN_x constants."""
    findings = []

    # Extract GPIO port assignments: GPIOA, GPIOB, etc.
    port_assignments = list(re.finditer(r'GPIO([A-Z])\b', content))

    # Extract specific pin numbers
    pin_pattern = re.compile(r'GPIO_PIN_(\d+)')
    pins_by_port: dict[str, set[int]] = {}
    for port_m in port_assignments:
        port = port_m.group(1)
        if port not in pins_by_port:
            pins_by_port[port] = set()

    for pin_m in pin_pattern.finditer(content):
        pin_num = int(pin_m.group(1))
        # Near-miss: find the closest GPIOx reference within the context
        preceding = content[:pin_m.start()]
        last_port = None
        for port_m in re.finditer(r'GPIO([A-Z])\b', preceding):
            last_port = port_m.group(1)
        if last_port:
            if last_port not in pins_by_port:
                pins_by_port[last_port] = set()
            pins_by_port[last_port].add(pin_num)

    # Flag ports with many pins assigned (potential overuse)
    for port, pins in pins_by_port.items():
        if len(pins) > 12:
            findings.append({
                "severity": "minor",
                "category": "pin_mux",
                "file": str(path),
                "message": f"GPIO{port} has {len(pins)} pins assigned — verify power budget "
                           f"and available pin count for this package",
            })

    return findings


# ── Static checks: Clock tree ─────────────────────────────────────────────


def _check_clock_hse(content: str, path: Path) -> list[BspFinding]:
    """Check HSE/LSE configuration."""
    findings = []

    has_hse = bool(re.search(r'HSE', content, re.IGNORECASE))
    has_lse = bool(re.search(r'LSE', content, re.IGNORECASE))
    has_hsi = bool(re.search(r'HSI', content, re.IGNORECASE))
    has_lsi = bool(re.search(r'LSI', content, re.IGNORECASE))

    hse_value = None
    hse_pat = re.search(r'HSE_VALUE\s*[=:]\s*(\d+)', content)
    if hse_pat:
        hse_value = int(hse_pat.group(1))
    if hse_value is None:
        hse_pat2 = re.search(r'HSE\s*.*?(\d+)\s*MHz', content, re.IGNORECASE)
        if hse_pat2:
            hse_value = int(hse_pat2.group(1)) * 1000000

    if not has_hse and not has_hsi:
        findings.append({
            "severity": "major",
            "category": "clock_tree",
            "file": str(path),
            "message": "Neither HSE nor HSI configured — system clock source undefined",
        })
    elif has_hse:
        if hse_value:
            findings.append({
                "severity": "info",
                "category": "clock_tree",
                "file": str(path),
                "message": f"HSE configured: {hse_value} Hz ({(hse_value / 1000000):.1f} MHz)",
            })
            if hse_value < 1000000 or hse_value > 50000000:
                findings.append({
                    "severity": "minor",
                    "category": "clock_tree",
                    "file": str(path),
                    "message": f"HSE value ({hse_value} Hz) outside typical range (1–50 MHz) "
                               f"— verify crystal specification",
                })
        else:
            findings.append({
                "severity": "info",
                "category": "clock_tree",
                "file": str(path),
                "message": "HSE configured (value parser could not determine frequency)",
            })
    else:
        findings.append({
            "severity": "info",
            "category": "clock_tree",
            "file": str(path),
            "message": "HSE not configured — using HSI as system clock source",
        })

    return findings


def _check_clock_pll(content: str, path: Path) -> list[BspFinding]:
    """Check PLL configuration parameters."""
    findings = []

    # Detect PLL-related symbols
    has_pll = bool(re.search(r'PLL', content, re.IGNORECASE))
    if not has_pll:
        findings.append({
            "severity": "info",
            "category": "clock_tree",
            "file": str(path),
            "message": "No PLL configuration found — system may run on HSI/HSE directly",
        })
        return findings

    # Check for PLLM, PLLN, PLLP, PLLQ parameters (STM32 pattern)
    pll_params = {}
    param_pats = {
        "PLLM": r'PLL[Mm]\s*[=:]\s*(\d+)',
        "PLLN": r'PLL[Nn]\s*[=:]\s*(\d+)',
        "PLLP": r'PLL[Pp]\s*[=:]\s*(\d+)',
        "PLLQ": r'PLL[Qq]\s*[=:]\s*(\d+)',
        "PLLR": r'PLL[Rr]\s*[=:]\s*(\d+)',
    }
    for param, pat in param_pats.items():
        m = re.search(pat, content)
        if m:
            pll_params[param] = int(m.group(1))

    if not pll_params:
        findings.append({
            "severity": "major",
            "category": "clock_tree",
            "file": str(path),
            "message": "PLL symbols found but no PLLM/PLLN/PLLP/PLLQ/PLLR parameters detected — "
                       "PLL may not be fully configured",
        })
        return findings

    # Validate PLLN (multiplication factor)
    if "PLLN" in pll_params:
        plln = pll_params["PLLN"]
        if plln < 8 or plln > 432:
            findings.append({
                "severity": "major",
                "category": "clock_tree",
                "file": str(path),
                "message": f"PLLN={plln} outside recommended range (8–432) — "
                           f"may cause PLL instability or out-of-spec VCO frequency",
            })
        else:
            findings.append({
                "severity": "info",
                "category": "clock_tree",
                "file": str(path),
                "message": f"PLLN={plln} within range",
            })

    # Validate PLLM (division factor)
    if "PLLM" in pll_params:
        pllm = pll_params["PLLM"]
        if pllm < 2 or pllm > 63:
            findings.append({
                "severity": "major",
                "category": "clock_tree",
                "file": str(path),
                "message": f"PLLM={pllm} outside recommended range (2–63) — "
                           f"may cause out-of-spec VCO input frequency",
            })
        else:
            findings.append({
                "severity": "info",
                "category": "clock_tree",
                "file": str(path),
                "message": f"PLLM={pllm} within range",
            })

    # Report all found PLL params
    params_str = ", ".join(f"{k}={v}" for k, v in sorted(pll_params.items()))
    findings.append({
        "severity": "info",
        "category": "clock_tree",
        "file": str(path),
        "message": f"PLL parameters: {params_str}",
    })

    # Check for HSE as PLL source
    has_pll_source = bool(re.search(
        r'RCC_PLLSOURCE_HSE|PLL_SOURCE_HSE|PLLSRC_HSE', content))
    if not has_pll_source:
        findings.append({
            "severity": "minor",
            "category": "clock_tree",
            "file": str(path),
            "message": "PLL source selection not explicitly set — verify PLL source "
                       "(HSE recommended for accuracy vs HSI)",
        })

    return findings


def _check_system_clock_frequency(content: str, path: Path) -> list[BspFinding]:
    """Check SystemCoreClock or HCLK frequency setting."""
    findings = []

    # Check SystemCoreClock definition or update
    core_clock_pat = re.search(
        r'SystemCoreClock\s*=\s*(\d+)', content)
    if core_clock_pat:
        freq = int(core_clock_pat.group(1))
        if freq > 0:
            findings.append({
                "severity": "info",
                "category": "clock_tree",
                "file": str(path),
                "message": f"SystemCoreClock = {freq} Hz ({(freq/1000000):.1f} MHz)",
            })
            if freq < 1000000:
                findings.append({
                    "severity": "minor",
                    "category": "clock_tree",
                    "file": str(path),
                    "message": f"SystemCoreClock ({freq} Hz) is < 1 MHz — "
                               f"verify this is intentional (may indicate clock failure)",
                })
            elif freq > 480000000:
                findings.append({
                    "severity": "major",
                    "category": "clock_tree",
                    "file": str(path),
                    "message": f"SystemCoreClock ({freq} Hz) exceeds typical MCU range "
                               f"(480 MHz max) — verify against target datasheet",
                })
    else:
        findings.append({
            "severity": "info",
            "category": "clock_tree",
            "file": str(path),
            "message": "SystemCoreClock not explicitly set in this file — "
                       "may be handled by HAL or CubeMX generated code",
        })

    # Check for HAL_RCC_OscConfig and HAL_RCC_ClockConfig calls
    rcc_osc = bool(re.search(r'HAL_RCC_OscConfig', content))
    rcc_clock = bool(re.search(r'HAL_RCC_ClockConfig', content))

    if rcc_osc and rcc_clock:
        findings.append({
            "severity": "info",
            "category": "clock_tree",
            "file": str(path),
            "message": "HAL RCC oscillator and clock configuration found — clock tree fully configured via HAL",
        })
    elif rcc_osc:
        findings.append({
            "severity": "info",
            "category": "clock_tree",
            "file": str(path),
            "message": "HAL_RCC_OscConfig found — oscillator configured",
        })

    return findings


# ── Static checks: alloca / VLA / Dynamic allocation ────────────────────


def _check_alloca_usage(content: str, path: Path) -> list[BspFinding]:
    """Detect alloca() usage — stack-allocated memory at runtime.

    alloca() is dangerous in embedded / safety-critical contexts because:
    - It allocates on the stack, which is typically small (few KB)
    - There is no error return on stack overflow — causes silent corruption
    - It is banned by MISRA C:2023 Rule-21-5 (use of alloca)
    - It is banned by AUTOSAR C++14 A18-5-2
    """
    findings = []

    # Pattern 1: Direct alloca() call
    alloca_direct = list(re.finditer(r'alloca\s*\(', content))
    if alloca_direct:
        findings.append({
            "severity": "critical",
            "category": "runtime_allocation",
            "file": str(path),
            "message": f"alloca() used {len(alloca_direct)} time(s) — stack allocation without overflow "
                       f"protection. MISRA C:2023 Rule-21-5 violation. "
                       f"Replace with fixed-size arrays or pool allocation.",
        })

    # Pattern 2: strdupa / strndupa (GNU extensions using alloca internally)
    strdupa_usage = list(re.finditer(r'strdupa\s*\(|strndupa\s*\(', content))
    if strdupa_usage:
        findings.append({
            "severity": "critical",
            "category": "runtime_allocation",
            "file": str(path),
            "message": f"strdupa/strndupa used {len(strdupa_usage)} time(s) — these use alloca() "
                       f"internally, same stack overflow risk. Replace with strdup + heap.",
        })

    return findings


def _check_vla_usage(content: str, path: Path) -> list[BspFinding]:
    """Detect Variable-Length Arrays (VLA) in C code.

    VLAs are dangerous in embedded / BSP code because:
    - Their size is determined at runtime, not compile-time
    - Stack overflow cannot be statically verified
    - VLAs are conditionally supported in C11 and optional in C23
    - Banned by MISRA C:2012 Rule-18-7 / MISRA C:2023 Rule-18-7
    - In BSP context: interrupt handlers and RTOS tasks have very limited stacks
    """
    findings = []

    # Pattern: type array[size_expr]  where size_expr is NOT a constant
    # Match patterns like: int arr[n]; int buf[len+1]; uint8_t data[size];
    # These are hard to detect precisely with regex, but we can find suspicious patterns

    # Look for array declarations with non-constant size in function bodies
    # VLA pattern:  <type> <name>[<non-constant>]  inside a function body
    vla_hits = []

    # Pattern 1: type name[variable];  — variable as array dimension
    vla_pat = re.finditer(
        r'\b(?:int|long|short|char|uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|'
        r'float|double|size_t)\s+\w+\s*\[(?!\s*\d+\s*\])(?!\s*\w+\s*=\s*\d+\s*\])'
        r'[^;\]]*\]',
        content,
    )
    for m in vla_pat:
        decl = m.group(0)
        # Exclude known constant patterns
        if re.search(r'\[\s*\d+\s*\]', decl):
            continue  # definitely constant size
        # Exclude sizeof() expressions
        if 'sizeof' in decl:
            continue
        # Exclude macro constants (ALL_CAPS) as they are compile-time constants
        expr = decl[decl.rfind('[')+1:decl.rfind(']')]
        if expr.isupper():
            continue
        vla_hits.append(decl)
        if len(vla_hits) >= 10:
            break  # cap at 10 findings per file

    if vla_hits:
        findings.append({
            "severity": "major",
            "category": "runtime_allocation",
            "file": str(path),
            "message": f"Potential VLA usage detected ({len(vla_hits)} pattern(s)). "
                       f"Examples: {'; '.join(vla_hits[:5])}. "
                       f"VLAs are not MISRA-compliant and risk stack overflow in BSP code. "
                       f"Replace with fixed-size arrays or dynamic pool allocation.",
        })

    return findings


def _check_dynamic_allocation(content: str, path: Path) -> list[BspFinding]:
    """Detect dynamic memory allocation (malloc/calloc/realloc/free) in BSP code.

    Dynamic allocation is discouraged in safety-critical embedded BSP code because:
    - Heap fragmentation over time
    - Out-of-memory error handling required but frequently missing
    - MISRA C:2023 Dir 4.12 prohibits dynamic memory allocation in safety-critical code
    - BSP code often runs before heap initialization
    - Interrupt handlers should never use dynamic allocation
    """
    findings = []

    # Pattern 1: Direct malloc/calloc/realloc calls
    malloc_calls = len(list(re.finditer(r'\bmalloc\s*\(', content)))
    calloc_calls = len(list(re.finditer(r'\bcalloc\s*\(', content)))
    realloc_calls = len(list(re.finditer(r'\brealloc\s*\(', content)))
    free_calls = len(list(re.finditer(r'\bfree\s*\(', content)))

    total_alloc = malloc_calls + calloc_calls + realloc_calls

    if total_alloc > 0 or free_calls > 0:
        severity = "major" if total_alloc > 3 else "minor"
        details = []
        if malloc_calls:
            details.append(f"malloc({malloc_calls})")
        if calloc_calls:
            details.append(f"calloc({calloc_calls})")
        if realloc_calls:
            details.append(f"realloc({realloc_calls})")
        if free_calls:
            details.append(f"free({free_calls})")

        findings.append({
            "severity": severity,
            "category": "runtime_allocation",
            "file": str(path),
            "message": f"Dynamic memory allocation detected: {', '.join(details)}. "
                       f"MISRA C:2023 Dir 4.12 prohibits dynamic allocation in safety-critical "
                       f"code. In BSP context this may be acceptable for non-critical init code "
                       f"but should be reviewed for heap safety and out-of-memory handling.",
        })

        # Check for NULL-check after allocation
        if total_alloc > 0 and not bool(re.search(r'(if\s*\(\s*\w+\s*\)\s*\{|if\s*\(\s*\w+\s*!=\s*NULL\s*\))', content[-2000:])):
            findings.append({
                "severity": "major",
                "category": "runtime_allocation",
                "file": str(path),
                "message": f"Dynamic allocation ({total_alloc} call(s)) found without visible "
                           f"NULL-return check in recent code. Missing OOM handling is a "
                           f"safety risk — verify or add error handling.",
            })

    # Pattern 2: new/delete for C++ files
    new_calls = len(list(re.finditer(r'\bnew\s+(?!constexpr)', content)))
    delete_calls = len(list(re.finditer(r'\bdelete\[?\]?\s+', content)))

    if new_calls > 0:
        findings.append({
            "severity": "major" if new_calls > 3 else "minor",
            "category": "runtime_allocation",
            "file": str(path),
            "message": f"C++ 'new' operator used {new_calls} time(s) in BSP code — "
                       f"prefer placement new with fixed pools for embedded targets.",
        })

    return findings


def _check_runtime_allocation_integrity(files: dict[str, list[Path]]) -> list[BspFinding]:
    """Run all runtime allocation checks across all BSP files."""
    findings = []

    all_categories = ["board_headers", "hal_config", "pin_mux", "clock_config",
                      "peripheral_config", "dma_config"]

    total_alloca = 0
    total_vla = 0
    total_dynamic = 0
    files_with_issues = 0

    for cat in all_categories:
        for f in files.get(cat, []):
            try:
                content = f.read_text()
            except OSError:
                continue

            before = len(findings)
            findings.extend(_check_alloca_usage(content, f))
            findings.extend(_check_vla_usage(content, f))
            findings.extend(_check_dynamic_allocation(content, f))
            if len(findings) > before:
                files_with_issues += 1

    # Add a cross-file summary finding
    alloca_count = sum(1 for f in findings if "alloca()" in f.get("message", ""))
    vla_count = sum(1 for f in findings if "VLA" in f.get("message", "") or "Variable-Length" in f.get("message", ""))
    malloc_count = sum(1 for f in findings if "malloc" in f.get("message", "") or "calloc" in f.get("message", ""))

    if alloca_count > 0 or vla_count > 0 or malloc_count > 0:
        parts = []
        if alloca_count:
            parts.append(f"{alloca_count} alloca")
        if vla_count:
            parts.append(f"{vla_count} VLA")
        if malloc_count:
            parts.append(f"{malloc_count} dynamic-alloc")
        summary_msg = f"Runtime allocation issues across {files_with_issues} file(s): {', '.join(parts)}"
        findings.append({
            "severity": "info",
            "category": "runtime_allocation",
            "file": "(multiple)",
            "message": summary_msg,
        })

    return findings


# ── Static checks: Peripheral initialization ──────────────────────────────


def _check_peripheral_init_order(files: dict[str, list[Path]]) -> list[BspFinding]:
    """Check HAL initialization order across peripheral config files.

    The expected order per STM32 HAL documentation:
    1. HAL_Init()
    2. HAL_RCC_OscConfig / HAL_RCC_ClockConfig
    3. HAL_Delay / HAL_GetTick (timebase)
    4. GPIO / HAL_GPIO_Init
    5. DMA / HAL_DMA_Init
    6. NVIC / HAL_NVIC_SetPriority
    7. USART / HAL_UART_Init
    8. SPI / HAL_SPI_Init
    9. I2C / HAL_I2C_Init
    10. ADC / HAL_ADC_Init
    11. TIM / HAL_TIM_Base_Init
    """
    findings = []

    # Collect all init calls across all files with file mapping
    init_patterns = {
        "HAL_Init": r'HAL_Init\s*\(',
        "RCC_OscConfig": r'HAL_RCC_OscConfig\s*\(',
        "RCC_ClockConfig": r'HAL_RCC_ClockConfig\s*\(',
        "GPIO_Init": r'HAL_GPIO_Init\s*\(',
        "DMA_Init": r'HAL_DMA_Init\s*\(',
        "NVIC_SetPriority": r'HAL_NVIC_SetPriority\s*\(',
        "UART_Init": r'HAL_UART_Init\s*\(',
        "SPI_Init": r'HAL_SPI_Init\s*\(',
        "I2C_Init": r'HAL_I2C_Init\s*\(',
        "ADC_Init": r'HAL_ADC_Init\s*\(',
        "TIM_Base_Init": r'HAL_TIM_Base_Init\s*\(',
        "TIM_PWM_Init": r'HAL_TIM_PWM_Init\s*\(',
        "TIM_OC_Init": r'HAL_TIM_OC_Init\s*\(',
        "TIM_IC_Init": r'HAL_TIM_IC_Init\s*\(',
    }

    init_positions: dict[str, int] = {}  # func_name -> overall position guess

    # Scan all peripheral files for init calls
    all_categories = ["pin_mux", "clock_config", "peripheral_config", "dma_config",
                      "board_headers", "hal_config"]
    for cat in all_categories:
        for f in files.get(cat, []):
            try:
                content = f.read_text()
            except OSError:
                continue
            for func_name, pat in init_patterns.items():
                for m in re.finditer(pat, content):
                    if func_name not in init_positions:
                        init_positions[func_name] = m.start()

    # Build ordered list based on source position (approximation)
    ordered = sorted(init_positions.items(), key=lambda x: x[1])

    # Check ordering requirements (only if we have enough entries)
    priorities = [
        ("HAL_Init", ["HAL_Init"], 0),
        ("RCC", ["RCC_OscConfig", "RCC_ClockConfig"], 1),
        ("GPIO", ["GPIO_Init"], 2),
        ("DMA", ["DMA_Init"], 3),
        ("NVIC", ["NVIC_SetPriority"], 4),
        ("UART", ["UART_Init"], 5),
        ("SPI", ["SPI_Init"], 5),
        ("I2C", ["I2C_Init"], 5),
        ("ADC", ["ADC_Init"], 6),
        ("TIM", ["TIM_Base_Init", "TIM_PWM_Init", "TIM_OC_Init", "TIM_IC_Init"], 7),
    ]

    # Simple ordering check: find first occurrence of each group
    positions: dict[str, int] = {}
    for group_name, func_names, _ in priorities:
        for fn, pos in ordered:
            if fn in func_names:
                if group_name not in positions or pos < positions[group_name]:
                    positions[group_name] = pos

    if not positions:
        findings.append({
            "severity": "info",
            "category": "init_order",
            "file": "(multiple)",
            "message": "No HAL initialization calls detected across BSP files — "
                       "may use bare-metal or non-HAL approach",
        })
        return findings

    # HAL_Init should be first
    if "HAL_Init" in positions:
        hal_init_pos = positions["HAL_Init"]
        for group_name, pos in positions.items():
            if group_name != "HAL_Init" and pos < hal_init_pos:
                findings.append({
                    "severity": "minor",
                    "category": "init_order",
                    "file": "(multiple)",
                    "message": f"'{group_name}' initialized before HAL_Init() — "
                               f"HAL_Init should be the first HAL call",
                })
                break

    # NVIC should be configured after DMA (DMA IRQs need to be enabled)
    if "NVIC" in positions and "DMA" in positions:
        if positions["NVIC"] < positions["DMA"]:
            findings.append({
                "severity": "info",
                "category": "init_order",
                "file": "(multiple)",
                "message": "NVIC priority set before DMA init — acceptable if DMA uses "
                           "default priority",
            })

    # Peripherals (UART, SPI, I2C) should come after DMA if they use it
    dma_pos = positions.get("DMA")
    if dma_pos:
        for periph in ["UART", "SPI", "I2C"]:
            if periph in positions and positions[periph] < dma_pos:
                findings.append({
                    "severity": "minor",
                    "category": "init_order",
                    "file": "(multiple)",
                    "message": f"{periph} initialized before DMA — verify {periph} does not "
                               f"require DMA channels during initialization",
                })

    return findings


def _check_peripheral_conflict(files: dict[str, list[Path]]) -> list[BspFinding]:
    """Check for peripheral conflicts (shared pins, resource contention)."""
    findings = []

    # Collect all GPIO pin assignments across peripheral config files
    pin_assignments: dict[str, str] = {}  # pin_id -> function

    all_categories = ["pin_mux", "peripheral_config"]
    for cat in all_categories:
        for f in files.get(cat, []):
            try:
                content = f.read_text()
            except OSError:
                continue

            # Look for patterns like: GPIO_PIN_X | GPIO_PIN_Y
            # and GPIO assignment to a specific UART/SPI/I2C instance
            pin_pats = re.finditer(
                r'(GPIO[A-Z])\s*.*?GPIO_PIN_(\d+)\s*[|]?\s*.*?(?:U(SART|ART|ART4|ART5|ART6|ART7|ART8|ART9)\d*'
                r'|SPI\d*|I2C\d*)',
                content, re.IGNORECASE)
            for m in pin_pats:
                port = m.group(1)
                pin = m.group(2)
                periph_match = re.search(
                    r'(U(SART|ART|ART4|ART5|ART6|ART7|ART8|ART9)\d*|SPI\d*|I2C\d*)',
                    content[m.start():m.end()], re.IGNORECASE)
                if periph_match:
                    pin_id = f"{port}_PIN{pin}"
                    func = periph_match.group(1)
                    if pin_id in pin_assignments and pin_assignments[pin_id] != func:
                        findings.append({
                            "severity": "critical",
                            "category": "pin_conflict",
                            "file": str(f),
                            "message": f"Pin {pin_id} assigned to BOTH "
                                       f"'{pin_assignments[pin_id]}' and '{func}' — "
                                       f"hardware conflict will cause malfunction",
                        })
                    else:
                        pin_assignments[pin_id] = func

    if not findings and pin_assignments:
        findings.append({
            "severity": "info",
            "category": "pin_conflict",
            "file": "(multiple)",
            "message": f"No pin conflicts detected across {len(pin_assignments)} pin assignments",
        })

    return findings


def _check_hal_api_consistency(files: dict[str, list[Path]]) -> list[BspFinding]:
    """Check HAL API usage for consistency across the BSP."""
    findings = []

    # Collect HAL Init/DeInit/MspInit/MspDeInit calls
    hal_api_counts: dict[str, int] = {}
    all_categories = list(files.keys())
    for cat in all_categories:
        for f in files.get(cat, []):
            try:
                content = f.read_text()
            except OSError:
                continue

            # Count init/deinit patterns
            for api_pat in [
                r'HAL_(\w+)_Init', r'HAL_(\w+)_DeInit',
                r'HAL_(\w+)_MspInit', r'HAL_(\w+)_MspDeInit',
                r'HAL_(\w+)_Start', r'HAL_(\w+)_Stop',
            ]:
                for m in re.finditer(api_pat, content):
                    key = m.group(0)
                    hal_api_counts[key] = hal_api_counts.get(key, 0) + 1

    if not hal_api_counts:
        findings.append({
            "severity": "info",
            "category": "hal_api",
            "file": "(multiple)",
            "message": "No HAL API calls detected — firmware may not use STM32 HAL",
        })
        return findings

    # Check: every _Init should ideally have a corresponding _DeInit or error handling
    init_calls = {k: v for k, v in hal_api_counts.items() if "_Init" in k}
    deinit_calls = {k: v for k, v in hal_api_counts.items() if "_DeInit" in k}

    if init_calls:
        # Extract peripheral type from init calls
        init_periphs = set()
        for k in init_calls:
            m = re.match(r'HAL_(\w+)_', k)
            if m:
                init_periphs.add(m.group(1))

        deinit_periphs = set()
        for k in deinit_calls:
            m = re.match(r'HAL_(\w+)_', k)
            if m:
                deinit_periphs.add(m.group(1))

        missing_deinit = init_periphs - deinit_periphs
        if missing_deinit:
            findings.append({
                "severity": "info",
                "category": "hal_api",
                "file": "(multiple)",
                "message": f"Peripherals with Init but no DeInit: {', '.join(sorted(missing_deinit))} "
                           f"— may be acceptable if peripherals are never deinitialized",
            })

    # Check MspInit/MspDeInit pairing
    msp_inits = {k for k in hal_api_counts if "_MspInit" in k}
    msp_deinits = {k for k in hal_api_counts if "_MspDeInit" in k}
    for msp in msp_inits:
        msp_base = msp.replace("_MspInit", "")
        if f"{msp_base}_MspDeInit" not in msp_deinits:
            findings.append({
                "severity": "minor",
                "category": "hal_api",
                "file": "(multiple)",
                "message": f"{msp_base} has MspInit but no MspDeInit — "
                           f"may cause resource leak on reinitialization",
            })

    # Summary
    findings.append({
        "severity": "info",
        "category": "hal_api",
        "file": "(multiple)",
        "message": f"HAL API usage: {len(init_calls)} Init calls, {len(deinit_calls)} DeInit calls",
    })

    return findings


# ── Static checks: DMA configuration ──────────────────────────────────────


def _check_dma_config(files: dict[str, list[Path]]) -> list[BspFinding]:
    """Check DMA configuration for correctness."""
    findings = []

    dma_files = files.get("dma_config", [])
    if not dma_files:
        findings.append({
            "severity": "info",
            "category": "dma",
            "file": "(multiple)",
            "message": "No DMA configuration files found — system may not use DMA",
        })
        return findings

    # Check for HAL_DMA_Init calls
    dma_init_found = False
    dma_channel_configs = 0
    dma_irq_handlers = 0
    dma_circular_mode = False
    dma_periph_incs = False
    dma_mem_incs = False

    for f in dma_files:
        try:
            content = f.read_text()
        except OSError:
            continue

        if re.search(r'HAL_DMA_Init', content):
            dma_init_found = True

        dma_channel_configs += len(list(re.finditer(
            r'Channel\s*=|\.Channel\s*=', content)))

        dma_irq_handlers += len(list(re.finditer(
            r'HAL_DMA_IRQHandler|HAL_DMA_RegisterCallback|DMA.*_IRQHandler|DMA.*_IRQn',
            content)))

        if re.search(r'DMA_CIRCULAR|CIRCULAR\b', content, re.IGNORECASE):
            dma_circular_mode = True

        if re.search(r'DMA_PERIPH_INC|PeriphInc\s*=', content):
            dma_periph_incs = True

        if re.search(r'DMA_MEM_INC|MemInc\s*=', content):
            dma_mem_incs = True

    if dma_init_found:
        findings.append({
            "severity": "info",
            "category": "dma",
            "file": "(multiple)",
            "message": f"DMA initialized with {dma_channel_configs} channel(s), "
                       f"{dma_irq_handlers} IRQ handler(s)",
        })

        if dma_irq_handlers == 0:
            findings.append({
                "severity": "minor",
                "category": "dma",
                "file": "(multiple)",
                "message": "DMA initialized without IRQ handlers — verify polling/LLI mode "
                           "is used or interrupts are enabled elsewhere",
            })

        if dma_circular_mode:
            findings.append({
                "severity": "info",
                "category": "dma",
                "file": "(multiple)",
                "message": "DMA circular mode configured — verify no buffer overrun risk",
            })

        if not dma_periph_incs and not dma_mem_incs:
            findings.append({
                "severity": "info",
                "category": "dma",
                "file": "(multiple)",
                "message": "DMA peripheral and memory increment not explicitly visible "
                           "— verify Increment settings match transfer type",
            })
    else:
        findings.append({
            "severity": "info",
            "category": "dma",
            "file": "(multiple)",
            "message": "DMA files found but no HAL_DMA_Init call — DMA may be unused or "
                       "initialized in a non-standard way",
        })

    return findings


# ── Main static review ────────────────────────────────────────────────────


def _static_bsp_review(project_dir: Path) -> list[BspFinding]:
    """Run all static checks on discovered BSP files."""
    all_findings: list[BspFinding] = []
    files = _find_bsp_files(project_dir)

    total_files = sum(len(v) for v in files.values())
    if total_files == 0:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No BSP files (board*.h, target*.h, clock, pin mux, peripheral config) "
                       "found in project tree",
        })
        return all_findings

    # ── Board headers ──
    for f in files.get("board_headers", []):
        try:
            content = f.read_text()
        except OSError:
            continue
        log.info(f"  Checking board header: {f}")
        all_findings.extend(_check_pin_mux_gpio(content, f))
        all_findings.extend(_check_pin_mux_conflicts(content, f))

    # ── Clock config ──
    for f in files.get("clock_config", []):
        try:
            content = f.read_text()
        except OSError:
            continue
        log.info(f"  Checking clock config: {f}")
        all_findings.extend(_check_clock_hse(content, f))
        all_findings.extend(_check_clock_pll(content, f))
        all_findings.extend(_check_system_clock_frequency(content, f))

    # ── Pin mux ──
    for f in files.get("pin_mux", []):
        try:
            content = f.read_text()
        except OSError:
            continue
        log.info(f"  Checking pin mux: {f}")
        all_findings.extend(_check_pin_mux_gpio(content, f))
        all_findings.extend(_check_pin_mux_conflicts(content, f))

    # ── Peripheral init order (cross-file) ──
    log.info("  Checking peripheral init order...")
    all_findings.extend(_check_peripheral_init_order(files))
    all_findings.extend(_check_peripheral_conflict(files))
    all_findings.extend(_check_hal_api_consistency(files))

    # ── DMA config ──
    log.info("  Checking DMA configuration...")
    all_findings.extend(_check_dma_config(files))

    # ── Runtime allocation checks (alloca/VLA/dynamic) ──
    log.info("  Checking runtime allocation (alloca/VLA/dynamic)...")
    all_findings.extend(_check_runtime_allocation_integrity(files))

    return all_findings


# ── LLM-powered review ────────────────────────────────────────────────────


def _build_bsp_review_prompt(files: dict[str, list[Path]]) -> tuple[str, str]:
    """Build prompts for LLM-powered BSP review."""
    contents: dict[str, str] = {}
    for category, cat_files in files.items():
        for f in cat_files:
            try:
                contents[f"{category}:{f}"] = f.read_text()
            except OSError:
                continue

    system_prompt = (
        "You are an embedded firmware expert reviewing a Board Support Package (BSP).\n"
        "Analyze the provided files for:\n"
        "1. **Pin Mux**: Are GPIO, UART, I2C, SPI, ADC pins correctly assigned?\n"
        "   Any conflicts or missing configurations?\n"
        "2. **Clock Tree**: Is the clock source (HSE/HSI/LSE/LSI) configured? Are PLL\n"
        "   parameters (PLLM, PLLN, PLLP, PLLQ/R) correct for the target frequency?\n"
        "3. **Peripheral Init Order**: Are peripherals initialized in the correct order\n"
        "   (HAL_Init → Clock → GPIO → DMA → NVIC → UART/SPI/I2C → ADC/TIM)?\n"
        "4. **HAL Interface Consistency**: Are Init/DeInit/MspInit/MspDeInit paired?\n"
        "5. **DMA Configuration**: Is DMA set up correctly for the peripherals that use it?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## BSP Files\n"]
    for path_key, text in contents.items():
        user_lines.append(f"### {path_key}\n```\n{text[:4000]}\n```\n")
    user_lines.append(
        "Review the BSP files above. "
        "Check for any issues with pin assignments, clock tree, peripheral init ordering, "
        "or HAL API consistency that would affect embedded firmware correctness."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_bsp(session: PipelineSession) -> str:
    """Step: 小克 — BSP 板级支持包验证。

    Discovers and reviews board support package files (board headers, pin mux,
    clock config, peripheral configuration, DMA config) for correctness.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  🧩 [小克] BSP 板级支持包验证开始...")
        log.info("Running BSP validation")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static BSP checks...")
        static_findings = _static_bsp_review(project_dir)
        log.info(f"Static BSP review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered BSP review...")
        llm_review = ""
        bsp_files = _find_bsp_files(project_dir)
        total_files = sum(len(v) for v in bsp_files.values())
        if total_files > 0:
            try:
                system_prompt, user_prompt = _build_bsp_review_prompt(bsp_files)
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-bsp", "usage": usage})
                log.info(f"LLM BSP review: {usage.get('total_tokens', '?')} tokens")
            except Exception as e:
                log.warning(f"LLM BSP review failed (non-fatal): {e}")
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

        req_ids = [
            "SWE-MISRA-S1",       # MISRA C:2023 integration
        ]

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-bsp",
            "spec_ref": "SWE.5",
            "req_ids": req_ids,
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "bsp_file_counts": {k: len(v) for k, v in bsp_files.items()},
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "bsp-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write BSP review: {e}")
            raise PipelineStepError(f"Cannot write BSP review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] BSP 板级支持包验证完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"BSP review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"BSP review step failed: {e}")
        raise PipelineStepError(f"BSP review step failed: {e}")
