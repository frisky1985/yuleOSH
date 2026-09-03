
# @tests src/yuleosh/pipeline/gates.py, src/yuleosh/pipeline/session.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Gate status aggregation + evidence provenance (2026-09-03).

Guards four defects found while running ``pipeline run --mock`` end-to-end:

1. ``write_gate_summary`` read ``session.steps[i]["step"]`` (the 1-based
   ordinal) instead of ``["name"]`` (the step key), so no step ever matched
   a ``GATES`` step_key and **every gate reported "passed" unconditionally**.
2. Step handlers that skip real work write ``skipped`` into their own
   artifact while the orchestrator still marks the step ``completed``;
   the artifact verdict must win.
3. Several artifacts do not follow ``<step_key>.json``
   (``critical-safety-report.json``, ``merge-gate-report.json``,
   ``fault-injection-report.md``), so their gates never saw a verdict.
4. ``worst_gate_status`` required *all* steps to be skipped before
   reporting ``skipped``, contradicting ``GATE_STATUS_ORDER`` and letting
   a summary list skipped gates while claiming ``passed``.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.pipeline.gates import write_gate_summary, _artifact_verdict
from yuleosh.pipeline.session import PipelineSession


def _session(tmp_path, steps):
    return SimpleNamespace(name="test-sess", session_dir=tmp_path, steps=steps)


def _summary(tmp_path, steps, **kwargs):
    out = write_gate_summary(_session(tmp_path, steps), **kwargs)
    return json.loads(Path(out).read_text())


def _gate(summary, key):
    return next(g for g in summary["gates"] if g["gate"] == key)


class TestStepKeyResolution:
    """Defect 1 — the ordinal/name mix-up that made every gate green."""

    def test_status_is_read_from_name_not_step_ordinal(self, tmp_path):
        """A failed step keyed by ``name`` MUST make its gate fail.

        Before the fix ``s["step"]`` (int 1) was used as the dict key, so
        no GATES step_key ever matched and this assertion returned passed.
        """
        summary = _summary(tmp_path, [
            {"step": 1, "name": "spec-check", "status": "failed"},
        ])
        assert _gate(summary, "G1")["status"] == "failed"

    def test_ordinal_only_entry_is_ignored_not_treated_as_green(self, tmp_path):
        """An entry without a usable step key contributes nothing."""
        summary = _summary(tmp_path, [{"step": 7, "status": "failed"}])
        assert _gate(summary, "G1")["status"] == "passed"

    def test_step_key_field_still_honoured(self, tmp_path):
        """Callers using ``step_key`` keep working."""
        summary = _summary(tmp_path, [
            {"step_key": "spec-check", "status": "failed"},
        ])
        assert _gate(summary, "G1")["status"] == "failed"


class TestArtifactVerdictOverlay:
    """Defect 2 — artifact ``skipped`` beats the optimistic ``completed``."""

    def test_skipped_artifact_overrides_completed_step(self, tmp_path):
        (tmp_path / "merge-gate-report.json").write_text(
            json.dumps({"skipped": True, "passed": False}), encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 22, "name": "merge-gate", "status": "completed"},
        ])
        assert _gate(summary, "G9")["status"] == "skipped"

    def test_explicit_false_passed_becomes_failed(self, tmp_path):
        (tmp_path / "merge-gate.json").write_text(
            json.dumps({"passed": False}), encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 22, "name": "merge-gate", "status": "completed"},
        ])
        assert _gate(summary, "G9")["status"] == "failed"

    def test_explicit_step_statuses_argument_is_never_overridden(self, tmp_path):
        """A caller that passes statuses explicitly knows better."""
        (tmp_path / "merge-gate-report.json").write_text(
            json.dumps({"skipped": True}), encoding="utf-8")
        out = write_gate_summary(
            _session(tmp_path, [{"name": "merge-gate", "status": "completed"}]),
            step_statuses={"merge-gate": "passed"},
        )
        summary = json.loads(Path(out).read_text())
        assert _gate(summary, "G9")["status"] == "passed"

    def test_unknown_schema_never_flips_a_passing_step(self, tmp_path):
        """spec-check.json has no status field — must stay passed."""
        (tmp_path / "spec-check.json").write_text(
            json.dumps({"coverage": {"score": 100.0}}), encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 1, "name": "spec-check", "status": "completed"},
        ])
        assert _gate(summary, "G1")["status"] == "passed"

    def test_unparsable_artifact_is_ignored(self, tmp_path):
        (tmp_path / "spec-check.json").write_text("{not json", encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 1, "name": "spec-check", "status": "completed"},
        ])
        assert _gate(summary, "G1")["status"] == "passed"


class TestArtifactNameOverrides:
    """Defect 3 — artifacts that do not follow ``<step_key>.json``."""

    def test_critical_safety_report_name(self, tmp_path):
        (tmp_path / "critical-safety-report.json").write_text(
            json.dumps({"skipped": True, "violations": []}), encoding="utf-8")
        (tmp_path / "fault-injection-report.md").write_text(
            "# Fault Injection — SKIPPED (mock mode)\n", encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 20, "name": "review-critical-safety", "status": "completed"},
            {"step": 21, "name": "fault-injection", "status": "completed"},
        ])
        assert _gate(summary, "G8")["status"] == "skipped"

    def test_fault_injection_markdown_banner(self, tmp_path):
        (tmp_path / "fault-injection-report.md").write_text(
            "# Fault Injection — SKIPPED (mock mode)\n", encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 21, "name": "fault-injection", "status": "completed"},
        ])
        assert _gate(summary, "G8")["status"] == "skipped"

    def test_code_review_unified_name(self, tmp_path):
        (tmp_path / "code-review-unified.json").write_text(
            json.dumps({"status": "skipped"}), encoding="utf-8")
        summary = _summary(tmp_path, [
            {"step": 15, "name": "code-review", "status": "completed"},
        ])
        assert _gate(summary, "G7")["status"] == "skipped"

    def test_verdict_helper_returns_empty_without_artifact(self, tmp_path):
        assert _artifact_verdict(tmp_path, "spec-check") == ""


class TestWorstGateStatus:
    """Defect 4 — the summary must not contradict its own gate list."""

    def test_skipped_gate_makes_worst_skipped(self, tmp_path):
        (tmp_path / "critical-safety-report.json").write_text(
            json.dumps({"skipped": True}), encoding="utf-8")
        (tmp_path / "fault-injection-report.md").write_text(
            "SKIPPED\n", encoding="utf-8")
        summary = _summary(tmp_path, [
            {"name": "spec-check", "status": "completed"},
            {"name": "review-critical-safety", "status": "completed"},
            {"name": "fault-injection", "status": "completed"},
        ])
        assert _gate(summary, "G8")["status"] == "skipped"
        assert summary["worst_gate_status"] == "skipped"

    def test_failed_outranks_skipped(self, tmp_path):
        summary = _summary(tmp_path, [
            {"name": "spec-check", "status": "failed"},
            {"name": "prd-review", "status": "skipped"},
        ])
        assert summary["worst_gate_status"] == "failed"

    def test_all_passed_stays_passed(self, tmp_path):
        summary = _summary(tmp_path, [
            {"name": "spec-check", "status": "completed"},
            {"name": "prd", "status": "completed"},
        ])
        assert summary["worst_gate_status"] == "passed"


class TestSessionMockProvenance:
    """Evidence chain must record whether a run used a real LLM."""

    def test_to_dict_exposes_mock_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = PipelineSession("t", "spec.md")
        assert session.to_dict()["mock_mode"] is False
        session.mock_mode = True
        assert session.to_dict()["mock_mode"] is True

    def test_mock_mode_survives_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = PipelineSession("t", "spec.md")
        session.mock_mode = True
        session._save()
        persisted = json.loads(
            (session.session_dir / "session.json").read_text(encoding="utf-8"))
        assert persisted["mock_mode"] is True

    def test_real_run_defaults_to_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = PipelineSession("t", "spec.md")
        session._save()
        persisted = json.loads(
            (session.session_dir / "session.json").read_text(encoding="utf-8"))
        assert persisted["mock_mode"] is False
