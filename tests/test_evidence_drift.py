# @tests src/yuleosh/evidence/drift.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Requirement drift detection tests."""

from yuleosh.evidence.drift import BASELINE_REL, detect_drift


def _rows(**extra):
    rows = [
        {"req_id": "SHALL-1", "statement": "The system SHALL start"},
        {"req_id": "SHALL-2", "statement": "The system SHALL stop"},
    ]
    if extra:
        rows.append(extra)
    return rows


def test_first_run_creates_baseline_without_drift(tmp_path):
    result = detect_drift(tmp_path, _rows())

    assert result["baseline_created"] is True
    assert result["changed"] == []
    assert result["added"] == []
    assert (tmp_path / BASELINE_REL).exists()


def test_changed_statement_is_reported(tmp_path):
    detect_drift(tmp_path, _rows())
    result = detect_drift(
        tmp_path,
        [
            {"req_id": "SHALL-1", "statement": "The system SHALL start quickly"},
            {"req_id": "SHALL-2", "statement": "The system SHALL stop"},
        ],
    )

    assert result["changed"] == ["SHALL-1"]
    assert result["baseline_created"] is False


def test_whitespace_change_is_not_drift(tmp_path):
    detect_drift(tmp_path, _rows())
    result = detect_drift(
        tmp_path,
        [
            {"req_id": "SHALL-1", "statement": "The   system SHALL   start"},
            {"req_id": "SHALL-2", "statement": "The system SHALL stop"},
        ],
    )

    assert result["changed"] == []


def test_added_and_removed_requirements_are_listed(tmp_path):
    detect_drift(tmp_path, _rows())
    result = detect_drift(
        tmp_path,
        [
            {"req_id": "SHALL-1", "statement": "The system SHALL start"},
            {"req_id": "SHALL-3", "statement": "The system SHALL pause"},
        ],
    )

    assert result["added"] == ["SHALL-3"]
    assert result["removed"] == ["SHALL-2"]
    assert result["changed"] == []


def test_env_flag_accepts_new_baseline(tmp_path, monkeypatch):
    detect_drift(tmp_path, _rows())
    monkeypatch.setenv("YULEOSH_ACCEPT_REQ_BASELINE", "1")
    changed_rows = [
        {"req_id": "SHALL-1", "statement": "The system SHALL restart"},
        {"req_id": "SHALL-2", "statement": "The system SHALL stop"},
    ]

    result = detect_drift(tmp_path, changed_rows)
    assert result["baseline_accepted"] is True
    assert result["changed"] == []

    monkeypatch.delenv("YULEOSH_ACCEPT_REQ_BASELINE")
    again = detect_drift(tmp_path, changed_rows)
    assert again["changed"] == []
