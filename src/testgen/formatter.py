#!/usr/bin/env python3
"""
TestGen Formatter — Convert TestCase objects to executable test code.

Supports three formats:
  - pytest (Python)
  - Go test (Go)
  - Ceedling / Unity (C)

Each formatter produces a complete, importable/compilable test file
annotated with the original spec traceability information.
"""

import textwrap
from typing import Optional

from .generator import TestCase

# ── Shared Helpers ────────────────────────────────────────────────────────────


def _sanitize(s: str) -> str:
    """Sanitize a description string for use as a test function name."""
    sanitized = s.strip().lower()
    sanitized = sanitized.replace(" ", "_").replace("-", "_").replace("/", "_per_")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
    # Remove leading digits/underscores
    sanitized = sanitized.lstrip("_0123456789")
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "test_" + sanitized
    return sanitized or "test_unnamed"


def _escape_c_string(s: str) -> str:
    """Escape a string for embedding in a C string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _escape_python_string(s: str) -> str:
    """Escape a string for embedding in a Python string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ── Priority badge helper ────────────────────────────────────────────────────

_PRIORITY_BADGE = {"P0": "[P0 🔴]", "P1": "[P1 🟡]", "P2": "[P2 🟢]"}


# ==============================================================================
# Python / pytest
# ==============================================================================


def format_pytest(test_cases: list[TestCase], module_name: str = "test_gen") -> str:
    """Format test cases as a pytest-compatible Python test file.

    Args:
        test_cases:   List of TestCase objects.
        module_name:  Python module name for the file (default: test_gen).

    Returns:
        A string containing the complete pytest test file.
    """
    lines: list[str] = []
    lines.append('"""')
    lines.append(f"Auto-generated tests from OpenSpec — {module_name}")
    lines.append(f"Generated {len(test_cases)} test cases.")
    lines.append('"""')
    lines.append("")
    lines.append("import pytest")
    lines.append("")
    lines.append("")
    lines.append("# === Auto-generated test cases ===")
    lines.append("")

    for tc in test_cases:
        fn_name = f"test_{_sanitize(tc.scenario)}_{tc.id.lower().replace('-', '_')}"
        badge = _PRIORITY_BADGE.get(tc.priority, f"[{tc.priority}]")

        lines.append("")
        lines.append(f"# {badge} {tc.id} — {tc.scenario}")
        lines.append(f"# SHALL ref: {tc.shall_ref}")
        lines.append(f"# Tags: {', '.join(tc.tags)}")
        lines.append(f"@pytest.mark.tag({', '.join(repr(t) for t in tc.tags)})")
        lines.append(f"def {fn_name}():")
        lines.append(f'    """')
        lines.append(f"    GIVEN: {tc.given}")
        lines.append(f"    WHEN:  {tc.when}")
        lines.append(f"    THEN:  {tc.then}")
        lines.append(f'    """')
        lines.append(f'    # GIVEN')
        lines.append(f'    # {_escape_python_string(tc.given)}')
        lines.append(f"")
        lines.append(f"    # WHEN")
        lines.append(f"    # {_escape_python_string(tc.when)}")
        lines.append(f"")
        lines.append(f"    # THEN")
        lines.append(f'    # {_escape_python_string(tc.then)}')
        lines.append(f'    assert True  # TODO: implement assertion')
        lines.append("")

    return "\n".join(lines)


# ==============================================================================
# Go / go test
# ==============================================================================


def format_gotest(test_cases: list[TestCase], package: str = "main") -> str:
    """Format test cases as a Go test file (testing package).

    Args:
        test_cases: List of TestCase objects.
        package:    Go package name (default: main).

    Returns:
        A string containing the complete Go test file.
    """
    lines: list[str] = []
    lines.append(f"package {package}")
    lines.append("")
    lines.append("import (")
    lines.append('\t"testing"')
    lines.append(")")
    lines.append("")
    lines.append("// Auto-generated tests from OpenSpec")
    lines.append(f"// Generated {len(test_cases)} test cases.")
    lines.append("")

    for tc in test_cases:
        fn_name = f"Test_{_sanitize(tc.scenario)}_{tc.id.lower().replace('-', '_')}"
        badge = _PRIORITY_BADGE.get(tc.priority, f"[{tc.priority}]")

        lines.append(f"// {badge} {tc.id} — {tc.scenario}")
        lines.append(f"// SHALL ref: {tc.shall_ref}")
        lines.append(f"// Tags: {', '.join(tc.tags)}")
        lines.append(f"// GIVEN: {tc.given}")
        lines.append(f"// WHEN:  {tc.when}")
        lines.append(f"// THEN:  {tc.then}")
        lines.append(f"func {fn_name}(t *testing.T) {{")
        lines.append(f'\tt.Log("TODO: implement test for {tc.id}")')
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


# ==============================================================================
# C / Ceedling + Unity
# ==============================================================================


def format_ceedling(test_cases: list[TestCase]) -> str:
    """Format test cases as a C test file using Ceedling / Unity Test framework.

    Produces a ``test_gen.c`` file with Unity TEST_ASSERT macros.

    Args:
        test_cases: List of TestCase objects.

    Returns:
        A string containing the complete C test file.
    """
    lines: list[str] = []
    lines.append("/*")
    lines.append(" * Auto-generated tests from OpenSpec — Ceedling / Unity")
    lines.append(f" * Generated {len(test_cases)} test cases.")
    lines.append(" */")
    lines.append("")
    lines.append('#include "unity.h"')
    lines.append("")
    lines.append("// Module under test (includes)")
    lines.append('// #include "module_under_test.h"')
    lines.append("")
    lines.append("// ── Setup / Teardown ──────────────────────────────────────")
    lines.append("")
    lines.append("void setUp(void)")
    lines.append("{")
    lines.append("    // TODO: initialize test fixture")
    lines.append("}")
    lines.append("")
    lines.append("void tearDown(void)")
    lines.append("{")
    lines.append("    // TODO: clean up test fixture")
    lines.append("}")
    lines.append("")

    for tc in test_cases:
        fn_name = f"test_{_sanitize(tc.scenario)}_{tc.id.lower().replace('-', '_')}"
        badge = _PRIORITY_BADGE.get(tc.priority, f"[{tc.priority}]")

        lines.append(f"// {badge} {tc.id} — {tc.scenario}")
        lines.append(f"// SHALL ref: {tc.shall_ref}")
        lines.append(f"// Tags: {', '.join(tc.tags)}")
        lines.append(f"// GIVEN: {tc.given}")
        lines.append(f"// WHEN:  {tc.when}")
        lines.append(f"// THEN:  {tc.then}")
        # C function name limited to 63 chars by Unity default
        if len(fn_name) > 60:
            fn_name = fn_name[:60]
        lines.append(f"void {fn_name}(void)")
        lines.append("{")
        lines.append("    // ── GIVEN ──")
        lines.append(f'    // {_escape_c_string(tc.given)}')
        lines.append("")
        lines.append("    // ── WHEN ──")
        lines.append(f'    // {_escape_c_string(tc.when)}')
        lines.append("")
        lines.append("    // ── THEN ──")
        lines.append(f'    // {_escape_c_string(tc.then)}')
        lines.append('    TEST_ASSERT_TRUE_MESSAGE(1, "TODO: implement assertion");')
        lines.append("}")
        lines.append("")

    return "\n".join(lines)
