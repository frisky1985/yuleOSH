#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CI Stages — Review stage execution functions.

Part of the stages/ package split from stages.py.

TD-005 split (pure relocation): the two large review domains moved to
dedicated modules —

- yuleosh.ci.stages.review_collect — C/C++ source collection & selection
  (``_categorize_file``, ``_find_c_sources``, ``_collect_delta_files``,
  ``_expand_header_dependents``, ``_exclude_paths``,
  ``_detect_include_paths``, ``_scan_include_dirs``, ``_get_git_commit``,
  ``_glob_to_regex``, ``_matches_glob``);
- yuleosh.ci.stages.review_misra — MISRA C static analysis
  (``run_misra_check``, ``_format_null_pointer_fix``).

This module keeps the review stage entry point (``run_docsync_gate``) and
re-exports every public symbol so existing imports and test patches keep
working.

L1 delta 接线（run_misra_check, mode="delta"）: 三源变更集收集
``_collect_delta_files(project_dir)`` → 头文件反向依赖展开
``_expand_header_dependents(project_dir, changed)`` → 只扫相关集。
"""

import logging

from yuleosh.ci.config import (  # noqa: F401 — backward-compat re-export
    _get_ci_config,
    is_misra_fail_fast,
    is_strict,
)
from yuleosh.ci.result import CIResult, timed_stage

from yuleosh.ci.stage_utils import (  # noqa: F401 — backward-compat re-export
    find_test_files, get_cache_key_for_dir,
    _test_file_cache, _test_file_cache_mtime,
    _should_skip_coverage, _coverage_skip_reason,
    _run_coverage_and_export, _load_coverage_json,
    _resolve_cross_compile, _cross_compile_via_docker,
    _handle_stage_error, _run_subprocess,
)

log = logging.getLogger("ci.stages")

# ── TD-005: 职责域模块 re-exports（纯搬移，导出符号与拆分前一致）─────────
from yuleosh.ci.stages.review_collect import (
    _categorize_file,
    _collect_delta_files,
    _detect_include_paths,
    _exclude_paths,
    _expand_header_dependents,
    _find_c_sources,
    _get_git_commit,
    _glob_to_regex,
    _matches_glob,
    _scan_include_dirs,
)
from yuleosh.ci.stages.review_misra import (
    _format_null_pointer_fix,
    run_misra_check,
)


def run_docsync_gate(project_dir: str, ci: CIResult) -> bool:
    """Run the document sync gate check (H-07).

    Integrates the enhanced sync_check module into the CI pipeline.
    Checks that code changes have corresponding documentation updates.
    Blocks pipeline only in strict mode.
    """
    print("  📝 CI: doc sync gate (H-07)...")

    from yuleosh.ci.sync_check import run_sync_check_gate, save_sync_evidence

    try:
        result = run_sync_check_gate(project_dir, base_ref="HEAD")
    except Exception as e:
        ci.add_stage("docsync-gate", "warning", f"Sync check error: {e}")
        print(f"    ⚠️  Doc sync gate error: {e}")
        return True  # Non-blocking on errors

    # Save evidence
    try:
        evidence_path = save_sync_evidence(project_dir, result)
    except Exception:
        evidence_path = ""

    status = result.get("status", "passed")
    summary = result.get("summary", "")

    if status == "failed":
        strict = is_strict()
        if strict:
            ci.add_stage("docsync-gate", "failed", summary)
            print(f"    ❌ Doc sync gate FAILED (strict mode): {summary}")
            return False
        else:
            ci.add_stage("docsync-gate", "warning", summary)
            print(f"    ⚠️  Doc sync gate: {summary}")
            return True
    elif status == "warning":
        ci.add_stage("docsync-gate", "warning", summary)
        print(f"    ⚠️  Doc sync gate: {summary}")
        return True
    else:
        ci.add_stage("docsync-gate", "passed", summary)
        print(f"    ✅ Doc sync gate: {summary}")
        if evidence_path:
            print(f"    📍 Evidence: {evidence_path}")
        return True
