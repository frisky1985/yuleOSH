#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Engine — backward-compatible re-exports from split modules.

This module is the canonical namespace for mutable module-level variables
(_notify, _ci_config_cache, _test_file_cache). Split modules import
these from run.py so that mock.patch("yuleosh.ci.run.*") works correctly.
"""

import logging
import os
import sys

# === Mutable module-level state (defined first so split modules can import) ===

# Notifications (optional import)
_notify = None
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from notify import notify_ci as _notify_ci
    _notify = _notify_ci
except ImportError:
    _notify = None

# === Re-exports from split modules ===

import subprocess  # re-export for tests that mock yuleosh.ci.run.subprocess

# Runner — orchestration and CLI
from yuleosh.ci.runner import (
    run_all, main, _save_layer_result, git_commit_hash, get_changed_files,
)

# Layers — layer-level orchestration
from yuleosh.ci.layers import (
    get_latest_layer_result, check_layer_dependency,
    run_layer1, run_layer2, run_layer_25, run_layer3,
    layer_dependencies,
)

# Stages — re-export mutable state and functions
import yuleosh.ci.stages as _stages
run_plan_lint = _stages.run_plan_lint
run_clang_tidy = _stages.run_clang_tidy
run_unit_tests = _stages.run_unit_tests
run_coverage_check = _stages.run_coverage_check
run_sil_tests = _stages.run_sil_tests
run_misra_check = _stages.run_misra_check
run_c_coverage = _stages.run_c_coverage
run_c_coverage_check = _stages.run_c_coverage_check
run_coverage_regression = _stages.run_coverage_regression
import yuleosh.ci.stage_utils as _sutils
_detect_hil_target = _sutils._detect_hil_target
_run_hil_mock_tests = _sutils._run_hil_mock_tests
_run_hil_real_tests = _sutils._run_hil_real_tests
_record_hil_results = _sutils._record_hil_results
_save_hil_report = _sutils._save_hil_report
_find_c_sources = _sutils._find_c_sources
_cross_compile_stage = _sutils._cross_compile_stage
_static_analysis_stage = _sutils._static_analysis_stage
_integration_test_stage = _sutils._integration_test_stage
_resolve_cross_compile = _sutils._resolve_cross_compile
_cross_compile_via_docker = _sutils._cross_compile_via_docker
_handle_stage_error = _sutils._handle_stage_error
_run_subprocess = _sutils._run_subprocess
get_cache_key_for_dir = _sutils.get_cache_key_for_dir
_test_file_cache = _sutils._test_file_cache
_test_file_cache_mtime = _sutils._test_file_cache_mtime
find_test_files = _sutils.find_test_files
_should_skip_coverage = _sutils._should_skip_coverage
_coverage_skip_reason = _sutils._coverage_skip_reason
_run_coverage_and_export = _sutils._run_coverage_and_export
_load_coverage_json = _sutils._load_coverage_json

# Config — re-export mutable state and functions
import yuleosh.ci.config as _cfg
_get_ci_config = _cfg._get_ci_config
_clear_ci_config_cache = _cfg._clear_ci_config_cache
_ci_config_cache = _cfg._ci_config_cache
is_strict = _cfg.is_strict
is_misra_fail_fast = _cfg.is_misra_fail_fast
load_ci_config = _cfg.load_ci_config
CiConfig = _cfg.CiConfig
MisraConfig = _cfg.MisraConfig

# Result
from yuleosh.ci.result import CIResult, timed_stage
