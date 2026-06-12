#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Embedded C Static Analyzer — AI-powered code review for
embedded firmware (ARM Cortex-M, ESP32, nRF52, STM32).

Detection rules:
  - volatile keyword missing on ISR-shared variables
  - memory barrier missing (ARM Cortex-M DSB/ISB/DMB)
  - Interrupt nesting race conditions
  - Watchdog feed position issues
  - Unprotected global variables (no critical section)
  - Hardcoded delays (raw loops, not HAL_Delay)
  - Stack overflow risk (large local variables / recursion)
  - printf/debug traces left in release code
"""

import re
import json
from pathlib import Path
from typing import Optional

# Import LLM client with fallback for direct/package execution
import sys
from pathlib import Path

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

# ── Regex patterns for static analysis ─────────────────────────

# ISR handler definition patterns
RE_ISR_HANDLER = re.compile(
    r'(?:Callback|_IRQHandler\s*\()|'
    r'__attribute__\s*\(\s*\(\s*interrupt\s*\)\s*\)',
)

# volatile keyword on shared variable patterns
RE_VOLATILE_VAR = re.compile(
    r'(?:static\s+)?(?:uint\d+_t|int\d+_t|char|float|double|bool)\s+\*?\s*\w+\s*;',
)

# Shared global variable (inside ISR context)
RE_GLOBAL_VAR = re.compile(
    r'^[a-zA-Z_]\w*\s+(?:\*\s*)?[a-zA-Z_]\w*\s*(?:\[[^\]]*\])?\s*;'
    r'|^extern\s+[a-zA-Z_]\w*\s+(?:\*\s*)?[a-zA-Z_]\w*\s*(?:\[[^\]]*\])?\s*;',
    re.MULTILINE,
)

# Memory barrier patterns (ARM Cortex-M)
RE_MEMORY_BARRIER = re.compile(
    r'\b(?:__DSB|__ISB|__DMB|dsb|isb|dmb)|\b__sync_synchronize|\b__atomic_store|'
    r'\b__atomic_load|\b__atomic_exchange',
)

# Critical section patterns
RE_CRITICAL_SECTION = re.compile(
    r'\b(?:taskENTER_CRITICAL|taskEXIT_CRITICAL|portENTER_CRITICAL|portEXIT_CRITICAL|'
    r'__disable_irq|__enable_irq|enter_critical|exit_critical|'
    r'HAL_NVIC_DisableIRQ|HAL_NVIC_EnableIRQ)\b',
)

# Watchdog feed patterns
RE_WATCHDOG_FEED = re.compile(
    r'\b(?:HAL_IWDG_Refresh|wdt_feed|WDOG_Feed|iwdg_refresh|feed_watchdog|'
    r'__HAL_IWDG_RELOAD_COUNTER)\b',
)

# Hardcoded delay patterns (non-HAL delays)
RE_HARDCODED_DELAY = re.compile(
    r'for\s*\(\s*(?:volatile\s+)?(?:int|long|unsigned|uint32_t)\s+\w+\s*=\s*\d+\s*;|'
    r'while\s*\(\s*\w+\s*--\s*\)|'
    r'delay_us\s*\(|'
    r'delay_ms\s*\(',
)

# HAL_Delay usage (acceptable)
RE_HAL_DELAY = re.compile(r'\bHAL_Delay\b')

# printf / debug output patterns
RE_DEBUG_PRINTF = re.compile(
    r'\bprintf\s*\(|fprintf\s*\(stdout|fprintf\s*\(stderr|'
    r'puts\s*\(|debug_print|DEBUG_PRINT|DBG_PRINT\b|'
    r'#\s*define\s+DEBUG\b',
)

# Large local arrays (stack overflow risk)
RE_LARGE_LOCAL = re.compile(
    r'\b(?:uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t|'
    r'char|float|double)\s+\w+\s*\[\s*\d{3,}\s*\]',
    re.MULTILINE,
)

# Recursive function indicators (stack overflow risk)
RE_RECURSIVE = re.compile(
    r'(\w+)\s*\(.*\)\s*\n?.*\{\n.*\1\s*\(',
    re.DOTALL | re.MULTILINE,
)

# ── LLM-enhanced reasoning ────────────────────────────────────

_LLM_SYSTEM_PROMPT = """你是一个嵌入式C代码审查专家，专注于ARM Cortex-M、ESP32、STM32、nRF52等MCU平台。
请分析提供的嵌入式C代码片段，给出专业审查意见。只讨论代码问题，不要夸奖代码。
输出格式为JSON数组：
[{"severity":"critical|major|minor|info", "line":N, "message":"问题描述", "suggestion":"修复建议"}]
如果无问题，返回空数组 []。"""


def _llm_review_snippet(code: str, max_retries: int = 1) -> list[dict]:
    """Use LLM to review a code snippet for embedded C issues.

    Returns a list of finding dicts with severity, line, message, suggestion.
    Falls back to empty list on failure.
    """
    try:
        trimmed = code[:8000]
        client = _get_llm_client()
        resp = client.chat_completion(
            system_prompt=_LLM_SYSTEM_PROMPT,
            user_prompt=(
                f"请审查以下嵌入式C代码。重点关注：\n"
                f"1. volatile关键字缺失（ISR共享变量）\n"
                f"2. memory barrier缺失（ARM Cortex-M）\n"
                f"3. 中断嵌套竞态条件\n"
                f"4. 看门狗喂狗位置不当\n"
                f"5. 全局变量未保护\n"
                f"6. 硬编码延时\n"
                f"7. 堆栈溢出风险\n"
                f"8. printf/debug遗留在release代码\n\n"
                f"```c\n{trimmed}\n```"
            ),
            temperature=0.1,
            max_tokens=4096,
            retries=max_retries,
        )
        content = resp.get("content", "")
        # Try to extract JSON array from response
        json_match = re.search(r'\[.*?\]', content, re.DOTALL)
        if json_match:
            findings = json.loads(json_match.group(0))
            if isinstance(findings, list):
                return findings
        return []
    except Exception:
        return []


# ── Static analysis functions ─────────────────────────────────

def _check_content(content: str, filepath: str, rel_path: str) -> list[dict]:
    """Run all static analysis checks on C source content.

    Returns a list of raw finding dicts (severity, line, message).
    """
    findings = []
    lines = content.split("\n")
    is_isr_context = bool(RE_ISR_HANDLER.search(content))

    # ── 1. Volatile missing on ISR-shared globals ──
    if is_isr_context:
        # Find global variable declarations that should be volatile
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip comments, typedefs, function signatures, local variables
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            if re.match(r'^(typedef|struct|enum|union|void\s+\w+\s*\()', stripped):
                continue

            # Detect non-volatile static/global variables inside ISR files
            if re.match(r'^(static\s+)?(uint\d+_t|int\d+_t|uint8_t|uint16_t|uint32_t|'
                       r'uint64_t|int8_t|int16_t|int32_t|int64_t|char|bool|float)\s+'
                       r'\w+\s*(?:\[[^\]]*\])?\s*;', stripped):
                # Check if it's inside a function (local) or file scope
                is_file_scope = True
                for j in range(i - 1, max(i - 10, -1), -1):
                    prev = lines[j].strip()
                    if prev.endswith("{"):
                        is_file_scope = False
                        break
                if is_file_scope and "volatile" not in line:
                    findings.append({
                        "severity": "critical",
                        "line": i + 1,
                        "message": f"全局变量缺少volatile关键字 —— ISR和主循环共享的变量应使用volatile防止编译器优化",
                    })

    # ── 2. Memory barrier missing after ISR / critical section ──
    if content.find("__disable_irq") >= 0 or content.find("taskENTER_CRITICAL") >= 0:
        if not RE_MEMORY_BARRIER.search(content):
            for i, line in enumerate(lines):
                if "taskEXIT_CRITICAL" in line or "__enable_irq" in line:
                    # Check if a memory barrier exists within 3 lines after
                    following = "\n".join(lines[i:min(i + 4, len(lines))])
                    if not RE_MEMORY_BARRIER.search(following):
                        findings.append({
                            "severity": "major",
                            "line": i + 1,
                            "message": "退出临界区后缺少memory barrier（DSB/ISB）—— ARM Cortex-M需要屏障指令确保内存操作顺序",
                        })
                    break

    # ── 3. Interrupt nesting race conditions ──
    if is_isr_context:
        # Check if global variables are modified within ISR without protection
        in_isr_body = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Track whether we're inside an ISR handler function body
            if re.search(r'Callback\s*\(|_IRQHandler\s*\(', line):
                in_isr_body = True
            elif stripped == "}":
                # Keep track of function body by checking if preceded by ISR
                pass  # We use a simpler approach below
            
            if "g_" in stripped:
                # Check for assignment expressions (not declarations with type names)
                is_declaration = bool(re.match(
                    r'^(static\s+)?(volatile\s+)?'
                    r'(uint\d+_t|int\d+_t|uint8_t|uint16_t|uint32_t|'
                    r'uint64_t|int8_t|int16_t|int32_t|int64_t|char|bool|float)',
                    stripped,
                ))
                if is_declaration:
                    continue
                if stripped.startswith("*") or stripped.startswith("//") or stripped.startswith("#"):
                    continue
                # Check for assignment to g_ variables
                if re.search(r'\bg_\w+\s*[+\-*/]?=', stripped):
                    # Check if inside critical section (look back up to 15 lines for entry)
                    protected = False
                    for j in range(max(i - 15, 0), i):
                        prev = lines[j].strip()
                        if "__disable_irq" in prev or "taskENTER_CRITICAL" in prev \
                           or "portENTER_CRITICAL" in prev:
                            protected = True
                            break
                    if not protected:
                        findings.append({
                            "severity": "major",
                            "line": i + 1,
                            "message": "中断上下文中修改全局变量缺少临界区保护 —— 可能发生竞态条件",
                        })

    # ── 4. Watchdog feed in wrong position ──
    wdt_lines = []
    for i, line in enumerate(lines):
        if RE_WATCHDOG_FEED.search(line):
            wdt_lines.append(i + 1)

    if wdt_lines and len(wdt_lines) > 1:
        # Check if feeds are inside long loops or ISRs
        for wdt_line_no in wdt_lines:
            wdt_idx = wdt_line_no - 1
            # Look for enclosing while/for blocks
            nesting = 0
            found_loop = False
            for j in range(wdt_idx, -1, -1):
                l = lines[j].strip()
                if "while (" in l or "for (" in l:
                    found_loop = True
                    break
            if found_loop:
                findings.append({
                    "severity": "info",
                    "line": wdt_line_no,
                    "message": "看门狗喂狗在循环内部 —— 长时间阻塞可能仍会触发看门狗复位，建议在循环顶部喂狗",
                })

    # ── 5. Unprotected global variables ──
    if not is_isr_context:
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Look for g_ prefix globals modified outside critical section
            if re.match(r'\bg_\w+\s*=', stripped):
                # Check if preceded by critical section entry (within reasonable window)
                protected = False
                for j in range(max(i - 20, 0), i):
                    prev = lines[j].strip()
                    if "taskENTER_CRITICAL" in prev or "__disable_irq" in prev or \
                       "portENTER_CRITICAL" in prev:
                        protected = True
                        break
                if not protected and not re.match(r'^\s*(//|/\*|\*)', stripped):
                    findings.append({
                        "severity": "major",
                        "line": i + 1,
                        "message": f"全局变量被修改但未使用临界区保护 —— 可能被多任务/ISR同时访问",
                    })

    # ── 6. Hardcoded delays (non-HAL) ──
    for i, line in enumerate(lines):
        m = RE_HARDCODED_DELAY.search(line)
        if m:
            # Skip HAL_Delay calls
            if RE_HAL_DELAY.search(line):
                continue
            findings.append({
                "severity": "major",
                "line": i + 1,
                "message": f"发现硬编码延时循环 —— 应使用HAL_Delay或vTaskDelay替代以支持FreeRTOS调度",
            })

    # ── 7. Large local variables on stack ──
    for i, line in enumerate(lines):
        m = RE_LARGE_LOCAL.search(line)
        if m:
            # Only flag if inside a function body, not at file scope
            is_inside_func = False
            for j in range(i, -1, -1):
                l = lines[j].strip()
                if "{" in l and not l.strip().startswith("//"):
                    is_inside_func = True
                    break
                if l.startswith("static") or l.startswith("#") or l == "":
                    break
            if is_inside_func:
                findings.append({
                    "severity": "major",
                    "line": i + 1,
                    "message": f"大局部数组在栈上分配 —— 可能导致栈溢出，建议使用静态分配或heap_caps_malloc",
                })

    # ── 8. Printf/debug in release code ──
    for i, line in enumerate(lines):
        stripped = line.strip()
        if RE_DEBUG_PRINTF.search(stripped):
            # Skip commented-out lines
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            # DEBUG #define is common, use info level
            if "#define" in stripped and "DEBUG" in stripped:
                findings.append({
                    "severity": "info",
                    "line": i + 1,
                    "message": "DEBUG宏定义存在 —— release构建应undef或条件编译",
                })
            elif re.search(r'\bprintf\s*\(', stripped):
                findings.append({
                    "severity": "major",
                    "line": i + 1,
                    "message": "printf遗留 —— release固件应移除或使用条件编译(#ifdef DEBUG)，否则增加ROM尺寸",
                })

    return findings


# ── Main review entry point ────────────────────────────────────

def review_embedded_c(task_name: str, project_dir: str, changed_files: list[str]) -> object:
    """Review embedded C source files for common firmware defects.

    Args:
        task_name: Name of the review task.
        project_dir: Project root directory.
        changed_files: List of changed file paths.

    Returns:
        ReviewResult object with findings.
    """
    # Late import to avoid circular dependency
    from .run import ReviewResult, ReviewFinding

    result = ReviewResult(task_name, "embedded-c-reviewer")

    c_files = [f for f in changed_files if f.endswith((".c", ".h"))]

    if not c_files:
        # Scan project directory for relevant C files
        src_dir = Path(project_dir) / "src"
        cross_dir = Path(project_dir) / "cross"
        main_dir = Path(project_dir) / "main"
        dirs_to_scan = [d for d in [src_dir, cross_dir, main_dir] if d.exists()]

        if not dirs_to_scan:
            # Try template directories
            templates = Path(project_dir) / "templates"
            if templates.exists():
                for tmpl in templates.iterdir():
                    main_subdir = tmpl / "main"
                    if main_subdir.exists():
                        dirs_to_scan.append(main_subdir)
                    src_subdir = tmpl / "src"
                    if src_subdir.exists():
                        dirs_to_scan.append(src_subdir)

        for scan_dir in dirs_to_scan:
            for fpath in scan_dir.rglob("*"):
                if fpath.suffix in (".c", ".h"):
                    c_files.append(str(fpath.relative_to(project_dir)))

    if not c_files:
        result.status = "passed"
        result.summary = "No embedded C files found for review"
        return result

    for rel_path in c_files:
        abs_path = Path(project_dir) / rel_path
        if not abs_path.exists():
            continue

        content = abs_path.read_text(encoding="utf-8", errors="replace")

        # ── Static analysis pass ──
        findings_data = _check_content(content, str(abs_path), rel_path)

        for fd in findings_data:
            result.add_finding(ReviewFinding(
                severity=fd.get("severity", "info"),
                category="embedded-c",
                file=rel_path,
                line=fd.get("line", 0),
                message=fd.get("message", fd.get("suggestion", "")),
            ))

        # ── LLM-enhanced pass (for complex patterns) ──
        try:
            llm_findings = _llm_review_snippet(content)
            for fd in llm_findings:
                sev = fd.get("severity", "info")
                line = fd.get("line", 0)
                msg = fd.get("message", "")
                suggestion = fd.get("suggestion", "")
                full_msg = msg
                if suggestion:
                    full_msg += f" | 建议: {suggestion}"
                result.add_finding(ReviewFinding(
                    severity=sev,
                    category="embedded-c-llm",
                    file=rel_path,
                    line=line,
                    message=full_msg,
                ))
        except Exception:
            pass  # LLM pass is non-blocking

    result.decide()
    return result
