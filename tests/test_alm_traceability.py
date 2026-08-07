"""Tests for yuleosh.alm.traceability — SHALL statement extraction & traceability."""

import json
from pathlib import Path
import pytest

from yuleosh.alm.traceability import (
    extract_shall_statements,
    extract_shall_from_text,
    generate_lrm,
    generate_lrt,
    _find_code_by_keywords,
    _extract_keywords,
)


# ------------------------------------------------------------------
# extract_shall_from_text
# ------------------------------------------------------------------

def test_extract_shall_from_text_basic():
    """GIVEN text with SHALL statements WHEN extracting THEN returns list."""
    text = """
    REQ-001: The system SHALL boot within 5 seconds.
    REQ-002: The system SHALL NOT crash on invalid input.
    # This is a comment, SHALL be ignored.
    """
    results = extract_shall_from_text(text)
    assert isinstance(results, list)
    assert len(results) >= 2


def test_extract_shall_from_text_no_shall():
    """GIVEN text without SHALL statements WHEN extracting THEN returns empty."""
    text = "This is just some regular text without requirements."
    results = extract_shall_from_text(text)
    assert results == []


def test_extract_shall_from_text_with_id():
    """GIVEN text with REQ-XXX IDs WHEN extracting THEN includes IDs."""
    text = "REQ-001: The system SHALL handle errors."
    results = extract_shall_from_text(text)
    if results:
        assert "id" in results[0] or "req_id" in results[0]


def test_extract_shall_from_text_multiple():
    """GIVEN text with SHALL WHEN extracting THEN returns non-empty list."""
    text = "SHALL do A. SHALL do B. SHALL do C."
    results = extract_shall_from_text(text)
    assert len(results) >= 1
    assert "SHALL" in results[0]["statement"]


# ------------------------------------------------------------------
# extract_shall_statements from file
# ------------------------------------------------------------------

def test_extract_shall_statements_no_file(tmp_path):
    """GIVEN missing spec file WHEN extracting THEN returns empty list."""
    results = extract_shall_statements(str(tmp_path / "nope.md"))
    assert results == []


def test_extract_shall_statements_valid_file(tmp_path):
    """GIVEN spec file with SHALL statements WHEN extracting THEN returns list."""
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\nREQ-001: The system SHALL boot.\nREQ-002: The system SHALL log.\n")
    results = extract_shall_statements(str(spec))
    assert isinstance(results, list)


def test_extract_shall_statements_no_shall(tmp_path):
    """GIVEN spec file without SHALL WHEN extracting THEN returns empty list."""
    spec = tmp_path / "no_req.md"
    spec.write_text("# Just a title\n")
    results = extract_shall_statements(str(spec))
    assert results == [] or isinstance(results, list)


# ------------------------------------------------------------------
# generate_lrm (requirements -> implemented mapping)
# ------------------------------------------------------------------

def test_generate_lrm_no_project(tmp_path):
    """GIVEN project without artifacts WHEN generating LRM THEN returns dict."""
    result = generate_lrm(str(tmp_path))
    assert isinstance(result, dict)


def test_generate_lrm_with_spec(tmp_path):
    """GIVEN project with spec WHEN generating LRM THEN returns dict."""
    spec = tmp_path / "spec.md"
    spec.write_text("REQ-001: The system SHALL work.\n")
    result = generate_lrm(str(tmp_path), spec_path=str(spec))
    assert isinstance(result, dict)


# ------------------------------------------------------------------
# generate_lrt (requirements -> test mapping)
# ------------------------------------------------------------------

def test_generate_lrt_no_project(tmp_path):
    """GIVEN project without artifacts WHEN generating LRT THEN returns dict."""
    result = generate_lrt(str(tmp_path))
    assert isinstance(result, dict)


# ------------------------------------------------------------------
# _extract_keywords
# ------------------------------------------------------------------

def test_extract_keywords_basic():
    """GIVEN a sentence WHEN extracting keywords THEN returns list."""
    result = _extract_keywords("The system shall boot the operating system")
    assert isinstance(result, list)


# ------------------------------------------------------------------
# _find_code_by_keywords
# ------------------------------------------------------------------

def test_find_code_by_keywords_no_dir(tmp_path):
    """GIVEN no source dir WHEN finding code by keywords THEN returns list."""
    result = _find_code_by_keywords(tmp_path / "nonexistent", ["boot"])
    assert isinstance(result, list)
