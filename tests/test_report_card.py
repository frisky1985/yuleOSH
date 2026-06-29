"""Tests for yuleosh.report.card_generator — quality card generation."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.report.card_generator import (
    _load_json,
    _load_jsonl_latest,
    _format_delta,
    generate_quality_card,
    generate_feishu_card_json,
)


# ------------------------------------------------------------------
# _format_delta
# ------------------------------------------------------------------

def test_format_delta_improvement():
    """GIVEN improvement in metric WHEN formatting delta THEN shows green up."""
    result = _format_delta(80.0, 70.0, higher_is_better=True)
    assert "🟢" in result
    assert "%" in result


def test_format_delta_decline():
    """GIVEN decline in metric WHEN formatting delta THEN shows red down."""
    result = _format_delta(60.0, 80.0, higher_is_better=True)
    assert "🔴" in result


def test_format_delta_no_change():
    """GIVEN no change in metric WHEN formatting delta THEN shows arrow."""
    result = _format_delta(70.0, 70.0, higher_is_better=True)
    assert result == "→"


def test_format_delta_lower_is_better():
    """GIVEN lower-is-better metric WHEN improving THEN shows green."""
    result = _format_delta(10.0, 20.0, higher_is_better=False)
    assert "🟢" in result


def test_format_delta_high_delta():
    """GIVEN large delta WHEN formatting THEN shows percentage."""
    result = _format_delta(200.0, 10.0, higher_is_better=True)
    assert "%" in result


# ------------------------------------------------------------------
# _load_json
# ------------------------------------------------------------------

def test_load_json_valid(tmp_path):
    """GIVEN valid JSON file WHEN loading THEN returns dict."""
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"score": 85}))
    result = _load_json(p)
    assert result == {"score": 85}


def test_load_json_missing(tmp_path):
    """GIVEN missing file WHEN loading THEN returns None."""
    result = _load_json(tmp_path / "nope.json")
    assert result is None


def test_load_json_invalid(tmp_path):
    """GIVEN invalid JSON WHEN loading THEN returns None."""
    p = tmp_path / "bad.json"
    p.write_text("not json")
    result = _load_json(p)
    assert result is None


# ------------------------------------------------------------------
# _load_jsonl_latest
# ------------------------------------------------------------------

def test_load_jsonl_latest_valid(tmp_path):
    """GIVEN JSONL file with entries WHEN loading latest THEN returns last."""
    p = tmp_path / "data.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}\n')
    result = _load_jsonl_latest(p)
    assert result == {"a": 2}


def test_load_jsonl_latest_empty(tmp_path):
    """GIVEN empty JSONL file WHEN loading latest THEN returns None."""
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    result = _load_jsonl_latest(p)
    assert result is None


def test_load_jsonl_latest_missing(tmp_path):
    """GIVEN missing JSONL file WHEN loading latest THEN returns None."""
    result = _load_jsonl_latest(tmp_path / "nope.jsonl")
    assert result is None


# ------------------------------------------------------------------
# generate_quality_card
# ------------------------------------------------------------------

def test_generate_quality_card_basic(tmp_path):
    """GIVEN project with metrics WHEN generating quality card THEN returns markdown string."""
    (tmp_path / ".osh").mkdir(parents=True, exist_ok=True)
    (tmp_path / "spec.md").write_text("# Spec\n")
    result = generate_quality_card(str(tmp_path))
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_quality_card_no_osh(tmp_path):
    """GIVEN project without .osh directory WHEN generating THEN handles gracefully."""
    result = generate_quality_card(str(tmp_path))
    assert isinstance(result, str)


# ------------------------------------------------------------------
# generate_feishu_card_json
# ------------------------------------------------------------------

def test_generate_feishu_card_json(tmp_path):
    """GIVEN project path WHEN generating feishu card THEN returns result."""
    result = generate_feishu_card_json(str(tmp_path))
    assert isinstance(result, (dict, str))
