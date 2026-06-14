#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — individual CI stage execution functions.

Each function runs one CI check (lint, coverage, etc.).
Called by layers.py to compose full CI layers.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.ci.config import is_strict, is_misra_fail_fast, _get_ci_config
from yuleosh.ci.result import CIResult, timed_stage

from yuleosh.ci.stage_utils import (
    find_test_files, get_cache_key_for_dir,
    _test_file_cache, _test_file_cache_mtime,
    _should_skip_coverage, _coverage_skip_reason,
    _run_coverage_and_export, _load_coverage_json,
    _resolve_cross_compile, _cross_compile_via_docker,
    _handle_stage_error, _run_subprocess,
)

log = logging.getLogger("ci.stages")

def run_plan_lint(project_dir: str, ci: CIResult) -> bool:
    """Run plan-lint: check task kind and T00 three-step format."""
    print("  🔍 CI: plan-lint...")
    
    # Look for task files
    task_files = []
    for root, dirs, files in os.walk(project_dir):
        # Skip non-project hidden directories (.git, .pytest_cache)
        # but keep .osh/ and .yuleosh/ for plan/target lint checks
        skip_hidden = {".git", ".pytest_cache", "__pycache__", ".egg-info", ".mypy_cache"}
        dirs[:] = [d for d in dirs if d not in skip_hidden and not (d.startswith(".") and d not in (".osh", ".yuleosh"))]
        # Only check files in tasks/ or plans/ directories (relative to project root)
        rel_parts = os.path.relpath(root, project_dir).split(os.sep)
        if "tasks" in rel_parts or "plans" in rel_parts:
            for f in files:
                if f.endswith(".md") and ("task" in f.lower() or "plan" in f.lower()):
                    task_files.append(os.path.join(root, f))
    
    if not task_files:
        ci.add_stage("plan-lint", "skipped", "No task/plan files found")
        print("    ⏭️  No task/plan files — skipped")
        return True
    
    issues = []
    for tf in task_files:
        content = Path(tf).read_text()
        # Check for kind classification
        if "feature" not in content.lower() and "bugfix" not in content.lower() and "refactor" not in content.lower():
            issues.append(f"{tf}: Missing kind classification")
        
        # Check for T00 sections
        if not all(marker in content for marker in ["RED", "GREEN", "REFACTOR"]):
            issues.append(f"{tf}: Missing T00 three-step sections")
    
    if issues:
        for i in issues:
            print(f"    ⚠️  {i}")
        ci.add_stage("plan-lint", "failed", "; ".join(issues[:3]))
        print(f"    ❌ plan-lint found {len(issues)} issue(s) — blocking pipeline")
        return False  # Warnings block the pipeline per A-01
    else:
        ci.add_stage("plan-lint", "passed")
        print("    ✅ plan-lint passed")
        return True
def run_clang_tidy(project_dir: str, ci: CIResult) -> bool:
    """Run clang-tidy on C/C++ files."""
    print("  🔎 CI: clang-tidy...")
    
    c_files = []
    for root, dirs, files in os.walk(os.path.join(project_dir, "src")):
        for f in files:
            if f.endswith((".c", ".cpp", ".h", ".hpp")):
                c_files.append(os.path.join(root, f))
    
    if not c_files:
        ci.add_stage("clang-tidy", "skipped", "No C/C++ files found")
        print("    ⏭️  No C/C++ files — skipped")
        return True
    
    strict = is_strict()
    misra_ff = is_misra_fail_fast()
    
    # Try to run clang-tidy
    try:
        result = subprocess.run(
            ["clang-tidy"] + c_files[:20] + ["--", "-std=c11"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            ci.add_stage("clang-tidy", "passed")
            print("    ✅ clang-tidy passed")
            return True
        else:
            detail = result.stdout[:500] if result.stdout else result.stderr[:500]
            if misra_ff:
                ci.add_stage("clang-tidy", "failed", detail)
                print(f"    ❌ clang-tidy found issues (MISRA_FAIL_FAST):\n{detail}")
                return False
            ci.add_stage("clang-tidy", "failed", detail)
            print(f"    ❌ clang-tidy found issues:\n{result.stdout[:300]}")
            return False  # A-01: always block on tool failure
    except FileNotFoundError:
        reason = "clang-tidy not installed"
        if strict:
            ci.add_stage("clang-tidy", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("clang-tidy", "skipped", reason)
        print(f"    ⏭️  {reason} — skipped")
        return False  # A-01: skip returns False, blocking pipeline
    except subprocess.TimeoutExpired:
        reason = "clang-tidy timed out"
        if strict:
            ci.add_stage("clang-tidy", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("clang-tidy", "skipped", reason)
        print(f"    ⏭️  {reason} — skipped")
        return False  # A-01: skip returns False, blocking pipeline
def run_unit_tests(project_dir: str, ci: CIResult) -> bool:
    """Discover and run unit tests."""
    print("  🧪 CI: unit tests...")
    
    # Python tests
    test_files = find_test_files(project_dir)
    if test_files:
        print(f"    Found {len(test_files)} test files")
    
    python_tests = [t for t in test_files if t.endswith(".py")]
    
    if python_tests:
        for tf in python_tests:
            rel = os.path.relpath(tf, project_dir)
            print(f"    Running: {rel}")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", tf, "-x", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                ci.add_stage("unit-tests", "failed", f"{rel}: {result.stdout[:200]}")
                print(f"    ❌ {rel} FAILED")
                return False
            else:
                ci.add_stage("unit-tests", "passed")
                print(f"    ✅ {rel} passed")
    
    if python_tests:
        return True
    
    # If no tests found, try pytest discovery
    if not python_tests:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q", "--collect-only"],
                capture_output=True, text=True, timeout=30, cwd=project_dir,
            )
            if result.returncode == 0:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
                    capture_output=True, text=True, timeout=120, cwd=project_dir,
                )
                if result.returncode == 0:
                    ci.add_stage("unit-tests", "passed")
                    print("    ✅ All pytest tests passed")
                    return True
                else:
                    ci.add_stage("unit-tests", "failed", result.stdout[:300])
                    print(f"    ❌ Tests failed")
                    return False
        except FileNotFoundError:
            ci.add_stage("unit-tests", "skipped", "pytest not installed")
            print("    ⏭️  pytest not installed — blocked")
            return False  # A-01: missing tool blocks
        except subprocess.TimeoutExpired:
            ci.add_stage("unit-tests", "skipped", "pytest timed out")
            print("    ⏭️  pytest timed out — blocked")
            return False  # A-01: tool error blocks
        except Exception as e:
            ci.add_stage("unit-tests", "skipped", f"pytest error: {e}")
            print(f"    ⏭️  pytest error: {e} — blocked")
            return False  # A-01: tool error blocks
        
        ci.add_stage("unit-tests", "skipped", "No test framework detected")
        print("    ⏭️  No tests discovered — skipped")
    
    return True
def run_coverage_check(project_dir: str, ci: CIResult) -> bool:
    """Check test coverage meets threshold.

    Skips coverage when HOOK_TYPE=commit (pre-commit hook) to avoid
    slowing down every commit.  Coverage runs on push (HOOK_TYPE=push
    or when not in a hook at all).
    """
    if _should_skip_coverage():
        reason = _coverage_skip_reason()
        ci.add_stage("coverage", "skipped", reason)
        print(f"    ⏭️  Coverage skipped ({reason})")
        return True

    print("  📊 CI: coverage check...")

    from yuleosh.ci.config import DEFAULT_COVERAGE_THRESHOLD_LINE, DEFAULT_COVERAGE_THRESHOLD_COND
    try:
        cfg = _get_ci_config(project_dir)
        threshold_line = cfg.coverage.threshold_line if cfg else DEFAULT_COVERAGE_THRESHOLD_LINE
        threshold_cond = cfg.coverage.threshold_condition if cfg else DEFAULT_COVERAGE_THRESHOLD_COND
    except Exception as e:
        import logging; logging.getLogger("ci.run").info("Coverage config fallback: %s", e)
        threshold_line = DEFAULT_COVERAGE_THRESHOLD_LINE
        threshold_cond = DEFAULT_COVERAGE_THRESHOLD_COND

    strict = is_strict()

    try:
        # Step 1: Run coverage
        run_ok, err_detail = _run_coverage_and_export(project_dir)
        if not run_ok:
            ci.add_stage("coverage", "failed", err_detail)
            print(f"    ❌ {err_detail}")
            return False

        # Step 2: Parse results
        line_pct, cond_pct = _load_coverage_json(project_dir)

        ci.coverage = {
            "line_coverage": line_pct,
            "condition_coverage": cond_pct,
            "threshold_line": threshold_line,
            "threshold_condition": threshold_cond,
            "line_pass": line_pct >= threshold_line,
            "condition_pass": cond_pct >= threshold_cond,
        }

        print(f"    Line coverage: {line_pct:.1f}% (threshold: {threshold_line}%)")
        print(f"    Condition coverage: {cond_pct:.1f}% (threshold: {threshold_cond}%)")

        # Step 3: Check thresholds
        if line_pct < threshold_line:
            ci.add_stage("coverage", "failed", f"Line coverage {line_pct}% < {threshold_line}%")
            print(f"    ❌ Line coverage below threshold!")
            return False
        if cond_pct < threshold_cond:
            ci.add_stage("coverage", "failed", f"Condition coverage {cond_pct}% < {threshold_cond}%")
            print(f"    ❌ Condition coverage below threshold!")
            return False

        ci.add_stage("coverage", "passed", f"line={line_pct}%, cond={cond_pct}%")
        print(f"    ✅ Coverage thresholds met")
        return True

    except FileNotFoundError:
        return _handle_stage_error(ci, "coverage", "Coverage tool not installed", strict)
    except subprocess.TimeoutExpired:
        return _handle_stage_error(ci, "coverage", "Coverage run timed out", strict)
    except json.JSONDecodeError as e:
        ci.add_stage("coverage", "skipped", f"Coverage JSON invalid: {e}")
        print(f"    ⏭️  Coverage JSON invalid: {e} — blocked")
        return False
def run_sil_tests(project_dir: str, ci: CIResult) -> bool:
    """Run SIL (Software-in-the-Loop) tests using QEMU emulation.

    Searches for prebuilt .elf firmware in ``tests/fixtures/prebuilt/``
    and runs each through the SIL runner.  Results are saved to
    ``.osh/ci/sil-test-results.json``.

    Returns ``True`` if all tests pass (or are skipped), ``False``
    on any failure.
    """
    print("  \U0001f5a5\ufe0f  CI: SIL tests...")

    # Look for prebuilt test firmware
    prebuilt_dir = Path(project_dir) / "tests" / "fixtures" / "prebuilt"

    elf_files = []
    if prebuilt_dir.exists():
        elf_files = list(prebuilt_dir.glob("*.elf"))

    if not elf_files:
        msg = (
            "No prebuilt .elf found in tests/fixtures/prebuilt/. "
            "Compile with: cd tests/fixtures/hello-arm && make"
        )
        ci.add_stage("sil-tests", "skipped", msg)
        print(f"    \u23ed\ufe0f  {msg}")
        return True  # Intentional skip — not a pipeline failure

    strict = is_strict()

    try:
        from cross.sil_runner import SilResult, sil_test
        from cross.target_config import TargetConfig

        results: list[dict] = []
        all_passed = True

        for elf_path in elf_files:
            print(f"    Running SIL test: {elf_path.name}")

            # Infer arch from filename convention or default to ARM
            cfg = TargetConfig(
                name="sil-ci-test",
                mcu="cortex-m3",
                arch="arm" if "arm" in elf_path.name else "arm",
                qemu_machine="lm3s6965evb",
                qemu_cpu="cortex-m3",
                qemu_serial="-serial stdio",
                elf=str(elf_path),
                default_timeout=30,
            )

            result = sil_test(
                cfg,
                expect_pattern="Hello from yuleOSH cross-compilation test!",
                timeout=15,
            )

            entry = {
                "elf": elf_path.name,
                "passed": result.passed,
                "elapsed": result.elapsed,
                "error": result.error,
                "assertion_failures": result.assertion_failures,
                "log_snippet": result.log[-200:],
            }
            results.append(entry)

            if result.passed:
                print(f"      \u2705 {elf_path.name} passed ({result.elapsed:.1f}s)")
            else:
                failures = result.error or result.assertion_failures[0] if result.assertion_failures else "unknown"
                print(f"      \u274c {elf_path.name} failed: {failures}")
                all_passed = False

        # Save results to .osh/ci/
        ci_dir = Path(project_dir) / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        results_path = ci_dir / "sil-test-results.json"
        with open(results_path, "w") as f:
            json.dump({
                "layer": 2,
                "stage": "sil-tests",
                "timestamp": datetime.now().isoformat(),
                "all_passed": all_passed,
                "results": results,
            }, f, indent=2)

        if all_passed:
            ci.add_stage("sil-tests", "passed", f"{len(results)} test(s) passed")
            print(f"    \u2705 SIL tests: {len(results)} passed")
            return True
        else:
            failed_count = sum(1 for r in results if not r["passed"])
            ci.add_stage("sil-tests", "failed", f"{failed_count}/{len(results)} failed")
            print(f"    \u274c SIL tests: {failed_count}/{len(results)} failed")
            return False

    except ImportError as e:
        reason = f"Cannot import SIL test modules: {e}"
        if strict:
            ci.add_stage("sil-tests", "failed", reason)
            print(f"    \u274c {reason} (strict mode)")
            return False
        ci.add_stage("sil-tests", "skipped", reason)
        print(f"    \u23ed\ufe0f  {reason} \u2014 skipped")
        return False  # A-01: missing tool blocks
    except Exception as e:
        reason = f"SIL test error: {e}"
        ci.add_stage("sil-tests", "failed", reason)
        print(f"    \u274c {reason}")
        return False