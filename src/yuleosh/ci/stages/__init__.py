#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — backward-compatible re-export package.

This package replaces the monolithic stages.py (Phase 2.2 refactor).
All public functions are re-exported here so that

    from yuleosh.ci.stages import run_misra_check

continues to work.
"""

import logging
import subprocess

log = logging.getLogger("ci.stages")

# ── Backward-compatible re-exports from stage_utils ──
# These names were originally imported into stages.py, and tests
# mock them via ``mock.patch("yuleosh.ci.stages.xxx")``.
from yuleosh.ci.stage_utils import (
    find_test_files,
    _run_coverage_and_export,
    _load_coverage_json,
    _should_skip_coverage,
    _coverage_skip_reason,
    _resolve_cross_compile,
    _cross_compile_via_docker,
    _handle_stage_error,
    _run_subprocess,
    get_cache_key_for_dir,
    _test_file_cache,
    _test_file_cache_mtime,
)




from yuleosh.ci.stages.validation import (
    run_yaml_validation,
    run_plan_lint,
    run_clang_tidy,
    run_spec_validation,
    run_architecture_review,
)

from yuleosh.ci.stages.test import (
    run_unit_tests,
    run_coverage_check,
    run_sil_tests,
    run_c_coverage_check,
    run_coverage_regression,
)

from yuleosh.ci.stages.build import (
    run_c_coverage,
)

from yuleosh.ci.stages.review import (
    _categorize_file,
    _format_null_pointer_fix,
    _exclude_paths,
    _detect_include_paths,
    _get_git_commit,
    run_misra_check,
    run_docsync_gate,
)

from yuleosh.ci.stages.traceability import (
    run_requirements_trace,
)

