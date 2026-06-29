#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Stages — Review stage execution functions.

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


def _categorize_file(filepath: str, categories: dict) -> tuple[str, dict]:
    """根据文件路径判断代码类别，返回 (category_name, category_config)。

    匹配优先级: template > third_party > business。
    无匹配时默认返回 ("business", business_config).
    """
    basename = os.path.basename(filepath)
    # Priority order: template, third_party, business
    priority_order = ["template", "third_party", "business"]
    for cat_name in priority_order:
        cat_cfg = categories.get(cat_name, {})
        for pattern in cat_cfg.get("paths", []):
            if fnmatch.fnmatch(filepath, pattern) or \
               fnmatch.fnmatch(basename, pattern):
                return cat_name, cat_cfg
    # Fallback: business
    return "business", categories.get("business", {})


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


def _exclude_paths(files: list[str], exclude_patterns: list[str], project_dir: str) -> list[str]:
    """Filter out files matching any of the exclude patterns (glob-style).

    Patterns like "tests/**" are matched relative to project_dir.
    """
    if not exclude_patterns:
        return files

    filtered = []
    for f in files:
        # Get relative path
        if os.path.isabs(f):
            try:
                rel = os.path.relpath(f, project_dir)
            except ValueError:
                rel = f
        else:
            rel = f

        excluded = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel, pattern):
                excluded = True
                break

        if not excluded:
            filtered.append(f)

    excluded_count = len(files) - len(filtered)
    if excluded_count > 0:
        log.info("Excluded %d file(s) via exclude_paths patterns", excluded_count)

    return filtered


def _detect_include_paths(project_dir: str) -> list[str]:
    """Auto-detect common include directories for cppcheck -I flags.

    Scans project_dir for standard C/C++ include directories
    that exist on disk.
    """
    candidates = [
        ".",
        "src",
        "include",
        "inc",
        "tests",
        "tests/unity/src",
        "Drivers",
        "Drivers/CMSIS",
        "Drivers/CMSIS/Include",
        "Drivers/STM32F4xx_HAL_Driver",
        "Drivers/STM32F4xx_HAL_Driver/Inc",
        "Middlewares",
        "third_party",
        "lib",
        "common",
    ]
    found = []
    for c in candidates:
        full = os.path.join(project_dir, c)
        if os.path.isdir(full):
            found.append(full)
    return found


def _get_git_commit(project_dir: str) -> str:
    """Get short git commit hash from the project directory."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=project_dir,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

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
    suppress_rules = misra_cfg.suppress_rules if misra_cfg else []
    rule_overrides = misra_cfg.rule_overrides if misra_cfg else []
    deviations = misra_cfg.deviations if misra_cfg else []
    strict = is_strict()

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
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            # If no git diff, fall back to empty (skip delta check)
    elif mode == "full":
        # L2: full scan + delta blocking on new Required
        is_full_delta = True
        if target_files is not None:
            c_files = [f for f in target_files
                       if f.endswith((".c", ".cpp")) and os.path.isfile(
                           os.path.join(project_dir, f) if not os.path.isabs(f) else f)]
        if not c_files:
            src_dir = os.path.join(project_dir, "src")
            if os.path.isdir(src_dir):
                for root, dirs, files in os.walk(src_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                    for f in files:
                        if f.endswith((".c", ".cpp")):
                            c_files.append(os.path.join(root, f))
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
                src_dir = os.path.join(project_dir, "src")
                if os.path.isdir(src_dir):
                    for root, dirs, files in os.walk(src_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                        for f in files:
                            if f.endswith((".c", ".cpp")):
                                c_files.append(os.path.join(root, f))

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
    include_args = []
    for inc in include_paths:
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
    cmd = [
        "cppcheck",
        "--addon=" + addon,
        "--language=c",
        "--std=" + cppcheck_std,
        "--enable=all",
        "--suppress=missingIncludeSystem",
        "-q",
    ] + include_args + suppress_args + c_files

    try:
        start = time.perf_counter()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=project_dir
        )
        elapsed = time.perf_counter() - start
    except FileNotFoundError:
        msg = "cppcheck not installed"
        print(f"    🔧 Fix: install cppcheck (e.g. 'apt install cppcheck' or 'brew install cppcheck')")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except subprocess.TimeoutExpired:
        msg = "cppcheck timed out after 120s"
        print(f"    🔧 Fix: increase timeout or reduce file count. Try 'cppcheck --project=compile_commands.json' for faster analysis")
        return _handle_stage_error(ci, "misra-check", msg, strict)
    except Exception as e:
        return _handle_stage_error(ci, "misra-check", "cppcheck execution error: " + str(e), strict)

    # Collect output (cppcheck writes MISRA warnings to stderr)
    output = result.stderr or result.stdout or ""

    # Process output through misra_report module
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

        rule_defs_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "misra-rules.yaml"
        if misra_cfg and misra_cfg.rule_texts_path:
            rule_defs_path = Path(misra_cfg.rule_texts_path)

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
        groups = enrich_with_definitions(groups, rule_defs)
        summary = compute_summary_stats(violations, groups)

        output_dir = Path(project_dir) / ".yuleosh" / "reports"

        # Apply deviations: mark matching violations as "acknowledged"
        deviations_used: list[tuple[str, str]] = []
        for dev in deviations:
            if dev.rule_id and dev.file_pattern:
                deviations_used.append((dev.rule_id, dev.file_pattern))

        save_report(violations, groups, summary, rule_defs, output_dir,
                    deviations=deviations_used)

        # ── 分类报告摘要 ──
        business_violations = [v for v in violations if v.get("code_category", "") == "business"]
        third_party_violations = [v for v in violations if v.get("code_category", "") == "third_party"]
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
            null_ptr_violations = [v for v in violations if "27.15" in v.get("rule_id", "") or "Dir-4.1" in v.get("rule_id", "")]
            for npv in null_ptr_violations:
                cat = npv.get("code_category", "business")
                np_file = npv.get("file", "")
                fix_suggestion = _format_null_pointer_fix(cat, np_file)
                if fix_suggestion:
                    print(fix_suggestion)

    except ImportError as e:
        log.warning("Could not import misra_report module: %s", e)
        raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
        summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                    "severity_counts": {}, "unique_files": [], "per_file_counts": {}}
    except Exception as e:
        log.warning("MISRA report formatting failed: %s", e)
        raw_violations = sum(1 for line in output.splitlines() if "misra" in line.lower())
        summary = {"total_violations": raw_violations, "total_rules_violated": 0,
                    "severity_counts": {}, "unique_files": [], "per_file_counts": {}}

    total_violations = summary["total_violations"]

    # --- Determine pass/fail with enhanced rules (G-09) ---
    if total_violations == 0:
        ci.add_stage("misra-check", "passed", "No MISRA violations")
        print("    ✅ MISRA check passed — no violations")
        return True

    # Count required vs advisory violations from enriched groups
    required_count = 0
    advisory_count = 0
    for g in groups.values():
        sev = g.get("severity_category", "").lower()
        if sev == "required":
            required_count += g["count"]
        elif sev == "advisory":
            advisory_count += g["count"]

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

    # Save raw output for debugging
    misra_dir = Path(project_dir) / ".yuleosh" / "reports"
    misra_dir.mkdir(parents=True, exist_ok=True)
    raw_path = misra_dir / "misra-raw-output.txt"
    raw_path.write_text(output)

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
        except Exception as delta_e:
            log.debug("L2 delta blocking skipped: %s", delta_e)
            new_required_count = 0

    # ── 三级分类阻断计算 ──
    # 从 violations 中计算分类细目
    try:
        from yuleosh.ci.misra_report import parse_cppcheck_output as _pco
        _current_violations = _pco(output)
        for _v in _current_violations:
            _vf = _v.get("file", "")
            _vfa = os.path.join(project_dir, _vf) if not os.path.isabs(_vf) else _vf
            _v["code_category"] = file_category_map.get(_vfa, "business")
        business_violations_c = [v for v in _current_violations if v.get("code_category", "") == "business"]
        third_party_violations_c = [v for v in _current_violations if v.get("code_category", "") == "third_party"]
    except Exception:
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

    # 1. Required violations with fail_on_required (G-09) — 仅对 business 代码生效
    if fail_on_required and required_count > 0 and business_block_on:
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} Required business-code violation(s) (fail_on_required=True)")

    # 1b. Legacy: fail_on_violation master switch
    if fail_on_violation and required_count > 0 and business_block_on:
        if business_req > 0:
            should_block = True
            block_reasons.append(f"{business_req} business-code violation(s) (fail_on_violation=True)")

    # 2. Total violations >= fail_threshold (仅 business 代码)
    if fail_threshold > 0 and business_total >= fail_threshold:
        should_block = True
        block_reasons.append(f"{business_total} business-code violation(s) >= threshold {fail_threshold}")

    # 3. Violations per KLOC (仅 business 文件的 KLOC)
    if violations_per_kloc > 0 and estimated_kloc > 0:
        actual_vpkloc = business_total / max(estimated_kloc, 0.001)
        if actual_vpkloc > violations_per_kloc:
            should_block = True
            block_reasons.append(
                f"{actual_vpkloc:.1f} business-code violations/kloc > limit {violations_per_kloc}"
            )

    # Advisory-blocking (separate flag) — 仅 business
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
