#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 内存安全审查。

检查嵌入式项目内存使用情况：
- 全局变量总大小（对比 RAM 容量）
- 动态内存分配（malloc/free — 嵌入式应避免）
- static 变量递归风险
- 循环缓冲区边界安全
- 栈溢出防护
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_memory")

__all__ = ["step_review_memory"]

MemoryFinding = dict

# ── Source file discovery ────────────────────────────────────────────────


def _find_source_files(project_dir: Path) -> list[Path]:
    """Discover C / C++ / header / assembly source files."""
    patterns = ["**/*.c", "**/*.h", "**/*.cpp", "**/*.hpp", "**/*.s", "**/*.S"]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file() and not any(
                part.startswith(".") or part == "__pycache__"
                for part in p.relative_to(project_dir).parts
            ):
                found.append(p)
    return found


# ── Static checks ─────────────────────────────────────────────────────────


def _check_dynamic_allocation(source_files: list[Path], project_dir: Path) -> list[MemoryFinding]:
    """Detect malloc / calloc / realloc / free usage (embedded anti-pattern)."""
    findings = []
    malloc_files: dict[str, list[str]] = {}
    for f in source_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue
        # Look for standard alloc calls
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and #define/#include
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            if stripped.startswith("#define") or stripped.startswith("#include"):
                continue

            m = re.search(r"\b(malloc|calloc|realloc|free)\s*\(", stripped)
            if m:
                fn = m.group(1)
                rel = str(Path(f).relative_to(project_dir))
                if rel not in malloc_files:
                    malloc_files[rel] = []
                malloc_files[rel].append(f"  Line {i}: {stripped[:120]}")

    if malloc_files:
        details = "; ".join(f"{f}({len(lines)} calls)" for f, lines in malloc_files.items())
        findings.append({
            "severity": "major",
            "category": "dynamic_allocation",
            "file": str(project_dir),
            "message": (
                f"Dynamic memory allocation (malloc/calloc/realloc/free) detected in "
                f"{len(malloc_files)} file(s): {details} — "
                f"embedded systems should prefer static allocation to avoid heap fragmentation"
            ),
            "details": malloc_files,
        })
    else:
        findings.append({
            "severity": "info",
            "category": "dynamic_allocation",
            "file": str(project_dir),
            "message": "No dynamic memory allocation (malloc/free) detected — good embedded practice",
        })

    return findings


def _find_map_files(project_dir: Path) -> list[Path]:
    """Discover linker map files (compiler output) in the project tree."""
    patterns = ["**/*.map", "**/*.elf", "**/*.out"]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file() and not p.name.startswith("."):
                found.append(p)
    return found


def _analyze_map_file(map_path: Path) -> dict:
    """Extract section size info from a linker map file.

    Parses common map file formats (GNU ld, ARMCC) to extract
    .text / .data / .bss / .noinit section sizes.
    """
    result = {
        "text": 0,
        "data": 0,
        "bss": 0,
        "noinit": 0,
        "total_ram": 0,
        "source": str(map_path),
    }

    try:
        content = map_path.read_text(errors="replace")
    except OSError:
        return result

    # GNU ld map file format:
    # .text      0x08001000      0x1a34  ...
    # .data      0x20000000      0x0024  ...
    # .bss       0x20000024      0x0200  ...
    section_re = re.compile(
        r'^\s*\.(text|data|bss|noinit|sbss|sdata|bss\.*|noinit\.*)\s+'
        r'0x[0-9a-fA-F]+\s+'
        r'(0x[0-9a-fA-F]+|\d+)\s',
        re.MULTILINE
    )

    for m in section_re.finditer(content):
        sec_name = m.group(1).lower()
        size_str = m.group(2)
        try:
            size = int(size_str, 16) if 'x' in size_str.lower() else int(size_str)
        except ValueError:
            continue

        if sec_name == 'text':
            result['text'] += size
        elif sec_name in ('data', 'sdata'):
            result['data'] += size
        elif sec_name in ('bss', 'sbss', 'bss.*'):
            result['bss'] += size
        elif 'noinit' in sec_name:
            result['noinit'] += size

    # ARMCC scatter-loading map format:
    #   Execution Region ER_RW (Base: 0x20000000, Size: 0x00000024, ...)
    if result['data'] == 0 and result['bss'] == 0:
        armcc_re = re.compile(
            r'Execution Region\s+\w+\s+\(Base:\s+0x[0-9a-fA-F]+,\s+'
            r'Size:\s+(0x[0-9a-fA-F]+|\d+)',
            re.IGNORECASE
        )
        # This is approximate — ARMCC format varies
        total = 0
        for m in armcc_re.finditer(content):
            sz_str = m.group(1)
            try:
                sz = int(sz_str, 16) if 'x' in sz_str.lower() else int(sz_str)
            except ValueError:
                continue
            # Assume first matching region is RW (data+bss)
            if total == 0:
                result['data'] = sz  # approximate
            total += sz

    result['total_ram'] = result['data'] + result['bss'] + result['noinit']
    return result


def _check_global_variables(
    source_files: list[Path], project_dir: Path,
) -> list[MemoryFinding]:
    """Estimate total global variable size using source heuristics + map file analysis.

    Two-tier approach:
    1. Direct map file analysis (most accurate) — extracts .data + .bss + .noinit sizes
    2. Source-level heuristic fallback (catches ~20-30% when no map file available)
    """
    findings = []

    # ── Tier 1: Map file analysis ──
    map_files = _find_map_files(project_dir)
    map_result = None
    for mf in map_files:
        log.info(f"  Analyzing map file: {mf}")
        result = _analyze_map_file(mf)
        if result['total_ram'] > 0:
            map_result = result
            break

    if map_result and map_result['total_ram'] > 0:
        total_ram_used = map_result['total_ram']
        findings.append({
            "severity": "info",
            "category": "global_size",
            "file": str(project_dir),
            "message": (
                f"[Map file analysis] Global variable memory usage: "
                f".data={map_result['data']} bytes, "
                f".bss={map_result['bss']} bytes, "
                f".noinit={map_result['noinit']} bytes, "
                f"total RAM={total_ram_used} bytes ({total_ram_used / 1024:.1f} KB) "
                f"from {map_result['source']}"
            ),
            "details": map_result,
        })

        # Try to estimate RAM capacity from linker scripts
        linker_scripts = list(project_dir.glob("**/*.ld")) + list(project_dir.glob("**/*.lds"))
        ram_capacity = 0
        for ls in linker_scripts:
            try:
                ls_content = ls.read_text()
                ram_matches = re.finditer(
                    r"(?:RAM|SRAM|DTCM|CCM)\w*\s*:.*LENGTH\s*=\s*(0x[0-9a-fA-F]+|\d+)",
                    ls_content, re.IGNORECASE)
                for rm in ram_matches:
                    sz_str = rm.group(1)
                    try:
                        sz = int(sz_str, 16) if 'x' in sz_str.lower() else int(sz_str)
                        ram_capacity += sz
                    except ValueError:
                        pass
            except OSError:
                pass

        if ram_capacity > 0:
            usage_pct = (total_ram_used / ram_capacity) * 100
            if usage_pct > 90:
                findings.append({
                    "severity": "critical",
                    "category": "global_size",
                    "file": str(project_dir),
                    "message": (
                        f"Global variable RAM usage ({total_ram_used} bytes / {ram_capacity} bytes, "
                        f"{usage_pct:.1f}%) exceeds 90% of available RAM — "
                        f"high risk of stack/heap collision; consider reducing .bss/.data size"
                    ),
                })
            elif usage_pct > 70:
                findings.append({
                    "severity": "major",
                    "category": "global_size",
                    "file": str(project_dir),
                    "message": (
                        f"Global variable RAM usage ({total_ram_used} bytes / {ram_capacity} bytes, "
                        f"{usage_pct:.1f}%) exceeds 70% — may limit stack and heap space"
                    ),
                })
            else:
                findings.append({
                    "severity": "info",
                    "category": "global_size",
                    "file": str(project_dir),
                    "message": (
                        f"RAM capacity: {ram_capacity} bytes ({ram_capacity / 1024:.1f} KB), "
                        f"usage: {usage_pct:.1f}%"
                    ),
                })

        return findings

    # ── Tier 2: Source-level heuristic fallback ──
    # This is a best-effort pattern scan, not a linker-map analysis.
    total_global_size = 0
    large_vars: list[tuple[str, int, str, int]] = []  # (file, line, name, size)

    for f in source_files:
        if f.suffix not in (".c", ".cpp"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Match global or static variable definitions
            # Patterns: type name[size];  or  type name = value;
            m = re.search(
                r"(?:static\s+)?(?:const\s+)?"
                r"(?:unsigned\s+)?(?:signed\s+)?"
                r"(?:volatile\s+)?"
                r"(int|char|short|long|float|double|uint8_t|uint16_t|uint32_t|"
                r"uint64_t|int8_t|int16_t|int32_t|int64_t|size_t|"
                r"bool|BOOL|uint8|uint16|uint32)"
                r"\s+"
                r"(\w+)\s*"
                r"(?:\[(\d+)\])?\s*"
                r"(?:=\s*\{?\s*(\d+|0[xX][0-9a-fA-F]+)\s*\}?)?"
                r"\s*;",
                stripped,
            )
            if m:
                type_str = m.group(1)
                var_name = m.group(2)
                array_size = m.group(3)
                init_val = m.group(4)

                # Estimate size in bytes
                type_sizes = {
                    "int": 4, "char": 1, "short": 2, "long": 4, "float": 4, "double": 8,
                    "uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "uint64_t": 8,
                    "int8_t": 1, "int16_t": 2, "int32_t": 4, "int64_t": 8,
                    "size_t": 4, "bool": 1, "BOOL": 1, "uint8": 1, "uint16": 2, "uint32": 4,
                }
                base_size = type_sizes.get(type_str, 4)
                if array_size:
                    try:
                        total_var_size = base_size * int(array_size)
                    except ValueError:
                        total_var_size = base_size
                else:
                    total_var_size = base_size

                rel_path = str(Path(f).relative_to(project_dir))
                if total_var_size > 1024:
                    large_vars.append((rel_path, i, var_name, total_var_size))

                total_global_size += total_var_size

    findings.append({
        "severity": "info",
        "category": "global_size",
        "file": str(project_dir),
        "message": f"Estimated total global/static variable size: ~{total_global_size} bytes "
                   f"({total_global_size / 1024:.1f} KB)",
    })

    if large_vars:
        for file_path, line, name, sz in large_vars:
            findings.append({
                "severity": "minor",
                "category": "large_variable",
                "file": file_path,
                "message": f"Large global variable '{name}' (~{sz} bytes) at line {line} — "
                           f"consider if it can be allocated dynamically or in a specific section",
            })

    return findings


def _check_static_recursion(source_files: list[Path], project_dir: Path) -> list[MemoryFinding]:
    """Detect recursive functions that use static locals (risk of corruption)."""
    findings = []
    recursion_candidates: list[tuple[str, int, str]] = []

    for f in source_files:
        if f.suffix not in (".c", ".cpp"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel_path = str(Path(f).relative_to(project_dir))
        lines = content.split("\n")

        # Find function definitions with static locals
        in_function = False
        func_name = ""
        func_start = 0
        brace_depth = 0
        has_static_local = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect function start (heuristic)
            fn_match = re.match(
                r"(?:static\s+)?(?:\w+(?:\s*\*)?\s+)"  # return type
                r"(\w+)\s*\(",                           # function name
                stripped,
            )
            if fn_match and not in_function and not stripped.startswith("#"):
                # Function found
                if brace_depth == 0:
                    func_name = fn_match.group(1)
                    func_start = i
                    in_function = True
                    has_static_local = False

            if in_function:
                # Track braces
                for ch in stripped:
                    if ch == "{":
                        brace_depth += 1
                    elif ch == "}":
                        brace_depth -= 1

                # Check for static local
                if "static" in stripped:
                    has_static_local = True

                # Detect self-call
                if re.search(rf"\b{re.escape(func_name)}\s*\(", stripped):
                    if has_static_local:
                        recursion_candidates.append(
                            (rel_path, func_start + 1, func_name)
                        )

                # End of function
                if brace_depth <= 0:
                    in_function = False

    if recursion_candidates:
        for file_path, line, name in recursion_candidates:
            findings.append({
                "severity": "major",
                "category": "static_recursion",
                "file": file_path,
                "message": f"Recursive function '{name}' (line ~{line}) uses static local variables — "
                           f"static locals are shared across all recursion levels, "
                           f"leading to corruption on re-entry",
            })
    else:
        findings.append({
            "severity": "info",
            "category": "static_recursion",
            "file": str(project_dir),
            "message": "No recursive functions with static locals detected",
        })

    return findings


def _check_circular_buffers(source_files: list[Path], project_dir: Path) -> list[MemoryFinding]:
    """Check circular buffer / ring buffer implementations for boundary safety."""
    findings = []

    for f in source_files:
        if f.suffix not in (".c", ".cpp", ".h", ".hpp"):
            continue
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        rel_path = str(Path(f).relative_to(project_dir))
        lines = content.split("\n")

        # Look for ring buffer read/write patterns
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.search(r"\b(ring_buf|ringbuf|circular|cir_buf|rb_)\w*\s*(?:->|\.)\s*(?:head|tail|read|write|put|get)\s*(?:=|\(|\[)", stripped, re.IGNORECASE):
                findings.append({
                    "severity": "info",
                    "category": "circular_buffer",
                    "file": rel_path,
                    "message": f"Circular buffer operation at line {i}: '{stripped[:100]}' — "
                               f"verify boundary checks and wrap-around logic",
                })

            # Check for modulo overflow in buffer index
            if re.search(r"\(.*%+\s*\w+_SIZE|\(.*%+\s*\w+_LEN|\(.*%+\s*\w+_MAX", stripped):
                findings.append({
                    "severity": "info",
                    "category": "circular_buffer",
                    "file": rel_path,
                    "message": f"Potential buffer modulo operation at line {i}: "
                               f"'{stripped[:100]}' — verify SIZE is power-of-2 for bitwise-and optimization",
                })

        # Check for BOUNDS / SAFE / SIZE macro pattern
        for i, line in enumerate(lines, 1):
            if re.search(r"#define\s+\w*BOUND\w*|#define\s+\w*SAFE\w*|#define\s+\w*CLAMP\w*", line):
                findings.append({
                    "severity": "info",
                    "category": "bounds_checking",
                    "file": rel_path,
                    "message": f"Bounds/safety macro at line {i}: '{line.strip()[:100]}'",
                })

    return findings


def _check_stack_protection(source_files: list[Path], project_dir: Path) -> list[MemoryFinding]:
    """Check for stack canary / stack protection mechanisms."""
    findings = []

    total_files = len(source_files)
    canary_count = 0
    guard_count = 0
    for f in source_files:
        try:
            content = f.read_text(errors="replace")
        except OSError:
            continue

        if re.search(r"__stack_chk_guard|__stack_chk_fail|_cyg_stack_chk", content):
            canary_count += 1
        if re.search(r"MPU_Config|MPU_Init|arm_mpu|MPU_Region", content, re.IGNORECASE):
            guard_count += 1

    if canary_count > 0:
        findings.append({
            "severity": "info",
            "category": "stack_protection",
            "file": str(project_dir),
            "message": f"Stack canary / stack smashing protection found in {canary_count} file(s)",
        })
    else:
        findings.append({
            "severity": "minor",
            "category": "stack_protection",
            "file": str(project_dir),
            "message": "No stack canary (__stack_chk_guard) detected — "
                       "consider -fstack-protector for production builds",
        })

    if guard_count > 0:
        findings.append({
            "severity": "info",
            "category": "mpu_protection",
            "file": str(project_dir),
            "message": f"MPU configuration found in {guard_count} file(s) — hardware memory protection active",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "mpu_protection",
            "file": str(project_dir),
            "message": "No MPU configuration detected — consider MPU for isolation if applicable",
        })

    return findings


def _static_memory_review(project_dir: Path) -> list[MemoryFinding]:
    """Run all static memory safety checks."""
    all_findings: list[MemoryFinding] = []
    source_files = _find_source_files(project_dir)

    if not source_files:
        all_findings.append({
            "severity": "info",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No source files found in project tree",
        })
        return all_findings

    log.info(f"  Scanning {len(source_files)} source/header files for memory analysis")

    all_findings.extend(_check_dynamic_allocation(source_files, project_dir))
    all_findings.extend(_check_global_variables(source_files, project_dir))
    all_findings.extend(_check_static_recursion(source_files, project_dir))
    all_findings.extend(_check_circular_buffers(source_files, project_dir))
    all_findings.extend(_check_stack_protection(source_files, project_dir))

    return all_findings


def _build_memory_review_prompt(project_dir: Path) -> tuple[str, str]:
    """Build prompts for LLM-powered memory safety review."""
    # Collect a sample of source files for LLM review
    source_files = _find_source_files(project_dir)

    system_prompt = (
        "You are an embedded firmware expert reviewing memory safety.\n"
        "Analyze the provided source code samples for:\n"
        "1. Dynamic memory usage — are malloc/free necessary, or can they be replaced with static pools?\n"
        "2. Buffer overflow risks — sprintf/snprintf, memcpy, strcpy usage\n"
        "3. Pointer safety — NULL checks, dangling pointers, use-after-free\n"
        "4. Stack usage — deep call chains, large stack-allocated arrays\n"
        "5. Global variable safety — shared globals, lack of guards\n"
        "6. Critical sections — unprotected shared data access\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )

    # Sample up to 10 C files (trimmed to 2000 chars each) and up to 5 headers
    c_samples = [f for f in source_files if f.suffix == ".c"][:10]
    h_samples = [f for f in source_files if f.suffix == ".h"][:5]

    user_lines = ["## Source Code Samples\n"]
    for f in c_samples + h_samples:
        try:
            content = f.read_text(errors="replace")[:2000]
            rel = str(f.relative_to(project_dir))
            user_lines.append(f"### {rel}\n```c\n{content}\n```\n")
        except OSError:
            pass

    user_lines.append(
        "Review the code above for memory safety issues. "
        "Focus on embedded-specific concerns: no heap fragmentation, "
        "no unchecked buffer writes, static allocation preferred."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_memory(session: PipelineSession) -> str:
    """Step: 小克 — 内存安全审查。

    Analyzes the project source tree for memory safety issues:
    dynamic allocation, global variable sizing, recursion, buffer overflows.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  🧠 [小克] 内存安全审查开始...")
        log.info("Running memory safety review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static memory checks...")
        static_findings = _static_memory_review(project_dir)
        log.info(f"Static memory review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered memory review...")
        llm_review = ""
        try:
            system_prompt, user_prompt = _build_memory_review_prompt(project_dir)
            llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
            llm_review = llm_result["content"]
            usage = llm_result.get("usage", {})
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "review-memory", "usage": usage})
            log.info(f"LLM memory review: {usage.get('total_tokens', '?')} tokens")
        except Exception as e:
            log.warning(f"LLM memory review failed (non-fatal): {e}")
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
            "step": "review-memory",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "memory-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write memory review: {e}")
            raise PipelineStepError(f"Cannot write memory review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 内存安全审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Memory review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Memory review step failed: {e}")
        raise PipelineStepError(f"Memory review step failed: {e}")
