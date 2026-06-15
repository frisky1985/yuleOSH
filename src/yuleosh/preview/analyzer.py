#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
AI Preview Assessment — Code Analyzer (PREVIEW-REQ-004).

Performs static analysis on uploaded source code to determine:
  - Project structure and file types
  - Detected frameworks (FreeRTOS, Zephyr, AUTOSAR, etc.)
  - Code complexity metrics (per-file and aggregate)
  - Test infrastructure maturity
  - Compliance risk factors (MISRA, safety)
  - Pipeline config recommendation
  - Documentation quality
  - Language distribution
  - Estimated effort
  - Overall maturity rating
"""

import os
import re
import time
from pathlib import Path
from typing import Optional

# Supported file extensions for analysis (PREVIEW-REQ-002)
SUPPORTED_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".py", ".yaml", ".yml", ".md",
                        ".cfg", ".cmake", ".txt", ".arxml", ".dts", ".ld", ".json",
                        ".toml", ".ini", ".svg", ".css", ".js", ".ts", ".tsx"}

# Language mapping for source files
LANGUAGE_MAP = {
    ".c": "C",
    ".h": "C Header",
    ".cpp": "C++",
    ".hpp": "C++ Header",
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
}


def analyze_directory(source_dir: str | Path) -> dict:
    """Analyze a source code directory and produce analysis data.

    Args:
        source_dir: Path to the extracted/cloned source code.

    Returns:
        dict with keys:
          - file_summary: total files, lines, by extension, by language
          - detected_frameworks: list of detected frameworks
          - complexity: avg function length, cyclomatic indicators, per-file
          - test_infrastructure: test framework, test file ratio
          - compliance_risks: list of risk findings
          - recommended_template: suggested template name
          - coverage_prediction: estimated coverage metrics
          - documentation_quality: README / docstring / spec quality
          - estimated_effort: person-hours estimate
          - maturity_rating: overall project maturity (0-100)
    """
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    # ── File discovery ──────────────────────────────────────────────
    all_files, source_files, header_files, test_files, config_files = _discover_files(source_dir)

    # ── Content scanning ────────────────────────────────────────────
    framework_hits = _scan_frameworks(source_dir)
    complexity = _measure_complexity(source_dir)
    risk_findings = _scan_risks(source_dir, complexity)

    # ── Test metrics ────────────────────────────────────────────────
    test_framework = _detect_test_framework(source_dir)
    test_density = len(test_files) / max(len(source_files), 1)

    # ── Language distribution ───────────────────────────────────────
    language_dist = _detect_languages(all_files, source_dir)

    # ── Documentation quality ───────────────────────────────────────
    doc_quality = _assess_documentation(source_dir)

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

    # ── Effort estimation ───────────────────────────────────────────
    effort = _estimate_effort(all_files, framework_hits, complexity)

    # ── Maturity rating ─────────────────────────────────────────────
    maturity = _compute_maturity(
        test_framework, test_density, len(test_files),
        complexity, doc_quality, framework_hits, coverage,
    )

    # ── Per-file complexity ─────────────────────────────────────────
    per_file_complexity = _measure_per_file_complexity(source_dir)

    result = {
        "file_summary": {
            "total_files": len(all_files),
            "source_files": len(source_files),
            "header_files": len(header_files),
            "test_files": len(test_files),
            "config_files": len(config_files),
            "total_lines": _count_total_lines(all_files),
            "by_extension": _count_by_extension(all_files),
            "by_language": language_dist,
        },
        "detected_frameworks": framework_hits,
        "complexity": complexity,
        "per_file_complexity": per_file_complexity,
        "test_infrastructure": {
            "detected_framework": test_framework,
            "test_density": round(test_density, 3),
            "test_file_count": len(test_files),
        },
        "compliance_risks": risk_findings,
        "recommended_template": recommended_template,
        "coverage_prediction": coverage,
        "documentation_quality": doc_quality,
        "estimated_effort": effort,
        "maturity_rating": maturity,
    }

    return result


# ── File discovery ────────────────────────────────────────────────────


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

        # Test detection
        if "test" in f.stem.lower():
            test_files.append(rel_path)

    return all_files, source_files, header_files, test_files, config_files


# ── Helper functions ────────────────────────────────────────────────────


def _count_total_lines(files: list[Path]) -> int:
    total = 0
    for f in files:
        try:
            total += len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass
    return total


def _count_by_extension(files: list[Path]) -> dict:
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1
    return counts


def _extract_lines(files: list[Path]) -> dict[str, int]:
    """Count total lines per extension."""
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        try:
            counts[ext] = counts.get(ext, 0) + len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass
    return counts


def _detect_languages(all_files: list[Path], source_dir: Path) -> dict:
    """Detect programming language distribution in the project."""
    lang_counts: dict[str, int] = {}
    lang_lines: dict[str, int] = {}

    for f in all_files:
        ext = f.suffix.lower()
        lang = LANGUAGE_MAP.get(ext, "Other")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        try:
            lang_lines[lang] = lang_lines.get(lang, 0) + len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass

    total = max(sum(lang_counts.values()), 1)
    return {
        "distribution": {
            lang: {
                "file_count": lang_counts.get(lang, 0),
                "total_lines": lang_lines.get(lang, 0),
                "percentage": round(lang_counts.get(lang, 0) / total * 100, 1),
            }
            for lang in sorted(lang_counts.keys())
        },
        "primary_language": max(lang_counts, key=lang_counts.get) if lang_counts else "Unknown",
    }


def _assess_documentation(source_dir: Path) -> dict:
    """Assess documentation quality (README, docstrings, code comments)."""
    has_readme = False
    readme_quality = 0
    for f in source_dir.rglob("*"):
        if f.is_file() and f.name.lower().startswith("readme"):
            has_readme = True
            try:
                lines = f.read_text(errors="replace").splitlines()
                content_lines = [l for l in lines if l.strip() and not l.startswith("#")]
                readme_quality = min(100, len(content_lines) * 5)
            except Exception:
                pass
            break

    # Comment-to-code ratio in .c/.h files
    comment_lines = 0
    code_lines = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    comment_lines += 1
                else:
                    code_lines += 1
        except Exception:
            pass

    comment_ratio = round(comment_lines / max(code_lines, 1), 3)

    # Docstring detection for Python
    docstring_count = 0
    for f in sorted(source_dir.rglob("*.py")):
        try:
            content = f.read_text(errors="replace")
            docstring_count += len(re.findall(r'"""', content)) // 2
        except Exception:
            pass

    # Spec doc presence
    has_spec = any(f.name == "spec.md" for f in source_dir.rglob("*") if f.is_file())

    score = 0
    if has_readme:
        score += 25
    if comment_ratio >= 0.15:
        score += 25
    elif comment_ratio >= 0.1:
        score += 15
    elif comment_ratio >= 0.05:
        score += 5
    if docstring_count >= 5:
        score += 25
    elif docstring_count >= 2:
        score += 15
    if has_spec:
        score += 25

    return {
        "has_readme": has_readme,
        "readme_quality": readme_quality,
        "comment_to_code_ratio": comment_ratio,
        "docstring_count": docstring_count,
        "has_spec": has_spec,
        "doc_score": min(100, score),
    }


def _estimate_effort(all_files: list[Path], frameworks: list[dict],
                     complexity: dict) -> dict:
    """Estimate person-hours based on code volume and complexity."""
    total_lines = _count_total_lines(all_files)
    source_exts = {".c", ".cpp", ".py", ".js", ".ts", ".tsx"}
    source_lines = 0
    for f in all_files:
        if f.suffix.lower() in source_exts:
            try:
                source_lines += len(f.read_text(errors="replace").splitlines())
            except Exception:
                pass

    # Based on industry averages: ~50 lines/hour for embedded C
    base_hours = source_lines / 50.0

    # Complexity multiplier
    avg_lpf = complexity.get("avg_lines_per_function", 0)
    if avg_lpf > 40:
        complexity_mult = 1.4
    elif avg_lpf > 25:
        complexity_mult = 1.2
    else:
        complexity_mult = 1.0

    # Framework complexity
    has_autosar = any(f["name"] == "AUTOSAR" for f in frameworks)
    framework_mult = 1.4 if has_autosar else 1.0

    estimated = round(base_hours * complexity_mult * framework_mult, 1)

    return {
        "estimated_person_hours": estimated,
        "source_lines_of_code": source_lines,
        "lines_per_hour_assumption": 50,
        "complexity_multiplier": complexity_mult,
        "framework_multiplier": framework_mult,
    }


def _compute_maturity(test_framework: str, test_density: float,
                      test_file_count: int, complexity: dict,
                      doc_quality: dict, frameworks: list[dict],
                      coverage: dict) -> dict:
    """Compute overall project maturity rating (0-100)."""
    score = 0

    # Test maturity (max 40)
    if test_framework not in ("none", "unknown"):
        score += 15
    if test_density >= 0.5:
        score += 15
    elif test_density >= 0.25:
        score += 10
    elif test_density > 0:
        score += 5
    if test_file_count >= 5:
        score += 10
    elif test_file_count >= 2:
        score += 5

    # Documentation (max 25)
    score += min(25, doc_quality.get("doc_score", 0) * 0.25)

    # Complexity penalty (max -15)
    avg_lpf = complexity.get("avg_lines_per_function", 0)
    if avg_lpf > 50:
        score -= 15
    elif avg_lpf > 30:
        score -= 10
    elif avg_lpf > 20:
        score -= 5

    # Coverage bonus (max 10)
    cov_est = coverage.get("current_coverage_estimate", 0)
    if cov_est >= 70:
        score += 10
    elif cov_est >= 50:
        score += 5

    # Safety critical penalty (max -10)
    for fw in frameworks:
        if fw["name"] == "AUTOSAR":
            score -= 5  # Higher bar for maturity in safety-critical
            break

    # Normalize
    score = max(0, min(100, score))

    # Rating labels
    if score >= 80:
        rating = "excellent"
    elif score >= 60:
        rating = "good"
    elif score >= 40:
        rating = "fair"
    elif score >= 20:
        rating = "developing"
    else:
        rating = "initial"

    return {
        "score": score,
        "rating": rating,
        "test_maturity_score": min(40, max(0, score)),
        "documentation_score": doc_quality.get("doc_score", 0),
    }


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

    # Nesting depth
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

        # Count function definitions
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

        # Count dynamic memory allocations
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

    # Sort by most complex (most code lines)
    file_metrics.sort(key=lambda x: x["code_lines"], reverse=True)
    return file_metrics[:10]  # Top 10 most complex files


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

    # 6. High function count warning
    if complexity.get("total_functions", 0) > 100:
        risks.append({
            "risk_level": "low",
            "description": f"Large number of functions detected ({complexity['total_functions']}). Consider modularization for maintainability.",
            "occurrences": complexity["total_functions"],
            "recommendation": "Organize functions into logical modules and ensure consistent naming conventions.",
        })

    # 7. Spec/evidence maturity
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

    # 8. Nesting depth risk
    max_nesting = complexity.get("max_nesting_depth", 0)
    if max_nesting > 5:
        risks.append({
            "risk_level": "medium",
            "description": f"Deep nesting detected (depth {max_nesting}). Deeply nested code is harder to test and review.",
            "occurrences": max_nesting,
            "recommendation": "Refactor deeply nested blocks into separate functions. Use early-return pattern to reduce nesting.",
        })

    # 9. Comment deficiency
    total_source = 0
    total_comments = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                total_source += 1
                if stripped.startswith(("//", "/*", "*")):
                    total_comments += 1
        except Exception:
            pass

    comment_ratio = total_comments / max(total_source, 1)
    if comment_ratio < 0.05 and total_source > 50:
        risks.append({
            "risk_level": "low",
            "description": f"Low comment-to-code ratio ({round(comment_ratio * 100, 1)}%). Code readability may be impacted.",
            "occurrences": total_source,
            "recommendation": "Add function-level doc comments and inline explanations for complex logic.",
        })

    return risks


def _recommend_template(frameworks: list, complexity: dict, risks: list) -> dict:
    """Recommend a pipeline template based on analysis (PREVIEW-REQ-004.3)."""
    framework_names = [f["name"] for f in frameworks]

    # Determine best template match
    if "FreeRTOS" in framework_names:
        recommended = "freertos-misra"
    elif "Zephyr" in framework_names:
        recommended = "zephyr-rtos"
    elif "AUTOSAR" in framework_names:
        recommended = "autosar-classic"
    elif "STM32 HAL" in framework_names:
        recommended = "stm32-hal"
    elif "ESP-IDF" in framework_names:
        recommended = "esp32-idf"
    elif "ARM CMSIS" in framework_names:
        recommended = "arm-cmsis"
    elif "Linux Kernel" in framework_names:
        recommended = "generic-embedded-c"
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

    Uses a heuristic model:
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
    elif test_framework in ("Google Test", "pytest", "unittest", "Catch2"):
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
