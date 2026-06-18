#!/usr/bin/env python3
"""
Tests for MISRA traceability: misra_report.py traceability functions.

Tests:
  1. generate_traceability_matrix returns correct count
  2. Each traceability entry has required fields
  3. spec_ref loaded from rule_defs
  4. check_method loaded from rule_defs
  5. auto_checkable loaded from rule_defs
  6. fix_status defaults to "unresolved"
  7. generate_fix_tasks creates .md files
  8. Fix task file contains rule_id and checklist
  9. Empty violations produce empty traceability
  10. Unknown rule_id yields empty spec_ref
  11. Multiple violations of same rule → one fix task
  12. Traceability matrix serializes to JSON
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from yuleosh.ci.misra_report import (
    generate_traceability_matrix,
    generate_fix_tasks,
    load_rule_definitions,
    parse_cppcheck_output,
)

# Sample rule definitions for testing
SAMPLE_RULE_DEFS = {
    "misra-c2023-10.1": {
        "title": "Operands shall not be of inappropriate type",
        "severity": "required",
        "category": "基本类型 (Essential Types)",
        "description": "操作数不得具有不适当的本质类型",
        "spec_ref": "SWE-MISRA-S1; SWE-MISRA-CFG2",
        "check_method": "cppcheck",
        "auto_checkable": True,
    },
    "misra-c2023-17.7": {
        "title": "返回值必须被使用",
        "severity": "required",
        "category": "函数行为",
        "description": "调用具有返回值的函数，其返回值应被检查或使用",
        "spec_ref": "SWE-MISRA-S1; SWE-MISRA-DEV2",
        "check_method": "cppcheck",
        "auto_checkable": True,
    },
    "misra-c2023-8.2": {
        "title": "Function types shall be in prototype form",
        "severity": "required",
        "category": "声明 (Declarations)",
        "description": "函数类型应使用原型形式声明",
        "spec_ref": "SWE-MISRA-S1; SWE-MISRA-CFG2",
        "check_method": "cppcheck",
        "auto_checkable": True,
    },
}

# Sample violations
SAMPLE_VIOLATIONS = [
    {
        "file": "src/main.c",
        "line": 42,
        "col": 5,
        "severity": "style",
        "message": "misra-c2023-10.1: Operands shall not be of inappropriate type",
        "rule_id": "misra-c2023-10.1",
    },
    {
        "file": "src/main.c",
        "line": 88,
        "col": 12,
        "severity": "style",
        "message": "misra-c2023-17.7: Return value shall be checked",
        "rule_id": "misra-c2023-17.7",
    },
    {
        "file": "src/uart.c",
        "line": 15,
        "col": 3,
        "severity": "style",
        "message": "misra-c2023-8.2: Function types shall be in prototype form",
        "rule_id": "misra-c2023-8.2",
    },
]


class TestGenerateTraceabilityMatrix:
    """Tests for generate_traceability_matrix()."""

    def test_returns_correct_count(self):
        """Test 1: Returns one entry per violation."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        assert len(result) == 3

    def test_all_required_fields_present(self):
        """Test 2: Each entry has all required fields."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        required_fields = {
            "rule_id", "file", "line", "col", "severity",
            "message", "spec_ref", "check_method",
            "auto_checkable", "fix_status",
        }
        for entry in result:
            assert required_fields.issubset(entry.keys()), f"Missing fields in {entry}"

    def test_spec_ref_from_rule_defs(self):
        """Test 3: spec_ref is loaded from rule_defs."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        entry = next(e for e in result if e["rule_id"] == "misra-c2023-10.1")
        assert entry["spec_ref"] == "SWE-MISRA-S1; SWE-MISRA-CFG2"

    def test_check_method_from_rule_defs(self):
        """Test 4: check_method is loaded from rule_defs."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        entry = next(e for e in result if e["rule_id"] == "misra-c2023-10.1")
        assert entry["check_method"] == "cppcheck"

    def test_auto_checkable_from_rule_defs(self):
        """Test 5: auto_checkable is loaded from rule_defs."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        entry = next(e for e in result if e["rule_id"] == "misra-c2023-10.1")
        assert entry["auto_checkable"] is True

    def test_fix_status_defaults_to_unresolved(self):
        """Test 6: fix_status defaults to 'unresolved'."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        assert all(e["fix_status"] == "unresolved" for e in result)

    def test_empty_violations(self):
        """Test 9: Empty violations produce empty traceability."""
        result = generate_traceability_matrix([], SAMPLE_RULE_DEFS)
        assert result == []

    def test_unknown_rule_id(self):
        """Test 10: Unknown rule_id yields empty spec_ref and defaults."""
        violations = [{
            "file": "src/unknown.c",
            "line": 1,
            "col": 1,
            "severity": "style",
            "message": "Unknown rule violation",
            "rule_id": "misra-c2023-999.9",
        }]
        result = generate_traceability_matrix(violations, SAMPLE_RULE_DEFS)
        assert len(result) == 1
        entry = result[0]
        assert entry["spec_ref"] == ""
        assert entry["check_method"] == ""
        assert entry["auto_checkable"] is True  # default

    def test_json_serializable(self):
        """Test 12: Traceability matrix serializes to JSON."""
        result = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        json_str = json.dumps(result, ensure_ascii=False, default=str)
        parsed = json.loads(json_str)
        assert len(parsed) == 3
        assert parsed[0]["rule_id"] == "misra-c2023-10.1"


class TestGenerateFixTasks:
    """Tests for generate_fix_tasks()."""

    def test_fix_tasks_created(self, tmp_path):
        """Test 7: generate_fix_tasks creates .md files."""
        project_dir = str(tmp_path)
        fix_files = generate_fix_tasks(project_dir, SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        assert len(fix_files) == 3  # 3 unique rules
        for f in fix_files:
            assert f.endswith(".md")
            assert os.path.isfile(f)

    def test_fix_task_content(self, tmp_path):
        """Test 8: Fix task file contains rule_id and checklist."""
        project_dir = str(tmp_path)
        fix_files = generate_fix_tasks(project_dir, SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        md_path = next(f for f in fix_files if "misra-c2023-10.1" in f)
        content = Path(md_path).read_text()
        assert "misra-c2023-10.1" in content
        assert "Fix Checklist" in content
        assert "[ ] Understand the violation context" in content

    def test_multiple_violations_one_rule(self, tmp_path):
        """Test 11: Multiple violations of same rule → one fix task."""
        violations = [
            {
                "file": "src/main.c",
                "line": 42,
                "col": 5,
                "severity": "style",
                "message": "misra-c2023-10.1: Violation #1",
                "rule_id": "misra-c2023-10.1",
            },
            {
                "file": "src/main.c",
                "line": 100,
                "col": 8,
                "severity": "style",
                "message": "misra-c2023-10.1: Violation #2",
                "rule_id": "misra-c2023-10.1",
            },
        ]
        project_dir = str(tmp_path)
        fix_files = generate_fix_tasks(project_dir, violations, SAMPLE_RULE_DEFS)
        # Only 1 file because both violations share the same rule
        assert len(fix_files) == 1
        content = Path(fix_files[0]).read_text()
        assert "Violation #1" in content
        assert "Violation #2" in content

    def test_no_violations_no_files(self, tmp_path):
        """No violations → no fix tasks."""
        project_dir = str(tmp_path)
        fix_files = generate_fix_tasks(project_dir, [], SAMPLE_RULE_DEFS)
        assert fix_files == []


# End-to-end: parse real cppcheck output → traceability
class TestEndToEnd:
    """End-to-end: parse → traceability → fix tasks."""

    SAMPLE_CPPCHECK_OUTPUT = """\
src/main.c:42:5: style: misra-c2023-10.1: [misra-c2012-10.1] Operands shall not be of inappropriate type
src/main.c:88:12: style: misra-c2023-17.7: [misra-c2012-17.7] Return value shall be checked
src/uart.c:15:3: style: (information) MISRA rule 8.2
"""

    def test_full_pipeline(self, tmp_path):
        """Full pipeline: parse → traceability → fix tasks."""
        violations = parse_cppcheck_output(self.SAMPLE_CPPCHECK_OUTPUT)
        assert len(violations) == 3

        trace = generate_traceability_matrix(violations, SAMPLE_RULE_DEFS)
        assert len(trace) == 3

        project_dir = str(tmp_path)
        fix_files = generate_fix_tasks(project_dir, violations, SAMPLE_RULE_DEFS)
        # 3 unique rule IDs
        assert len(fix_files) == 3

        # Check the traceability JSON content
        for entry in trace:
            assert "rule_id" in entry
            assert "file" in entry
            assert entry["fix_status"] == "unresolved"
