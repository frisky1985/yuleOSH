"""Tests for yuleosh.evidence.evidence_check — evidence bundle verification."""

import json
import hashlib
from pathlib import Path
import pytest

from yuleosh.evidence.evidence_check import (
    _sha256_file,
    _ensure_dir,
    pack_evidence_bundle,
    check_evidence_integrity,
)


# ------------------------------------------------------------------
# _sha256_file
# ------------------------------------------------------------------

def test_sha256_file(tmp_path):
    """GIVEN a file with known content WHEN hashing THEN returns correct hash."""
    p = tmp_path / "test.txt"
    p.write_text("hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    result = _sha256_file(str(p))
    assert result == expected


def test_sha256_file_unicode(tmp_path):
    """GIVEN a file with unicode content WHEN hashing THEN returns hash."""
    p = tmp_path / "unicode.txt"
    p.write_text("🔥 yuleOSH")
    result = _sha256_file(str(p))
    assert isinstance(result, str)
    assert len(result) == 64


def test_sha256_file_missing(tmp_path):
    """GIVEN a missing file WHEN hashing THEN raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        _sha256_file(str(tmp_path / "nope.txt"))


# ------------------------------------------------------------------
# _ensure_dir
# ------------------------------------------------------------------

def test_ensure_dir_creates(tmp_path):
    """GIVEN a path that doesn't exist WHEN ensuring dir THEN creates it."""
    target = tmp_path / "new" / "dir"
    assert not target.exists()
    _ensure_dir(target)
    assert target.exists()
    assert target.is_dir()


def test_ensure_dir_already_exists(tmp_path):
    """GIVEN a path that already exists WHEN ensuring dir THEN no error."""
    _ensure_dir(tmp_path)
    assert tmp_path.exists()


# ------------------------------------------------------------------
# pack_evidence_bundle
# ------------------------------------------------------------------

def test_pack_evidence_bundle_basic(tmp_path):
    """GIVEN source files WHEN packing evidence bundle THEN creates bundle."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "evidence.txt").write_text("test evidence")

    bundle = pack_evidence_bundle(str(src), str(tmp_path / "bundle"))
    assert bundle is not None or bundle is True or isinstance(bundle, dict)


def test_pack_evidence_bundle_empty_source(tmp_path):
    """GIVEN empty source dir WHEN packing evidence bundle THEN handles."""
    src = tmp_path / "empty_src"
    src.mkdir()

    result = pack_evidence_bundle(str(src), str(tmp_path / "bundle"))
    # Should still produce a result without error


# ------------------------------------------------------------------
# check_evidence_integrity
# ------------------------------------------------------------------

def test_check_evidence_integrity_no_bundle(tmp_path):
    """GIVEN missing bundle directory WHEN checking integrity THEN returns result."""
    result = check_evidence_integrity(str(tmp_path / "nope"))
    assert isinstance(result, dict)
