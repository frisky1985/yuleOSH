# @tests src/yuleosh/pipeline/step_handlers/sup_man.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""SUP.1 / SUP.8 / SUP.9 / SUP.10 / MAN.3 确定性生成 + 评审回归。

覆盖:
- aspice_sup_man_v3.1 profile：5 个过程域，各 4 条 BP，证据路径对齐
- SUP.1：无审计记录如实记录；登记缺 scan_sources / 文档漏列记录 → RED
- SUP.8：基线逐项 SHA256 + 清单摘要；摘要篡改 → RED
- SUP.9：无问题如实记录；已关闭缺关闭说明 / 文档漏列 → RED
- SUP.10：无变更如实记录；已批准缺决策依据 → RED
- MAN.3：无里程碑如实记录；已完成缺完成证据 → RED
- G19/G20/G21 门禁注册与步骤顺序
"""

import json
import os

import pytest
import yaml

from yuleosh.compliance import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_man3_project,
    step_review_man3,
    step_review_sup1,
    step_review_sup8,
    step_review_sup9,
    step_review_sup10,
    step_sup1_quality,
    step_sup8_config,
    step_sup9_problem,
    step_sup10_change,
)
from yuleosh.pipeline.step_handlers.sup_man import (
    CM_BASELINE,
    CM_ITEMS,
    CM_PLAN,
    CR_DOC,
    CR_REGISTER,
    ISSUE_REGISTER,
    ISSUES_DOC,
    MILESTONES,
    PROJECT_PLAN,
    QA_PLAN,
    QA_REGISTER,
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
    sess = PipelineSession("sup-man-test", str(spec))
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


def _write_json(tmp_path, rel, data):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestProfile:
    def test_five_domains_with_four_bps(self):
        profile = load_profile("aspice_sup_man_v3.1")
        areas = {a.id: a for a in profile.areas}
        assert set(areas) == {"SUP.1", "SUP.8", "SUP.9", "SUP.10", "MAN.3"}
        for area in areas.values():
            assert len(area.base_practices) == 4, area.id

    def test_evidence_paths_align_with_handlers(self):
        profile = load_profile("aspice_sup_man_v3.1")
        paths = {
            ev.path
            for area in profile.areas
            for bp in area.base_practices
            for ev in (bp.output_evidence or [])
        }
        for expected in (QA_PLAN, QA_REGISTER, CM_PLAN, CM_ITEMS, CM_BASELINE,
                         ISSUES_DOC, ISSUE_REGISTER, CR_DOC, CR_REGISTER,
                         PROJECT_PLAN, MILESTONES):
            assert expected in paths, expected


class TestSup1Quality:
    def test_generate_and_review_green_without_audit_records(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup1_quality(sess)
        assert (tmp_path / QA_PLAN).is_file()
        assert "（无审计记录" in (tmp_path / QA_PLAN).read_text(encoding="utf-8")
        step_review_sup1(sess)

    def test_register_without_scan_sources_red(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup1_quality(sess)
        data = _load(tmp_path, QA_REGISTER)
        data["scan_sources"] = []
        _save(tmp_path, QA_REGISTER, data)
        with pytest.raises(PipelineStepError, match="scan_sources"):
            step_review_sup1(sess)

    def test_register_record_missing_from_doc_red(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup1_quality(sess)
        data = _load(tmp_path, QA_REGISTER)
        data.setdefault("records", []).append(
            {"id": "QA-FAKE", "kind": "audit", "source": "nowhere"})
        _save(tmp_path, QA_REGISTER, data)
        with pytest.raises(PipelineStepError, match="QA-FAKE"):
            step_review_sup1(sess)


class TestSup8Config:
    def test_baseline_digest_roundtrip(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup8_config(sess)
        baseline = json.loads((tmp_path / CM_BASELINE).read_text(encoding="utf-8"))
        assert baseline["files"]
        assert baseline["manifest_sha256"]
        step_review_sup8(sess)

    def test_tampered_manifest_red(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup8_config(sess)
        baseline = json.loads((tmp_path / CM_BASELINE).read_text(encoding="utf-8"))
        first = sorted(baseline["files"])[0]
        baseline["files"][first] = "0" * 64
        _write_json(tmp_path, CM_BASELINE, baseline)
        with pytest.raises(PipelineStepError, match="摘要不一致"):
            step_review_sup8(sess)

    def test_missing_scan_sources_red(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup8_config(sess)
        data = _load(tmp_path, CM_ITEMS)
        data["scan_sources"] = []
        _save(tmp_path, CM_ITEMS, data)
        with pytest.raises(PipelineStepError, match="scan_sources"):
            step_review_sup8(sess)


class TestSup9Problem:
    def test_no_records_recorded_honestly(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup9_problem(sess)
        assert "（无条目" in (tmp_path / ISSUES_DOC).read_text(encoding="utf-8")
        step_review_sup9(sess)

    def test_closed_without_closure_red(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, ".osh/issues/ISS-1.json",
                    {"id": "ISS-1", "title": "断链", "status": "closed"})
        step_sup9_problem(sess)
        with pytest.raises(PipelineStepError, match="关闭说明"):
            step_review_sup9(sess)

    def test_closed_with_closure_green(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, ".osh/issues/ISS-1.json",
                    {"id": "ISS-1", "title": "断链", "status": "closed",
                     "closure": "补充链接后回归通过"})
        step_sup9_problem(sess)
        text = (tmp_path / ISSUES_DOC).read_text(encoding="utf-8")
        assert "ISS-1" in text
        step_review_sup9(sess)


class TestSup10Change:
    def test_no_records_recorded_honestly(self, tmp_path):
        sess = _make_session(tmp_path)
        step_sup10_change(sess)
        assert "（无条目" in (tmp_path / CR_DOC).read_text(encoding="utf-8")
        step_review_sup10(sess)

    def test_approved_without_decision_red(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, "change-requests/CRQ-1.json",
                    {"id": "CRQ-1", "title": "增加看板", "status": "approved"})
        step_sup10_change(sess)
        with pytest.raises(PipelineStepError, match="决策依据"):
            step_review_sup10(sess)

    def test_approved_with_decision_green(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, "change-requests/CRQ-1.json",
                    {"id": "CRQ-1", "title": "增加看板", "status": "approved",
                     "decision": "影响可控，纳入本迭代"})
        step_sup10_change(sess)
        assert "CRQ-1" in (tmp_path / CR_DOC).read_text(encoding="utf-8")
        step_review_sup10(sess)


class TestMan3Project:
    def test_no_milestones_recorded_honestly(self, tmp_path):
        sess = _make_session(tmp_path)
        step_man3_project(sess)
        assert json.loads((tmp_path / MILESTONES).read_text(encoding="utf-8")) == []
        assert "（无里程碑" in (tmp_path / PROJECT_PLAN).read_text(encoding="utf-8")
        step_review_man3(sess)

    def test_done_without_evidence_red(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, MILESTONES, [
            {"id": "MS-1", "title": "G0 评审", "due": "2026-12-01",
             "status": "done"}])
        step_man3_project(sess)
        with pytest.raises(PipelineStepError, match="完成证据"):
            step_review_man3(sess)

    def test_done_with_evidence_green(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_json(tmp_path, MILESTONES, [
            {"id": "MS-1", "title": "G0 评审", "due": "2026-12-01",
             "status": "done", "evidence": ".osh/ci/gate-summary.json"}])
        step_man3_project(sess)
        assert "MS-1" in (tmp_path / PROJECT_PLAN).read_text(encoding="utf-8")
        step_review_man3(sess)


class TestComplianceProfile:
    def test_all_red_before_generation(self, tmp_path):
        _make_session(tmp_path)
        summary = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_sup_man_v3.1"]
        ).run()["summary"]
        assert summary["passed"] == 0 and summary["failed"] > 0

    def test_all_green_after_generation(self, tmp_path):
        sess = _make_session(tmp_path)
        for fn in (step_sup1_quality, step_sup8_config, step_sup9_problem,
                   step_sup10_change, step_man3_project):
            fn(sess)
        summary = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_sup_man_v3.1"]
        ).run()["summary"]
        assert summary["failed"] == 0 and summary["passed"] == 20


class TestRegistration:
    @pytest.mark.parametrize("gate,steps", [
        ("G19", ["sup1-quality", "sup1-review",
                 "sup8-config", "sup8-review",
                 "sup9-problem", "sup9-review",
                 "sup10-change", "sup10-review"]),
        ("G20", ["man3-project", "man3-review"]),
        ("G21", ["spl2-release", "spl2-review", "final-report"]),
    ])
    def test_gates_registered(self, gate, steps):
        registered = next(g for g in GATES if g["gate"] == gate)
        assert registered["step_keys"] == steps

    def test_step_order(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        order = [
            "mle4-review", "sup1-quality", "sup1-review",
            "sup8-config", "sup8-review", "sup9-problem", "sup9-review",
            "sup10-change", "sup10-review", "man3-project", "man3-review",
            "spl2-release", "spl2-review", "final-report",
        ]
        positions = [keys.index(k) for k in order]
        assert positions == sorted(positions)
