#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — Test stage execution functions.

Part of the stages/ package split from stages.py.
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — individual CI stage execution functions.

Each function runs one CI check (lint, coverage, etc.).
Called by layers.py to compose full CI layers.
"""

import fnmatch
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

    检测范围：全项目 ``src/`` 下的所有 Python 代码。
    阈值来自 ci-config.yaml 的 coverage.threshold_line，默认 5.0。
    当前全局 Python 覆盖率约 5%，故全局阈值设为 5.0。
    如需模块级门禁（如只对 ci/kpi/ 子模块设置更高阈值），
    请在 ci-config.yaml coverage.module_thresholds 中添加。

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
            print(f"    🔧 Fix: add more tests, or adjust threshold_line in ci-config.yaml coverage block")
            print(f"    🔧 Tip: consider excluded_paths for startup/HAL code in ci-config.yaml")
            return False
        if cond_pct < threshold_cond:
            ci.add_stage("coverage", "failed", f"Condition coverage {cond_pct}% < {threshold_cond}%")
            print(f"    ❌ Condition coverage below threshold!")
            print(f"    🔧 Fix: add branch coverage tests or adjust threshold_condition in ci-config.yaml")
            return False

        ci.add_stage("coverage", "passed", f"line={line_pct}%, cond={cond_pct}%")
        print(f"    ✅ Coverage thresholds met")
        return True

    except FileNotFoundError:
        print(f"    🔧 Fix: install coverage tool ('pip install coverage', or 'apt install lcov' for C coverage)")
        return _handle_stage_error(ci, "coverage", "Coverage tool not installed", strict)
    except subprocess.TimeoutExpired:
        print(f"    🔧 Fix: increase timeout or reduce test scope")
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
                qemu_serial="-serial mon:stdio",
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

def run_c_coverage_check(project_dir: str, ci: CIResult) -> bool:
    """C Coverage gate — block pipeline if line_rate < c_fail_under threshold.

    Reads ``.yuleosh/reports/c-coverage.json`` (written by :func:`run_c_coverage`)
    and compares the ``line_rate`` against the ``c_fail_under`` threshold from
    ``.yuleosh/ci-config.yaml``.

    Returns True if coverage meets or exceeds the threshold, False if blocked.
    Reports 'skipped' when no C coverage report exists.
    """
    print("  🚧 CI: C coverage gate (c_fail_under)...")

    from yuleosh.ci.config import _get_ci_config

    try:
        cfg = _get_ci_config(project_dir)
        c_fail_under = cfg.coverage.c_fail_under if cfg else 70
    except Exception as e:
        log.info("c_fail_under config fallback: %s", e)
        c_fail_under = 70

    cov_path = Path(project_dir) / ".yuleosh" / "reports" / "c-coverage.json"
    if not cov_path.exists():
        ci.add_stage("c-coverage-gate", "skipped",
                     "No C coverage report at .yuleosh/reports/c-coverage.json")
        print("    ⏭️  No C coverage report — skipped")
        return True

    try:
        with open(cov_path) as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        ci.add_stage("c-coverage-gate", "failed",
                     f"Cannot read coverage report: {e}")
        print(f"    ❌ Cannot read coverage report: {e}")
        return False

    # Support both CI format (line_rate at root) and batch format (summary.lines.rate)
    line_rate = report.get("line_rate")
    if line_rate is None:
        # Batch format: nested under summary.lines.rate (as fraction 0.0-1.0)
        summary_block = report.get("summary", {})
        lines_block = summary_block.get("lines", {}) if isinstance(summary_block, dict) else {}
        line_rate = lines_block.get("rate", 0.0) * 100 if isinstance(lines_block, dict) else 0.0
    branch_rate = report.get("branch_rate", 0.0)

    print(f"    C line coverage:   {line_rate:.1f}%")
    print(f"    C branch coverage: {branch_rate:.1f}%")
    print(f"    Threshold (c_fail_under): {c_fail_under}%")

    # ── Coordinate: fail_under gate ──
    if line_rate < c_fail_under:
        detail = f"C line coverage {line_rate:.1f}% < c_fail_under {c_fail_under}%"
        ci.add_stage("c-coverage-gate", "failed", detail)
        print(f"    ❌ {detail}")
        print(f"    🔧 Improve C unit tests to raise coverage above threshold")
        # Show low-coverage files for debugging
        raw_files = report.get("files", [])
        # Handle both list and dict formats for files
        if isinstance(raw_files, dict):
            raw_files = list(raw_files.values()) if raw_files else []
        files_list = raw_files
        low_files = sorted(
            [f for f in files_list if isinstance(f, dict) and f.get("line_rate", 100) < c_fail_under],
            key=lambda x: (1 - x.get("line_rate", 0) / 100) * x.get("lines", {}).get("found", 0),
            reverse=True,
        )[:5]
        if low_files:
            print(f"    📋 Low-coverage files (top 5 by uncovered lines):")
            for lf in low_files:
                lr = lf.get("line_rate", 0)
                lines_found = lf.get("lines", {}).get("found", 0)
                uncovered = int(lines_found * (1 - lr / 100))
                print(f"        • {lf.get('file', '?')}: {lr:.1f}% ({uncovered} lines uncovered)")
            print(f"    🔧 Consider adding module_thresholds in ci-config.yaml for low-coverage modules")
        return False

    # ── Module-level threshold checks (SWR-003.2) ──
    try:
        module_thresholds = cfg.coverage.module_thresholds if cfg else {}
    except Exception:
        module_thresholds = {}

    if module_thresholds and "files" in report:
        raw_files_for_mod = report.get("files", [])
        if isinstance(raw_files_for_mod, dict):
            raw_files_for_mod = list(raw_files_for_mod.values()) if raw_files_for_mod else []
        files_list = raw_files_for_mod
        # Group files by module prefix (first path component after src/)
        from collections import defaultdict as _dd
        module_files: dict = _dd(list)
        for f in files_list:
            fpath = f.get("file", "")
            rel = os.path.relpath(fpath, project_dir) if os.path.isabs(fpath) else fpath
            parts = rel.replace("\\", "/").split("/")
            # Module = first meaningful directory after src/
            module_key = "root"
            try:
                src_idx = parts.index("src")
                if src_idx + 1 < len(parts):
                    module_key = parts[src_idx + 1]
            except ValueError:
                module_key = parts[0] if parts else "root"
            module_files[module_key].append(f)

        # Check each module against its threshold
        module_failures = []
        for mod_name, mod_files in module_files.items():
            if mod_name in module_thresholds:
                mod_threshold = module_thresholds[mod_name]
                total_found = sum(f.get("lines", {}).get("found", 0) for f in mod_files)
                total_hit = sum(f.get("lines", {}).get("hit", 0) for f in mod_files)
                mod_rate = (total_hit / total_found * 100) if total_found > 0 else 100.0
                if mod_rate < mod_threshold:
                    module_failures.append((mod_name, mod_rate, mod_threshold))

        if module_failures:
            detail_parts = []
            for mod_name, mod_rate, mod_threshold in module_failures:
                detail_parts.append(f"{mod_name}: {mod_rate:.1f}% < {mod_threshold}%")
            detail = "; ".join(detail_parts)
            ci.add_stage("c-coverage-gate", "failed", f"Module thresholds: {detail}")
            print(f"    ❌ Module coverage thresholds not met:")
            for mod_name, mod_rate, mod_threshold in module_failures:
                print(f"        • {mod_name}: {mod_rate:.1f}% < {mod_threshold}%")
            return False

    # Record coverage trend (小马建议: auto-record on each C coverage gate run)
    try:
        from yuleosh.ci.coverage_trend import record_coverage
        record_coverage(project_dir)
    except Exception as trend_e:
        log.debug("Coverage trend record skipped: %s", trend_e)

    ci.add_stage("c-coverage-gate", "passed",
                 f"line_rate={line_rate:.1f}% >= {c_fail_under}%")
    print(f"    ✅ C coverage gate passed")
    return True


def run_coverage_regression(project_dir: str, ci: CIResult) -> bool:
    """Check Python coverage regression against trend history.

    CL3 P1-5: 覆盖率退化监控。
    比较最新覆盖率与历史滚动平均值的差异。
    如果 line/branch 覆盖率下降超过 5 个百分点，发出告警。
    """
    print("  📉 CI: coverage regression check...")

    try:
        from yuleosh.ci.coverage_trend import (
            record_coverage, check_coverage_regression,
        )

        # Step 1: Record current coverage
        record_coverage(project_dir)

        # Step 2: Check regression
        reg = check_coverage_regression(
            project_dir,
            line_drop_threshold=5.0,
            branch_drop_threshold=5.0,
            window=3,
        )

        if reg.get("regression"):
            alerts = reg.get("alerts", [])
            for alert in alerts:
                msg = alert.get("message", "")
                ci.add_stage("coverage-regression", "warning", msg)
                print(f"    ⚠️  Coverage regression detected: {msg}")

        if reg.get("alerts"):
            ci.add_stage("coverage-regression", "passed",
                         f"{len(reg['alerts'])} alert(s) (non-blocking)")
            print(f"    ⚠️  {len(reg['alerts'])} regression alert(s) - non-blocking")
        else:
            ci.add_stage("coverage-regression", "passed", "No regression detected")
            print(f"    ✅ No coverage regression detected")

        return True

    except ImportError as e:
        ci.add_stage("coverage-regression", "skipped", f"Cannot import: {e}")
        print(f"    ⏭️  Coverage regression skipped: {e}")
        return True
    except Exception as e:
        ci.add_stage("coverage-regression", "skipped", str(e))
        print(f"    ⏭️  Coverage regression error (non-blocking): {e}")
        return True


# ═══════════════════════════════════════════════════════════════════════
# V-Model Left Side (SWE.5): requirements, architecture, traceability
# ═══════════════════════════════════════════════════════════════════════

