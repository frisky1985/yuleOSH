"""Unit tests for yuleosh.audit.model — AuditEvent + AuditLog (v3.4.2 Wave 0).

Covers:
  - AuditEvent: defaults, to_dict/from_dict roundtrip, partial from_dict, repr
  - AuditLog: init with explicit/custom data_root, _get_file_path date/tenant variants
  - record(): tenant-scoped + global JSONL writes
  - query(): filters (action/actor/tenant/limit/date-range), missing files,
    malformed lines, OSError handling, newest-first sorting
  - get_summary(): aggregation by action
"""

# @tests src/yuleosh/audit/model.py

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.audit.model import (
    AuditEvent,
    AuditLog,
    EVENT_PROJECT_CREATE,
    EVENT_PIPELINE_RUN,
    EVENT_AUTH_LOGIN,
)


# ── AuditEvent ────────────────────────────────────────────────────────

class TestAuditEvent:
    def test_init_defaults(self):
        """GIVEN minimal args WHEN creating event THEN defaults are filled."""
        ev = AuditEvent(actor="user:1", action="project.create")
        assert ev.actor == "user:1"
        assert ev.action == "project.create"
        assert ev.target == ""
        assert ev.timestamp, "timestamp should be auto-filled"
        assert ev.tenant == ""
        assert ev.detail == {}

    def test_init_explicit_values(self):
        """GIVEN full args WHEN creating event THEN all fields preserved."""
        ev = AuditEvent(actor="system", action="pipeline.run", target="pipeline:p1",
                        timestamp="2026-07-27T01:00:00", tenant="my-org",
                        detail={"k": "v"})
        assert ev.target == "pipeline:p1"
        assert ev.timestamp == "2026-07-27T01:00:00"
        assert ev.tenant == "my-org"
        assert ev.detail == {"k": "v"}

    def test_to_dict(self):
        """GIVEN event WHEN to_dict THEN JSON-safe mapping returned."""
        ev = AuditEvent(actor="user:1", action=EVENT_PROJECT_CREATE,
                        target="project:x", timestamp="ts", tenant="org",
                        detail={"n": 1})
        d = ev.to_dict()
        assert d["actor"] == "user:1"
        assert d["action"] == EVENT_PROJECT_CREATE
        assert d["target"] == "project:x"
        assert d["timestamp"] == "ts"
        assert d["tenant"] == "org"
        assert d["detail"] == {"n": 1}

    def test_from_dict_full(self):
        """GIVEN full dict WHEN from_dict THEN event reconstructed."""
        ev = AuditEvent.from_dict({
            "actor": "a", "action": "b", "target": "c",
            "timestamp": "t", "tenant": "tn", "detail": {"x": 1},
        })
        assert (ev.actor, ev.action, ev.target) == ("a", "b", "c")
        assert (ev.timestamp, ev.tenant, ev.detail) == ("t", "tn", {"x": 1})

    def test_from_dict_partial(self):
        """GIVEN sparse dict WHEN from_dict THEN defaults for missing keys."""
        ev = AuditEvent.from_dict({"action": "review.approve"})
        assert ev.actor == "unknown"
        assert ev.detail == {}

    def test_repr(self):
        """GIVEN event WHEN repr THEN contains actor/action."""
        ev = AuditEvent(actor="u", action="x", target="t", timestamp="ts")
        r = repr(ev)
        assert "AuditEvent" in r and "u" in r and "x" in r


# ── AuditLog: path resolution ─────────────────────────────────────────

class TestAuditLogPaths:
    def test_default_data_root_from_osh_home(self, monkeypatch):
        """GIVEN no OSH_HOME WHEN init THEN uses ~/.openclaw fallback."""
        monkeypatch.delenv("OSH_HOME", raising=False)
        log = AuditLog()
        assert log.data_root.name == "data"
        assert log.audit_dir.name == "audit"

    def test_custom_data_root(self, tmp_path):
        """GIVEN explicit data_root WHEN init THEN dirs created."""
        log = AuditLog(data_root=str(tmp_path))
        assert log.data_root == tmp_path
        assert (tmp_path / "audit").is_dir()

    def test_get_file_path_default_date(self, tmp_path):
        """GIVEN no date WHEN _get_file_path THEN today's file used."""
        log = AuditLog(data_root=str(tmp_path))
        p = log._get_file_path()
        assert p.name == f"{date.today().isoformat()}.jsonl"
        assert p.parent == log.audit_dir

    def test_get_file_path_explicit_date(self, tmp_path):
        """GIVEN date WHEN _get_file_path THEN dated file returned."""
        log = AuditLog(data_root=str(tmp_path))
        p = log._get_file_path("2026-01-02")
        assert p.name == "2026-01-02.jsonl"

    def test_get_file_path_tenant(self, tmp_path):
        """GIVEN tenant WHEN _get_file_path THEN tenant-scoped path."""
        log = AuditLog(data_root=str(tmp_path))
        p = log._get_file_path("2026-01-02", tenant="my-org")
        assert str(p).endswith("my-org/audit/2026-01-02.jsonl")


# ── AuditLog: record / query / summary ────────────────────────────────

class TestAuditLogRecord:
    def test_record_writes_global_log(self, tmp_path):
        """GIVEN tenantless event WHEN record THEN global JSONL appended."""
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record("user:1", EVENT_PROJECT_CREATE, target="project:p")
        assert ev.action == EVENT_PROJECT_CREATE
        lines = (tmp_path / "audit" / f"{date.today().isoformat()}.jsonl") \
            .read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["actor"] == "user:1"
        assert data["target"] == "project:p"

    def test_record_tenant_writes_both(self, tmp_path):
        """GIVEN tenant event WHEN record THEN tenant + global logs written."""
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record("system", EVENT_PIPELINE_RUN, tenant="acme")
        assert ev.tenant == "acme"
        tenant_file = tmp_path / "acme" / "audit" / f"{date.today().isoformat()}.jsonl"
        global_file = tmp_path / "audit" / f"{date.today().isoformat()}.jsonl"
        assert tenant_file.exists()
        assert global_file.exists()
        assert json.loads(tenant_file.read_text())["tenant"] == "acme"

    def test_query_empty(self, tmp_path):
        """GIVEN no records WHEN query THEN empty list."""
        log = AuditLog(data_root=str(tmp_path))
        assert log.query() == []

    def test_query_filters_action(self, tmp_path):
        """GIVEN mixed events WHEN query by action THEN only matches."""
        log = AuditLog(data_root=str(tmp_path))
        log.record("u1", "project.create")
        log.record("u1", "project.delete")
        results = log.query(action="project.create")
        assert len(results) == 1
        assert results[0].action == "project.create"

    def test_query_filters_actor(self, tmp_path):
        """GIVEN mixed events WHEN query by actor THEN only matches."""
        log = AuditLog(data_root=str(tmp_path))
        log.record("u1", "a1")
        log.record("u2", "a2")
        results = log.query(actor="u2")
        assert len(results) == 1 and results[0].actor == "u2"

    def test_query_filters_tenant(self, tmp_path):
        """GIVEN tenant events WHEN query tenant mismatched THEN filtered out."""
        log = AuditLog(data_root=str(tmp_path))
        log.record("u1", "a1", tenant="acme")
        log.record("u1", "a1", tenant="globex")
        # Querying acme without tenant filter returns both (tenant filter only
        # applies when event.tenant is set AND query tenant is set)
        assert len(log.query(tenant="acme")) == 1

    def test_query_limit(self, tmp_path):
        """GIVEN many events WHEN query with limit THEN capped newest first."""
        log = AuditLog(data_root=str(tmp_path))
        for i in range(5):
            log.record("u", "a", timestamp=f"2026-07-2{i}T00:00:00")
        results = log.query(limit=2)
        assert len(results) == 2
        assert results[0].timestamp > results[1].timestamp

    def test_query_date_range(self, tmp_path):
        """GIVEN records over days WHEN date range given THEN scoped results."""
        log = AuditLog(data_root=str(tmp_path))
        # write directly to specific dated files
        p1 = log._get_file_path("2026-01-01")
        p1.write_text(json.dumps({"actor": "u", "action": "a", "target": "",
                                  "timestamp": "2026-01-01T00:00:00",
                                  "tenant": "", "detail": {}}) + "\n")
        p2 = log._get_file_path("2026-01-03")
        p2.write_text(json.dumps({"actor": "u", "action": "a", "target": "",
                                  "timestamp": "2026-01-03T00:00:00",
                                  "tenant": "", "detail": {}}) + "\n")
        results = log.query(from_date="2026-01-02", to_date="2026-01-04")
        assert len(results) == 1
        assert results[0].timestamp.startswith("2026-01-03")

    def test_query_skips_malformed_lines(self, tmp_path):
        """GIVEN corrupt JSONL lines WHEN query THEN skipped gracefully."""
        log = AuditLog(data_root=str(tmp_path))
        p = log._get_file_path("2026-02-02")
        p.write_text('{"actor": "u", "action": "a", "target": "", '
                     '"timestamp": "2026-02-02T00:00:00", "tenant": "", "detail": {}}\n'
                     "not-json\n")
        results = log.query(from_date="2026-02-02", to_date="2026-02-02")
        assert len(results) == 1

    def test_query_handles_oserror(self, tmp_path):
        """GIVEN unreadable path WHEN query THEN warning logged, no crash."""
        log = AuditLog(data_root=str(tmp_path))
        p = log._get_file_path("2026-03-03")
        p.mkdir()  # directory at file path → open() raises IsADirectoryError (OSError)
        with mock.patch("yuleosh.audit.model.logger") as mlog:
            results = log.query(from_date="2026-03-03", to_date="2026-03-03")
        assert results == []
        mlog.warning.assert_called()

    def test_get_summary(self, tmp_path):
        """GIVEN events WHEN get_summary THEN counts by action."""
        log = AuditLog(data_root=str(tmp_path))
        log.record("u", EVENT_AUTH_LOGIN)
        log.record("u", EVENT_AUTH_LOGIN)
        log.record("u", EVENT_PROJECT_CREATE)
        summary = log.get_summary()
        assert summary["total_events"] == 3
        assert summary["by_action"] == {EVENT_AUTH_LOGIN: 2, EVENT_PROJECT_CREATE: 1}
        assert summary["from_date"]
        assert summary["to_date"]
