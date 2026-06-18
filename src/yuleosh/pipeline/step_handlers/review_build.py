#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 编译输出验证。

检查项:
- map 文件 .text/.data/.bss 段大小 vs 芯片规格
- 二进制大小增长趋势
- 函数/变量地址对齐
- 未使用的段/符号
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_build")

__all__ = ["step_review_build"]

BuildFinding = dict


# ── Discovery ─────────────────────────────────────────────────────────────


def _find_map_file(project_dir: Path) -> Path | None:
    """Find the linker map file (.map) in the build output directory."""
    for pat in ["**/*.map", "build/**/*.map", "build/**/*.map.txt",
                "out/**/*.map", "_build/**/*.map"]:
        candidates = list(project_dir.glob(pat))
        if candidates:
            # Pick the largest .map file (usually the most complete)
            return max(candidates, key=lambda p: p.stat().st_size)
    return None


def _find_binary_files(project_dir: Path) -> dict[str, list[Path]]:
    """Discover compiled binary output files."""
    result: dict[str, list[Path]] = {
        "elf": [],
        "hex": [],
        "bin": [],
        "lst": [],
    }
    for pat, key in [("**/*.elf", "elf"), ("**/*.hex", "hex"),
                      ("**/*.bin", "bin"), ("**/*.lst", "lst")]:
        for p in project_dir.glob(pat):
            if p.is_file():
                result[key].append(p)
    return result


# ── Map file parser ───────────────────────────────────────────────────────


def _parse_map_file(path: Path) -> dict:
    """Parse a GNU ld map file into structured sections data."""
    parsed = {
        "memory_config": {},
        "sections": {},
        "symbols": [],
        "discarded_input_sections": [],
        "load_region_summary": [],
    }

    try:
        content = path.read_text(errors="replace")
    except OSError as e:
        log.warning(f"Cannot read map file {path}: {e}")
        return parsed

    lines = content.splitlines()
    current_section = None

    # Track section boundaries
    in_memory_config = False
    in_sections = False
    in_discarded = False
    in_symbol_table = False
    in_load_region = False

    section_re = re.compile(
        r'^\s*\.(\w+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)')
    symbol_re = re.compile(
        r'^\s+0x([0-9a-fA-F]+)\s+(\w+)\s+(.+)$')
    memory_re = re.compile(
        r'^(\w+(?:\s*\(\w*\))?)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)')
    load_region_re = re.compile(
        r'^\s*(LOAD|ROM|RAM)\s+\w+\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)')

    for line in lines:
        stripped = line.strip()

        # Detect sections
        if stripped == "Memory Configuration":
            in_memory_config = True
            in_sections = False
            in_discarded = False
            in_symbol_table = False
            in_load_region = False
            continue
        elif stripped == "Linker script and memory map":
            in_memory_config = False
            in_sections = True
            in_discarded = False
            in_symbol_table = False
            in_load_region = False
            continue
        elif stripped.startswith("Discarded input sections"):
            in_memory_config = False
            in_sections = False
            in_discarded = True
            in_symbol_table = False
            in_load_region = False
            continue
        elif stripped.startswith("Symbol Table"):
            in_memory_config = False
            in_sections = False
            in_discarded = False
            in_symbol_table = True
            in_load_region = False
            continue

        # Parse memory configuration
        if in_memory_config:
            m = memory_re.match(stripped)
            if m:
                name = m.group(1).strip()
                origin = int(m.group(2), 16)
                length = int(m.group(3), 16)
                parsed["memory_config"][name] = {"origin": origin, "length": length}

        # Parse section entries
        if in_sections:
            m = section_re.match(stripped)
            if m:
                sec_name = m.group(1)
                addr = int(m.group(2), 16)
                size = int(m.group(3), 16)
                parsed["sections"][sec_name] = {"address": addr, "size": size}

        # Parse load region summary
        if in_sections:
            m = load_region_re.match(stripped)
            if m:
                parsed["load_region_summary"].append({
                    "type": m.group(1),
                    "address": int(m.group(2), 16),
                    "size": int(m.group(3), 16),
                })

        # Collect discarded input sections
        if in_discarded and stripped:
            parsed["discarded_input_sections"].append(stripped)

        # Collect symbol entries
        if in_symbol_table:
            m = symbol_re.match(stripped)
            if m:
                parsed["symbols"].append({
                    "address": int(m.group(1), 16),
                    "type": m.group(2),
                    "name": m.group(3).strip(),
                })

    return parsed


# ── Size parsing (arm-none-eabi-size / gcc size output) ───────────────────


def _parse_size_output(project_dir: Path) -> dict | None:
    """Try to run arm-none-eabi-size or read a size output file."""
    paths_to_try = [
        project_dir / "build" / "*.elf",
        project_dir / "out" / "*.elf",
    ]
    for pat_path in paths_to_try:
        for elf in sorted(project_dir.glob(str(pat_path.relative_to(project_dir)))):
            try:
                import subprocess
                result = subprocess.run(
                    ["arm-none-eabi-size", str(elf)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().splitlines()
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        if len(parts) >= 4:
                            return {
                                "text": int(parts[0]),
                                "data": int(parts[1]),
                                "bss": int(parts[2]),
                                "total_rom": int(parts[0]) + int(parts[1]),
                                "total_ram": int(parts[1]) + int(parts[2]),
                                "source": "arm-none-eabi-size",
                            }
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                continue

    # Fallback: try to read a size report file
    for pat in ["build/**/*.size", "build/**/size*.txt",
                "out/**/*.size", "_build/**/size*.txt"]:
        for p in project_dir.glob(pat):
            try:
                content = p.read_text()
                m = re.search(r'(\d+)\s+(\d+)\s+(\d+)', content)
                if m:
                    return {
                        "text": int(m.group(1)),
                        "data": int(m.group(2)),
                        "bss": int(m.group(3)),
                        "total_rom": int(m.group(1)) + int(m.group(2)),
                        "total_ram": int(m.group(2)) + int(m.group(3)),
                        "source": "size_report_file",
                    }
            except OSError:
                continue

    return None


# ── Static checks ─────────────────────────────────────────────────────────


def _check_section_sizes(parsed: dict, project_dir: Path) -> list[BuildFinding]:
    """Check section sizes against available memory."""
    findings = []

    # Get section sizes from map file
    sections = parsed.get("sections", {})
    memory = parsed.get("memory_config", {})

    # Known flash regions
    flash_names = ["FLASH", "ROM", "EROM", "BANK1", "BANK2"]
    ram_names = ["RAM", "SRAM", "DRAM", "CCM", "DTCM", "ITCM"]

    flash_total = 0
    ram_total = 0

    for name, cfg in memory.items():
        name_upper = name.upper()
        # Strip attribute parens like "FLASH (rx)"
        clean_name = re.sub(r'\s*\(.*?\)', '', name_upper).strip()
        if clean_name in [r.upper() for r in flash_names]:
            flash_total = cfg["length"]
        elif any(r in clean_name for r in ram_names):
            if cfg["length"] > ram_total:
                ram_total = cfg["length"]

    # Calculate ROM usage: .text + .rodata + .data (init values)
    rom_used = 0
    for sec in [".text", ".rodata", ".data"]:
        if sec in sections:
            rom_used += sections[sec]["size"]

    # Calculate RAM usage: .data + .bss + .noinit + .heap + .stack
    ram_used = 0
    for sec in [".data", ".bss", ".noinit", ".heap", ".stack"]:
        if sec in sections:
            ram_used += sections[sec]["size"]

    if flash_total > 0:
        pct = (rom_used / flash_total) * 100
        findings.append({
            "severity": "info",
            "category": "section_size",
            "file": "(map)",
            "message": f"ROM usage: {rom_used} / {flash_total} bytes ({pct:.1f}%)",
        })
        if pct > 90:
            findings.append({
                "severity": "major",
                "category": "section_size",
                "file": "(map)",
                "message": f"ROM usage ({pct:.1f}%) exceeds 90% — risk of out-of-flash on firmware update",
            })
        elif pct > 95:
            findings.append({
                "severity": "critical",
                "category": "section_size",
                "file": "(map)",
                "message": f"ROM usage ({pct:.1f}%) exceeds 95% — linker will likely fail",
            })
    else:
        # Try to infer from sections
        for sec_name in [".text", ".rodata"]:
            if sec_name in sections:
                findings.append({
                    "severity": "info",
                    "category": "section_size",
                    "file": "(map)",
                    "message": f"{sec_name}: {sections[sec_name]['size']} bytes "
                               f"@ 0x{sections[sec_name]['address']:08X}",
                })

    if ram_total > 0:
        pct = (ram_used / ram_total) * 100
        findings.append({
            "severity": "info",
            "category": "section_size",
            "file": "(map)",
            "message": f"RAM usage: {ram_used} / {ram_total} bytes ({pct:.1f}%)",
        })
        if pct > 90:
            findings.append({
                "severity": "major",
                "category": "section_size",
                "file": "(map)",
                "message": f"RAM usage ({pct:.1f}%) exceeds 90% — risk of stack/heap overflow",
            })
        elif pct > 95:
            findings.append({
                "severity": "critical",
                "category": "section_size",
                "file": "(map)",
                "message": f"RAM usage ({pct:.1f}%) exceeds 95% — critical risk of memory exhaustion",
            })
    else:
        for sec_name in [".data", ".bss"]:
            if sec_name in sections:
                findings.append({
                    "severity": "info",
                    "category": "section_size",
                    "file": "(map)",
                    "message": f"{sec_name}: {sections[sec_name]['size']} bytes "
                               f"@ 0x{sections[sec_name]['address']:08X}",
                })

    return findings


def _check_address_alignment(parsed: dict) -> list[BuildFinding]:
    """Check function/variable address alignment in the map file."""
    findings = []
    symbols = parsed.get("symbols", [])
    if not symbols:
        return findings

    # Check vector table alignment (should be 256-byte aligned for Cortex-M)
    vector_symbols = [s for s in symbols if "Vectors" in s["name"] or "vector" in s["name"].lower()]
    for s in vector_symbols:
        if s["address"] % 256 != 0:
            findings.append({
                "severity": "major",
                "category": "alignment",
                "file": "(map)",
                "message": f"Vector table '{s['name']}' at 0x{s['address']:08X} is not "
                           f"256-byte aligned — may cause hard fault on Cortex-M",
            })

    # Check main entry points
    entry_symbols = [s for s in symbols if s["name"] in (
        "Reset_Handler", "main", "SystemInit", "__main")]
    for s in entry_symbols:
        if s["address"] % 4 != 0:
            findings.append({
                "severity": "major",
                "category": "alignment",
                "file": "(map)",
                "message": f"Entry point '{s['name']}' at 0x{s['address']:08X} is not "
                           f"4-byte aligned — may cause alignment fault",
            })

    # Check ISR handlers for alignment
    isr_symbols = [s for s in symbols if "_IRQHandler" in s["name"] or "_Handler" in s["name"]]
    misaligned_isrs = [s for s in isr_symbols if s["address"] % 4 != 0]
    if misaligned_isrs:
        names = ", ".join(s["name"] for s in misaligned_isrs[:5])
        findings.append({
            "severity": "minor",
            "category": "alignment",
            "file": "(map)",
            "message": f"{len(misaligned_isrs)} ISR handlers not 4-byte aligned: {names}",
        })

    # Check for DMA buffer alignment (should be 16 or 32 byte aligned)
    dma_buffers = [s for s in symbols if "DMA" in s["name"] and "Buf" in s["name"]]
    misaligned_dma = [s for s in dma_buffers if s["address"] % 16 != 0]
    if misaligned_dma:
        for s in misaligned_dma[:3]:
            findings.append({
                "severity": "minor",
                "category": "alignment",
                "file": "(map)",
                "message": f"DMA buffer '{s['name']}' at 0x{s['address']:08X} "
                           f"not 16-byte aligned — may cause DMA alignment issues",
            })

    return findings


def _check_unused_sections(parsed: dict) -> list[BuildFinding]:
    """Check for unused/discarded sections and orphan sections."""
    findings = []
    sections = parsed.get("sections", {})

    # Known sections that should always be present in an embedded binary
    required_sections = [".text", ".data", ".bss"]
    for sec in required_sections:
        if sec not in sections:
            findings.append({
                "severity": "critical" if sec in (".text",) else "major",
                "category": "unused_sections",
                "file": "(map)",
                "message": f"Required section '{sec}' not found in map file — "
                           f"build may be incomplete or corrupt",
            })

    # Check for orphan sections (known but not present)
    orphan_candidates = [".rodata", ".noinit", ".ARM.exidx",
                         ".init_array", ".fini_array",
                         ".heap", ".stack"]

    # Check for discarding startup sections
    discarded = parsed.get("discarded_input_sections", [])
    startup_discards = [d for d in discarded if "startup" in d.lower()
                        or "crt" in d.lower()]
    if startup_discards:
        findings.append({
            "severity": "major",
            "category": "unused_sections",
            "file": "(map)",
            "message": f"{len(startup_discards)} startup object(s) discarded "
                       f"— system may not boot correctly. First: {startup_discards[0]}",
        })

    # Check for .debug sections (should be stripped for release builds)
    debug_sections = {name for name in sections
                      if name.startswith("debug") or "_debug_" in name}
    if debug_sections:
        findings.append({
            "severity": "info",
            "category": "unused_sections",
            "file": "(map)",
            "message": f"{len(debug_sections)} debug section(s) present in "
                       f"output — will increase binary size",
        })

    # Check for common .comment / .note sections
    overhead_sections = {name for name in sections
                         if name in (".comment", ".note", ".note.gnu.*",
                                     ".note.GNU-stack")}
    if overhead_sections:
        findings.append({
            "severity": "info",
            "category": "unused_sections",
            "file": "(map)",
            "message": f"Overhead sections present: {', '.join(sorted(overhead_sections))}",
        })

    # Check .rodata size (potential for string literal bloat)
    if ".rodata" in sections:
        rodata_size = sections[".rodata"]["size"]
        if rodata_size > 50000:
            findings.append({
                "severity": "minor",
                "category": "unused_sections",
                "file": "(map)",
                "message": f".rodata section is large ({rodata_size} bytes) — "
                           f"check for embedded strings, logs, or large const tables",
            })

    return findings


def _check_binary_sizes(project_dir: Path) -> list[BuildFinding]:
    """Check compiled binary file sizes."""
    findings = []
    binaries = _find_binary_files(project_dir)

    # Check ELF size
    for f in binaries.get("elf", []):
        size_bytes = f.stat().st_size
        if size_bytes > 1024 * 1024:  # 1 MB
            findings.append({
                "severity": "major",
                "category": "binary_size",
                "file": str(f),
                "message": f"ELF binary is {size_bytes / 1024:.1f} KB — "
                           f"verify target flash capacity",
            })

    # Check BIN size (stripped, usually closest to actual flash usage)
    for f in binaries.get("bin", []):
        size_bytes = f.stat().st_size
        findings.append({
            "severity": "info",
            "category": "binary_size",
            "file": str(f),
            "message": f"BIN size: {size_bytes} bytes ({size_bytes / 1024:.1f} KB)",
        })

    # Check HEX size
    for f in binaries.get("hex", []):
        size_bytes = f.stat().st_size
        findings.append({
            "severity": "info",
            "category": "binary_size",
            "file": str(f),
            "message": f"HEX size: {size_bytes} bytes ({size_bytes / 1024:.1f} KB)",
        })

    # Check listing size (assembly listing)
    for f in binaries.get("lst", []):
        findings.append({
            "severity": "info",
            "category": "binary_size",
            "file": str(f),
            "message": f"Listing file: {f.name} ({f.stat().st_size / 1024:.1f} KB)",
        })

    return findings


def _check_size_trend(parsed: dict, project_dir: Path) -> list[BuildFinding]:
    """Compare current sizes against a historical baseline if available."""
    findings = []
    baseline_path = project_dir / ".build-size-baseline.json"

    if not baseline_path.exists():
        # Create baseline for future comparisons
        try:
            size_data = _parse_size_output(project_dir)
            if size_data:
                with open(baseline_path, "w") as f:
                    json.dump({
                        "baseline": size_data,
                        "timestamp": datetime.now().isoformat(),
                    }, f, indent=2)
                findings.append({
                    "severity": "info",
                    "category": "size_trend",
                    "file": str(baseline_path),
                    "message": f"Created size baseline: text={size_data.get('text', '?')}, "
                               f"data={size_data.get('data', '?')}, bss={size_data.get('bss', '?')}",
                })
        except OSError:
            pass
        return findings

    # Compare against baseline
    try:
        baseline = json.loads(baseline_path.read_text())
        current = _parse_size_output(project_dir)
        if current and "baseline" in baseline:
            prev = baseline["baseline"]
            for sect in ["text", "data", "bss"]:
                prev_val = prev.get(sect, 0)
                curr_val = current.get(sect, 0)
                diff = curr_val - prev_val
                if diff > 1024:
                    findings.append({
                        "severity": "minor",
                        "category": "size_trend",
                        "file": str(baseline_path),
                        "message": f".{sect} size increased by {diff} bytes "
                                   f"({prev_val} → {curr_val}) — verify new code is expected",
                    })
                elif diff > 0:
                    findings.append({
                        "severity": "info",
                        "category": "size_trend",
                        "file": str(baseline_path),
                        "message": f".{sect} size increased by {diff} bytes "
                                   f"({prev_val} → {curr_val})",
                    })
                elif diff < 0:
                    findings.append({
                        "severity": "info",
                        "category": "size_trend",
                        "file": str(baseline_path),
                        "message": f".{sect} size decreased by {abs(diff)} bytes "
                                   f"({prev_val} → {curr_val})",
                    })
    except (OSError, json.JSONDecodeError) as e:
        log.warning(f"Cannot read size baseline: {e}")

    return findings


def _check_unused_symbols(parsed: dict) -> list[BuildFinding]:
    """Check for unused or redundant symbols."""
    findings = []
    symbols = parsed.get("symbols", [])

    if not symbols:
        return findings

    # Count symbols by type
    type_counts: dict[str, int] = {}
    for s in symbols:
        t = s["type"].upper()
        type_counts[t] = type_counts.get(t, 0) + 1

    allowed_types = {"T", "t", "D", "d", "B", "b", "C", "c", "A", "a",
                     "U", "u", "W", "w", "V", "v"}
    unusual_types = set(s["type"] for s in symbols) - allowed_types
    if unusual_types:
        findings.append({
            "severity": "info",
            "category": "symbols",
            "file": "(map)",
            "message": f"Unusual symbol types: {', '.join(sorted(unusual_types))}",
        })

    # Check for weak symbols (may indicate missing implementations)
    weak_symbols = [s for s in symbols if s["type"] in ("V", "v", "W", "w")]
    if weak_symbols:
        findings.append({
            "severity": "info",
            "category": "symbols",
            "file": "(map)",
            "message": f"{len(weak_symbols)} weak symbol(s) — may indicate "
                       f"unimplemented functions (potential runtime issues)",
        })

    # Check for undefined references
    undefined = [s for s in symbols if s["type"] in ("U", "u")]
    if undefined:
        udef_names = [s["name"] for s in undefined[:10]]
        findings.append({
            "severity": "major",
            "category": "symbols",
            "file": "(map)",
            "message": f"{len(undefined)} undefined reference(s): "
                       f"{', '.join(udef_names[:5])}{'...' if len(udef_names) > 5 else ''} "
                       f"— linker will fail",
        })

    # Summary
    if symbols:
        findings.append({
            "severity": "info",
            "category": "symbols",
            "file": "(map)",
            "message": f"Total symbols: {len(symbols)} "
                       f"(T={type_counts.get('T', 0)}, "
                       f"D={type_counts.get('D', 0)}, "
                       f"B={type_counts.get('B', 0)}, "
                       f"U={type_counts.get('U', 0)})",
        })

    return findings


# ── Main static review ────────────────────────────────────────────────────


def _static_build_review(project_dir: Path) -> list[BuildFinding]:
    """Run all static checks on build artifacts."""
    all_findings: list[BuildFinding] = []

    # ── Find map file ──
    map_file = _find_map_file(project_dir)
    parsed: dict = {}

    if map_file:
        log.info(f"  Parsing map file: {map_file}")
        parsed = _parse_map_file(map_file)
        log.info(f"  Map file: {len(parsed.get('sections', {}))} sections, "
                 f"{len(parsed.get('symbols', {}))} symbols")
    else:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No map file (.map) found in project — cannot perform "
                       "detailed section/symbol analysis",
        })

    # ── Section size checks (requires map file) ──
    if parsed:
        all_findings.extend(_check_section_sizes(parsed, project_dir))

    # ── Address alignment checks ──
    if parsed:
        all_findings.extend(_check_address_alignment(parsed))

    # ── Unused sections ──
    if parsed:
        all_findings.extend(_check_unused_sections(parsed))

    # ── Unused symbols ──
    if parsed:
        all_findings.extend(_check_unused_symbols(parsed))

    # ── Binary sizes ──
    all_findings.extend(_check_binary_sizes(project_dir))

    # ── Size trend ──
    all_findings.extend(_check_size_trend(parsed, project_dir))

    return all_findings


# ── LLM-powered review ────────────────────────────────────────────────────


def _build_build_review_prompt(map_file: Path | None, binaries: dict) -> tuple[str, str]:
    """Build prompts for LLM-powered build output review."""
    system_prompt = (
        "You are an embedded firmware build expert reviewing compiler/linker "
        "output for an MCU target.\n"
        "Analyze the build output for:\n"
        "1. **Memory Usage**: Are .text/.data/.bss sizes within chip specifications?\n"
        "2. **Binary Size**: Is the total binary size appropriate for the target flash?\n"
        "3. **Section Layout**: Are sections correctly placed (code in ROM, data in RAM)?\n"
        "4. **Alignment**: Are key symbols (vector table, ISRs) properly aligned?\n"
        "5. **Any optimization opportunities**: Unused sections, large .rodata, etc.\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## Build Output\n"]
    if map_file:
        try:
            content = map_file.read_text(errors="replace")
            user_lines.append(f"### Map File: {map_file}\n```\n{content[:6000]}\n```\n")
        except OSError:
            pass

    binary_info = {}
    for fmt, files in binaries.items():
        for f in files:
            binary_info[str(f)] = f.stat().st_size
    if binary_info:
        user_lines.append("### Binary Files\n")
        for path, size in sorted(binary_info.items()):
            user_lines.append(f"- {path}: {size} bytes ({size / 1024:.1f} KB)\n")
        user_lines.append("\n")

    user_lines.append(
        "Review the build output above. Check memory usage, alignment, "
        "and any issues with the build artifacts for an MCU target."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_build(session: PipelineSession) -> str:
    """Step: 小克 — 编译输出验证。

    Discovers and analyzes build artifacts (map file, binary outputs).
    Checks section sizes, alignment, unused sections/symbols, and size trends.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  📦 [小克] 编译输出验证开始...")
        log.info("Running build output validation")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static build checks...")
        static_findings = _static_build_review(project_dir)
        log.info(f"Static build review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered build review...")
        llm_review = ""
        map_file = _find_map_file(project_dir)
        binaries = _find_binary_files(project_dir)
        try:
            system_prompt, user_prompt = _build_build_review_prompt(map_file, binaries)
            llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
            llm_review = llm_result["content"]
            usage = llm_result.get("usage", {})
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "review-build", "usage": usage})
            log.info(f"LLM build review: {usage.get('total_tokens', '?')} tokens")
        except Exception as e:
            log.warning(f"LLM build review failed (non-fatal): {e}")
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
            "SWE-MISRA-S1",
        ]

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-build",
            "spec_ref": "SWE.5",
            "req_ids": req_ids,
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "map_file_found": str(map_file) if map_file else None,
            "binary_files": {k: [str(p) for p in v] for k, v in binaries.items()},
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "build-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write build review: {e}")
            raise PipelineStepError(f"Cannot write build review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 编译输出验证完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Build review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Build review step failed: {e}")
        raise PipelineStepError(f"Build review step failed: {e}")
