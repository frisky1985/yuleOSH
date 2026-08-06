"""Unit tests for yuleosh.report.audit_report (v3.4.2 Wave 1 C5).

Covers:
  - EvidenceItem / ProcessDimension / AspiceReport dataclasses
  - EvidenceScanner: scan_all (missing dir, corrupt files, dict/list),
    _classify_evidence (process field, type mappings, path fallback),
    _classify_system, _to_evidence_item
  - AuditReportGenerator.generate_aspice_report: scoring (E3/E2/E1/NI 证据覆盖度分级,
    P0-4 — 非 ASPICE 能力等级), dedup, findings, supplementary sources, recommendations
  - exports: json/html/text/pdf (with/without weasyprint)
  - main() CLI
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.report.audit_report import (
    EvidenceItem,
    ProcessDimension,
    AspiceReport,
    EvidenceScanner,
    AuditReportGenerator,
    main,
)


def _ev(process="", etype="", status="passed", title="T", ref="R1", **kw):
    d = {"process": process, "type": etype, "status": status,
         "title": title, "id": ref}
    d.update(kw)
    return d


# ── Dataclasses ───────────────────────────────────────────────────────

class TestDataclasses:
    def test_evidence_item_defaults(self):
        """GIVEN minimal EvidenceItem THEN defaults applied."""
        e = EvidenceItem(process="SWE.1", category="spec", title="t",
                         ref_id="r", path="p", status="passed")
        assert e.status == "passed"
        assert e.details == ""
        assert e.evidence_type == "test"

    def test_evidence_item_to_dict(self):
        """GIVEN EvidenceItem WHEN to_dict THEN fields serialized."""
        e = EvidenceItem(process="SWE.1", category="spec", title="t",
                         ref_id="r", path="p", status="passed")
        d = e.to_dict()
        assert d["process"] == "SWE.1" and d["status"] == "passed"

    def test_process_dimension_to_dict(self):
        """GIVEN ProcessDimension WHEN to_dict THEN evidence list included."""
        dim = ProcessDimension(process_id="SWE.1", title="SWE.1",
                               score="E2", coverage_pct=75.0,
                               evidence_count=2, gap_count=0,
                               findings=[], evidences=[_ev()])
        d = dim.to_dict()
        assert d["score"] == "E2"
        assert d["evidences"] == [_ev()]

    def test_aspice_report_to_dict(self):
        """GIVEN AspiceReport WHEN to_dict THEN nested dims serialized."""
        dim = ProcessDimension(process_id="SWE.1", title="t", score="NI",
                               coverage_pct=0.0, evidence_count=0,
                               gap_count=1, findings=[], evidences=[])
        r = AspiceReport(project_name="P", version="1.0", generated_at="g",
                         report_id="id", overall_score="NI",
                         overall_coverage_pct=0.0, total_evidences=0,
                         total_gaps=1, dimensions=[dim],
                         summary_by_process={}, recommendations=[])
        d = r.to_dict()
        assert d["project_name"] == "P"
        assert d["dimensions"] == [dim.to_dict()]


# ── EvidenceScanner ───────────────────────────────────────────────────

class TestEvidenceScanner:
    def test_scan_missing_dir(self, tmp_path):
        """GIVEN missing evidence dir WHEN scan_all THEN empty per process."""
        scanner = EvidenceScanner(str(tmp_path / "ghost"))
        result = scanner.scan_all()
        assert set(result) == set(EvidenceScanner.PROCESS_DIMENSIONS)
        assert all(v == [] for v in result.values())

    def test_scan_ignores_corrupt_json(self, tmp_path):
        """GIVEN corrupt json file WHEN scan_all THEN skipped with warning."""
        ev_dir = tmp_path / "evidence"
        (ev_dir / "sub").mkdir(parents=True)
        (ev_dir / "sub" / "bad.json").write_text("{not json")
        with mock.patch("yuleosh.report.audit_report.log") as mlog:
            result = EvidenceScanner(str(ev_dir)).scan_all()
        assert all(v == [] for v in result.values())
        mlog.warning.assert_called()

    def test_scan_classifies_by_process_field(self, tmp_path):
        """GIVEN evidence with explicit process WHEN scan_all THEN bucketed."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        (ev_dir / "a.json").write_text(json.dumps(
            _ev(process="SWE.4", etype="unit_test")))
        result = EvidenceScanner(str(ev_dir)).scan_all()
        assert len(result["SWE.4"]) == 1

    def test_scan_list_file(self, tmp_path):
        """GIVEN JSON list file WHEN scan_all THEN each item classified."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        (ev_dir / "many.json").write_text(json.dumps([
            _ev(process="SWE.1"), _ev(process="SWE.2")]))
        result = EvidenceScanner(str(ev_dir)).scan_all()
        assert len(result["SWE.1"]) == 1
        assert len(result["SWE.2"]) == 1

    def test_classify_by_type_mapping(self):
        """GIVEN type-based evidence WHEN classify THEN mapped dimension."""
        scanner = EvidenceScanner(str(Path("/tmp/nonexistent")))
        assert scanner._classify_evidence(_ev(etype="requirement"), Path("x")) == "SWE.1"
        assert scanner._classify_evidence(_ev(etype="architecture"), Path("x")) == "SWE.2"
        assert scanner._classify_evidence(_ev(etype="code"), Path("x")) == "SWE.3"
        assert scanner._classify_evidence(_ev(etype="coverage"), Path("x")) == "SWE.4"
        assert scanner._classify_evidence(_ev(etype="integration"), Path("x")) == "SWE.5"
        assert scanner._classify_evidence(_ev(etype="acceptance"), Path("x")) == "SWE.6"
        assert scanner._classify_evidence(_ev(etype="plan"), Path("x")) == "MAN.3"
        assert scanner._classify_evidence(_ev(etype="audit"), Path("x")) == "SUP.1"
        assert scanner._classify_evidence(_ev(etype="defect"), Path("x")) == "SUP.9"
        assert scanner._classify_evidence(_ev(etype="change_request"), Path("x")) == "SUP.10"

    def test_classify_system_evidence(self):
        """GIVEN system_requirement WHEN classify THEN SYS.1 by default."""
        scanner = EvidenceScanner(str(Path("/tmp/nonexistent")))
        assert scanner._classify_evidence(
            _ev(etype="system_requirement"), Path("data/x.json")) == "SYS.1"
        assert scanner._classify_evidence(
            _ev(etype="system_analysis"), Path("reports/sys.3-arch.json")) == "SYS.3"

    def test_classify_path_fallback(self):
        """GIVEN unknown type but path hints WHEN classify THEN dimension."""
        scanner = EvidenceScanner(str(Path("/tmp/nonexistent")))
        assert scanner._classify_evidence({"type": "weird"}, Path("swe.4-notes.json")) == "SWE.4"
        assert scanner._classify_evidence({"type": "weird"}, Path("swe.5.json")) == "SWE.5"
        assert scanner._classify_evidence({"type": "weird"}, Path("random.json")) is None

    def test_classify_non_dict(self):
        """GIVEN non-dict evidence WHEN classify THEN None."""
        scanner = EvidenceScanner(str(Path("/tmp/nonexistent")))
        assert scanner._classify_evidence([1, 2], Path("x")) is None

    def test_classify_system_sub(self):
        """GIVEN sys path variants WHEN _classify_system THEN matched."""
        scanner = EvidenceScanner(str(Path("/tmp/nonexistent")))
        assert scanner._classify_system(Path("sys.1-elicitation.json"), "x") == "SYS.1"
        assert scanner._classify_system(Path("sys.2-analysis.json"), "x") == "SYS.2"
        assert scanner._classify_system(Path("sys.4-integration.json"), "x") == "SYS.4"
        assert scanner._classify_system(Path("sys.5-qualification.json"), "x") == "SYS.5"
        assert scanner._classify_system(Path("plain.json"), "x") == "SYS.1"

    def test_to_evidence_item(self, tmp_path):
        """GIVEN raw dict WHEN _to_evidence_item THEN populated item."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        scanner = EvidenceScanner(str(ev_dir))
        f = ev_dir / "one.json"
        item = scanner._to_evidence_item(
            {"process": "SWE.1", "type": "spec", "title": "Req", "id": "r1",
             "status": "approved", "details": "d", "timestamp": "t"},
            f)
        assert item.process == "SWE.1"
        assert item.ref_id == "r1"
        assert item.path.endswith("evidence/one.json")
        assert item.status == "approved"

    def test_to_evidence_item_non_dict(self, tmp_path):
        """GIVEN non-dict WHEN _to_evidence_item THEN defaults used."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        scanner = EvidenceScanner(str(ev_dir))
        item = scanner._to_evidence_item("just-a-string", ev_dir / "s.json")
        assert item.category == "unknown"
        assert item.ref_id == "s"


# ── AuditReportGenerator ──────────────────────────────────────────────

class TestGenerateAspiceReport:
    def test_no_evidence_all_ni(self, tmp_path):
        """GIVEN no evidence WHEN generate THEN all dimensions NI."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "evidence"))
        report = gen.generate_aspice_report(project_name="P", version="1.0")
        assert report.overall_score == "NI"
        assert report.total_evidences == 0
        assert report.total_gaps == len(EvidenceScanner.PROCESS_DIMENSIONS)
        assert report.report_id.startswith("ASPICE-AUDIT-")
        assert all(d.score == "NI" for d in report.dimensions)

    def test_scoring_e3(self, tmp_path):
        """GIVEN all passing evidence WHEN generate THEN E3 (证据覆盖度高)."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        for pid in ("SWE.1", "SWE.2"):
            (ev_dir / f"{pid}.json").write_text(json.dumps(_ev(process=pid, status="passed")))
        gen = AuditReportGenerator(evidence_dir=str(ev_dir))
        report = gen.generate_aspice_report()
        dim_swe1 = next(d for d in report.dimensions if d.process_id == "SWE.1")
        assert dim_swe1.score == "E3"
        assert dim_swe1.coverage_pct == 100.0

    def test_scoring_e1_and_findings(self, tmp_path):
        """GIVEN partial failures WHEN generate THEN E1 + failed findings."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        (ev_dir / "swe1.json").write_text(json.dumps([
            _ev(process="SWE.1", status="passed", ref="r1"),
            _ev(process="SWE.1", status="failed", ref="r2"),
            _ev(process="SWE.1", status="passed", ref="r3"),
        ]))
        gen = AuditReportGenerator(evidence_dir=str(ev_dir))
        report = gen.generate_aspice_report()
        dim = next(d for d in report.dimensions if d.process_id == "SWE.1")
        assert dim.coverage_pct == pytest.approx(66.7, abs=0.1)
        assert dim.score == "E1"
        assert any(f["type"] == "failed_evidence" for f in dim.findings)

    def test_dedup_by_ref_id(self, tmp_path):
        """GIVEN duplicate ref_ids across sources WHEN generate THEN deduped."""
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        (ev_dir / "a.json").write_text(json.dumps(
            _ev(process="SWE.1", ref="dup1")))
        req_file = tmp_path / "requirements.json"
        req_file.write_text(json.dumps([
            {"id": "dup1", "title": "Req", "status": "passed"},
            {"id": "other", "title": "Req2", "status": "passed"},
        ]))
        gen = AuditReportGenerator(evidence_dir=str(ev_dir),
                                   requirements_file=str(req_file))
        report = gen.generate_aspice_report()
        dim = next(d for d in report.dimensions if d.process_id == "SWE.1")
        assert dim.evidence_count == 2  # dup1 deduped

    def test_supplementary_requirements(self, tmp_path):
        """GIVEN requirements file WHEN generate THEN SWE.1 supplemented."""
        req_file = tmp_path / "requirements.json"
        req_file.write_text(json.dumps(
            [{"id": "r1", "title": "Req", "status": "passed", "priority": "P1",
              "asil": "D", "created_at": "t"}]))
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"),
                                   requirements_file=str(req_file))
        report = gen.generate_aspice_report()
        dim = next(d for d in report.dimensions if d.process_id == "SWE.1")
        assert dim.evidence_count == 1

    def test_supplementary_tests(self, tmp_path):
        """GIVEN tests file WHEN generate THEN SWE.5/SWE.6 supplemented."""
        tests_file = tmp_path / "tests.json"
        tests_file.write_text(json.dumps({"test_cases": [
            {"id": "t1", "title": "TC1", "test_level": "SWE.5",
             "requirement_ids": ["r1"], "tags": ["smoke"],
             "last_run": {"status": "passed", "timestamp": "t"}},
            {"id": "t2", "title": "TC2", "test_level": "SWE.6",
             "last_run": {"status": "failed", "timestamp": "t"}},
        ]}))
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"),
                                   tests_file=str(tests_file))
        report = gen.generate_aspice_report()
        swe5 = next(d for d in report.dimensions if d.process_id == "SWE.5")
        swe6 = next(d for d in report.dimensions if d.process_id == "SWE.6")
        assert swe5.evidence_count == 1
        assert swe6.evidence_count == 1

    def test_recommendations_swe(self):
        """GIVEN dimensions WHEN _generate_recommendations THEN mixed recs."""
        gen = AuditReportGenerator(evidence_dir=str(Path("/tmp/nonexistent")))
        dims = [
            ProcessDimension(process_id="SWE.1", title="t", score="NI",
                             coverage_pct=0.0, evidence_count=0, gap_count=1,
                             findings=[{"type": "missing_evidence"}], evidences=[]),
            ProcessDimension(process_id="SWE.2", title="t", score="E1",
                             coverage_pct=50.0, evidence_count=2, gap_count=1,
                             findings=[{"type": "failed_evidence", "ref_id": "x"}],
                             evidences=[]),
            ProcessDimension(process_id="SWE.3", title="t", score="E2",
                             coverage_pct=80.0, evidence_count=4, gap_count=0,
                             findings=[], evidences=[]),
        ]
        recs = gen._generate_recommendations(dims)
        joined = "\n".join(recs)
        assert "SWE.1" in joined and "SWE.2" in joined
        assert "E2 已满足" in joined
        assert "SWE 维度无证据" in joined


# ── Exports ───────────────────────────────────────────────────────────

def _make_report():
    dim = ProcessDimension(process_id="SWE.1", title="t", score="NI",
                           coverage_pct=0.0, evidence_count=0, gap_count=1,
                           findings=[{"type": "missing_evidence",
                                      "details": "No evidence"}], evidences=[])
    return AspiceReport(project_name="P", version="1.0", generated_at="g",
                        report_id="id", overall_score="NI",
                        overall_coverage_pct=0.0, total_evidences=0,
                        total_gaps=1, dimensions=[dim],
                        summary_by_process={}, recommendations=["rec"])


class TestExports:
    def test_export_json(self, tmp_path):
        """GIVEN report WHEN export_json THEN file written."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        out = gen.export_json(_make_report(), str(tmp_path / "out" / "r.json"))
        data = json.loads(Path(out).read_text())
        assert data["project_name"] == "P"
        assert data["dimensions"][0]["score"] == "NI"

    def test_export_html(self, tmp_path):
        """GIVEN report WHEN export_html THEN html written with content."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        out = gen.export_html(_make_report(), str(tmp_path / "r.html"))
        content = Path(out).read_text()
        assert "<html" in content
        assert "ASPICE Audit Report" in content
        assert "No evidence" in content  # escaped finding rendered

    def test_export_html_declares_not_aspice_level(self, tmp_path):
        """P0-4: rendered HTML legend must disclaim ASPICE capability levels."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        out = gen.export_html(_make_report(), str(tmp_path / "r2.html"))
        content = Path(out).read_text()
        assert "非 ASPICE 能力等级" in content
        assert "证据覆盖度分级" in content
        # No legacy ASPICE capability-level grades in the rendered report
        assert "AL1" not in content and "AL2" not in content and "AL3" not in content

    def test_export_text_declares_not_aspice_level(self):
        """P0-4: text export carries the same honesty disclaimer."""
        gen = AuditReportGenerator(evidence_dir=str(Path("/tmp/nonexistent")))
        text = gen.export_text(_make_report())
        assert "非 ASPICE 能力等级" in text or "不是 Automotive SPICE" in text

    def test_export_text(self, tmp_path):
        """GIVEN report WHEN export_text THEN text content."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        text = gen.export_text(_make_report())
        assert "ASPICE AUDIT REPORT — P v1.0" in text
        assert "RECOMMENDATIONS" in text
        # with output path
        out = gen.export_text(_make_report(), str(tmp_path / "r.txt"))
        assert Path(out).exists()

    def test_export_pdf_fallback_html(self, tmp_path):
        """GIVEN no weasyprint WHEN export_pdf THEN html fallback."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        with mock.patch.dict(sys.modules, {"weasyprint": None}):
            # force ImportError by removing the module
            with mock.patch("builtins.__import__", side_effect=ImportError("no weasyprint")):
                out = gen.export_pdf(_make_report(), str(tmp_path / "r.pdf"))
        assert out.endswith(".html")

    def test_export_pdf_success(self, tmp_path):
        """GIVEN weasyprint WHEN export_pdf THEN pdf written."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        fake_wp = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"weasyprint": fake_wp}):
            out = gen.export_pdf(_make_report(), str(tmp_path / "r.pdf"))
        assert out.endswith(".pdf")
        fake_wp.HTML.return_value.write_pdf.assert_called_once()

    def test_export_pdf_error_fallback(self, tmp_path):
        """GIVEN weasyprint raises WHEN export_pdf THEN html fallback."""
        gen = AuditReportGenerator(evidence_dir=str(tmp_path / "e"))
        fake_wp = mock.MagicMock()
        fake_wp.HTML.return_value.write_pdf.side_effect = RuntimeError("boom")
        with mock.patch.dict(sys.modules, {"weasyprint": fake_wp}):
            with mock.patch("yuleosh.report.audit_report.log") as mlog:
                out = gen.export_pdf(_make_report(), str(tmp_path / "r.pdf"))
        assert out.endswith(".html")
        mlog.error.assert_called()


# ── CLI ───────────────────────────────────────────────────────────────

class TestMain:
    def test_all_formats(self, tmp_path, monkeypatch, capsys):
        """GIVEN --format all WHEN main THEN all four exports written."""
        monkeypatch.setattr(sys, "argv", ["audit-report",
                                          "--evidence-dir", str(tmp_path / "e"),
                                          "--output", str(tmp_path / "out"),
                                          "--project", "Proj", "--version", "2.0"])
        with mock.patch("yuleosh.report.audit_report.weasyprint", create=True) as wp:
            wp.HTML.return_value.write_pdf.return_value = None
            main()
        out_dir = tmp_path / "out"
        assert (out_dir / "aspice-report.html").exists()
        assert (out_dir / "aspice-report.json").exists()
        assert (out_dir / "aspice-report.txt").exists()
        out = capsys.readouterr().out
        assert "Overall Score" in out

    def test_single_format_json(self, tmp_path, monkeypatch):
        """GIVEN --format json WHEN main THEN only json written."""
        monkeypatch.setattr(sys, "argv", ["audit-report",
                                          "--evidence-dir", str(tmp_path / "e"),
                                          "--output", str(tmp_path / "out"),
                                          "--format", "json"])
        main()
        out_dir = tmp_path / "out"
        assert (out_dir / "aspice-report.json").exists()
        assert not (out_dir / "aspice-report.html").exists()
