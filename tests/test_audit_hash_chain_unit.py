"""Unit tests for audit log SHA-256 hash chain + integrity verification.

Covers the 安全可审计 (security & auditability) feature (2026-08-07):
  - record() links events into a SHA-256 hash chain (hash + prev_hash)
  - verify() accepts an intact chain and reports event counts
  - verify() detects payload tampering (edit of a recorded event)
  - verify() detects chain breakage (deletion / reordering)
  - verify() handles legacy rows written before the hash-chain feature
  - cross-day files are verified sequentially with a continuing chain
"""

import json
from pathlib import Path

import pytest

from yuleosh.audit.model import (
    AuditEvent,
    AuditLog,
    compute_event_hash,
)


def _write_event(path: Path, event_dict: dict):
    """Append a raw event dict (bypassing record()) for tamper tests."""
    with open(path, "a") as f:
        f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")


class TestHashChainRecord:
    def test_record_has_hash_fields(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record("user:1", "project.create", "project:p1", tenant="org-a")
        assert ev.hash
        assert ev.prev_hash == ""  # first event anchors the chain
        assert len(ev.hash) == 64  # sha256 hex

    def test_chain_links_events(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        e1 = log.record("user:1", "project.create", "project:p1", tenant="org-a")
        e2 = log.record("user:1", "project.update", "project:p1", tenant="org-a")
        assert e2.prev_hash == e1.hash
        assert e1.hash != e2.hash

    def test_hash_is_content_sensitive(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        e1 = log.record("user:1", "project.create", "project:p1", tenant="org-a")
        e2 = log.record("user:1", "project.create", "project:p2", tenant="org-a")
        assert e1.hash != e2.hash

    def test_compute_event_hash_ignores_chain_metadata(self):
        base = {"actor": "u", "action": "a", "target": "t",
                "timestamp": "2026-01-01T00:00:00", "tenant": "", "detail": {}}
        h1 = compute_event_hash(base, "prev1")
        h2 = compute_event_hash({**base, "hash": "stale", "prev_hash": "stale"}, "prev1")
        assert h1 == h2


class TestVerify:
    def test_verify_intact_chain(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record("user:1", "a1", tenant="")
        log.record("user:1", "a2", tenant="")
        log.record("user:1", "a3", tenant="")
        result = log.verify()
        assert result["valid"] is True
        assert result["checked"] == 3
        assert result["legacy"] == 0
        assert len(result["files"]) == 1

    def test_verify_detects_payload_tamper(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record("user:1", "a1", tenant="")
        log.record("user:1", "a2", tenant="")
        # Tamper with the middle event's target after the fact.
        path = log._get_file_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        data = json.loads(lines[1])
        data["target"] = "project:EVIL"
        lines[1] = json.dumps(data, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = log.verify()
        assert result["valid"] is False
        assert result["broken_at"] == 2
        assert "hash mismatch" in result["reason"]

    def test_verify_detects_deletion(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record("user:1", "a1", tenant="")
        log.record("user:1", "a2", tenant="")
        log.record("user:1", "a3", tenant="")
        # Delete the middle event: e3's prev_hash no longer matches e1's hash.
        path = log._get_file_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        del lines[1]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = log.verify()
        assert result["valid"] is False
        assert result["broken_at"] == 2  # e3 is now the 2nd checked event

    def test_verify_legacy_rows_compatible(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        # Write a legacy row (no hash fields) then record a new one.
        _write_event(log._get_file_path(), {
            "actor": "user:0", "action": "legacy.old", "target": "",
            "timestamp": "2026-01-01T00:00:00", "tenant": "", "detail": {},
        })
        ev = log.record("user:1", "a2", tenant="")
        assert ev.prev_hash  # legacy row used as chain anchor
        result = log.verify()
        assert result["valid"] is True
        assert result["legacy"] == 1
        assert result["checked"] == 2

    def test_verify_cross_day_files(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        # Write events into two different day files explicitly.
        p1 = log._get_file_path("2026-07-01", "")
        p1.parent.mkdir(parents=True, exist_ok=True)
        e1 = log.record("user:1", "a1", timestamp="2026-07-01T10:00:00", tenant="")
        # e1 lands in today's file; move it to the 07-01 file for the test.
        today_path = log._get_file_path()
        if today_path != p1:
            today_path.replace(p1)

        log2 = AuditLog(data_root=str(tmp_path))
        p2 = log2._get_file_path("2026-07-02", "")
        p2.parent.mkdir(parents=True, exist_ok=True)
        e2 = log2.record("user:1", "a2", timestamp="2026-07-02T10:00:00", tenant="")
        today2 = log2._get_file_path()
        if today2 != p2:
            today2.replace(p2)

        assert e2.prev_hash  # chain continues across files
        result = log.verify(from_date="2026-07-01", to_date="2026-07-02")
        assert result["valid"] is True
        assert result["checked"] == 2
        assert len(result["files"]) == 2

    def test_verify_no_files_is_valid(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        result = log.verify()
        assert result["valid"] is True
        assert result["checked"] == 0

    def test_verify_malformed_json_detected(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record("user:1", "a1", tenant="")
        path = log._get_file_path()
        with open(path, "a") as f:
            f.write("{not-json}\n")
        result = log.verify()
        assert result["valid"] is False
        assert "malformed JSON" in result["reason"]
