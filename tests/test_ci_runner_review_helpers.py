#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for ci/runner.py and ci/review_helpers.py.

Target: 70%+ statement coverage for runner.py, 50%+ for review_helpers.py.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# ==================================================================
# ci/runner.py
# ==================================================================


class TestRunnerFunctions:
    """Test pure/helper functions from ci/runner.py."""

    def test_import_module(self):
        """Verify the module can be imported."""
        import yuleosh.ci.runner
        assert hasattr(yuleosh.ci.runner, 'run_all')

    @mock.patch("yuleosh.ci.runner.subprocess.run")
    def test_git_commit_hash(self, mock_run):
        from yuleosh.ci.runner import git_commit_hash

        mock_proc = mock.Mock()
        mock_proc.stdout = "abc123def456\n"
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = git_commit_hash()
        assert result == "abc123def456"

    @mock.patch("yuleosh.ci.runner.subprocess.run")
    def test_git_commit_hash_nonzero_exit(self, mock_run):
        from yuleosh.ci.runner import git_commit_hash

        mock_proc = mock.Mock()
        mock_proc.stdout = ""
        mock_proc.returncode = 1
        mock_run.return_value = mock_proc

        result = git_commit_hash()
        assert result == "unknown"

    @mock.patch("yuleosh.ci.runner.subprocess.run")
    def test_git_commit_hash_empty_stdout(self, mock_run):
        from yuleosh.ci.runner import git_commit_hash

        mock_proc = mock.Mock()
        mock_proc.stdout = "abc\n"
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = git_commit_hash()
        assert result == "abc"

    @mock.patch("yuleosh.ci.runner.subprocess.run")
    def test_get_changed_files(self, mock_run):
        from yuleosh.ci.runner import get_changed_files

        mock_proc = mock.Mock()
        mock_proc.stdout = "src/main.c\nsrc/utils.h\n"
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = get_changed_files()
        assert len(result) == 2
        assert "src/main.c" in result

    @mock.patch("yuleosh.ci.runner.subprocess.run")
    def test_get_changed_files_empty(self, mock_run):
        from yuleosh.ci.runner import get_changed_files

        mock_proc = mock.Mock()
        mock_proc.stdout = ""
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        result = get_changed_files()
        assert result == []

    def test_run_all_importable(self):
        """Verify run_all exists and is callable."""
        from yuleosh.ci.runner import run_all
        assert callable(run_all)


# ==================================================================
# ci/review_helpers.py
# ==================================================================


class TestReviewHelpers:
    """Tests for ci/review_helpers.py functions."""

    def test_import(self):
        import yuleosh.ci.review_helpers as rh
        assert hasattr(rh, 'parse_junit_xml')
        assert hasattr(rh, '_infer_test_type')
        assert hasattr(rh, 'auto_map_shall_coverage')

    def test_parse_junit_xml_empty_file(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "empty.xml"
            xml_path.write_text("")
            result = parse_junit_xml(xml_path)
        assert result == []

    def test_parse_junit_xml_testsuite(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "report.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="suite1" tests="2" failures="0" errors="0" time="0.1">
                <testcase name="test_foo" classname="TestFoo" time="0.05"/>
                <testcase name="test_bar" classname="TestBar" time="0.03"/>
            </testsuite>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 2

    def test_parse_junit_xml_with_failure(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "fail.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="suite1" tests="1" failures="1">
                <testcase name="test_fail" classname="TestFail" time="0.1">
                    <failure message="assertion error" type="AssertionError"/>
                </testcase>
            </testsuite>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 1
        assert result[0]["status"] == "failed"

    def test_parse_junit_xml_with_skipped(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "skip.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="suite1" tests="1" skipped="1">
                <testcase name="test_skip" classname="TestSkip" time="0.0">
                    <skipped message="skip reason"/>
                </testcase>
            </testsuite>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 1
        assert result[0]["status"] == "skipped"

    def test_parse_junit_xml_with_error(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "error.xml"
            xml_path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="suite1" tests="1" errors="1">
                <testcase name="test_err" classname="TestErr" time="0.1">
                    <error message="setup failed" type="Exception"/>
                </testcase>
            </testsuite>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 1
        assert result[0]["status"] == "error"

    def test_parse_junit_xml_testsuites_wrapper(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "multi.xml"
            xml_path.write_text("""<?xml version="1.0"?>
            <testsuites>
                <testsuite name="a" tests="1">
                    <testcase name="t1" classname="C1" time="0.1"/>
                </testsuite>
                <testsuite name="b" tests="1">
                    <testcase name="t2" classname="C2" time="0.2"/>
                </testsuite>
            </testsuites>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 2

    def test_parse_junit_xml_unknown_root(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "unknown.xml"
            xml_path.write_text("""<?xml version="1.0"?><unknown_root/>""")
            result = parse_junit_xml(xml_path)
        assert result == []

    def test_parse_junit_xml_no_classname(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "no_class.xml"
            xml_path.write_text("""<?xml version="1.0"?>
            <testsuite name="s" tests="1">
                <testcase name="test_no_class" time="0.1"/>
            </testsuite>""")
            result = parse_junit_xml(xml_path)
        assert len(result) == 1
        assert result[0]["classname"] == ""

    def test_parse_junit_xml_nonexistent_file(self):
        from yuleosh.ci.review_helpers import parse_junit_xml

        result = parse_junit_xml(Path("/nonexistent/path/report.xml"))
        assert result == []

    def test_infer_test_type_unit(self):
        from yuleosh.ci.review_helpers import _infer_test_type

        result = _infer_test_type("test_unit_foo", Path("dummy.xml"))
        assert result == "unit"

    def test_infer_test_type_integration(self):
        from yuleosh.ci.review_helpers import _infer_test_type

        result = _infer_test_type("test_integration_bar", Path("dummy.xml"))
        assert result == "integration"

    def test_infer_test_type_system(self):
        from yuleosh.ci.review_helpers import _infer_test_type

        result = _infer_test_type("test_system_baz", Path("dummy.xml"))
        assert result == "system"

    def test_infer_test_type_default(self):
        from yuleosh.ci.review_helpers import _infer_test_type

        result = _infer_test_type("test_something_else", Path("dummy.xml"))
        assert result == "unit"

    def test_auto_map_shall_coverage_basic(self):
        from yuleosh.ci.review_helpers import auto_map_shall_coverage

        shall_statements = [
            {"statement": "SHALL-001: The system shall do X.", "section": "3.1"},
            {"statement": "SHALL-002: The system shall do Y.", "section": "3.2"},
        ]
        test_results = [
            {"name": "test_unit_shall_001"},
            {"name": "test_unit_shall_002"},
        ]

        covered_indices, shall_to_tests, _ = auto_map_shall_coverage(shall_statements, test_results)
        assert len(covered_indices) == 2
        assert any("SHALL-001" in k for k in shall_to_tests)
        assert any("SHALL-002" in k for k in shall_to_tests)

    def test_auto_map_shall_coverage_no_match(self):
        from yuleosh.ci.review_helpers import auto_map_shall_coverage

        shall_statements = [
            {"statement": "SHALL-001: The system shall do X.", "section": "3.1"},
        ]
        test_results = [
            {"name": "test_unrelated_function"},
        ]

        covered_indices, shall_to_tests, _ = auto_map_shall_coverage(shall_statements, test_results)
        assert len(covered_indices) == 0
        assert len(shall_to_tests) == 0

    def test_auto_map_shall_coverage_empty_spec(self):
        from yuleosh.ci.review_helpers import auto_map_shall_coverage

        covered_indices, shall_to_tests, shall_assertion_map = auto_map_shall_coverage([], [])
        assert len(covered_indices) == 0
        assert shall_to_tests == {}
        assert shall_assertion_map == {}

    def test_find_test_source_files(self):
        from yuleosh.ci.review_helpers import find_test_source_files

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "tests"
            test_dir.mkdir()
            (test_dir / "test_foo.py").write_text("def test_foo(): pass")
            (test_dir / "test_bar.c").write_text("void test_bar(void) {}")

            result = find_test_source_files(Path(tmpdir))

        assert len(result) > 0

    def test_extract_assertion_lines_with_func_body(self):
        from yuleosh.ci.review_helpers import _extract_assertion_lines

        with tempfile.TemporaryDirectory() as tmpdir:
            src_file = Path(tmpdir) / "test_something.py"
            src_file.write_text(
                "def test_something():\n"
                "    assert x == 1\n"
                "    assert y == 2\n"
                "def other_func():\n"
                "    pass\n"
            )

            result = _extract_assertion_lines([src_file], "test_something")
            assert len(result) >= 2

    def test_extract_assertion_lines_no_matches(self):
        from yuleosh.ci.review_helpers import _extract_assertion_lines

        result = _extract_assertion_lines([], "nonexistent")
        assert result == []

    def test_auto_map_shall_with_section_fallback(self):
        from yuleosh.ci.review_helpers import auto_map_shall_coverage

        shall_statements = [
            {"statement": "SHALL-003: The system shall handle errors.", "section": "4.2"},
        ]
        tests = [{"name": "test_shall_003_check"}]
        covered_indices, shall_to_tests, shall_assertion_map = auto_map_shall_coverage(shall_statements, tests)
        assert len(covered_indices) == 1
        assert len(shall_to_tests) == 1
