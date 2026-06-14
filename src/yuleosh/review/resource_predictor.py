#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH AI Resource Usage Predictor — estimates RAM, ROM, CPU usage,
stack risk, and ISR latency for embedded firmware (ARM Cortex-M,
ESP32, STM32, nRF52).

Uses LLM-enhanced reasoning via DeepSeek V4 to analyze C source code
and produce realistic resource projections.
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional

# Import LLM client with fallback for direct/package execution
_LLM_CLIENT = None

def _get_llm_client():
    """Lazy-load the LLM client, supporting both relative and direct imports."""
    global _LLM_CLIENT
    if _LLM_CLIENT is not None:
        return _LLM_CLIENT
    try:
        from ..llm import client as llm_client
        _LLM_CLIENT = llm_client
        return _LLM_CLIENT
    except (ImportError, ValueError):
        try:
            from llm import client as llm_client
            _LLM_CLIENT = llm_client
            return _LLM_CLIENT
        except ImportError:
            # Mock client for testing
            class _MockLLM:
                @staticmethod
                def chat_completion(**kwargs):
                    return {"content": "[]", "model": "mock", "usage": {}}
            _LLM_CLIENT = _MockLLM()
            return _LLM_CLIENT

log = logging.getLogger("review.resource_predictor")

# ── Statistical heuristics ────────────────────────────────────

# Average code size per construct (ARM Thumb-2 / Cortex-M4)
CODE_SIZE_ESTIMATES: dict[str, int] = {
    "function_prologue": 8,       # push r4-r11, lr
    "function_epilogue": 4,       # pop, bx lr
    "integer_arith": 2,           # ADD, SUB, etc.
    "load_store": 4,              # LDR, STR (literal pool)
    "branch": 4,                  # B, BL, BX
    "call": 4,                    # BL <target>
    "per_call_overhead": 8,       # Argument passing + link register
    "switch_case": 8,             # Table branch (average)
    "loop_overhead": 12,          # CMP + B per iteration
}

# Average RAM per data type (bytes)
RAM_SIZE: dict[str, int] = {
    "uint8_t": 1,
    "int8_t": 1,
    "uint16_t": 2,
    "int16_t": 2,
    "uint32_t": 4,
    "int32_t": 4,
    "uint64_t": 8,
    "int64_t": 8,
    "float": 4,
    "double": 8,
    "bool": 1,
    "char": 1,
    "pointer": 4,  # 32-bit MCU
}

# ISR latency estimates per platform (critical section, microseconds)
ISR_LATENCY_ESTIMATE = {
    "cortex_m0": 1.5,
    "cortex_m3": 0.9,
    "cortex_m4": 0.8,
    "cortex_m7": 0.6,
    "esp32": 1.2,
    "nrf52": 0.8,
    "stm32f4": 0.8,
}


# ── Static estimators ─────────────────────────────────────────

def _detect_platform(content: str) -> str:
    """Detect target platform from C source content."""
    platform_map = {
        "cortex_m0": [r"STM32F0", r"STM32L0", r"Cortex-M0"],
        "cortex_m3": [r"STM32F1", r"STM32F2", r"Cortex-M3"],
        "cortex_m4": [r"STM32F4", r"STM32L4", r"STM32G4", r"Cortex-M4"],
        "cortex_m7": [r"STM32F7", r"STM32H7", r"Cortex-M7"],
        "esp32": [r"ESP32", r"esp32", r"esp_wifi", r"esp_event", r"nvs_flash"],
        "nrf52": [r"nRF52", r"nrf52", r"NRF52", r"softdevice"],
    }
    for platform, patterns in platform_map.items():
        for pat in patterns:
            if re.search(pat, content):
                return platform
    return "cortex_m4"  # Default


def _count_global_ram(content: str) -> int:
    """Estimate RAM usage from global/static variables (BSS + data)."""
    total = 0
    patterns = [
        r'(?:static\s+)?(?:const\s+)?(uint8_t|uint16_t|uint32_t|uint64_t|'
        r'int8_t|int16_t|int32_t|int64_t|float|double|bool|char)\s+\w+\s*;',
        r'(?:static\s+)?(?:const\s+)?(uint8_t|uint16_t|uint32_t|uint64_t|'
        r'int8_t|int16_t|int32_t|int64_t|float|double|bool|char)\s+\w+\s*\[(\d+)\]',
        r'(?:static\s+)?(?:const\s+)?(uint8_t|uint16_t|uint32_t|uint64_t|'
        r'int8_t|int16_t|int32_t|int64_t|float|double|bool|char)\s+\w+\s*\[(\d+)\]\[\d+\]',
    ]
    for pat in patterns:
        for m in re.finditer(pat, content):
            dtype = m.group(1)
            base_size = RAM_SIZE.get(dtype, 4)
            array_size = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else 1
            total += base_size * array_size

    # Add struct/typedef sizes (approximate by member count)
    struct_matches = re.findall(
        r'(?:typedef\s+)?struct\s+\w*\s*\{([^}]+)\}', content, re.DOTALL
    )
    for body in struct_matches:
        members = body.strip().split(";")
        for m in members:
            m = m.strip()
            if not m:
                continue
            for dtype, size in RAM_SIZE.items():
                if dtype in m:
                    total += size
                    break
            else:
                total += 4  # Unknown type, assume 4 bytes

    return total


def _count_rom_estimate(content: str) -> int:
    """Estimate ROM (code section) usage."""
    total = 0

    # Count functions
    funcs = re.findall(
        r'(?:static\s+)?(?:\w+\s+)*\w+\s+\*?\w+\s*\([^)]*\)\s*\{',
        content,
    )
    total += len(funcs) * 40  # Average 40 bytes per function (prologue + body baseline)

    # Count statements (approximate Thumb2 instructions)
    stmts = re.findall(r'[;{}]', content)
    total += len(stmts) * 2  # ~2 bytes per statement

    # Count string literals (stored in flash)
    strings = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content)
    for s in strings:
        total += len(s) + 1  # +1 for null terminator

    # Count constant data
    const_arrays = re.findall(
        r'(?:static\s+)?const\s+\w+\s+\w+\s*\[\s*\d*\s*\]\s*=\s*\{([^}]+)\}',
        content,
    )
    for arr in const_arrays:
        items = arr.split(",")
        total += len(items) * 4  # Assume 4 bytes per element

    return total


def _assess_stack_risk(content: str) -> str:
    """Assess stack overflow risk: low/medium/high."""
    risk_score = 0

    # Check for large local arrays
    large_locals = re.findall(
        r'\b(?:uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|'
        r'int64_t|char|float|double)\s+\w+\s*\[\s*(\d{2,})\s*\]',
        content,
    )
    for size_str in large_locals:
        size = int(size_str)
        if size > 512:
            risk_score += 3
        elif size > 256:
            risk_score += 2
        elif size > 128:
            risk_score += 1

    # Check for deep nesting
    nesting = 0
    max_nesting = 0
    for ch in content:
        if ch == "{":
            nesting += 1
            max_nesting = max(max_nesting, nesting)
        elif ch == "}":
            nesting = max(0, nesting - 1)
    if max_nesting > 8:
        risk_score += 2
    elif max_nesting > 5:
        risk_score += 1

    # Check for recursion
    recursive_funcs = re.findall(
        r'(\w+)\s*\(.*\)\s*\n?.*\{\n.*\1\s*\(', content, re.DOTALL
    )
    if recursive_funcs:
        risk_score += 3

    # Check for alloca or VLA
    if "alloca" in content or "__builtin_alloca" in content:
        risk_score += 3

    # Check for deep call chains
    call_chain_depth = 0
    for _ in re.finditer(r'\b(\w+)\s*\([^)]*\)\s*;', content):
        call_chain_depth += 1
    if call_chain_depth > 50:
        risk_score += 1

    if risk_score >= 5:
        return "高"
    elif risk_score >= 2:
        return "中"
    return "低"


def _estimate_isr_latency(content: str, platform: str) -> str:
    """Estimate worst-case ISR latency in microseconds."""
    base = ISR_LATENCY_ESTIMATE.get(platform, 1.0)
    latency = base

    # Check for long critical sections
    critical_sections = re.findall(
        r'(?:__disable_irq|taskENTER_CRITICAL|portENTER_CRITICAL).*?(?:__enable_irq|taskEXIT_CRITICAL|portEXIT_CRITICAL)',
        content,
        re.DOTALL,
    )
    for cs in critical_sections:
        cs_len = len(cs)
        # Each ~100 chars of critical section adds ~0.5 us
        latency += (cs_len / 100) * 0.5

    # Check for nested ISRs
    isr_count = len(re.findall(r'HAL_\w+_IRQHandler|__attribute__\s*\(\s*\(\s*interrupt\s*\)', content))
    if isr_count > 3:
        latency += isr_count * 0.3

    # FreeRTOS with multiple tasks adds overhead
    if "xTaskCreate" in content or "osThreadNew" in content:
        latency += 0.5

    return f"~{latency:.1f} μs (critical section)"


# ── LLM-enhanced predictor ────────────────────────────────────

_RESOURCE_LLM_PROMPT = """你是嵌入式固件资源估算专家。分析以下C代码片段，估算其在典型MCU（Cortex-M4 @ 80 MHz）上的资源占用。
输出必须是严格JSON格式，不要添加markdown标记：
{
  "ram_estimate": "~X.X KB (堆+数据段)",
  "rom_estimate": "~X.X KB (代码段)",
  "cpu_estimate": "~X% @ 80MHz (FreeRTOS)",
  "stack_risk": "低/中/高",
  "isr_latency": "~X.X μs (critical section)",
  "suggestions": ["建议1", "建议2"]
}
如果无法分析，使用统计估算。"""


def _llm_predict_resources(content: str) -> Optional[dict]:
    """Use LLM to generate resource predictions."""
    try:
        trimmed = content[:6000]
        client = _get_llm_client()
        resp = client.chat_completion(
            system_prompt=_RESOURCE_LLM_PROMPT,
            user_prompt=f"```c\n{trimmed}\n```",
            temperature=0.1,
            max_tokens=2048,
            retries=1,
        )
        raw = resp.get("content", "").strip()
        # Remove any markdown code block markers
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        data = json.loads(raw)
        # Validate required keys
        required = ["ram_estimate", "rom_estimate", "cpu_estimate", "stack_risk", "isr_latency", "suggestions"]
        if all(k in data for k in required):
            return data
        return None
    except Exception as e:
        log.warning("LLM resource prediction failed: %s", e)
        return None


# ── Public API ────────────────────────────────────────────────


def predict_resources(file_path: str) -> dict:
    """AI resource usage predictor.

    Args:
        file_path: Path to embedded C source file (.c/.h)

    Returns:
        dict with keys:
          ram_estimate, rom_estimate, cpu_estimate,
          stack_risk, isr_latency, suggestions
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "ram_estimate": "N/A (文件不存在)",
            "rom_estimate": "N/A (文件不存在)",
            "cpu_estimate": "N/A",
            "stack_risk": "N/A",
            "isr_latency": "N/A",
            "suggestions": ["文件未找到"],
        }

    content = path.read_text(encoding="utf-8", errors="replace")
    platform = _detect_platform(content)

    # ── Statistical estimation ──
    ram_bytes = _count_global_ram(content)
    rom_bytes = _count_rom_estimate(content)

    ram_kb = ram_bytes / 1024
    rom_kb = rom_bytes / 1024

    stack_risk = _assess_stack_risk(content)
    isr_latency = _estimate_isr_latency(content, platform)

    # Crude CPU estimate: assume loop heavy code uses ~15% at 80 MHz
    cpu_base = 5
    loops = len(re.findall(r'\b(?:while|for)\s*\(', content))
    cpu_base += min(loops, 40)  # Each loop structure adds overhead
    cpu_est = f"~{cpu_base}% @ 80MHz (FreeRTOS)"

    # ── LLM-enhanced pass ──
    llm_data = _llm_predict_resources(content)
    if llm_data:
        # Use LLM results as primary, with statistical as fallback reference
        suggestions = llm_data.get("suggestions", [])
        if ram_kb > 0 and "RAM" not in " ".join(suggestions):
            if ram_kb > 10:
                suggestions.append(f"静态RAM占用约{ram_kb:.1f}KB，考虑优化全局变量")
        return {
            "ram_estimate": llm_data.get("ram_estimate", f"~{ram_kb:.1f} KB (堆+数据段)"),
            "rom_estimate": llm_data.get("rom_estimate", f"~{rom_kb:.1f} KB (代码段)"),
            "cpu_estimate": llm_data.get("cpu_estimate", cpu_est),
            "stack_risk": llm_data.get("stack_risk", stack_risk),
            "isr_latency": llm_data.get("isr_latency", isr_latency),
            "suggestions": suggestions,
        }

    # ── Fallback: pure statistical ──
    suggestions = []
    if stack_risk in ("中", "高"):
        suggestions.append(f"栈溢出风险{stack_risk} —— 检查大局部变量和递归调用")
    if ram_kb > 10:
        suggestions.append(f"静态RAM占用约{ram_kb:.1f}KB，考虑优化全局变量")

    return {
        "ram_estimate": f"~{ram_kb:.1f} KB (堆+数据段)",
        "rom_estimate": f"~{rom_kb:.1f} KB (代码段)",
        "cpu_estimate": cpu_est,
        "stack_risk": stack_risk,
        "isr_latency": isr_latency,
        "suggestions": suggestions,
    }


def predict_all_in_project(project_dir: str) -> list[dict]:
    """Run resource prediction on all C/H files in the project.

    Args:
        project_dir: Project root path.

    Returns:
        List of dicts with per-file resource predictions.
    """
    results = []
    base = Path(project_dir)
    for pattern in ("**/*.c", "**/*.h"):
        for fpath in base.glob(pattern):
            rel = str(fpath.relative_to(base))
            try:
                pred = predict_resources(str(fpath))
                pred["file"] = rel
                results.append(pred)
            except Exception as e:
                results.append({
                    "file": rel,
                    "error": str(e),
                })
    return results
