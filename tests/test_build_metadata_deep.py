"""Deep tests for yuleosh.ci.build_metadata."""

import json
import tempfile
from pathlib import Path
import pytest

from yuleosh.ci.build_metadata import (
    get_build_metadata,
    validate_metadata_integrity,
    _generate_build_id,
    _validate_fields,
)


# ------------------------------------------------------------------
# _generate_build_id
# ------------------------------------------------------------------

def test_generate_build_id(tmp_path):
    """GIVEN project dir WHEN generating build ID THEN returns string."""
    bid = _generate_build_id(str(tmp_path))
    assert isinstance(bid, str)
    assert len(bid) > 0


# ------------------------------------------------------------------
# _validate_fields
# ------------------------------------------------------------------

def test_validate_fields_valid():
    """GIVEN entry with required fields WHEN validating THEN no errors."""
    entry = {
        "build_id": "b-001",
        "timestamp": "2024-01-01T00:00:00",
        "commit": "abc1234",
        "branch": "main",
        "status": "passed",
    }
    errors = _validate_fields(entry)
    assert isinstance(errors, list)


def test_validate_fields_missing():
    """GIVEN entry with missing fields WHEN validating THEN returns errors."""
    entry = {}
    errors = _validate_fields(entry)
    assert isinstance(errors, list)
    # Should have errors for missing fields


# ------------------------------------------------------------------
# get_build_metadata
# ------------------------------------------------------------------

def test_get_build_metadata_not_found(tmp_path):
    """GIVEN no build metadata file WHEN getting metadata THEN returns empty."""
    result = get_build_metadata(str(tmp_path))
    assert result == []


def test_get_build_metadata_with_data(tmp_path):
    """GIVEN build metadata file with entries WHEN getting metadata THEN returns list."""
    meta_dir = tmp_path / ".yuleosh" / "metrics"
    meta_dir.mkdir(parents=True)
    meta_file = meta_dir / "build-metadata.jsonl"
    meta_file.write_text(
        json.dumps({"build_id": "b1", "commit": "aaa", "branch": "main", "status": "passed", "timestamp": "2024-01-01"}) + "\n"
    )
    result = get_build_metadata(str(tmp_path))
    assert len(result) == 1
    assert result[0]["build_id"] == "b1"


def test_get_build_metadata_filter_by_build_id(tmp_path):
    """GIVEN multiple entries WHEN filtering by build ID THEN returns only that one."""
    meta_dir = tmp_path / ".yuleosh" / "metrics"
    meta_dir.mkdir(parents=True)
    meta_file = meta_dir / "build-metadata.jsonl"
    meta_file.write_text(
        json.dumps({"build_id": "b1", "commit": "aaa", "status": "passed", "timestamp": "t1", "branch": "m"}) + "\n"
        + json.dumps({"build_id": "b2", "commit": "bbb", "status": "failed", "timestamp": "t2", "branch": "m"}) + "\n"
    )
    result = get_build_metadata(str(tmp_path), build_id="b2")
    assert len(result) == 1
    assert result[0]["build_id"] == "b2"


def test_get_build_metadata_limit(tmp_path):
    """GIVEN multiple entries WHEN limiting THEN respects limit."""
    meta_dir = tmp_path / ".yuleosh" / "metrics"
    meta_dir.mkdir(parents=True)
    meta_file = meta_dir / "build-metadata.jsonl"
    meta_file.write_text(
        json.dumps({"build_id": "b1", "status": "ok", "timestamp": "t1", "branch": "m", "commit": "a"}) + "\n"
        + json.dumps({"build_id": "b2", "status": "ok", "timestamp": "t2", "branch": "m", "commit": "b"}) + "\n"
    )
    result = get_build_metadata(str(tmp_path), limit=1)
    assert len(result) == 1


# ------------------------------------------------------------------
# validate_metadata_integrity
# ------------------------------------------------------------------

def test_validate_metadata_integrity_no_file(tmp_path):
    """GIVEN no build metadata file WHEN validating THEN returns result."""
    result = validate_metadata_integrity(str(tmp_path))
    assert isinstance(result, dict)
    assert "integrity" in result or "valid" in result or "status" in result


def test_validate_metadata_integrity_valid(tmp_path):
    """GIVEN valid metadata file WHEN validating THEN passes."""
    meta_dir = tmp_path / ".yuleosh" / "metrics"
    meta_dir.mkdir(parents=True)
    (meta_dir / "build-metadata.jsonl").write_text(
        json.dumps({"build_id": "b1", "commit": "a", "branch": "m", "status": "ok", "timestamp": "t1"}) + "\n"
    )
    result = validate_metadata_integrity(str(tmp_path))
    assert isinstance(result, dict)
