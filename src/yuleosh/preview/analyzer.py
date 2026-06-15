#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
AI Preview Assessment — Code Analyzer (PREVIEW-REQ-004).

Performs static analysis on uploaded source code to determine:
  - Project structure and file types
  - Detected frameworks (FreeRTOS, Zephyr, AUTOSAR, etc.)
  - Code complexity metrics
  - Test infrastructure maturity
  - Compliance risk factors (MISRA, safety)
  - Pipeline config recommendation
"""

import os
import re
from pathlib import Path
from typing import Optional

# Supported file extensions for analysis (PREVIEW-REQ-002)
SUPPORTED_EXTENSIONS = {".c", ".h", ".py", ".yaml", ".yml", ".md",
                        ".cfg", ".cmake", ".txt", ".arxml", ".dts", ".ld"}


def analyze_directory(source_dir: str | Path) -> dict:
    """Analyze a source code directory and produce analysis data.

    Args:
        source_dir: Path to the extracted/cloned source code.

    Returns:
        dict with keys:
          - file_summary: total files, lines, by extension
          - detected_frameworks: list of detected frameworks
          - complexity: avg function length, cyclomatic indicators
          - test_infrastructure: test framework, test file ratio
          - compliance_risks: list of risk findings
          - recommended_template: suggested template name
    """
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    # ── File discovery ──────────────────────────────────────────────
    all_files = []
    source_files = []  # .c, .py, etc.
    header_files = []  # .h
    test_files = []
    config_files = []

    for f in source_dir.rglob("*"):
        if f.is_dir() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        all_files.append(f)

        # Categorize
        rel_path = str(f.relative_to(source_dir))

        if ext == ".h":
            header_files.append(rel_path)
        elif ext in (".c", ".py"):
            source_files.append(rel_path)
        elif ext in (".yaml", ".yml", ".cfg", ".cmake", ".txt", ".ld"):
            config_files.append(rel_path)

        # Test detection
        if "test" in f.stem.lower():
            test_files.append(rel_path)

    # ── Content scanning ────────────────────────────────────────────
    # Scan for framework headers and patterns
    framework_hits = _scan_frameworks(source_dir)
    complexity = _measure_complexity(source_dir)
    risk_findings = _scan_risks(source_dir, complexity)

    # ── Test metrics ────────────────────────────────────────────────
    test_framework = _detect_test_framework(source_dir)
    test_density = len(test_files) / max(len(source_files), 1)

    # ── Determine recommended template ──────────────────────────────
    recommended_template = _recommend_template(
        framework_hits, complexity, risk_findings
    )

    # ── Compute coverage prediction ────────────────────────────────
    coverage = _predict_coverage(
        test_density=test_density,
        test_framework=test_framework,
        complexity_score=complexity.get("avg_lines_per_function", 0),
    )

    result = {
        "file_summary": {
            "total_files": len(all_files),
            "source_files": len(source_files),
            "header_files": len(header_files),
            "test_files": len(test_files),
            "config_files": len(config_files),
            "total_lines": _count_total_lines(all_files),
            "by_extension": _count_by_extension(all_files),
        },
        "detected_frameworks": framework_hits,
        "complexity": complexity,
        "test_infrastructure": {
            "detected_framework": test_framework,
            "test_density": round(test_density, 3),
            "test_file_count": len(test_files),
        },
        "compliance_risks": risk_findings,
        "recommended_template": recommended_template,
        "coverage_prediction": coverage,
    }

    return result


# ── Helper functions ────────────────────────────────────────────────────


def _count_total_lines(files: list[Path]) -> int:
    total = 0
    for f in files:
        try:
            total += len(f.read_text().splitlines())
        except Exception:
            pass
    return total


def _count_by_extension(files: list[Path]) -> dict:
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1
    return counts


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
    }

    for name, patterns in checks.items():
        found_any = []
        for pat in patterns:
            for f in _find_matching_files(source_dir, pat):
                found_any.append(str(f.relative_to(source_dir)))
                break  # one per file, but keep searching for more matches

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


def _measure_complexity(source_dir: Path) -> dict:
    """Measure code complexity metrics."""
    total_functions = 0
    total_lines_in_functions = 0
    max_function_lines = 0
    function_lengths: list[int] = []

    # Scan .c files for function definitions
    func_re = re.compile(r'^\w+(?:\s+\w+)*\s+\w+\s*\([^)]*\)\s*\n?\{', re.MULTILINE)
    simpler_func_re = re.compile(r'^(?:static\s+)?\w+(?:\s+\w+)*\s*\(')

    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        brace_depth = 0
        in_function = False
        func_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()

            if not in_function:
                if simpler_func_re.match(stripped) and stripped.endswith("("):
                    # Check it's a function definition, not declaration
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

    return {
        "total_functions": total_functions,
        "total_function_lines": total_lines_in_functions,
        "avg_lines_per_function": avg_lpf,
        "max_function_lines": max_function_lines,
    }


def _detect_test_framework(source_dir: Path) -> str:
    """Detect which test framework is used."""
    checks = [
        ("Unity", [r'#include\s+["<]unity\.h[">]']),
        ("CMock", [r'#include\s+["<]cmock\.h[">]', r'mock\.h']),
        ("Google Test", [r'#include\s+[<"]gtest/gtest\.h[>"]']),
        ("pytest", [r'import\s+pytest', r'from\s+pytest\b']),
        ("unittest", [r'import\s+unittest', r'from\s+unittest\b']),
        ("CUnit", [r'#include\s+["<]CUnit/']),
    ]

    for name, patterns in checks:
        for pat in patterns:
            if _find_matching_files(source_dir, pat):
                return name

    # Check if there are test files at all
    has_test_files = False
    for f in source_dir.rglob("*"):
        if f.is_file() and "test" in f.stem.lower():
            has_test_files = True
            break

    if has_test_files:
        return "unknown"
    return "none"


def _scan_risks(source_dir: Path, complexity: dict) -> list[dict]:
    """Scan for compliance risk factors (PREVIEW-REQ-004.2)."""
    risks = []

    # 1. Dynamic memory allocation in embedded C
    malloc_count = 0
    free_count = 0
    new_count = 0

    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        malloc_count += len(re.findall(r'\bmalloc\s*\(', content))
        free_count += len(re.findall(r'\bfree\s*\(', content))
        new_count += len(re.findall(r'\bnew\s+', content))

    if malloc_count > 0:
        risk_level = "high" if malloc_count > 10 else "medium"
        risks.append({
            "risk_level": risk_level,
            "description": f"Dynamic memory allocation detected ({malloc_count} malloc/free calls). Not recommended for safety-critical embedded systems.",
            "occurrences": malloc_count + free_count,
            "recommendation": "Replace dynamic allocation with static pool allocation. Use pre-allocated buffers or memory pools.",
        })

    # 2. Recursion detection
    recursion_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        recursion_count += len(re.findall(r'(\w+)\s*\([^)]*\)\s*\n?\{[^}]*\1\s*\(', content, re.DOTALL))

    if recursion_count > 0:
        risks.append({
            "risk_level": "high" if recursion_count > 3 else "medium",
            "description": f"Recursive function calls detected ({recursion_count} instances). Recursion is not recommended for safety-critical embedded systems.",
            "occurrences": recursion_count,
            "recommendation": "Replace recursive algorithms with iterative equivalents. Ensure bounded recursion depth if unavoidable.",
        })

    # 3. Unbounded loops (while(1) / for(;;) with no break/return)
    unbounded_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        # Count while(1) / for (;;) patterns
        unbounded_count += len(re.findall(r'while\s*\(1\)', content))
        unbounded_count += len(re.findall(r'for\s*\(\s*;\s*;', content))

    if unbounded_count > 0:
        risks.append({
            "risk_level": "medium",
            "description": f"Unbounded loops detected ({unbounded_count} instances). Ensure loops have deterministic exit conditions for safety-critical contexts.",
            "occurrences": unbounded_count,
            "recommendation": "Add explicit exit conditions or timeout counters to all loops. For while(1), ensure watchdog refresh is present.",
        })

    # 4. Lack of assertions
    assert_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        assert_count += len(re.findall(r'\bassert\s*\(', content))

    if assert_count == 0:
        risks.append({
            "risk_level": "medium",
            "description": "No assertions found. Defensive programming practices are recommended.",
            "occurrences": 0,
            "recommendation": "Add assertions for preconditions, postconditions, and invariant checks.",
        })

    # 5. Function length
    if complexity.get("max_function_lines", 0) > 100:
        risks.append({
            "risk_level": "low",
            "description": f"Overly long functions found (max {complexity['max_function_lines']} lines). Long functions reduce readability and testability.",
            "occurrences": 1,
            "recommendation": "Refactor long functions into smaller units following the Single Responsibility Principle.",
        })

    # 6. Spec/evidence maturity
    has_specs = any(f.name == "spec.md" for f in source_dir.rglob("*") if f.is_file())
    has_trace = any("trace" in f.stem.lower() for f in source_dir.rglob("*") if f.is_file())

    if not has_specs:
        risks.append({
            "risk_level": "high",
            "description": "No OpenSpec specification file (spec.md) found. ASPICE compliance requires traceable requirements.",
            "occurrences": 0,
            "recommendation": "Create a spec.md file with SHALL statements following the yuleOSH OpenSpec format.",
        })

    if not has_trace:
        risks.append({
            "risk_level": "medium",
            "description": "No traceability matrix found. Evidence traceability is required for ASPICE compliance.",
            "occurrences": 0,
            "recommendation": "Generate a traceability matrix linking requirements to test cases.",
        })

    return risks


def _recommend_template(frameworks: list, complexity: dict, risks: list) -> dict:
    """Recommend a pipeline template based on analysis (PREVIEW-REQ-004.3)."""
    framework_names = [f["name"] for f in frameworks]

    # Determine best template match
    if "FreeRTOS" in framework_names:
        if any("MISRA" in str(r) for r in str(risks)):
            recommended = "freertos-misra"
        else:
            recommended = "freertos-misra"
    elif "Zephyr" in framework_names:
        recommended = "zephyr-rtos"
    elif "AUTOSAR" in framework_names:
        recommended = "autosar-classic"
    elif "STM32 HAL" in framework_names:
        if "FreeRTOS" in framework_names:
            recommended = "stm32-hal"
        else:
            recommended = "stm32-hal"
    elif "ESP-IDF" in framework_names:
        recommended = "esp32-idf"
    elif "ARM CMSIS" in framework_names:
        recommended = "arm-cmsis"
    else:
        recommended = "generic-embedded-c"

    # Build recommended steps
    steps = [
        {"name": "Spec Parsing", "rationale": "Parse and validate OpenSpec"},
        {"name": "Requirements Analysis", "rationale": "Analyze requirements and traceability"},
        {"name": "System Design Document", "rationale": "Generate architecture document"},
        {"name": "Code Generation", "rationale": "AI-assisted code generation"},
        {"name": "Internal Review", "rationale": "Quality gate before external review"},
        {"name": "Test Plan Generation", "rationale": "Generate test cases from spec"},
        {"name": "Code Review (4-Agent Matrix)", "rationale": "Multi-agent review for quality, security, style, safety"},
    ]

    # Adjust based on analysis
    if framework_names:
        steps.append({"name": "Cross-Compile + Static Analysis", "rationale": f"Target platform: {framework_names[0]}"})

    # Safety-critical: add extra gates
    has_dynamic_memory = any("Dynamic memory" in str(r) for r in risks)
    has_recursion = any("Recursive" in str(r) for r in risks)
    if has_dynamic_memory or has_recursion or complexity.get("max_function_lines", 0) > 100:
        steps.append({"name": "MISRA Static Analysis", "rationale": "Safety-critical: enforce MISRA-C rules"})
        steps.append({"name": "Safety Review", "rationale": "ISO 26262 compliance review"})

    steps.append({"name": "System Verification + Evidence Pack", "rationale": "Final verification and traceability evidence"})

    # Generate YAML snippet
    yaml_snippet = f"""# Recommended pipeline config for {recommended}
# Generated by yuleOSH AI Preview Assessment
steps:
"""
    for s in steps:
        yaml_snippet += f"""  - id: {s['name'].lower().replace(' ', '-')}
    name: {s['name']}
    handler: auto
"""
    yaml_snippet += """
ci_layers:
  L1:
    unit_test: true
    linter: true
  L2:
    cross_compile: true
    static_analysis: true
"""

    return {
        "recommended_template": recommended,
        "steps": steps,
        "ci_layers": {
            "L1": {"unit_test": True, "linter": True},
            "L2": {"cross_compile": True, "static_analysis": True},
        },
        "review_gates": [
            {"type": "internal", "before": "code-gen"},
            {"type": "compliance", "after": "system-verification"},
        ],
        "yaml_snippet": yaml_snippet,
    }


def _predict_coverage(test_density: float, test_framework: str,
                      complexity_score: float) -> dict:
    """Predict current and projected coverage (PREVIEW-REQ-004.1).

    Uses a simple heuristic model:
      coverage_estimate = f(test_density, code_complexity, test_maturity)
    """
    # Base estimate from test density
    if test_framework == "none":
        base = 5.0
        confidence = "low"
        maturity = 0.0
    elif test_framework == "unknown":
        base = 25.0
        confidence = "low"
        maturity = 1.0
    elif test_framework in ("Unity", "CUnit"):
        base = 40.0 + (test_density * 30.0)
        confidence = "medium"
        maturity = 2.0
    elif test_framework in ("CMock",):
        base = 50.0 + (test_density * 25.0)
        confidence = "medium"
        maturity = 2.5
    elif test_framework in ("Google Test", "pytest", "unittest"):
        base = 55.0 + (test_density * 25.0)
        confidence = "medium"
        maturity = 2.0
    else:
        base = 30.0
        confidence = "low"
        maturity = 1.0

    # Penalize complexity
    if complexity_score > 50:
        penalty = 10.0
    elif complexity_score > 30:
        penalty = 5.0
    else:
        penalty = 0.0

    current = max(0, min(100, round(base - penalty, 1)))

    # Projected coverage after yuleOSH
    projected = min(100, round(current + 30.0 + (maturity * 5.0), 1))

    # Bottleneck files (simulated — real analysis would use per-file results)
    bottleneck_files = []
    if current < 50:
        bottleneck_files.append("src/main.c (estimated < 30% coverage)")
    if current < 60:
        bottleneck_files.append("src/hal/gpio.c (estimated < 40% coverage)")

    return {
        "current_coverage_estimate": current,
        "projected_coverage_after_yuleosh": projected,
        "confidence": confidence,
        "bottleneck_files": bottleneck_files[:5],
    }
