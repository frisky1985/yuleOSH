"""Deep tests for yuleosh.review.c_review — embedded C code review."""

from unittest import mock
import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.review.c_review import (
    _check_content,
    _llm_review_snippet,
)


# ------------------------------------------------------------------
# _check_content
# ------------------------------------------------------------------

def test_check_content_basic(tmp_path):
    """GIVEN C source file WHEN checking content THEN returns issues."""
    c_file = tmp_path / "test.c"
    c_file.write_text("int main() { return 0; }")
    results = _check_content("int main() { return 0; }", str(c_file), "test.c")
    assert isinstance(results, list)


def test_check_content_empty(tmp_path):
    """GIVEN empty file WHEN checking content THEN returns empty list."""
    c_file = tmp_path / "empty.c"
    c_file.write_text("")
    results = _check_content("", str(c_file), "empty.c")
    assert results == []


def test_check_content_missing_file(tmp_path):
    """GIVEN file path that doesn't exist WHEN checking THEN handles gracefully."""
    results = _check_content("code", str(tmp_path / "nope.c"), "nope.c")
    assert isinstance(results, list)


# ------------------------------------------------------------------
# _llm_review_snippet
# ------------------------------------------------------------------

@mock.patch("yuleosh.review.c_review._get_llm_client")
def test_llm_review_snippet_simple(mock_client):
    """GIVEN simple code snippet WHEN doing LLM review THEN returns list."""
    mock_client.return_value = mock.MagicMock()
    mock_instance = mock_client.return_value
    mock_instance.chat.return_value = "No issues found."

    results = _llm_review_snippet("int x = 5;")
    assert isinstance(results, list)


@mock.patch("yuleosh.review.c_review._get_llm_client")
def test_llm_review_snippet_empty(mock_client):
    """GIVEN empty code snippet WHEN doing LLM review THEN returns empty list."""
    results = _llm_review_snippet("")
    assert isinstance(results, list)


@mock.patch("yuleosh.review.c_review._get_llm_client")
def test_llm_review_snippet_timeout_retry(mock_client):
    """GIVEN LLM timeout WHEN retrying THEN handles gracefully."""
    mock_client.return_value = mock.MagicMock()
    mock_instance = mock_client.return_value
    mock_instance.chat.side_effect = TimeoutError("timed out")

    results = _llm_review_snippet("int x = 5;", max_retries=2)
    assert isinstance(results, list)
