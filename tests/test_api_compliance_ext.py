"""Tests for api/compliance.py — Compliance overview API."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from yuleosh.api.compliance import handle_compliance


def test_method_not_allowed():
    """POST returns 405."""
    result, code = handle_compliance("POST", "overview", {}, {}, handler=None)
    assert code == 405


def test_unknown_subpath():
    """GET with unknown subpath returns 404."""
    result, code = handle_compliance("GET", "foobar", {}, {}, handler=None)
    assert code == 404


def test_no_reports(tmp_path):
    """No compliance reports exist."""
    with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
        result, code = handle_compliance("GET", "overview", {}, {}, handler=None)
        assert code == 200
        assert result["data"]["misra_total"] == 0


def test_empty_path_tail(tmp_path):
    """Empty path_tail returns overview."""
    with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
        result, code = handle_compliance("GET", "", {}, {}, handler=None)
        assert code == 200


def test_with_extended_report(tmp_path):
    """Extended compliance report exists."""
    report_dir = tmp_path / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True)
    report_data = {
        "summary": {
            "misra_total": 42, "gscr_mapped": 30, "gscr_mapping_rate": 71.4,
            "s0_count": 10, "s1_count": 20, "s2_count": 12,
            "files_checked": 5, "lines_checked": 1000,
            "violation_density": 0.5, "last_check": None,
        },
        "generated_at": "2025-01-01T00:00:00",
        "top5": [{"rule_id": "R1", "count": 5}],
    }
    (report_dir / "gscr-extended-compliance.json").write_text(json.dumps(report_data))

    with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
        result, code = handle_compliance("GET", "overview", {}, {}, handler=None)
        assert code == 200
        assert result["data"]["misra_total"] == 42


def test_fallback_misra_report(tmp_path):
    """Fallback to misra-report.json."""
    report_dir = tmp_path / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True)
    misra_data = {
        "summary": {
            "total_violations": 10,
            "severity_counts": {"S0": 5, "S1": 3},
            "unique_files": ["a.c"],
            "misra_classification": {"required": 8, "advisory": 2},
        },
        "generated_at": "2025-02-01",
        "groups": [{"rule_id": "R1", "count": 5, "trend": "\u2191"}],
    }
    (report_dir / "misra-report.json").write_text(json.dumps(misra_data))

    with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
        result, code = handle_compliance("GET", "overview", {}, {}, handler=None)
        assert code == 200
        assert result["data"]["misra_total"] == 10
