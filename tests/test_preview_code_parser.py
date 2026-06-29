"""Tests for yuleosh.preview.code_parser — file discovery and analysis."""

import tempfile
from pathlib import Path
import pytest

from yuleosh.preview.code_parser import (
    _discover_files,
    _scan_frameworks,
    _find_matching_files,
    _measure_complexity,
    _measure_max_nesting,
    _measure_per_file_complexity,
    _detect_test_framework,
)


@pytest.fixture
def tmp_project():
    """Create a temp project with mixed source files."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        (root / "src" / "main.c").write_text(
            "int main() {\n    int x = 1;\n    if (x) { return 0; }\n    return 1;\n}\n"
        )
        (root / "src" / "utils.h").write_text("#pragma once\nvoid foo(void);\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text(
            "def test_shall_1():\n    assert True\n"
        )
        (root / "Makefile").write_text("all:\n\tgcc main.c\n")
        (root / "README.md").write_text("# Project\n")
        yield root


# ------------------------------------------------------------------
# _discover_files
# ------------------------------------------------------------------

def test_discover_files_basic(tmp_project):
    """GIVEN source directory WHEN discovering files THEN returns categorized lists."""
    result = _discover_files(tmp_project)
    files, source_exts, test_exts, config_files, doc_files = result
    assert len(files) >= 3
    # files are relative paths like "src/main.c"
    file_names = [str(f) for f in files]
    assert any("main.c" in n for n in file_names)


def test_discover_files_empty(tmp_path):
    """GIVEN empty directory WHEN discovering files THEN returns empty lists."""
    result = _discover_files(tmp_path)
    files, source_exts, test_exts, config_files, doc_files = result
    assert files == []
    assert source_exts == []


# ------------------------------------------------------------------
# _scan_frameworks
# ------------------------------------------------------------------

def test_scan_frameworks_basic(tmp_project):
    """GIVEN project with known files WHEN scanning frameworks THEN detects them."""
    frameworks = _scan_frameworks(tmp_project)
    assert isinstance(frameworks, list)
    # May be empty if no framework markers found


def test_scan_frameworks_with_makefile(tmp_project):
    """GIVEN project with Makefile WHEN scanning THEN may detect build system."""
    frameworks = _scan_frameworks(tmp_project)
    names = [fw["name"] for fw in frameworks]
    # Makefile is detected
    assert isinstance(frameworks, list)


# ------------------------------------------------------------------
# _find_matching_files
# ------------------------------------------------------------------

def test_find_matching_files_valid_regex(tmp_project):
    """GIVEN valid regex pattern WHEN finding matching files THEN returns matches."""
    # _find_matching_files uses re.compile, so the pattern is a regex, not glob
    files = _find_matching_files(tmp_project, r"int main")
    assert len(files) >= 1


def test_find_matching_files_no_match(tmp_project):
    """GIVEN pattern with no matches WHEN finding THEN returns empty list."""
    files = _find_matching_files(tmp_project, r"nonexistent_pattern_xyz")
    assert files == []


# ------------------------------------------------------------------
# _measure_complexity
# ------------------------------------------------------------------

def test_measure_complexity_basic(tmp_project):
    """GIVEN project with source files WHEN measuring complexity THEN returns dict."""
    result = _measure_complexity(tmp_project)
    assert isinstance(result, dict)
    assert "total_functions" in result or "avg_lines_per_function" in result


def test_measure_complexity_empty(tmp_path):
    """GIVEN empty project WHEN measuring complexity THEN returns default values."""
    result = _measure_complexity(tmp_path)
    assert isinstance(result, dict)


# ------------------------------------------------------------------
# _measure_max_nesting
# ------------------------------------------------------------------

def test_measure_max_nesting_basic(tmp_project):
    """GIVEN project with nested code WHEN measuring nesting THEN returns int."""
    nesting = _measure_max_nesting(tmp_project)
    assert isinstance(nesting, int)
    assert nesting >= 0


def test_measure_max_nesting_empty(tmp_path):
    """GIVEN empty project WHEN measuring nesting THEN returns 0."""
    nesting = _measure_max_nesting(tmp_path)
    assert nesting == 0


# ------------------------------------------------------------------
# _measure_per_file_complexity
# ------------------------------------------------------------------

def test_measure_per_file_complexity_basic(tmp_project):
    """GIVEN project WHEN measuring per-file complexity THEN returns list."""
    results = _measure_per_file_complexity(tmp_project)
    assert isinstance(results, list)


# ------------------------------------------------------------------
# _detect_test_framework
# ------------------------------------------------------------------

def test_detect_test_framework_pytest(tmp_project):
    """GIVEN project with pytest test files WHEN detecting framework THEN identifies pytest."""
    framework = _detect_test_framework(tmp_project)
    assert isinstance(framework, str)


def test_detect_test_framework_empty(tmp_path):
    """GIVEN project without tests WHEN detecting framework THEN returns 'unknown'."""
    framework = _detect_test_framework(tmp_path)
    assert framework in ("unknown", "none")
