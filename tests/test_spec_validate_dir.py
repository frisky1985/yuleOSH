"""Tests for OpenSpec directory aggregation in spec/validate.py."""

# @tests src/yuleosh/spec/validate.py

import pytest
from pathlib import Path

from yuleosh.spec.validate import (
    find_spec_files,
    aggregate_docs,
    validate_spec_dir,
)


def _write_capability(root: Path, cap: str, req_id: str, name: str, shall: str = "work") -> Path:
    """Write a minimal OpenSpec capability spec file."""
    d = root / cap
    d.mkdir(parents=True, exist_ok=True)
    p = d / "spec.md"
    p.write_text(
        f"# {name}\n\n"
        f"## {req_id}: {name}\n\n"
        f"- The system SHALL {shall}\n\n"
        "### Reason\n\nNeeded\n"
    )
    return p


class TestFindSpecFiles:
    def test_capability_layout(self, tmp_path):
        """Finds .osh/specs/<cap>/spec.md files, sorted."""
        specs = tmp_path / ".osh" / "specs"
        _write_capability(specs, "window-control", "SR-001", "Window")
        _write_capability(specs, "light-control", "SR-002", "Light")
        files = find_spec_files(str(specs))
        assert len(files) == 2
        names = [Path(f).parent.name for f in files]
        assert names == ["light-control", "window-control"]  # sorted

    def test_flat_fallback(self, tmp_path):
        """Flat *.md files inside the dir are a fallback."""
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")
        files = find_spec_files(str(tmp_path))
        assert len(files) == 2

    def test_non_dir_returns_empty(self, tmp_path):
        assert find_spec_files(str(tmp_path / "nope")) == []


class TestAggregateDocs:
    def test_merges_requirements(self, tmp_path):
        p1 = _write_capability(tmp_path, "win", "SR-001", "Window")
        p2 = _write_capability(tmp_path, "light", "SR-002", "Light")
        doc = aggregate_docs([str(p1), str(p2)])
        assert len(doc.requirements) == 2
        assert doc.requirements[0].req_id == "SR-001"
        assert doc.requirements[1].req_id == "SR-002"

    def test_duplicate_req_id_raises(self, tmp_path):
        p1 = _write_capability(tmp_path, "a", "SR-001", "A")
        p2 = _write_capability(tmp_path, "b", "SR-001", "B")
        with pytest.raises(ValueError, match="Duplicate requirement ID"):
            aggregate_docs([str(p1), str(p2)])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No spec files"):
            aggregate_docs([])


class TestValidateSpecDir:
    def test_valid_dir(self, tmp_path):
        specs = tmp_path / ".osh" / "specs"
        _write_capability(specs, "win", "SR-001", "Window")
        _write_capability(specs, "light", "SR-002", "Light")
        result = validate_spec_dir(str(specs))
        assert result["requirements"] == 2
        assert result["error_count"] == 0
        assert len(result["files"]) == 2

    def test_empty_dir_errors(self, tmp_path):
        result = validate_spec_dir(str(tmp_path))
        assert result["error_count"] == 1
        assert result["issues"][0]["type"] == "no-spec-files"

    def test_duplicate_id_errors(self, tmp_path):
        specs = tmp_path / "specs"
        _write_capability(specs, "a", "SR-001", "A")
        _write_capability(specs, "b", "SR-001", "B")
        result = validate_spec_dir(str(specs))
        assert result["error_count"] == 1
        assert result["issues"][0]["type"] == "duplicate-req-id"
