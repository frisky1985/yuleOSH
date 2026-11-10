"""管理支撑过程（ACQ.4 / REU.2 / PIM.3 / SPL.2）落地测试。

覆盖:
- aspice_mgmt_support_v3.1 profile：4 个过程域，各 4 条 BP，证据路径对齐
- ACQ.4：自动盘点第三方依赖、人工评估字段跨轮次保留、拒绝需纠正措施
- REU.2：自动识别内部组件、拒绝复用需理由
- PIM.3：改进项只从 MAN.6 FAIL / MAN.5 高风险派生，无输入不臆造
- SPL.2：发布清单含真实 SHA256，摘要篡改 / 门禁未通过时批准 → RED
- G14~G16 / G19 门禁注册与步骤顺序
"""

import json
import os
from pathlib import Path

import pytest
import yaml

from yuleosh.compliance.profile import load_profile
from yuleosh.compliance import ComplianceChecker
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_acq4_monitoring,
    step_pim3_improvement,
    step_reu2_reuse,
    step_review_acq4,
    step_review_pim3,
    step_review_reu2,
    step_review_spl2,
    step_spl2_release,
)
from yuleosh.pipeline.step_handlers.mgmt_support import (
    ACQ_REGISTER,
    ACQ_REPORT,
    PIM_PLAN,
    PIM_REGISTER,
    PIM_REPORT,
    RELEASE_MANIFEST,
    RELEASE_PLAN,
    REUSE_REGISTER,
    REUSE_REPORT,
)


@pytest.fixture(autouse=True)
def _restore_osh_home():
    before = os.environ.get("OSH_HOME")
    yield
    if before is None:
        os.environ.pop("OSH_HOME", None)
    else:
        os.environ["OSH_HOME"] = before


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("# 产品\n\n## 需求\n\n可度量。\n", encoding="utf-8")
    sess = PipelineSession("mgmt-support-test", str(spec))
    sess.project_dir = str(tmp_path)
    return sess


def _load(tmp_path, rel):
    return yaml.safe_load((tmp_path / rel).read_text(encoding="utf-8"))


def _save(tmp_path, rel, data):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_pyproject(tmp_path, version="1.2.3"):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo"\n'
        f'version = "{version}"\n'
        'dependencies = ["PyYAML>=6.0", "requests>=2.31"]\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8.0"]\n',
        encoding="utf-8",
    )


# ── profile ─────────────────────────────────────────────────────────────


class TestProfile:
    def test_profile_has_four_areas(self):
        profile = load_profile("aspice_mgmt_support_v3.1")
        ids = {a.id for a in profile.areas}
        assert ids == {"ACQ.4", "REU.2", "PIM.3", "SPL.2"}
        for area in profile.areas:
            assert len(area.base_practices) == 4
            assert {bp.id for bp in area.base_practices} == {
                f"{area.id}.BP{i}" for i in range(1, 5)
            }

    def test_evidence_paths_match_handlers(self):
        profile = load_profile("aspice_mgmt_support_v3.1")
        paths = {
            ev.path
            for area in profile.areas
            for bp in area.base_practices
            for ev in bp.output_evidence
        }
        assert {
            ACQ_REGISTER, ACQ_REPORT, REUSE_REGISTER, REUSE_REPORT,
            PIM_PLAN, PIM_REGISTER, PIM_REPORT, RELEASE_PLAN, RELEASE_MANIFEST,
        } <= paths


# ── ACQ.4 ───────────────────────────────────────────────────────────────


class TestSupplierMonitoring:
    def test_scans_pyproject_and_requirements(self, tmp_path):
        _write_pyproject(tmp_path)
        (tmp_path / "requirements-dev.txt").write_text(
            "# comment\njsonschema>=4\n", encoding="utf-8")
        sess = _make_session(tmp_path)

        step_acq4_monitoring(sess)

        register = _load(tmp_path, ACQ_REGISTER)
        names = {s["name"] for s in register["suppliers"]}
        assert {"PyYAML", "requests", "pytest", "jsonschema"} <= names
        assert register["scan_sources"]
        for supplier in register["suppliers"]:
            assert supplier["id"].startswith("ACQ-")
            assert supplier["status"] == "待评估"
            assert supplier["owner"] == "待指定"

        report = (tmp_path / ACQ_REPORT).read_text(encoding="utf-8")
        for supplier in register["suppliers"]:
            assert supplier["id"] in report

        marker = json.loads(
            (sess.session_dir / "acq4-monitoring.json").read_text(encoding="utf-8"))
        assert marker["supplier_count"] == len(register["suppliers"])

    def test_human_assessment_survives_regeneration(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        step_acq4_monitoring(sess)

        register = _load(tmp_path, ACQ_REGISTER)
        register["suppliers"][0].update({
            "status": "approved", "owner": "张三",
            "requirements_agreed": True, "monitoring_method": "季度评审",
        })
        _save(tmp_path, ACQ_REGISTER, register)

        step_acq4_monitoring(sess)

        again = _load(tmp_path, ACQ_REGISTER)
        first = again["suppliers"][0]
        assert first["status"] == "approved"
        assert first["owner"] == "张三"
        assert first["requirements_agreed"] is True

    def test_review_red_when_rejected_without_action(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        step_acq4_monitoring(sess)
        step_review_acq4(sess)  # 结构完整时可过

        register = _load(tmp_path, ACQ_REGISTER)
        register["suppliers"][0]["status"] = "rejected"
        register["suppliers"][0]["corrective_action"] = ""
        _save(tmp_path, ACQ_REGISTER, register)

        with pytest.raises(PipelineStepError, match="ACQ.4"):
            step_review_acq4(sess)


# ── REU.2 ───────────────────────────────────────────────────────────────


class TestReuseManagement:
    def test_scans_src_packages(self, tmp_path):
        pkg = tmp_path / "src" / "demo"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "core.py").write_text("x = 1\n", encoding="utf-8")
        sess = _make_session(tmp_path)

        step_reu2_reuse(sess)

        register = _load(tmp_path, REUSE_REGISTER)
        assert [c["name"] for c in register["components"]] == ["demo"]
        component = register["components"][0]
        assert component["kind"] == "internal"
        assert component["reuse_status"] == "待评估"
        assert component["module_count"] == 2

        report = (tmp_path / REUSE_REPORT).read_text(encoding="utf-8")
        assert component["id"] in report

    def test_rejected_reuse_requires_rationale(self, tmp_path):
        pkg = tmp_path / "src" / "demo"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        sess = _make_session(tmp_path)
        step_reu2_reuse(sess)
        step_review_reu2(sess)

        register = _load(tmp_path, REUSE_REGISTER)
        register["components"][0]["reuse_status"] = "rejected"
        register["components"][0]["rationale"] = ""
        _save(tmp_path, REUSE_REGISTER, register)

        with pytest.raises(PipelineStepError, match="REU.2"):
            step_review_reu2(sess)


# ── PIM.3 ───────────────────────────────────────────────────────────────


def _fake_kpi(entries, monkeypatch):
    payload = json.dumps(
        {"timestamp": "2026-11-09T00:00:00+00:00", "entries": entries,
         "trend_28d": {}}, ensure_ascii=False)
    monkeypatch.setattr(
        "yuleosh.ci.kpi.report.kpi_status", lambda *a, **k: payload)


class TestProcessImprovement:
    def test_derives_from_kpi_failure_and_high_risk(self, tmp_path, monkeypatch):
        reports = tmp_path / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "misra-trend.jsonl").write_text('{"total": 3}\n', encoding="utf-8")
        _fake_kpi([{
            "metric": "misra_required_violations", "label": "MISRA Required 违规数",
            "value": 3, "threshold": 0, "status": "FAIL",
        }], monkeypatch)
        _save(tmp_path, "docs/risk-register.yaml", {
            "version": 1, "scan_sources": ["MAN.6/KPI"],
            "risks": [{
                "id": "RISK-KPI-MISRA-REQUIRED-VIOLATIONS",
                "title": "度量项未达标", "score": 16, "status": "open",
            }],
        })
        sess = _make_session(tmp_path)

        step_pim3_improvement(sess)

        register = _load(tmp_path, PIM_REGISTER)
        ids = {i["id"] for i in register["improvements"]}
        assert "PIM-KPI-MISRA-REQUIRED-VIOLATIONS" in ids
        assert "PIM-RISK-KPI-MISRA-REQUIRED-VIOLATIONS" in ids
        report = (tmp_path / PIM_REPORT).read_text(encoding="utf-8")
        assert "MAN.6 FAIL 1 项" in report
        assert "MAN.5 开放高风险 1 项" in report
        step_review_pim3(sess)

    def test_no_input_is_recorded_not_invented(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        sess = _make_session(tmp_path)

        step_pim3_improvement(sess)

        register = _load(tmp_path, PIM_REGISTER)
        assert register["improvements"] == []
        assert register["scan_sources"]
        report = (tmp_path / PIM_REPORT).read_text(encoding="utf-8")
        assert "无改进输入" in report
        step_review_pim3(sess)

    def test_manual_open_item_requires_owner_and_due(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        sess = _make_session(tmp_path)
        step_pim3_improvement(sess)

        register = _load(tmp_path, PIM_REGISTER)
        register["improvements"].append({
            "id": "PIM-MANUAL-001", "source": "人工评估", "origin": "manual",
            "title": "补充评审", "objective": "提高评审覆盖",
            "owner": "待指定", "due": "", "status": "open",
        })
        _save(tmp_path, PIM_REGISTER, register)

        with pytest.raises(PipelineStepError, match="PIM.3"):
            step_review_pim3(sess)


# ── SPL.2 ───────────────────────────────────────────────────────────────


def _seed_artifact(tmp_path, sess, rel="docs/design.md"):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# design\n", encoding="utf-8")
    sess.artifacts["design"] = str(target)
    return target


class TestProductRelease:
    def test_manifest_records_real_digests(self, tmp_path):
        _write_pyproject(tmp_path, "1.2.3")
        sess = _make_session(tmp_path)
        _seed_artifact(tmp_path, sess)

        step_spl2_release(sess)

        manifest = _load(tmp_path, RELEASE_MANIFEST)
        assert manifest["release_version"] == "1.2.3"
        assert manifest["approval_status"] == "待批准"
        assert manifest["artifact_count"] == 1
        artifact = manifest["artifacts"][0]
        assert artifact["path"] == "docs/design.md"
        assert len(artifact["sha256"]) == 64
        step_review_spl2(sess)

    def test_tampered_artifact_is_red(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        target = _seed_artifact(tmp_path, sess)
        step_spl2_release(sess)

        target.write_text("# tampered\n", encoding="utf-8")

        with pytest.raises(PipelineStepError, match="摘要不一致"):
            step_review_spl2(sess)

    def test_approved_with_failed_gate_is_red(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        _seed_artifact(tmp_path, sess)
        (Path(sess.session_dir) / "gate-summary.json").write_text(
            json.dumps({"worst_gate_status": "failed"}), encoding="utf-8")
        step_spl2_release(sess)

        manifest = _load(tmp_path, RELEASE_MANIFEST)
        manifest["approval_status"] = "approved"
        _save(tmp_path, RELEASE_MANIFEST, manifest)

        with pytest.raises(PipelineStepError, match="不得批准发布"):
            step_review_spl2(sess)

    def test_approved_with_passed_gate_is_allowed(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        _seed_artifact(tmp_path, sess)
        (Path(sess.session_dir) / "gate-summary.json").write_text(
            json.dumps({"worst_gate_status": "passed"}), encoding="utf-8")
        step_spl2_release(sess)

        manifest = _load(tmp_path, RELEASE_MANIFEST)
        manifest["approval_status"] = "approved"
        _save(tmp_path, RELEASE_MANIFEST, manifest)

        step_review_spl2(sess)

    def test_empty_release_is_red(self, tmp_path):
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        step_spl2_release(sess)

        with pytest.raises(PipelineStepError, match="发布清单为空"):
            step_review_spl2(sess)


# ── registration ────────────────────────────────────────────────────────


class TestComplianceProfile:
    def test_green_only_after_artifacts_exist(self, tmp_path):
        """有确定性产物 → 16/16;无产物 → 0/16（不假绿）。"""
        _write_pyproject(tmp_path)
        sess = _make_session(tmp_path)
        checker = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_mgmt_support_v3.1"])

        before = checker.run()["summary"]
        assert before["passed"] == 0 and before["failed"] == 16

        step_acq4_monitoring(sess)
        step_reu2_reuse(sess)
        step_pim3_improvement(sess)
        _seed_artifact(tmp_path, sess)
        step_spl2_release(sess)

        after = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_mgmt_support_v3.1"]
        ).run()["summary"]
        assert after["passed"] == 16 and after["failed"] == 0


class TestRegistration:
    @pytest.mark.parametrize("gate,steps", [
        ("G14", ["acq4-monitoring", "acq4-review"]),
        ("G15", ["reu2-reuse", "reu2-review"]),
        ("G16", ["pim3-improvement", "pim3-review"]),
        ("G19", ["spl2-release", "spl2-review", "final-report"]),
    ])
    def test_gates_registered(self, gate, steps):
        registered = next(g for g in GATES if g["gate"] == gate)
        assert registered["step_keys"] == steps

    def test_step_order(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        order = [
            "risk-review", "acq4-monitoring", "acq4-review",
            "reu2-reuse", "reu2-review", "pim3-improvement", "pim3-review",
            "hwe4-review", "mle4-review",
            "spl2-release", "spl2-review", "final-report",
        ]
        positions = [keys.index(k) for k in order]
        assert positions == sorted(positions)
