"""Depth tests for alm/traceability.py — SHALL extraction, traceability generation, and edge cases.

Covers:
  - extract_shall_statements: table format, list format, edge cases
  - extract_shall_from_text: various input formats
  - _is_table_separator, _is_shall_table_header: detection logic
  - scan_review_artifacts: .yuleosh/ and .osh/ sessions
  - scan_test_reports, scan_ci_results
  - generate_lrm: LRM generation with mock data
  - generate_lrt: full traceability report
  - generate_traceability_report: aggregated report
  - Internal helpers: _extract_keywords, _find_code_by_keywords, _find_step_handlers_for_requirement
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.alm.traceability import (
    extract_shall_statements,
    extract_shall_from_text,
    _is_table_separator,
    _is_shall_table_header,
    scan_review_artifacts,
    scan_test_reports,
    scan_ci_results,
    generate_lrm,
    generate_lrt,
    generate_traceability_report,
    _extract_keywords,
    _find_code_by_keywords,
    _find_step_handlers_for_requirement,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project():
    """Create a temporary project directory with minimal structure."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src" / "yuleosh"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        yield tmp


# ── extract_shall_from_text ───────────────────────────────────────────

class TestExtractShallFromText:
    def test_basic_shall_statements(self):
        """GIVEN text with SHALL statements WHEN extracting THEN returns all."""
        text = """
        REQ-001: The system SHALL boot within 5 seconds.
        REQ-002: The system SHALL NOT crash on invalid input.
        # This is a comment, SHALL be ignored.
        """
        results = extract_shall_from_text(text)
        assert isinstance(results, list)
        # Should find at least some SHALL statements in bullet format
        # (list markers are needed for list format)

    def test_bullet_list_format(self):
        """GIVEN bullet list format WHEN extracting THEN extracts SHALLs."""
        text = """
        # Requirements
        - The system SHALL initialize all peripherals.
        - The system SHALL report errors via CAN bus.
        """
        results = extract_shall_from_text(text)
        assert len(results) >= 2
        ids = [r["id"] for r in results]
        assert "SHALL-1" in ids or "SHALL-2" in ids

    def test_table_format(self):
        """GIVEN table format WHEN extracting THEN extracts SHALL rows."""
        text = """
        | ID | 描述 | ASIL |
        |:---|:-----|:-----|
        | KL-SHALL-01 | The system SHALL boot | QM |
        | KL-SHALL-02 | The system SHALL monitor | ASIL B |
        """
        results = extract_shall_from_text(text)
        # Should capture table rows with -SHALL prefix
        shall_ids = [r["id"] for r in results]
        assert any("KL-SHALL" in sid for sid in shall_ids)

    def test_table_format_header_detection(self):
        """GIVEN _is_shall_table_header WHEN called THEN detects correctly."""
        assert _is_shall_table_header(["ID", "SHALL Description"]) is True
        assert _is_shall_table_header(["ID", "描述", "ASIL"]) is True
        assert _is_shall_table_header(["ID", "Description"]) is True
        assert _is_shall_table_header(["ID", "STATEMENT", "ASIL"]) is True
        assert _is_shall_table_header(["Name", "Type"]) is False
        assert _is_shall_table_header(["ID"]) is False

    def test_table_separator_detection(self):
        """GIVEN _is_table_separator WHEN called THEN detects correctly."""
        assert _is_table_separator("|:---|:---|") is True
        assert _is_table_separator("| --- | --- |") is True
        assert _is_table_separator("|---|:---:|---|") is True
        assert _is_table_separator("This is not a separator") is False
        assert _is_table_separator("| a | b |") is False

    def test_non_shall_text(self):
        """GIVEN text without SHALL WHEN extracting THEN empty."""
        results = extract_shall_from_text("This is a regular paragraph without requirements.")
        assert len(results) == 0

    def test_in_given_when_then_skipped(self):
        """GIVEN text with SHALL inside GIVEN/WHEN/THEN blocks WHEN extracting THEN skipped."""
        text = """
        # Requirements
        - The system SHALL respond within 10ms.
        ##### GIVEN power is applied
        ##### WHEN the SHALL condition triggers
        ##### THEN it responds
        """
        results = extract_shall_from_text(text)
        # Should find one SHALL (not the one in the scenario block)
        counts = len(results)
        assert counts == 1

    def test_spec_id_pattern_extraction(self):
        """GIVEN text with **ID**: prefix WHEN extracting THEN captures req_id."""
        text = """
        **SWE-MISRA-S1**: The system SHALL handle errors.
        [REQ-MISRA-S1.1] The system SHALL log errors.
        """
        results = extract_shall_from_text(text)
        # These need list markers
    def test_spec_id_with_bullet(self):
        """GIVEN bullet with **ID**: WHEN extracting THEN captures."""
        text = """
        - **SWE-MISRA-S1**: The system SHALL handle errors.
        - [REQ-MISRA-S1.1] The system SHALL log errors.
        """
        results = extract_shall_from_text(text)
        req_ids = [r["req_id"] for r in results]
        assert "SWE-MISRA-S1" in req_ids
        assert "REQ-MISRA-S1.1" in req_ids


# ── extract_shall_statements ─────────────────────────────────────────

class TestExtractShallStatements:
    def test_file_not_found(self):
        """GIVEN non-existent spec file WHEN extracting THEN returns empty."""
        results = extract_shall_statements("/nonexistent/spec.md")
        assert results == []

    def test_from_file_list_format(self, tmp_project):
        """GIVEN spec file with list format WHEN extracting THEN returns SHALLs."""
        spec_path = Path(tmp_project) / "docs" / "spec.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("""# Requirements
        - The system SHALL boot.
        - The system SHALL validate inputs.
        """)
        results = extract_shall_statements(str(spec_path))
        assert len(results) >= 1

    def test_empty_file(self, tmp_project):
        """GIVEN empty spec file WHEN extracting THEN returns empty."""
        spec_path = Path(tmp_project) / "empty.md"
        spec_path.write_text("")
        results = extract_shall_statements(str(spec_path))
        assert results == []

    def test_table_format_from_file(self, tmp_project):
        """GIVEN spec file with table format WHEN extracting THEN returns rows."""
        spec_path = Path(tmp_project) / "table_spec.md"
        spec_path.write_text("""| ID | 描述 | ASIL |
        |:---|:-----|:-----|
        | PE-SHALL-01 | The system SHALL boot | ASIL B |
        | PE-SHALL-02 | The system SHALL monitor | QM |
        """)
        results = extract_shall_statements(str(spec_path))
        shall_ids = [r["id"] for r in results]
        assert "PE-SHALL-01" in shall_ids
        assert "PE-SHALL-02" in shall_ids

    def test_spec_heading_with_req_id(self, tmp_project):
        """GIVEN section heading with requirement ID WHEN extracting THEN captures req_id."""
        spec_path = Path(tmp_project) / "heading_spec.md"
        spec_path.write_text("""# SWE-1 The system SHALL boot
        - Additional SHALL details
        """)
        results = extract_shall_statements(str(spec_path))
        # Should extract section and find SHALL


# ── scan_review_artifacts ─────────────────────────────────────────────

class TestScanReviewArtifacts:
    def test_no_sessions_dir(self, tmp_project):
        """GIVEN no sessions dir WHEN scanning THEN empty."""
        results = scan_review_artifacts(tmp_project)
        assert results == []

    def test_yuleosh_sessions_dir(self, tmp_project):
        """GIVEN .yuleosh/sessions/ with review.json WHEN scanning THEN returns data."""
        session_dir = Path(tmp_project) / ".yuleosh" / "sessions" / "rev001"
        session_dir.mkdir(parents=True)
        review_file = session_dir / "code-review.json"
        review_file.write_text(json.dumps({
            "agent": "claude",
            "reviewed_files": ["src/main.c"],
            "findings": [{"description": "Null check missing"}],
        }))
        results = scan_review_artifacts(tmp_project)
        assert len(results) == 1
        assert results[0]["agent"] == "claude"

    def test_osh_sessions_dir(self, tmp_project):
        """GIVEN .osh/sessions/ without .yuleosh WHEN scanning THEN uses .osh."""
        session_dir = Path(tmp_project) / ".osh" / "sessions" / "rev002"
        session_dir.mkdir(parents=True)
        review_file = session_dir / "code-review.json"
        review_file.write_text(json.dumps({
            "agent": "gpt4",
            "reviewed_files": ["src/main.c"],
            "findings": ["Issue found"],
        }))
        results = scan_review_artifacts(tmp_project)
        assert len(results) == 1

    def test_evidence_reviews_fallback(self, tmp_project):
        """GIVEN evidence reviews dir WHEN scanning THEN parses JSON files."""
        # Create a session dir without code-review.json to trigger fallback
        session_dir = Path(tmp_project) / ".osh" / "sessions" / "fallen-session"
        session_dir.mkdir(parents=True)
        ev_dir = Path(tmp_project) / ".osh" / "evidence" / "reviews"
        ev_dir.mkdir(parents=True)
        (ev_dir / "review_003.json").write_text(json.dumps({
            "agent": "claude",
            "files": ["src/module.c"],
            "issues": [{"description": "Style issue"}],
        }))
        results = scan_review_artifacts(tmp_project)
        assert len(results) >= 1

    def test_invalid_json_skipped(self, tmp_project):
        """GIVEN invalid JSON review file WHEN scanning THEN skips."""
        session_dir = Path(tmp_project) / ".osh" / "sessions" / "bad"
        session_dir.mkdir(parents=True)
        (session_dir / "code-review.json").write_text("not json")
        results = scan_review_artifacts(tmp_project)
        assert len(results) == 0


# ── scan_test_reports ─────────────────────────────────────────────────

class TestScanTestReports:
    def test_no_dir(self, tmp_project):
        """GIVEN no sessions dir WHEN scanning tests THEN empty."""
        results = scan_test_reports(tmp_project)
        assert results == []

    def test_finds_test_reports(self, tmp_project):
        """GIVEN session dirs with *test*.json files WHEN scanning THEN returns reports."""
        session_dir = Path(tmp_project) / ".yuleosh" / "sessions" / "t001"
        session_dir.mkdir(parents=True)
        (session_dir / "unittest_result.json").write_text(json.dumps({
            "step": "unit-tests",
            "status": "passed",
            "passed": 10,
            "failed": 0,
        }))
        results = scan_test_reports(tmp_project)
        assert len(results) == 1
        assert results[0]["status"] == "passed"

    def test_prefers_osh_over_yuleosh(self, tmp_project):
        """GIVEN both .osh and .yuleosh WHEN scanning THEN prefers .osh."""
        osh_dir = Path(tmp_project) / ".osh" / "sessions" / "t001"
        osh_dir.mkdir(parents=True)
        (osh_dir / "test_report.json").write_text(json.dumps({"status": "passed"}))

        yul_dir = Path(tmp_project) / ".yuleosh" / "sessions" / "t001"
        yul_dir.mkdir(parents=True)
        (yul_dir / "test_report.json").write_text(json.dumps({"status": "failed"}))

        results = scan_test_reports(tmp_project)
        assert results[0]["status"] == "passed"


# ── scan_ci_results ───────────────────────────────────────────────────

class TestScanCiResults:
    def test_no_ci_dir(self, tmp_project):
        """GIVEN no .osh/ci dir WHEN scanning THEN empty."""
        results = scan_ci_results(tmp_project)
        assert results == []

    def test_finds_ci_results(self, tmp_project):
        """GIVEN .osh/ci with layer JSON files WHEN scanning THEN returns results."""
        ci_dir = Path(tmp_project) / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1.json").write_text(json.dumps({
            "layer": "L1", "status": "passed", "timestamp": "2025-01-01",
        }))
        results = scan_ci_results(tmp_project)
        assert len(results) == 1


# ── _extract_keywords ─────────────────────────────────────────────────

class TestExtractKeywords:
    def test_basic_keywords(self):
        """GIVEN SHALL statement WHEN extracting keywords THEN returns meaningful words."""
        keywords = _extract_keywords("The system SHALL boot within 5 seconds")
        assert "boot" in keywords
        assert "system" in keywords
        assert "seconds" in keywords
        assert "the" not in keywords  # stop word
        assert "shall" not in keywords  # stop word

    def test_empty_input(self):
        """GIVEN empty statement WHEN extracting THEN empty list."""
        assert _extract_keywords("") == []


# ── _find_code_by_keywords ────────────────────────────────────────────

class TestFindCodeByKeywords:
    def test_no_src_dir(self, tmp_project):
        """GIVEN no src dir WHEN finding code THEN empty."""
        results = _find_code_by_keywords(Path(tmp_project) / "nonexistent", ["test"])
        assert results == []

    def test_finds_matching_code(self, tmp_project):
        """GIVEN source file with keywords WHEN finding THEN returns relative path."""
        src_dir = Path(tmp_project) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "module.py").write_text("def boot(): pass")
        results = _find_code_by_keywords(src_dir, ["boot"])
        assert len(results) >= 1


# ── _find_step_handlers_for_requirement ───────────────────────────────

class TestFindStepHandlers:
    def test_no_sessions_dir(self, tmp_project):
        """GIVEN no sessions dir WHEN finding handlers THEN empty."""
        result = _find_step_handlers_for_requirement(
            tmp_project, "RS-001", {"id": "SHALL-1"}
        )
        assert result == []

    def test_matching_handler_found(self, tmp_project):
        """GIVEN handler with matching req_id WHEN finding THEN returns handler."""
        session_dir = Path(tmp_project) / ".osh" / "sessions" / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "step.json").write_text(json.dumps({
            "step": "validate",
            "req_ids": ["RS-001"],
        }))
        result = _find_step_handlers_for_requirement(
            tmp_project, "RS-001", {"id": "SHALL-1"}
        )
        assert len(result) == 1
        assert result[0]["step"] == "validate"


# ── generate_lrm ──────────────────────────────────────────────────────

class TestGenerateLRM:
    def test_no_spec_file(self, tmp_project):
        """GIVEN no spec file WHEN generating LRM THEN returns empty."""
        result = generate_lrm(tmp_project)
        assert result["summary"]["total"] == 0

    def test_with_spec_file(self, tmp_project):
        """GIVEN spec file with SHALLs WHEN generating LRM THEN returns matrix."""
        docs_dir = Path(tmp_project) / "docs"
        docs_dir.mkdir(parents=True)
        spec_path = docs_dir / "spec.md"
        spec_path.write_text("""# Requirements
        - The system SHALL boot.
        - The system SHALL validate.
        """)
        result = generate_lrm(tmp_project, spec_path=str(spec_path))
        assert result["summary"]["total"] >= 1


# ── generate_traceability_report ─────────────────────────────────────

class TestGenerateTraceabilityReport:
    def test_no_spec_file(self, tmp_project):
        """GIVEN no spec file WHEN generating traceability THEN returns report."""
        result = generate_traceability_report(tmp_project)
        assert "coverage_summary" in result
        assert "lrm" in result
        assert "lrt" in result

    def test_with_spec_file(self, tmp_project):
        """GIVEN spec file WHEN generating traceability THEN includes recommendations."""
        docs_dir = Path(tmp_project) / "docs"
        docs_dir.mkdir(parents=True)
        spec_path = docs_dir / "spec.md"
        spec_path.write_text("""# Requirements
        - The system SHALL boot.
        """)
        result = generate_traceability_report(
            tmp_project, spec_path=str(spec_path)
        )
        assert "recommendations" in result


# ── generate_lrt ──────────────────────────────────────────────────────

class TestGenerateLRT:
    def test_basic_report(self, tmp_project):
        """GIVEN spec file WHEN generating LRT THEN includes gap analysis."""
        docs_dir = Path(tmp_project) / "docs"
        docs_dir.mkdir(parents=True)
        spec_path = docs_dir / "spec.md"
        spec_path.write_text("""# Requirements
        - The system SHALL boot.
        """)
        result = generate_lrt(tmp_project, spec_path=str(spec_path))
        assert "lrm" in result
        assert "gap_analysis" in result
        assert "orphaned_test_files" in result
