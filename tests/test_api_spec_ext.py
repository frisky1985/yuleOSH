"""Tests for api/spec.py — Spec validate/diff endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.spec import handle_spec


class TestApiSpec:
    """Test spec endpoint."""

    def test_unknown_resource(self):
        """Unknown spec resource returns 404."""
        result, code = handle_spec("GET", "unknown", {}, {})
        assert code == 404

    def test_validate_no_path(self):
        """POST without path returns 400."""
        result, code = handle_spec("POST", "validate", {}, {})
        assert code == 400

    def test_validate_file_not_found(self):
        """POST with non-existing file returns 400."""
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = False

        with patch("yuleosh.api.spec.Path", return_value=mock_path):
            result, code = handle_spec(
                "POST", "validate", {"path": "/tmp/nonexistent.md"}, {}
            )
            assert code == 400

    def test_validate_get_method(self):
        """GET request returns 405."""
        result, code = handle_spec("GET", "validate", {}, {})
        assert code == 405

    @patch("yuleosh.spec.validate.validate_spec")
    @patch("yuleosh.spec.validate.parse_spec")
    def test_validate_success(self, mock_parse, mock_validate):
        """POST /spec/validate returns validation result."""
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True

        mock_doc = MagicMock()
        mock_doc.requirements = [MagicMock(shall=["shall1"])]
        mock_doc.scenarios = [MagicMock()]
        mock_parse.return_value = mock_doc
        mock_validate.return_value = []

        with patch("yuleosh.api.spec.Path", return_value=mock_path):
            result, code = handle_spec(
                "POST", "validate", {"path": "/tmp/test.md"}, {}
            )
            assert code == 200
            assert result["data"]["issue_count"] == 0

    def test_diff_no_paths(self):
        """POST without old/new returns 400."""
        result, code = handle_spec("POST", "diff", {}, {})
        assert code == 400

    def test_diff_get_method(self):
        """GET request returns 405."""
        result, code = handle_spec("GET", "diff", {}, {})
        assert code == 405

    def test_diff_old_not_found(self):
        """POST with non-existing old file returns 400."""
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.side_effect = [False, True]  # old not found, new found

        with patch("yuleosh.api.spec.Path", return_value=mock_path):
            result, code = handle_spec(
                "POST", "diff", {"old": "/tmp/old.md", "new": "/tmp/new.md"}, {}
            )
            assert code == 400

    @patch("yuleosh.spec.validate.diff_specs")
    def test_diff_success(self, mock_diff_specs):
        """POST /spec/diff returns diff result."""
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True

        mock_diff_specs.return_value = {
            "old": "old.md", "new": "new.md", "total_changes": 0,
        }

        with patch("yuleosh.api.spec.Path", return_value=mock_path):
            result, code = handle_spec(
                "POST", "diff", {"old": "/tmp/old.md", "new": "/tmp/new.md"}, {}
            )
            assert code == 200
            assert "old" in result["data"]
