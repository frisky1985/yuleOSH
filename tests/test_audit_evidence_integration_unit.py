"""Tests for audit log verification integrated into evidence bundle (安全可审计).

Covers the 2026-08-07 feature: `yuleosh audit evidence` now runs
`AuditLog.verify()` and writes audit-log-verification.json into the bundle.
"""

# @tests src/yuleosh/audit/model.py

import json
import subprocess
import sys
from pathlib import Path

import pytest

from yuleosh.audit import AuditLog
from yuleosh.cli.commands.misc import _collect_audit_log_verification


class TestCollectAuditLogVerification:
    def test_intact_chain_writes_verification(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path / "data"))
        log.record("user:1", "project.create", "project:p1")
        log.record("system", "evidence.export", "bundle:1")

        out = tmp_path / "bundle"
        out.mkdir()
        entry = _collect_audit_log_verification(tmp_path, out)

        assert entry is not None
        assert entry["type"] == "audit-log-verification"
        assert entry["valid"] is True
        assert entry["checked_events"] == 2

        verify_path = out / "audit-log-verification.json"
        assert verify_path.exists()
        data = json.loads(verify_path.read_text())
        assert data["valid"] is True
        assert data["checked_events"] == 2

    def test_tampered_chain_detected(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path / "data"))
        log.record("user:1", "project.create", "project:p1")
        log.record("system", "evidence.export", "bundle:1")

        # Tamper with the first event's target.
        f = sorted((tmp_path / "data" / "audit").glob("*.jsonl"))[-1]
        lines = f.read_text().splitlines()
        data = json.loads(lines[0])
        data["target"] = "project:EVIL"
        lines[0] = json.dumps(data, ensure_ascii=False)
        f.write_text("\n".join(lines) + "\n")

        out = tmp_path / "bundle"
        out.mkdir()
        entry = _collect_audit_log_verification(tmp_path, out)

        assert entry is not None
        assert entry["valid"] is False

        verify_path = out / "audit-log-verification.json"
        data = json.loads(verify_path.read_text())
        assert data["valid"] is False
        assert data["broken_at"] == 1
        assert "hash mismatch" in data["reason"]

    def test_no_audit_dir_is_graceful(self, tmp_path):
        """No audit logs yet — verification still produces a valid empty report."""
        out = tmp_path / "bundle"
        out.mkdir()
        entry = _collect_audit_log_verification(tmp_path, out)

        assert entry is not None
        assert entry["valid"] is True
        assert entry["checked_events"] == 0

    def test_audit_evidence_cli_includes_verification(self, tmp_path, monkeypatch):
        """End-to-end: `yuleosh audit evidence` embeds the verification artifact."""
        data_root = tmp_path / "data"
        log = AuditLog(data_root=str(data_root))
        log.record("user:1", "project.create", "project:p1")

        out = tmp_path / "evidence-out"
        monkeypatch.setenv("OSH_HOME", str(tmp_path))

        from yuleosh.cli.commands.misc import cmd_audit_evidence
        cmd_audit_evidence(output_dir=str(out), create_zip=False)

        manifest = json.loads((out / "audit-manifest.json").read_text())
        types = [a.get("type") for a in manifest["artifacts"]]
        assert "audit-log-verification" in types
        assert (out / "audit-log-verification.json").exists()
