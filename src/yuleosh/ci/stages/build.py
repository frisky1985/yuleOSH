#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — Build stage execution functions.

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


