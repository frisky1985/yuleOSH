"""假绿修复测试：审计报告不再被空对象（仅自报 status）撑绿。

对应 sprint-contract-fake-green-hardening T1/T2：
- T1: 空对象 {"type":..,"status":"passed"} 不再让维度绿（需实质内容）
- T2: 实质内容证据仍正常通过（不误杀）
"""

# @tests src/yuleosh/audit/model.py
import json
import pathlib

from yuleosh.report.audit_report import AuditReportGenerator


def _make_evidence_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True)
    return ev


def _gen_report(evidence_dir: pathlib.Path):
    return AuditReportGenerator(evidence_dir=str(evidence_dir)).generate_aspice_report(
        project_name="test"
    )


def _dim_by_id(report, pid: str):
    for dim in report.dimensions:
        if dim.process_id == pid:
            return dim
    raise AssertionError(f"process dimension {pid} not found in report")


class TestEmptyEvidenceNotGreen:
    def test_empty_passed_object_not_green(self, tmp_path):
        """T1: 仅 {"type","status"} 的空对象不能撑起维度绿。"""
        ev = _make_evidence_dir(tmp_path)
        (ev / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed"})
        )
        report = _gen_report(ev)
        dim = _dim_by_id(report, "SWE.4")
        assert dim is not None
        # 空对象 → 不算 passing → coverage 0，score 不可能是 E3
        assert dim.score != "E3"
        assert dim.coverage_pct == 0.0
        # 且应被标记为 gap/空洞证据
        assert any(f["type"] == "empty_evidence" for f in dim.findings)

    def test_empty_object_with_process_field_not_green(self, tmp_path):
        """T1: 即使带 process 字段，纯自报无内容仍不绿。"""
        ev = _make_evidence_dir(tmp_path)
        (ev / "review.json").write_text(
            json.dumps({"type": "review", "status": "passed", "process": "SWE.4"})
        )
        report = _gen_report(ev)
        dim = _dim_by_id(report, "SWE.4")
        assert dim.score != "E3"
        assert dim.coverage_pct == 0.0

    def test_substantive_evidence_still_green(self, tmp_path):
        """T2: 带 title+details 的真实证据正常绿（不误杀）。"""
        ev = _make_evidence_dir(tmp_path)
        (ev / "review.json").write_text(json.dumps({
            "type": "review",
            "status": "passed",
            "title": "Code review of module X",
            "details": "Reviewed 12 files; 3 findings all resolved.",
        }))
        report = _gen_report(ev)
        dim = _dim_by_id(report, "SWE.4")
        assert dim is not None
        assert dim.coverage_pct == 100.0
        assert dim.score == "E3"

    def test_mixed_empty_and_substantive(self, tmp_path):
        """T1+T2: 一个实质 + 一个空洞 → 50% 覆盖，不 E3。"""
        ev = _make_evidence_dir(tmp_path)
        (ev / "review1.json").write_text(json.dumps({
            "type": "review", "status": "passed",
            "title": "Real review", "details": "full findings",
        }))
        (ev / "review2.json").write_text(
            json.dumps({"type": "review", "status": "passed"})
        )
        report = _gen_report(ev)
        dim = _dim_by_id(report, "SWE.4")
        assert dim.coverage_pct == 50.0
        assert dim.score != "E3"
        assert dim.gap_count >= 1

    def test_failed_evidence_still_fails(self, tmp_path):
        """回归：status=failed 仍算 gap（不被 substance 逻辑误改）。"""
        ev = _make_evidence_dir(tmp_path)
        (ev / "review.json").write_text(json.dumps({
            "type": "review", "status": "failed",
            "title": "Broken review", "details": "2 unresolved findings",
        }))
        report = _gen_report(ev)
        dim = _dim_by_id(report, "SWE.4")
        assert dim.coverage_pct == 0.0
        assert any(f["type"] == "failed_evidence" for f in dim.findings)
