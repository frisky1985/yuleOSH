
# @tests src/yuleosh/pipeline/gates.py, src/yuleosh/cli/commands/consistency.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""P0 regressions (2026-09-23): gate evidence reachability, integrity
coverage, and "no artifact ⇒ no pass".

Three defects, all confirmed against run ``57fa80e754ed`` (24/24 steps
``completed``, ``worst_gate_status=skipped``, reported as GREEN until the
outcome classifier was fixed):

* **P0-A — the gate never opened its step's artifact.**  ``_ARTIFACT_CANDIDATES``
  listed 4 of the 11 steps whose artifact name differs from ``<step_key>.json``,
  so 7 steps were judged purely on the orchestrator's own bookkeeping.  G10 was
  the sharp edge: ``ci/gate_policy.py`` blocks on ``test-qualification``, whose
  only evidence is ``qualification-test.json`` — a file no gate had ever read.
  Reverting the table makes ``TestCandidateTableIsReachable`` fail.

* **P0-B — the integrity fingerprint covered 14 of 50 artifacts.**
  ``write_gate_summary`` hashed ``<step_key>.json`` and never consulted the
  candidate table, so G5/G8/G9/G10 carried an *empty* ``artifact_hashes``, and
  ``artifact_index`` (the session-wide index) did not exist at all — meaning
  ``c-coverage-gate.json`` (a GATE_BLOCK step), the 12 ``review-*.json``
  sub-reports and ``ctest-junit.xml`` could be rewritten without
  ``consistency`` noticing.  Reverting makes
  ``TestIntegrityIndexCoverage`` / ``TestFingerprintConsumer`` fail.

* **P0-C — "artifact missing" and "artifact passed" were the same
  observation.**  A step recorded ``completed`` kept that status even when no
  artifact existed, so deleting a step's evidence left its gate green.
  Reverting makes ``TestNoArtifactIsNotAPass`` fail.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.cli.commands.consistency import (
    _compute_session_fingerprint,
    _load_session_summary,
)
from yuleosh.pipeline.gates import (
    GATES,
    _ARTIFACT_CANDIDATES,
    _apply_artifact_overlay,
    artifact_index,
    write_gate_summary,
)


def _pipeline_keys() -> list[str]:
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    return [e[0] if isinstance(e, (tuple, list)) else e for e in PIPELINE_STEPS]


def _gate_of(step_key: str) -> str:
    return next(g["gate"] for g in GATES if step_key in g["step_keys"])


def _summary(tmp_path, steps, session="test-sess"):
    out = write_gate_summary(
        SimpleNamespace(name=session, session_dir=tmp_path, steps=steps))
    return json.loads(Path(out).read_text())


def _gate(summary, key):
    return next(g for g in summary["gates"] if g["gate"] == key)


def _write_all(tmp_path, session="test-sess", **override):
    """Write one artifact per pipeline step (candidate name where applicable)."""
    default = json.dumps({"session": session, "status": "passed"})
    for key in _pipeline_keys():
        name = _ARTIFACT_CANDIDATES.get(key, (f"{key}.json",))[0]
        (tmp_path / name).write_text(override.get(key, default), encoding="utf-8")


def _all_completed():
    return [{"name": k, "status": "completed"} for k in _pipeline_keys()]


# ── P0-A ────────────────────────────────────────────────────────────────

class TestCandidateTableIsReachable:
    """Every step whose artifact name differs from ``<step_key>.json`` must be
    listed, and the listed keys must be real steps (no dangling entries)."""

    def test_candidate_keys_are_real_pipeline_steps(self):
        """撤销则：漏列无影响，但错列会在此暴露（表与 registry 分叉）。"""
        keys = set(_pipeline_keys())
        assert set(_ARTIFACT_CANDIDATES) <= keys, (
            f"unknown step keys in candidate table: "
            f"{sorted(set(_ARTIFACT_CANDIDATES) - keys)}")

    def test_every_candidate_key_maps_to_a_gate(self):
        """A candidate entry for a step no gate owns would be dead weight."""
        for key in _ARTIFACT_CANDIDATES:
            assert _gate_of(key), f"{key} belongs to no gate"

    @pytest.mark.parametrize("step_key,artifact", [
        ("super-analysis", "startup-analysis.md"),
        ("prd", "prd.md"),
        ("architecture", "architecture.md"),
        ("development", "development-plan.md"),
        ("test-planning", "test-plan.md"),
    ])
    def test_markdown_candidates_are_read(self, tmp_path, step_key, artifact):
        """A skip banner in these artifacts must reach the gate.

        撤销修复（从 _ARTIFACT_CANDIDATES 删掉该条目）→ 门禁退回
        session.steps 的 ``completed`` → 断言 ``skipped`` 失败。
        """
        (tmp_path / artifact).write_text("# SKIPPED (mock)\n", encoding="utf-8")
        summary = _summary(tmp_path, [{"name": step_key, "status": "completed"}])
        assert _gate(summary, _gate_of(step_key))["status"] == "skipped"

    def test_qualification_test_json_is_read_by_g10(self, tmp_path):
        """G10's single piece of evidence — the GATE_BLOCK step's artifact.

        变异注入实测：从候选表删掉 ``test-qualification`` 后**本用例仍然通过**
        —— 该 JSON 自带 ``step`` 字段，会被 ``_scan_artifact_step_map`` 接住。
        因此它断言的是"G10 能读到证据"这一**结果**，而不是候选表不可替代。
        候选表的必要性由 Markdown 类用例证伪（``.md`` 没有 ``step`` 字段可扫，
        删掉条目即读不到任何东西）：见 ``test_markdown_candidates_are_read``
        与 ``test_final_report_markdown_is_read_by_g10``。
        """
        (tmp_path / "qualification-test.json").write_text(
            json.dumps({"session": "test-sess", "step": "test-qualification",
                        "status": "skipped"}), encoding="utf-8")
        summary = _summary(tmp_path,
                           [{"name": "test-qualification", "status": "completed"}])
        assert _gate(summary, "G10")["status"] == "skipped"

    def test_final_report_markdown_is_read_by_g10(self, tmp_path):
        """撤销修复（删除 final-report 候选）→ 实测本用例转红。

        ``final-report.md`` 无 ``step`` 字段可扫，候选表是唯一通路。
        """
        (tmp_path / "qualification-test.json").write_text(
            json.dumps({"session": "test-sess", "step": "test-qualification",
                        "status": "passed"}), encoding="utf-8")
        (tmp_path / "final-report.md").write_text(
            "# Final report — SKIPPED (no qualification run)\n", encoding="utf-8")
        summary = _summary(tmp_path, _all_completed())
        assert _gate(summary, "G10")["status"] == "skipped"


# ── P0-B ────────────────────────────────────────────────────────────────

AUXILIARY = (
    "c-coverage-gate.json",        # GATE_BLOCK step, maps to no gate step key
    "review-bsp.json",             # one of 12 review-* sub-reports
    "embedded-build-review.json",
    "ctest-junit.xml",
)


class TestIntegrityIndexCoverage:
    """``artifact_index`` must cover *every* artifact, not just gate-mapped ones."""

    def test_index_covers_auxiliary_artifacts(self, tmp_path):
        """撤销修复（删除 artifact_index）→ KeyError，测试失败。"""
        _write_all(tmp_path)
        for name in AUXILIARY:
            (tmp_path / name).write_text('{"ok":true}', encoding="utf-8")

        summary = _summary(tmp_path, _all_completed())

        index = summary["artifact_index"]
        assert summary["artifact_index_count"] == len(index)
        for name in AUXILIARY:
            assert name in index, f"auxiliary artifact {name} has no tamper evidence"
        assert index["merge-gate-report.json"]  # gate-mapped artifact still there
        assert len(index) > len({k for g in GATES for k in g["step_keys"]})

    def test_gate_mapped_digests_are_no_longer_empty(self, tmp_path):
        """G5/G8/G9/G10 used to emit an empty artifact_hashes.

        撤销修复（回到 ``Path(sdir) / f"{step_key}.json"``）→ 这四个门禁没有
        artifact_hashes 键 → 断言失败。
        """
        _write_all(tmp_path)
        summary = _summary(tmp_path, _all_completed())
        for gate_key in ("G5", "G8", "G9", "G10"):
            entry = _gate(summary, gate_key)
            assert entry.get("artifact_hashes"), f"{gate_key} has no digests"
            for step_key in entry["step_keys"]:
                assert entry["artifact_hashes"].get(step_key), (
                    f"{gate_key}/{step_key} resolved to no artifact")

    def test_index_excludes_self_and_session_metadata(self, tmp_path):
        """The summary cannot hash itself; session.json changes every run."""
        _write_all(tmp_path)
        (tmp_path / "session.json").write_text('{"status":"completed"}',
                                               encoding="utf-8")
        summary = _summary(tmp_path, _all_completed())
        index = summary["artifact_index"]
        assert "gate-summary.json" not in index
        assert "session.json" not in index

    def test_index_is_deterministic(self, tmp_path):
        """Same directory ⇒ same digests (fingerprints must be comparable)."""
        _write_all(tmp_path)
        assert artifact_index(tmp_path) == artifact_index(tmp_path)

    def test_nested_artifacts_are_keyed_by_relative_path(self, tmp_path):
        sub = tmp_path / "logs"
        sub.mkdir()
        (sub / "run.log").write_text("hello", encoding="utf-8")
        assert "logs/run.log" in artifact_index(tmp_path)

    def test_dot_files_are_ignored(self, tmp_path):
        """Editor/OS noise must not perturb an integrity fingerprint."""
        (tmp_path / ".DS_Store").write_text("noise", encoding="utf-8")
        _write_all(tmp_path)
        assert ".DS_Store" not in artifact_index(tmp_path)


class TestFingerprintConsumer:
    """``consistency`` must fingerprint the live directory, and stay readable
    for old summaries that only carry per-gate digests."""

    def test_live_scan_outranks_archived_snapshot(self, tmp_path):
        _write_all(tmp_path)
        (tmp_path / "c-coverage-gate.json").write_text('{"gate_passed":true}',
                                                      encoding="utf-8")
        summary = _summary(tmp_path, _all_completed())
        loaded = _load_session_summary(tmp_path)
        assert loaded["artifact_source"] == "live_scan"
        assert "c-coverage-gate.json" in loaded["artifact_hashes"]
        assert summary["artifact_index_count"] == len(loaded["artifact_hashes"])

    def test_rewriting_auxiliary_artifact_changes_fingerprint(self, tmp_path):
        """The exact hole P0-B opened: an unprotected artifact could be edited
        without the baseline fingerprint moving.

        撤销修复 → 指纹只覆盖 step 产物、且只读 gate-summary 的冻结快照
        → 断言两指纹不同失败。
        """
        _write_all(tmp_path)
        aux = tmp_path / "c-coverage-gate.json"
        aux.write_text('{"gate_passed":true}', encoding="utf-8")
        _summary(tmp_path, _all_completed())          # writes gate-summary.json
        before = _compute_session_fingerprint(tmp_path)["fingerprint"]

        aux.write_text('{"gate_passed":false}', encoding="utf-8")
        after = _compute_session_fingerprint(tmp_path)["fingerprint"]
        assert before != after

    def test_rewriting_a_gate_mapped_artifact_changes_fingerprint(self, tmp_path):
        """Candidate-named artifacts count too (they had no digest before)."""
        _write_all(tmp_path)
        report = tmp_path / "merge-gate-report.json"
        _summary(tmp_path, _all_completed())
        before = _compute_session_fingerprint(tmp_path)["fingerprint"]

        report.write_text(json.dumps({"passed": False}), encoding="utf-8")
        after = _compute_session_fingerprint(tmp_path)["fingerprint"]
        assert before != after

    def test_legacy_summary_falls_back_to_per_gate_hashes(self, tmp_path):
        """Old gate-summary files stay usable (backward compatibility)."""
        (tmp_path / "gate-summary.json").write_text(json.dumps({
            "schema": "gate-summary-v1",
            "gates": [{"gate": "G1", "artifact_hashes": {"spec-check": "abc"}}],
        }), encoding="utf-8")
        loaded = _load_session_summary(tmp_path)
        assert loaded["artifact_source"] == "gate_artifact_hashes"
        assert loaded["artifact_hashes"] == {"spec-check": "abc"}


# ── P0-C ────────────────────────────────────────────────────────────────

class TestNoArtifactIsNotAPass:
    """A self-reported success with no artifact must not count as evidence."""

    def test_complete_run_with_evidence_is_green(self, tmp_path):
        """Control case — the downgrade must not fire when artifacts exist."""
        _write_all(tmp_path)
        summary = _summary(tmp_path, _all_completed())
        assert summary["worst_gate_status"] == "passed"
        assert summary["not_run_gates"] == []

    def test_deleting_an_artifact_downgrades_its_gate(self, tmp_path):
        """撤销修复 → 门禁仍 passed（删证据不改变结论）→ 断言失败。"""
        _write_all(tmp_path)
        assert _gate(_summary(tmp_path, _all_completed()), "G9")["status"] == "passed"

        (tmp_path / "merge-gate-report.json").unlink()
        summary = _summary(tmp_path, _all_completed())
        assert _gate(summary, "G9")["status"] == "not-run"
        assert "G9" in summary["not_run_gates"]

    def test_overlay_reports_downgraded_steps(self, tmp_path):
        statuses = {"merge-gate": "completed", "misra-review": "completed"}
        downgraded = _apply_artifact_overlay(statuses, tmp_path)
        assert downgraded == ["merge-gate", "misra-review"]
        assert statuses == {"merge-gate": "not-run", "misra-review": "not-run"}

    def test_unparsable_artifact_is_not_downgraded(self, tmp_path):
        """A present-but-broken artifact is not *missing* — no downgrade."""
        (tmp_path / "merge-gate-report.json").write_text("{not json",
                                                        encoding="utf-8")
        summary = _summary(tmp_path,
                           [{"name": "merge-gate", "status": "completed"}])
        assert _gate(summary, "G9")["status"] == "passed"

    def test_artifact_found_via_its_own_step_field(self, tmp_path):
        """Some artifacts carry their producer in ``step`` under a name the
        candidate table cannot express; they must still count as evidence."""
        (tmp_path / "c-unit-result.json").write_text(json.dumps({
            "step": "c-unit-test", "session": "test-sess",
            "status": "skipped"}), encoding="utf-8")
        summary = _summary(tmp_path,
                           [{"name": "c-unit-test", "status": "completed"}])
        assert _gate(summary, "G6")["status"] == "skipped"

    def test_reusable_step_without_artifact_is_exempt(self, tmp_path):
        """spec-check reuses an earlier run's artifact, so an absent file in
        this session is by design — not a missing evidence."""
        statuses = {"spec-check": "completed"}
        assert _apply_artifact_overlay(statuses, tmp_path) == []
        assert statuses == {"spec-check": "completed"}

    def test_failed_step_without_artifact_stays_failed(self, tmp_path):
        """The downgrade only applies to *success* claims (fail-closed)."""
        summary = _summary(tmp_path, [{"name": "merge-gate", "status": "failed"}])
        assert _gate(summary, "G9")["status"] == "failed"
