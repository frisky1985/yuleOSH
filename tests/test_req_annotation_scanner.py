#!/usr/bin/env python3

# @tests src/yuleosh/alm/traceability.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for @req annotation scanner and CJK keyword extraction."""

import pytest
from pathlib import Path

from yuleosh.alm.traceability import (
    scan_req_annotations,
    scan_test_code_links,
    _extract_keywords,
    _find_code_by_keywords,
    generate_lrm,
)


class TestScanReqAnnotations:
    """Tests for scan_req_annotations()."""

    def test_python_req_annotation(self, tmp_path):
        """# @req RS-001 in .py file → result["RS-001"] contains file."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "module.py"
        py_file.write_text("# @req RS-001\ndef foo(): pass\n")

        result = scan_req_annotations(src_dir)

        assert "RS-001" in result
        assert any("module.py" in p for p in result["RS-001"])

    def test_c_line_comment_annotation(self, tmp_path):
        """// @req RS-001 in .c file → mapped."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        c_file = src_dir / "driver.c"
        c_file.write_text("// @req RS-002\nvoid init() {}\n")

        result = scan_req_annotations(src_dir)

        assert "RS-002" in result
        assert any("driver.c" in p for p in result["RS-002"])

    def test_decorator_style(self, tmp_path):
        """@req(RS-001) decorator style → mapped."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "handler.py"
        py_file.write_text("@req(RS-003)\ndef handle(): pass\n")

        result = scan_req_annotations(src_dir)

        assert "RS-003" in result
        assert any("handler.py" in p for p in result["RS-003"])

    def test_multi_id_one_line(self, tmp_path):
        """@req RS-001, RS-002 → both in result."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "multi.py"
        py_file.write_text("# @req RS-001, RS-004\ndef dual(): pass\n")

        result = scan_req_annotations(src_dir)

        assert "RS-001" in result
        assert "RS-004" in result

    def test_case_insensitive_normalized(self, tmp_path):
        """@req rs-001 → "RS-001" key (uppercased)."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "lower.py"
        py_file.write_text("# @req rs-005\ndef low(): pass\n")

        result = scan_req_annotations(src_dir)

        assert "RS-005" in result

    def test_no_annotations_empty(self, tmp_path):
        """File with no @req → {}."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "plain.py"
        py_file.write_text("def plain(): pass\n")

        result = scan_req_annotations(src_dir)

        assert result == {}

    def test_c_block_comment_not_false_positive(self, tmp_path):
        """Annotation inside stripped /* */ block comment → NOT in result."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        c_file = src_dir / "commented.c"
        # The @req is inside a block comment, should be stripped
        c_file.write_text("/* @req RS-006 */\nvoid foo() {}\n")

        result = scan_req_annotations(src_dir)

        # Block comments are stripped, so RS-006 should NOT appear
        assert "RS-006" not in result


class TestCJKKeywordExtraction:
    """Tests for CJK bigram extraction in _extract_keywords()."""

    def test_chinese_bigrams_in_extract_keywords(self):
        """_extract_keywords("系统应在100ms内完成初始化") contains 初始 bigram."""
        statement = "系统应在100ms内完成初始化"
        keywords = _extract_keywords(statement)

        # 初始化 → 初始, 始化 bigrams
        assert "初始" in keywords or "始化" in keywords

    def test_zh_stop_words_filtered(self):
        """应当 configured as zh stop word → excluded from keywords."""
        # The default _DEFAULT_ZH_STOP_WORDS includes "应当"
        statement = "系统应当完成初始化"
        keywords = _extract_keywords(statement)

        # 应当 is a stop word, should be filtered out
        assert "应当" not in keywords


class TestCFileScanning:
    """Tests for C/H file scanning in keyword functions."""

    def test_c_file_scanned_by_find_code_keywords(self, tmp_path):
        """.c file with keyword → returned by _find_code_by_keywords."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        c_file = src_dir / "driver.c"
        c_file.write_text("void uart_init() {}\n")

        result = _find_code_by_keywords(src_dir, ["uart"])

        assert len(result) > 0
        assert any("driver.c" in p for p in result)


class TestGenerateLRMIntegration:
    """Integration tests for generate_lrm() with annotations and Chinese."""

    def test_generate_lrm_annotation_integration(self, tmp_path):
        """generate_lrm on tmp project with @req RS-001 in .py → has_code=True, match_method="annotation"."""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create spec with SHALL statement in list format
        spec_file = docs_dir / "spec.md"
        spec_file.write_text("# Requirements\n\n## RS-001\n\n- The system SHALL initialize within 100ms.\n")

        # Create source file with @req annotation
        py_file = src_dir / "init.py"
        py_file.write_text("# @req RS-001\ndef init(): pass\n")

        result = generate_lrm(str(tmp_path))

        assert len(result["requirements"]) > 0
        req = result["requirements"][0]
        assert req["has_code"] is True
        assert req["match_method"] == "annotation"

    def test_generate_lrm_chinese_spec(self, tmp_path):
        """generate_lrm on tmp project with Chinese SHALL → keyword bigrams find source with same CJK chars."""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create spec with Chinese text but include SHALL keyword for extraction
        spec_file = docs_dir / "spec.md"
        spec_file.write_text("# 需求\n\n## RS-010\n\n- The system SHALL 完成初始化 within 100ms.\n")

        # Create source file with matching CJK content
        py_file = src_dir / "init.py"
        py_file.write_text("# 初始化模块\ndef init(): pass\n")

        result = generate_lrm(str(tmp_path))

        assert len(result["requirements"]) > 0
        req = result["requirements"][0]
        # Should find the source file via CJK bigram matching
        assert req["has_code"] is True
        assert req["match_method"] in ("keyword", "annotation", "comment")


class TestScanTestCodeLinks:
    """Tests for scan_test_code_links() — test → code direct traceability."""

    def test_tests_annotation_file_only(self, tmp_path):
        """@tests src/init.py → test_links contains source_file."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_init.py"
        test_file.write_text("# @tests src/init.py\ndef test_init(): pass\n")

        result = scan_test_code_links(tmp_path)

        assert "tests/test_init.py" in result
        assert result["tests/test_init.py"]["source_file"] == "src/init.py"
        assert result["tests/test_init.py"]["functions"] == []

    def test_tests_annotation_with_function(self, tmp_path):
        """@tests src/init.py:init() → functions contains 'init'."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_init.py"
        test_file.write_text("# @tests src/init.py:init()\ndef test_init(): pass\n")

        result = scan_test_code_links(tmp_path)

        assert "tests/test_init.py" in result
        assert result["tests/test_init.py"]["source_file"] == "src/init.py"
        assert "init" in result["tests/test_init.py"]["functions"]

    def test_tests_annotation_multiple_functions(self, tmp_path):
        """@tests src/init.py:init, helper → functions contains both."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_init.py"
        test_file.write_text("# @tests src/init.py:init, helper\ndef test_init(): pass\n")

        result = scan_test_code_links(tmp_path)

        assert "tests/test_init.py" in result
        funcs = result["tests/test_init.py"]["functions"]
        assert "init" in funcs
        assert "helper" in funcs

    def test_no_tests_annotation_empty(self, tmp_path):
        """Test file with no @tests → {}."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_plain.py"
        test_file.write_text("def test_plain(): pass\n")

        result = scan_test_code_links(tmp_path)

        assert result == {}

    def test_no_tests_dir(self, tmp_path):
        """No tests/ directory → {}."""
        result = scan_test_code_links(tmp_path)
        assert result == {}
