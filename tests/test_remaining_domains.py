# @tests src/yuleosh/pipeline/step_handlers/remaining_processes.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""剩余 13 域（ACQ.1~3 / SPL.1 / SUP.2~7 / PIM.1~2 / REU.1）回归。

覆盖:
- aspice_remaining_v3.1 profile：13 域 × 4 BP，证据路径与 handler 对齐
- 26 个生成/评审步骤：无记录时如实记录、终态证据门禁
- G21~G24 注册、102 步 / 25 Gate 契约
- 合规检查：生成后 52 BP 全绿；伪造终态记录 → 检查转红
"""

import json
import os

import pytest
import yaml

from yuleosh.compliance import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.compliance.remaining_specs import SPECS
from yuleosh.pipeline.gates import GATES, validate_gates_contract
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
from yuleosh.pipeline.step_handlers import remaining_processes as rp

HANDLERS = {
    "ACQ.1": (rp.step_acq1_preparation, rp.step_review_acq1),
    "ACQ.2": (rp.step_acq2_selection, rp.step_review_acq2),
    "ACQ.3": (rp.step_acq3_contract, rp.step_review_acq3),
    "SPL.1": (rp.step_spl1_tendering, rp.step_review_spl1),
    "SUP.2": (rp.step_sup2_verification, rp.step_review_sup2),
    "SUP.3": (rp.step_sup3_validation, rp.step_review_sup3),
    "SUP.4": (rp.step_sup4_joint_review, rp.step_review_sup4),
    "SUP.5": (rp.step_sup5_audit, rp.step_review_sup5),
    "SUP.6": (rp.step_sup6_evaluation, rp.step_review_sup6),
    "SUP.7": (rp.step_sup7_documentation, rp.step_review_sup7),
    "PIM.1": (rp.step_pim1_establishment, rp.step_review_pim1),
    "PIM.2": (rp.step_pim2_assessment, rp.step_review_pim2),
    "REU.1": (rp.step_reu1_assets, rp.step_review_reu1),
}


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
    sess = PipelineSession("remaining-test", str(spec))
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


class TestProfile:
    def test_thirteen_domains_with_four_bps(self):
        profile = load_profile("aspice_remaining_v3.1")
        areas = {a.id: a for a in profile.areas}
        assert set(areas) == set(SPECS)
        assert len(areas) == 13
        for area in areas.values():
            assert len(area.base_practices) == 4, area.id

    def test_evidence_paths_align_with_handlers(self):
        profile = load_profile("aspice_remaining_v3.1")
        paths = {
            ev.path
            for area in profile.areas
            for bp in area.base_practices
            for ev in (bp.output_evidence or [])
        }
        for spec in SPECS.values():
            assert spec["doc"] in paths, spec["doc"]
            assert spec["register"] in paths, spec["register"]


class TestGenerationReview:
    @pytest.mark.parametrize("area", list(SPECS))
    def test_generate_and_review_green(self, tmp_path, area):
        sess = _make_session(tmp_path)
        gen, review = HANDLERS[area]
        gen(sess)
        spec = SPECS[area]
        assert (tmp_path / spec["doc"]).is_file()
        assert (tmp_path / spec["register"]).is_file()
        review(sess)

    @pytest.mark.parametrize("area", list(SPECS))
    def test_no_records_recorded_honestly(self, tmp_path, area):
        if area == "SUP.7":
            pytest.skip("SUP.7 索引真实 docs 文件，天然非空")
        sess = _make_session(tmp_path)
        HANDLERS[area][0](sess)
        spec = SPECS[area]
        text = (tmp_path / spec["doc"]).read_text(encoding="utf-8")
        assert spec["no_data"] in text
        data = _load(tmp_path, spec["register"])
        assert data["items"] == []
        assert data["scan_sources"]

    def test_sup7_indexes_real_docs(self, tmp_path):
        sess = _make_session(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)
        (tmp_path / "docs" / "architecture.md").write_text(
            "# 架构\n\n分层设计。\n", encoding="utf-8")
        rp.step_sup7_documentation(sess)
        data = _load(tmp_path, "docs/document-index.yaml")
        titles = {item["title"] for item in data["items"]}
        assert "docs/architecture.md" in titles
        rp.step_review_sup7(sess)

    @pytest.mark.parametrize("area", list(SPECS))
    def test_terminal_without_evidence_red(self, tmp_path, area):
        sess = _make_session(tmp_path)
        gen, review = HANDLERS[area]
        gen(sess)
        spec = SPECS[area]
        data = _load(tmp_path, spec["register"])
        data.setdefault("items", []).append({
            "id": f"{spec['id_prefix']}-FAKE",
            "title": "伪造终态记录",
            "status": spec["terminal"][0],
            "source": "nowhere",
        })
        _save(tmp_path, spec["register"], data)
        with pytest.raises(PipelineStepError, match="缺少"):
            review(sess)

    @pytest.mark.parametrize("area", list(SPECS))
    def test_missing_scan_sources_red(self, tmp_path, area):
        sess = _make_session(tmp_path)
        gen, review = HANDLERS[area]
        gen(sess)
        spec = SPECS[area]
        data = _load(tmp_path, spec["register"])
        data["scan_sources"] = []
        _save(tmp_path, spec["register"], data)
        with pytest.raises(PipelineStepError, match="scan_sources|扫描来源"):
            review(sess)

    def test_scanned_record_requires_doc_trace(self, tmp_path):
        sess = _make_session(tmp_path)
        (tmp_path / "contracts").mkdir()
        (tmp_path / "contracts" / "c1.json").write_text(
            json.dumps({"id": "CTR-1", "title": "主合同"}), encoding="utf-8")
        rp.step_acq3_contract(sess)
        assert "CTR-1" in (tmp_path / "docs/contract-agreement.md").read_text(
            encoding="utf-8")
        rp.step_review_acq3(sess)


class TestCompliance:
    def test_all_red_before_generation(self, tmp_path):
        _make_session(tmp_path)
        summary = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_remaining_v3.1"]
        ).run()["summary"]
        assert summary["passed"] == 0 and summary["failed"] == 52

    def test_all_green_after_generation(self, tmp_path):
        sess = _make_session(tmp_path)
        for gen, _ in HANDLERS.values():
            gen(sess)
        summary = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_remaining_v3.1"]
        ).run()["summary"]
        assert summary["failed"] == 0 and summary["passed"] == 52, summary

    def test_fake_terminal_record_turns_profile_red(self, tmp_path):
        sess = _make_session(tmp_path)
        for gen, _ in HANDLERS.values():
            gen(sess)
        spec = SPECS["ACQ.1"]
        data = _load(tmp_path, spec["register"])
        data["items"].append({
            "id": "ACP-FAKE", "title": "伪造批准", "status": "approved",
            "source": "nowhere",
        })
        _save(tmp_path, spec["register"], data)
        summary = ComplianceChecker(
            str(tmp_path), profile_names=["aspice_remaining_v3.1"]
        ).run()["summary"]
        assert summary["failed"] >= 1


class TestRegistration:
    def test_step_and_gate_counts(self):
        assert len(PIPELINE_STEPS) == 102
        assert len(GATES) == 25
        assert validate_gates_contract([s[0] for s in PIPELINE_STEPS]) == []

    @pytest.mark.parametrize("gate,steps", [
        ("G21", ["acq1-preparation", "acq1-review",
                 "acq2-selection", "acq2-review",
                 "acq3-contract", "acq3-review",
                 "spl1-tendering", "spl1-review"]),
        ("G22", ["sup2-verification", "sup2-review",
                 "sup3-validation", "sup3-review",
                 "sup4-joint-review", "sup4-review",
                 "sup5-audit", "sup5-review",
                 "sup6-evaluation", "sup6-review",
                 "sup7-documentation", "sup7-review"]),
        ("G23", ["pim1-establishment", "pim1-review",
                 "pim2-assessment", "pim2-review",
                 "reu1-assets", "reu1-review"]),
    ])
    def test_gates_registered(self, gate, steps):
        registered = next(g for g in GATES if g["gate"] == gate)
        assert registered["step_keys"] == steps

    def test_chain_rules_cover_new_domains(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        rules = yaml.safe_load(
            (root / "src/yuleosh/evidence/chain_rules.yaml").read_text(
                encoding="utf-8"))
        areas = set(rules["aspice"]["process_areas"])
        assert set(SPECS) <= areas
