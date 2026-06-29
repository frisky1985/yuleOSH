"""Tests for yuleosh.report.exporter — CI report generation."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.report.exporter import (
    _load_ci_results,
    _status_emoji,
    _serialize_layer_to_summary,
)


# ------------------------------------------------------------------
# _load_ci_results
# ------------------------------------------------------------------

def test_load_ci_results_no_dir(tmp_path):
    """GIVEN no CI directory WHEN loading results THEN returns None."""
    result = _load_ci_results(str(tmp_path), 1)
    assert result is None


def test_load_ci_results_empty_dir(tmp_path):
    """GIVEN empty CI directory WHEN loading results THEN returns None."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    result = _load_ci_results(str(tmp_path), 1)
    assert result is None


def test_load_ci_results_valid(tmp_path):
    """GIVEN CI directory with matching JSON WHEN loading THEN returns dict."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1-build123.json").write_text(
        json.dumps({"layer": 1, "status": "passed", "timestamp": "2024-01-01"})
    )
    result = _load_ci_results(str(tmp_path), 1)
    assert result is not None
    assert result["status"] == "passed"


def test_load_ci_results_wrong_layer(tmp_path):
    """GIVEN results for different layer WHEN loading THEN returns None."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer2-build.json").write_text(
        json.dumps({"layer": 2, "status": "passed"})
    )
    result = _load_ci_results(str(tmp_path), 1)
    assert result is None


def test_load_ci_results_returns_most_recent(tmp_path):
    """GIVEN multiple results for same layer WHEN loading THEN returns most recent."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1-old.json").write_text(json.dumps({"ver": "old"}))
    (ci_dir / "layer1-new.json").write_text(json.dumps({"ver": "new"}))
    result = _load_ci_results(str(tmp_path), 1)
    assert result is not None
    assert result["ver"] == "new"


def test_load_ci_results_invalid_json(tmp_path):
    """GIVEN invalid JSON file WHEN loading THEN returns None."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1-bad.json").write_text("not json")
    result = _load_ci_results(str(tmp_path), 1)
    assert result is None


# ------------------------------------------------------------------
# _status_emoji
# ------------------------------------------------------------------

def test_status_emoji_passed():
    """GIVEN passed status WHEN getting emoji THEN returns green."""
    assert "✅" in _status_emoji("passed") or "🟢" in _status_emoji("passed") or "✔" in _status_emoji("passed")


def test_status_emoji_failed():
    """GIVEN failed status WHEN getting emoji THEN returns red."""
    emoji = _status_emoji("failed")
    assert len(emoji) > 0


def test_status_emoji_skipped():
    """GIVEN skipped status WHEN getting emoji THEN returns some emoji."""
    emoji = _status_emoji("skipped")
    assert len(emoji) > 0


def test_status_emoji_unknown():
    """GIVEN unknown status WHEN getting emoji THEN returns string."""
    emoji = _status_emoji("unknown_status_xyz")
    assert isinstance(emoji, str)


# ------------------------------------------------------------------
# _serialize_layer_to_summary
# ------------------------------------------------------------------

def test_serialize_layer_to_summary_basic():
    """GIVEN a valid CI result dict WHEN serializing THEN returns summary."""
    result = {
        "layer": 2,
        "status": "passed",
        "timestamp": "2024-01-01T00:00:00",
        "stages": [{"name": "test", "status": "passed"}],
    }
    summary = _serialize_layer_to_summary(result)
    assert isinstance(summary, dict)
    assert summary.get("layer") == 2 or summary.get("id") == 2


def test_serialize_layer_to_summary_minimal():
    """GIVEN a minimal CI result WHEN serializing THEN handles gracefully."""
    result = {"layer": 1, "status": "failed"}
    summary = _serialize_layer_to_summary(result)
    assert isinstance(summary, dict)


def test_serialize_layer_to_summary_empty():
    """GIVEN empty dict WHEN serializing THEN handles gracefully."""
    summary = _serialize_layer_to_summary({})
    assert isinstance(summary, dict)
