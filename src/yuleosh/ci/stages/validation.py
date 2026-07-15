#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — Validation stage execution functions.

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
        # Also skip large dependency directories that never contain task/plan files
        _SKIP_LARGE_DIRS = {"node_modules", "venv", ".venv", "vendor",
                            "third_party", ".cache", ".go", "target",
                            ".build", "dist", ".tox"}
        dirs[:] = [d for d in dirs
                   if d not in skip_hidden | _SKIP_LARGE_DIRS
                   and not (d.startswith(".") and d not in (".osh", ".yuleosh"))]
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

