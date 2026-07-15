#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Review Helpers — reusable utility functions for CI review and JUnit parsing.

Extracted from ``yuleosh.pipeline.step_handlers.review_selftest`` so that
end-to-end tests can import them without depending on pipeline internals.

Public functions:
  - parse_junit_xml(xml_path) -> list[dict]
  - auto_map_shall_coverage(shall_statements, test_case_results, test_source_files) -> tuple
"""

import logging
import re
from pathlib import Path
from xml.etree import ElementTree as ET

log = logging.getLogger("ci.review_helpers")


# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------


def _infer_test_type(tc_name: str, xml_path: Path) -> str:
    """Infer test type (unit/integration/system) from test name and file path.

    R4-P0-3: Test type inference prioritised order:
      1. Function name prefix: test_unit_ / test_integration_ / test_system_
      2. File path segment: tests/unit/ / tests/integration/ / tests/system/
      3. Classname prefix: TestUnit / TestIntegration / TestSystem
      4. Default: "unit"
    """
    # Check function name prefixes
    # Note: \b before _ works; after _ doesn't because _ is a \w char.
    # Use (?:\w|$) to match either a following word char or end-of-string.
    if re.search(r"\btest_unit_(?:\w|$)", tc_name, re.IGNORECASE):
        return "unit"
    if re.search(r"\btest_integration_(?:\w|$)", tc_name, re.IGNORECASE):
        return "integration"
    if re.search(r"\btest_system_(?:\w|$)", tc_name, re.IGNORECASE):
        return "system"

    # Check file path segments
    path_str = str(xml_path.resolve())
    if "/tests/unit/" in path_str or "\\tests\\unit\\" in path_str:
        return "unit"
    if "/tests/integration/" in path_str or "\\tests\\integration\\" in path_str:
        return "integration"
    if "/tests/system/" in path_str or "\\tests\\system\\" in path_str:
        return "system"

    # Check classname prefixes
    if re.search(r"\bTestUnit\b", tc_name):
        return "unit"
    if re.search(r"\bTestIntegration\b", tc_name):
        return "integration"
    if re.search(r"\bTestSystem\b", tc_name):
        return "system"

    # Check classname:: prefix (e.g. test_api_smoke.py::test_foo_bar)
    class_part = tc_name.split("::")[0] if "::" in tc_name else ""
    if "integration" in class_part.lower():
        return "integration"
    if "system" in class_part.lower() or "smoke" in class_part.lower():
        return "system"
    if "unit" in class_part.lower():
        return "unit"

    return "unit"


def _extract_testcase(tc: ET.Element, suite: ET.Element | None = None) -> dict:
    """Extract a single test case result from a <testcase> element.

    R4-P0-6: Produces structured ``failure`` field with type/message/stacktrace.
    """
    class_name = tc.get("classname", "")
    name = tc.get("name", "")
    # Full name: classname + name (e.g., test_file.py::test_function)
    full_name = f"{class_name}::{name}" if class_name else name
    time_str = tc.get("time", "0")
    try:
        duration = float(time_str)
    except (ValueError, TypeError):
        duration = 0.0

    # Determine status
    failure = tc.find("failure")
    error = tc.find("error")
    skipped = tc.find("skipped")

    # R4-P0-6: Structured failure diagnostics
    failure_info: dict | None = None

    if skipped is not None:
        status = "skipped"
        message = skipped.get("message", "") or skipped.text or ""
    elif failure is not None:
        status = "failed"
        message = failure.get("message", "") or failure.text or ""
        # R4-P0-6: Parse failure type, message, and stacktrace
        failure_info = {
            "type": failure.get("type", "AssertionError"),
            "message": message.strip()[:500],
            "stacktrace": (failure.text or "").strip()[:2000],
        }
    elif error is not None:
        status = "error"
        message = error.get("message", "") or error.text or ""
        # R4-P0-6: Parse error type, message, and stacktrace
        failure_info = {
            "type": error.get("type", "Error"),
            "message": message.strip()[:500],
            "stacktrace": (error.text or "").strip()[:2000],
        }
    else:
        status = "passed"
        message = ""

    result = {
        "name": full_name,
        "classname": class_name,
        "status": status,
        "duration": round(duration, 3),
        "message": message.strip()[:500],  # Truncate long messages
    }
    # R4-P0-6: Include structured failure details
    if failure_info is not None:
        result["failure"] = failure_info
    return result


def parse_junit_xml(xml_path: Path) -> list[dict]:
    """Parse pytest JUnit XML file and return test_case_results list.

    R4-P0-3: Each test case result includes a ``type`` field (unit/integration/system).

    Returns list[dict] with keys:
      - name: str (test case name)
      - status: str ("passed" | "failed" | "skipped" | "error")
      - duration: float (seconds)
      - message: str (error/failure message, empty if passed)
      - type: str ("unit" | "integration" | "system", R4-P0-3)
    """
    results: list[dict] = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except (ET.ParseError, OSError, Exception) as e:
        log.warning("Failed to parse JUnit XML %s: %s", xml_path, e)
        return results

    # Handle both <testsuite> and <testsuites> wrappers
    if root.tag == "testsuites":
        # Flatten all test cases from all suites
        for suite in root.findall("testsuite"):
            for tc in suite.findall("testcase"):
                results.append(_extract_testcase(tc, suite))
    elif root.tag == "testsuite":
        for tc in root.findall("testcase"):
            results.append(_extract_testcase(tc, root))
    else:
        # Look for testsuite anywhere
        for suite in root.findall(".//testsuite"):
            for tc in suite.findall("testcase"):
                results.append(_extract_testcase(tc, suite))

    # R4-P0-3: Annotate each test case with inferred type
    for tc in results:
        tc["type"] = _infer_test_type(tc.get("name", ""), xml_path)

    log.info("Parsed %d test cases from %s", len(results), xml_path.name)
    return results


# ---------------------------------------------------------------------------
# SHALL auto-mapping via test function name matching
# ---------------------------------------------------------------------------

# Regex to extract SHALL IDs from test function names.
# Supported formats:
#   test_shall_10_1
#   test_SHALL_10_1
#   test_requirement_10_1
#   test_SWE_4_BP1_shall_10_1
#   test_SWE4865_shall_10_1
_SHALL_ID_PATTERN = re.compile(
    r"(?:SHALL|shall|requirement|req)[_.-]?(?P<id>\d+(?:[_.]\d+)?)",
    re.IGNORECASE,
)


def find_test_source_files(project_dir: Path) -> list[Path]:
    """Discover test source files (*.py, *.c) in the project tree."""
    src_files: list[Path] = []
    # Python test files
    for pattern in ["tests/*.py", "tests/**/*.py", "src/**/test_*.py", "src/**/*_test.py"]:
        src_files.extend(sorted(project_dir.glob(pattern)))
    # C unit-test files
    for pattern in ["tests/**/*.c", "src/**/test_*.c"]:
        src_files.extend(sorted(project_dir.glob(pattern)))
    # Deduplicate
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in src_files:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def _extract_assertion_lines(source_files: list[Path], test_name: str) -> list[int]:
    """Search test source files for a function definition matching *test_name*
    and return line numbers of assertion statements inside its body.
    """
    if not test_name:
        return []

    # Derive the short function name from "classname::test_func" format
    func_name = test_name.split("::")[-1] if "::" in test_name else test_name

    # Assertion patterns to search for inside function bodies
    assert_patterns = [
        r"\bassert\b",             # pytest assert (generic, e.g. assert x == 1)
        r"assert\s*[(]",           # pytest assert with parens
        r"self\.assert",           # unittest.TestCase.assert*
        r"TEST_ASSERT",            # Unity TEST_ASSERT*
        r"TEST_CHECK",             # Unity TEST_CHECK
        r"assertTrue\s*[(]",
        r"assertFalse\s*[(]",
        r"assertEqual\s*[(]",
        r"assertNotEqual\s*[(]",
        r"assertIn\s*[(]",
        r"assertNotIn\s*[(]",
        r"assertIs\s*[(]",
        r"assertIsNot\s*[(]",
        r"assertIsNone\s*[(]",
        r"assertIsNotNone\s*[(]",
        r"assertRaises\s*[(]",
        r"assertGreater\s*[(]",
        r"assertLess\s*[(]",
        r"assertAlmostEqual\s*[(]",
        r"assert_(?:True|False|Equal|NotEqual|In|NotIn|"
        r"Is|IsNot|IsNone|IsNotNone|Raises|Greater|Less|"
        r"AlmostEqual|NotAlmostEqual|Regex|NotRegex)",
    ]

    assertion_lines: list[int] = []

    for src_file in source_files:
        try:
            content = src_file.read_text("utf-8", errors="replace")
        except (OSError, Exception):
            continue

        lines = content.split("\n")

        # Find the function definition matching our test name
        inside_function = False

        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()

            # Detect function definition: def test_xxx or void test_xxx
            is_def = (
                (stripped.startswith("def ") or stripped.startswith("async def "))
                and func_name in stripped
            ) or (
                "void " in stripped and func_name in stripped and "(" in stripped
            )

            if is_def:
                inside_function = True
                continue

            if inside_function:
                # Track Python indentation-based function body
                # Use the original line (not stripped) to test indentation
                if stripped and not line.startswith((" ", "\t")):
                    # Back to module-level scope
                    inside_function = False
                    continue

                # Check for assertion patterns
                for pat in assert_patterns:
                    if re.search(pat, stripped):
                        assertion_lines.append(line_no)
                        break

        # Early exit if found in this file
        if assertion_lines:
            break

    return sorted(set(assertion_lines))


def auto_map_shall_coverage(
    shall_statements: list[dict],
    test_case_results: list[dict],
    test_source_files: list[Path] | None = None,
) -> tuple[set[int], dict[str, list[str]], dict[str, dict[str, list[int]]]]:
    """Automatically map SHALL statements to test cases by test function name.

    Matches SHALL IDs (e.g., "10.1" from spec) against test function names
    (e.g., "test_shall_10_1" or "test_SHALL_10_1").

    R4-P0-4: Also parses test source files to extract assertion line numbers
    for each matched SHALL, returning assertion_refs.

    Parameters
    ----------
    shall_statements : list[dict]
        SHALL statements with {statement, section, line, ...}.
    test_case_results : list[dict]
        Test case results with {name, status, duration, message}.
    test_source_files : list[Path] | None
        Test source files to search for assertion line numbers (R4-P0-4).

    Returns
    -------
    tuple[set[int], dict[str, list[str]], dict[str, dict[str, list[int]]]]
        (covered_indices, shall_to_tests_map, shall_assertion_map)
        - covered_indices: set of indices (into shall_statements) that are covered
        - shall_to_tests_map: {shall_statement_text: [test_name, ...]}
        - shall_assertion_map: {shall_statement_text: {test_name: [line_num, ...]}} (R4-P0-4)
    """
    covered_indices: set[int] = set()
    shall_to_tests_map: dict[str, list[str]] = {}
    shall_assertion_map: dict[str, dict[str, list[int]]] = {}  # R4-P0-4

    # Build {shall_id_clean: [(index, statement_text)]} from shall_statements
    shall_by_id: dict[str, list[tuple[int, str]]] = {}
    for i, shall in enumerate(shall_statements):
        stmt = shall.get("statement", "")
        # Try to extract SHALL ID from statement (e.g., "SHALL-10.1" or "10.1")
        id_match = re.search(r"(?:SHALL|shall|Requirement|requirement|REQ|req)[-_.\s]*(\d+(?:[_.]\d+)?)", stmt)
        if id_match:
            sid = id_match.group(1).replace("_", ".")
        else:
            # Use section.line as fallback ID
            section = shall.get("section", "")
            sid = re.sub(r"[^\d.]", "", section)
        if sid:
            shall_by_id.setdefault(sid, []).append((i, stmt))

    # Extract SHALL IDs from test function names
    for tc in test_case_results:
        test_name = tc.get("name", "")
        for m in _SHALL_ID_PATTERN.finditer(test_name):
            sid = m.group("id").replace("_", ".")
            if sid in shall_by_id:
                for idx, stmt in shall_by_id[sid]:
                    covered_indices.add(idx)
                    shall_to_tests_map.setdefault(stmt, []).append(test_name)
                    # R4-P0-4: Extract assertion line numbers for this test
                    if test_source_files and test_name not in shall_assertion_map.setdefault(stmt, {}):
                        assert_lines = _extract_assertion_lines(test_source_files, test_name)
                        shall_assertion_map[stmt][test_name] = assert_lines

    log.info("SHALL auto-mapping: %d of %d SHALLs covered by test names",
             len(covered_indices), len(shall_statements))
    return covered_indices, shall_to_tests_map, shall_assertion_map
