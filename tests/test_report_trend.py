"""Tests for yuleosh.report.trend_exporter — trend data export."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.report.trend_exporter import (
    _load_jsonl,
    _safe_float,
    _safe_int,
    _normalize_timestamp,
    export_misra_trend,
    export_ut_trend,
    export_trend_for_project,
)


# ------------------------------------------------------------------
# _load_jsonl
# ------------------------------------------------------------------

def test_load_jsonl_valid(tmp_path):
    """GIVEN valid JSONL file WHEN loading THEN returns list of dicts."""
    p = tmp_path / "data.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n')
    result = _load_jsonl(p)
    assert len(result) == 3
    assert result[-1]["a"] == 3


def test_load_jsonl_empty(tmp_path):
    """GIVEN empty JSONL file WHEN loading THEN returns empty list."""
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    result = _load_jsonl(p)
    assert result == []


def test_load_jsonl_missing(tmp_path):
    """GIVEN missing file WHEN loading THEN returns empty list."""
    result = _load_jsonl(tmp_path / "nope.jsonl")
    assert result == []


def test_load_jsonl_partial_invalid(tmp_path):
    """GIVEN JSONL with some invalid lines WHEN loading THEN skips bad lines."""
    p = tmp_path / "mixed.jsonl"
    p.write_text('{"ok": 1}\nnot json\n{"ok": 2}\n')
    result = _load_jsonl(p)
    assert len(result) == 2


# ------------------------------------------------------------------
# _safe_float / _safe_int
# ------------------------------------------------------------------

def test_safe_float_valid():
    """GIVEN valid number WHEN converting to float THEN returns float."""
    assert _safe_float("42.5") == 42.5
    assert _safe_float(42) == 42.0


def test_safe_float_invalid():
    """GIVEN invalid input WHEN converting to float THEN returns 0.0."""
    assert _safe_float("abc") == 0.0
    assert _safe_float(None) == 0.0


def test_safe_int_valid():
    """GIVEN valid number WHEN converting to int THEN returns int."""
    assert _safe_int("42") == 42
    assert _safe_int(42.9) == 42


def test_safe_int_invalid():
    """GIVEN invalid input WHEN converting to int THEN returns 0."""
    assert _safe_int("abc") == 0
    assert _safe_int(None) == 0


# ------------------------------------------------------------------
# _normalize_timestamp
# ------------------------------------------------------------------

def test_normalize_timestamp_iso():
    """GIVEN ISO timestamp WHEN normalizing THEN returns readable format."""
    result = _normalize_timestamp("2024-06-16T10:30:00")
    assert "2024" in result
    assert "06" in result or "6月" in result or "Jun" in result


def test_normalize_timestamp_unix():
    """GIVEN unix timestamp string WHEN normalizing THEN handles."""
    result = _normalize_timestamp("1718535000")
    assert isinstance(result, str)


def test_normalize_timestamp_empty():
    """GIVEN empty string WHEN normalizing THEN returns empty."""
    result = _normalize_timestamp("")
    assert result == ""


# ------------------------------------------------------------------
# export_misra_trend (mock-based)
# ------------------------------------------------------------------

def test_export_misra_trend_empty(tmp_path):
    """GIVEN empty project WHEN exporting misra trend THEN returns dict."""
    result = export_misra_trend(str(tmp_path))
    assert isinstance(result, dict)
    assert "report_type" in result
    assert result["report_type"] == "misra"


def test_export_ut_trend_empty(tmp_path):
    """GIVEN empty project WHEN exporting UT trend THEN returns dict."""
    result = export_ut_trend(str(tmp_path))
    assert isinstance(result, dict)
    assert result["report_type"] == "ut"


def test_export_trend_for_project_empty(tmp_path):
    """GIVEN empty project WHEN exporting trend THEN returns dict."""
    result = export_trend_for_project(str(tmp_path), "misra")
    assert isinstance(result, dict)
