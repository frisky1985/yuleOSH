#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Layers — layer-level CI orchestration functions.

Each function runs multiple CI stages for one CI layer.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.ci.config import _get_ci_config, is_strict, is_misra_fail_fast, layer_dependencies
from yuleosh.ci.result import CIResult, timed_stage
from yuleosh.ci.stages import (
    run_plan_lint, run_clang_tidy, run_unit_tests, run_coverage_check, run_sil_tests,
)
from yuleosh.ci.stage_utils import (
    _detect_hil_target, _run_hil_mock_tests, _run_hil_real_tests, _record_hil_results, _save_hil_report,
    _find_c_sources, _cross_compile_stage, _static_analysis_stage, _integration_test_stage,
    find_test_files,
)

log = logging.getLogger("ci.layers")

def get_latest_layer_result(layer: int, project_dir: str) -> Optional[dict]:
    """Read the most recent CI result for the given layer from .osh/ci/.

    Returns the parsed JSON dict if found, or None if no result exists.
    """
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        return None

    prefix = f"layer{layer}-"
    result_files = sorted(
        [f for f in ci_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not result_files:
        return None
    try:
        return json.loads(result_files[0].read_text())
    except (json.JSONDecodeError, OSError):
        return None


def check_layer_dependency(target_layer: int, project_dir: str) -> Optional[str]:
    """Check if all dependencies for *target_layer* are satisfied.

    Reads the dependency chain from ``ci-config.yaml`` first, falling back
    to the hardcoded global ``layer_dependencies`` dict when the config
    file is absent or broken.

    Returns None if all deps passed, or a string describing the first
    blocking dependency failure.
    """
    try:
        cfg = _get_ci_config(project_dir)
        deps = cfg.layer_dependencies.get(target_layer, [])
    except Exception as e:
        import logging; logging.getLogger("ci.run").info("Layer dependency check config: %s", e)
        deps = layer_dependencies.get(target_layer, [])
    for dep in deps:
        result = get_latest_layer_result(dep, project_dir)
        if result is None:
            return (
                f"Layer {dep} has no recorded result — "
                f"run layer {dep} first before layer {target_layer}"
            )
        if result.get("status") != "passed":
            return (
                f"Layer {dep} status is '{result.get('status', 'unknown')}' — "
                f"layer {target_layer} blocked (dependency chain: "
                f"{' → '.join(str(l) for l in deps)})"
            )
    return None


# ------------------------------------------------------------------
# Timing decorator
# ------------------------------------------------------------------




def run_layer1(project_dir: Optional[str] = None):
    """Run Layer 1 CI pipeline."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    from yuleosh.ci.runner import git_commit_hash; commit = git_commit_hash()
    print(f"\n🔬 CI Layer 1: Development Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()
    
    ci = CIResult(1, commit)
    
    stages = [
        ("plan-lint", run_plan_lint),
        ("clang-tidy", run_clang_tidy),
        ("unit-tests", run_unit_tests),
        ("coverage", run_coverage_check),
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
    
    ci.complete("passed" if all_passed else "failed")
    
    # Save result
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    result_path = ci_dir / f"layer1-{commit}.json"
    with open(result_path, "w") as f:
        json.dump(ci.to_dict(), f, indent=2)
    
    # Send notification
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

    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 1: ALL STAGES PASSED")
    else:
        print(f"❌ CI Layer 1: FAILED — {len(ci.errors)} error(s)")
    
    print(f"   Report: {result_path}")
    print()
    
    return all_passed


# ------------------------------------------------------------------
# HIL stage helpers — break up run_layer_25
# ------------------------------------------------------------------




def run_layer_25(project_dir: Optional[str] = None):
    """CI Layer 2.5: Hardware-in-the-Loop (HIL) — runs after L2 passes.

    When ``mock=True`` in ci-config.yaml, all hardware interaction is
    simulated — suitable for CI environments without physical boards.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    from yuleosh.ci.runner import git_commit_hash; commit = git_commit_hash()
    print(f"\n🛠️  CI Layer 2.5: Hardware-in-the-Loop (HIL)")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}\n")

    ci = CIResult(25, commit)
    all_passed = True
    strict = is_strict()

    try:
        cfg = _get_ci_config(project_dir)
    except Exception as e:
        import logging; logging.getLogger("ci.run").info("HIL config fallback: %s", e)
        cfg = None
        cfg = None

    hw_cfg = cfg.hardware_test if cfg else None
    mock_mode = hw_cfg.mock if hw_cfg else True
    boot_pattern = hw_cfg.boot_pattern if hw_cfg else "Boot Complete"

    # Stage 1: Target detection
    target_ok = _detect_hil_target(project_dir, ci, mock_mode, strict)
    if not target_ok:
        all_passed = False

    # Stage 2: HIL tests
    print("  🧪 CI: HIL tests...")
    firmware_path = hw_cfg.firmware if hw_cfg else "build/firmware.elf"
    firmware_full = os.path.join(project_dir, firmware_path)
    scripts_dir = hw_cfg.test_scripts_dir if hw_cfg else "tests/hil"
    scripts_full = os.path.join(project_dir, scripts_dir)

    hil_results: list[dict] = []
    try:
        if not os.path.exists(scripts_full) and not mock_mode:
            print(f"    ⏭️  No HIL test scripts at {scripts_dir}")
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
        print(f"    ❌ {msg}")
        if strict:
            all_passed = False
            ci.errors.append(msg)

    # Stage 3: Report
    _save_hil_report(project_dir, all_passed, commit, mock_mode, boot_pattern)

    ci.complete("passed" if all_passed else "failed")
    from yuleosh.ci.runner import _save_layer_result; result_path = _save_layer_result(project_dir, ci, all_passed, commit, 25)

    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 2.5: ALL HIL STAGES PASSED")
    else:
        print(f"❌ CI Layer 2.5: FAILED — {len(ci.errors)} error(s)")
    print(f"   Report: {result_path}\n")
    return all_passed




def run_layer2(project_dir: Optional[str] = None):
    """CI Layer 2: Integration Verification — runs on MR."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    from yuleosh.ci.runner import git_commit_hash; commit = git_commit_hash()
    print(f"\n🔄 CI Layer 2: Integration Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}\n")

    ci = CIResult(2, commit)
    all_passed = True
    misra_ff = is_misra_fail_fast()
    strict = is_strict()

    c_files, cross_src, build_dir = _find_c_sources(project_dir)

    # Stage 1: Cross-compilation
    if not _cross_compile_stage(project_dir, cross_src, build_dir, ci):
        all_passed = False

    # Stage 2: Static analysis
    if not _static_analysis_stage(c_files, project_dir, ci, misra_ff, strict):
        all_passed = False

    # Stage 3: SIL tests
    print("  🖥️  CI: SIL tests...")
    try:
        if not run_sil_tests(project_dir, ci):
            all_passed = False
            ci.errors.append("sil-tests failed")
    except Exception as e:
        ci.add_stage("sil-tests", "error", str(e))
        ci.errors.append(f"sil-tests: {e}")
        all_passed = False

    # Stage 4: Integration tests
    if not _integration_test_stage(project_dir, ci):
        all_passed = False

    # Stage 5: Memory safety
    print("  🛡️  CI: memory safety check...")
    if os.path.exists(os.path.join(project_dir, "tests", "asan")):
        ci.add_stage("memory-safety", "info", "ASan tests configured")
        print(f"    ⏭️  ASan tests configured but not run (requires dedicated env)")
    else:
        ci.add_stage("memory-safety", "skipped", "No ASan tests")
        print(f"    ⏭️  No ASan tests found")

    ci.complete("passed" if all_passed else "failed")
    from yuleosh.ci.runner import _save_layer_result; _save_layer_result(project_dir, ci, all_passed, commit, 2)

    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 2: ALL STAGES PASSED")
    else:
        print(f"❌ CI Layer 2: FAILED")
    print()
    return all_passed




def run_layer3(project_dir: Optional[str] = None):
    """CI Layer 3: System Verification — runs on Release."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    from yuleosh.ci.runner import git_commit_hash; commit = git_commit_hash()
    print(f"\n🚀 CI Layer 3: System Verification (Release)")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()
    
    ci = CIResult(3, commit)
    all_passed = True
    
    # Stage 1: E2E tests
    print("  📋 CI: end-to-end tests...")
    e2e_dir = os.path.join(project_dir, "tests", "e2e")
    if os.path.exists(e2e_dir):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", e2e_dir, "-x", "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                ci.add_stage("e2e-tests", "passed")
                print(f"    ✅ E2E tests passed")
            else:
                ci.add_stage("e2e-tests", "failed", result.stdout[:200])
                print(f"    ❌ E2E tests failed")
                all_passed = False
        except FileNotFoundError:
            ci.add_stage("e2e-tests", "skipped", "pytest not installed — blocked")
            print(f"    ⏭️  pytest not installed — blocked")
            all_passed = False
        except subprocess.TimeoutExpired:
            ci.add_stage("e2e-tests", "skipped", "E2E tests timed out — blocked")
            print(f"    ⏭️  E2E tests timed out — blocked")
            all_passed = False
        except Exception as e:
            ci.add_stage("e2e-tests", "error", str(e))
            print(f"    ❌ E2E tests error: {e}")
            all_passed = False
    else:
        ci.add_stage("e2e-tests", "skipped", "No E2E tests")
        print(f"    ⏭️  No E2E tests directory")
    
    # Stage 2: Version check
    print("  📦 CI: version check...")
    pyproject = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject):
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version", "unknown")
        ci.add_stage("version-check", "passed", f"Version: {version}")
        print(f"    ✅ Version: {version}")
    else:
        ci.add_stage("version-check", "skipped", "No pyproject.toml")
        print(f"    ⏭️  No version file")
    
    # Stage 3: Evidence pack generation
    print("  📦 CI: generating evidence pack...")
    try:
        sys.path.insert(0, os.path.join(project_dir, "src"))
        from evidence import pack as evidence_pack
        evidence_pack.generate_evidence(project_dir)
        ci.add_stage("evidence-pack", "passed", "Compliance pack generated")
        print(f"    ✅ Evidence pack generated")
    except Exception as e:
        ci.add_stage("evidence-pack", "warning", str(e))
        print(f"    ⚠️  Evidence pack partially generated: {e}")
    
    ci.complete("passed" if all_passed else "failed")
    
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    with open(ci_dir / f"layer3-{commit}.json", "w") as f:
        json.dump(ci.to_dict(), f, indent=2)
    
    # Send notification
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

    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 3: ALL STAGES PASSED 🎉")
    else:
        print(f"❌ CI Layer 3: FAILED")
    print()
    return all_passed


