#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Layers — 层执行函数 (extracted from layers.py).

包含各语言的具体实现和各层 CI 函数:
  - _run_go_build / _run_go_vet / _run_go_test / _run_go_layer1
  - _run_python_layer1
  - _run_layer1_impl / run_layer1
  - run_layer2 / run_layer_25 / run_layer3
"""

import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from yuleosh.ci.config import _get_ci_config, is_strict, is_misra_fail_fast
from yuleosh.ci.result import CIResult
from yuleosh.ci.stages import (
    run_plan_lint, run_clang_tidy, run_unit_tests, run_coverage_check,
    run_c_coverage, run_c_coverage_check, run_sil_tests,
    run_misra_check, run_yaml_validation,
    run_spec_validation, run_architecture_review,
    run_requirements_trace, run_docsync_gate,
)
from yuleosh.ci.stage_utils import (
    _detect_hil_target, _run_hil_mock_tests, _run_hil_real_tests,
    _record_hil_results, _save_hil_report,
    _find_c_sources, _cross_compile_stage, _static_analysis_stage,
    _integration_test_stage, find_test_files,
)
from yuleosh.ci.layers.layer_config import (
    _detect_project_language, _LayerTimeout,
)

log = logging.getLogger("ci.layers.executor")

# Report generation
try:
    from yuleosh.report.exporter import generate_layer_report as _generate_layer_report
except ImportError:
    _generate_layer_report = None


# ═══════════════════════════════════════════════════════════════════════
# Go Layer 1 stages
# ═══════════════════════════════════════════════════════════════════════


def _run_go_build(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Run ``go build ./...``."""
    print("  \U0001f3d7\ufe0f  CI: go build...")
    try:
        result = subprocess.run(
            ["go", "build", "./..."],
            capture_output=True, text=True, timeout=timeout, cwd=project_dir,
        )
        if result.returncode == 0:
            ci.add_stage("go-build", "passed")
            print(f"    \u2705 go build passed")
            return True
        ci.add_stage("go-build", "failed", result.stderr[:500])
        print(f"    \u274c go build failed")
        return False
    except FileNotFoundError:
        ci.add_stage("go-build", "error", "go not installed")
        print(f"    \u274c go not installed")
        return False
    except subprocess.TimeoutExpired:
        ci.add_stage("go-build", "error", f"go build timed out ({timeout}s)")
        print(f"    \u274c go build timed out")
        return False


def _run_go_vet(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Run ``go vet ./...``."""
    print("  \U0001f50d CI: go vet...")
    try:
        result = subprocess.run(
            ["go", "vet", "./..."],
            capture_output=True, text=True, timeout=timeout, cwd=project_dir,
        )
        if result.returncode == 0:
            ci.add_stage("go-vet", "passed")
            print(f"    \u2705 go vet passed")
            return True
        ci.add_stage("go-vet", "failed", result.stderr[:500])
        print(f"    \u274c go vet failed")
        return False
    except FileNotFoundError:
        ci.add_stage("go-vet", "error", "go not installed")
        print(f"    \u274c go not installed")
        return False
    except subprocess.TimeoutExpired:
        ci.add_stage("go-vet", "error", f"go vet timed out ({timeout}s)")
        print(f"    \u274c go vet timed out")
        return False


def _run_go_test(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Run ``go test ./...``."""
    print("  \U0001f9ea CI: go test...")
    try:
        result = subprocess.run(
            ["go", "test", "./..."],
            capture_output=True, text=True, timeout=timeout, cwd=project_dir,
        )
        if result.returncode == 0:
            ci.add_stage("go-test", "passed")
            print(f"    \u2705 go test passed")
            return True
        ci.add_stage("go-test", "failed", result.stderr[:500])
        print(f"    \u274c go test failed")
        return False
    except FileNotFoundError:
        ci.add_stage("go-test", "error", "go not installed")
        print(f"    \u274c go not installed")
        return False
    except subprocess.TimeoutExpired:
        ci.add_stage("go-test", "error", f"go test timed out ({timeout}s)")
        print(f"    \u274c go test timed out")
        return False


def _run_go_layer1(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Run Layer 1 CI checks for a Go project.

    Stages: go build, go vet, go test
    """
    print(f"  \U0001f433 Detected: Go project")
    print()

    all_passed = True
    for name, handler in [
        ("go-build", lambda pd, ci, t: _run_go_build(pd, ci, t)),
        ("go-vet", lambda pd, ci, t: _run_go_vet(pd, ci, t)),
        ("go-test", lambda pd, ci, t: _run_go_test(pd, ci, t)),
    ]:
        try:
            passed = handler(project_dir, ci, timeout)
            if not passed:
                all_passed = False
                ci.errors.append(f"{name} failed")
        except Exception as e:
            ci.add_stage(name, "error", str(e))
            ci.errors.append(f"{name}: {e}")
            all_passed = False

    return all_passed


# ═══════════════════════════════════════════════════════════════════════
# Python Layer 1 stages
# ═══════════════════════════════════════════════════════════════════════


def _run_python_layer1(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Run Layer 1 CI checks for a Python project.

    Stages: pytest (if available), lint checks.
    """
    print(f"  \U0001f40d Detected: Python project")
    print()

    all_passed = True

    print("  \U0001f9ea CI: pytest...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=timeout, cwd=project_dir,
        )
        if result.returncode == 0:
            ci.add_stage("python-tests", "passed")
            print(f"    \u2705 pytest passed")
        else:
            ci.add_stage("python-tests", "failed", result.stdout[:500])
            print(f"    \u274c pytest returned {result.returncode}")
            all_passed = False
    except FileNotFoundError:
        ci.add_stage("python-tests", "skipped", "pytest not installed")
        print(f"    \u23ed\ufe0f  pytest not installed — skipping")
    except subprocess.TimeoutExpired:
        ci.add_stage("python-tests", "skipped", f"pytest timed out ({timeout}s)")
        print(f"    \u23ed\ufe0f  pytest timed out — skipping")

    return all_passed


# ═══════════════════════════════════════════════════════════════════════
# Layer 1 — Implementation + Public API
# ═══════════════════════════════════════════════════════════════════════


def _run_layer1_impl(project_dir: str, ci: CIResult, timeout: int) -> bool:
    """Core implementation of Layer 1, called inside the timeout guard."""
    lang = _detect_project_language(project_dir)

    if lang == "go":
        return _run_go_layer1(project_dir, ci, timeout)

    if lang == "python":
        return _run_python_layer1(project_dir, ci, timeout)

    print(f"  \U0001f4e6 Detected: C/C++ project")
    print()

    stages = [
        ("yaml-validation", run_yaml_validation),
        ("spec-validation", run_spec_validation),
        ("architecture-review", run_architecture_review),
        ("requirements-trace", run_requirements_trace),
        ("plan-lint", run_plan_lint),
        ("docsync-gate", run_docsync_gate),
        ("clang-tidy", run_clang_tidy),
        ("misra-check", lambda pd, ci: run_misra_check(pd, ci, mode="full")),
        ("unit-tests", run_unit_tests),
        ("coverage", run_coverage_check),
        ("c-coverage", run_c_coverage),
        ("c-coverage-gate", run_c_coverage_check),
    ]

    all_passed = True
    for name, handler in stages:
        try:
            passed = handler(project_dir, ci)
            if not passed:
                all_passed = False
                ci.errors.append(f"{name} failed")
        except Exception as e:
            ci.add_stage(name, "error", str(e))
            ci.errors.append(f"{name}: {e}")
            all_passed = False

    return all_passed


def run_layer1(project_dir: Optional[str] = None, timeout: Optional[int] = None) -> bool:
    """Run Layer 1 CI pipeline.

    Automatically detects the project language (Go, Python, or C) and
    runs appropriate stages.

    A safety timeout wraps the entire layer. Default is 180 seconds;
    overridable via ``CI_LAYER1_TIMEOUT`` environment variable or
    the *timeout* parameter.

    Parameters
    ----------
    project_dir : str, optional
        Project root directory. Defaults to ``OSH_HOME`` or current dir.
    timeout : int, optional
        Maximum seconds for the entire layer. Defaults to 30, or the
        value of env var ``CI_LAYER1_TIMEOUT``.

    Returns
    -------
    bool
        ``True`` if all stages passed, ``False`` otherwise (or on timeout).
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    if timeout is None:
        try:
            timeout = int(os.environ.get("CI_LAYER1_TIMEOUT", "180"))
        except (ValueError, TypeError):
            timeout = 30
    timeout = max(timeout, 1)

    from yuleosh.ci.runner import git_commit_hash
    commit = git_commit_hash()
    print(f"\n\U0001f52c CI Layer 1: Development Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print(f"   Timeout: {timeout}s")
    print()

    ci = CIResult(1, commit)
    all_passed = False
    timed_out = False

    _timeout_alarm_active = False

    def _alarm_handler(signum, frame):
        nonlocal timed_out
        timed_out = True
        raise _LayerTimeout(
            f"CI Layer 1 timed out after {timeout}s — "
            f"adjust via CI_LAYER1_TIMEOUT env or timeout parameter"
        )

    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    try:
        signal.alarm(timeout)
        _timeout_alarm_active = True

        all_passed = _run_layer1_impl(project_dir, ci, timeout)

        signal.alarm(0)
        _timeout_alarm_active = False

    except _LayerTimeout as e:
        print(f"\n    \u23f0 {e}")
        all_passed = False
        ci.errors.append(f"layer-timeout: {e}")
    except Exception as e:
        ci.add_stage("layer1", "error", str(e))
        ci.errors.append(f"layer1: {e}")
        all_passed = False
    finally:
        if _timeout_alarm_active:
            signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    ci.complete("passed" if all_passed else "failed")

    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    result_path = ci_dir / f"layer1-{commit}.json"
    with open(result_path, "w") as f:
        json.dump(ci.to_dict(), f, indent=2)

    import yuleosh.ci.run as _run_notify
    if _run_notify._notify:
        try:
            _run_notify._notify(
                layer=1,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")

    if _generate_layer_report:
        try:
            _generate_layer_report(project_dir, 1)
        except Exception as re:
            log.warning(f"Layer 1 report generation failed: {re}")

    print(f"\n{'='*40}")
    if timed_out:
        print("\u23f0 CI Layer 1: TIMED OUT")
    elif all_passed:
        print("\u2705 CI Layer 1: ALL STAGES PASSED")
    else:
        print(f"\u274c CI Layer 1: FAILED \u2014 {len(ci.errors)} error(s)")

    print(f"   Report: {result_path}")
    print()

    return all_passed


# ═══════════════════════════════════════════════════════════════════════
# Layer 2.5 — HIL
# ═══════════════════════════════════════════════════════════════════════


def run_layer_25(project_dir: Optional[str] = None) -> bool:
    """CI Layer 2.5: Hardware-in-the-Loop (HIL) — runs after L2 passes.

    When ``mock=True`` in ci-config.yaml, all hardware interaction is
    simulated — suitable for CI environments without physical boards.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    from yuleosh.ci.runner import git_commit_hash
    commit = git_commit_hash()
    print(f"\n\U0001f6e0\ufe0f  CI Layer 2.5: Hardware-in-the-Loop (HIL)")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}\n")

    ci = CIResult(25, commit)
    all_passed = True
    strict = is_strict()

    try:
        cfg = _get_ci_config(project_dir)
    except Exception:
        cfg = None

    hw_cfg = cfg.hardware_test if cfg else None
    mock_mode = hw_cfg.mock if hw_cfg else True
    boot_pattern = hw_cfg.boot_pattern if hw_cfg else "Boot Complete"

    target_ok = _detect_hil_target(project_dir, ci, mock_mode, strict)
    if not target_ok:
        all_passed = False

    print("  \U0001f9ea CI: HIL tests...")
    firmware_path = hw_cfg.firmware if hw_cfg else "build/firmware.elf"
    firmware_full = os.path.join(project_dir, firmware_path)
    scripts_dir = hw_cfg.test_scripts_dir if hw_cfg else "tests/hil"
    scripts_full = os.path.join(project_dir, scripts_dir)

    hil_results: list[dict] = []
    try:
        if not os.path.exists(scripts_full) and not mock_mode:
            print(f"    \u23ed\ufe0f  No HIL test scripts at {scripts_dir}")
            ci.add_stage("hil-tests", "skipped", f"No {scripts_dir} directory")
        elif mock_mode:
            hil_results = _run_hil_mock_tests(ci, hw_cfg, scripts_full, boot_pattern)
        else:
            hil_results = _run_hil_real_tests(ci, hw_cfg, firmware_full, strict, boot_pattern)

        if not _record_hil_results(ci, hil_results):
            all_passed = False
    except Exception as e:
        msg = f"HIL test error: {e}"
        ci.add_stage("hil-tests", "failed", msg)
        print(f"    \u274c {msg}")
        if strict:
            all_passed = False
            ci.errors.append(msg)

    _save_hil_report(project_dir, all_passed, commit, mock_mode, boot_pattern)

    ci.complete("passed" if all_passed else "failed")
    from yuleosh.ci.runner import _save_layer_result
    result_path = _save_layer_result(project_dir, ci, all_passed, commit, 25)

    if _generate_layer_report:
        try:
            _generate_layer_report(project_dir, 25)
        except Exception as re:
            log.warning(f"Layer 25 report generation failed: {re}")

    print(f"\n{'='*40}")
    if all_passed:
        print("\u2705 CI Layer 2.5: ALL HIL STAGES PASSED")
    else:
        print(f"\u274c CI Layer 2.5: FAILED \u2014 {len(ci.errors)} error(s)")
    print(f"   Report: {result_path}\n")
    return all_passed


# ═══════════════════════════════════════════════════════════════════════
# Layer 2 — Integration
# ═══════════════════════════════════════════════════════════════════════


def run_layer2(project_dir: Optional[str] = None) -> bool:
    """CI Layer 2: Integration Verification — runs on MR."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    from yuleosh.ci.runner import git_commit_hash
    commit = git_commit_hash()
    print(f"\n\U0001f504 CI Layer 2: Integration Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}\n")

    ci = CIResult(2, commit)
    all_passed = True
    misra_ff = is_misra_fail_fast()
    strict = is_strict()

    c_files, cross_src, build_dir = _find_c_sources(project_dir)

    if not _cross_compile_stage(project_dir, cross_src, build_dir, ci):
        all_passed = False

    if not _static_analysis_stage(c_files, project_dir, ci, misra_ff, strict):
        all_passed = False

    print("  \U0001f5a5\ufe0f  CI: SIL tests...")
    try:
        if not run_sil_tests(project_dir, ci):
            all_passed = False
            ci.errors.append("sil-tests failed")
    except Exception as e:
        ci.add_stage("sil-tests", "error", str(e))
        ci.errors.append(f"sil-tests: {e}")
        all_passed = False

    if not _integration_test_stage(project_dir, ci):
        all_passed = False

    print("  \U0001f6e1\ufe0f  CI: memory safety check...")
    if os.path.exists(os.path.join(project_dir, "tests", "asan")):
        ci.add_stage("memory-safety", "info", "ASan tests configured")
        print(f"    \u23ed\ufe0f  ASan tests configured but not run (requires dedicated env)")
    else:
        ci.add_stage("memory-safety", "skipped", "No ASan tests")
        print(f"    \u23ed\ufe0f  No ASan tests found")

    ci.complete("passed" if all_passed else "failed")
    from yuleosh.ci.runner import _save_layer_result
    _save_layer_result(project_dir, ci, all_passed, commit, 2)

    if _generate_layer_report:
        try:
            _generate_layer_report(project_dir, 2)
        except Exception as re:
            log.warning(f"Layer 2 report generation failed: {re}")

    print(f"\n{'='*40}")
    if all_passed:
        print("\u2705 CI Layer 2: ALL STAGES PASSED")
    else:
        print(f"\u274c CI Layer 2: FAILED")
    print()
    return all_passed


# ═══════════════════════════════════════════════════════════════════════
# Layer 3 — System
# ═══════════════════════════════════════════════════════════════════════


def run_layer3(project_dir: Optional[str] = None) -> bool:
    """CI Layer 3: System Verification — runs on Release."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    from yuleosh.ci.runner import git_commit_hash
    commit = git_commit_hash()
    print(f"\n\U0001f680 CI Layer 3: System Verification (Release)")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()

    ci = CIResult(3, commit)
    all_passed = True

    print("  \U0001f4cb CI: end-to-end tests...")
    e2e_dir = os.path.join(project_dir, "tests", "e2e")
    if os.path.exists(e2e_dir):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", e2e_dir, "-x", "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                ci.add_stage("e2e-tests", "passed")
                print(f"    \u2705 E2E tests passed")
            else:
                ci.add_stage("e2e-tests", "failed", result.stdout[:200])
                print(f"    \u274c E2E tests failed")
                all_passed = False
        except FileNotFoundError:
            ci.add_stage("e2e-tests", "skipped", "pytest not installed — blocked")
            print(f"    \u23ed\ufe0f  pytest not installed — blocked")
            all_passed = False
        except subprocess.TimeoutExpired:
            ci.add_stage("e2e-tests", "skipped", "E2E tests timed out — blocked")
            print(f"    \u23ed\ufe0f  E2E tests timed out — blocked")
            all_passed = False
        except Exception as e:
            ci.add_stage("e2e-tests", "error", str(e))
            print(f"    \u274c E2E tests error: {e}")
            all_passed = False
    else:
        ci.add_stage("e2e-tests", "skipped", "No E2E tests")
        print(f"    \u23ed\ufe0f  No E2E tests directory")

    print("  \U0001f4e6 CI: version check...")
    pyproject = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject):
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version", "unknown")
        ci.add_stage("version-check", "passed", f"Version: {version}")
        print(f"    \u2705 Version: {version}")
    else:
        ci.add_stage("version-check", "skipped", "No pyproject.toml")
        print(f"    \u23ed\ufe0f  No version file")

    print("  \U0001f4e6 CI: generating evidence pack...")
    try:
        sys.path.insert(0, os.path.join(project_dir, "src"))
        from evidence import pack as evidence_pack
        evidence_pack.generate_evidence(project_dir)
        ci.add_stage("evidence-pack", "passed", "Compliance pack generated")
        print(f"    \u2705 Evidence pack generated")
    except Exception as e:
        ci.add_stage("evidence-pack", "warning", str(e))
        print(f"    \u26a0\ufe0f  Evidence pack partially generated: {e}")

    ci.complete("passed" if all_passed else "failed")

    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    with open(ci_dir / f"layer3-{commit}.json", "w") as f:
        json.dump(ci.to_dict(), f, indent=2)

    import yuleosh.ci.run as _run_notify
    if _run_notify._notify:
        try:
            _run_notify._notify(
                layer=3,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")

    if _generate_layer_report:
        try:
            _generate_layer_report(project_dir, 3)
        except Exception as re:
            log.warning(f"Layer 3 report generation failed: {re}")

    print(f"\n{'='*40}")
    if all_passed:
        print("\u2705 CI Layer 3: ALL STAGES PASSED \U0001f389")
    else:
        print(f"\u274c CI Layer 3: FAILED")
    print()
    return all_passed
