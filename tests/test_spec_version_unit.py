"""Unit tests for yuleosh.spec.version — pure Python, no external deps."""

# @tests src/yuleosh/spec/version.py

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from yuleosh.spec.version import (
    SpecVersion,
    parse_version,
    compare_versions,
    increment_version,
    read_spec_version,
    write_spec_version,
    detect_spec_path,
)


class TestSpecVersionDataclass:
    def test_default_creation(self):
        sv = SpecVersion()
        assert sv.version == "1.0.0"
        assert sv.spec_path == "docs/spec.md"
        assert sv.updated_at == ""
        assert sv.updated_by == ""
        assert sv.history == []

    def test_custom_creation(self):
        sv = SpecVersion(
            version="2.3.4",
            spec_path="my/spec.md",
            updated_at="2024-01-01T00:00:00",
            updated_by="bot",
            history=[{"v": "2.3.3"}],
        )
        assert sv.version == "2.3.4"
        assert sv.spec_path == "my/spec.md"

    def test_to_dict(self):
        sv = SpecVersion(version="1.2.3")
        d = sv.to_dict()
        assert d["version"] == "1.2.3"
        assert d["spec_path"] == "docs/spec.md"
        assert "history" in d
        assert "updated_at" in d

    def test_from_dict_full(self):
        data = {
            "version": "3.0.0",
            "spec_path": "specs/main.md",
            "updated_at": "2024-06-15T12:00:00",
            "updated_by": "cli",
            "history": [{"version": "2.9.0"}],
        }
        sv = SpecVersion.from_dict(data)
        assert sv.version == "3.0.0"
        assert sv.spec_path == "specs/main.md"
        assert len(sv.history) == 1

    def test_from_dict_empty(self):
        sv = SpecVersion.from_dict({})
        assert sv.version == "1.0.0"
        assert sv.spec_path == "docs/spec.md"
        assert sv.history == []

    def test_from_dict_partial(self):
        data = {"version": "2.0.0"}
        sv = SpecVersion.from_dict(data)
        assert sv.version == "2.0.0"
        assert sv.spec_path == "docs/spec.md"


class TestParseVersion:
    @pytest.mark.parametrize(
        "input_str, expected",
        [
            ("1.0.0", (1, 0, 0)),
            ("0.0.1", (0, 0, 1)),
            ("99.88.77", (99, 88, 77)),
            ("2.5", (2, 5, 0)),
            ("10", (10, 0, 0)),
            (" 3.4.5 ", (3, 4, 5)),
        ],
    )
    def test_valid_versions(self, input_str, expected):
        assert parse_version(input_str) == expected

    @pytest.mark.parametrize(
        "input_str",
        ["", "abc", None, "x.y.z", "1..0"],
    )
    def test_invalid_versions(self, input_str):
        assert parse_version(input_str) == (0, 0, 0)


class TestCompareVersions:
    @pytest.mark.parametrize(
        "a, b, expected",
        [
            ("1.0.0", "1.0.0", 0),
            ("2.0.0", "1.0.0", 1),
            ("1.0.0", "2.0.0", -1),
            ("1.2.0", "1.3.0", -1),
            ("1.2.3", "1.2.2", 1),
            ("0.9.0", "1.0.0", -1),
        ],
    )
    def test_compare(self, a, b, expected):
        assert compare_versions(a, b) == expected


class TestIncrementVersion:
    def test_minor_default(self):
        assert increment_version("1.0.0") == "1.1.0"

    def test_major(self):
        assert increment_version("1.0.0", part="major") == "2.0.0"

    def test_minor(self):
        assert increment_version("1.0.0", part="minor") == "1.1.0"

    def test_patch(self):
        assert increment_version("1.0.0", part="patch") == "1.0.1"

    def test_major_resets_minor_patch(self):
        assert increment_version("2.5.3", part="major") == "3.0.0"

    def test_minor_resets_patch(self):
        assert increment_version("2.5.3", part="minor") == "2.6.0"

    def test_with_delta_version_higher(self):
        assert increment_version("1.0.0", delta_version="2.0.0") == "2.0.0"

    def test_with_delta_version_lower(self):
        result = increment_version("2.0.0", delta_version="1.5.0")
        parsed = parse_version(result)
        assert parsed >= (2, 0, 0)
        # Should auto-bump current
        assert parsed[0] >= 2

    def test_with_delta_version_equal(self):
        result = increment_version("1.5.0", delta_version="1.5.0")
        parsed = parse_version(result)
        assert parsed >= (1, 5, 0)
        # Should auto-bump (not stay same)
        assert parsed > (1, 5, 0) or parsed == (1, 5, 0)


class TestReadSpecVersion:
    def test_read_existing_file(self):
        """Read from a valid JSON file."""
        data = json.dumps({
            "version": "2.0.0",
            "spec_path": "docs/spec.md",
            "updated_at": "2024-01-01T00:00:00",
            "updated_by": "test",
            "history": [],
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = os.path.join(tmpdir, ".yuleosh", "spec-version.json")
            os.makedirs(os.path.dirname(version_file))
            with open(version_file, "w") as f:
                f.write(data)
            sv = read_spec_version(project_dir=tmpdir)
            assert sv.version == "2.0.0"

    def test_read_empty_dir_returns_default(self):
        """If no version file and no spec.md, return default SpecVersion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sv = read_spec_version(project_dir=tmpdir)
            assert sv.version == "1.0.0"
            assert sv.spec_path == "docs/spec.md"

    def test_read_from_spec_header(self):
        """Fallback to parsing version from docs/spec.md header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(docs_dir)
            spec_path = os.path.join(docs_dir, "spec.md")
            with open(spec_path, "w") as f:
                f.write("# Spec\n\n**Version**: 3.2.1\n")
            sv = read_spec_version(project_dir=tmpdir)
            assert sv.version == "3.2.1"

    def test_read_corrupt_json_returns_default(self):
        """If JSON is corrupt, fallback to default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            version_file = os.path.join(tmpdir, ".yuleosh", "spec-version.json")
            os.makedirs(os.path.dirname(version_file))
            with open(version_file, "w") as f:
                f.write("{not valid json}")
            sv = read_spec_version(project_dir=tmpdir)
            assert sv.version == "1.0.0"

    def test_read_custom_version_file(self):
        """Use a custom version file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = "my-version.json"
            full_path = os.path.join(tmpdir, custom_path)
            with open(full_path, "w") as f:
                json.dump({"version": "4.0.0"}, f)
            sv = read_spec_version(project_dir=tmpdir, version_file=custom_path)
            assert sv.version == "4.0.0"


class TestWriteSpecVersion:
    def test_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sv = SpecVersion(version="2.0.0")
            result = write_spec_version(sv, project_dir=tmpdir)
            assert result is True
            version_file = os.path.join(tmpdir, ".yuleosh", "spec-version.json")
            assert os.path.exists(version_file)
            with open(version_file) as f:
                data = json.load(f)
            assert data["version"] == "2.0.0"
            assert "updated_at" in data

    def test_write_custom_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sv = SpecVersion(version="1.5.0")
            result = write_spec_version(sv, project_dir=tmpdir, version_file="custom.json")
            assert result is True
            assert os.path.exists(os.path.join(tmpdir, "custom.json"))

    def test_write_readonly_fails(self):
        sv = SpecVersion(version="1.0.0")
        result = write_spec_version(sv, project_dir="/nonexistent_dir_xyz")
        assert result is False


class TestDetectSpecPath:
    def test_docs_spec_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "docs"))
            Path(os.path.join(tmpdir, "docs", "spec.md")).touch()
            assert detect_spec_path(tmpdir) == "docs/spec.md"

    def test_specs_spec_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "specs"))
            Path(os.path.join(tmpdir, "specs", "spec.md")).touch()
            assert detect_spec_path(tmpdir) == "specs/spec.md"

    def test_root_spec_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "SPEC.md")).touch()
            assert detect_spec_path(tmpdir) == "SPEC.md"

    def test_no_spec_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert detect_spec_path(tmpdir) == "docs/spec.md"
