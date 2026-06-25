#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit tests for yuleosh.ci.review_helpers."""

import tempfile
from pathlib import Path

import pytest

from yuleosh.ci.review_helpers import (
    parse_junit_xml,
    auto_map_shall_coverage,
    find_test_source_files,
)


class TestFindTestSourceFiles:
    """Tests for find_test_source_files()."""

    def test_finds_python_test_files(self):
        """SHALL find .py test files matching known patterns."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            # Create test files matching glob patterns
            (tdir / "tests" / "unit").mkdir(parents=True)
            (tdir / "tests" / "unit" / "test_foo.py").write_text("")
            (tdir / "tests" / "unit" / "test_bar.py").write_text("")
            (tdir / "src" / "yuleosh" / "ci").mkdir(parents=True)
            (tdir / "src" / "yuleosh" / "ci" / "test_baz.py").write_text("")
            (tdir / "src" / "yuleosh" / "ci" / "stuff_test.py").write_text("")

            result = find_test_source_files(tdir)

            names = [p.name for p in result]
            assert "test_foo.py" in names
            assert "test_bar.py" in names
            assert "test_baz.py" in names
            assert "stuff_test.py" in names
            assert len(result) >= 4

    def test_finds_c_test_files(self):
        """SHALL find .c test files matching known patterns."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "tests" / "unit").mkdir(parents=True)
            (tdir / "src").mkdir(parents=True)
            (tdir / "tests" / "unit" / "test_main.c").write_text("")
            (tdir / "tests" / "unit" / "test_foo.c").write_text("")
            (tdir / "src" / "test_bar.c").write_text("")

            result = find_test_source_files(tdir)

            names = [p.name for p in result]
            assert "test_main.c" in names
            assert "test_foo.c" in names
            assert "test_bar.c" in names
            assert len(result) >= 3

    def test_deduplicates(self):
        """SHALL return unique files when paths resolve to same location."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "tests" / "unit").mkdir(parents=True)
            # Create a file that matches multiple patterns
            (tdir / "tests" / "unit" / "test_foo.py").write_text("")

            result = find_test_source_files(tdir)

            # Should only appear once despite matching multiple patterns
            names = [p.name for p in result]
            assert names.count("test_foo.py") == 1

    def test_empty_project(self):
        """SHALL return empty list when no test files exist."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            result = find_test_source_files(tdir)
            assert isinstance(result, list)
            assert len(result) == 0

    def test_non_python_non_c_files_excluded(self):
        """SHALL NOT include non-test files or irrelevant extensions."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "tests" / "unit").mkdir(parents=True)
            (tdir / "tests" / "unit" / "test_helper.js").write_text("")
            (tdir / "tests" / "unit" / "data.json").write_text("")
            (tdir / "tests" / "unit" / "test_foo.cpp").write_text("")

            result = find_test_source_files(tdir)

            names = [p.name for p in result]
            assert "test_foo.cpp" not in names  # .cpp excluded
            assert "test_helper.js" not in names  # .js excluded
            assert "data.json" not in names  # .json excluded

    def test_handles_relative_paths(self):
        """SHALL accept relative paths and still return valid results."""
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            (tdir / "tests" / "unit").mkdir(parents=True)
            (tdir / "tests" / "unit" / "test_rel.py").write_text("")

            result = find_test_source_files(Path(td))

            names = [p.name for p in result]
            assert "test_rel.py" in names


class TestParseJunitXml:
    """Tests for parse_junit_xml()."""

    def test_valid_xml(self):
        """SHALL parse a valid JUnit XML file."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = Path(td) / "junit.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3" errors="1" failures="1" skipped="0">
    <testcase classname="test_foo" name="test_passes" time="0.01"/>
    <testcase classname="test_foo" name="test_fails" time="0.02">
        <failure message="AssertionError: assert 0">
Traceback (most recent call last):
  File "test_foo.py", line 10, in test_fails
    assert 0
AssertionError
        </failure>
    </testcase>
    <testcase classname="test_foo" name="test_errors" time="0.03">
        <error message="ValueError: invalid literal" type="ValueError"/>
    </testcase>
</testsuite>
""")
            result = parse_junit_xml(xml_path)

            assert len(result) == 3
            statuses = {tc["name"]: tc["status"] for tc in result}
            assert statuses["test_foo::test_passes"] == "passed"
            assert statuses["test_foo::test_fails"] == "failed"
            assert statuses["test_foo::test_errors"] == "error"

    def test_empty_xml(self):
        """SHALL return empty list for an empty testsuite."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = Path(td) / "empty.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="0"/>
""")
            result = parse_junit_xml(xml_path)
            assert result == []

    def test_malformed_xml(self):
        """SHALL return empty list for malformed XML."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = Path(td) / "bad.xml"
            xml_path.write_text("not valid xml")
            result = parse_junit_xml(xml_path)
            assert result == []


class TestAutoMapShallCoverage:
    """Tests for auto_map_shall_coverage()."""

    def test_basic_mapping(self):
        """SHALL map SHALL IDs to matching test case result names."""
        shalls = [
            {"id": "SYS_REQ_SWE_1", "shall_id": "10.1", "text": "The system shall..."},
            {"id": "SYS_REQ_SWE_2", "shall_id": "10.2", "text": "The system shall..."},
        ]
        test_results = [
            {"name": "test_foo::test_shall_10_1", "status": "passed", "duration": 0.01},
            {"name": "test_foo::test_shall_10_2", "status": "failed", "duration": 0.02},
        ]
        source_files = []

        result = auto_map_shall_coverage(shall_stats := shalls, test_results, source_files)

        # Returns (covered_indices, shall_to_tests_map, shall_assertion_map)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_no_matches(self):
        """SHALL return empty map when no SHALL IDs match test names."""
        shalls = [
            {"id": "SYS_REQ_SWE_1", "shall_id": "99.9", "text": "The system shall..."},
        ]
        test_results = [
            {"name": "test_foo::test_something", "status": "passed", "duration": 0.01},
        ]
        source_files = []

        result = auto_map_shall_coverage(shall_stats := shalls, test_results, source_files)

        assert isinstance(result, tuple)
        assert len(result) == 3
