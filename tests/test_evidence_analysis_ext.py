"""Extended tests for evidence.analysis — targeting uncovered paths."""

import sys
import os
import ast
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.evidence.analysis import (
    parse_scenario_refs,
    parse_module_covers,
    parse_comment_covers,
    parse_function_covers,
    infer_covers_from_function_names,
    parse_covers_from_file,
    categorize_uncovered,
    _strip_scenario_ref,
)


class TestParseScenarioRefs:
    """Cover uncovered Scenario-Ref parsing paths."""

    def test_scenario_ref_standalone(self):
        text = "Some docstring\nScenario-Ref: REF-001\nMore text"
        assert parse_scenario_refs(text) == ["REF-001"]

    def test_scenario_ref_inline_covers(self):
        text = "Covers: feature A, Scenario-Ref: REF-002"
        assert parse_scenario_refs(text) == ["REF-002"]

    def test_scenario_ref_multiple_inline(self):
        text = "Covers: x, Scenario-Ref: REF-003, Scenario-Ref: REF-004"
        refs = parse_scenario_refs(text)
        # Single line match; the regex captures to end-of-line, then splits on ', Scenario-Ref:'
        assert len(refs) >= 1
        assert "REF-003" in refs

    def test_scenario_ref_case_insensitive(self):
        text = "scenario-ref: REF-005"
        assert parse_scenario_refs(text) == ["REF-005"]

    def test_scenario_ref_trailing_punctuation(self):
        text = 'Scenario-Ref: REF-006".'
        refs = parse_scenario_refs(text)
        assert len(refs) == 1

    def test_scenario_ref_empty_line(self):
        assert parse_scenario_refs("") == []

    def test_scenario_ref_no_match(self):
        assert parse_scenario_refs("Just some text") == []

    def test_scenario_ref_duplicate(self):
        text = "Scenario-Ref: REF-007\nScenario-Ref: REF-007"
        assert parse_scenario_refs(text) == ["REF-007"]


class TestParseModuleCovers:
    """Cover parse_module_covers paths."""

    def test_module_covers_present(self):
        tree = ast.parse('"""Covers: feature-x, feature-y"""')
        result = parse_module_covers(tree)
        assert "feature-x" in result
        assert "feature-y" in result

    def test_module_covers_with_scenario_ref(self):
        tree = ast.parse('"""Covers: feature-z, Scenario-Ref: REF-010"""')
        result = parse_module_covers(tree)
        assert "feature-z" in result
        # Scenario-Ref should be stripped
        assert "Scenario-Ref:" not in " ".join(result)

    def test_module_covers_no_docstring(self):
        tree = ast.parse("x = 1")
        assert parse_module_covers(tree) == []

    def test_module_covers_no_covers(self):
        tree = ast.parse('"""No covers marker here"""')
        assert parse_module_covers(tree) == []


class TestParseCommentCovers:
    """Cover parse_comment_covers paths."""

    def test_comment_covers_present(self):
        content = "# Covers: feature-a\n# Covers: feature-b"
        result = parse_comment_covers(content)
        assert "feature-a" in result
        assert "feature-b" in result

    def test_comment_covers_no_match(self):
        assert parse_comment_covers("/* Covers: feature */") == []

    def test_comment_covers_empty(self):
        assert parse_comment_covers("") == []

    def test_comment_covers_case_insensitive(self):
        content = "# COVERS: feature-c"
        assert parse_comment_covers(content) == ["feature-c"]


class TestParseFunctionCovers:
    """Cover parse_function_covers paths."""

    def test_function_covers_present(self):
        source = '''
def test_feature():
    """Covers: feature-d"""
    pass
'''
        tree = ast.parse(source)
        assert parse_function_covers(tree) == ["feature-d"]

    def test_function_covers_no_docstring(self):
        source = '''
def test_feature():
    pass
'''
        tree = ast.parse(source)
        assert parse_function_covers(tree) == []

    def test_function_covers_non_test_function(self):
        source = '''
def helper():
    """Covers: feature-e"""
    pass
'''
        tree = ast.parse(source)
        assert parse_function_covers(tree) == []

    def test_function_covers_async_function(self):
        source = '''
async def test_async():
    """Covers: feature-f"""
    pass
'''
        tree = ast.parse(source)
        assert parse_function_covers(tree) == ["feature-f"]


class TestInferCoversFromFunctionNames:
    """Cover infer_covers_from_function_names paths."""

    def test_infer_basic(self):
        source = '''
def test_pipeline_processing():
    pass
'''
        tree = ast.parse(source)
        result = infer_covers_from_function_names(tree)
        assert "pipeline" in result
        assert "processing" in result

    def test_infer_with_stop_words(self):
        source = '''
def test_the_system():
    pass
'''
        tree = ast.parse(source)
        result = infer_covers_from_function_names(tree)
        # "the" and "system" are stop words
        assert result == [] or all(w not in result for w in ["the", "system"])

    def test_infer_empty(self):
        tree = ast.parse("x = 1")
        assert infer_covers_from_function_names(tree) == []

    def test_infer_camel_case(self):
        source = '''
def test_CanProcessData():
    pass
'''
        tree = ast.parse(source)
        result = infer_covers_from_function_names(tree)
        # CamelCase split should yield process and data
        assert "process" in result or "data" in result

    def test_infer_custom_stop_words(self):
        source = '''
def test_flash_write():
    pass
'''
        tree = ast.parse(source)
        result = infer_covers_from_function_names(tree, stop_words={"test", "flash"})
        assert "write" in result
        assert "flash" not in result

    def test_infer_async_function(self):
        source = '''
async def test_async_op():
    pass
'''
        tree = ast.parse(source)
        result = infer_covers_from_function_names(tree)
        assert "async" in result or "op" in result


class TestParseCoversFromFile:
    """Cover parse_covers_from_file paths."""

    def test_parse_from_file_module_covers(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""Covers: module-feature"""\ndef test_x(): pass\n')
            f.flush()
            result = parse_covers_from_file(f.name)
            assert "module-feature" in result
            os.unlink(f.name)

    def test_parse_from_file_comment_covers(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Covers: comment-feature\ndef test_x(): pass\n")
            f.flush()
            result = parse_covers_from_file(f.name)
            assert "comment-feature" in result
            os.unlink(f.name)

    def test_parse_from_file_function_covers(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('def test_x():\n    """Covers: fn-feature"""\n    pass\n')
            f.flush()
            result = parse_covers_from_file(f.name)
            assert "fn-feature" in result
            os.unlink(f.name)

    def test_parse_from_file_syntax_error_fallback(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Covers: syntax-fallback\ninvalid python syntax {{{{\n")
            f.flush()
            result = parse_covers_from_file(f.name)
            assert "syntax-fallback" in result
            os.unlink(f.name)

    def test_parse_from_file_not_found(self):
        result = parse_covers_from_file("/nonexistent/file.py")
        assert result == []

    def test_parse_from_file_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()
            result = parse_covers_from_file(f.name)
            os.unlink(f.name)
            # Empty file has no covers
            assert isinstance(result, list)

    def test_parse_from_file_non_utf8(self):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"\xff\xfe\x00invalid utf-8")
            f.flush()
            result = parse_covers_from_file(f.name)
            assert result == []
            os.unlink(f.name)


class TestCategorizeUncovered:
    """Cover categorize_uncovered paths."""

    def test_critical_shall(self):
        uncovered = [{"shall": "The system SHALL process data", "req_name": "REQ-001"}]
        critical, warn = categorize_uncovered(uncovered)
        assert len(critical) == 1
        assert len(warn) == 0

    def test_non_functional_shall(self):
        uncovered = [{"shall": "The system SHALL support multitenant deployment", "req_name": "REQ-002"}]
        critical, warn = categorize_uncovered(uncovered)
        assert len(critical) == 0
        assert len(warn) == 1

    def test_mixed_categories(self):
        uncovered = [
            {"shall": "SHALL process data", "req_name": "REQ-001"},
            {"shall": "SHALL support SaaS", "req_name": "REQ-002"},
            {"shall": "SHALL handle errors", "req_name": "REQ-003"},
        ]
        critical, warn = categorize_uncovered(uncovered)
        assert len(critical) == 2  # REQ-001 + REQ-003
        assert len(warn) == 1  # REQ-002

    def test_empty_list(self):
        critical, warn = categorize_uncovered([])
        assert critical == []
        assert warn == []

    def test_non_functional_from_req_name(self):
        uncovered = [{"shall": "some text", "req_name": "web-ui-feature"}]
        critical, warn = categorize_uncovered(uncovered)
        assert len(critical) == 0
        assert len(warn) == 1

    def test_multi_keyword_match(self):
        """Test that deployment-related keywords are caught."""
        uncovered = [
            {"shall": "SHALL support deploy in production", "req_name": "REQ-010"},
            {"shall": "SHALL be performant", "req_name": "REQ-011"},
        ]
        critical, warn = categorize_uncovered(uncovered)
        assert len(warn) == 1  # deploy keyword
        assert len(critical) == 1  # performant


class TestStripScenarioRef:
    """Cover _strip_scenario_ref utility."""

    def test_strip_scenario_ref_simple(self):
        result = _strip_scenario_ref("feature-a, Scenario-Ref: REF-100")
        assert "Scenario-Ref" not in result
        assert "feature-a" in result

    def test_strip_scenario_ref_no_ref(self):
        result = _strip_scenario_ref("feature-b, feature-c")
        assert result == "feature-b, feature-c"

    def test_strip_scenario_ref_empty(self):
        result = _strip_scenario_ref("")
        assert result == ""
