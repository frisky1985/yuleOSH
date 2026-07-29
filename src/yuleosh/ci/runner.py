#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Runner — run_all orchestration, main CLI, and utility functions.

Lazy-imports from layers.py to avoid circular dependency.
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

from yuleosh.ci.result import CIResult, timed_stage
from yuleosh.ci.config import _get_ci_config, CoverageConfig

log = logging.getLogger("ci.runner")

# Notifications — imported from run.py (canonical mutable state)
import yuleosh.ci.run as _run

def _save_layer_result(
    project_dir: str,
    ci: "CIResult",
    all_passed: bool,
    commit: str,
    layer: int,
) -> Path:
    """Write CI result JSON to disk and send notification."""
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    result_path = ci_dir / f"layer{layer}-{commit}.json"
    with open(result_path, "w") as f:
        json.dump(ci.to_dict(), f, indent=2)

    if _run._notify:
        try:
            _run._notify(
                layer=layer,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")
    return result_path


def git_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_changed_files(base_ref: str = "HEAD") -> list[str]:
    """Get list of changed files."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    return []


# ------------------------------------------------------------------
# Coverage Gate — strict mode, module-level thresholds
# ------------------------------------------------------------------


def check_coverage_gate(
    project_dir: str,
    coverage_data: Optional[dict] = None,
    override_strict: bool = False,
) -> tuple[bool, list[str]]:
    """Check coverage gate with strict mode and module-level thresholds.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    coverage_data : dict, optional
        Coverage report data with line_rate, branch_rate, and per-file
        breakdown.  If None, the gate passes with a warning.
    override_strict : bool
        If True, bypass strict mode blocking (``--override-strict``).

    Returns
    -------
    tuple[bool, list[str]]
        (passed, messages) where passed is True if all gates pass,
        and messages contains status/warning/error strings.
    """
    messages: list[str] = []

    try:
        cfg = _get_ci_config(project_dir)
    except Exception as e:
        messages.append(f"⚠️  Could not load CI config: {e}")
        return True, messages

    cov: CoverageConfig = cfg.coverage
    strict = cov.strict and not override_strict

    # --- Global threshold check ---
    if cov.threshold_line < 50:
        messages.append(
            f"⚠️  threshold_line={cov.threshold_line} is below "
            f"recommended minimum (50)"
        )

    if coverage_data:
        line_rate = coverage_data.get("line_rate", 0.0)
        branch_rate = coverage_data.get("branch_rate", 0.0)

        line_ok = line_rate >= cov.threshold_line
        if not line_ok:
            msg = (
                f"❌ Line coverage {line_rate:.1f}% < threshold "
                f"{cov.threshold_line:.1f}%"
            )
            messages.append(msg)
        else:
            messages.append(
                f"✅ Line coverage {line_rate:.1f}% >= {cov.threshold_line:.1f}%"
            )

        branch_ok = branch_rate >= cov.threshold_condition
        if not branch_ok:
            msg = (
                f"❌ Branch coverage {branch_rate:.1f}% < threshold "
                f"{cov.threshold_condition:.1f}%"
            )
            messages.append(msg)
        else:
            messages.append(
                f"✅ Branch coverage {branch_rate:.1f}% >= {cov.threshold_condition:.1f}%"
            )

        # --- Module-level threshold check ---
        if cov.module_thresholds and "files" in coverage_data:
            module_ok = True
            for module_name, module_threshold in cov.module_thresholds.items():
                module_coverage = _compute_module_coverage(
                    coverage_data["files"], module_name
                )
                if module_coverage is not None and module_coverage < module_threshold:
                    module_ok = False
                    messages.append(
                        f"❌ Module '{module_name}' coverage {module_coverage:.1f}% < "
                        f"threshold {module_threshold:.1f}%"
                    )
                elif module_coverage is not None:
                    messages.append(
                        f"✅ Module '{module_name}' coverage {module_coverage:.1f}% >= "
                        f"{module_threshold:.1f}%"
                    )
                else:
                    messages.append(
                        f"⚠️  Module '{module_name}': no files matched, cannot check"
                    )

        # --- Strict mode ---
        all_gates_ok = line_ok and branch_ok
        if strict and not all_gates_ok:
            messages.append(
                "🔒 strict: true — coverage gate BLOCKING pipeline"
            )
            return False, messages
        elif not strict and not all_gates_ok:
            messages.append(
                "⚠️  strict: false — coverage gate is advisory-only"
            )
            return True, messages

        return all_gates_ok, messages

    messages.append("⚠️  No coverage data available — gate check skipped")
    return True, messages


def _compute_module_coverage(files: list[dict], module_prefix: str) -> Optional[float]:
    """Compute line coverage for a module (by file path prefix)."""
    matched = [
        f for f in files
        if f.get("file", "").startswith(module_prefix)
    ]
    if not matched:
        return None
    total_found = sum(f.get("lines", {}).get("found", 0) for f in matched)
    total_hit = sum(f.get("lines", {}).get("hit", 0) for f in matched)
    if total_found == 0:
        return None
    return (total_hit / total_found) * 100


def _load_latest_coverage(project_dir: str) -> Optional[dict]:
    """Load the latest coverage report from the CI cache."""
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.is_dir():
        return None
    json_files = sorted(ci_dir.glob("layer2-*.json"))
    if not json_files:
        json_files = sorted(ci_dir.glob("*.json"))
    if not json_files:
        return None
    try:
        data = json.loads(json_files[-1].read_text())
        return data
    except (json.JSONDecodeError, OSError, IndexError):
        return None


def _load_python_coverage(project_dir: str) -> Optional[dict]:
    """Try to load a pytest --cov JSON report from .yuleosh/reports/."""
    cov_path = Path(project_dir) / ".yuleosh" / "reports" / "coverage-report.json"
    if cov_path.exists():
        try:
            return json.loads(cov_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    c_path = Path(project_dir) / ".yuleosh" / "reports" / "c-coverage.json"
    if c_path.exists():
        try:
            return json.loads(c_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def run_all(
    project_dir: Optional[str] = None,
    override_strict: bool = False,
):
    """Run the full CI pipeline: L1 → L2 → L2.5 → L3 with dependency gating.

    Each layer only runs if all its upstream dependencies passed.
    Layer order is read from ``ci-config.yaml`` if available.
    Returns True if all layers passed, False otherwise.

    Parameters
    ----------
    project_dir : str, optional
        Project root directory.
    override_strict : bool
        If True, bypass strict mode blocking for coverage gates.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    # Load layer order from config
    try:
        cfg = _get_ci_config(project_dir)
        layers = cfg.layers if cfg else [1, 2, 25, 3]
    except Exception as e:
        import logging; logging.getLogger("ci.run").info("Run all config: %s", e)
        layers = [1, 2, 25, 3]

    print("\n" + "=" * 50)
    print(f"  🚀 CI Pipeline: {layers}")
    print("=" * 50)
    all_passed = True

    # --- Coverage gate check ---
    try:
        coverage_data = _load_python_coverage(project_dir) or _load_latest_coverage(project_dir)
        gate_passed, gate_msgs = check_coverage_gate(
            project_dir, coverage_data, override_strict=override_strict,
        )
        print()
        for msg in gate_msgs:
            print(f"  {msg}")
        if not gate_passed:
            all_passed = False
            print()
    except Exception as e:
        log.warning("Coverage gate check failed: %s", e)

    for layer in layers:
        # Check dependencies before running
        from yuleosh.ci.layers import check_layer_dependency
        blocker = check_layer_dependency(layer, project_dir)
        if blocker:
            print(f"\n  🔒 Layer {layer} SKIPPED — dependency not satisfied")
            print(f"     Reason: {blocker}")
            all_passed = False
            break

        # Run the layer — lazy imports to avoid circular dep
        if layer == 1:
            from yuleosh.ci.run import run_layer1; passed = run_layer1(project_dir)
        elif layer == 2:
            from yuleosh.ci.run import run_layer2; passed = run_layer2(project_dir)
        elif layer == 25:
            from yuleosh.ci.run import run_layer_25; passed = run_layer_25(project_dir)
        elif layer == 3:
            from yuleosh.ci.run import run_layer3; passed = run_layer3(project_dir)
        else:
            passed = False

        if not passed:
            all_passed = False
            print(f"\n  🔒 Layer {layer} FAILED — downstream layers blocked")
            remaining = [l for l in layers if l > layer]
            if remaining:
                print(f"     Blocked layers: {', '.join(f'L{l}' for l in remaining)}")
            break

    # A4: Generate final comprehensive report after all layers
    try:
        from yuleosh.report.exporter import generate_final_report
        report_dir = generate_final_report(project_dir)
        if report_dir:
            print(f"\n  📊 Final CI report: {report_dir}/ci-final-report.*")
    except ImportError:
        log.warning("report.exporter not available — final report not generated")
    except Exception as fre:
        log.warning(f"Final report generation failed: {fre}")

    print("\n" + "=" * 50)
    if all_passed:
        print("  ✅ CI Pipeline: ALL LAYERS PASSED 🎉")
    else:
        print("  ❌ CI Pipeline: FAILED")
    print("=" * 50 + "\n")
    return all_passed


def main():
    args = sys.argv[1:]
    override_strict = "--override-strict" in args
    args = [a for a in args if a != "--override-strict"]

    layer = args[0] if args else "1"
    
    if layer == "all":
        success = run_all(override_strict=override_strict)
        sys.exit(0 if success else 1)
    elif layer == "1":
        from yuleosh.ci.run import run_layer1
        success = run_layer1()
        sys.exit(0 if success else 1)
    elif layer == "2":
        from yuleosh.ci.run import run_layer2
        success = run_layer2()
        sys.exit(0 if success else 1)
    elif layer in ("25", "2.5"):
        from yuleosh.ci.run import run_layer_25
        success = run_layer_25()
        sys.exit(0 if success else 1)
    elif layer == "3":
        from yuleosh.ci.run import run_layer3
        success = run_layer3()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown layer: {layer}")
        print("Usage: python3 run.py [1|2|2.5|3|all] [--override-strict]")
        sys.exit(1)


if __name__ == "__main__":
    main()
