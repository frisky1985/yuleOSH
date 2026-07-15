"""Tests for api/compliance.py — Compliance overview API."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from yuleosh.api.compliance import handle_compliance


def test_method_not_allowed():
    """POST returns 405."""
    result, code = handle_compliance("POST", "overview", {}, {}, None)
    assert code == 405


def test_unknown_subpath():
    """GET with unknown subpath returns 404."""
    result, code = handle_compliance("GET", "foobar", {}, {}, None)
    assert code == 404


def test_no_reports(tmp_path):
    """No compliance reports exist - uses Path() for OSH_HOME."""
    with patch("yuleosh.api.compliance.Path") as mock_path_cls:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path
        result, code = handle_compliance("GET", "overview", {}, {}, None)
        assert code == 200
        assert result["data"]["misra_total"] == 0


def test_empty_path_tail(tmp_path):
    """Empty path_tail returns overview."""
    with patch("yuleosh.api.compliance.Path") as mock_path_cls:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path
        result, code = handle_compliance("GET", "", {}, {}, None)
        assert code == 200


def test_with_extended_report(tmp_path):
    """Extended compliance report exists."""
    def path_side_effect(*args):
        p = MagicMock()
        arg0 = str(args[0]) if args else ""
        if "gscr-extended-compliance" in arg0:
            p.exists.return_value = True
            p.read_text.return_value = json.dumps({
                "summary": {
                    "misra_total": 42, "gscr_mapped": 30, "gscr_mapping_rate": 71.4,
                    "s0_count": 10, "s1_count": 20, "s2_count": 12,
                    "files_checked": 5, "lines_checked": 1000,
                    "violation_density": 0.5, "last_check": None,
                },
                "generated_at": "2025-01-01T00:00:00",
                "top5": [{"rule_id": "R1", "count": 5}],
            })
        elif "misra-report" in arg0:
            p.exists.return_value = False
        else:
            p.exists.return_value = False
        return p

    with patch("yuleosh.api.compliance.Path", side_effect=path_side_effect):
        result, code = handle_compliance("GET", "overview", {}, {}, None)
        assert code == 200
        assert result["data"]["misra_total"] == 42


def test_fallback_misra_report(tmp_path):
    """Fallback to misra-report.json."""
    call_count = 0

    def path_side_effect(*args):
        p = MagicMock()
        arg0 = str(args[0]) if args else ""
        if "gscr-extended-compliance" in arg0:
            p.exists.return_value = False
        elif "misra-report" in arg0:
            p.exists.return_value = True
            p.read_text.return_value = json.dumps({
                "summary": {
                    "total_violations": 10,
                    "severity_counts": {"S0": 5, "S1": 3},
                    "unique_files": ["a.c"],
                    "misra_classification": {"required": 8, "advisory": 2},
                },
                "generated_at": "2025-02-01",
                "groups": [{"rule_id": "R1", "count": 5, "trend": "↑"}],
            })
        else:
            p.exists.return_value = False
        return p

    with patch("yuleosh.api.compliance.Path", side_effect=path_side_effect):
        result, code = handle_compliance("GET", "overview", {}, {}, None)
        assert code == 200
        assert result["data"]["misra_total"] == 10
