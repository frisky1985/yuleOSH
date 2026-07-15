"""Tests for pipeline/orchestrator.py — focused on mock_llm and status."""

from unittest.mock import patch, MagicMock
import pytest
from yuleosh.pipeline.orchestrator import _mock_llm_client, status_pipeline


def test_mock_llm_client():
    """_mock_llm_client returns a working mock client."""
    client = _mock_llm_client()
    result = client("system prompt", "user prompt", max_tokens=100)
    assert "content" in result
    assert result["model"] == "mock-mode"
    assert result["usage"]["total_tokens"] == 1500
    assert result["usage"]["prompt_tokens"] == 1000
    assert result["usage"]["completion_tokens"] == 500


def test_mock_llm_client_extra_kwargs():
    """Mock LLM client ignores extra kwargs."""
    client = _mock_llm_client()
    result = client("sys", "usr", temperature=0.5, max_tokens=200)
    assert result["model"] == "mock-mode"


@patch("yuleosh.pipeline.orchestrator.Path")
def test_status_pipeline_no_sessions(mock_path_cls):
    """status_pipeline with no sessions."""
    mock_base = MagicMock()
    mock_path_cls.return_value = mock_base
    mock_base.__truediv__.return_value.__truediv__.return_value = MagicMock()
    mock_base.__truediv__.return_value.__truediv__.return_value.exists.return_value = False

    status_pipeline("session-1")  # should not raise


@patch("yuleosh.pipeline.orchestrator.Path")
def test_status_pipeline_list_all(mock_path_cls):
    """status_pipeline lists all sessions."""
    mock_base = MagicMock()
    mock_path_cls.return_value = mock_base
    mock_osh = MagicMock()
    mock_base.__truediv__.return_value = mock_osh
    mock_sessions = MagicMock()
    mock_osh.__truediv__.return_value = mock_sessions

    mock_dir = MagicMock()
    mock_dir.name = "s1"
    mock_dir.is_dir.return_value = True
    mock_sessions.iterdir.return_value = [mock_dir]

    mock_sfile = MagicMock()
    mock_sfile.exists.return_value = True
    mock_sfile.read_text.return_value = (
        '{"status": "completed", "steps": [{"status": "completed"}]}'
    )
    mock_dir.__truediv__.return_value = mock_sfile

    status_pipeline(None)
