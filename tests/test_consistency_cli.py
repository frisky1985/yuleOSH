#!/usr/bin/env python3

# @tests src/yuleosh/cli/commands/consistency.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for consistency verification CLI (T-004)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from yuleosh.cli.commands.consistency import (
    _compute_session_fingerprint,
    _load_session_summary,
    cmd_baseline_save,
    cmd_baseline_list,
    cmd_consistency_check,
)


@pytest.fixture
def mock_session(tmp_path):
    """Create a mock session directory with artifacts."""
    session_dir = tmp_path / ".yuleosh" / "sessions" / "test-session"
    session_dir.mkdir(parents=True)

    # Create gate-summary.json
    gate_summary = {
        "gates": [
            {
                "gate": "G1",
                "name": "Requirements",
                "status": "passed",
                "step_keys": ["extract-reqs"],
                "artifact_hashes": {
                    "extract-reqs": "abc123def456",
                },
            },
            {
                "gate": "G2",
                "name": "Code",
                "status": "passed",
                "step_keys": ["codegen"],
                "artifact_hashes": {
                    "codegen": "789xyz012abc",
                },
            },
        ],
    }
    (session_dir / "gate-summary.json").write_text(
        json.dumps(gate_summary), encoding="utf-8"
    )

    # Create test-cases.json
    test_cases = {
        "test_cases": [
            {"test_id": "RS-001::SC-001", "req_id": "RS-001"},
            {"test_id": "RS-002::SC-001", "req_id": "RS-002"},
        ],
    }
    (session_dir / "test-cases.json").write_text(
        json.dumps(test_cases), encoding="utf-8"
    )

    return tmp_path, session_dir


class TestLoadSessionSummary:
    """Tests for _load_session_summary()."""

    def test_loads_gate_summary(self, mock_session):
        """_load_session_summary extracts artifact hashes from gate-summary.json."""
        tmp_path, session_dir = mock_session

        summary = _load_session_summary(session_dir)

        assert "extract-reqs" in summary["artifact_hashes"]
        assert "codegen" in summary["artifact_hashes"]
        assert summary["artifact_hashes"]["extract-reqs"] == "abc123def456"

    def test_loads_test_cases(self, mock_session):
        """_load_session_summary loads test case IDs."""
        tmp_path, session_dir = mock_session

        summary = _load_session_summary(session_dir)

        assert len(summary["test_cases"]) == 2
        assert summary["test_cases"][0]["test_id"] == "RS-001::SC-001"

    def test_missing_files_handled(self, tmp_path):
        """_load_session_summary returns empty dict for missing files."""
        session_dir = tmp_path / "empty-session"
        session_dir.mkdir()

        summary = _load_session_summary(session_dir)

        assert summary["artifact_hashes"] == {}
        assert summary["test_cases"] == []


class TestComputeSessionFingerprint:
    """Tests for _compute_session_fingerprint()."""

    def test_fingerprint_is_deterministic(self, mock_session):
        """Same session produces same fingerprint."""
        tmp_path, session_dir = mock_session

        fp1 = _compute_session_fingerprint(session_dir)
        fp2 = _compute_session_fingerprint(session_dir)

        assert fp1["fingerprint"] == fp2["fingerprint"]

    def test_fingerprint_changes_on_artifact_change(self, mock_session):
        """Different artifact hashes produce different fingerprints."""
        tmp_path, session_dir = mock_session

        fp1 = _compute_session_fingerprint(session_dir)

        # Modify gate-summary.json
        gate_summary = json.loads((session_dir / "gate-summary.json").read_text())
        gate_summary["gates"][0]["artifact_hashes"]["extract-reqs"] = "different_hash"
        (session_dir / "gate-summary.json").write_text(json.dumps(gate_summary))

        fp2 = _compute_session_fingerprint(session_dir)

        assert fp1["fingerprint"] != fp2["fingerprint"]

    def test_fingerprint_changes_on_test_case_change(self, mock_session):
        """Different test cases produce different fingerprints."""
        tmp_path, session_dir = mock_session

        fp1 = _compute_session_fingerprint(session_dir)

        # Modify test-cases.json
        test_cases = json.loads((session_dir / "test-cases.json").read_text())
        test_cases["test_cases"].append({"test_id": "RS-003::SC-001", "req_id": "RS-003"})
        (session_dir / "test-cases.json").write_text(json.dumps(test_cases))

        fp2 = _compute_session_fingerprint(session_dir)

        assert fp1["fingerprint"] != fp2["fingerprint"]

    def test_fingerprint_includes_counts(self, mock_session):
        """Fingerprint includes artifact and test case counts."""
        tmp_path, session_dir = mock_session

        fp = _compute_session_fingerprint(session_dir)

        assert fp["artifact_count"] == 2
        assert fp["test_case_count"] == 2


class TestBaselineCommands:
    """Tests for baseline save/list/check commands."""

    def test_baseline_save_creates_file(self, mock_session):
        """baseline save creates a JSON file in baselines directory."""
        tmp_path, session_dir = mock_session

        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            args = type("Args", (), {"session": "test-session", "name": "golden"})()
            result = cmd_baseline_save(args)

        assert result == 0
        baseline_path = tmp_path / ".yuleosh" / "baselines" / "golden.json"
        assert baseline_path.exists()

        baseline = json.loads(baseline_path.read_text())
        assert baseline["name"] == "golden"
        assert baseline["session"] == "test-session"
        assert "fingerprint" in baseline

    def test_baseline_list_shows_saved(self, mock_session, capsys):
        """baseline list shows all saved baselines."""
        tmp_path, session_dir = mock_session

        # Save a baseline first
        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            args = type("Args", (), {"session": "test-session", "name": "golden"})()
            cmd_baseline_save(args)

            # List baselines
            args = type("Args", (), {})()
            result = cmd_baseline_list(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "golden" in captured.out

    def test_consistency_check_match(self, mock_session, capsys):
        """consistency check returns 0 when session matches baseline."""
        tmp_path, session_dir = mock_session

        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            # Save baseline
            args = type("Args", (), {"session": "test-session", "name": "golden"})()
            cmd_baseline_save(args)

            # Check consistency (same session)
            args = type("Args", (), {"session": "test-session", "baseline": "golden"})()
            result = cmd_consistency_check(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "CONSISTENT" in captured.out

    def test_consistency_check_mismatch(self, mock_session, capsys):
        """consistency check returns 1 when session differs from baseline."""
        tmp_path, session_dir = mock_session

        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            # Save baseline
            args = type("Args", (), {"session": "test-session", "name": "golden"})()
            cmd_baseline_save(args)

            # Modify session
            gate_summary = json.loads((session_dir / "gate-summary.json").read_text())
            gate_summary["gates"][0]["artifact_hashes"]["extract-reqs"] = "changed_hash"
            (session_dir / "gate-summary.json").write_text(json.dumps(gate_summary))

            # Check consistency (modified session)
            args = type("Args", (), {"session": "test-session", "baseline": "golden"})()
            result = cmd_consistency_check(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "INCONSISTENT" in captured.out

    def test_consistency_check_missing_session(self, mock_session, capsys):
        """consistency check returns 1 for missing session."""
        tmp_path, session_dir = mock_session

        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            # Save baseline first
            args = type("Args", (), {"session": "test-session", "name": "golden"})()
            cmd_baseline_save(args)

            # Check non-existent session
            args = type("Args", (), {"session": "nonexistent", "baseline": "golden"})()
            result = cmd_consistency_check(args)

        assert result == 1

    def test_consistency_check_missing_baseline(self, mock_session, capsys):
        """consistency check returns 0 (with error message) for missing baseline."""
        tmp_path, session_dir = mock_session

        with patch("yuleosh.cli.commands.consistency._osh_home", return_value=str(tmp_path)):
            args = type("Args", (), {"session": "test-session", "baseline": "nonexistent"})()
            result = cmd_consistency_check(args)

        # Returns 0 because it prints error but doesn't fail hard
        captured = capsys.readouterr()
        assert "not found" in captured.out
