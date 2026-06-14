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
from yuleosh.ci.config import _get_ci_config

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




def run_all(project_dir: Optional[str] = None):
    """Run the full CI pipeline: L1 → L2 → L2.5 → L3 with dependency gating.

    Each layer only runs if all its upstream dependencies passed.
    Layer order is read from ``ci-config.yaml`` if available.
    Returns True if all layers passed, False otherwise.
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

    for layer in layers:
        # Check dependencies before running
        from yuleosh.ci.run import check_layer_dependency  # lazy: avoid circular dep
        blocker = check_layer_dependency(layer, project_dir)
        if blocker:
            print(f"\n  🔒 Layer {layer} SKIPPED — dependency not satisfied")
            print(f"     Reason: {blocker}")
            all_passed = False
            break  # Chain break: no point continuing

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

    print("\n" + "=" * 50)
    if all_passed:
        print("  ✅ CI Pipeline: ALL LAYERS PASSED 🎉")
    else:
        print("  ❌ CI Pipeline: FAILED")
    print("=" * 50 + "\n")
    return all_passed




def main():
    layer = sys.argv[1] if len(sys.argv) > 1 else "1"
    
    if layer == "all":
        success = run_all()
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
        print("Usage: python3 run.py [1|2|2.5|3|all]")
        sys.exit(1)


if __name__ == "__main__":
    main()
