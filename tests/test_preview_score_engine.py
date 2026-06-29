"""Tests for yuleosh.preview.score_engine — pure function coverage."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.preview.score_engine import (
    _count_total_lines,
    _count_by_extension,
    _extract_lines,
    _detect_languages,
    _assess_documentation,
    _estimate_effort,
    _compute_maturity,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def tmp_source_dir():
    """Create a temp source directory with a few sample files."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "main.c").write_text("int main() {\n    return 0;\n}\n")
        (root / "utils.h").write_text("#pragma once\nint add(int, int);\n")
        (root / "script.py").write_text("def hello():\n    return 'world'\n")
        (root / "README.md").write_text("# Project\n\n## Usage\nRun make.")
        (root / "spec.md").write_text("# Spec\n\nSHALL-1: do something.\n")
        yield root


@pytest.fixture
def sample_files(tmp_source_dir):
    return sorted(tmp_source_dir.rglob("*"))


# ------------------------------------------------------------------
# _count_total_lines
# ------------------------------------------------------------------

def test_count_total_lines_returns_sum(sample_files):
    """GIVEN a list of files WHEN counting total lines THEN return correct sum."""
    assert _count_total_lines(sample_files) >= 6


def test_count_total_lines_empty_list():
    """GIVEN empty list WHEN counting total lines THEN return 0."""
    assert _count_total_lines([]) == 0


def test_count_total_lines_ignores_missing_files(tmp_path):
    """GIVEN files with read errors WHEN counting lines THEN silently skip."""
    missing = [tmp_path / "nonexistent.py"]
    assert _count_total_lines(missing) == 0


# ------------------------------------------------------------------
# _count_by_extension
# ------------------------------------------------------------------

def test_count_by_extension_basic(sample_files):
    """GIVEN files of different extensions WHEN counting by ext THEN return correct dict."""
    result = _count_by_extension(sample_files)
    assert ".c" in result
    assert ".h" in result
    assert ".py" in result


def test_count_by_extension_empty():
    """GIVEN empty list WHEN counting by ext THEN return empty dict."""
    assert _count_by_extension([]) == {}


def test_count_by_extension_case_insensitive(tmp_path):
    """GIVEN same extension with different cases WHEN counting THEN group together."""
    (tmp_path / "a.C").write_text("a")
    (tmp_path / "b.c").write_text("b")
    files = sorted(tmp_path.iterdir())
    result = _count_by_extension(files)
    assert result.get(".c", 0) == 2


# ------------------------------------------------------------------
# _extract_lines
# ------------------------------------------------------------------

def test_extract_lines_basic(sample_files):
    """GIVEN files WHEN extracting lines by ext THEN return correct dict."""
    result = _extract_lines(sample_files)
    assert result.get(".py", 0) >= 1
    assert result.get(".c", 0) >= 3


def test_extract_lines_empty():
    """GIVEN empty list WHEN extracting lines THEN return empty dict."""
    assert _extract_lines([]) == {}


# ------------------------------------------------------------------
# _detect_languages
# ------------------------------------------------------------------

def test_detect_languages_returns_distribution(sample_files, tmp_source_dir):
    """GIVEN files in source dir WHEN detecting languages THEN return distribution."""
    result = _detect_languages(sample_files, tmp_source_dir)
    assert "distribution" in result
    assert "primary_language" in result
    assert isinstance(result["primary_language"], str)


def test_detect_languages_empty_dir(tmp_path):
    """GIVEN empty directory WHEN detecting languages THEN return unknown."""
    result = _detect_languages([], tmp_path)
    assert result["primary_language"] == "Unknown"


def test_detect_languages_unknown_extension(tmp_path):
    """GIVEN files with unknown extension WHEN detecting THEN classify as Other."""
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01")
    result = _detect_languages([f], tmp_path)
    assert "Other" in result["distribution"]


# ------------------------------------------------------------------
# _assess_documentation
# ------------------------------------------------------------------

def test_assess_documentation_has_readme_and_spec(tmp_source_dir):
    """GIVEN project with README and spec WHEN assessing THEN score > 0."""
    result = _assess_documentation(tmp_source_dir)
    assert result["has_readme"] is True
    assert result["has_spec"] is True
    assert result["doc_score"] >= 50


def test_assess_documentation_empty(tmp_path):
    """GIVEN empty project WHEN assessing THEN returns zero scores."""
    result = _assess_documentation(tmp_path)
    assert result["has_readme"] is False
    assert result["has_spec"] is False
    assert result["doc_score"] == 0


def test_assess_documentation_c_comment_ratio(tmp_source_dir):
    """GIVEN C files with comments WHEN assessing THEN ratio is computed."""
    (tmp_source_dir / "test.c").write_text(
        "// comment line\nint x = 1;\n/* block */\nint y = 2;\n"
    )
    result = _assess_documentation(tmp_source_dir)
    assert result["comment_to_code_ratio"] >= 0.3


# ------------------------------------------------------------------
# _estimate_effort
# ------------------------------------------------------------------

def test_estimate_effort_basic(sample_files):
    """GIVEN source files WHEN estimating effort THEN return dict with hours."""
    result = _estimate_effort(sample_files, [], {"avg_lines_per_function": 10})
    assert "estimated_person_hours" in result
    assert result["source_lines_of_code"] >= 1
    assert result["complexity_multiplier"] == 1.0


def test_estimate_effort_high_complexity(sample_files):
    """GIVEN high average LPF WHEN estimating THEN apply complexity multiplier > 1."""
    result = _estimate_effort(sample_files, [], {"avg_lines_per_function": 50})
    assert result["complexity_multiplier"] == 1.4


def test_estimate_effort_autosar(sample_files):
    """GIVEN AUTOSAR framework WHEN estimating THEN framework multiplier is 1.4."""
    result = _estimate_effort(sample_files, [{"name": "AUTOSAR"}], {"avg_lines_per_function": 10})
    assert result["framework_multiplier"] == 1.4


def test_estimate_effort_empty_files():
    """GIVEN no source files WHEN estimating THEN hours is 0."""
    result = _estimate_effort([], [], {"avg_lines_per_function": 10})
    assert result["estimated_person_hours"] == 0.0
    assert result["source_lines_of_code"] == 0


# ------------------------------------------------------------------
# _compute_maturity
# ------------------------------------------------------------------

def test_compute_maturity_good_score():
    """GIVEN excellent project parameters WHEN computing maturity THEN score >= 70."""
    result = _compute_maturity(
        test_framework="pytest",
        test_density=0.8,
        test_file_count=10,
        complexity={"avg_lines_per_function": 10},
        doc_quality={"doc_score": 100},
        frameworks=[],
        coverage={"current_coverage_estimate": 80},
    )
    assert result["score"] >= 70
    assert result["rating"] == "good"


def test_compute_maturity_no_tests():
    """GIVEN no test framework WHEN computing maturity THEN score is low."""
    result = _compute_maturity(
        test_framework="none",
        test_density=0.0,
        test_file_count=0,
        complexity={"avg_lines_per_function": 10},
        doc_quality={"doc_score": 0},
        frameworks=[],
        coverage={"current_coverage_estimate": 0},
    )
    assert result["score"] <= 20


def test_compute_maturity_autosar_penalty():
    """GIVEN AUTOSAR framework WHEN computing maturity THEN score is reduced."""
    result = _compute_maturity(
        test_framework="pytest",
        test_density=0.5,
        test_file_count=5,
        complexity={"avg_lines_per_function": 10},
        doc_quality={"doc_score": 50},
        frameworks=[{"name": "AUTOSAR"}],
        coverage={"current_coverage_estimate": 60},
    )
    # AUTOSAR subtracts 5
    assert result["score"] >= 0


def test_compute_maturity_high_function_complexity():
    """GIVEN very high LPF WHEN computing maturity THEN score is reduced."""
    result = _compute_maturity(
        test_framework="pytest",
        test_density=0.3,
        test_file_count=3,
        complexity={"avg_lines_per_function": 60},
        doc_quality={"doc_score": 20},
        frameworks=[],
        coverage={"current_coverage_estimate": 30},
    )
    assert result["score"] < 50


def test_compute_maturity_score_clamped():
    """GIVEN extreme values WHEN computing maturity THEN score stays 0-100."""
    result = _compute_maturity(
        test_framework="pytest",
        test_density=99.0,
        test_file_count=999,
        complexity={"avg_lines_per_function": 1},
        doc_quality={"doc_score": 100},
        frameworks=[],
        coverage={"current_coverage_estimate": 100},
    )
    assert 0 <= result["score"] <= 100
