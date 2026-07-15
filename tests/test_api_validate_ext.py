"""Tests for api/validate.py — Validation helpers."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.validate import (
    validate_spec_path,
    validate_pagination,
    validate_json_body,
)


class TestApiValidate:
    """Test validation helpers."""

    def test_validate_spec_path_empty(self):
        """Empty path returns error."""
        valid, err = validate_spec_path(None)
        assert valid is False
        assert err is not None

        valid, err = validate_spec_path("")
        assert valid is False

        valid, err = validate_spec_path("  ")
        assert valid is False

    def test_validate_spec_path_traversal(self):
        """Path traversal returns error."""
        valid, err = validate_spec_path("../etc/passwd")
        assert valid is False

        valid, err = validate_spec_path("/absolute/path")
        assert valid is False

    def test_validate_spec_path_bad_extension(self):
        """Bad extension returns error."""
        valid, err = validate_spec_path("spec.txt")
        assert valid is False
        assert "extension" in err.lower()

    def test_validate_spec_path_not_a_file(self):
        """Directory path returns error."""
        # The function uses Path(OSH_HOME) / spec_path, so we need the result
        # of division to return a mock that is not a file
        mock_full = MagicMock()
        mock_full.exists.return_value = True
        mock_full.is_file.return_value = False

        mock_base = MagicMock()
        mock_base.__truediv__.return_value = mock_full

        with patch("yuleosh.api.validate.Path", return_value=mock_base):
            valid, err = validate_spec_path("spec.md")
            assert valid is False

    def test_validate_spec_path_not_exists(self):
        """Non-existing file returns error."""
        mock_full = MagicMock()
        mock_full.exists.return_value = False

        mock_base = MagicMock()
        mock_base.__truediv__.return_value = mock_full

        with patch("yuleosh.api.validate.Path", return_value=mock_base):
            valid, err = validate_spec_path("spec.md")
            assert valid is False

    def test_validate_spec_path_ok(self):
        """Valid path returns success."""
        mock_full = MagicMock()
        mock_full.exists.return_value = True
        mock_full.is_file.return_value = True

        mock_base = MagicMock()
        mock_base.__truediv__.return_value = mock_full

        with patch("yuleosh.api.validate.Path", return_value=mock_base):
            valid, err = validate_spec_path("spec.md")
            assert valid is True
            assert err is None

    def test_validate_pagination_defaults(self):
        """Default pagination is 50/0."""
        result = validate_pagination({})
        assert result["limit"] == 50
        assert result["offset"] == 0

    def test_validate_pagination_custom(self):
        """Custom pagination values work."""
        result = validate_pagination({"limit": ["10"], "offset": ["5"]})
        assert result["limit"] == 10
        assert result["offset"] == 5

    def test_validate_pagination_cap(self):
        """Limit capped at 200."""
        result = validate_pagination({"limit": ["500"]})
        assert result["limit"] == 200

    def test_validate_pagination_invalid(self):
        """Invalid values default."""
        result = validate_pagination({"limit": ["abc"], "offset": ["xyz"]})
        assert result["limit"] == 50
        assert result["offset"] == 0

    def test_validate_pagination_negative(self):
        """Negative values default."""
        result = validate_pagination({"limit": ["-5"], "offset": ["-10"]})
        assert result["limit"] == 50
        assert result["offset"] == 0

    def test_validate_json_body_valid(self):
        """Valid JSON object."""
        valid, err = validate_json_body({"key": "value"})
        assert valid is True
        assert err is None

    def test_validate_json_body_invalid(self):
        """Non-dict returns error."""
        valid, err = validate_json_body([])
        assert valid is False

        valid, err = validate_json_body("string")
        assert valid is False

        valid, err = validate_json_body(None)
        assert valid is False

    def test_validate_spec_path_allowed_extensions(self):
        """All extensions work."""
        for ext in [".md", ".yaml", ".yml", ".json"]:
            mock_full = MagicMock()
            mock_full.exists.return_value = True
            mock_full.is_file.return_value = True

            mock_base = MagicMock()
            mock_base.__truediv__.return_value = mock_full

            with patch("yuleosh.api.validate.Path", return_value=mock_base):
                valid, err = validate_spec_path(f"spec{ext}")
                assert valid is True, f"Failed for {ext}"
