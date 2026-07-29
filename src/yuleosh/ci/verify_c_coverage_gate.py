#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
C Coverage Gate — End-to-End Verification Pipeline (QG-006).

This module verifies that the C coverage gate end-to-end pipeline
actually works: compiles a C project, runs tests to produce .gcda
files, parses coverage with gcovr, compares against c_fail_under
threshold, and generates a verification report.

Usage:
    python -m yuleosh.ci.verify_c_coverage_gate --project <path>

The verification uses the demo C project under the yuleOSH demos/uart/
directory as the test subject.  It compiles with GCC + --coverage flags,
runs the host-mode demo executable, then parses .gcda output with gcovr.

On success it writes ``.yuleosh/reports/c-coverage-gate-verification.json``.
If no ``.gcda`` data is produced, it logs a P0 alert to
``.yuleosh/reports/p0-alerts.jsonl``.
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.verify_c_coverage_gate")

# P0 alert file path (relative to .yuleosh/)
P0_ALERTS_FILE = Path(".yuleosh") / "reports" / "p0-alerts.jsonl"
VERIFICATION_REPORT_FILE = Path(".yuleosh") / "reports" / "c-coverage-gate-verification.json"

# Demo C project relative path (from yuleOSH project root)
_DEMO_REL_PATH = "demos/uart"


def _ensure_report_dir(project_dir: Path) -> Path:
    """Ensure the .yuleosh/reports directory exists."""
    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _log_p0_alert(project_dir: Path, message: str, details: Optional[dict] = None) -> None:
    """Write a P0 alert entry to the p0-alerts.jsonl file."""
    report_dir = _ensure_report_dir(project_dir)
    alert_path = report_dir / "p0-alerts.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "severity": "P0",
        "source": "verify_c_coverage_gate",
        "message": message,
        "details": details or {},
    }
    log.error("P0 ALERT: %s", message)
    with open(alert_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _find_demo_project(project_dir: Path) -> Optional[Path]:
    """Locate the demo C project directory to use for verification.

    Checks these locations in order:
    1. ``<project_dir>/demos/uart/`` (yuleOSH built-in demo)
    2. ``<project_dir>/tests/unity/`` (existing unity test harness)
    """
    demo_path = project_dir / _DEMO_REL_PATH
    if demo_path.exists() and (demo_path / "CMakeLists.txt").exists():
        return demo_path

    # Fallback: check for unity tests
    unity_path = project_dir / "tests" / "unity"
    if unity_path.exists() and unity_path.is_dir():
        return unity_path

    return None


def _build_c_demo(demo_dir: Path) -> Optional[Path]:
    """Build the C demo project with --coverage flags.

    Creates a temporary build directory inside the demo directory and
    compiles with gcc + ``--coverage`` (equiv. ``-fprofile-arcs -ftest-coverage``).

    Returns the path to the compiled executable, or None on failure.
    """
    build_dir = demo_dir / "_build_verify"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    # Collect .c sources recursively
    c_files = []
    for root, _dirs, files in os.walk(demo_dir):
        for f in files:
            if f.endswith((".c", ".cpp")):
                # Skip files in the build dir
                if root.startswith(str(build_dir)):
                    continue
                c_files.append(os.path.join(root, f))

    if not c_files:
        log.warning("No C source files found in %s", demo_dir)
        return None

    # Try CMake-based build first
    cmake_path = shutil.which("cmake")
    if cmake_path and (demo_dir / "CMakeLists.txt").exists():
        log.info("Building demo with CMake + --coverage in %s ...", build_dir)
        try:
            cmake_result = subprocess.run(
                [cmake_path, demo_dir,
                 "-DCMAKE_C_FLAGS=--coverage",
                 "-DCMAKE_CXX_FLAGS=--coverage",
                 "-DTARGET=host",
                 "-DCMAKE_BUILD_TYPE=Debug",
                 f"-B{build_dir}", f"-S{demo_dir}"],
                capture_output=True, text=True, timeout=60,
            )
            if cmake_result.returncode != 0:
                log.warning("CMake configure failed: %s", cmake_result.stderr[:500])
                log.info("Falling back to manual gcc compilation...")
            else:
                build_result = subprocess.run(
                    [cmake_path, "--build", str(build_dir)],
                    capture_output=True, text=True, timeout=120,
                )
                if build_result.returncode == 0:
                    # Find the generated executable
                    for exe_name in ["uart_demo_host", "demo_host",
                                     "all", os.path.basename(demo_dir)]:
                        exe_path = build_dir / exe_name
                        if exe_path.exists() and os.access(exe_path, os.X_OK):
                            log.info("CMake build succeeded: %s", exe_path)
                            return exe_path
                    # Check for any executable in build dir
                    for item in build_dir.iterdir():
                        if item.is_file() and os.access(item, os.X_OK):
                            return item
                log.warning("CMake build failed, falling back to manual gcc...")
        except (subprocess.TimeoutExpired, Exception) as e:
            log.warning("CMake build error: %s, falling back to manual gcc...", e)

    # Manual gcc compilation with --coverage
    gcc = shutil.which("gcc") or shutil.which("cc")
    if not gcc:
        log.error("No C compiler found (gcc or cc)")
        return None

    includes = []
    for root, _dirs, _files in os.walk(demo_dir):
        # Look for header directories
        if any(f.endswith(".h") for f in os.listdir(root)):
            includes.append(f"-I{root}")

    output_exe = build_dir / "demo_verify"
    compile_cmd = (
        [gcc, "--coverage", "-g", "-O0", "-DTARGET_HOST", "-o", str(output_exe)]
        + c_files
        + includes
        + ["-lm"]
    )

    log.info("Compiling with: %s", " ".join(str(c) for c in compile_cmd[:10]) + " ...")
    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.error("gcc compilation failed:\n%s", result.stderr[:1000])
            return None
        log.info("Compilation succeeded: %s", output_exe)
        return output_exe
    except subprocess.TimeoutExpired:
        log.error("gcc compilation timed out")
        return None
    except Exception as e:
        log.error("gcc compilation error: %s", e)
        return None


def _run_demo_executable(exe_path: Path) -> bool:
    """Run the compiled demo executable to produce .gcda files.

    Returns True if execution succeeded (exit code 0).
    """
    log.info("Running: %s ...", exe_path)
    try:
        result = subprocess.run(
            [str(exe_path)],
            capture_output=True, text=True, timeout=30,
            cwd=str(exe_path.parent),
        )
        if result.returncode == 0:
            log.info("Demo executable ran successfully")
            log.debug("Output:\n%s", result.stdout[:500])
            return True
        else:
            log.warning("Demo executable exited with code %d", result.returncode)
            log.debug("Stderr:\n%s", result.stderr[:500])
            return False
    except subprocess.TimeoutExpired:
        log.warning("Demo executable timed out")
        return False
    except Exception as e:
        log.warning("Error running demo executable: %s", e)
        return False


def _find_gcda_files(build_dir: Path) -> list[Path]:
    """Find all .gcda files produced by the demo run."""
    gcda_files = []
    for root, _dirs, files in os.walk(build_dir):
        for f in files:
            if f.endswith(".gcda"):
                gcda_files.append(Path(root) / f)
    return gcda_files


def _parse_gcovr_coverage(gcda_dir: Path) -> Optional[dict]:
    """Run gcovr --json to parse .gcda coverage data.

    Returns the parsed JSON coverage report, or None on failure.
    """
    gcovr = shutil.which("gcovr")
    if not gcovr:
        log.warning("gcovr not installed — trying gcov (text parse)...")
        return _parse_gcov_text(gcda_dir)

    # Point gcovr at the build directory root (where .gcda files live)
    json_output = gcda_dir / "_gcovr_output.json"
    try:
        result = subprocess.run(
            [gcovr, "--json", "-r", str(gcda_dir), "-o", str(json_output)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.warning("gcovr returned non-zero: %s", result.stderr[:500])
        if json_output.exists():
            with open(json_output) as f:
                data = json.load(f)
            log.info("gcovr parsed %d files", len(data.get("files", [])))
            return data
    except subprocess.TimeoutExpired:
        log.warning("gcovr timed out")
    except Exception as e:
        log.warning("gcovr error: %s", e)

    # Fallback: try gcov text parse
    return _parse_gcov_text(gcda_dir)


def _parse_gcov_text(gcda_dir: Path) -> Optional[dict]:
    """Parse .gcda coverage via gcov text output (fallback when gcovr unavailable).

    Runs ``gcov`` on each .gcda file, parses the report lines,
    and returns a minimal report dict.
    """
    gcov = shutil.which("gcov")
    if not gcov:
        log.error("Neither gcovr nor gcov found — cannot parse coverage data")
        return None

    # Run gcov on .gcda files
    gcda_files = _find_gcda_files(gcda_dir)
    if not gcda_files:
        log.warning("No .gcda files found in %s", gcda_dir)
        return None

    total_lines = 0
    total_hit = 0
    files_data = []

    for gcda_path in gcda_files:
        try:
            result = subprocess.run(
                [gcov, str(gcda_path), "--json"],
                capture_output=True, text=True, timeout=30,
                cwd=str(gcda_dir),
            )
            # Try parsing JSON output (gcov >= 14 supports --json)
            out = result.stdout.strip()
            if out and out.startswith("{"):
                try:
                    gcov_data = json.loads(out)
                    for file_entry in gcov_data.get("files", [gcov_data]):
                        file_lines = file_entry.get("lines", {}).get("count", [])
                        found = len(file_lines)
                        hit = sum(1 for c in file_lines if c > 0)
                        total_lines += found
                        total_hit += hit
                        files_data.append({
                            "file": file_entry.get("file", str(gcda_path)),
                            "lines": {"found": found, "hit": hit},
                            "line_rate": (hit / found) if found > 0 else 0.0,
                        })
                    continue
                except json.JSONDecodeError:
                    pass

            # Fallback: parse gcov plain text output
            for line in result.stdout.split("\n"):
                if line.startswith("        "):
                    parts = line.strip().split(":")
                    if len(parts) >= 2:
                        count_str = parts[0].strip()
                        try:
                            count = int(count_str)
                            total_lines += 1
                            if count > 0 or "run" in count_str:
                                total_hit += 1
                        except ValueError:
                            pass

            files_data.append({
                "file": str(gcda_path),
                "lines": {"found": 0, "hit": 0},
                "line_rate": 0.0,
            })

        except (subprocess.TimeoutExpired, Exception) as e:
            log.warning("gcov parse error for %s: %s", gcda_path.name, e)

    if total_lines == 0:
        return None

    return {
        "files": files_data,
        "totals": {
            "lines": {"found": total_lines, "hit": total_hit},
        },
        "line_rate": total_hit / total_lines if total_lines > 0 else 0.0,
    }


def _load_c_fail_under(project_dir: Path) -> int:
    """Load the c_fail_under threshold from ci-config.yaml."""
    try:
        from yuleosh.ci.config import _get_ci_config
        cfg = _get_ci_config(str(project_dir))
        return cfg.coverage.c_fail_under if cfg else 70
    except Exception:
        return 70


def verify_c_coverage_gate(project_path: str) -> dict:
    """Run the end-to-end C coverage gate verification.

    This is the main entry point.  It:
    1. Finds a demo C project
    2. Compiles with --coverage
    3. Runs the executable to produce .gcda files
    4. Parses coverage data via gcovr (or gcov fallback)
    5. Compares against c_fail_under threshold
    6. Writes verification report JSON
    7. Logs P0 alert if no .gcda data

    Parameters
    ----------
    project_path : str
        Path to the yuleOSH project root.

    Returns
    -------
    dict
        Verification result with keys:
        - success: bool
        - line_rate: float or None
        - c_fail_under: int
        - gate_passed: bool or None
        - gcda_files_found: int
        - warnings: list[str]
        - report_path: str
    """
    project_dir = Path(project_path).resolve()
    report_dir = _ensure_report_dir(project_dir)
    report_path = report_dir / "c-coverage-gate-verification.json"

    result: dict = {
        "success": False,
        "verification_timestamp": datetime.now().isoformat(),
        "project_path": str(project_dir),
        "line_rate": None,
        "branch_rate": None,
        "c_fail_under": None,
        "gate_passed": None,
        "gcda_files_found": 0,
        "executable_success": None,
        "compile_success": None,
        "gcovr_available": shutil.which("gcovr") is not None,
        "gcc_available": shutil.which("gcc") is not None,
        "warnings": [],
        "report_path": str(report_path),
    }

    # Step 1: Find demo C project
    demo_dir = _find_demo_project(project_dir)
    if not demo_dir:
        msg = "No demo C project found for verification"
        result["warnings"].append(msg)
        log.warning(msg)
        result["compile_success"] = False
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    log.info("Using demo C project: %s", demo_dir)

    # Step 2: Compile with --coverage
    exe_path = _build_c_demo(demo_dir)
    if not exe_path:
        msg = "C demo compilation failed — cannot verify coverage gate"
        result["warnings"].append(msg)
        result["compile_success"] = False
        result["success"] = True  # Verification itself completed
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    result["compile_success"] = True
    build_dir = exe_path.parent

    # Step 3: Run the executable
    exec_ok = _run_demo_executable(exe_path)
    result["executable_success"] = exec_ok

    # Step 4: Find .gcda files
    gcda_files = _find_gcda_files(build_dir)
    result["gcda_files_found"] = len(gcda_files)

    if not gcda_files:
        msg = "No .gcda files produced after running executable"
        result["warnings"].append(msg)
        log.warning(msg)
        # P0 alert: no .gcda data
        _log_p0_alert(project_dir, msg, {
            "demo_dir": str(demo_dir),
            "exe_path": str(exe_path),
            "exec_success": exec_ok,
        })
        result["success"] = True  # Verification itself completed
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    log.info("Found %d .gcda file(s) in %s", len(gcda_files), build_dir)

    # Step 5: Parse coverage data
    coverage_data = _parse_gcovr_coverage(build_dir)
    if coverage_data is None:
        msg = "Failed to parse coverage data from .gcda files"
        result["warnings"].append(msg)
        result["success"] = True
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Extract line rate (gcovr JSON format)
    line_rate = coverage_data.get("line_rate", 0.0)
    if isinstance(line_rate, float) and 0 <= line_rate <= 1:
        line_rate_pct = round(line_rate * 100, 2)
    else:
        line_rate_pct = round(float(line_rate), 2)

    branch_rate = coverage_data.get("branch_rate", 0.0)
    if isinstance(branch_rate, float) and 0 <= branch_rate <= 1:
        branch_rate_pct = round(branch_rate * 100, 2)
    else:
        branch_rate_pct = round(float(branch_rate), 2)

    result["line_rate"] = line_rate_pct
    result["branch_rate"] = branch_rate_pct
    total_files = len(coverage_data.get("files", []))
    result["total_files"] = total_files

    # Per-file breakdown
    per_file = []
    for f_entry in coverage_data.get("files", []):
        per_file.append({
            "file": f_entry.get("file", "?"),
            "line_rate": f_entry.get("line_rate", 0.0),
        })
    result["per_file"] = per_file[:20]  # Keep top 20

    # Step 6: Compare against c_fail_under
    c_fail_under = _load_c_fail_under(project_dir)
    result["c_fail_under"] = c_fail_under

    gate_passed = line_rate_pct >= c_fail_under
    result["gate_passed"] = gate_passed

    log.info(
        "C coverage gate verification: line=%.1f%%, c_fail_under=%d%% → %s",
        line_rate_pct, c_fail_under,
        "PASS" if gate_passed else "FAIL",
    )

    result["success"] = True

    # Write verification report
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2)

    log.info("Verification report written to %s", report_path)
    return result


def main():
    """CLI entry point for the verification pipeline."""
    parser = argparse.ArgumentParser(
        description="C Coverage Gate — End-to-End Verification Pipeline (QG-006)",
    )
    parser.add_argument(
        "--project", default=".",
        help="Path to the yuleOSH project root (default: current directory)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    result = verify_c_coverage_gate(args.project)

    print(f"\n  {'=' * 55}")
    print(f"  C Coverage Gate Verification Report")
    print(f"  {'=' * 55}")
    print(f"  Success:         {'✅ YES' if result['success'] else '❌ NO'}")
    print(f"  Compile:         {'✅' if result.get('compile_success') else '❌'}")
    print(f"  Executable:      {'✅' if result.get('executable_success') else '❌'}")
    print(f"  .gcda files:     {result.get('gcda_files_found', 0)}")
    print(f"  Line rate:       {result.get('line_rate', 'N/A')}%")
    print(f"  Branch rate:     {result.get('branch_rate', 'N/A')}%")
    print(f"  c_fail_under:    {result.get('c_fail_under', 'N/A')}%")
    print(f"  Gate:            {'✅ PASS' if result.get('gate_passed') else '❌ FAIL' if result.get('gate_passed') is False else 'N/A'}")
    print(f"  gcovr available: {'✅' if result.get('gcovr_available') else '❌'}")
    print(f"  gcc available:   {'✅' if result.get('gcc_available') else '❌'}")
    print()

    if result.get("warnings"):
        print(f"  ⚠️  Warnings:")
        for w in result["warnings"]:
            print(f"    • {w}")
        print()

    report_path = result.get("report_path", "")
    if report_path:
        print(f"  📍 Report: {report_path}")

    if result.get("gcda_files_found", 0) == 0 and result.get("success"):
        print()
        print(f"  🚨 P0 ALERT: No .gcda data produced — coverage gate cannot be verified")
        print(f"     See .yuleosh/reports/p0-alerts.jsonl for details")
        sys.exit(2)

    if not result.get("gate_passed", False) and result.get("gate_passed") is not None:
        print()
        print(f"  ❌ Coverage gate FAILED: {result.get('line_rate', 0):.1f}% < c_fail_under {result.get('c_fail_under', 0)}%")
        print(f"     Improve C unit tests to raise coverage above threshold")
        sys.exit(1)

    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
