"""
yuleOSH Preview — Code parser and metrics.

Provides file discovery, framework scanning, and complexity measurement
functions used by the preview analyzer.
"""

import re
from pathlib import Path
from typing import Optional

from yuleosh.preview.compliance_analyzer import _scan_risks

# Supported file extensions for analysis (PREVIEW-REQ-002)
SUPPORTED_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".py", ".yaml", ".yml", ".md",
                        ".cfg", ".cmake", ".txt", ".arxml", ".dts", ".ld", ".json",
                        ".toml", ".ini", ".svg", ".css", ".js", ".ts", ".tsx"}


def _discover_files(source_dir: Path) -> tuple[list[Path], list[str], list[str], list[str], list[str]]:
    """Discover and categorize all files in source directory."""
    all_files = []
    source_files = []  # .c, .cpp, .py, etc.
    header_files = []  # .h, .hpp
    test_files = []
    config_files = []

    for f in source_dir.rglob("*"):
        if f.is_dir() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        all_files.append(f)
        rel_path = str(f.relative_to(source_dir))

        if ext in (".h", ".hpp"):
            header_files.append(rel_path)
        elif ext in (".c", ".cpp", ".py", ".js", ".ts", ".tsx"):
            source_files.append(rel_path)
        elif ext in (".yaml", ".yml", ".cfg", ".cmake", ".txt", ".ld",
                     ".json", ".toml", ".ini"):
            config_files.append(rel_path)

        if "test" in f.stem.lower():
            test_files.append(rel_path)

    return all_files, source_files, header_files, test_files, config_files


# ── Framework scanning ─────────────────────────────────────────────────


def _scan_frameworks(source_dir: Path) -> list[dict]:
    """Detect embedded frameworks from source content/signatures."""
    frameworks = []
    checks = {
        "FreeRTOS": [
            r'#include\s+["<]FreeRTOS\.h[">]',
            r'vTaskStartScheduler\s*\(',
            r'xQueueCreate\s*\(',
        ],
        "Zephyr": [
            r'#include\s+[<"]zephyr/kernel\.h[>"]',
            r'#include\s+[<"]zephyr/device\.h[>"]',
            r'K_SEM_DEFINE\s*\(',
        ],
        "AUTOSAR": [
            r'#include\s+["<]Rte_',
            r'#include\s+["<]Os\.h[">]',
            r'SchM_Init\s*\(',
            r'EcuM_Init\s*\(',
        ],
        "STM32 HAL": [
            r'#include\s+["<]stm32f4xx_hal\.h[">]',
            r'HAL_Init\s*\(',
            r'HAL_GPIO_Init\s*\(',
        ],
        "ESP-IDF": [
            r'#include\s+[<"]esp_system\.h[>"]',
            r'#include\s+[<"]esp_wifi\.h[>"]',
            r'nvs_flash_init\s*\(',
            r'esp_event_loop_create_default\s*\(',
        ],
        "ARM CMSIS": [
            r'#include\s+["<]CMSIS/core_cm',
            r'SystemCoreClock\b',
            r'SysTick_Config\s*\(',
            r'SystemInit\s*\(',
        ],
        "Unity Test": [
            r'#include\s+["<]unity\.h[">]',
            r'UNITY_BEGIN\s*\(',
            r'TEST_ASSERT_',
        ],
        "Linux Kernel": [
            r'#include\s+[<"]linux/kernel\.h[>"]',
            r'#include\s+[<"]linux/module\.h[>"]',
            r'MODULE_LICENSE\s*\(',
            r'MODULE_AUTHOR\s*\(',
        ],
    }

    for name, patterns in checks.items():
        found_any = []
        for pat in patterns:
            for f in _find_matching_files(source_dir, pat):
                found_any.append(str(f.relative_to(source_dir)))
                break

        if found_any:
            frameworks.append({
                "name": name,
                "detected": True,
                "matched_patterns": len(found_any),
                "sample_files": found_any[:3],
            })

    return frameworks


def _find_matching_files(source_dir: Path, pattern: str) -> list[Path]:
    """Find files whose content matches the given regex pattern."""
    matched = []
    compiled = re.compile(pattern)
    for f in source_dir.rglob("*"):
        if f.is_dir() or f.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            content = f.read_text(errors="replace")
            if compiled.search(content):
                matched.append(f)
        except Exception:
            pass
    return matched


# ── Complexity measurement ────────────────────────────────────────────


def _measure_complexity(source_dir: Path) -> dict:
    """Measure code complexity metrics."""
    total_functions = 0
    total_lines_in_functions = 0
    max_function_lines = 0
    function_lengths: list[int] = []

    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        brace_depth = 0
        in_function = False
        func_start = 0
        simpler_func_re = re.compile(r'^(?:static\s+)?\w+(?:\s+\w+)*\s*\(')

        for i, line in enumerate(lines):
            stripped = line.strip()

            if not in_function:
                if simpler_func_re.match(stripped) and stripped.endswith("("):
                    in_function = True
                    func_start = i
                    total_functions += 1
                    continue

            if in_function:
                brace_depth += stripped.count("{")
                brace_depth -= stripped.count("}")
                if brace_depth <= 0:
                    func_lines = i - func_start + 1
                    function_lengths.append(func_lines)
                    total_lines_in_functions += func_lines
                    max_function_lines = max(max_function_lines, func_lines)
                    in_function = False

    avg_lpf = round(total_lines_in_functions / max(total_functions, 1), 1)

    max_nesting = _measure_max_nesting(source_dir)

    return {
        "total_functions": total_functions,
        "total_function_lines": total_lines_in_functions,
        "avg_lines_per_function": avg_lpf,
        "max_function_lines": max_function_lines,
        "max_nesting_depth": max_nesting,
    }


def _measure_max_nesting(source_dir: Path) -> int:
    """Measure maximum nesting depth of control structures in .c files."""
    max_nesting = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue

        depth = 0
        for line in content.split("\n"):
            stripped = line.strip()
            open_braces = stripped.count("{")
            close_braces = stripped.count("}")
            depth += open_braces
            depth -= close_braces
            if depth > max_nesting:
                max_nesting = depth
    return max_nesting


def _measure_per_file_complexity(source_dir: Path) -> list[dict]:
    """Measure per-file complexity metrics for top-level source files."""
    file_metrics = []

    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        total_lines = len(lines)
        blank_lines = sum(1 for l in lines if not l.strip())
        code_lines = total_lines - blank_lines
        comment_lines = sum(1 for l in lines if l.strip().startswith(("//", "/*", "*")))

        simpler_func_re = re.compile(r'^(?:static\s+)?\w+(?:\s+\w+)*\s*\(')
        func_count = 0
        in_function = False
        brace_depth = 0
        func_start = 0
        func_sizes = []
        max_func_lines = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not in_function:
                if simpler_func_re.match(stripped) and stripped.endswith("("):
                    in_function = True
                    func_start = i
                    func_count += 1
                    continue
            if in_function:
                brace_depth += stripped.count("{")
                brace_depth -= stripped.count("}")
                if brace_depth <= 0:
                    fl = i - func_start + 1
                    func_sizes.append(fl)
                    max_func_lines = max(max_func_lines, fl)
                    in_function = False

        avg_func = round(sum(func_sizes) / max(func_count, 1), 1)

        malloc_count = len(re.findall(r'\bmalloc\s*\(', content))
        free_count = len(re.findall(r'\bfree\s*\(', content))

        file_metrics.append({
            "file": str(f.relative_to(source_dir)),
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
            "function_count": func_count,
            "avg_function_lines": avg_func,
            "max_function_lines": max_func_lines,
            "malloc_count": malloc_count,
            "free_count": free_count,
        })

    file_metrics.sort(key=lambda x: x["code_lines"], reverse=True)
    return file_metrics[:10]


def _detect_test_framework(source_dir: Path) -> str:
    """Detect which test framework is used."""
    checks = [
        ("Unity", [r'#include\s+["<]unity\.h[">]']),
        ("CMock", [r'#include\s+["<]cmock\.h[">]', r'mock\.h']),
        ("Google Test", [r'#include\s+[<"]gtest/gtest\.h[>"]']),
        ("pytest", [r'import\s+pytest', r'from\s+pytest\b']),
        ("unittest", [r'import\s+unittest', r'from\s+unittest\b']),
        ("CUnit", [r'#include\s+["<]CUnit/']),
        ("Catch2", [r'#include\s+[<"]catch2/catch\.hpp[>"]', r'#include\s+[<"]catch\.hpp[>"]']),
    ]

    for name, patterns in checks:
        for pat in patterns:
            if _find_matching_files(source_dir, pat):
                return name

    has_test_files = any(f.is_file() and "test" in f.stem.lower() for f in source_dir.rglob("*"))
    if has_test_files:
        return "unknown"
    return "none"
