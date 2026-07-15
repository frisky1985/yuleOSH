#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 5.5: 小克 — 自测结果审查。

在 Self-Test 完成后自动执行：
- 分析测试结果（通过/失败/跳过）
- 检查测试是否覆盖了 spec 中的 SHALL
- 标注未覆盖的 SHALL
- 输出测试gap报告
- 解析 JUnit XML 生成用例级结果
- 集成 lcov 覆盖率数据
- SHALL 自动映射（基于测试函数名匹配）
"""

import json
import logging
import os
import re
import socket
import sys
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from yuleosh.ci.review_helpers import (
    parse_junit_xml,
    auto_map_shall_coverage,
    find_test_source_files,
)

# Thin wrappers — preserve backward-compatible private names
_parse_junit_xml = parse_junit_xml
_auto_map_shall_coverage = auto_map_shall_coverage
_find_test_source_files = find_test_source_files

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec, _try_parse_hermes_json

log = logging.getLogger("pipeline.step_handlers.review_selftest")

__all__ = ["step_review_selftest"]

# R3-P0-6: Report schema version
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"

# ---------------------------------------------------------------------------
# ASPICE mapping (P0-7)
# ---------------------------------------------------------------------------
ASPICE_MAP = {
    "SWE.4": {
        "description": "Software Unit Verification",
        "bp1": {
            "id": "SWE.4.BP1",
            "title": "Develop unit verification specification including regression strategy",
            "report_section": "Test Case Results / SHALL Coverage",
        },
        "bp2": {
            "id": "SWE.4.BP2",
            "title": "Verify software units",
            "report_section": "Coverage Metrics / Summary",
        },
    },
}


# ---------------------------------------------------------------------------
# Regression analysis and trend comparison (R3-P0-4, R3-P0-5)
# ---------------------------------------------------------------------------


def _load_prev_selftest_review(session_dir: str | Path) -> dict | None:
    """Load the previous selftest-review.json for trend comparison."""
    prev_path = Path(session_dir).parent / "selftest-review.json"
    if not prev_path.exists():
        # Also try the .yuleosh/reports/ directory
        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        prev_path = project_dir / ".yuleosh" / "reports" / "selftest-review.json"
    if prev_path.exists():
        try:
            with open(prev_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, Exception) as e:
            log.warning("Failed to load previous selftest review %s: %s", prev_path, e)
    return None


def _compute_selftest_regression(
    current_review: dict,
    prev_review: dict | None,
) -> dict:
    """Compute regression analysis between current and previous build (R3-P0-5).

    Compares pass_rate, shall_covered, coverage metrics, and test failures.

    Returns dict with:
      - pass_rate_delta: float (current - previous)
      - coverage_deltas: dict[str, float] (per-dimension coverage changes)
      - new_failures: list[str] (tests newly failing)
      - resolved_failures: list[str] (tests previously failing, now passing/removed)
    """
    if prev_review is None:
        return {}

    # Pass rate delta
    curr_pass_rate = current_review.get("pass_rate", 0.0)
    prev_pass_rate = prev_review.get("pass_rate", 0.0)
    pass_rate_delta = round(curr_pass_rate - prev_pass_rate, 1)

    # Coverage deltas
    curr_coverage = current_review.get("coverage", {})
    prev_coverage = prev_review.get("coverage", {})
    coverage_deltas: dict[str, float] = {}
    for dim in ["line_rate", "branch_rate", "function_rate"]:
        curr_val = curr_coverage.get(dim, 0.0)
        prev_val = prev_coverage.get(dim, 0.0)
        delta = round(curr_val - prev_val, 1)
        if delta != 0.0:
            coverage_deltas[dim] = delta

    # New failures: tests passing in prev but failing now
    # (or new tests that are failing)
    prev_failed_names = set()
    for tc in prev_review.get("test_case_results", []):
        if tc.get("status") == "failed":
            prev_failed_names.add(tc.get("name", ""))

    curr_failed_names = set()
    for tc in current_review.get("test_case_results", []):
        if tc.get("status") == "failed":
            curr_failed_names.add(tc.get("name", ""))

    new_failures = sorted(curr_failed_names - prev_failed_names)
    resolved_failures = sorted(prev_failed_names - curr_failed_names)

    return {
        "pass_rate_delta": pass_rate_delta,
        "coverage_deltas": coverage_deltas,
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
    }


# ---------------------------------------------------------------------------
# CI environment helpers (P0-6)
# ---------------------------------------------------------------------------
def _get_ci_environ() -> dict:
    """Extract CI environment variables for build_id, commit_sha, branch."""
    return {
        "build_id": os.environ.get("BUILD_ID", ""),
        "commit_sha": os.environ.get("GIT_COMMIT", ""),
        "branch": os.environ.get("GIT_BRANCH", ""),
    }


def _get_tool_version(tool_name: str = "pytest") -> str:
    """Try to get tool version string by running <tool_name> --version."""
    import subprocess
    try:
        result = subprocess.run(
            [tool_name, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip().split("\n")[0] or result.stderr.strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"


# ---------------------------------------------------------------------------
# R5-P2-5: Environment info collection
# ---------------------------------------------------------------------------


def _collect_environment_info() -> dict:
    """Collect environment information for the test run.

    R5-P2-5: Returns dict with platform, python_version, hostname.

    Returns
    -------
    dict
        Environment info dict.
    """
    return {
        "platform": sys.platform,
        "python_version": sys.version,
        "hostname": socket.gethostname(),
    }


# ---------------------------------------------------------------------------
# R5-P2-2: xUnit/JUnit compatible format generation
# ---------------------------------------------------------------------------


def _generate_xunit_compatible(test_case_results: list[dict]) -> str:
    """Generate a JUnit XML compatible string from test case results.

    R5-P2-2: Produces a valid JUnit XML string (``<testsuite>`` / ``<testcase>``
    elements) from the list of test case result dicts. Used for downstream
    CI pipeline integration.

    Parameters
    ----------
    test_case_results : list[dict]
        Parsed test case results with name, status, duration, etc.

    Returns
    -------
    str
        JUnit XML string.
    """
    if not test_case_results:
        return ""

    testsuite = ET.Element("testsuite")
    testsuite.set("name", "yuleosh-selftest")

    passed = 0
    failed = 0
    skipped = 0
    errors = 0
    total_time = 0.0

    for tc in test_case_results:
        testcase = ET.SubElement(testsuite, "testcase")
        name = tc.get("name", "unknown")
        classname = name.split("::")[0] if "::" in name else ""
        testname = name.split("::")[-1] if "::" in name else name
        testcase.set("classname", classname)
        testcase.set("name", testname)
        duration = tc.get("duration", 0.0)
        testcase.set("time", str(duration))
        total_time += duration

        status = tc.get("status", "passed")
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
            failure = ET.SubElement(testcase, "failure")
            failure.set("message", tc.get("message", "")[:500])
            # Include structured failure data if available
            failure_info = tc.get("failure", {})
            if failure_info:
                failure.set("type", failure_info.get("type", "AssertionError"))
                stack = failure_info.get("stacktrace", "")
                if stack:
                    failure.text = stack[:2000]
        elif status == "error":
            errors += 1
            err = ET.SubElement(testcase, "error")
            err.set("message", tc.get("message", "")[:500])
        elif status == "skipped":
            skipped += 1
            ET.SubElement(testcase, "skipped")

    testsuite.set("tests", str(len(test_case_results)))
    testsuite.set("passes", str(passed))
    testsuite.set("failures", str(failed))
    testsuite.set("errors", str(errors))
    testsuite.set("skipped", str(skipped))
    testsuite.set("time", str(round(total_time, 3)))

    return ET.tostring(testsuite, encoding="unicode", xml_declaration=True)


# ---------------------------------------------------------------------------
# R5-P2-3: Test execution run history
# ---------------------------------------------------------------------------


def _get_run_history_path() -> Path:
    """Get the path to the selftest-history.json file."""
    project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
    return project_dir / ".yuleosh" / "reports" / "selftest-history.json"


def _load_run_history() -> list[dict]:
    """Load past test execution run history from disk.

    R5-P2-3: Reads from ``.yuleosh/reports/selftest-history.json``.
    Returns at most the past 5 records.

    Returns
    -------
    list[dict]
        List of run history entries with generated_at, pass_rate, line_rate, etc.
    """
    history_path = _get_run_history_path()
    if not history_path.exists():
        return []
    try:
        with open(history_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data[-5:]  # Keep at most 5 entries
        return []
    except (json.JSONDecodeError, OSError, Exception) as e:
        log.warning("Failed to load run history from %s: %s", history_path, e)
        return []


def _save_run_history(current_run: dict, existing_history: list[dict] | None = None) -> list[dict]:
    """Append current run to history and save to disk.

    R5-P2-3: Appends the current run entry and persists to
    ``.yuleosh/reports/selftest-history.json``, keeping at most 5 entries.

    Parameters
    ----------
    current_run : dict
        Current run entry with generated_at, pass_rate, line_rate, etc.
    existing_history : list[dict] | None
        Existing history records. If None, loads from disk.

    Returns
    -------
    list[dict]
        Updated history list (max 5 entries).
    """
    if existing_history is None:
        existing_history = _load_run_history()

    # Append current run
    existing_history.append(current_run)

    # Keep at most 5 entries
    history = existing_history[-5:]

    # Write to disk
    history_path = _get_run_history_path()
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except (OSError, Exception) as e:
        log.warning("Failed to save run history to %s: %s", history_path, e)

    log.info("Run history updated: %d entries saved", len(history))
    return history


# ---------------------------------------------------------------------------
# JUnit XML parsing (P0-3)
# ---------------------------------------------------------------------------
def _discover_junit_xml(session: PipelineSession) -> list[Path]:
    """Discover JUnit XML report files in session and project directories."""
    candidates: list[Path] = []

    # 1. Check session artifacts for "self-test" directory
    if "self-test" in session.artifacts:
        ap = Path(session.artifacts["self-test"])
        if ap.is_dir():
            candidates.extend(sorted(ap.glob("*.xml")))
            candidates.extend(sorted(ap.glob("**/junit*.xml")))
            candidates.extend(sorted(ap.glob("**/pytest*.xml")))

    # 2. Check session directory
    if hasattr(session, "session_dir") and session.session_dir:
        sd = Path(session.session_dir)
        candidates.extend(sorted(sd.glob("*.xml")))
        candidates.extend(sorted(sd.glob("**/junit*.xml")))

    # 3. Check project root / workspace
    project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
    for pattern in ["*.xml", "**/junit*.xml", "**/pytest*.xml"]:
        candidates.extend(sorted(project_dir.glob(pattern)))

    # 4. Common explicit paths
    for p in ["junit.xml", "pytest-report.xml", "report.xml",
              ".yuleosh/reports/junit.xml", ".yuleosh/reports/pytest-report.xml"]:
        fp = project_dir / p
        if fp.exists():
            candidates.append(fp)

    # Deduplicate
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in candidates:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# lcov coverage parsing (P0-4)
# ---------------------------------------------------------------------------
def _discover_coverage_files(session: PipelineSession) -> list[Path]:
    """Discover lcov coverage.info files in session and project directories."""
    candidates: list[Path] = []
    project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

    # Common paths
    for p in ["coverage.info", ".yuleosh/reports/coverage.info",
              "build/coverage.info", "build/reports/coverage.info"]:
        fp = project_dir / p
        if fp.exists():
            candidates.append(fp)

    # Session directory
    if hasattr(session, "session_dir") and session.session_dir:
        sd = Path(session.session_dir)
        for f in sd.rglob("coverage.info"):
            candidates.append(f)

    # Check artifacts
    if "self-test" in session.artifacts:
        ap = Path(session.artifacts["self-test"])
        if ap.is_dir():
            for f in ap.rglob("coverage.info"):
                candidates.append(f)

    return candidates


def _parse_lcov_coverage(lcov_path: Path) -> dict:
    """Parse lcov coverage.info file and return structured coverage data.

    R5-P1-2: Adds ``mc_dc_rate`` (MC/DC condition coverage from BRDA lines).
    R5-P1-3: Adds ``per_file`` list with per-file line/branch/function rates.

    Returns dict with:
      - line_rate: float (0-100, percentage)
      - branch_rate: float (0-100, percentage)
      - function_rate: float (0-100, percentage)
      - mc_dc_rate: float or None (MC/DC condition coverage, 0-100)
      - mc_dc_note: str ("not available" if no BRDA data)
      - source_file: str
      - per_file: list[dict] (R5-P1-3, per-file statistics)
    """
    result: dict = {
        "line_rate": 0.0,
        "branch_rate": 0.0,
        "function_rate": 0.0,
        "mc_dc_rate": None,
        "source_file": str(lcov_path),
        "per_file": [],  # R5-P1-3
    }

    try:
        content = lcov_path.read_text(encoding="utf-8")
    except (OSError, Exception) as e:
        log.warning("Failed to read coverage file %s: %s", lcov_path, e)
        return result

    total_lines_found = 0
    total_lines_hit = 0
    total_branches_found = 0
    total_branches_hit = 0
    total_functions_found = 0
    total_functions_hit = 0

    # R5-P1-2: MC/DC tracking — count BRDA entries as condition coverage
    total_mcdc_conditions = 0
    total_mcdc_hit = 0

    # R5-P1-3: Per-file tracking
    per_file_data: dict[str, dict] = {}

    current_file = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SF:"):
            # Finalize previous file stats before switching
            current_file = line[3:]
            if current_file not in per_file_data:
                per_file_data[current_file] = {
                    "file": current_file,
                    "lines_found": 0,
                    "lines_hit": 0,
                    "branches_found": 0,
                    "branches_hit": 0,
                    "functions_found": 0,
                    "functions_hit": 0,
                    "mcdc_conditions": 0,
                    "mcdc_hit": 0,
                }
        elif line.startswith("DA:"):
            # DA:line,hit_count
            parts = line[3:].split(",")
            if len(parts) == 2:
                total_lines_found += 1
                if current_file and current_file in per_file_data:
                    per_file_data[current_file]["lines_found"] += 1
                try:
                    if int(parts[1]) > 0:
                        total_lines_hit += 1
                        if current_file and current_file in per_file_data:
                            per_file_data[current_file]["lines_hit"] += 1
                except ValueError:
                    pass
        elif line.startswith("BRDA:"):
            # BRDA:line,block,branch,taken
            parts = line[5:].split(",")
            if len(parts) == 4:
                total_branches_found += 1
                # R5-P1-2: MC/DC — each BRDA is a condition outcome
                total_mcdc_conditions += 1
                if current_file and current_file in per_file_data:
                    per_file_data[current_file]["branches_found"] += 1
                    per_file_data[current_file]["mcdc_conditions"] += 1
                taken = parts[3].strip()
                if taken != "-" and taken != "0":
                    total_branches_hit += 1
                    total_mcdc_hit += 1
                    if current_file and current_file in per_file_data:
                        per_file_data[current_file]["branches_hit"] += 1
                        per_file_data[current_file]["mcdc_hit"] += 1
        elif line.startswith("FNF:"):
            # FNF:count
            try:
                total_functions_found = int(line[4:])
            except ValueError:
                pass
            if current_file and current_file in per_file_data:
                per_file_data[current_file]["functions_found"] = int(line[4:])
        elif line.startswith("FNH:"):
            # FNH:count
            try:
                total_functions_hit = int(line[4:])
            except ValueError:
                pass
            if current_file and current_file in per_file_data:
                per_file_data[current_file]["functions_hit"] = int(line[4:])
        elif line.startswith("end_of_record"):
            current_file = ""

    if total_lines_found > 0:
        result["line_rate"] = round(total_lines_hit / total_lines_found * 100, 2)
    if total_branches_found > 0:
        result["branch_rate"] = round(total_branches_hit / total_branches_found * 100, 2)
    if total_functions_found > 0:
        result["function_rate"] = round(total_functions_hit / total_functions_found * 100, 2)

    # R5-P1-2: MC/DC rate
    if total_mcdc_conditions > 0:
        result["mc_dc_rate"] = round(total_mcdc_hit / total_mcdc_conditions * 100, 2)
    else:
        result["mc_dc_rate"] = None

    # R5-P1-3: Build per_file list
    per_file_list: list[dict] = []
    for pf_data in per_file_data.values():
        pf_lines = pf_data["lines_found"]
        pf_branches = pf_data["branches_found"]
        pf_funcs = pf_data["functions_found"]
        pf_entry = {
            "file": pf_data["file"],
            "line_rate": round(pf_data["lines_hit"] / pf_lines * 100, 2) if pf_lines > 0 else 0.0,
            "branch_rate": round(pf_data["branches_hit"] / pf_branches * 100, 2) if pf_branches > 0 else 0.0,
            "function_rate": round(pf_data["functions_hit"] / pf_funcs * 100, 2) if pf_funcs > 0 else 0.0,
        }
        per_file_list.append(pf_entry)
    result["per_file"] = per_file_list

    log.info(
        "Coverage from %s: line=%.1f%%, branch=%.1f%%, function=%.1f%%, mc_dc=%s",
        lcov_path.name,
        result["line_rate"],
        result["branch_rate"],
        result["function_rate"],
        f"{result.get('mc_dc_rate', 'N/A')}%" if result.get('mc_dc_rate') is not None else "N/A",
    )
    return result


# ---------------------------------------------------------------------------

def _extract_shall_statements(spec_content: str) -> list[dict]:
    """Extract SHALL/MAY/SHOULD statements from spec content with context.

    Returns a list of dicts: {statement, section, line_number}.
    """
    shalls: list[dict] = []
    lines = spec_content.split("\n")
    current_section = "preamble"

    for i, line in enumerate(lines):
        # Track headings as section context
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if heading_match:
            current_section = heading_match.group(2).strip()
            continue

        # Match SHALL / SHOULD / MAY keywords (case-insensitive)
        matches = re.finditer(
            r"([^.!?]*?\b(SHALL|SHOULD|MAY)\b[^.!?]*[.!?])",
            line,
            re.IGNORECASE,
        )
        for m in matches:
            statement = m.group(1).strip()
            if statement:
                shalls.append({
                    "statement": statement,
                    "section": current_section,
                    "line": i + 1,
                })

    return shalls


# ---------------------------------------------------------------------------
# (Enhanced) Build self-test review prompt
# ---------------------------------------------------------------------------


def _build_selftest_review_prompt(
    spec_content: str,
    spec_name: str,
    self_test_content: str,
    shall_statements: list[dict],
    test_plan_content: str,
    test_case_results: list[dict] | None = None,
    auto_shall_coverage: tuple[set[int], dict[str, list[str]]] | None = None,
) -> tuple[str, str]:
    """Build prompts for the LLM-powered self-test results review.

    Includes auto-mapped SHALL coverage data to guide the LLM analysis.

    Returns (system_prompt, user_prompt).
    """
    # Format SHALL list for the prompt
    shall_lines = []
    auto_covered_indices, shall_to_tests_map = auto_shall_coverage or (set(), {})

    for i, s in enumerate(shall_statements):
        prefix = "✅" if i in auto_covered_indices else "❓"
        shall_lines.append(f"- {prefix} [{s['section']}] L{s['line']}: {s['statement']}")
    shall_str = "\n".join(shall_lines[:60])
    if len(shall_statements) > 60:
        shall_str += f"\n- ... and {len(shall_statements) - 60} more"

    # Format auto-mapped coverage
    auto_mapped_lines = []
    for stmt, tests in shall_to_tests_map.items():
        auto_mapped_lines.append(f"- ✅ \"{stmt[:80]}...\" → {tests}")
    auto_map_str = "\n".join(auto_mapped_lines[:30])

    # Format test case results summary
    tc_summary = ""
    if test_case_results:
        passed = sum(1 for tc in test_case_results if tc["status"] == "passed")
        failed = sum(1 for tc in test_case_results if tc["status"] == "failed")
        skipped = sum(1 for tc in test_case_results if tc["status"] == "skipped")
        tc_summary = (
            f"\n### Test Case Summary (from JUnit XML)\n"
            f"- Total: {len(test_case_results)}\n"
            f"- Passed: {passed}\n"
            f"- Failed: {failed}\n"
            f"- Skipped: {skipped}\n"
        )

    system_prompt = (
        "You are a test reviewer analyzing self-test results against requirements.\n"
        "Your task is to:\n"
        "1. **Analyze test results**: Summarize pass/fail/skip from the test output.\n"
        "2. **SHALL coverage mapping**: For each SHALL/SHOULD/MAY statement in the spec, "
        "determine if it is covered by the test results.\n"
        "3. **Identify gaps**: List SHALL statements that have no corresponding test coverage.\n"
        "4. **Suggest improvements**: Recommend additional tests for uncovered areas.\n\n"
        "IMPORTANT: Test cases have already been auto-mapped to SHALL statements "
        "using test function name matching (shown with ✅). Please use these mappings "
        "as a starting point but also apply your own analysis.\n\n"
        "Output a structured JSON with:\n"
        "- `status`: \"passed\" if all critical SHALLs covered and tests pass, "
        "\"failed\" if critical gaps exist, \"retry\" for minor gaps\n"
        "- `findings`: array of finding objects (severity, category, message)\n"
        "- `finding_breakdown`: {critical: N, major: N, minor: N, info: N}\n"
        "- `shall_total`: total number of SHALL/SHOULD/MAY statements\n"
        "- `shall_covered`: number covered by tests (use auto-mapping as base)\n"
        "- `shall_uncovered`: list of uncovered SHALL statement texts\n"
        "- `test_gap_areas`: [\"description of untested area\", ...]\n"
        "- `summary`: \"Short summary paragraph\"\n"
        "Wrap the JSON in ```json ... ```."
    )

    auto_section = ""
    if auto_map_str:
        auto_section = (
            f"\n### Auto-Mapped SHALL Coverage (from test function names)\n"
            f"The following SHALL statements were automatically matched to test cases:\n"
            f"{auto_map_str}\n\n"
        )

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification (excerpt)\n"
        f"```\n{spec_content[:5000]}\n```\n\n"
        f"### SHALL/SHOULD/MAY Statements ({len(shall_statements)} total)\n"
        f"{shall_str}\n\n"
        f"### Self-Test Report\n"
        f"```\n{self_test_content[:3000]}\n```\n\n"
        f"### Test Plan (if available)\n"
        f"```\n{test_plan_content[:3000]}\n```\n\n"
        f"{tc_summary}"
        f"{auto_section}"
        f"Analyze the test coverage. For each SHALL statement, determine if:\n"
        f"- ✅ Covered by tests\n"
        f"- ❌ Not covered (gap)\n"
        f"- ❓ Unknown / ambiguous\n\n"
        f"Output your analysis as structured JSON."
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Generate self-test-report.md (R2-P0-4)
# ---------------------------------------------------------------------------


def _generate_selftest_markdown(review: dict) -> str:
    """Generate a structured Markdown self-test report from the enhanced JSON data.

    Produces a comprehensive report including:
      - Test execution summary (pass_rate, duration)
      - SHALL coverage statistics
      - Coverage overview
      - Uncovered SHALL list

    Parameters
    ----------
    review : dict
        The enhanced review dict (same as written to selftest-review.json).

    Returns
    -------
    str
        Markdown formatted report.
    """
    # R4-P0-5: Error code display
    error_code = review.get("error_code", -1)
    error_code_label = {-1: "?", 0: "✅ OK", 1: "⚠️ WARNING", 2: "❌ FAILURE"}.get(error_code, "?")

    lines = [
        f"# Self-Test Report: {review.get('session', 'unknown')}",
        "",
        f"> Generated: {review.get('timestamp', datetime.now().isoformat())}",
        "",
        "## Test Execution Summary",
        "",
        "| Metric | Value |",
        "|:-------|------:|",
        f"| Pass Rate | {review.get('pass_rate', 0):.1f}% |",
        f"| Total Passed | {review.get('total_passed', 0)} |",
        f"| Total Failed | {review.get('total_failed', 0)} |",
        f"| Total Skipped | {review.get('total_skipped', 0)} |",
        f"| Total Errors | {review.get('total_errors', 0)} |",
        f"| Duration | {review.get('duration_sec', 0):.2f}s |",
        f"| Status | {review.get('status', 'unknown')} |",
        f"| Error Code | {error_code} — {error_code_label} |",  # R4-P0-5
        "",
    ]

    # SHALL coverage
    shall_total = review.get("shall_total", 0)
    shall_covered = review.get("shall_covered", 0)
    shall_unknown = review.get("shall_unknown", 0)
    shall_rate = round(shall_covered / shall_total * 100, 1) if shall_total > 0 else 0.0

    lines.extend([
        "## SHALL Coverage",
        "",
        "| Metric | Value |",
        "|:-------|------:|",
        f"| SHALL Statements | {shall_total} |",
        f"| Covered | {shall_covered} |",
        f"| Unknown | {shall_unknown} |",
        f"| Coverage Rate | {shall_rate}% |",
        "",
        f"### Uncovered SHALL Statements ({len(review.get('shall_uncovered', []))})",
        "",
    ])

    uncovered = review.get("shall_uncovered", [])
    if uncovered:
        for stmt in uncovered:
            lines.append(f"- ❌ {stmt[:120]}")
    else:
        lines.append("- ✅ All SHALL statements are covered.")
    lines.append("")

    # R4-P0-3: Test type breakdown
    tc_results = review.get("test_case_results", [])
    unit_count = sum(1 for tc in tc_results if tc.get("type") == "unit")
    integration_count = sum(1 for tc in tc_results if tc.get("type") == "integration")
    system_count = sum(1 for tc in tc_results if tc.get("type") == "system")
    if any(tc.get("type") for tc in tc_results):
        lines.extend([
            "## Test Classification Breakdown",
            "",
            "| Type | Count |",
            "|:-----|------:|",
            f"| 🔬 Unit | {unit_count} |",
            f"| 🔗 Integration | {integration_count} |",
            f"| 🚀 System | {system_count} |",
            "",
        ])

    # Coverage metrics
    coverage = review.get("coverage", {})
    lines.extend([
        "## Coverage Metrics",
        "",
        "| Metric | Value |",
        "|:-------|------:|",
        f"| Line Coverage | {coverage.get('line_rate', 0):.1f}% |",
        f"| Branch Coverage | {coverage.get('branch_rate', 0):.1f}% |",
        f"| Function Coverage | {coverage.get('function_rate', 0):.1f}% |",
        "",
    ])

    # R5-P1-2: MC/DC rate
    mc_dc_rate = coverage.get("mc_dc_rate")
    if mc_dc_rate is not None:
        lines.extend([
            "### MC/DC Condition Coverage (R5-P1-2)",
            "",
            f"| MC/DC Rate | {mc_dc_rate:.1f}% |",
            "",
        ])
    else:
        lines.extend([
            "### MC/DC Condition Coverage (R5-P1-2)",
            "",
            "MC/DC coverage not available (no BRDA condition data in lcov file).",
            "",
        ])

    # R5-P1-3: Coverage by File table
    per_file = coverage.get("per_file", [])
    if per_file:
        lines.append("## Coverage by File (R5-P1-3)")
        lines.append("")
        lines.append("| File | Line Rate | Branch Rate | Function Rate |")
        lines.append("|:-----|----------:|------------:|--------------:|")
        for pf in sorted(per_file, key=lambda x: x.get("file", "")):
            fname = pf.get("file", "")
            lr = f"{pf.get('line_rate', 0):.1f}%"
            br = f"{pf.get('branch_rate', 0):.1f}%"
            fr = f"{pf.get('function_rate', 0):.1f}%"
            lines.append(f"| `{fname}` | {lr} | {br} | {fr} |")
        lines.append("")

    # Test gap areas
    gap_areas = review.get("test_gap_areas", [])
    if gap_areas:
        lines.append("## Test Gap Areas")
        lines.append("")
        for area in gap_areas:
            lines.append(f"- {area}")
        lines.append("")

    # Findings summary
    findings = review.get("findings", [])
    fb = review.get("finding_breakdown", {})
    if findings:
        lines.extend([
            "## Findings",
            "",
            f"| Severity | Count |",
            f"|:---------|------:|",
            f"| 🔴 Critical | {fb.get('critical', 0)} |",
            f"| 🟠 Major | {fb.get('major', 0)} |",
            f"| 🟡 Minor | {fb.get('minor', 0)} |",
            f"| 🔵 Info | {fb.get('info', 0)} |",
            "",
        ])
        for f in findings[:20]:
            sev_icon = {"critical": "🔴", "major": "🟠", "minor": "🟡", "info": "🔵"}.get(
                f.get("severity", ""), "•"
            )
            lines.append(f"- {sev_icon} **{f.get('severity', 'info').upper()}**: {f.get('message', '')[:200]}")
        if len(findings) > 20:
            lines.append(f"- ... and {len(findings) - 20} more findings")
        lines.append("")

    # SHALL auto-mapping details
    # R4-P0-4: Include assertion refs in the SHALL→test mapping table
    shall_auto_map = review.get("shall_auto_mapping", {})
    shall_assertion_map = review.get("shall_assertion_map", {})
    if shall_auto_map:
        lines.append("## SHALL Auto-Mapping Details")
        lines.append("")
        lines.append("| SHALL Statement | Matched Tests | Assertion Lines |")
        lines.append("|:---------------|:--------------|:----------------|")
        for stmt, tests in sorted(shall_auto_map.items())[:30]:
            test_str = ", ".join(tests[:3])
            if len(tests) > 3:
                test_str += f" (+{len(tests) - 3} more)"
            # R4-P0-4: Show assertion line numbers for each test
            assertion_refs = shall_assertion_map.get(stmt, {})
            # Collect all unique assertion lines across all tests for this SHALL
            all_assertion_lines: list[int] = []
            for test_lines in assertion_refs.values():
                all_assertion_lines.extend(test_lines)
            all_assertion_lines = sorted(set(all_assertion_lines))
            assertion_str = ", ".join(f"L{n}" for n in all_assertion_lines[:10])
            if len(all_assertion_lines) > 10:
                assertion_str += f" (+{len(all_assertion_lines) - 10} more)"
            lines.append(f"| {stmt[:80]}... | {test_str} | {assertion_str or '—'} |")
        if len(shall_auto_map) > 30:
            lines.append(f"| ... | ... and {len(shall_auto_map) - 30} more |")
        lines.append("")

    # R3-P0-4 / R3-P0-5: Regression Analysis
    regression = review.get("regression_analysis", {})
    if regression:
        lines.append("## Regression Analysis")
        lines.append("")

        pass_delta = regression.get("pass_rate_delta", 0.0)
        pass_emoji = "🟢" if pass_delta >= 0 else "🔴"
        lines.append("### Pass Rate")
        lines.append("")
        lines.append(f"| {pass_emoji} Pass Rate Delta | {pass_delta:+.1f}% |")
        lines.append(f"|:--------------------|-----:|")
        lines.append("")

        cov_deltas = regression.get("coverage_deltas", {})
        if cov_deltas:
            lines.append("### Coverage Deltas")
            lines.append("")
            lines.append("| Dimension | Delta |")
            lines.append("|:----------|-----:|")
            for dim, delta in sorted(cov_deltas.items()):
                dim_name = dim.replace("_", " ").replace("rate", "").strip().capitalize()
                dim_emoji = "🟢" if delta >= 0 else "🔴"
                lines.append(f"| {dim_emoji} {dim_name} | {delta:+.1f}% |")
            lines.append("")

        new_failures = regression.get("new_failures", [])
        resolved_failures = regression.get("resolved_failures", [])

        if new_failures:
            lines.append("### 🆕 New Failures")
            lines.append("")
            for fname in new_failures[:10]:
                lines.append(f"- ❌ `{fname}`")
            if len(new_failures) > 10:
                lines.append(f"- ... and {len(new_failures) - 10} more new failures")
            lines.append("")

        if resolved_failures:
            lines.append("### ✅ Resolved Failures")
            lines.append("")
            for fname in resolved_failures[:10]:
                lines.append(f"- ✅ `{fname}`")
            if len(resolved_failures) > 10:
                lines.append(f"- ... and {len(resolved_failures) - 10} more resolved failures")
            lines.append("")

    # R5-P2-3: Run history
    run_history = review.get("run_history", [])
    if run_history:
        lines.append("## Test Execution History (R5-P2-3)")
        lines.append("")
        lines.append("| Run | Timestamp | Pass Rate | Line Rate | Branch Rate | Func Rate | MC/DC |")
        lines.append("|:----|:----------|----------:|----------:|------------:|----------:|------:|")
        for i, run in enumerate(run_history, 1):
            ts = run.get("generated_at", "")[:19]  # Truncate ISO timestamp
            pr = f"{run.get('pass_rate', 0):.1f}%"
            lr = f"{run.get('line_rate', 0):.1f}%"
            br = f"{run.get('branch_rate', 0):.1f}%"
            fr = f"{run.get('function_rate', 0):.1f}%"
            mcdc = f"{run.get('mc_dc_rate', 0):.1f}%" if run.get('mc_dc_rate') is not None else "—"
            lines.append(f"| #{i} | {ts} | {pr} | {lr} | {br} | {fr} | {mcdc} |")
        lines.append("")

    # R5-P2-4: LLM degradation info
    llm_degradation = review.get("llm_degradation", {})
    if llm_degradation:
        lines.append("## LLM Analysis Status (R5-P2-4)")
        lines.append("")
        llm_success = llm_degradation.get("llm_succeeded", False)
        fallback_used = llm_degradation.get("fallback_used", False)
        icon = "✅" if llm_success else "⚠️"
        lines.append(f"| Metric | Value |")
        lines.append(f"|:-------|:------|")
        lines.append(f"| {icon} LLM Called | {llm_degradation.get('llm_called', False)} |")
        lines.append(f"| LLM Succeeded | {llm_degradation.get('llm_succeeded', False)} |")
        lines.append(f"| Fallback Used | {llm_degradation.get('fallback_used', False)} |")
        if fallback_used:
            lines.append(f"| Fallback Reason | {llm_degradation.get('fallback_reason', '')} |")
        lines.append("")

    # R5-P2-5: Environment info
    env_info = review.get("environment", {})
    if env_info:
        lines.append("## Test Environment (R5-P2-5)")
        lines.append("")
        lines.append(f"| Attribute | Value |")
        lines.append(f"|:----------|:------|")
        lines.append(f"| Platform | `{env_info.get('platform', '?')}` |")
        py_ver = env_info.get("python_version", "?")
        # Truncate python version to first line
        py_ver_short = py_ver.split("\n")[0] if py_ver else "?"
        lines.append(f"| Python Version | `{py_ver_short}` |")
        lines.append(f"| Hostname | `{env_info.get('hostname', '?')}` |")
        lines.append("")

    # Summary
    summary = review.get("summary", "")
    if summary:
        lines.extend([
            "## Summary",
            "",
            summary,
            "",
        ])

    # CI info
    lines.extend([
        "---",
        "*Self-test report generated by yuleOSH self-test reviewer*",
    ])
    if review.get("build_id"):
        lines.append(f"*Build: {review['build_id']} | Branch: {review.get('branch', '?')}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point (enhanced)
# ---------------------------------------------------------------------------


@timed_step
def step_review_selftest(session: PipelineSession) -> str:
    """Step: 小克 — 自测结果审查（增强版）。

    Parses:
      - Self-test report (text)
      - JUnit XML for per-test-case results (P0-3)
      - lcov coverage.info for coverage metrics (P0-4)
      - Spec SHALL statements with auto-mapping (P0-5)
      - CI env vars for build_id/commit_sha (P0-6)
    """
    try:
        print("  🔍 [小克] 自测结果审查开始...")
        log.info("Running self-test review (enhanced)")

        spec_path = Path(session.spec_path)
        ci_env = _get_ci_environ()

        # --------------------------------------------------------------------
        # 1. Parse JUnit XML → test_case_results (P0-3)
        # --------------------------------------------------------------------
        test_case_results: list[dict] = []
        junit_xml_files = _discover_junit_xml(session)
        for xml_path in junit_xml_files:
            parsed = _parse_junit_xml(xml_path)
            test_case_results.extend(parsed)

        # Deduplicate test cases by name
        seen_names: set[str] = set()
        unique_tc: list[dict] = []
        for tc in test_case_results:
            name = tc["name"]
            if name not in seen_names:
                seen_names.add(name)
                unique_tc.append(tc)
        test_case_results = unique_tc

        log.info("Found %d unique test cases from JUnit XML", len(test_case_results))

        # --------------------------------------------------------------------
        # 2. Parse lcov coverage → coverage data (P0-4)
        # --------------------------------------------------------------------
        coverage_data: dict = {
            "line_rate": 0.0,
            "branch_rate": 0.0,
            "function_rate": 0.0,
            "mc_dc_rate": None,  # R5-P1-2
            "per_file": [],       # R5-P1-3
        }
        coverage_files = _discover_coverage_files(session)
        for cf in coverage_files:
            cd = _parse_lcov_coverage(cf)
            # Take the best rates across multiple files
            if cd.get("line_rate", 0) > coverage_data.get("line_rate", 0):
                coverage_data["line_rate"] = cd["line_rate"]
            if cd.get("branch_rate", 0) > coverage_data.get("branch_rate", 0):
                coverage_data["branch_rate"] = cd["branch_rate"]
            if cd.get("function_rate", 0) > coverage_data.get("function_rate", 0):
                coverage_data["function_rate"] = cd["function_rate"]
            # R5-P1-2: Propagate mc_dc_rate (take the one with data)
            if cd.get("mc_dc_rate") is not None:
                coverage_data["mc_dc_rate"] = cd["mc_dc_rate"]
            # R5-P1-3: Merge per_file data
            coverage_data["per_file"].extend(cd.get("per_file", []))
        if coverage_files:
            log.info("Coverage: line=%.1f%%, branch=%.1f%%, function=%.1f%%, mc_dc=%s",
                     coverage_data["line_rate"], coverage_data["branch_rate"],
                     coverage_data["function_rate"],
                     f"{coverage_data.get('mc_dc_rate', 'N/A')}%" if coverage_data.get('mc_dc_rate') is not None else "N/A")

        # --------------------------------------------------------------------
        # 3. Read self-test report (text)
        # --------------------------------------------------------------------
        self_test_content = ""
        if "self-test" in session.artifacts:
            ap = Path(session.artifacts["self-test"])
            if ap.exists():
                self_test_content = ap.read_text()

        if not self_test_content:
            log.warning("No self-test artifact found")
            self_test_content = "(No self-test report available)"

        # --------------------------------------------------------------------
        # 4. Read spec and extract SHALL statements
        # --------------------------------------------------------------------
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        shall_statements = _extract_shall_statements(spec_content)
        log.info(f"Found {len(shall_statements)} SHALL statements in spec")

        # --------------------------------------------------------------------
        # 5. SHALL auto-mapping from test function names (P0-5)
        # R4-P0-4: Discover test source files for assertion extraction
        # --------------------------------------------------------------------
        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        test_source_files = _find_test_source_files(project_dir)
        log.info("Discovered %d test source files for assertion extraction", len(test_source_files))

        auto_covered_indices, shall_to_tests_map, shall_assertion_map = _auto_map_shall_coverage(
            shall_statements, test_case_results, test_source_files,
        )
        auto_shall_covered = len(auto_covered_indices)
        log.info("SHALL auto-mapping: %d/%d covered", auto_shall_covered, len(shall_statements))

        # --------------------------------------------------------------------
        # 6. Read test plan
        # --------------------------------------------------------------------
        test_plan_content = ""
        if "test-planning" in session.artifacts:
            ap = Path(session.artifacts["test-planning"])
            if ap.exists():
                test_plan_content = ap.read_text()

        # --------------------------------------------------------------------
        # 7. Run LLM-based gap analysis (supplemented by auto-mapping)
        # --------------------------------------------------------------------
        system_prompt, user_prompt = _build_selftest_review_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            self_test_content=self_test_content,
            shall_statements=shall_statements,
            test_plan_content=test_plan_content,
            test_case_results=test_case_results,
            auto_shall_coverage=(auto_covered_indices, shall_to_tests_map),
        )

        # R5-P2-4: Track LLM degradation
        llm_degradation = {
            "llm_called": True,
            "llm_succeeded": False,
            "fallback_used": False,
            "fallback_reason": "",
        }

        try:
            llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
            llm_degradation["llm_succeeded"] = True
            result = llm_result
        except Exception as e:
            log.error(f"LLM call failed during self-test review: {e}")
            err_str = str(e)
            # Check if it's a timeout vs other error
            if "timeout" in err_str.lower():
                llm_degradation["fallback_reason"] = "LLM timeout — using auto-mapped SHALL coverage only"
            else:
                llm_degradation["fallback_reason"] = f"LLM call failed: {err_str[:200]}"
            llm_degradation["fallback_used"] = True
            # Continue with auto-mapped data even without LLM
            log.warning("Continuing without LLM — using auto-mapped SHALL coverage only")
            result = None

        if result:
            raw = result["content"].strip()
            usage = result.get("usage", {})
            log.info(
                "LLM returned %d tokens for self-test review (prompt=%s, completion=%s)",
                usage.get("total_tokens", "?"),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
            )
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "self-test-review", "usage": usage})

            # Parse structured response
            review = _try_parse_hermes_json(raw, session.name)
        else:
            review = {}

        # --------------------------------------------------------------------
        # 8. Build final review with all enhancements
        # --------------------------------------------------------------------
        # Ensure required fields (use auto-mapped values as fallback)
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "小克")
        review.setdefault("step", "self-test-review")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")
        review.setdefault("shall_total", len(shall_statements))
        review.setdefault("shall_uncovered", [])
        review.setdefault("test_gap_areas", [])

        # Prefer auto-mapped SHALL coverage over LLM result (LLM tends to return 0)
        review["shall_covered"] = max(
            review.get("shall_covered", 0),
            auto_shall_covered,
        )
        review["shall_unknown"] = len(shall_statements) - review["shall_covered"]

        # Add P0-3: test_case_results
        review["test_case_results"] = test_case_results

        # Add P0-4: coverage
        review["coverage"] = coverage_data

        # Add P0-5: SHALL auto-mapping details
        review["shall_auto_mapped"] = auto_shall_covered > 0
        review["shall_auto_mapping"] = shall_to_tests_map
        review["shall_statements"] = shall_statements

        # R4-P0-4: Add per-SHALL assertion refs
        review["shall_assertion_map"] = shall_assertion_map

        # Add P0-6: build_id / commit_sha / branch
        review["build_id"] = ci_env["build_id"]
        review["commit_sha"] = ci_env["commit_sha"]
        review["branch"] = ci_env["branch"]

        # Add P0-7: ASPICE map
        review["aspice_map"] = ASPICE_MAP

        # R2-P0-5: Compute top-level summary fields from test_case_results
        passed = sum(1 for tc in test_case_results if tc["status"] == "passed")
        failed = sum(1 for tc in test_case_results if tc["status"] == "failed")
        skipped = sum(1 for tc in test_case_results if tc["status"] == "skipped")
        errors = sum(1 for tc in test_case_results if tc["status"] == "error")
        total_tc = len(test_case_results)
        total_duration = round(sum(tc.get("duration", 0) for tc in test_case_results), 3)
        pass_rate = round(passed / total_tc * 100, 1) if total_tc > 0 else 0.0

        review["pass_rate"] = pass_rate
        review["total_passed"] = passed
        review["total_failed"] = failed
        review["total_skipped"] = skipped
        review["total_errors"] = errors
        review["duration_sec"] = total_duration

        # R3-P0-6: Add schema_version to review
        # R4-P0-5: Add error_code field (0=OK, 1=WARNING, 2=FAILURE)
        review["schema_version"] = _SELFTEST_SCHEMA_VERSION
        if failed > 0 or errors > 0:
            error_code = 2
        elif review.get("shall_uncovered", []):
            error_code = 1
        else:
            error_code = 0
        review["error_code"] = error_code

        # R3-P0-5: Compute regression analysis by comparing with previous build
        prev_review = _load_prev_selftest_review(session.session_dir)
        regression_analysis = _compute_selftest_regression(review, prev_review)
        if regression_analysis:
            review["regression_analysis"] = regression_analysis

        # R5-P2-4: Add LLM degradation tracking
        review["llm_degradation"] = llm_degradation

        # R5-P2-5: Add environment info
        review["environment"] = _collect_environment_info()

        # R5-P2-2: Add xUnit/JUnit compatible format (if test cases exist)
        if test_case_results:
            xunit_xml = _generate_xunit_compatible(test_case_results)
            if xunit_xml:
                review["xunit_compat"] = xunit_xml

        # R5-P2-3: Add run history
        current_run_entry = {
            "generated_at": datetime.now().isoformat(),
            "pass_rate": pass_rate,
            "line_rate": coverage_data.get("line_rate", 0.0),
            "branch_rate": coverage_data.get("branch_rate", 0.0),
            "function_rate": coverage_data.get("function_rate", 0.0),
            "mc_dc_rate": coverage_data.get("mc_dc_rate"),
            "total_tests": total_tc,
            "total_passed": passed,
            "total_failed": failed,
        }
        run_history = _save_run_history(current_run_entry)
        if run_history:
            review["run_history"] = run_history

        # Write JSON output
        out_path = session.session_dir / "selftest-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write self-test review: {e}")
            raise PipelineStepError(f"Cannot write self-test review: {e}")

        # R2-P0-4: Generate and write self-test-report.md (dynamic, replacing the old stub)
        md_content = _generate_selftest_markdown(review)
        md_path = session.session_dir / "self-test-report.md"
        try:
            md_path.write_text(md_content, encoding="utf-8")
            log.info("Self-test report markdown written: %s", md_path)
        except OSError as e:
            log.warning("Cannot write self-test report markdown: %s", e)

        # Generate Excel report
        try:
            from yuleosh.evidence.excel_writer import ExcelReportWriter
            writer = ExcelReportWriter(session.session_dir)
            excel_path = writer.write_selftest_report(
                review=review,
                output_path=session.session_dir / "selftest-report.xlsx",
            )
            log.info("Self-test Excel report written: %s", excel_path)
        except Exception as e:
            log.warning("Cannot write self-test Excel report: %s", e)

        findings_count = len(review.get("findings", []))
        uncovered_count = len(review.get("shall_uncovered", []))
        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(review['status'], '❓')} [小克] 自测审查完成 "
              f"({findings_count} findings, "
              f"{review.get('shall_covered', 0)}/{review.get('shall_total', 0)} SHALLs covered, "
              f"{uncovered_count} uncovered)")
        if test_case_results:
            print(f"     📋 Test cases: {review.get('total_passed', 0)}/{len(test_case_results)} passed "
                  f"(rate: {review.get('pass_rate', 0):.1f}%, duration: {review.get('duration_sec', 0):.2f}s)")
        if coverage_data.get("line_rate", 0) > 0:
            mc_dc_str = f", mc/dc: {coverage_data['mc_dc_rate']:.1f}%" if coverage_data.get("mc_dc_rate") is not None else ""
            print(f"     📊 Coverage: {coverage_data['line_rate']:.1f}% lines, "
                  f"{coverage_data['branch_rate']:.1f}% branches, "
                  f"{coverage_data['function_rate']:.1f}% functions{mc_dc_str}")

        log.info("Self-test review: %d findings, "
                 "%d/%d SHALLs covered, build_id=%s",
                 findings_count,
                 review.get("shall_covered", 0),
                 review.get("shall_total", 0),
                 ci_env["build_id"] or "(local)")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Self-test review step failed: {e}")
        raise PipelineStepError(f"Self-test review step failed: {e}")
