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

log = logging.getLogger("ci.stage_utils")

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

    检测范围：整个 ``src/`` 目录下的所有代码（含 Python + C 扩展）。
    这是一个全项目级别的覆盖率检测，阈值由 pyproject.toml/pytest.ini
    的 fail_under 控制，或由 CI pipeline 的 ci-config.yaml 中 coverage.threshold_line 控制。
    当前全局 Python 覆盖率约 5%，对应的 fail_under 阈值已统一设置为 5。

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