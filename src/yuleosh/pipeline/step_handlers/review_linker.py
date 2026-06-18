#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 链接脚本审查。

检查嵌入式链接脚本（.ld / .lds / .scatter）中的：
- 栈/堆大小定义
- 内存布局（ROM/RAM 地址范围）
- 段定义（.text / .data / .bss / .noinit）
- 中断向量表对齐
- 段对齐和填充策略
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_linker")

__all__ = ["step_review_linker"]

# ── Static checks for linker scripts ─────────────────────────────────────

LinkerFinding = dict  # type alias for readability


def _find_linker_scripts(project_dir: Path) -> list[Path]:
    """Discover linker/ scatter files in the project tree."""
    patterns = ["**/*.ld", "**/*.lds", "**/*.scatter", "**/linker/*"]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file() and p.suffix in (".ld", ".lds", ".scatter", "") and not p.name.startswith("."):
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


def _check_stack_size(content: str, path: Path) -> list[LinkerFinding]:
    """Check stack / heap size definitions."""
    findings = []
    stack_patterns = [
        (r"STACK_SIZE\s*=\s*(\d+)", "STACK_SIZE"),
        (r"__stack_size\s*=\s*(\d+)", "__stack_size"),
        (r"Stack_Size\s+EQU\s+(\d+)", "Stack_Size"),
        (r"stack_size\s*=\s*(\d+)", "stack_size"),
    ]
    heap_patterns = [
        (r"HEAP_SIZE\s*=\s*(\d+)", "HEAP_SIZE"),
        (r"__heap_size\s*=\s*(\d+)", "__heap_size"),
        (r"Heap_Size\s+EQU\s+(\d+)", "Heap_Size"),
        (r"heap_size\s*=\s*(\d+)", "heap_size"),
    ]

    # Check stack
    stack_found = False
    for pat, name in stack_patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            stack_found = True
            val = int(m.group(1))
            if val < 1024:
                findings.append({
                    "severity": "major",
                    "category": "stack",
                    "file": str(path),
                    "message": f"Stack size ({name}={val}) is < 1 KB — may be insufficient for embedded targets",
                })
            elif val < 2048:
                findings.append({
                    "severity": "minor",
                    "category": "stack",
                    "file": str(path),
                    "message": f"Stack size ({name}={val}) is < 2 KB — verify against worst-case call depth",
                })
            else:
                findings.append({
                    "severity": "info",
                    "category": "stack",
                    "file": str(path),
                    "message": f"Stack size defined ({name}={val})",
                })
            break

    if not stack_found:
        findings.append({
            "severity": "minor",
            "category": "stack",
            "file": str(path),
            "message": "No explicit stack size definition found — using default (may be toolchain-dependent)",
        })

    # Check heap
    heap_found = False
    for pat, name in heap_patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            heap_found = True
            val = int(m.group(1))
            if val == 0:
                findings.append({
                    "severity": "info",
                    "category": "heap",
                    "file": str(path),
                    "message": "Heap size explicitly set to 0 (no dynamic memory expected)",
                })
            elif val > 0:
                findings.append({
                    "severity": "info",
                    "category": "heap",
                    "file": str(path),
                    "message": f"Heap size defined ({name}={val}) — verify dynamic allocation is intentional",
                })
            break

    if not heap_found:
        findings.append({
            "severity": "info",
            "category": "heap",
            "file": str(path),
            "message": "No explicit heap size definition — heap may be sized by default",
        })

    return findings


def _check_section_definitions(content: str, path: Path) -> list[LinkerFinding]:
    """Check for essential section definitions."""
    findings = []

    # .text
    if not re.search(r'\.text', content):
        findings.append({
            "severity": "critical",
            "category": "sections",
            "file": str(path),
            "message": "No .text section defined — code will not link correctly",
        })
    # .data
    if not re.search(r'\.data', content):
        findings.append({
            "severity": "major",
            "category": "sections",
            "file": str(path),
            "message": "No .data section defined — initialized data will not be placed",
        })
    # .bss
    if not re.search(r'\.bss', content):
        findings.append({
            "severity": "major",
            "category": "sections",
            "file": str(path),
            "message": "No .bss section defined — zero-initialized data will not be placed",
        })
    # .noinit (optional but recommended for embedded)
    if not re.search(r'\.noinit', content):
        findings.append({
            "severity": "info",
            "category": "sections",
            "file": str(path),
            "message": "No .noinit section found — consider if any variables must retain value across reset",
        })

    return findings


def _check_vector_table_alignment(content: str, path: Path) -> list[LinkerFinding]:
    """Check interrupt vector table alignment."""
    findings = []
    # Common patterns for vector table symbols/labels
    vtable_patterns = [
        r"__Vectors\s*=",
        r"__vector_table\s*=",
        r"g_pfnVectors",
        r"isr_vector",
        r"VECTOR_TABLE",
        r"_vectors",
    ]
    has_vtable = any(re.search(pat, content, re.IGNORECASE) for pat in vtable_patterns)

    if has_vtable:
        # Check alignment directive nearby
        align_patterns = [
            r"\.\s*=\s*ALIGN\s*\(\s*(\d+)\s*\)",
            r"ALIGN\s*\(\s*(\d+)\s*\)",
        ]
        aligns = []
        for pat in align_patterns:
            aligns.extend(re.findall(pat, content, re.IGNORECASE))
        align_vals = [int(a) for a in aligns if a.isdigit()]

        min_align = min(align_vals) if align_vals else 0
        if min_align < 256 and min_align > 0:
            findings.append({
                "severity": "minor",
                "category": "vector_table",
                "file": str(path),
                "message": f"Vector table alignment ({min_align}) may be insufficient — "
                           f"Cortex-M requires 256-byte alignment; verify architecture",
            })
        elif min_align == 0:
            findings.append({
                "severity": "info",
                "category": "vector_table",
                "file": str(path),
                "message": "Vector table present but no explicit ALIGN directive found — verify alignment",
            })
    else:
        findings.append({
            "severity": "info",
            "category": "vector_table",
            "file": str(path),
            "message": "No vector table symbol detected in linker script — may be defined elsewhere",
        })

    return findings


def _check_lma_vma_difference(content: str, path: Path) -> list[LinkerFinding]:
    """Check if .data section has AT> for LMA/VMA separation (ARM XIP)."""
    findings = []
    # ARM XIP architectures require .data to have AT> to specify load address (LMA) in Flash
    # VMA is in RAM, LMA is in Flash
    if re.search(r'\.data\s*:', content, re.IGNORECASE):
        if not re.search(r'AT\s*[>]', content, re.IGNORECASE):
            findings.append({
                "severity": "major",
                "category": "lma_vma",
                "file": str(path),
                "message": (
                    ".data section found without AT> (load address) specification — "
                    "on ARM XIP architectures, .data must have AT> to set LMA (Flash) "
                    "separate from VMA (RAM); without it, the .data copy loop may read "
                    "from the wrong address"
                ),
            })
        else:
            findings.append({
                "severity": "info",
                "category": "lma_vma",
                "file": str(path),
                "message": ".data section specifies AT> load address — LMA/VMA separation confirmed",
            })
    else:
        findings.append({
            "severity": "info",
            "category": "lma_vma",
            "file": str(path),
            "message": "No .data section found — LMA/VMA check skipped",
        })
    return findings


def _check_arm_exception_tables(content: str, path: Path) -> list[LinkerFinding]:
    """Check for .ARM.exidx and .ARM.extab exception table sections.

    ARM ELF exception tables (.ARM.exidx and .ARM.extab) are required for
    C++ exception handling and for backtrace/unwind support.  In safety-critical
    embedded firmware these sections SHOULD be absent (no exceptions), but
    when present they MUST be properly placed in a non-volatile region.

    Missing .ARM.exidx reference means the linker will not produce unwind
    tables, causing abort() on any C++ exception thrown.  Conversely, in
    C-only codebases it is normal to omit them entirely — the check flags
    the absence as info, not a defect.
    """
    findings = []

    # Check for explicit .ARM.exidx section definition
    has_exidx = bool(re.search(r'\.ARM\.exidx', content))
    has_extab = bool(re.search(r'\.ARM\.extab', content))

    # Detect C++ runtime references that imply exception tables are needed
    cpp_runtime_refs = [
        r'__gxx_personality',
        r'__gnu_unwind',
        r'__cxa_',
        r'__exidx_start',
        r'__exidx_end',
    ]
    has_cpp_ref = any(re.search(p, content, re.IGNORECASE) for p in cpp_runtime_refs)

    if has_exidx:
        # Check placement — should be in ROM/Flash (not RAM)
        exidx_region = None
        # Look for .ARM.exidx in a SECTIONS block
        # Typical: .ARM.exidx : { *(.ARM.exidx* ) } > FLASH
        exidx_m = re.search(r'\.ARM\.exidx\s*:.*?[>]?(\w+)',
                            content, re.IGNORECASE | re.DOTALL)
        if exidx_m:
            exidx_region = exidx_m.group(1).upper()

        # Check if placed in a read-only / flash region
        flash_like = ['FLASH', 'ROM', 'EROM', 'FALSH', 'BANK']
        in_flash = any(r in (exidx_region or '') for r in flash_like)

        if in_flash:
            findings.append({
                "severity": "info",
                "category": "arm_exception",
                "file": str(path),
                "message": (
                    f".ARM.exidx section defined and placed in {exidx_region} — "
                    "correct for ARM exception tables; verify table size does not "
                    "exceed available flash region"
                ),
            })
        elif exidx_region:
            findings.append({
                "severity": "major",
                "category": "arm_exception",
                "file": str(path),
                "message": (
                    f".ARM.exidx section placed in {exidx_region} — "
                    "ARM exception tables MUST be in a read-only region (Flash/ROM), "
                    "not RAM; execution will fail if tables are in writeable memory"
                ),
            })
        else:
            findings.append({
                "severity": "info",
                "category": "arm_exception",
                "file": str(path),
                "message": (
                    ".ARM.exidx section defined but no explicit placement region "
                    "detected — verify it defaults to a read-only region"
                ),
            })

        # Also check for matching .ARM.extab
        if has_extab:
            findings.append({
                "severity": "info",
                "category": "arm_exception",
                "file": str(path),
                "message": (
                    ".ARM.extab also present — C++ exception table data "
                    "will be available for frame unwinding"
                ),
            })
        else:
            findings.append({
                "severity": "info",
                "category": "arm_exception",
                "file": str(path),
                "message": (
                    ".ARM.exidx present without .ARM.extab — compact model "
                    "(no exception-handling data) or table references only"
                ),
            })
    elif has_cpp_ref:
        findings.append({
            "severity": "critical",
            "category": "arm_exception",
            "file": str(path),
            "message": (
                "C++ personality/unwind references detected (__gxx_personality, "
                "__cxa_, __gnu_unwind) but no .ARM.exidx section found — "
                "linker will fail to produce exception tables; C++ exceptions "
                "will cause abort()"
            ),
        })
    else:
        findings.append({
            "severity": "info",
            "category": "arm_exception",
            "file": str(path),
            "message": (
                "No .ARM.exidx section — expected for C-only firmware; "
                "no ARM exception table required"
            ),
        })

    return findings


def _check_heap_stack_overlap(content: str, path: Path) -> list[LinkerFinding]:
    """Check if .heap and .stack share the same memory region without separator."""
    findings = []

    # Find memory regions
    regions = []
    region_pat = r"(?P<name>\w+)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)"
    for m in re.finditer(region_pat, content, re.IGNORECASE):
        regions.append(m.group("name").upper())

    # Find which region heap and stack belong to (look for OVERLAY or section placement)
    # Check if both .heap and .stack are defined
    has_heap = bool(re.search(r'\.heap', content))
    has_stack = bool(re.search(r'\.stack', content))

    if has_heap and has_stack:
        # Extract the memory region names used by heap and stack
        heap_region = None
        stack_region = None

        # Look for region placement after >
        heap_m = re.search(r'\.heap\s*:.*?[>](\w+)', content, re.IGNORECASE | re.DOTALL)
        if heap_m:
            heap_region = heap_m.group(1).upper()

        stack_m = re.search(r'\.stack\s*:.*?[>](\w+)', content, re.IGNORECASE | re.DOTALL)
        if stack_m:
            stack_region = stack_m.group(1).upper()

        # If explicit region placement differs, no overlap risk
        if heap_region and stack_region and heap_region != stack_region:
            findings.append({
                "severity": "info",
                "category": "heap_stack",
                "file": str(path),
                "message": f".heap and .stack in different regions ({heap_region} vs {stack_region}) — "
                           f"no overlap risk",
            })
            return findings

        # Check if there's a separator / fill / guard pattern between them
        # Look for NOLOAD sections or fill values that act as a guard
        has_guard = bool(re.search(
            r'FILL\s*\(|NOLOAD|PROVIDE\s*\(\s*__.*guard|__heap_limit|__stack_limit|__heap_stack_gap',
            content, re.IGNORECASE))

        # Check if there is a gap defined between heap end and stack start
        gap_patterns = [
            r'__heap_size\s*=\s*(\d+)',
            r'__stack_size\s*=\s*(\d+)',
        ]
        heap_sizes = []
        for pat in gap_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                heap_sizes.append(int(m.group(1)))

        if heap_region or stack_region or (has_heap and has_stack and not has_guard):
            findings.append({
                "severity": "minor",
                "category": "heap_stack",
                "file": str(path),
                "message": (
                    ".heap and .stack share the same memory region — "
                    "if they expand toward each other without a guard/separator, "
                    "heap overflow can corrupt the stack (or vice versa). "
                    "Consider adding a fill region or guard gap between them."
                ),
            })
        else:
            findings.append({
                "severity": "info",
                "category": "heap_stack",
                "file": str(path),
                "message": ".heap and .stack defined with guard separation",
            })

    elif has_heap:
        findings.append({
            "severity": "info",
            "category": "heap_stack",
            "file": str(path),
            "message": ".heap defined but no .stack section — stack may be in a separate region",
        })
    elif has_stack:
        findings.append({
            "severity": "info",
            "category": "heap_stack",
            "file": str(path),
            "message": ".stack defined but no .heap section — heap may use dynamic mechanism",
        })

    return findings


def _check_memory_regions(content: str, path: Path) -> list[LinkerFinding]:
    """Check ROM / RAM address ranges for reasonableness."""
    findings = []

    # Match MEMORY { ... } block or individual region definitions
    # RAM(?:xw?)?\s*:\s*ORIGIN\s*=\s*(\S+)\s*,\s*LENGTH\s*=\s*(\S+)
    region_patterns = [
        r"(?P<name>RAM\w*)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)",
        r"(?P<name>ROM\w*)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)",
        r"(?P<name>FLASH\w*)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)",
        r"(?P<name>SRAM\w*)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)",
        r"(?P<name>CCM\w*)\s*:\s*ORIGIN\s*=\s*(?P<origin>\S+)\s*,\s*LENGTH\s*=\s*(?P<length>\S+)",
    ]

    regions_found = []
    for pat in region_patterns:
        for m in re.finditer(pat, content, re.IGNORECASE):
            name = m.group("name")
            origin_str = m.group("origin").replace("0x", "").replace("X", "x")
            length_str = m.group("length").replace("0x", "").replace("X", "x")
            try:
                origin = int(origin_str, 16) if "x" in origin_str.lower() else int(origin_str)
                length = int(length_str, 16) if "x" in length_str.lower() else int(length_str)
                regions_found.append({"name": name, "origin": origin, "length": length})
            except ValueError:
                pass  # skip unparseable entries

    if not regions_found:
        findings.append({
            "severity": "major",
            "category": "memory_regions",
            "file": str(path),
            "message": "No MEMORY regions defined — will use default layout; verify for embedded target",
        })
        return findings

    for r in regions_found:
        name = r["name"]
        origin = r["origin"]
        length = r["length"]

        # RAM sanity: origin should be non-zero and reasonable
        if "RAM" in name.upper() or "SRAM" in name.upper() or "CCM" in name.upper():
            if origin < 0x10000000:
                findings.append({
                    "severity": "info",
                    "category": "memory_regions",
                    "file": str(path),
                    "message": f"RAM region '{name}': ORIGIN=0x{origin:08X}, LENGTH={length} "
                               f"({length / 1024:.1f} KB)",
                })
            if length < 4096:
                findings.append({
                    "severity": "major",
                    "category": "memory_regions",
                    "file": str(path),
                    "message": f"RAM region '{name}' length ({length}) is < 4 KB — "
                               f"may be too small for non-trivial firmware",
                })

        # ROM/FLASH sanity
        if "ROM" in name.upper() or "FLASH" in name.upper():
            findings.append({
                "severity": "info",
                "category": "memory_regions",
                "file": str(path),
                "message": f"ROM region '{name}': ORIGIN=0x{origin:08X}, LENGTH={length} "
                           f"({length / 1024:.1f} KB)",
            })

    return findings


def _static_linker_review(project_dir: Path) -> list[LinkerFinding]:
    """Run all static checks on discovered linker scripts."""
    all_findings: list[LinkerFinding] = []
    scripts = _find_linker_scripts(project_dir)

    if not scripts:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No linker script (.ld/.lds/.scatter) found in project tree",
        })
        return all_findings

    for script in scripts:
        log.info(f"  Checking linker script: {script}")
        try:
            content = script.read_text()
        except OSError as e:
            all_findings.append({
                "severity": "major",
                "category": "io",
                "file": str(script),
                "message": f"Cannot read linker script: {e}",
            })
            continue

        all_findings.extend(_check_stack_size(content, script))
        all_findings.extend(_check_section_definitions(content, script))
        all_findings.extend(_check_vector_table_alignment(content, script))
        all_findings.extend(_check_memory_regions(content, script))
        all_findings.extend(_check_lma_vma_difference(content, script))
        all_findings.extend(_check_arm_exception_tables(content, script))
        all_findings.extend(_check_heap_stack_overlap(content, script))

    return all_findings


def _build_linker_review_prompt(
    linker_contents: dict[str, str],
) -> tuple[str, str]:
    """Build prompts for LLM-powered linker script review."""
    system_prompt = (
        "You are an embedded firmware expert reviewing linker scripts.\n"
        "Analyze the provided linker scripts for:\n"
        "1. Memory map correctness — does the layout match common MCU architectures?\n"
        "2. Stack/heap sizing — are they appropriate for the target?\n"
        "3. Section placement — is code in flash, data in RAM, BSS zero-initialized?\n"
        "4. Alignment — vector tables, MPU regions, DMA buffers?\n"
        "5. Any missing sections or overlapping regions?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## Linker Scripts\n"]
    for path, content in linker_contents.items():
        user_lines.append(f"### {path}\n```\n{content[:6000]}\n```\n")
    user_lines.append(
        "Review the linker scripts above. "
        "Check for any issues with memory layout, alignment, "
        "or missing sections that would affect embedded firmware correctness."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_linker(session: PipelineSession) -> str:
    """Step: 小克 — 链接脚本审查。

    Discovers and reviews linker scripts in the project tree.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  🔗 [小克] 链接脚本审查开始...")
        log.info("Running linker script review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static linker checks...")
        static_findings = _static_linker_review(project_dir)
        log.info(f"Static linker review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered linker review...")
        llm_review = ""
        linker_scripts = _find_linker_scripts(project_dir)
        if linker_scripts:
            linker_contents = {}
            for p in linker_scripts:
                try:
                    linker_contents[str(p)] = p.read_text()
                except OSError:
                    pass
            if linker_contents:
                try:
                    system_prompt, user_prompt = _build_linker_review_prompt(linker_contents)
                    llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                    llm_review = llm_result["content"]
                    usage = llm_result.get("usage", {})
                    session.token_usage_total += usage.get("total_tokens", 0)
                    session.token_usage_steps.append({"step": "review-linker", "usage": usage})
                    log.info(f"LLM linker review: {usage.get('total_tokens', '?')} tokens")
                except Exception as e:
                    log.warning(f"LLM linker review failed (non-fatal): {e}")
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

        # Map this step handler to spec requirement IDs (req_id)
        # Used by traceability matrix for CL2 traceability
        req_ids = [
            "SWE-MISRA-S1",       # MISRA C:2023 integration
            "SWE-MISRA-CFG1",     # misra-rules.yaml rule definitions
        ]

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-linker",
            "spec_ref": "SWE.5",
            "req_ids": req_ids,
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "linker_scripts_found": [str(p) for p in linker_scripts],
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "linker-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write linker review: {e}")
            raise PipelineStepError(f"Cannot write linker review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 链接脚本审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Linker review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Linker review step failed: {e}")
        raise PipelineStepError(f"Linker review step failed: {e}")
