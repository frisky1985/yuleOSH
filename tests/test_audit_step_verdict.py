
# @tests src/yuleosh/pipeline/step_handlers/audit_utils.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for step.verdict audit events (Q1-d).

Verifies that:
- audit_utils.record_step_verdict writes a step.verdict event into the chain
- The event carries artifact_hashes with correct SHA-256 digests
- The event is linked into the hash chain (verify() passes)
- Non-fatal: missing file paths produce empty hash, not an exception
- record_step_verdict on BaseHandler delegates to audit_utils correctly
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.audit.model import AuditLog
from yuleosh.pipeline.step_handlers.audit_utils import record_step_verdict


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_session(tmp_path):
    session = SimpleNamespace(
        name="test-session-001",
        session_id="test-session-001",
        session_dir=tmp_path,
    )
    return session


@pytest.fixture()
def artifact_file(tmp_path):
    """A small artifact file with known content."""
    p = tmp_path / "report.json"
    p.write_text('{"status": "passed"}', encoding="utf-8")
    return p


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Tests: audit_utils.record_step_verdict ────────────────────────────────────

class TestRecordStepVerdict:

    def test_writes_step_verdict_event(self, tmp_path, fake_session, artifact_file):
        """record_step_verdict writes an event with action=step.verdict."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "c-unit-test", "passed", [str(artifact_file)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert len(events) == 1
        assert events[0].action == "step.verdict"

    def test_event_target_is_step_name(self, tmp_path, fake_session, artifact_file):
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "code-review", "failed", [str(artifact_file)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert events[0].target == "step:code-review"

    def test_event_detail_contains_verdict(self, tmp_path, fake_session, artifact_file):
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "test-qualification", "incomplete", [str(artifact_file)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        detail = events[0].detail
        assert detail["verdict"] == "incomplete"
        assert detail["step"] == "test-qualification"
        assert detail["session_id"] == "test-session-001"

    def test_artifact_hash_matches_file_content(self, tmp_path, fake_session, artifact_file):
        """artifact_hashes dict must carry correct SHA-256 of the file."""
        expected_hash = _sha256_file(str(artifact_file))

        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "python-unit-test", "passed", [str(artifact_file)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        hashes = events[0].detail["artifact_hashes"]
        assert hashes["report.json"] == expected_hash

    def test_multiple_artifact_paths(self, tmp_path, fake_session):
        """Multiple artifacts all appear in artifact_hashes."""
        f1 = tmp_path / "report.json"
        f2 = tmp_path / "junit.xml"
        f1.write_text('{"status":"passed"}', encoding="utf-8")
        f2.write_text("<testsuite/>", encoding="utf-8")

        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "test-qualification", "passed", [str(f1), str(f2)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        hashes = events[0].detail["artifact_hashes"]
        assert "report.json" in hashes
        assert "junit.xml" in hashes
        assert hashes["report.json"] == _sha256_file(str(f1))
        assert hashes["junit.xml"] == _sha256_file(str(f2))

    def test_missing_artifact_path_produces_empty_hash(self, tmp_path, fake_session):
        """A path that does not exist gets empty string hash, no exception."""
        missing = str(tmp_path / "nonexistent.json")

        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "arch-review", "passed", [missing])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        hashes = events[0].detail["artifact_hashes"]
        assert hashes.get("nonexistent.json") == ""

    def test_empty_artifact_list(self, tmp_path, fake_session):
        """Empty artifact_paths is valid — records event with empty hashes."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "prd-review", "warning", [])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert events[0].detail["artifact_hashes"] == {}

    def test_none_artifact_paths(self, tmp_path, fake_session):
        """None artifact_paths is treated as empty."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "prd-review", "passed", None)

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert events[0].detail["artifact_hashes"] == {}

    def test_hash_chain_integrity_after_two_verdicts(self, tmp_path, fake_session, artifact_file):
        """Two consecutive step.verdict events form a valid hash chain."""
        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            record_step_verdict(fake_session, "c-unit-test", "passed", [str(artifact_file)])
            record_step_verdict(fake_session, "code-review", "passed", [str(artifact_file)])

        audit = AuditLog(data_root=str(tmp_path))
        result = audit.verify()
        assert result["valid"], f"Hash chain broken: {result.get('reason')}"

    def test_non_fatal_on_audit_failure(self, fake_session, artifact_file):
        """If AuditLog raises, record_step_verdict does NOT propagate the exception."""
        with patch("yuleosh.audit.model.AuditLog", side_effect=RuntimeError("disk full")):
            record_step_verdict(fake_session, "c-unit-test", "passed", [str(artifact_file)])


# ── Tests: BaseHandler.record_step_verdict ───────────────────────────────────

class TestBaseHandlerRecordStepVerdict:

    def _make_handler(self, tmp_path):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class ConcreteHandler(BaseHandler):
            step_name = "test-step"

            def execute(self, session):
                return str(session.session_dir / "out.json")

        return ConcreteHandler()

    def test_base_handler_writes_verdict_event(self, tmp_path):
        handler = self._make_handler(tmp_path)
        artifact = tmp_path / "out.json"
        artifact.write_text('{"status":"passed"}', encoding="utf-8")

        session = SimpleNamespace(
            name="sess-42",
            session_id="sess-42",
            session_dir=tmp_path,
        )

        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            handler.record_step_verdict(session, "passed", [str(artifact)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert len(events) == 1
        assert events[0].action == "step.verdict"
        assert events[0].detail["verdict"] == "passed"
        assert events[0].detail["step"] == "test-step"

    def test_base_handler_verdict_artifact_hash(self, tmp_path):
        handler = self._make_handler(tmp_path)
        artifact = tmp_path / "result.json"
        artifact.write_text('{"result": 42}', encoding="utf-8")
        expected = _sha256_file(str(artifact))

        session = SimpleNamespace(
            name="sess-43",
            session_id="sess-43",
            session_dir=tmp_path,
        )

        with patch.dict(os.environ, {"YULEOSH_AUDIT_ROOT": str(tmp_path)}):
            handler.record_step_verdict(session, "passed", [str(artifact)])

        audit = AuditLog(data_root=str(tmp_path))
        events = audit.query(action="step.verdict")
        assert events[0].detail["artifact_hashes"]["result.json"] == expected
