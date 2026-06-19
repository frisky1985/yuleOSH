#!/usr/bin/env python3
"""
yuleOSH — C Coverage Runner (v4)

Builds C unit tests with --coverage in a temporary directory, runs them,
and generates coverage reports via gcovr. Saves JSON to .yuleosh/reports/,
appends to .yuleosh/reports/coverage-trend.jsonl.

Usage:
    python3 scripts/run_c_coverage.py [--fail-under=60]
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

log = logging.getLogger("c_coverage")

PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_DIR / ".yuleosh" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _get_git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5,
                           cwd=str(PROJECT_DIR))
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _count_lines_in_file_gcovr(f_entry: dict) -> tuple:
    """Count lines/functions/branches from a gcovr file entry.

    gcovr JSON per-file entries have:
        file, lines=[{line_number, count, branches=[{branchno, count},...]}], functions=[...]
    Returns (total_lines, covered_lines, total_funcs, hit_funcs, total_branches, covered_branches)
    """
    total_lines = covered_lines = 0
    total_funcs = hit_funcs = 0
    total_branches = covered_branches = 0

    for line_entry in f_entry.get("lines", []):
        total_lines += 1
        if line_entry.get("count", 0) > 0:
            covered_lines += 1
        for br in line_entry.get("branches", []):
            total_branches += 1
            if br.get("count", 0) > 0:
                covered_branches += 1

    for func_entry in f_entry.get("functions", []):
        total_funcs += 1
        if func_entry.get("execution_count", 0) > 0:
            hit_funcs += 1

    return total_lines, covered_lines, total_funcs, hit_funcs, total_branches, covered_branches


def build_and_run(build_root: Path) -> bool:
    """Set up build directory, compile and run tests."""
    cross_dir = PROJECT_DIR / "src" / "yuleosh" / "cross"
    hal_mock_dir = cross_dir / "hal_mock"
    unity_src_dir = PROJECT_DIR / "tests" / "unity" / "src"

    src_dir = build_root / "src" / "yuleosh" / "cross"
    hal_dir = src_dir / "hal_mock"; hal_dir.mkdir(parents=True)
    test_dir = build_root / "tests" / "unity"
    test_dir.mkdir(parents=True)
    usrc = test_dir / "src"; usrc.mkdir(parents=True)

    shutil.copy2(cross_dir / "hello.c", src_dir / "hello.c")
    shutil.copy2(hal_mock_dir / "hal_mock_impl.c", hal_dir / "hal_mock_impl.c")
    for h in ["mock_core.h", "uart_mock.h", "gpio_mock.h",
              "timer_mock.h", "i2c_mock.h", "spi_mock.h"]:
        shutil.copy2(hal_mock_dir / h, hal_dir / h)
    for tf in ["test_hal_mock_unity.c", "test_hello_unity.c"]:
        shutil.copy2(PROJECT_DIR / "tests" / "unity" / tf, test_dir / tf)
    for sf in ["unity.c", "unity.h", "unity_internals.h"]:
        shutil.copy2(unity_src_dir / sf, usrc / sf)

    includes = "-Isrc/yuleosh/cross -Isrc/yuleosh/cross/hal_mock -Itests/unity/src"
    cmds = [
        f"gcc -std=c11 -g -O0 --coverage {includes} -o tests/unity/test_hal_mock "
        f"tests/unity/test_hal_mock_unity.c tests/unity/src/unity.c "
        f"src/yuleosh/cross/hal_mock/hal_mock_impl.c",
        f"gcc -std=c11 -g -O0 --coverage {includes} -o tests/unity/test_hello "
        f"tests/unity/test_hello_unity.c tests/unity/src/unity.c",
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=60, cwd=str(build_root))
        if r.returncode != 0:
            log.error("Build failed:\n%s", r.stderr)
            return False

    for tgt in ["test_hal_mock", "test_hello"]:
        exe = build_root / "tests" / "unity" / tgt
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log.error("Test %s failed (exit=%d):\n%s", tgt, r.returncode, r.stdout[:300])
            return False
    return True


def run_gcovr(build_root: Path) -> dict:
    """Run gcovr and return parsed coverage dict."""
    result = subprocess.run(
        ["gcovr", "--gcov-executable=gcov", "--json-pretty",
         "-r", str(build_root)],
        capture_output=True, text=True, timeout=60)
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        log.error("gcovr JSON error: %s", e)
        log.error("stdout: %s", result.stdout[:300])
        return {}


def merge_report(cov_data: dict, fail_under: float = None) -> dict:
    """Merge gcovr JSON into yuleOSH coverage report format."""
    total_lines = total_covered = 0
    total_funcs = total_funcs_hit = 0
    total_branches = total_br_covered = 0
    files_out = []

    for f_entry in cov_data.get("files", []):
        fn = f_entry.get("file", "")
        # Only include production source files
        if not fn.startswith("src/yuleosh/cross/"):
            continue
        # Make project-relative path
        proj_fn = fn.replace("src/yuleosh/cross/", "src/yuleosh/cross/")

        tl, tc, tf, tfh, tb, tbc = _count_lines_in_file_gcovr(f_entry)
        total_lines += tl
        total_covered += tc
        total_funcs += tf
        total_funcs_hit += tfh
        total_branches += tb
        total_br_covered += tbc

        files_out.append({
            "file": proj_fn,
            "line_rate": round((tc / tl * 100) if tl > 0 else 0.0, 2),
            "branch_rate": round((tbc / tb * 100) if tb > 0 else 0.0, 2),
            "function_rate": round((tfh / tf * 100) if tf > 0 else 0.0, 2),
            "lines": {"found": tl, "hit": tc},
            "functions": {"found": tf, "hit": tfh},
        })

    line_rate = round((total_covered / total_lines * 100) if total_lines > 0 else 0.0, 2)
    branch_rate = round((total_br_covered / total_branches * 100) if total_branches > 0 else 0.0, 2)
    func_rate = round((total_funcs_hit / total_funcs * 100) if total_funcs > 0 else 0.0, 2)

    report = {
        "success": True,
        "line_rate": line_rate,
        "branch_rate": branch_rate,
        "function_rate": func_rate,
        "total_files": len(files_out),
        "files": files_out,
        "totals": {
            "lines": {"found": total_lines, "hit": total_covered},
            "functions": {"found": total_funcs, "hit": total_funcs_hit},
            "branches": {"found": total_branches, "hit": total_br_covered},
        },
    }

    if fail_under is not None:
        line_ok = line_rate >= fail_under
        report["gate_passed"] = line_ok
        report["gate_details"] = [{
            "metric": "line_rate", "value": line_rate,
            "threshold": fail_under, "passed": line_ok,
        }]

    return report


def save_report(report: dict):
    json_path = REPORT_DIR / "c-coverage.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    log.info("Saved: %s (line_rate=%.1f%%)", json_path, report["line_rate"])

    trend_path = REPORT_DIR / "coverage-trend.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "commit": _get_git_commit(),
        "c": {
            "line_rate": report["line_rate"],
            "branch_rate": report["branch_rate"],
            "total_files": report["total_files"],
        },
        "python": {"line_rate": None, "branch_rate": None},
    }
    with open(trend_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="yuleOSH C coverage runner")
    parser.add_argument("--fail-under", type=float, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    with tempfile.TemporaryDirectory(prefix="yuleosh-cov-") as tmpdir:
        build_root = Path(tmpdir)
        if not build_and_run(build_root):
            sys.exit(1)
        cov_data = run_gcovr(build_root)
        if not cov_data:
            log.error("gcovr returned no data")
            sys.exit(1)
        report = merge_report(cov_data, fail_under=args.fail_under)
        save_report(report)

    line_rate = report["line_rate"]
    print(f"\n📊 C Coverage Report")
    print(f"{'='*50}")
    print(f"  Line coverage:      {line_rate:.1f}%")
    print(f"  Branch coverage:    {report['branch_rate']:.1f}%")
    print(f"  Function coverage:  {report['function_rate']:.1f}%")
    print(f"  Files measured:     {report['total_files']}\n")

    for f in report["files"]:
        lr = f["line_rate"]; br = f["branch_rate"]; fr = f["function_rate"]
        print(f"    {f['file']:50s} L{lr:6.1f}% B{br:6.1f}% F{fr:6.1f}%")

    if args.fail_under is not None:
        passed = line_rate >= args.fail_under
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n  Gate: {status} ({line_rate:.1f}% >= {args.fail_under:.0f}%)")
        if not passed:
            sys.exit(1)
    else:
        print(f"\n  (no gate threshold)")
    print(f"  ✅ Done!")


if __name__ == "__main__":
    main()
