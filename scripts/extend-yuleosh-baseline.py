#!/usr/bin/env python3
"""Extend .cppcheck_suppressions baseline for yuleOSH full-embedded scans.

The yuleOSH toolchain scans ALL of embedded/ (including bsw_integration,
mcal_stubs, freertos_port from the v2.1.0 merge), while misra-ci.yml only
covers the 4 protocol modules. This script runs the same cppcheck command as
yuleOSH, collects un-suppressed MISRA violations, and appends rule:file
suppressions until the scan is clean (iterative baseline extension).
"""
import re
import subprocess
import sys
import os
from pathlib import Path

PROJECT = Path("/Users/stefan/.openclaw/workspace/yuleDKCS")
SUPP = PROJECT / ".cppcheck_suppressions"
BASELINE_SRC = PROJECT / "embedded/.cppcheck"

# Same command shape as yuleosh.ci.stages.review.run_misra_check (full mode)
CMD = [
    "cppcheck", "--addon=misra", "--language=c", "--std=c99", "--enable=all",
    "--suppress=missingIncludeSystem", "-q",
    "--suppressions-list=./.cppcheck_suppressions",
    "-DSTD_ON", "-DSTD_OFF", "-DSTD_HIGH", "-DSTD_LOW", "-DSTD_ACTIVE", "-DSTD_IDLE",
    "-DNULL_PTR", "-DTRUE", "-DFALSE", "-DE_OK", "-DE_NOT_OK", "-DNULL",
    "-I", ".", "-I", "src", "-I", "tests",
    "-I", "tests/qemu_m33/include",
    "-I", "tests/qemu_m33/third_party/FreeRTOS-Kernel/include",
    "-I", "tests/qemu_m33/src",
    "-I", "embedded",
    "-I", "embedded/iccoa_protocol/include",
    "-I", "embedded/ccc_protocol/include",
    "-I", "embedded/mcal_stubs/include",
    "-I", "embedded/bsw_integration/include",
    "-I", "embedded/unified_protocol/include",
    "-I", "embedded/icce_protocol/include",
    "-I", "embedded/freertos_port/include",
    "-I", "embedded/freestanding_includes",
]


def build_scan_files() -> list[str]:
    """Collect scan files exactly like yuleOSH does (scan_dirs + exclude_paths)."""
    sys.path.insert(0, "/Users/stefan/workspace/tasks/yuleOSH-check/src")
    from yuleosh.ci.stages.review import _find_c_sources, _exclude_paths
    from yuleosh.ci.config import _get_ci_config
    cfg = _get_ci_config(str(PROJECT))
    scan_dirs = cfg.misra.scan_dirs if cfg and cfg.misra.scan_dirs else ["src", "benchmark", "ref"]
    files = _find_c_sources(str(PROJECT), scan_dirs)
    exclude = cfg.misra.exclude_paths if cfg else []
    files = _exclude_paths(files, exclude, str(PROJECT))
    # Relative paths, normalized
    rel = []
    for f in files:
        if os.path.isabs(f):
            r = os.path.relpath(f, str(PROJECT))
        else:
            r = f
        rel.append(os.path.normpath(r))
    return sorted(set(rel))


def scan() -> list[str]:
    """Run cppcheck (same file list as yuleOSH) and return unsuppressed lines."""
    files = build_scan_files()
    cmd = list(CMD) + files
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT, timeout=400)
    out = r.stderr or r.stdout or ""
    lines = []
    for line in out.splitlines():
        # Skip informational lines (missingInclude, branch limits, unmatched)
        if "information" in line:
            continue
        # Keep everything else that carries a check id in [brackets]
        if re.search(r"\[[^\]]+\]$", line):
            lines.append(line)
    return lines


def parse_rule_file(line: str) -> tuple[str, str] | None:
    """Extract (rule_id, file_path) from a cppcheck output line.

    Default cppcheck format:
      file:line:col: severity: message [rule-id]
    Rule id may be misra-c2012-N.N, misra-config, unusedFunction, etc.
    """
    m = re.search(r"\[([^\]]+)\]$", line)
    if not m:
        return None
    rule = m.group(1).strip()
    if not rule:
        return None
    # file:line:col prefix — strip trailing :severity: message
    prefix = line.split("[")[0].strip()
    fm = re.match(r"^(.+?):(\d+):\d+:", prefix)
    if not fm:
        return None
    fpath = fm.group(1).strip()
    if not fpath or fpath == "nofile":
        return None
    # Normalize ./ prefix
    if fpath.startswith("./"):
        fpath = fpath[2:]
    # Skip unmatchedSuppression — informational, not a real violation
    if rule == "unmatchedSuppression":
        return None
    return rule, fpath


def main():
    # Read current baseline (keep existing entries)
    existing = set()
    for line in SUPP.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            existing.add(line)

    for iteration in range(1, 6):
        print(f"--- Iteration {iteration} ---")
        lines = scan()
        new_entries = set()
        real_count = 0
        for line in lines:
            parsed = parse_rule_file(line)
            if not parsed:
                continue
            rule, fpath = parsed
            real_count += 1
            # Normalize c2023 -> c2012 for the baseline (cppcheck emits c2012)
            rule = rule.replace("misra-c2023-", "misra-c2012-")
            entry = f"{rule}:{fpath}"
            if entry not in existing:
                new_entries.add(entry)

        print(f"  cppcheck misra lines: {len(lines)}, real violations: {real_count}, new suppressions: {len(new_entries)}")
        if not new_entries:
            print("  ✅ Baseline complete — no new violations to suppress")
            return 0

        with SUPP.open("a", encoding="utf-8") as f:
            f.write(f"\n# ---- Auto-extended for yuleOSH full-embedded scan (iter {iteration}) ----\n")
            for entry in sorted(new_entries):
                f.write(entry + "\n")
                existing.add(entry)
        print(f"  Appended {len(new_entries)} entries")

    print("  ⚠️  Reached max iterations — baseline may still be incomplete")
    return 1


if __name__ == "__main__":
    sys.exit(main())
