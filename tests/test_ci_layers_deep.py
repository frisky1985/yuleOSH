"""Deep tests for yuleosh.ci.layers — CI layer orchestration."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.ci.layers import (
    get_latest_layer_result,
    check_layer_dependency,
)


def test_get_latest_layer_result_no_ci_dir(tmp_path):
    """GIVEN missing .osh/ci dir WHEN getting result THEN returns None."""
    result = get_latest_layer_result(1, str(tmp_path))
    assert result is None


def test_get_latest_layer_result_empty_ci_dir(tmp_path):
    """GIVEN empty .osh/ci dir WHEN getting result THEN returns None."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    result = get_latest_layer_result(1, str(tmp_path))
    assert result is None


def test_get_latest_layer_result_with_json(tmp_path):
    """GIVEN .osh/ci dir with layer result WHEN getting result THEN returns dict."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1-20240101.json").write_text(
        json.dumps({"layer": 1, "status": "passed", "timestamp": "2024-01-01"})
    )
    result = get_latest_layer_result(1, str(tmp_path))
    assert result is not None
    assert result["layer"] == 1
    assert result["status"] == "passed"


def test_get_latest_layer_result_multi_layer(tmp_path):
    """GIVEN multiple layer results WHEN getting specific layer THEN returns correct."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer2-20240101.json").write_text(
        json.dumps({"layer": 2, "status": "failed"})
    )
    (ci_dir / "layer1-20240102.json").write_text(
        json.dumps({"layer": 1, "status": "passed"})
    )
    result = get_latest_layer_result(1, str(tmp_path))
    assert result is not None
    assert result["layer"] == 1


def test_get_latest_layer_result_returns_most_recent(tmp_path):
    """GIVEN multiple results for same layer WHEN getting THEN returns most recent."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1-20240101.json").write_text(json.dumps({"ver": "old"}))
    (ci_dir / "layer1-20240102.json").write_text(json.dumps({"ver": "new"}))
    result = get_latest_layer_result(1, str(tmp_path))
    assert result is not None
    assert result["ver"] == "new"


# ------------------------------------------------------------------
# check_layer_dependency
# ------------------------------------------------------------------

def test_check_layer_dependency_no_data():
    """GIVEN no CI data WHEN checking dependency THEN returns None or str."""
    with tempfile.TemporaryDirectory() as d:
        result = check_layer_dependency(1, d)
    assert result is None or isinstance(result, str)
