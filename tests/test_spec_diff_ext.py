"""Tests for spec/diff.py — Spec diff CLI and helpers."""

import pytest
import json
from unittest.mock import patch, MagicMock
from yuleosh.spec.diff import main, _print_human


class TestSpecDiff:
    """Test spec diff module."""

    @patch("yuleosh.spec.diff.diff_specs")
    @patch("yuleosh.spec.diff.sys.argv", ["diff.py", "old.md", "new.md"])
    def test_main_human(self, mock_diff_specs):
        """CLI main prints human-readable diff."""
        mock_diff_specs.return_value = {
            "old": "old.md",
            "new": "new.md",
            "total_changes": 0,
            "added_count": 0,
            "removed_count": 0,
            "modified_count": 0,
            "status_changed_count": 0,
            "added_requirements": [],
            "removed_requirements": [],
            "modified_requirements": [],
            "status_changed": [],
            "impact_analysis": {},
        }
        # Should not raise
        main()

    @patch("yuleosh.spec.diff.diff_specs")
    @patch("yuleosh.spec.diff.sys.argv", ["diff.py", "old.md", "new.md", "--json"])
    def test_main_json(self, mock_diff_specs):
        """CLI main with --json flag."""
        mock_diff_specs.return_value = {"old": "old.md", "new": "new.md", "total_changes": 0}
        main()

    @patch("yuleosh.spec.diff.diff_specs")
    @patch("yuleosh.spec.diff.sys.argv", ["diff.py", "old.md", "new.md"])
    def test_main_exception(self, mock_diff_specs):
        """CLI main when diff raises."""
        mock_diff_specs.side_effect = Exception("Parse error")
        with pytest.raises(SystemExit):
            main()

    @patch("yuleosh.spec.diff.sys.argv", ["diff.py"])
    def test_main_no_args(self):
        """CLI main without args exits with error."""
        with pytest.raises(SystemExit):
            main()

    def test_print_human_with_impact(self):
        """_print_human handles impact analysis."""
        delta = {
            "old": "old.md",
            "new": "new.md",
            "total_changes": 5,
            "added_count": 2,
            "removed_count": 1,
            "modified_count": 1,
            "status_changed_count": 1,
            "added_requirements": ["RS-003", "RS-004"],
            "removed_requirements": ["RS-001"],
            "modified_requirements": [{
                "name": "RS-002",
                "req_id": "RS-002",
                "changes": [
                    "+ SHALL something",
                    "- SHALL something else",
                ]
            }],
            "status_changed": [{
                "name": "RS-002",
                "req_id": "RS-002",
                "old_status": "PROPOSED",
                "new_status": "APPROVED",
            }],
            "impact_analysis": {
                "affected_requirements": ["RS-001", "RS-002"],
                "affected_children": ["SWR-002.1"],
                "affected_scenarios": ["Test Flow"],
                "affected_architecture_components": ["runner"],
                "recommended_actions": ["Update tests"],
                "action_count": 1,
            },
        }
        # Should not raise
        _print_human(delta)

    def test_print_human_empty_impact(self):
        """_print_human without impact analysis."""
        delta = {
            "old": "old.md",
            "new": "new.md",
            "total_changes": 0,
            "added_count": 0,
            "removed_count": 0,
            "modified_count": 0,
            "status_changed_count": 0,
            "added_requirements": [],
            "removed_requirements": [],
            "modified_requirements": [],
            "status_changed": [],
            "impact_analysis": {},
        }
        _print_human(delta)
