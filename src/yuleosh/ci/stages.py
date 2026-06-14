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

from yuleosh.ci.config import is_strict, is_misra_fail_fast
from yuleosh.ci.result import CIResult, timed_stage

log = logging.getLogger("ci.stages")

def _resolve_cross_compile(
    project_dir: str,
    cross_src: str,
    build_dir: str,
    ci: "CIResult",
) -> bool:
    """Attempt cross-compilation via make or Docker fallback.

    Returns True if compilation succeeded, False otherwise.
    """
    compiled_ok = False
    make_available = False
    try:
        subprocess.run(["make", "--version"], capture_output=True, timeout=5)
        make_available = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        make_available = False

    if make_available:
        print(f"    Running: make TARGET=arm...")
        try:
            result = subprocess.run(
                ["make", "TARGET=arm"],
                capture_output=True, text=True, timeout=60,
                cwd=project_dir,
            )
            if result.returncode == 0:
                elf_files = list(Path(build_dir).glob("*.elf")) if os.path.exists(build_dir) else []
                if elf_files:
                    print(f"    ✅ Cross-compilation succeeded: {', '.join(str(e) for e in elf_files)}")
                    ci.add_stage("cross-compile", "passed", f"ARM ELF at {elf_files[0]}")
                    compiled_ok = True
                else:
                    print(f"    ⚠️  make succeeded but no .elf found in build/")
                    ci.add_stage("cross-compile", "failed", "make returned 0 but no .elf found")
            else:
                detail = result.stderr[:400] if result.stderr else result.stdout[:400]
                print(f"    ❌ make TARGET=arm failed: {detail}")
                ci.add_stage("cross-compile", "failed", f"make returned {result.returncode}: {detail}")
        except subprocess.TimeoutExpired:
            print(f"    ❌ make timed out")
            ci.add_stage("cross-compile", "failed", "make timed out")
            compiled_ok = False
    else:
        # Fallback: try Docker
        compiled_ok = _cross_compile_via_docker(project_dir, ci)
    return compiled_ok


def _cross_compile_via_docker(project_dir: str, ci: "CIResult") -> bool:
    """Cross-compile via Dockerfile.cross when make is unavailable."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        msg = "ARM cross-compilation tools not found. Install gcc-arm-none-eabi or Docker."
        print(f"    ❌ Cross-compilation FAILED: no ARM toolchain, no make, no Docker")
        ci.add_stage("cross-compile", "failed", msg)
        return False

    print(f"    make not available, trying Docker (Dockerfile.cross)...")
    try:
        subprocess.run(
            ["docker", "build", "-t", "yuleosh-cross", "-f", "Dockerfile.cross", "."],
            capture_output=True, text=True, timeout=120, cwd=project_dir,
        )
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{project_dir}:/work",
             "yuleosh-cross", "make", "TARGET=arm"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"    ✅ Docker cross-compilation succeeded")
            ci.add_stage("cross-compile", "passed", "ARM ELF via Docker")
            return True
        else:
            detail = result.stderr[:400] if result.stderr else result.stdout[:400]
            print(f"    ❌ Docker cross-compilation failed: {detail}")
            ci.add_stage("cross-compile", "failed", f"Docker make failed: {detail}")
            return False
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"    ❌ Docker error: {e}")
        ci.add_stage("cross-compile", "failed", f"Docker error: {e}")
        return False


def _handle_stage_error(ci, stage: str, reason: str, strict: bool) -> bool:
    """Record a stage error with strict-mode awareness. Returns True if blocked."""
    if strict:
        ci.add_stage(stage, "failed", reason)
        print(f"    ❌ {reason} (strict mode)")
    else:
        ci.add_stage(stage, "skipped", reason)
        print(f"    ⏭️  {reason} — blocked (missing tool)")
    return False  # All tool errors block per A-01


def _run_subprocess(
    cmd: list[str],
    cwd: str,
    timeout: int = 60,
) -> tuple[bool, str, str]:
    """Run a subprocess with unified error handling.

    Returns (success, stdout_summary, error_detail).
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        if result.returncode == 0:
            return True, result.stdout[:200], ""
        return False, result.stdout[:200], result.stderr[:400]
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


# ------------------------------------------------------------------
# Test file discovery cache — keyed by project_dir, invalidated on mtime
# ------------------------------------------------------------------

_test_file_cache: dict = {}
_test_file_cache_mtime: dict = {}


def get_cache_key_for_dir(project_dir: str) -> str:
    """Build a cache key that changes when test files or dirs change.

    Uses a simple hash of all .py / _test.go files and test directories.
    """
    import hashlib
    h = hashlib.md5()
    # Walk once to collect relevant paths and their mtimes
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") 
                   and d not in ("node_modules", "__pycache__", "venv")]
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                h.update(f.encode())
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    h.update(str(mtime).encode())
                except OSError:
                    pass
            elif f.endswith("_test.go"):
                h.update(f.encode())
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    h.update(str(mtime).encode())
                except OSError:
                    pass
    return h.hexdigest()

# Notifications (optional import)
_notify = None
try:
    from notify import notify_ci as _notify_ci
    _notify = _notify_ci
except ImportError:
    _notify = None




def find_test_files(project_dir: str) -> list[str]:
    """Auto-discover test files with mtime-based caching.

    Caches results keyed by a hash of file names + mtimes, so
    repeated scans only walk the filesystem when files change.
    """
    # Build cache key
    cache_key = get_cache_key_for_dir(project_dir)
    cached = _test_file_cache.get(cache_key)
    if cached is not None:
        return cached

    tests = []
    for root, dirs, files in os.walk(project_dir):
        # Skip hidden dirs and common non-source dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") 
                   and d not in ("node_modules", "__pycache__", "venv")]
        
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                tests.append(os.path.join(root, f))
            elif f.startswith("Test") and f.endswith(".java"):
                tests.append(os.path.join(root, f))
            elif f.endswith("_test.go"):
                tests.append(os.path.join(root, f))
            elif "_test." in f and (f.endswith(".c") or f.endswith(".cpp")):
                tests.append(os.path.join(root, f))
    
    # Cache result
    _test_file_cache[cache_key] = tests
    return tests


@timed_stage
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


@timed_stage
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


@timed_stage
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


@timed_stage
def _should_skip_coverage() -> bool:
    """Check if coverage should be skipped (pre-commit hook or nested run)."""
    hook_type = os.environ.get("HOOK_TYPE", "")
    if hook_type == "commit":
        return True
    if os.environ.get("COVERAGE_RUN") == "1":
        return True
    return False


def _coverage_skip_reason() -> str:
    """Return the human-readable skip reason."""
    if os.environ.get("HOOK_TYPE") == "commit":
        return "HOOK_TYPE=commit — skip coverage, runs on push"
    if os.environ.get("COVERAGE_RUN") == "1":
        return "Skipped to prevent recursion"
    return ""


def _run_coverage_and_export(project_dir: str) -> tuple[bool, str]:
    """Run ``coverage run`` + ``coverage json``.

    Returns (success, error_detail).
    """
    cov_env = {**os.environ, "COVERAGE_RUN": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "--branch", "--source=src",
         "-m", "pytest", "-q", "--tb=short", "tests/"],
        capture_output=True, text=True, timeout=120, cwd=project_dir, env=cov_env,
    )
    if result.returncode != 0:
        return False, f"coverage run returned non-zero ({result.returncode}): {result.stderr[:200]}"

    result2 = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "--pretty"],
        capture_output=True, text=True, timeout=30, cwd=project_dir,
    )
    if result2.returncode != 0:
        return False, f"coverage json returned non-zero ({result2.returncode}): {result2.stderr[:200]}"

    return True, ""


def _load_coverage_json(project_dir: str) -> tuple[float, float]:
    """Parse coverage.json and return (line_pct, condition_pct)."""
    json_file_path = os.path.join(project_dir, "coverage.json")
    with open(json_file_path) as f:
        cov_data = json.loads(f.read())
    totals = cov_data.get("totals", {})
    line_pct = totals.get("percent_covered", 0)
    cond_pct = totals.get("percent_covered_condition", line_pct)
    return line_pct, cond_pct


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


@timed_stage
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




def _detect_hil_target(project_dir: str, ci: "CIResult", mock_mode: bool, strict: bool) -> bool:
    """Stage 1: Detect hardware target (real or mock). Returns True on success."""
    print("  🎯 CI: HIL target detection...")
    try:
        sys.path.insert(0, os.path.join(project_dir, "src", "cross"))
        sys.path.insert(0, os.path.join(project_dir, "src"))

        if mock_mode:
            print(f"    ✅ Mock mode — hardware detection skipped")
            ci.add_stage("target-detect", "passed", "mock mode")
            return True

        from cross.target_config import discover_targets
        targets = discover_targets(project_dir)
        if targets:
            target_names = list(targets.keys())
            print(f"    ✅ Found {len(targets)} target(s): {', '.join(target_names)}")
            ci.add_stage("target-detect", "passed", f"{len(target_names)} targets")
        else:
            print(f"    ⚠️  No hardware targets configured in .yuleosh/targets/")
            ci.add_stage("target-detect", "warning", "no targets")
        return True
    except ImportError as e:
        msg = f"Cannot import target detection: {e}"
        ci.add_stage("target-detect", "warning", msg)
        print(f"    ⚠️  {msg}")
        return True
    except Exception as e:
        msg = f"Target detection error: {e}"
        if strict:
            ci.add_stage("target-detect", "failed", msg)
            print(f"    ❌ {msg}")
            return False
        ci.add_stage("target-detect", "warning", msg)
        print(f"    ⚠️  {msg}")
        return True


def _run_hil_mock_tests(ci: "CIResult", hw_cfg, scripts_full: str, boot_pattern: str) -> list[dict]:
    """Run simulated (mock) HIL tests — no real hardware needed."""
    import time as t_mod
    mock_start = t_mod.monotonic()
    t_mod.sleep(0.1)
    mock_duration = t_mod.monotonic() - mock_start

    results = [{
        "test": "mock-boot-test",
        "passed": True,
        "flash": {"passed": True, "tool": "mock"},
        "boot_log": f"{boot_pattern}\nSystem ready\n",
        "duration": round(mock_duration, 2),
    }]

    script_files = list(Path(scripts_full).glob("*.yaml")) if os.path.exists(scripts_full) else []
    for script_file in script_files:
        results.append({
            "test": script_file.name, "passed": True,
            "flash": {"passed": True, "tool": "mock"},
            "boot_log": f"(mock) processed {script_file.name}", "duration": 0.01,
        })

    print(f"    ✅ Mock HIL: {len(results)} test(s) simulated")
    return results


def _run_hil_real_tests(ci: "CIResult", hw_cfg, firmware_full: str, strict: bool,
                        boot_pattern: str) -> list[dict]:
    """Run real HIL tests — flash firmware and assert serial output."""
    try:
        from cross.flash import flash_firmware
        from cross.hil_runner import hil_test
    except ImportError as e:
        print(f"    ❌ Cannot import HIL modules: {e}")
        if strict:
            ci.errors.append(f"hil-import-failed: {e}")
        return []

    flash_tool = hw_cfg.flash_tool if hw_cfg else "auto"
    serial_port = hw_cfg.serial_port if hw_cfg else ""
    baud = hw_cfg.baud if hw_cfg else 115200
    boot_delay = hw_cfg.boot_delay if hw_cfg else 2.0
    test_timeout = hw_cfg.test_timeout if hw_cfg else 30

    if not os.path.exists(firmware_full):
        print(f"    ⏭️  Firmware not found: {firmware_full}")
        return []

    result = hil_test(
        firmware=firmware_full, expect_pattern=boot_pattern,
        flash_tool=flash_tool, serial_port=serial_port,
        baud=baud, boot_delay=boot_delay, timeout=test_timeout,
    )
    entry = {
        "test": "hil-boot-test",
        "passed": result.passed,
        "flash": {
            "passed": result.flash_result.passed if result.flash_result else False,
            "tool": result.flash_result.tool if result.flash_result else "",
        },
        "boot_log": result.boot_log,
        "duration": result.phase_timings.get("total", 0),
    }
    print(f"    {'✅' if result.passed else '❌'} HIL boot test: {boot_pattern}")
    return [entry]


def _record_hil_results(ci: "CIResult", results: list[dict]) -> bool:
    """Record HIL test results into CI stages. Returns True if all passed."""
    if not results:
        return True
    failures = [r for r in results if not r["passed"]]
    if failures:
        ci.add_stage("hil-tests", "failed", f"{len(failures)}/{len(results)} test(s) failed")
        for f in failures:
            print(f"    ❌ {f['test']}: FAILED")
        return False
    ci.add_stage("hil-tests", "passed", f"{len(results)} test(s) passed")
    return True


def _save_hil_report(project_dir: str, all_passed: bool, commit: str,
                     mock_mode: bool, boot_pattern: str) -> dict:
    """Stage 3: Save HIL report to disk and return report dict."""
    print("  📋 CI: HIL report...")
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "layer": 25, "commit": commit,
        "timestamp": datetime.now().isoformat(),
        "passed": all_passed,
        "config": {"mock_mode": mock_mode, "boot_pattern": boot_pattern},
    }
    report_path = ci_dir / f"hil-report-{commit}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"    ✅ HIL report saved to {report_path}")
    return report


# ------------------------------------------------------------------




def _find_c_sources(project_dir: str) -> tuple[list[str], str, str]:
    """Find C/C++ source files and cross-compile paths."""
    src_dir = os.path.join(project_dir, "src")
    c_files = []
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith((".c", ".cpp")):
                c_files.append(os.path.join(root, f))
    cross_src = os.path.join(project_dir, "src", "cross", "hello.c")
    build_dir = os.path.join(project_dir, "build")
    return c_files, cross_src, build_dir


def _cross_compile_stage(project_dir: str, cross_src: str, build_dir: str, ci) -> bool:
    """Stage 1: Cross-compilation check. Returns True if passed/skipped."""
    print("  🔧 CI: cross-compilation check...")
    if not os.path.exists(cross_src):
        print(f"    ⏭️  No cross-compile test source (src/cross/hello.c)")
        ci.add_stage("cross-compile", "skipped", "No src/cross/hello.c")
        return True

    compiled_ok = _resolve_cross_compile(project_dir, cross_src, build_dir, ci)
    if not compiled_ok:
        return False
    return True


def _static_analysis_stage(c_files: list[str], project_dir: str, ci, misra_ff: bool, strict: bool) -> bool:
    """Stage 2: Static analysis via cppcheck. Returns True if passed/skipped."""
    print("  🔎 CI: static analysis...")
    if not c_files:
        ci.add_stage("static-analysis", "skipped", "No C/C++ sources")
        print(f"    ⏭️  No C/C++ sources")
        return True

    success, stdout, stderr = _run_subprocess(
        ["cppcheck", "--enable=all", "--suppress=missingIncludeSystem", "-q"] + c_files[:30],
        project_dir, timeout=30,
    )
    if stderr.startswith("Command not found"):
        return _handle_stage_error(ci, "static-analysis", "cppcheck not installed", strict)
    if stderr.startswith("Command timed out"):
        return _handle_stage_error(ci, "static-analysis", "cppcheck timed out", strict)

    if success:
        ci.add_stage("static-analysis", "passed")
        print(f"    ✅ cppcheck passed")
        return True

    detail = stderr[:500] if stderr else stdout[:500]
    issue_type = "failed (MISRA_FAIL_FAST)" if misra_ff else "failed"
    ci.add_stage("static-analysis", issue_type, detail)
    print(f"    ❌ cppcheck found issues")
    return False


def _integration_test_stage(project_dir: str, ci) -> bool:
    """Stage 4: Integration tests. Returns True if passed/skipped."""
    print("  🔗 CI: integration tests...")
    int_test_dir = os.path.join(project_dir, "tests", "integration")
    if not os.path.exists(int_test_dir):
        ci.add_stage("integration-tests", "skipped", "No integration tests")
        print(f"    ⏭️  No integration tests directory")
        return True

    success, stdout, stderr = _run_subprocess(
        [sys.executable, "-m", "pytest", int_test_dir, "-x", "-q"],
        project_dir, timeout=60,
    )
    if stderr.startswith("Command not found"):
        ci.add_stage("integration-tests", "skipped", "pytest not installed")
        print(f"    ⏭️  pytest not installed — blocked")
        return False
    if stderr.startswith("Command timed out"):
        ci.add_stage("integration-tests", "skipped", "Integration tests timed out")
        print(f"    ⏭️  Tests timed out — blocked")
        return False

    if success:
        ci.add_stage("integration-tests", "passed")
        print(f"    ✅ Integration tests passed")
        return True

    ci.add_stage("integration-tests", "failed", stdout[:200])
    print(f"    ❌ Integration tests failed")
    return False


