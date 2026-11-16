"""AUD-ASPICE-001 B4 回归：证据包（ReqIF / 签批 / AST 追溯 / D-01 / D-02）。"""

# @tests src/yuleosh/evidence/reqif.py, src/yuleosh/evidence/signoff.py,
#        src/yuleosh/evidence/ast_trace.py, src/yuleosh/ci/kpi/report.py,
#        src/yuleosh/pipeline/step_handlers/sys_layer.py, src/yuleosh/pipeline/gates.py

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.ci.kpi.report import kpi_status
from yuleosh.evidence.ast_trace import scan_source, validate
from yuleosh.evidence.reqif import export_reqif, parse_reqif
from yuleosh.evidence.signoff import (
    latest,
    record_signoff,
    required_signoff_status,
    verify_gate,
)
from yuleosh.pipeline.gates import classify_run_outcome

SPEC = """# LED Blink Demo

## 1. 概述
演示。

### SR-001
The system SHALL blink the LED every 1000 ms via the HAL.

### SR-002
The system SHALL select LED state through hal_led_toggle.

## 场景
- Scenario: 上电后闪灯
"""


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs" / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(SPEC, encoding="utf-8")
    return spec


class TestReqifExport:
    def test_export_is_valid_and_roundtrips(self, tmp_path):
        spec = _write_spec(tmp_path)
        out = tmp_path / "out" / "requirements.reqif"
        result = export_reqif(spec, out)
        assert result["valid"] is True
        assert result["objects"] >= 2
        parsed = parse_reqif(out)
        assert parsed["valid"] is True
        text = out.read_text(encoding="utf-8")
        assert "SR-001" in text and "REQ-IF" in text

    def test_ids_are_unique(self, tmp_path):
        spec = _write_spec(tmp_path)
        out = tmp_path / "r.reqif"
        export_reqif(spec, out)
        ids = parse_reqif(out)["ids"]
        assert len(ids) == len(set(ids))

    def test_empty_spec_is_invalid(self, tmp_path):
        spec = tmp_path / "empty.md"
        spec.write_text("# nothing here\n", encoding="utf-8")
        result = export_reqif(spec, tmp_path / "r.reqif")
        assert result["valid"] is False
        assert result["objects"] == 0

    def test_parse_rejects_broken_xml(self, tmp_path):
        broken = tmp_path / "bad.reqif"
        broken.write_text("<REQ-IF><oops>", encoding="utf-8")
        assert parse_reqif(broken)["valid"] is False


class TestSignoff:
    def test_approved_signoff_is_valid(self, tmp_path):
        artifact = tmp_path / "docs" / "req.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("# requirements\n", encoding="utf-8")

        record_signoff(tmp_path, "G1", artifact, reviewer="alice",
                       role="requirements-owner", tag=False)
        assert verify_gate(tmp_path, "G1")["signed"] is True
        assert latest(tmp_path, "G1")["reviewer"] == "alice"

    def test_artifact_change_invalidates_signoff(self, tmp_path):
        artifact = tmp_path / "req.md"
        artifact.write_text("v1", encoding="utf-8")
        record_signoff(tmp_path, "G1", artifact, reviewer="alice", tag=False)
        artifact.write_text("v2 changed after approval", encoding="utf-8")
        verdict = verify_gate(tmp_path, "G1")
        assert verdict["signed"] is False
        assert "digest mismatch" in verdict["reason"]

    def test_missing_signoff_is_not_signed(self, tmp_path):
        assert verify_gate(tmp_path, "G2")["signed"] is False

    def test_reviewer_identity_is_required(self, tmp_path):
        artifact = tmp_path / "a.md"
        artifact.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            record_signoff(tmp_path, "G1", artifact, reviewer="  ", tag=False)

    def test_rejected_decision_is_not_signed(self, tmp_path):
        artifact = tmp_path / "a.md"
        artifact.write_text("x", encoding="utf-8")
        record_signoff(tmp_path, "G1", artifact, reviewer="bob",
                       decision="rejected", tag=False)
        assert verify_gate(tmp_path, "G1")["signed"] is False

    def test_missing_artifact_cannot_be_signed(self, tmp_path):
        with pytest.raises(ValueError):
            record_signoff(tmp_path, "G1", tmp_path / "nope.md",
                           reviewer="alice", tag=False)

    def test_required_status_reports_both_gates(self, tmp_path):
        status = required_signoff_status(tmp_path)
        assert set(status) == {"G1", "G2"}
        assert all(not v["signed"] for v in status.values())

    def test_cli_record_and_verify(self, tmp_path, capsys):
        from yuleosh.evidence.signoff import _main

        artifact = tmp_path / "a.md"
        artifact.write_text("baseline", encoding="utf-8")
        assert _main(["record", "--project", str(tmp_path), "--gate", "G1",
                      "--artifact", str(artifact), "--reviewer", "alice",
                      "--no-tag"]) == 0
        capsys.readouterr()
        assert _main(["verify", "--project", str(tmp_path), "--gate", "G1"]) == 0
        capsys.readouterr()
        assert _main(["verify", "--project", str(tmp_path), "--gate", "G2"]) == 1


class TestAgentPreReview:
    """agent 预审 + 人批准：agent 有否决权，没有放行权（CL2 责任分层）。"""

    def _artifact(self, tmp_path: Path) -> Path:
        artifact = tmp_path / "docs" / "prd.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# prd baseline\n", encoding="utf-8")
        return artifact

    def test_agent_identity_cannot_sign(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        artifact = self._artifact(tmp_path)
        rec = write_recommendation(tmp_path, "G1", [artifact])
        for agent_name in ("agent:arch-reviewer", "AI:independent", "bot/ci"):
            with pytest.raises(ValueError):
                record_signoff(tmp_path, "G1", artifact, reviewer=agent_name,
                               based_on_recommendation=rec, tag=False)

    def test_recommendation_alone_never_turns_gate_green(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        artifact = self._artifact(tmp_path)
        rec = write_recommendation(tmp_path, "G1", [artifact],
                                   independence="isolated")
        assert json.loads(rec.read_text(encoding="utf-8"))["verdict"] == \
            "recommend-approve"
        assert verify_gate(tmp_path, "G1")["signed"] is False
        verdict = classify_run_outcome(
            "completed", [], {
                "worst_gate_status": "passed",
                "gates": [{"gate": "G1", "status": "passed"},
                          {"gate": "G2", "status": "passed"}],
            },
            signoffs={"G1": verify_gate(tmp_path, "G1"),
                      "G2": {"signed": False, "reason": "no sign-off record"}})
        assert verdict["outcome"] == "awaiting-signoff"

    def test_human_signoff_referencing_recommendation_is_traceable(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        artifact = self._artifact(tmp_path)
        rec = write_recommendation(tmp_path, "G1", [artifact],
                                   independence="isolated")
        record_signoff(tmp_path, "G1", artifact, reviewer="alice",
                       role="requirements-owner", tag=False,
                       based_on_recommendation=rec)
        verdict = verify_gate(tmp_path, "G1")
        assert verdict["signed"] is True
        assert verdict["basis"]["verdict"] == "recommend-approve"
        assert verdict["basis"]["intact"] is True

    def test_override_of_reject_requires_reason(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        artifact = self._artifact(tmp_path)
        rec = write_recommendation(tmp_path, "G1", [artifact],
                                   blocking=["G1 gate status is skipped"])
        assert json.loads(rec.read_text(encoding="utf-8"))["verdict"] == \
            "recommend-reject"
        with pytest.raises(ValueError):
            record_signoff(tmp_path, "G1", artifact, reviewer="alice",
                           based_on_recommendation=rec, tag=False)
        record = record_signoff(tmp_path, "G1", artifact, reviewer="alice",
                                based_on_recommendation=rec, tag=False,
                                override_reason="blocker 已关闭，见 CR-42")
        assert record["override_reason"] == "blocker 已关闭，见 CR-42"
        assert verify_gate(tmp_path, "G1")["basis"]["verdict"] == \
            "recommend-reject"

    def test_tampered_recommendation_breaks_signoff(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        artifact = self._artifact(tmp_path)
        rec = write_recommendation(tmp_path, "G1", [artifact])
        record_signoff(tmp_path, "G1", artifact, reviewer="alice", tag=False,
                       based_on_recommendation=rec)
        assert verify_gate(tmp_path, "G1")["signed"] is True
        body = json.loads(rec.read_text(encoding="utf-8"))
        body["verdict"] = "recommend-approve"
        body["blocking_items"] = []
        body["notes"] = "rewritten after approval"
        rec.write_text(json.dumps(body, indent=2), encoding="utf-8")
        verdict = verify_gate(tmp_path, "G1")
        assert verdict["signed"] is False
        assert "recommendation changed" in verdict["reason"]

    def test_missing_artifact_becomes_blocking(self, tmp_path):
        from yuleosh.evidence.signoff import write_recommendation

        rec = write_recommendation(tmp_path, "G2",
                                   [tmp_path / "docs" / "missing.md"])
        body = json.loads(rec.read_text(encoding="utf-8"))
        assert body["verdict"] == "recommend-reject"
        assert any("artifact missing" in b for b in body["blocking_items"])
        assert body["release_authority"] == "none"

    def test_pipeline_writes_recommendation_for_unsigned_gates(self, tmp_path):
        from yuleosh.pipeline.orchestrator import _prepare_signoff_recommendations

        artifact = self._artifact(tmp_path)
        session = SimpleNamespace(
            project_dir=str(tmp_path),
            steps=[{"name": "prd", "output_path": str(artifact)}],
            verification_independence={})
        written = _prepare_signoff_recommendations(
            session, {"gates": [{"gate": "G1", "status": "passed"},
                                {"gate": "G2", "status": "skipped"}]},
            {"G1": {"signed": False, "reason": "no sign-off record"},
             "G2": {"signed": True}})
        assert set(written) == {"G1"}
        body = json.loads(Path(written["G1"]).read_text(encoding="utf-8"))
        assert body["verdict"] == "recommend-reject"
        assert body["artifacts"][0]["sha256"]
        assert "no sign-off record" in " ".join(body["blocking_items"])

    def test_cli_recommend_then_record(self, tmp_path, capsys):
        from yuleosh.evidence.signoff import _main

        artifact = self._artifact(tmp_path)
        assert _main(["recommend", "--project", str(tmp_path), "--gate", "G1",
                      "--artifact", str(artifact)]) == 0
        rec = Path(capsys.readouterr().out.strip())
        assert rec.is_file()
        assert _main(["record", "--project", str(tmp_path), "--gate", "G1",
                      "--artifact", str(artifact), "--reviewer", "alice",
                      "--based-on-recommendation", str(rec),
                      "--no-tag"]) == 0
        capsys.readouterr()
        assert _main(["verify", "--project", str(tmp_path), "--gate", "G1"]) == 0


class TestGateAwaitingSignoff:
    SUMMARY = {
        "worst_gate_status": "passed",
        "gates": [{"gate": "G1", "status": "passed"},
                  {"gate": "G2", "status": "passed"}],
    }

    def test_green_requires_signoff_in_cl2(self):
        verdict = classify_run_outcome(
            "completed", [], self.SUMMARY,
            signoffs={"G1": {"signed": False, "reason": "no sign-off record"},
                      "G2": {"signed": True}},
        )
        assert verdict["outcome"] == "awaiting-signoff"
        assert any(b["gate"] == "G1" and b["status"] == "awaiting-signoff"
                   for b in verdict["blocking_gates"])

    def test_signed_gates_can_be_green(self):
        verdict = classify_run_outcome(
            "completed", [], self.SUMMARY,
            signoffs={"G1": {"signed": True}, "G2": {"signed": True}},
        )
        assert verdict["outcome"] == "green"

    def test_no_signoff_input_keeps_legacy_behaviour(self):
        assert classify_run_outcome("completed", [], self.SUMMARY)["outcome"] == "green"


class TestAstTrace:
    FAKE = """// @req SR-001
static int helper(void) {
    return 0;
}
"""

    REAL = """// @req SR-001
int led_blink_1000ms(void) {
    hal_led_toggle(1);
    return 0;
}
"""

    def test_fake_annotation_is_flagged(self, tmp_path):
        spec = _write_spec(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "fake.c").write_text(self.FAKE, encoding="utf-8")
        report = validate(tmp_path, spec)
        assert report["status"] == "failed"
        assert report["findings"][0]["rule"] == "TRACE-UNSUBSTANTIATED"

    def test_real_implementation_passes(self, tmp_path):
        spec = _write_spec(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "real.c").write_text(self.REAL, encoding="utf-8")
        report = validate(tmp_path, spec)
        assert report["status"] == "passed"

    def test_unknown_requirement_is_flagged(self, tmp_path):
        spec = _write_spec(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "unknown.c").write_text(
            "// @req SR-999\nint blink_led(void) { return 1; }\n", encoding="utf-8")
        report = validate(tmp_path, spec)
        assert any(f["rule"] == "TRACE-UNKNOWN-REQ" for f in report["findings"])

    def test_no_annotations_is_not_run(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "plain.c").write_text("int f(void) { return 0; }\n", encoding="utf-8")
        assert validate(tmp_path, None)["status"] == "not-run"

    def test_scan_skips_test_and_artifact_dirs(self, tmp_path):
        for sub in ("tests", "artifacts/x"):
            d = tmp_path / sub
            d.mkdir(parents=True)
            (d / "t.c").write_text(self.FAKE, encoding="utf-8")
        assert scan_source(self.FAKE, "src/fake.c")[0].requirements == ["SR-001"]
        assert validate(tmp_path, None)["status"] == "not-run"


class TestD01MeasurementEvidence:
    def test_missing_misra_report_is_insufficient_not_pass(self, tmp_path):
        data = json.loads(kpi_status(str(tmp_path), as_json=True))
        misra = [e for e in data["entries"] if e["metric"].startswith("misra_")]
        assert misra, "misra entries must always be reported"
        assert all(e["status"] == "INSUFFICIENT-EVIDENCE" for e in misra)
        assert "misra_total_violations" in data["insufficient_evidence"]

    def test_markdown_does_not_claim_all_pass_without_evidence(self, tmp_path):
        md = kpi_status(str(tmp_path), as_json=False)
        assert "ALL PASS" not in md


class TestD02SysSpecAlignment:
    def test_sys_requirements_bind_spec_ids_and_align(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.sys_layer import step_sys_requirements

        spec = _write_spec(tmp_path)
        session = SimpleNamespace(project_dir=str(tmp_path), spec_path=str(spec))
        out = step_sys_requirements(session)

        doc = Path(out).read_text(encoding="utf-8")
        assert "SR-001" in doc and "SR-002" in doc
        assert "双向比对" in doc

        align = json.loads(
            (tmp_path / ".osh" / "evidence" / "sys-spec-alignment.json")
            .read_text(encoding="utf-8"))
        assert align["bidirectional_ok"] is True
        assert align["missing_in_sys"] == []
        assert align["missing_in_spec"] == []
        assert set(align["sys_to_spec"].values()) == {"SR-001", "SR-002"}
