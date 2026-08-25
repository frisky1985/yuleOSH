
# @tests src/yuleosh/alm/traceability.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for RTM integrity hash audit anchor (Q2-c).

Verifies that compute_trace_integrity() anchors the integrity_hash into
the SHA-256 audit chain via a traceability.snapshot event.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from yuleosh.audit.model import AuditLog
from yuleosh.alm.traceability import compute_trace_integrity


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def minimal_project(tmp_path):
    """A minimal project directory with a spec file."""
    spec = tmp_path / "docs" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "# Spec\n\nRS-001: The system SHALL initialize within 100ms.\n",
        encoding="utf-8",
    )
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestTraceabilitySnapshotAudit:

    def test_snapshot_event_written_to_audit_chain(self, tmp_path, minimal_project):
        """compute_trace_integrity writes a traceability.snapshot audit event."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            result = compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="traceability.snapshot")
        assert len(events) >= 1
        assert events[0].action == "traceability.snapshot"

    def test_snapshot_event_carries_integrity_hash(self, tmp_path, minimal_project):
        """The audit event's detail.integrity_hash matches the returned record."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record = compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="traceability.snapshot")
        detail = events[0].detail
        assert detail["integrity_hash"] == record["integrity_hash"]

    def test_snapshot_event_carries_coverage_pct(self, tmp_path, minimal_project):
        """The audit event includes test_coverage_pct for traceability audit."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record = compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="traceability.snapshot")
        assert "test_coverage_pct" in events[0].detail

    def test_snapshot_event_target_contains_project_name(self, tmp_path, minimal_project):
        """Event target is 'project:<dirname>' for traceability."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="traceability.snapshot")
        assert events[0].target.startswith("project:")
        assert minimal_project.name in events[0].target

    def test_snapshot_hash_chain_valid(self, tmp_path, minimal_project):
        """After anchoring RTM snapshot, the audit hash chain remains valid."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        result = audit.verify()
        assert result["valid"], f"Hash chain broken: {result.get('reason')}"

    def test_compute_trace_integrity_non_fatal_on_audit_failure(self, minimal_project):
        """If AuditLog raises, compute_trace_integrity still returns the record."""
        with patch("yuleosh.audit.model.AuditLog", side_effect=RuntimeError("disk full")):
            record = compute_trace_integrity(str(minimal_project))

        assert "integrity_hash" in record
        assert "status" in record
        assert "requirements_total" in record

    def test_two_snapshots_form_valid_chain(self, tmp_path, minimal_project):
        """Two sequential compute_trace_integrity calls build a valid 2-event chain."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            compute_trace_integrity(str(minimal_project))
            compute_trace_integrity(str(minimal_project))

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="traceability.snapshot")
        assert len(events) == 2

        result = audit.verify()
        assert result["valid"], f"Hash chain broken after 2 snapshots: {result.get('reason')}"
