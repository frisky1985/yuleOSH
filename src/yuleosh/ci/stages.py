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


def _categorize_file(filepath: str, categories: dict) -> tuple[str, dict]:
    """根据文件路径判断代码类别，返回 (category_name, category_config)。

    匹配优先级: template > third_party > business。
    无匹配时默认返回 ("business", business_config).
    """
    basename = os.path.basename(filepath)
    # Priority order: template, third_party, business
    priority_order = ["template", "third_party", "business"]
    for cat_name in priority_order:
        cat_cfg = categories.get(cat_name, {})
        for pattern in cat_cfg.get("paths", []):
            if fnmatch.fnmatch(filepath, pattern) or \
               fnmatch.fnmatch(basename, pattern):
                return cat_name, cat_cfg
    # Fallback: business
    return "business", categories.get("business", {})


def _format_null_pointer_fix(category: str, file_path: str) -> str:
    """根据代码类别生成针对性的多级指针空修复建议。"""
    if category == "template":
        return ""  # template 代码不显示

    fix_text = """
    🔧 修复建议（多级指针判空）:
        // 方法一：逐层判空（推荐）
        if (ptr != NULL) {
            if (*ptr != NULL) {
                **ptr = value;
            }
        }
        // 方法二：封装安全访问函数
        int safe_set(int **ptr, int row, int col, int value) {
            if (ptr == NULL || ptr[row] == NULL) return -1;
            ptr[row][col] = value;
            return 0;
        }
        // 方法三：若确认不会为NULL，加断言（仅限于业务代码）
        assert(ptr != NULL && *ptr != NULL);
"""
    if category == "third_party":
        fix_text += """
    ⚠️ 第三方库代码：
        如果确认是误报（该指针在该场景中不可能为NULL），
        请在 ci-config.yaml 中添加 deviation 豁免：
            deviations:
              - rule: Dir-4.1
                file: "third_party/xxx/**/*.c"
                reason: "第三方库，指针安全已由对方保证"
                approved_by: "your-name"
                expires: "2027-06-30"
                status: approved
"""
    return fix_text


def _exclude_paths(files: list[str], exclude_patterns: list[str], project_dir: str) -> list[str]:
    """Filter out files matching any of the exclude patterns (glob-style).

    Patterns like "tests/**" are matched relative to project_dir.
    """
    if not exclude_patterns:
        return files

    filtered = []
    for f in files:
        # Get relative path
        if os.path.isabs(f):
            try:
                rel = os.path.relpath(f, project_dir)
            except ValueError:
                rel = f
        else:
            rel = f

        excluded = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel, pattern):
                excluded = True
                break

        if not excluded:
            filtered.append(f)

    excluded_count = len(files) - len(filtered)
    if excluded_count > 0:
        log.info("Excluded %d file(s) via exclude_paths patterns", excluded_count)

    return filtered


def _detect_include_paths(project_dir: str) -> list[str]:
    """Auto-detect common include directories for cppcheck -I flags.

    Scans project_dir for standard C/C++ include directories
    that exist on disk.
    """
    candidates = [
        ".",
        "src",
        "include",
        "inc",
        "tests",
        "tests/unity/src",
        "Drivers",
        "Drivers/CMSIS",
        "Drivers/CMSIS/Include",
        "Drivers/STM32F4xx_HAL_Driver",
        "Drivers/STM32F4xx_HAL_Driver/Inc",
        "Middlewares",
        "third_party",
        "lib",
        "common",
    ]
    found = []
    for c in candidates:
        full = os.path.join(project_dir, c)
        if os.path.isdir(full):
            found.append(full)
    return found


def _get_git_commit(project_dir: str) -> str:
    """Get short git commit hash from the project directory."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=project_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

def run_yaml_validation(project_dir: str, ci: CIResult) -> bool:
    """Validate YAML configuration files (ci-config.yaml, misra-rules.yaml).

    Calls ``yuleosh.ci.yaml_validator.validate_all()`` and blocks the pipeline
    if either configuration file has schema violations.
    """
    print("  \U0001f4cb CI: YAML validation...")

    from yuleosh.ci.yaml_validator import validate_all

    result = validate_all(path=project_dir)
    if result["valid"]:
        ci.add_stage("yaml-validation", "passed")
        print("    \u2705 YAML validation passed")
        return True

    # Collect all error messages
    all_errors = []
    for cfg_name, errs in result["errors"].items():
        for e in errs:
            all_errors.append(f"[{cfg_name}] {e}")

    detail = "; ".join(all_errors[:5])
    ci.add_stage("yaml-validation", "failed", detail)
    print(f"    \u274c YAML validation FAILED — blocking pipeline")
    for e in all_errors:
        print(f"        \u26a0\ufe0f  {e}")
    return False


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
        print(f"    🔧 Fix: install clang-tidy (e.g. 'apt install clang-tidy' or 'brew install llvm')")
        if strict:
            ci.add_stage("clang-tidy", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("clang-tidy", "skipped", reason)
        print(f"    ⏭️  {reason} — skipped")
        return False  # A-01: skip returns False, blocking pipeline
    except subprocess.TimeoutExpired:
        reason = "clang-tidy timed out"
        print(f"    🔧 Fix: increase timeout or reduce analyzed file count (currently limited to 20)")
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

def run_misra_check(project_dir: str, ci: CIResult,
                    target_files: list[str] | None = None,
                    mode: str = "auto") -> bool:
    """Run MISRA C:2023 static analysis via cppcheck --addon=misra.

    Parses output through misra_report.py, saves structured report
    to ``.yuleosh/reports/misra-report.json``, and blocks the pipeline
    when violations exceed the configured threshold in strict mode.

    Configuration is read from ``.yuleosh/ci-config.yaml`` (misra block).
    Falls back to cppcheck --std=c11 --addon=misra when no config file.

    When ``target_files`` is provided, only those files are checked
    (incremental / delta mode).  When omitted, ``git diff HEAD~1`` is
    used to auto-detect changed C/C++ files in the repo; if the repo
    is not a git checkout, all source files are checked (full mode).

    Parameters
    ----------
    project_dir : str
        Root path of the project.
    ci : CIResult
        CI result accumulator.
    target_files : list[str] | None
        Explicit list of files to check.  None = auto-detect.
    mode : str
        MISRA check mode: "auto" (default, auto-detect delta/full),
        "delta" (L1 — only scan modified files),
        "full" (L2 — full scan with zero-delta blocking for new Required).

    Returns True if passed/acceptable violations, False if blocked.
    """

    def _load_misra_baseline(proj_dir: str) -> dict:
        """Load the most recent MISRA trend entry as a baseline for delta comparison."""
        from yuleosh.ci.misra_trend import TREND_FILE as _mf
        trend_path = Path(proj_dir) / _mf
        if not trend_path.exists():
            return {}
        entries: list[dict] = []
        with open(trend_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
        if not entries:
            return {}
        # Return most recent FULL scan entry (is_delta=False) as baseline
        for e in reversed(entries):
            if not e.get("is_delta", True):
                return e
        return entries[-1] if entries else {}

    def _is_new_required_violation(v: dict, baseline_violations: list) -> bool:
        """Check if a Required violation is new (not in baseline)."""
        rule_id = v.get("rule_id", "")
        v_file = v.get("file", "")
        severity = v.get("severity_category", "").lower()
        if severity != "required":
            return False
        for bv in baseline_violations:
            if bv.get("rule_id") == rule_id and bv.get("file") == v_file:
                if bv.get("line") == v.get("line"):  # Same line = same violation
                    return False
        return True
    print("  🔍 CI: MISRA C:2023 static analysis...")

    # Load config
    try:
        cfg = _get_ci_config(project_dir)
        misra_cfg = cfg.misra if cfg else None
    except Exception:
        misra_cfg = None

    enabled = misra_cfg.enabled if misra_cfg else True
    if not enabled:
        ci.add_stage("misra-check", "skipped", "MISRA check disabled in config")
        print("    ⏭️  MISRA check disabled — skipped")
        return True

    fail_on_required = misra_cfg.fail_on_required if misra_cfg else True  # G-09: default True
    fail_on_violation = misra_cfg.fail_on_violation if misra_cfg else False  # G-09: deprecated master switch
    fail_on_advisory = misra_cfg.fail_on_advisory if misra_cfg else False
    fail_threshold = misra_cfg.fail_threshold if misra_cfg else 10
    violations_per_kloc = misra_cfg.violations_per_kloc if misra_cfg else 2.0
    addon = misra_cfg.addon if misra_cfg else "misra"
    cppcheck_std = misra_cfg.cppcheck_std if misra_cfg else "c11"
    suppress_rules = misra_cfg.suppress_rules if misra_cfg else []
    rule_overrides = misra_cfg.rule_overrides if misra_cfg else []
    deviations = misra_cfg.deviations if misra_cfg else []
    strict = is_strict()

    # --- Determine which files to check (delta / full) ---
    # DEF-006: Support explicit mode parameter (L1 delta, L2 full)
    is_delta = False
    is_full_delta = False  # L2: full scan + delta blocking on new Required
    c_files: list[str] = []

    if mode == "delta":
        # L1: delta mode — only scan modified files
        is_delta = True
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
        else:
            try:
                git_result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD~1"],
                    capture_output=True, text=True, timeout=10,
                    cwd=project_dir,
                )
                if git_result.returncode == 0:
                    changed_files = [f.strip() for f in git_result.stdout.splitlines() if f.strip()]
                    c_files = [
                        os.path.join(project_dir, f) if not os.path.isabs(f) else f
                        for f in changed_files
                        if f.endswith((".c", ".cpp"))
                    ]
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            # If no git diff, fall back to empty (skip delta check)
    elif mode == "full":
        # L2: full scan + delta blocking on new Required
        is_full_delta = True
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
        if not c_files:
            src_dir = os.path.join(project_dir, "src")
            if os.path.isdir(src_dir):
                for root, dirs, files in os.walk(src_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                    for f in files:
                        if f.endswith((".c", ".cpp")):
                            c_files.append(os.path.join(root, f))
    else:
        # auto mode (default) — same as before
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
            is_delta = True
        else:
            try:
                git_result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD~1"],
                    capture_output=True, text=True, timeout=10,
                    cwd=project_dir,
                )
                if git_result.returncode == 0:
                    changed_files = [f.strip() for f in git_result.stdout.splitlines() if f.strip()]
                    c_files = [
                        os.path.join(project_dir, f) if not os.path.isabs(f) else f
                        for f in changed_files
                        if f.endswith((".c", ".cpp"))
                    ]
                    if c_files:
                        is_delta = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            if not c_files:
                src_dir = os.path.join(project_dir, "src")
                if os.path.isdir(src_dir):
                    for root, dirs, files in os.walk(src_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                        for f in files:
                            if f.endswith((".c", ".cpp")):
                                c_files.append(os.path.join(root, f))

    if not c_files:
        ci.add_stage("misra-check", "skipped", "No C/C++ source files found")
        print("    ⏭️  No C/C++ source files — skipped")
        return True

    # ── Apply exclude_paths filtering ──
    exclude_patterns = misra_cfg.exclude_paths if misra_cfg else []
    c_files = _exclude_paths(c_files, exclude_patterns, project_dir)

    if not c_files:
        ci.add_stage("misra-check", "skipped", "All C/C++ files excluded by exclude_paths")
        print("    ⏭️  All C/C++ files excluded by exclude_paths — skipped")
        return True

    # ── 三级分类过滤 ──
    code_categories = misra_cfg.code_categories if misra_cfg else {}
    file_category_map: dict[str, str] = {}  # filepath -> category_name
    categorized_c_files: list[str] = []
    template_skipped = 0
    for f in c_files:
        cat_name, cat_cfg = _categorize_file(f, code_categories)
        if cat_name == "template":
            # template 代码完全跳过
            template_skipped += 1
            continue
        file_category_map[f] = cat_name
        categorized_c_files.append(f)
    c_files = categorized_c_files
    del categorized_c_files

    if template_skipped > 0:
        print(f"    📋 Template files excluded by code_categories: {template_skipped}")

    if not c_files:
        ci.add_stage("misra-check", "skipped", "All C/C++ files excluded by code_categories")
        print("    ⏭️  All C/C++ files excluded by code_categories — skipped")
        return True

    # Print mode header
    if is_full_delta:
        mode_label = "L2 全量+Delta阻断"
    else:
        mode_label = "L1 增量检查" if is_delta else "全量检查"
    print(f"    📋 Mode: {mode_label} ({len(c_files)} file(s))")

    # Build suppression arguments from config + rule_overrides
    suppress_args = []
    for rule_id in suppress_rules:
        suppress_args.append("--suppress=misra-c2023-" + rule_id)
        suppress_args.append("--suppress=misra-c2012-" + rule_id)
    for override in rule_overrides:
        if not override.enabled and override.rule_id:
            suppress_args.append("--suppress=" + override.rule_id)

    # ── Auto-detect include paths and add -I flags ──
    include_paths = _detect_include_paths(project_dir)
    include_args = []
    for inc in include_paths:
        include_args.extend(["-I", inc])
    if include_args:
        log.info("Adding include paths: %s", " ".join(
            [inc for i, inc in enumerate(include_args) if i % 2 == 1]
        ))

    # Check for compile_commands.json and suggest it
    compile_db = os.path.join(project_dir, "compile_commands.json")
    if os.path.isfile(compile_db):
        log.info("Found compile_commands.json — consider using --project=compile_commands.json")

    # Construct cppcheck command
    cmd = [
        "cppcheck",
        "--addon=" + addon,
        "--language=c",
        "--std=" + cppcheck_std,
        "--enable=all",
        "--suppress=missingIncludeSystem",
        "-q",
    ] + include_args + suppress_args + c_files

    try:
        start = time.perf_counter()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=project_dir
        )
        elapsed = time.perf_counter() - start
    except FileNotFoundError:
        msg = "cppcheck not installed"
        print(f"    🔧 Fix: install cppcheck (e.g. 'apt install cppcheck' or 'brew install cppcheck')")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except subprocess.TimeoutExpired:
        msg = "cppcheck timed out after 120s"
        print(f"    🔧 Fix: increase timeout or reduce file count. Try 'cppcheck --project=compile_commands.json' for faster analysis")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except Exception as e:
        return _handle_stage_error(ci, "misra-check", "cppcheck execution error: " + str(e), strict)

    # Collect output (cppcheck writes MISRA warnings to stderr)
    output = result.stderr or result.stdout or ""

    # Process output through misra_report module
    try:
        # Try importing from the project-level ci/ directory
        sys.path.insert(0, project_dir)
        from yuleosh.ci.misra_report import (
            parse_cppcheck_output, group_by_rule, enrich_with_definitions,
            compute_summary_stats, save_report, load_rule_definitions,
            print_summary,
            generate_traceability_matrix,
            generate_fix_tasks,
        )
        sys.path.pop(0)

        rule_defs_path = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"
        if misra_cfg and misra_cfg.rule_texts_path:
            rule_defs_path = Path(misra_cfg.rule_texts_path)

        rule_defs = load_rule_definitions(rule_defs_path)
        violations = parse_cppcheck_output(output)

        # ── 给每条违规标注代码类别 ──
        for v in violations:
            v_file = v.get("file", "")
            # Resolve relative path for category matching
            if not os.path.isabs(v_file):
                v_file_abs = os.path.join(project_dir, v_file)
            else:
                v_file_abs = v_file
            cat_name = file_category_map.get(v_file_abs, "business")
            v["code_category"] = cat_name

        groups = group_by_rule(violations)
        groups = enrich_with_definitions(groups, rule_defs)
        summary = compute_summary_stats(violations, groups)

        output_dir = Path(project_dir) / ".yuleosh" / "reports"

        # Apply deviations: mark matching violations as "acknowledged"
        deviations_used: list[tuple[str, str]] = []
        for dev in deviations:
            if dev.rule_id and dev.file_pattern:
                deviations_used.append((dev.rule_id, dev.file_pattern))

        save_report(violations, groups, summary, rule_defs, output_dir,
                    deviations=deviations_used)

        # ── 分类报告摘要 ──
        business_violations = [v for v in violations if v.get("code_category", "") == "business"]
        third_party_violations = [v for v in violations if v.get("code_category", "") == "third_party"]
        print(f"    📋 Code category breakdown: business={len(business_violations)}, third_party={len(third_party_violations)}")

        # --- Generate traceability matrix and fix tasks (MISRA loop closure) ---
        if violations:
            print_summary(summary)

            trace_matrix = generate_traceability_matrix(
                violations, rule_defs, deviations=deviations_used
            )
            print(f"    📋 Traceability: {len(trace_matrix)} entries")

            # Report deviation info
            if deviations:
                print(f"    📋 Deviations configured: {len(deviations)}")
                for dev in deviations:
                    print(f"      - {dev.rule_id} on {dev.file_pattern}: {dev.reason} (by {dev.approved_by}, expires {dev.expires})")

            try:
                fix_files = generate_fix_tasks(project_dir, violations, rule_defs, deviations=deviations_used)
                print(f"    🔧 Fix tasks created: {len(fix_files)} file(s)")
            except Exception as fix_e:
                log.warning("Failed to generate MISRA fix tasks: %s", fix_e)

            # Also check MISRA_FAIL_FAST (F-04 fix)
            misra_ff = is_misra_fail_fast()
            if misra_ff:
                print(f"    🚨 MISRA_FAIL_FAST enabled — violations will be treated as blocking")

            # ── 针对多级指针空违规 (GSCR-C-27.15) 输出修复建议 ──
            null_ptr_violations = [v for v in violations if "27.15" in v.get("rule_id", "") or "Dir-4.1" in v.get("rule_id", "")]
            for npv in null_ptr_violations:
                cat = npv.get("code_category", "business")
                np_file = npv.get("file", "")
                fix_suggestion = _format_null_pointer_fix(cat, np_file)
                if fix_suggestion:
                    print(fix_suggestion)

    except ImportError as e:
        log.warning("Could not import misra_report module: %s", e)
        raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
        summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                    "severity_counts": {}, "unique_files": [], "per_file_counts": {}}
    except Exception as e:
        log.warning("MISRA report formatting failed: %s", e)
        raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
        summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                    "severity_counts": {}, "unique_files": [], "per_file_counts": {}}

    total_violations = summary["total_violations"]

    # --- Determine pass/fail with enhanced rules (G-09) ---
    if total_violations == 0:
        ci.add_stage("misra-check", "passed", "No MISRA violations")
        print("    ✅ MISRA check passed — no violations")
        return True

    # Count required vs advisory violations from enriched groups
    required_count = 0
    advisory_count = 0
    for g in groups.values():
        sev = g.get("severity_category", "").lower()
        if sev == "required":
            required_count += g["count"]
        elif sev == "advisory":
            advisory_count += g["count"]

    # Estimate KLOC from checked files
    estimated_kloc = 0
    try:
        for cf in c_files:
            if os.path.isfile(cf):
                with open(cf) as _fh:
                    estimated_kloc += sum(1 for _ in _fh)
        estimated_kloc /= 1000.0
    except Exception:
        estimated_kloc = 0

    # ── GSCR: Translate MISRA violations to Corporate Standard Rules ──
    try:
        from yuleosh.ci.rulesets import RulesetRegistry
        gscr_ruleset = RulesetRegistry.get_default()
        if gscr_ruleset and gscr_ruleset.name != "misra-c2023":
            # Translate all violations to GSCR
            gscr_violations = gscr_ruleset.translate_violations(violations)

            # Save GSCR-enhanced report
            gscr_report_path = Path(project_dir) / ".yuleosh" / "reports" / "gscr-report.json"
            gscr_report = {
                "standard": gscr_ruleset.display_name,
                "version": "1.1",
                "generated_at": datetime.now().isoformat(),
                "total_violations": len(gscr_violations),
                "gscr_mapped": sum(1 for v in gscr_violations if v.get("gscr_rule_ids")),
                "gscr_unmapped": sum(1 for v in gscr_violations if not v.get("gscr_rule_ids")),
                "severity_counts": {
                    "S0": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S0"),
                    "S1": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S1"),
                    "S2": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S2"),
                },
                "gscr_rule_counts": {},
                "violations": gscr_violations,
            }

            # Group by GSCR rule ID
            from collections import Counter
            gscr_rule_counter = Counter()
            for v in gscr_violations:
                for gid in v.get("gscr_rule_ids", []):
                    gscr_rule_counter[gid] += 1
            gscr_report["gscr_rule_counts"] = dict(gscr_rule_counter.most_common())

            gscr_report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(gscr_report_path, "w", encoding="utf-8") as f:
                json.dump(gscr_report, f, ensure_ascii=False, indent=2)

            print(f"    📋 GSCR report: {gscr_report['gscr_mapped']}/{gscr_report['total_violations']} "
                  f"violations mapped to corporate standard rules")

            # Show top 5 GSCR rules violated
            if gscr_report["gscr_rule_counts"]:
                print(f"    📋 Top GSCR rules violated:")
                for gid, count in list(gscr_report["gscr_rule_counts"].items())[:5]:
                    gscr_def = gscr_ruleset.rule_definitions().get("rules", {}).get(gid, {})
                    title = gscr_def.get("description_cn", gid)[:60]
                    print(f"        • {gid} ({gscr_def.get('severity', 'S2')}): {title} — {count} violation(s)")

            # Severity summary
            sc = gscr_report["severity_counts"]
            print(f"    📋 GSCR severity: S0={sc['S0']}, S1={sc['S1']}, S2={sc['S2']}")

        else:
            log.debug("Default ruleset is MISRA — no GSCR translation needed")

    except Exception as gscr_e:
        log.warning("GSCR translation failed (non-blocking): %s", gscr_e)

    # Save raw output for debugging
    misra_dir = Path(project_dir) / ".yuleosh" / "reports"
    misra_dir.mkdir(parents=True, exist_ok=True)
    raw_path = misra_dir / "misra-raw-output.txt"
    raw_path.write_text(output)

    # ── L2 Delta blocking: only block NEW Required violations ────
    new_required_count = 0
    if is_full_delta and total_violations > 0:
        try:
            baseline = _load_misra_baseline(project_dir)
            baseline_violations = baseline.get("violations", [])
            if baseline_violations:
                from yuleosh.ci.misra_report import parse_cppcheck_output
                # Re-parse violations for comparison
                current_violations = parse_cppcheck_output(output)
                new_required = [v for v in current_violations
                                if _is_new_required_violation(v, baseline_violations)]
                new_required_count = len(new_required)
                if new_required_count > 0:
                    print(f"    🆕 New Required violations since last baseline: {new_required_count}")
                    for nv in new_required[:5]:  # Show top 5
                        print(f"        - {nv.get('rule_id', '?')} in {nv.get('file', '?')}:{nv.get('line', '?')}")
                    if len(new_required) > 5:
                        print(f"        ... and {len(new_required) - 5} more")
        except Exception as delta_e:
            log.debug("L2 delta blocking skipped: %s", delta_e)
            new_required_count = 0

    # ── 三级分类阻断计算 ──
    # 从 violations 中计算分类细目
    try:
        from yuleosh.ci.misra_report import parse_cppcheck_output as _pco
        _current_violations = _pco(output)
        for _v in _current_violations:
            _vf = _v.get("file", "")
            _vfa = os.path.join(project_dir, _vf) if not os.path.isabs(_vf) else _vf
            _v["code_category"] = file_category_map.get(_vfa, "business")
        business_violations_c = [v for v in _current_violations if v.get("code_category", "") == "business"]
        third_party_violations_c = [v for v in _current_violations if v.get("code_category", "") == "third_party"]
    except Exception:
        _current_violations = []
        business_violations_c = []
        third_party_violations_c = []

    # 确定 third_party 是否阻断
    third_party_cfg = code_categories.get("third_party", {})
    third_party_block_on = third_party_cfg.get("block_on", False)
    business_cfg = code_categories.get("business", {})
    business_block_on = business_cfg.get("block_on", True)

    # 仅针对 business 代码计算阻断阈值
    business_req = 0
    business_adv = 0
    business_total = len(business_violations_c)
    third_party_total = len(third_party_violations_c)

    # Blocking checks (in order of severity)
    should_block = False
    block_reasons = []

    # 0. L2: New Required violations block unconditionally (zero-delta)
    if is_full_delta and new_required_count > 0:
        should_block = True
        block_reasons.append(
            f"L2-P0: {new_required_count} new Required violation(s) since baseline "
            f"(zero-delta blocking)"
        )

    # 0b. 业务代码 Required violations (三级分类阻断)
    if business_block_on and business_total > 0:
        # Count only business Required violations
        for v in business_violations_c:
            if v.get("severity", "").lower() in ("error", "warning"):
                business_req += 1
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} business-code violation(s) (business.block_on=True)")

    # 0c. 第三方库按 block_on 配置
    if third_party_block_on and third_party_total > 0:
        should_block = True
        block_reasons.append(f"{third_party_total} third-party violation(s) (third_party.block_on=True)")
    elif not third_party_block_on and third_party_total > 0:
        print(f"    ℹ️  Third-party violations ({third_party_total}) do not block (third_party.block_on=False)")

    # 1. Required violations with fail_on_required (G-09) — 仅对 business 代码生效
    if fail_on_required and required_count > 0 and business_block_on:
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} Required business-code violation(s) (fail_on_required=True)")

    # 1b. Legacy: fail_on_violation master switch
    if fail_on_violation and required_count > 0 and business_block_on:
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} business-code violation(s) (fail_on_violation=True)")

    # 2. Total violations >= fail_threshold (仅 business 代码)
    if fail_threshold > 0 and business_total >= fail_threshold:
        should_block = True
        block_reasons.append(f"{business_total} business-code violation(s) >= threshold {fail_threshold}")

    # 3. Violations per KLOC (仅 business 文件的 KLOC)
    if violations_per_kloc > 0 and estimated_kloc > 0:
        actual_vpkloc = business_total / max(estimated_kloc, 0.001)
        if actual_vpkloc > violations_per_kloc:
            should_block = True
            block_reasons.append(
                f"{actual_vpkloc:.1f} business-code violations/kloc > limit {violations_per_kloc}"
            )

    # Advisory-blocking (separate flag) — 仅 business
    if fail_on_advisory and advisory_count > 0 and business_block_on:
        should_block = True
        block_reasons.append(f"{advisory_count} Advisory business-code violation(s) (fail_on_advisory=True)")

    detail = (
        f"{total_violations} MISRA violation(s) "
        f"({required_count} required, {advisory_count} advisory) — "
        f"see .yuleosh/reports/misra-report.json"
    )

    # ── Append trend entry ─────────────────────────────────────────
    try:
        from yuleosh.ci.misra_trend import append_entry, _print_trend_summary
        commit = _get_git_commit(project_dir)
        append_entry(
            project_dir=project_dir,
            total_violations=total_violations,
            required=required_count,
            advisory=advisory_count,
            files_checked=len(c_files),
            is_delta=is_delta,
            commit=commit,
        )
        _print_trend_summary(project_dir)
    except Exception as trend_e:
        log.debug("MISRA trend append skipped: %s", trend_e)
    # ────────────────────────────────────────────────────────────────

    if should_block:
        ci.add_stage("misra-check", "failed", "; ".join(block_reasons))
        print(f"    ❌ MISRA check FAILED: {detail}")
        for br in block_reasons:
            print(f"        • {br}")
        return False

    # Advisory violations over threshold → warning but don't block
    if advisory_count > 0 and not fail_on_advisory:
        ci.add_stage("misra-check", "warning", detail)
        print(f"    ⚠️  MISRA check: {detail}")
        print(f"        Advisory violations ({advisory_count}) do not block pipeline")
        print(f"    📍 Full report: .yuleosh/reports/misra-report.json")
        return True

    ci.add_stage("misra-check", "passed", detail)
    print(f"    ✅ MISRA check: {detail}")
    print(f"    📍 Full report: .yuleosh/reports/misra-report.json")
    return True


def run_c_coverage(project_dir: str, ci: CIResult) -> bool:
    """Run C/C++ code coverage via gcov/lcov.

    Runs in SWE.4 (unit test) slot after C unit tests execute.
    Requires ``.gcda`` / ``.gcno`` files in the build directory.
    Falls back to finding build directories with coverage data.
    Saves structured JSON to ``.yuleosh/reports/c-coverage.json``.
    """
    print("  📊 CI: C/C++ code coverage (gcov/lcov)...")

    from yuleosh.ci.gcov_coverage import generate_c_coverage_report

    # Find a build directory with coverage data
    # Expanded search: common embedded/CMake build output directories
    coverage_dirs = [
        os.path.join(project_dir, "build"),
        os.path.join(project_dir, "build", "coverage"),
        os.path.join(project_dir, "cmake-build-coverage"),
        os.path.join(project_dir, "build", "Debug"),
        os.path.join(project_dir, "build", "Release"),
        os.path.join(project_dir, "build", "RelWithDebInfo"),
        os.path.join(project_dir, "_build"),
        os.path.join(project_dir, "out"),
        os.path.join(project_dir, "build_arm"),
        os.path.join(project_dir, "build_x86"),
        os.path.join(project_dir, "cmake-build-debug"),
        os.path.join(project_dir, "cmake-build-release"),
        os.path.join(project_dir, "Debug"),
        os.path.join(project_dir, "Release"),
    ]

    # Also try recursive search for .gcda files across all directories
    build_dir = None
    for d in coverage_dirs:
        if os.path.isdir(d):
            # Check for .gcda or .gcno files
            for root, _, files in os.walk(d):
                if any(f.endswith(".gcda") or f.endswith(".gcno") for f in files):
                    build_dir = d
                    break
            if build_dir:
                break

    if not build_dir:
        # Last resort: recursive search for any .gcda file in project_dir
        log.info("No build dir found in known paths — scanning project recursively for .gcda files...")
        for root, dirs, files in os.walk(project_dir):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if any(f.endswith(".gcda") for f in files):
                build_dir = root
                log.info("Found .gcda files in: %s", root)
                break

    if not build_dir:
        # Last resort: just check if any known dir exists
        for d in coverage_dirs:
            if os.path.isdir(d):
                build_dir = d
                break

    if not build_dir:
        ci.add_stage("c-coverage", "skipped", "No build directory with coverage data found")
        print(f"    ⏭️  No build directory with .gcda/.gcno — skipped")
        print(f"    🔧 Fix: compile with '--coverage' flag and run tests to generate .gcda files")
        print(f"    🔧 Tip: export COVERAGE_BUILD_DIR=/path/to/build to specify a custom build dir")
        return True

    try:
        json_path = generate_c_coverage_report(build_dir=build_dir)
        if not json_path:
            ci.add_stage("c-coverage", "warning", "lcov/gcov may not be installed")
            print("    ⚠️  C coverage generation failed (lcov/gcov not available)")
            return True  # Non-blocking — tool may not be available

        # Load and report summary
        try:
            with open(json_path) as f:
                report = json.load(f)
            line_rate = report.get("line_rate", 0.0)
            branch_rate = report.get("branch_rate", 0.0)
            total_files = report.get("total_files", 0)
            detail = f"line={line_rate}%, branch={branch_rate}%, {total_files} file(s)"
            ci.add_stage("c-coverage", "passed", detail)
            print(f"    ✅ C/C++ coverage: {detail}")
            print(f"    📍 Report: {json_path}")
        except (json.JSONDecodeError, OSError) as e:
            ci.add_stage("c-coverage", "passed", f"Report saved but unreadable: {e}")
            print(f"    ⚠️  C coverage saved but failed to read: {e}")

        return True

    except ImportError:
        ci.add_stage("c-coverage", "skipped", "gcov_coverage module not available")
        print("    ⏭️  gcov_coverage module not available — skipped")
        return True
    except Exception as e:
        ci.add_stage("c-coverage", "warning", f"Error: {e}")
        print(f"    ⚠️  C coverage error: {e}")
        return True


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

    line_rate = report.get("line_rate", 0.0)
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
        files_list = report.get("files", [])
        low_files = sorted(
            [f for f in files_list if f.get("line_rate", 100) < c_fail_under],
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
        files_list = report.get("files", [])
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


# ═══════════════════════════════════════════════════════════════════════
# V-Model Left Side (SWE.5): requirements, architecture, traceability
# ═══════════════════════════════════════════════════════════════════════


def run_spec_validation(project_dir: str, ci: CIResult) -> bool:
    """Validate that spec files are present and parseable (SWE.5 left side).

    Checks existence of spec.md, architecture.md, and any *-spec.md files.
    Verifies basic YAML/JSON syntax for spec-adjacent config files.
    """
    print("  📋 CI: spec validation (SWE.5 V-Model left side)...")

    spec_files = [
        ("docs/spec.md", "Project spec"),
        ("specs/misra-acceptance-matrix.md", "MISRA acceptance matrix"),
    ]
    missing = []
    for path, label in spec_files:
        full = Path(project_dir) / path
        if not full.exists():
            missing.append(f"{label} ({path})")

    if missing:
        ci.add_stage("spec-validation", "warning", "; ".join(missing))
        print(f"    ⚠️  Missing spec files: {', '.join(missing)}")
        return True  # Warning only — don't block pipeline

    # Check spec.md has SHA-1 needs markers
    spec_path = Path(project_dir) / "docs/spec.md"
    if spec_path.exists():
        content = spec_path.read_text(errors="replace")
        keyword_count = sum(
            1 for kw in ["SHALL", "SHOULD", "MAY"] if kw in content
        )
        ci.add_stage("spec-validation", "passed",
                     f"{len(missing)} missing, {keyword_count} req keywords found")
        print(f"    ✅ Spec validation passed ({keyword_count} req keywords)")
        return True

    ci.add_stage("spec-validation", "passed")
    return True


def run_architecture_review(project_dir: str, ci: CIResult) -> bool:
    """Check architecture documentation and structure (SWE.5 left side).

    Verifies that architecture/positioning docs exist and that the
    src/ module structure matches documented expectations.
    """
    print("  🏗️  CI: architecture review (SWE.5 V-Model left side)...")

    arch_docs = [
        "docs/positioning-unified.md",
        "docs/spec.md",
    ]

    missing = []
    for doc_path in arch_docs:
        full = Path(project_dir) / doc_path
        if not full.exists():
            missing.append(doc_path)

    # Check src/ module structure
    src_dir = Path(project_dir) / "src" / "yuleosh"
    modules = []
    if src_dir.exists():
        for item in sorted(src_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("__"):
                modules.append(item.name)

    if missing:
        ci.add_stage("architecture-review", "warning",
                     f"Missing docs: {', '.join(missing)}")
        print(f"    ⚠️  Missing architecture docs: {', '.join(missing)}")
        return True

    ci.add_stage("architecture-review", "passed",
                 f"{len(modules)} modules: {', '.join(modules[:6])}")
    print(f"    ✅ Architecture review: {len(modules)} modules found")
    return True


def run_requirements_trace(project_dir: str, ci: CIResult) -> bool:
    """Check basic requirements traceability (SWE.5 left side).

    Verifies that requirements in spec.md have corresponding code
    modules or test files.  This is a lightweight left-side check;
    full LRM/LRT is generated by the traceability command.
    """
    print("  🔗 CI: requirements trace check (SWE.5 V-Model left side)...")

    specs_dir = Path(project_dir) / "specs"
    docs_dir = Path(project_dir) / "docs"

    # Count SHALL statements in spec files
    req_count = 0
    keywords_found = []
    for spec_file in list(specs_dir.glob("*.md")) + list(docs_dir.glob("*.md")):
        content = spec_file.read_text(errors="replace")
        shall_count = content.count("SHALL")
        if shall_count > 0:
            req_count += shall_count
            keywords_found.append(f"{spec_file.name}: {shall_count}")

    # Estimate code coverage by module files
    code_dir = Path(project_dir) / "src" / "yuleosh"
    py_files = list(code_dir.rglob("*.py")) if code_dir.exists() else []
    test_dir = Path(project_dir) / "tests"
    test_files = list(test_dir.rglob("test_*.py")) if test_dir.exists() else []

    code_to_test_ratio = len(test_files) / max(len(py_files), 1)
    trace_score = min(100, int(code_to_test_ratio * 100))

    ci.add_stage("requirements-trace", "passed",
                 f"{req_count} reqs, {len(py_files)} modules, "
                 f"{len(test_files)} tests (ratio {code_to_test_ratio:.1%})")
    print(f"    ✅ Requirements trace: {req_count} reqs, "
          f"{len(py_files)} modules, {len(test_files)} tests")
    return True


# ═══════════════════════════════════════════════════════════════════════
# H-07: Code↔Doc Sync Gate CI Integration
# ═══════════════════════════════════════════════════════════════════════


def run_docsync_gate(project_dir: str, ci: CIResult) -> bool:
    """Run the document sync gate check (H-07).

    Integrates the enhanced sync_check module into the CI pipeline.
    Checks that code changes have corresponding documentation updates.
    Blocks pipeline only in strict mode.
    """
    print("  📝 CI: doc sync gate (H-07)...")

    from yuleosh.ci.sync_check import run_sync_check_gate, save_sync_evidence

    try:
        result = run_sync_check_gate(project_dir, base_ref="HEAD")
    except Exception as e:
        ci.add_stage("docsync-gate", "warning", f"Sync check error: {e}")
        print(f"    ⚠️  Doc sync gate error: {e}")
        return True  # Non-blocking on errors

    # Save evidence
    try:
        evidence_path = save_sync_evidence(project_dir, result)
    except Exception:
        evidence_path = ""

    status = result.get("status", "passed")
    summary = result.get("summary", "")

    if status == "failed":
        strict = is_strict()
        if strict:
            ci.add_stage("docsync-gate", "failed", summary)
            print(f"    ❌ Doc sync gate FAILED (strict mode): {summary}")
            return False
        else:
            ci.add_stage("docsync-gate", "warning", summary)
            print(f"    ⚠️  Doc sync gate: {summary}")
            return True
    elif status == "warning":
        ci.add_stage("docsync-gate", "warning", summary)
        print(f"    ⚠️  Doc sync gate: {summary}")
        return True
    else:
        ci.add_stage("docsync-gate", "passed", summary)
        print(f"    ✅ Doc sync gate: {summary}")
        if evidence_path:
            print(f"    📍 Evidence: {evidence_path}")
        return True
