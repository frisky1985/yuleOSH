
# @tests src/yuleosh/pipeline/gates.py, src/yuleosh/pipeline/session.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Gate status aggregation + evidence provenance (2026-09-03, extended 2026-09-23).

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

Added 2026-09-23 (run ``57fa80e754ed`` — 24/24 steps ``completed``, G7 fully
skipped, console still printed "GREEN — all gates passed"):

5. **Evidence freshness.** Each artifact records the ``session`` that wrote
   it.  A mismatch means leftover evidence from an earlier run and must be
   reported as ``stale``, not silently accepted.  ``REUSABLE_STEPS``
   (spec-check / codegen-deploy) are exempt because reuse is by design.
6. **No evidence ⇒ no green.** A gate with no recorded steps is ``not-run``
   (it used to claim ``passed``), and ``classify_run_outcome`` only grants
   GREEN when every non-advisory gate actually passed.
7. **A green claim needs evidence, not just bookkeeping** (P0-C,
   2026-09-23).  A step that reports ``completed`` while producing *no*
   artifact is recorded as ``not-run``: "the artifact is missing" and "the
   artifact passed" used to be the same observation, so deleting evidence
   left the gate green.  Tests below therefore materialise artifacts via
   ``_write_all_artifacts`` before asserting that a full run is green — the
   later cases in ``test_gate_artifact_coverage.py`` assert the downgrade
   itself.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.pipeline.gates import (
    _artifact_verdict,
    classify_run_outcome,
    write_gate_summary,
)
from yuleosh.pipeline.session import PipelineSession


def _session(tmp_path, steps):
    return SimpleNamespace(name="test-sess", session_dir=tmp_path, steps=steps)


def _all_steps_completed(**override):
    """Build a *complete* step list (every pipeline step ``completed``).

    A full list matters since 2026-09-23: gates with no recorded steps now
    report ``not-run`` rather than ``passed``, so a partial list would make
    ``worst_gate_status`` reflect the *missing* gates instead of the gate
    under test.  ``override`` maps step_key -> status.
    """
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    steps = []
    for entry in PIPELINE_STEPS:
        key = entry[0] if isinstance(entry, (tuple, list)) else entry
        steps.append({"name": key, "status": override.get(key, "completed")})
    return steps


def _summary(tmp_path, steps, **kwargs):
    out = write_gate_summary(_session(tmp_path, steps), **kwargs)
    return json.loads(Path(out).read_text())


def _write_all_artifacts(tmp_path, session="test-sess", **override):
    """Materialise an artifact for *every* pipeline step.

    Since P0-C (2026-09-23) a step claiming ``completed`` without producing an
    artifact is recorded as ``not-run``, so "all steps completed" is only a
    meaningful precondition once the evidence exists — that is what this
    helper makes true.  ``override`` maps step_key -> JSON text for cases that
    need a specific verdict in one step's artifact.
    """
    from yuleosh.pipeline.gates import _ARTIFACT_CANDIDATES
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    default = json.dumps({"session": session, "status": "passed"})
    for entry in PIPELINE_STEPS:
        key = entry[0] if isinstance(entry, (tuple, list)) else entry
        name = _ARTIFACT_CANDIDATES.get(key, (f"{key}.json",))[0]
        (tmp_path / name).write_text(override.get(key, default), encoding="utf-8")


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
        """An entry without a usable step key contributes nothing.

        Since 2026-09-23 that means the gate has **no evidence** and reports
        ``not-run`` — it must never read as ``passed`` merely because no
        matching step key was found.
        """
        summary = _summary(tmp_path, [{"step": 7, "status": "failed"}])
        assert _gate(summary, "G1")["status"] == "not-run"
        assert summary["worst_gate_status"] != "passed"

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
        _write_all_artifacts(tmp_path, **{
            "review-critical-safety": json.dumps({"skipped": True}),
            "fault-injection": "SKIPPED\n",
        })
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G8")["status"] == "skipped"
        assert summary["worst_gate_status"] == "skipped"

    def test_failed_outranks_skipped(self, tmp_path):
        summary = _summary(tmp_path, _all_steps_completed(**{
            "spec-check": "failed", "prd-review": "skipped"}))
        assert summary["worst_gate_status"] == "failed"

    def test_all_passed_stays_passed(self, tmp_path):
        _write_all_artifacts(tmp_path)
        summary = _summary(tmp_path, _all_steps_completed())
        assert summary["worst_gate_status"] == "passed"
        assert summary["not_run_gates"] == []
        assert summary["stale_gates"] == []


class TestNoEvidenceIsNotGreen:
    """Defect 6 — a gate with no recorded steps used to claim ``passed``."""

    def test_empty_gate_reports_not_run(self, tmp_path):
        """Only G1 has steps; every other gate has no evidence at all."""
        summary = _summary(tmp_path, [
            {"name": "spec-check", "status": "completed"},
        ])
        assert _gate(summary, "G1")["status"] == "passed"
        assert _gate(summary, "G7")["status"] == "not-run"
        assert summary["worst_gate_status"] == "not-run"

    def test_not_run_gates_are_listed_explicitly(self, tmp_path):
        summary = _summary(tmp_path, [
            {"name": "spec-check", "status": "completed"},
        ])
        assert "G1" not in summary["not_run_gates"]
        assert "G7" in summary["not_run_gates"]
        assert "G10" in summary["not_run_gates"]

    def test_pending_step_is_not_run_not_passed(self, tmp_path):
        """``pending`` is written by add_step before a step runs."""
        summary = _summary(tmp_path, _all_steps_completed(**{
            "integration-test": "pending"}))
        assert _gate(summary, "G7")["status"] == "not-run"


class TestEvidenceFreshness:
    """Defect 5 — artifacts left over from an earlier run must read stale."""

    def test_foreign_session_artifact_is_stale(self, tmp_path):
        (tmp_path / "integration-test.json").write_text(json.dumps({
            "session": "some-earlier-run", "step": "integration-test",
            "status": "passed",
        }), encoding="utf-8")
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G7")["status"] == "stale"
        assert summary["stale_gates"] == ["G7"]
        assert summary["worst_gate_status"] == "stale"

    def test_matching_session_artifact_is_current(self, tmp_path):
        _write_all_artifacts(tmp_path, **{"integration-test": json.dumps({
            "session": "test-sess", "step": "integration-test",
            "status": "passed",
        })})
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G7")["status"] == "passed"
        assert summary["stale_gates"] == []

    def test_artifact_without_session_field_is_not_stale(self, tmp_path):
        """Legacy/unknown schemas must not gain a verdict they did not earn."""
        _write_all_artifacts(tmp_path, **{
            "integration-test": json.dumps({"tests_passed": 3})})
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G7")["status"] == "passed"

    def test_reusable_step_reuse_is_not_stale(self, tmp_path):
        """spec-check is in REUSABLE_STEPS — an older session is by design."""
        _write_all_artifacts(tmp_path, **{"spec-check": json.dumps({
            "session": "some-earlier-run", "coverage": {"score": 100.0},
        })})
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G1")["status"] == "passed"
        assert summary["stale_gates"] == []

    def test_stale_outranks_skipped_and_not_run(self, tmp_path):
        (tmp_path / "integration-test.json").write_text(json.dumps({
            "session": "old-run", "status": "skipped",
        }), encoding="utf-8")
        (tmp_path / "misra-review.json").write_text(json.dumps({
            "session": "old-run", "status": "skipped",
        }), encoding="utf-8")
        summary = _summary(tmp_path, _all_steps_completed())
        assert _gate(summary, "G7")["status"] == "stale"
        assert summary["worst_gate_status"] == "stale"

    def test_verdict_helper_honours_expected_session(self, tmp_path):
        (tmp_path / "integration-test.json").write_text(json.dumps({
            "session": "old-run", "status": "passed",
        }), encoding="utf-8")
        assert _artifact_verdict(tmp_path, "integration-test", "new-run") == "stale"
        assert _artifact_verdict(tmp_path, "integration-test", "old-run") == ""
        assert _artifact_verdict(tmp_path, "integration-test") == ""


class TestClassifyRunOutcome:
    """Defect 5/6 consumer — GREEN requires gate evidence, not just completion."""

    @pytest.fixture(autouse=True)
    def _no_env_na(self, monkeypatch):
        """Keep an ambient OSH_NA_GATES out of every case but the env one."""
        monkeypatch.delenv("OSH_NA_GATES", raising=False)

    def _summary_dict(self, worst, gates):
        return {"worst_gate_status": worst, "gates": gates}

    def test_green_requires_every_gate_passed(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "passed", [{"gate": "G1", "status": "passed"}]))
        assert v["outcome"] == "green"

    def test_stale_gate_is_unverified(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "stale", [{"gate": "G1", "status": "passed"},
                      {"gate": "G7", "status": "stale"}]))
        assert v["outcome"] == "unverified"
        assert "G7=stale" in v["reason"]
        assert v["blocking_gates"] == [{"gate": "G7", "status": "stale"}]

    def test_skipped_gate_is_unverified_not_green(self):
        """The exact run 57fa80e754ed shape: no failure, but not verified."""
        v = classify_run_outcome("completed", [], self._summary_dict(
            "skipped", [{"gate": "G7", "status": "skipped"}]))
        assert v["outcome"] == "unverified"

    def test_advisory_gate_does_not_block_green(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "passed", [{"gate": "G1", "status": "passed"},
                       {"gate": "G4", "status": "skipped", "advisory": True}]))
        assert v["outcome"] == "green"

    def test_missing_gate_summary_is_unverified(self):
        assert classify_run_outcome("completed", [], {})["outcome"] == "unverified"
        assert classify_run_outcome("completed", [], None)["outcome"] == "unverified"

    def test_failed_session_is_red(self):
        v = classify_run_outcome("failed", ["boom"],
                                 self._summary_dict("failed", []))
        assert v["outcome"] == "red"

    def test_step_errors_are_unverified(self):
        v = classify_run_outcome("completed", ["verdict failed"],
                                 self._summary_dict(
                                     "passed", [{"gate": "G1", "status": "passed"}]))
        assert v["outcome"] == "unverified"
        assert "verdict failure" in v["reason"]


class TestDeclaredNotApplicable:
    """A run must *state* which gates don't apply — never infer it.

    Planning mode never generates code (G3 n/a), a board with no emulator has
    nothing to emulate (G7 n/a).  Both look identical to "nobody ran it" at
    the evidence level, so the caller declares it and the declaration is
    recorded.  The exemption is deliberately narrow: it never covers stale
    evidence or a real failure.
    """

    def _summary_dict(self, worst, gates):
        return {"worst_gate_status": worst, "gates": gates}

    @pytest.fixture(autouse=True)
    def _no_env_na(self, monkeypatch):
        monkeypatch.delenv("OSH_NA_GATES", raising=False)

    def test_declared_na_gate_does_not_block_green(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "skipped", [{"gate": "G1", "status": "passed"},
                        {"gate": "G3", "status": "skipped"}]),
            na_gates=["G3"])
        assert v["outcome"] == "green"
        assert v["declared_na"] == ["G3"]
        assert v["blocking_gates"] == []

    def test_not_run_gate_can_also_be_declared_na(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "not-run", [{"gate": "G1", "status": "passed"},
                        {"gate": "G7", "status": "not-run"}]),
            na_gates=["G7"])
        assert v["outcome"] == "green"

    def test_declared_na_never_excuses_stale_evidence(self):
        """The exact failure this module exists to catch, declared away."""
        v = classify_run_outcome("completed", [], self._summary_dict(
            "stale", [{"gate": "G7", "status": "stale"}]),
            na_gates=["G7"])
        assert v["outcome"] == "unverified"
        assert v["blocking_gates"] == [{"gate": "G7", "status": "stale"}]

    def test_declared_na_never_excuses_failure(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "failed", [{"gate": "G7", "status": "failed"}]),
            na_gates=["G7"])
        assert v["outcome"] == "unverified"

    def test_undeclared_skipped_gate_still_blocks(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "skipped", [{"gate": "G3", "status": "skipped"}]))
        assert v["outcome"] == "unverified"
        assert v["declared_na"] == []

    def test_na_gates_read_from_environment(self, monkeypatch):
        monkeypatch.setenv("OSH_NA_GATES", "g3, G5")
        v = classify_run_outcome("completed", [], self._summary_dict(
            "skipped", [{"gate": "G3", "status": "skipped"},
                        {"gate": "G5", "status": "not-run"}]))
        assert v["outcome"] == "green"
        assert v["declared_na"] == ["G3", "G5"]

    def test_na_gates_read_from_session_config(self):
        v = classify_run_outcome("completed", [], self._summary_dict(
            "skipped", [{"gate": "G3", "status": "skipped"}]),
            config={"na_gates": ["G3"]})
        assert v["outcome"] == "green"

    def test_declared_na_gates_helper(self, monkeypatch):
        from yuleosh.pipeline.gates import declared_na_gates

        monkeypatch.delenv("OSH_NA_GATES", raising=False)
        assert declared_na_gates(None) == set()
        assert declared_na_gates({"na_gates": "g3, g4"}) == {"G3", "G4"}
        assert declared_na_gates({"na_gates": ["G1"]}) == {"G1"}
        assert declared_na_gates({"na_gates": []}) == set()
        monkeypatch.setenv("OSH_NA_GATES", "G9")
        assert declared_na_gates({}) == {"G9"}
        # session.config 优先于环境变量
        assert declared_na_gates({"na_gates": ["G2"]}) == {"G2"}


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
