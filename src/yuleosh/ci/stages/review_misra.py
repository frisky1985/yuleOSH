#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""CI Stages — MISRA C static-analysis review domain (TD-005, split from review.py).

run_misra_check: cppcheck --addon=misra execution, report generation
(.yuleosh/reports/misra-report.json), GSCR translation, L2 delta blocking
and trend tracking.  Moved verbatim from yuleosh/ci/stages/review.py.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from yuleosh.ci.config import _get_ci_config, is_misra_fail_fast, is_strict
from yuleosh.ci.result import CIResult
from yuleosh.ci.stage_utils import _handle_stage_error
from yuleosh.ci.stages.review_collect import (
    _categorize_file,
    _collect_delta_files,
    _detect_include_paths,
    _exclude_paths,
    _expand_header_dependents,
    _find_c_sources,
    _get_git_commit,
)

log = logging.getLogger("ci.stages")

def _format_null_pointer_fix(category: str, file_path: str) -> str:
    """根据代码类别生成针对性的多级指针空修复建议。"""
    if category == "template":
        return ""  # template 代码不显示

    fix_text = """
    🔧 修复建议（多级指针判空）:
        // 方法一：逐层判空（推荐）
        if (ptr != NULL) {
            if (*ptr != NULL) {
                **ptr = value;
            }
        }
        // 方法二：封装安全访问函数
        int safe_set(int **ptr, int row, int col, int value) {
            if (ptr == NULL || ptr[row] == NULL) return -1;
            ptr[row][col] = value;
            return 0;
        }
        // 方法三：若确认不会为NULL，加断言（仅限于业务代码）
        assert(ptr != NULL && *ptr != NULL);
"""
    if category == "third_party":
        fix_text += """
    ⚠️ 第三方库代码：
        如果确认是误报（该指针在该场景中不可能为NULL），
        请在 ci-config.yaml 中添加 deviation 豁免：
            deviations:
              - rule: Dir-4.1
                file: "third_party/xxx/**/*.c"
                reason: "第三方库，指针安全已由对方保证"
                approved_by: "your-name"
                expires: "2027-06-30"
                status: approved
"""
    return fix_text

def run_misra_check(project_dir: str, ci: CIResult,
                    target_files: list[str] | None = None,
                    mode: str = "auto") -> bool:
    """Run MISRA C:2023 static analysis via cppcheck --addon=misra.

    Parses output through misra_report.py, saves structured report
    to ``.yuleosh/reports/misra-report.json``, and blocks the pipeline
    when violations exceed the configured threshold in strict mode.

    Configuration is read from ``.yuleosh/ci-config.yaml`` (misra block).
    Falls back to cppcheck --std=c11 --addon=misra when no config file.

    When ``target_files`` is provided, only those files are checked
    (incremental / delta mode).  When omitted, ``git diff HEAD~1`` is
    used to auto-detect changed C/C++ files in the repo; if the repo
    is not a git checkout, all source files are checked (full mode).

    Parameters
    ----------
    project_dir : str
        Root path of the project.
    ci : CIResult
        CI result accumulator.
    target_files : list[str] | None
        Explicit list of files to check.  None = auto-detect.
    mode : str
        MISRA check mode: "auto" (default, auto-detect delta/full),
        "delta" (L1 — only scan modified files),
        "full" (L2 — full scan with zero-delta blocking for new Required).

    Returns True if passed/acceptable violations, False if blocked.
    """

    def _load_misra_baseline(proj_dir: str) -> dict:
        """Load the most recent MISRA trend entry as a baseline for delta comparison."""
        from yuleosh.ci.misra_trend import TREND_FILE as _mf
        trend_path = Path(proj_dir) / _mf
        if not trend_path.exists():
            return {}
        entries: list[dict] = []
        with open(trend_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
        if not entries:
            return {}
        # Return most recent FULL scan entry (is_delta=False) as baseline
        for e in reversed(entries):
            if not e.get("is_delta", True):
                return e
        return entries[-1] if entries else {}

    def _is_new_required_violation(v: dict, baseline_violations: list) -> bool:
        """Check if a Required violation is new (not in baseline)."""
        rule_id = v.get("rule_id", "")
        v_file = v.get("file", "")
        severity = v.get("severity_category", "").lower()
        if severity != "required":
            return False
        for bv in baseline_violations:
            if bv.get("rule_id") == rule_id and bv.get("file") == v_file:
                if bv.get("line") == v.get("line"):  # Same line = same violation
                    return False
        return True
    print("  🔍 CI: MISRA C:2023 static analysis...")

    # Load config
    try:
        cfg = _get_ci_config(project_dir)
        misra_cfg = cfg.misra if cfg else None
    except Exception:
        misra_cfg = None

    enabled = misra_cfg.enabled if misra_cfg else True
    if not enabled:
        ci.add_stage("misra-check", "skipped", "MISRA check disabled in config")
        print("    ⏭️  MISRA check disabled — skipped")
        return True

    fail_on_required = misra_cfg.fail_on_required if misra_cfg else True  # G-09: default True
    fail_on_violation = misra_cfg.fail_on_violation if misra_cfg else False  # G-09: deprecated master switch
    fail_on_advisory = misra_cfg.fail_on_advisory if misra_cfg else False
    fail_threshold = misra_cfg.fail_threshold if misra_cfg else 10
    violations_per_kloc = misra_cfg.violations_per_kloc if misra_cfg else 2.0
    addon = misra_cfg.addon if misra_cfg else "misra"
    cppcheck_std = misra_cfg.cppcheck_std if misra_cfg else "c11"
    enable = getattr(misra_cfg, "enable", "all") if misra_cfg else "all"
    suppress_rules = misra_cfg.suppress_rules if misra_cfg else []
    rule_overrides = misra_cfg.rule_overrides if misra_cfg else []
    deviations = misra_cfg.deviations if misra_cfg else []
    strict = is_strict()

    # ── Resolve active MISRA profile (QG-002) ──
    active_profile_name = misra_cfg.active_profile if misra_cfg else "safety"
    active_profile = misra_cfg.profiles.get(active_profile_name) if misra_cfg and misra_cfg.profiles else None
    profile_block_on: list[str] = []
    profile_rules: list[str] = []
    if active_profile:
        profile_block_on = active_profile.block_on or []
        profile_rules = active_profile.rules or []
        log.info("Active MISRA profile: %s — block_on=%s, rules=%s",
                 active_profile_name, profile_block_on, profile_rules)
        print(f"    📋 MISRA profile: {active_profile_name} — block_on={profile_block_on}, rules={profile_rules}")
    elif misra_cfg and misra_cfg.profiles:
        log.warning("Active profile '%s' not found in profiles — defaulting to safety blocking",
                    active_profile_name)
        print(f"    ⚠️  Active profile '{active_profile_name}' not found — using safety defaults")
        profile_block_on = ["mandatory", "required"]
        profile_rules = ["mandatory", "required", "advisory"]
    else:
        # No profiles configured — backwards compatible: all severities may block
        profile_block_on = ["mandatory", "required", "advisory"]
        profile_rules = ["mandatory", "required", "advisory"]

    # --- Determine which files to check (delta / full) ---
    # DEF-006: Support explicit mode parameter (L1 delta, L2 full)
    is_delta = False
    is_full_delta = False  # L2: full scan + delta blocking on new Required
    c_files: list[str] = []

    if mode == "delta":
        # L1: delta mode — only scan modified files
        is_delta = True
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
        else:
            # Three-source union: committed diff + working tree + untracked,
            # then expand changed headers into dependent .c/.cpp files so a
            # header-only change (macros/inlines) never goes unscanned.
            try:
                changed = _collect_delta_files(project_dir)
                changed = _expand_header_dependents(project_dir, changed)
                c_files = [
                    os.path.join(project_dir, f) if not os.path.isabs(f) else f
                    for f in changed
                    if f.endswith((".c", ".cpp"))
                ]
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("delta file collection failed: %s", exc)
                c_files = []
            # If no git diff, fall back to empty (skip delta check)
    elif mode == "full":
        # L2: full scan + delta blocking on new Required
        is_full_delta = True
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
        if not c_files:
            # Full scan: walk configurable scan_dirs (default src/benchmark/ref)
            scan_dirs = misra_cfg.scan_dirs if misra_cfg and misra_cfg.scan_dirs else ["src", "benchmark", "ref"]
            c_files = _find_c_sources(project_dir, scan_dirs)
    else:
        # auto mode (default) — same as before
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
            is_delta = True
        else:
            try:
                git_result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD~1"],
                    capture_output=True, text=True, timeout=10,
                    cwd=project_dir,
                )
                if git_result.returncode == 0:
                    changed_files = [f.strip() for f in git_result.stdout.splitlines() if f.strip()]
                    c_files = [
                        os.path.join(project_dir, f) if not os.path.isabs(f) else f
                        for f in changed_files
                        if f.endswith((".c", ".cpp"))
                    ]
                    if c_files:
                        is_delta = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            if not c_files:
                # Fallback: walk configurable scan_dirs (default src/benchmark/ref)
                scan_dirs = misra_cfg.scan_dirs if misra_cfg and misra_cfg.scan_dirs else ["src", "benchmark", "ref"]
                c_files = _find_c_sources(project_dir, scan_dirs)

    if not c_files:
        ci.add_stage("misra-check", "skipped", "No C/C++ source files found")
        print("    ⏭️  No C/C++ source files — skipped")
        return True

    # ── Apply exclude_paths filtering ──
    exclude_patterns = misra_cfg.exclude_paths if misra_cfg else []
    c_files = _exclude_paths(c_files, exclude_patterns, project_dir)

    if not c_files:
        ci.add_stage("misra-check", "skipped", "All C/C++ files excluded by exclude_paths")
        print("    ⏭️  All C/C++ files excluded by exclude_paths — skipped")
        return True

    # ── 三级分类过滤 ──
    code_categories = misra_cfg.code_categories if misra_cfg else {}
    file_category_map: dict[str, str] = {}  # filepath -> category_name
    categorized_c_files: list[str] = []
    template_skipped = 0
    for f in c_files:
        cat_name, cat_cfg = _categorize_file(f, code_categories)
        if cat_name == "template":
            # template 代码完全跳过
            template_skipped += 1
            continue
        file_category_map[f] = cat_name
        categorized_c_files.append(f)
    c_files = categorized_c_files
    del categorized_c_files

    if template_skipped > 0:
        print(f"    📋 Template files excluded by code_categories: {template_skipped}")

    if not c_files:
        ci.add_stage("misra-check", "skipped", "All C/C++ files excluded by code_categories")
        print("    ⏭️  All C/C++ files excluded by code_categories — skipped")
        return True

    # Print mode header
    if is_full_delta:
        mode_label = "L2 全量+Delta阻断"
    else:
        mode_label = "L1 增量检查" if is_delta else "全量检查"
    print(f"    📋 Mode: {mode_label} ({len(c_files)} file(s))")

    # Build suppression arguments from config + rule_overrides
    suppress_args = []
    for rule_id in suppress_rules:
        suppress_args.append("--suppress=misra-c2023-" + rule_id)
        suppress_args.append("--suppress=misra-c2012-" + rule_id)
    for override in rule_overrides:
        if not override.enabled and override.rule_id:
            suppress_args.append("--suppress=" + override.rule_id)

    # ── Auto-detect include paths and add -I flags ──
    include_paths = _detect_include_paths(project_dir)
    # Extra configured include dirs (e.g. embedded/freestanding_includes)
    if misra_cfg and misra_cfg.include_paths:
        for inc in misra_cfg.include_paths:
            inc_resolved = os.path.join(project_dir, inc) if not os.path.isabs(inc) else inc
            if os.path.isdir(inc_resolved) and inc_resolved not in include_paths:
                include_paths.append(inc_resolved)
    include_args = []
    for inc in include_paths:
        # Use project-relative -I so cppcheck emits relative file paths in its
        # output — otherwise absolute -I makes included .h paths absolute and
        # they never match project-relative suppressions-list entries.
        if os.path.isabs(inc):
            try:
                rel_inc = os.path.relpath(inc, project_dir)
                if not rel_inc.startswith(".."):
                    inc = rel_inc
            except ValueError:
                pass
        include_args.extend(["-I", inc])
    if include_args:
        log.info("Adding include paths: %s", " ".join(
            [inc for i, inc in enumerate(include_args) if i % 2 == 1]
        ))

    # Check for compile_commands.json and suggest it
    compile_db = os.path.join(project_dir, "compile_commands.json")
    if os.path.isfile(compile_db):
        log.info("Found compile_commands.json — consider using --project=compile_commands.json")

    # Construct cppcheck command
    cppcheck_suppressions = os.path.join(project_dir, ".cppcheck_suppressions")
    suppressions_list_args = []
    if os.path.isfile(cppcheck_suppressions):
        suppressions_list_args = ["--suppressions-list=" + cppcheck_suppressions]

    # AUTOSAR macro defines — suppress false positives from common
    # AUTOSAR platform constants that are not defined in source headers.
    define_args = [
        "-DSTD_ON", "-DSTD_OFF", "-DSTD_HIGH", "-DSTD_LOW",
        "-DSTD_ACTIVE", "-DSTD_IDLE",
        "-DNULL_PTR", "-DTRUE", "-DFALSE",
        "-DE_OK", "-DE_NOT_OK",
        "-DNULL",
    ]

    # ── cppcheck-config.h for AUTOSAR platform defines ──
    # Provides configuration constants for MISRA addon completeness.
    # Simplifies config analysis and suppresses [misra-config] false positives.
    cppcheck_config_h = os.path.join(project_dir, "cppcheck-config.h")
    if os.path.isfile(cppcheck_config_h):
        define_args.append("--include=" + cppcheck_config_h)
        define_args.append("--max-configs=1")
        if misra_cfg and misra_cfg.enabled:
            suppress_args.append("--suppress=misra-config")

    # Determine addon arg: use JSON config when rule_texts_path is set
    if misra_cfg and misra_cfg.rule_texts_path:
        rt_path = misra_cfg.rule_texts_path
        rt_resolved = os.path.join(project_dir, rt_path) if not os.path.isabs(rt_path) else rt_path
        if os.path.isfile(rt_resolved):
            # Use JSON addon config to pass --rule-texts to misra.py
            addon_json = os.path.join(project_dir, ".yuleosh", "misra-addon-config.json")
            if not os.path.isfile(addon_json):
                # Create dynamically
                import json as _json
                addon_cfg = {
                    "script": addon,
                    "python": "python3",
                    "args": ["--rule-texts=" + rt_resolved],
                }
                with open(addon_json, "w") as _f:
                    _json.dump(addon_cfg, _f, indent=2)
                log.info("Created addon JSON config: %s", addon_json)
            addon_arg = addon_json
        else:
            log.warning("rule_texts_path configured but file not found: %s", rt_resolved)
            addon_arg = addon
    else:
        addon_arg = addon

    cmd = [
        "cppcheck",
        "--addon=" + addon_arg,
        "--language=c",
        "--std=" + cppcheck_std,
        "--enable=" + enable,
        "--suppress=missingIncludeSystem",
        "--suppress=missingInclude",
        "--suppress=normalCheckLevelMaxBranches",
        "-q",
    ] + suppressions_list_args + define_args + include_args + suppress_args

    # Pass relative paths to cppcheck so output paths match suppressions-list
    # entries (which use project-relative paths like embedded/...). Absolute
    # paths would produce absolute output paths that never match the baseline.
    rel_c_files = []
    for f in c_files:
        if os.path.isabs(f):
            try:
                rel = os.path.relpath(f, project_dir)
                if not rel.startswith(".."):
                    rel_c_files.append(rel)
                    continue
            except ValueError:
                pass
        rel_c_files.append(f)
    cmd += rel_c_files

    try:
        start = time.perf_counter()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180, cwd=project_dir
        )
        elapsed = time.perf_counter() - start
    except FileNotFoundError:
        msg = "cppcheck not installed"
        print(f"    🔧 Fix: install cppcheck (e.g. 'apt install cppcheck' or 'brew install cppcheck')")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except subprocess.TimeoutExpired:
        msg = "cppcheck timed out after 180s"
        print(f"    🔧 Fix: increase timeout or reduce file count. Try 'cppcheck --project=compile_commands.json' for faster analysis")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except Exception as e:
        return _handle_stage_error(ci, "misra-check", "cppcheck execution error: " + str(e), strict)

    # Collect output (cppcheck writes MISRA warnings to stderr)
    output = result.stderr or result.stdout or ""

    # Process output through misra_report module
    summary = None
    try:
        # Try importing from the project-level ci/ directory
        sys.path.insert(0, project_dir)
        from yuleosh.ci.misra_report import (
            parse_cppcheck_output, group_by_rule, enrich_with_definitions,
            compute_summary_stats, save_report, load_rule_definitions,
            print_summary,
            generate_traceability_matrix,
            generate_fix_tasks,
        )
        sys.path.pop(0)

        # Rule definitions file: misra-rules.yaml in project root (NOT rule_texts_path)
        rule_defs_path = Path(project_dir) / "misra-rules.yaml"
        if not rule_defs_path.exists():
            rule_defs_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "misra-rules.yaml"

        rule_defs = load_rule_definitions(rule_defs_path)
        violations = parse_cppcheck_output(output)

        # ── 给每条违规标注代码类别 ──
        for v in violations:
            v_file = v.get("file", "")
            # Resolve relative path for category matching
            if not os.path.isabs(v_file):
                v_file_abs = os.path.join(project_dir, v_file)
            else:
                v_file_abs = v_file
            cat_name = file_category_map.get(v_file_abs, "business")
            v["code_category"] = cat_name

        groups = group_by_rule(violations)
        enriched_violations = enrich_with_definitions(violations, rule_defs)

        output_dir = Path(project_dir) / ".yuleosh" / "reports"

        # Apply deviations: mark matching violations as "acknowledged"
        # Store full deviation objects so reason/expiry are serialized correctly
        deviations_used: list[dict] = []
        for dev in deviations:
            if dev.rule_id and dev.file_pattern:
                deviations_used.append({
                    "rule_id": dev.rule_id,
                    "file_pattern": dev.file_pattern,
                    "reason": dev.reason or "",
                    "expires": dev.expires or None,
                    "approved_by": dev.approved_by or "",
                })

        # Count with deviation exemptions applied (approved deviations are
        # reported as acknowledged, not as required/advisory).
        summary = compute_summary_stats(enriched_violations, groups, rule_defs,
                                        deviations=deviations_used)

        save_report(enriched_violations, groups, summary, rule_defs, output_dir,
                    deviations=deviations_used)

        # ── 分类报告摘要 ──
        business_violations = [v for v in enriched_violations if v.get("code_category", "") == "business"]
        third_party_violations = [v for v in enriched_violations if v.get("code_category", "") == "third_party"]
        print(f"    📋 Code category breakdown: business={len(business_violations)}, third_party={len(third_party_violations)}")

        # --- Generate traceability matrix and fix tasks (MISRA loop closure) ---
        if violations:
            print_summary(summary)

            trace_matrix = generate_traceability_matrix(
                violations, rule_defs, deviations=deviations_used
            )
            print(f"    📋 Traceability: {len(trace_matrix)} entries")

            # Report deviation info
            if deviations:
                print(f"    📋 Deviations configured: {len(deviations)}")
                for dev in deviations:
                    print(f"      - {dev.rule_id} on {dev.file_pattern}: {dev.reason} (by {dev.approved_by}, expires {dev.expires})")

            try:
                fix_files = generate_fix_tasks(project_dir, violations, rule_defs, deviations=deviations_used)
                print(f"    🔧 Fix tasks created: {len(fix_files)} file(s)")
            except Exception as fix_e:
                log.warning("Failed to generate MISRA fix tasks: %s", fix_e)

            # Also check MISRA_FAIL_FAST (F-04 fix)
            misra_ff = is_misra_fail_fast()
            if misra_ff:
                print(f"    🚨 MISRA_FAIL_FAST enabled — violations will be treated as blocking")

            # ── 针对多级指针空违规 (GSCR-C-27.15) 输出修复建议 ──
            null_ptr_violations = [v for v in violations if "27.15" in (v.get("rule_id") or "") or "Dir-4.1" in (v.get("rule_id") or "")]
            for npv in null_ptr_violations:
                cat = npv.get("code_category", "business")
                np_file = npv.get("file", "")
                fix_suggestion = _format_null_pointer_fix(cat, np_file)
                if fix_suggestion:
                    print(fix_suggestion)

    except ImportError as e:
        log.warning("Could not import misra_report module: %s", e)
    except Exception as e:
        # P2-5 (S-P2-01): structured logging instead of traceback dump.
        log.warning("MISRA report formatting failed: %s", e, exc_info=True)

    # If report was saved but summary creation failed, reload from disk
    if summary is None:
        report_json = Path(project_dir) / ".yuleosh" / "reports" / "misra-report.json"
        if report_json.exists():
            try:
                with open(report_json) as _f:
                    _report_data = json.load(_f)
                summary = {
                    "total_violations": _report_data.get("total_violations", 0),
                    "unique_rules": _report_data.get("unique_rules", 0),
                    "affected_files": _report_data.get("affected_files", 0),
                    "total_source_lines": _report_data.get("total_source_lines", 0),
                    "by_severity": _report_data.get("by_severity", {}),
                    "by_rule_type": _report_data.get("by_rule_type", {}),
                    "density_per_kloc": _report_data.get("density_per_kloc", 0),
                }
                print(f"    📋 Summary reloaded from saved report (by_rule_type: {summary['by_rule_type']})")
            except Exception as _fe:
                log.warning("Failed to reload report for summary: %s", _fe)
                raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
                summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                          "severity_counts": {}, "unique_files": [], "per_file_counts": {}}
        else:
            raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
            summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                      "severity_counts": {}, "unique_files": [], "per_file_counts": {}}

    total_violations = summary["total_violations"]

    # Save raw output for debugging — BEFORE any early return so the raw
    # cppcheck output is always available even on the zero-violation path.
    try:
        misra_dir = Path(project_dir) / ".yuleosh" / "reports"
        misra_dir.mkdir(parents=True, exist_ok=True)
        raw_path = misra_dir / "misra-raw-output.txt"
        raw_path.write_text(output)
    except OSError as _we:
        log.warning("Failed to write misra raw output: %s", _we)

    # --- Determine pass/fail with enhanced rules (G-09) ---
    if total_violations == 0:
        ci.add_stage("misra-check", "passed", "No MISRA violations")
        print("    ✅ MISRA check passed — no violations")
        return True

    # Count required vs advisory violations from enriched groups
    # Fix P1.5-F: use summary's by_rule_type for accurate required/advisory counts.
    # enrich_with_definitions() returns a flat list (not a dict of groups),
    # so the old severity_category iteration over groups always returned 0.
    by_rule_type = summary.get("by_rule_type", {})
    required_count = by_rule_type.get("required", 0)
    advisory_count = by_rule_type.get("advisory", 0)

    # Estimate KLOC from checked files
    estimated_kloc = 0
    try:
        for cf in c_files:
            if os.path.isfile(cf):
                with open(cf) as _fh:
                    estimated_kloc += sum(1 for _ in _fh)
        estimated_kloc /= 1000.0
    except Exception:
        estimated_kloc = 0

    # ── GSCR: Translate MISRA violations to Corporate Standard Rules ──
    try:
        from yuleosh.ci.rulesets import RulesetRegistry
        gscr_ruleset = RulesetRegistry.get_default()
        if gscr_ruleset and gscr_ruleset.name != "misra-c2023":
            # Translate all violations to GSCR
            gscr_violations = gscr_ruleset.translate_violations(violations)

            # Save GSCR-enhanced report
            gscr_report_path = Path(project_dir) / ".yuleosh" / "reports" / "gscr-report.json"
            gscr_report = {
                "standard": gscr_ruleset.display_name,
                "version": "1.1",
                "generated_at": datetime.now().isoformat(),
                "total_violations": len(gscr_violations),
                "gscr_mapped": sum(1 for v in gscr_violations if v.get("gscr_rule_ids")),
                "gscr_unmapped": sum(1 for v in gscr_violations if not v.get("gscr_rule_ids")),
                "severity_counts": {
                    "S0": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S0"),
                    "S1": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S1"),
                    "S2": sum(1 for v in gscr_violations if v.get("gscr_severity", "") == "S2"),
                },
                "gscr_rule_counts": {},
                "violations": gscr_violations,
            }

            # Group by GSCR rule ID
            from collections import Counter
            gscr_rule_counter = Counter()
            for v in gscr_violations:
                for gid in v.get("gscr_rule_ids", []):
                    gscr_rule_counter[gid] += 1
            gscr_report["gscr_rule_counts"] = dict(gscr_rule_counter.most_common())

            gscr_report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(gscr_report_path, "w", encoding="utf-8") as f:
                json.dump(gscr_report, f, ensure_ascii=False, indent=2)

            print(f"    📋 GSCR report: {gscr_report['gscr_mapped']}/{gscr_report['total_violations']} "
                  f"violations mapped to corporate standard rules")

            # Show top 5 GSCR rules violated
            if gscr_report["gscr_rule_counts"]:
                print(f"    📋 Top GSCR rules violated:")
                for gid, count in list(gscr_report["gscr_rule_counts"].items())[:5]:
                    gscr_def = gscr_ruleset.rule_definitions().get("rules", {}).get(gid, {})
                    title = gscr_def.get("description_cn", gid)[:60]
                    print(f"        • {gid} ({gscr_def.get('severity', 'S2')}): {title} — {count} violation(s)")

            # Severity summary
            sc = gscr_report["severity_counts"]
            print(f"    📋 GSCR severity: S0={sc['S0']}, S1={sc['S1']}, S2={sc['S2']}")

        else:
            log.debug("Default ruleset is MISRA — no GSCR translation needed")

    except Exception as gscr_e:
        log.warning("GSCR translation failed (non-blocking): %s", gscr_e)

    # Raw output already written earlier (before the zero-violation early
    # return) — see the block above the pass/fail determination.

    # ── L2 Delta blocking: only block NEW Required violations ────
    new_required_count = 0
    if is_full_delta and total_violations > 0:
        try:
            baseline = _load_misra_baseline(project_dir)
            baseline_violations = baseline.get("violations", [])
            if baseline_violations:
                from yuleosh.ci.misra_report import parse_cppcheck_output
                # Re-parse violations for comparison
                current_violations = parse_cppcheck_output(output)
                new_required = [v for v in current_violations
                                if _is_new_required_violation(v, baseline_violations)]
                new_required_count = len(new_required)
                if new_required_count > 0:
                    print(f"    🆕 New Required violations since last baseline: {new_required_count}")
                    for nv in new_required[:5]:  # Show top 5
                        print(f"        - {nv.get('rule_id', '?')} in {nv.get('file', '?')}:{nv.get('line', '?')}")
                    if len(new_required) > 5:
                        print(f"        ... and {len(new_required) - 5} more")
        except (OSError, ValueError, KeyError) as delta_e:
            log.warning("MISRA L2 delta 计算失败，delta 阻断跳过（分类 fail-safe 仍兜底）: %s", delta_e)
            new_required_count = 0

    # ── 三级分类阻断计算 ──
    # 从 violations 中计算分类细目
    classification_failed = False
    try:
        from yuleosh.ci.misra_report import parse_cppcheck_output as _pco
        _current_violations = _pco(output)
        for _v in _current_violations:
            _vf = _v.get("file", "")
            _vfa = os.path.join(project_dir, _vf) if not os.path.isabs(_vf) else _vf
            _v["code_category"] = file_category_map.get(_vfa, "business")
        business_violations_c = [v for v in _current_violations if v.get("code_category", "") == "business"]
        third_party_violations_c = [v for v in _current_violations if v.get("code_category", "") == "third_party"]

        # Approved deviations exempt matching violations from gate counts.
        # (报告层 compute_summary_stats 已扣减，但 fail_threshold / violations_per_kloc
        #  门禁判定必须与报告语义一致，否则 approved deviation 无法通过门禁。)
        if deviations:
            try:
                from yuleosh.ci.misra_report.deviation import _match_deviation as _match_dev
                _approved_devs = [d for d in deviations
                                  if getattr(d, "status", None) in (None, "", "approved", "pending") or
                                  (isinstance(d, dict) and d.get("status") in (None, "", "approved", "pending"))]
                _filtered = []
                for _v in business_violations_c:
                    _vfile = _v.get("file", "")
                    # fnmatch 不递归匹配 '/'：必须用相对项目路径匹配 file_pattern
                    _vfile_rel = _vfile
                    if os.path.isabs(_vfile):
                        try:
                            _vfile_rel = os.path.relpath(_vfile, project_dir)
                        except ValueError:
                            _vfile_rel = _vfile
                    _vrule = _v.get("rule_id")
                    _matched = False
                    if _vrule:
                        _matched, _ = _match_dev(str(_vrule), _vfile_rel, _approved_devs)
                    if not _matched:
                        _filtered.append(_v)
                if len(_filtered) != len(business_violations_c):
                    log.info("MISRA deviations exempted %d violation(s) from gate counts",
                             len(business_violations_c) - len(_filtered))
                business_violations_c = _filtered
            except Exception as _dev_e:
                log.warning("MISRA deviation gate exemption failed (continuing without): %s", _dev_e)
    except (ValueError, KeyError, TypeError) as classif_e:
        # P2: 分类失败不得静默放行 —— 留 warning 日志 + 置 flag，
        # 由下方 0d fail-safe 阻断兜底（无法枚举违规时按 business 违规阻断）。
        log.warning("MISRA 三级分类失败，按 business 违规 fail-safe 阻断: %s", classif_e)
        classification_failed = True
        _current_violations = []
        business_violations_c = []
        third_party_violations_c = []

    # 确定 third_party 是否阻断
    third_party_cfg = code_categories.get("third_party", {})
    third_party_block_on = third_party_cfg.get("block_on", False)
    business_cfg = code_categories.get("business", {})
    business_block_on = business_cfg.get("block_on", True)

    # 仅针对 business 代码计算阻断阈值
    business_req = 0
    business_adv = 0
    business_total = len(business_violations_c)
    third_party_total = len(third_party_violations_c)

    # Blocking checks (in order of severity)
    should_block = False
    block_reasons = []

    # 0. L2: New Required violations block unconditionally (zero-delta)
    if is_full_delta and new_required_count > 0:
        should_block = True
        block_reasons.append(
            f"L2-P0: {new_required_count} new Required violation(s) since baseline "
            f"(zero-delta blocking)"
        )

    # 0b. 业务代码 Required violations (三级分类阻断)
    if business_block_on and business_total > 0:
        # Count only business Required violations
        for v in business_violations_c:
            if v.get("severity", "").lower() in ("error", "warning"):
                business_req += 1
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} business-code violation(s) (business.block_on=True)")

    # 0c. 第三方库按 block_on 配置
    if third_party_block_on and third_party_total > 0:
        should_block = True
        block_reasons.append(f"{third_party_total} third-party violation(s) (third_party.block_on=True)")
    elif not third_party_block_on and third_party_total > 0:
        print(f"    ℹ️  Third-party violations ({third_party_total}) do not block (third_party.block_on=False)")

    # 0d. 三级分类失败 → fail-safe 阻断（工程诚实：内部失败不得静默放行）
    # 注意: block_reasons 清空逻辑只清含 "business-code" 或 "fail_on_" 的
    # reason，本条 reason 不受影响，安全放在 profile 过滤之前。
    if classification_failed:
        should_block = True
        block_reasons.append("MISRA 三级分类失败，fail-safe 阻断（不静默放行）")

    # ── Profile-based blocking filter (QG-002) ──
    # Only block on violation tiers that are in the active profile's block_on list
    # Mapping: profile tier → severity_category value in cppcheck output
    profile_tier_to_severity = {
        "mandatory": ["error", "warning"],
        "required": ["required"],
        "advisory": ["advisory", "style"],
    }
    # Build a set of severity values that should block based on active profile
    blocking_severities: set[str] = set()
    for tier in profile_block_on:
        blocking_severities.update(profile_tier_to_severity.get(tier, []))

    # Count business violations that match the profile's block_on severity tiers
    business_blocking = 0
    if business_violations_c:
        for v in business_violations_c:
            sev = v.get("severity_category", v.get("severity", "")).lower()
            if sev in blocking_severities:
                business_blocking += 1

    has_blocking_violations = business_blocking > 0

    # If profile filtering says no blocking violations exist, clear should_block reasons
    # that were added by generic checks above (code-category checks are unaffected)
    if profile_block_on and not has_blocking_violations:
        # Only clear reasons that are not code-category related
        generic_block_reasons = [r for r in block_reasons if "business-code" in r or "fail_on_" in r]
        for r in generic_block_reasons:
            if r in block_reasons:
                block_reasons.remove(r)
                if r in block_reasons:
                    block_reasons.remove(r)  # handle duplicates
        if block_reasons:
            # Still other reasons (e.g., code-category, threshold) remain
            pass
        elif should_block and not has_blocking_violations:
            # No other reasons — profile says this shouldn't block
            should_block = False

    if profile_block_on:
        profile_block_str = ", ".join(profile_block_on)
        print(f"    📋 Profile block_on={profile_block_str}: {business_blocking} business-code blocking violations")

    # 1. Required violations with fail_on_required (G-09) — 仅对 business 代码生效
    # Profile-aware: only counts if "required" is in profile_block_on
    if not profile_block_on or "required" in profile_block_on:
        if fail_on_required and required_count > 0 and business_block_on:
            if business_req > 0:
                should_block = True
                block_reasons.append(f"{business_req} Required business-code violation(s) (fail_on_required=True)")

    # 1b. Legacy: fail_on_violation master switch
    if fail_on_violation and required_count > 0 and business_block_on:
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} business-code violation(s) (fail_on_violation=True)")

    # 2. Total violations >= fail_threshold (仅 business 代码) — profile-aware
    # Only count violations whose severity matches the profile's rules
    if profile_block_on and profile_rules:
        profile_severities_for_check: set[str] = set()
        for tier in profile_rules:
            profile_severities_for_check.update(profile_tier_to_severity.get(tier, []))
        business_profile_total = sum(
            1 for v in business_violations_c
            if v.get("severity_category", v.get("severity", "")).lower() in profile_severities_for_check
        )
    else:
        business_profile_total = business_total

    if fail_threshold > 0 and business_profile_total >= fail_threshold:
        should_block = True
        block_reasons.append(f"{business_profile_total} business-code violation(s) (profile-matching) >= threshold {fail_threshold}")

    # 3. Violations per KLOC (仅 business 文件的 KLOC) — profile-aware
    if violations_per_kloc > 0 and estimated_kloc > 0:
        actual_vpkloc = business_profile_total / max(estimated_kloc, 0.001)
        if actual_vpkloc > violations_per_kloc:
            should_block = True
            block_reasons.append(
                f"{actual_vpkloc:.1f} business-code (profile-matching) violations/kloc > limit {violations_per_kloc}"
            )

    # Advisory-blocking (separate flag) — 仅 business, profile-aware
    if not profile_block_on or "advisory" in profile_block_on:
        if fail_on_advisory and advisory_count > 0 and business_block_on:
            should_block = True
            block_reasons.append(f"{advisory_count} Advisory business-code violation(s) (fail_on_advisory=True)")

    detail = (
        f"{total_violations} MISRA violation(s) "
        f"({required_count} required, {advisory_count} advisory) — "
        f"see .yuleosh/reports/misra-report.json"
    )

    # ── Append trend entry ─────────────────────────────────────────
    try:
        from yuleosh.ci.misra_trend import append_entry, _print_trend_summary
        commit = _get_git_commit(project_dir)
        append_entry(
            project_dir=project_dir,
            total_violations=total_violations,
            required=required_count,
            advisory=advisory_count,
            files_checked=len(c_files),
            is_delta=is_delta,
            commit=commit,
        )
        _print_trend_summary(project_dir)
    except Exception as trend_e:
        log.debug("MISRA trend append skipped: %s", trend_e)
    # ────────────────────────────────────────────────────────────────

    if should_block:
        ci.add_stage("misra-check", "failed", "; ".join(block_reasons))
        print(f"    ❌ MISRA check FAILED: {detail}")
        for br in block_reasons:
            print(f"        • {br}")
        return False

    # Advisory violations over threshold → warning but don't block
    if advisory_count > 0 and not fail_on_advisory:
        ci.add_stage("misra-check", "warning", detail)
        print(f"    ⚠️  MISRA check: {detail}")
        print(f"        Advisory violations ({advisory_count}) do not block pipeline")
        print(f"    📍 Full report: .yuleosh/reports/misra-report.json")
        return True

    ci.add_stage("misra-check", "passed", detail)
    print(f"    ✅ MISRA check: {detail}")
    print(f"    📍 Full report: .yuleosh/reports/misra-report.json")
    return True
