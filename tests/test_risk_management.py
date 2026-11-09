"""MAN.5 风险管理（管理过程组）落地测试。

覆盖:
- aspice_man_v3.1 profile 含 MAN.5 四条 BP，证据路径与产物对齐
- 计划/登记/报告三类产物生成，计划确定性
- 自动风险来源：MAN.6 FAIL 度量项、流水线失败步骤；无数据时不生成风险
- 人工登记的评分/责任人/状态在重建时保留
- 确定性门禁：高风险缺责任人/缓解措施/评审日、accept 无理由、score≠L×I 均 RED
- G13 门禁注册与步骤顺序
"""

import json
import os

import pytest
import yaml

from yuleosh.ci.misra_trend import TREND_FILE as MISRA_TREND_FILE
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_review_risk,
    step_risk_assessment,
)
from yuleosh.pipeline.step_handlers.risk import (
    RISK_PLAN,
    RISK_REGISTER,
    RISK_REPORT,
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
    sess = PipelineSession("man5-test", str(spec))
    sess.project_dir = str(tmp_path)
    return sess


def _fake_kpi(entries, monkeypatch):
    payload = json.dumps({"timestamp": "2026-11-09T00:00:00+00:00",
                          "entries": entries, "trend_28d": {}},
                         ensure_ascii=False)
    monkeypatch.setattr(
        "yuleosh.ci.kpi.report.kpi_status", lambda *a, **k: payload
    )


def _load_register(tmp_path):
    return yaml.safe_load((tmp_path / RISK_REGISTER).read_text(encoding="utf-8"))


def _save_register(tmp_path, data):
    target = tmp_path / RISK_REGISTER
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _touch(tmp_path, *rel_paths):
    for rel in rel_paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}\n", encoding="utf-8")


def _valid_risk(**overrides):
    risk = {
        "id": "RISK-MANUAL-001",
        "title": "人工登记风险",
        "category": "质量",
        "source": "manual",
        "likelihood": 3,
        "impact": 3,
        "score": 9,
        "band": "high",
        "status": "open",
        "owner": "张工",
        "response": "mitigate",
        "mitigation": "增加回归测试",
        "review_due": "2027-01-31",
    }
    risk.update(overrides)
    return risk


class TestRiskPlan:
    def test_plan_has_required_sections(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        step_risk_assessment(_make_session(tmp_path))

        plan = (tmp_path / RISK_PLAN).read_text(encoding="utf-8")
        assert "## 风险管理范围" in plan
        assert "## 风险评分方法" in plan
        assert "## 评审与升级" in plan
        # 评分方法必须给出 L×I 与四个等级区间
        for level in ("critical", "high", "medium", "low"):
            assert level in plan
        assert "1-5" in plan

    def test_plan_is_deterministic(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        sess = _make_session(tmp_path)
        step_risk_assessment(sess)
        first = (tmp_path / RISK_PLAN).read_text(encoding="utf-8")
        step_risk_assessment(sess)
        second = (tmp_path / RISK_PLAN).read_text(encoding="utf-8")
        assert first == second


class TestRiskIdentification:
    def test_kpi_fail_generates_high_impact_risk(self, tmp_path, monkeypatch):
        _fake_kpi([{
            "metric": "misra_required_violations", "label": "MISRA Required",
            "value": 12, "threshold": 0, "status": "FAIL",
        }], monkeypatch)
        _touch(tmp_path, MISRA_TREND_FILE)
        step_risk_assessment(_make_session(tmp_path))

        register = _load_register(tmp_path)
        assert register["scan_sources"], "登记必须记录扫描来源"
        risk = next(r for r in register["risks"]
                    if r["id"] == "RISK-KPI-MISRA-REQUIRED-VIOLATIONS")
        assert risk["score"] == 16
        assert risk["band"] == "critical"
        assert risk["source"] == "MAN.6/KPI"
        assert risk["origin"] == "auto"

    def test_kpi_fail_without_raw_data_creates_no_risk(
        self, tmp_path, monkeypatch
    ):
        # 无原始数据时的 FAIL 是测量缺口，不是风险（MAN.6 已标注无数据）
        _fake_kpi([{
            "metric": "c_line_coverage_pct", "label": "C 行覆盖率",
            "value": 0, "threshold": 80, "status": "FAIL",
        }], monkeypatch)
        step_risk_assessment(_make_session(tmp_path))
        assert _load_register(tmp_path)["risks"] == []

    def test_kpi_pass_creates_no_risk(self, tmp_path, monkeypatch):
        _fake_kpi([{
            "metric": "misra_required_violations", "label": "MISRA Required",
            "value": 0, "threshold": 0, "status": "PASS",
        }], monkeypatch)
        step_risk_assessment(_make_session(tmp_path))
        assert _load_register(tmp_path)["risks"] == []

    def test_unavailable_kpi_does_not_invent_risk(self, tmp_path, monkeypatch):
        def _boom(*a, **k):
            raise OSError("kpi unavailable")

        monkeypatch.setattr("yuleosh.ci.kpi.report.kpi_status", _boom)
        step_risk_assessment(_make_session(tmp_path))
        # 无数据 ≠ 风险，也 ≠ 通过：只是不生成条目
        assert _load_register(tmp_path)["risks"] == []

    def test_failed_step_generates_risk(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        marker = tmp_path / ".osh" / "sessions" / "old-run" / "verify-loop.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(
            json.dumps({"session": "old-run", "step": "verify-loop",
                        "status": "failed"}),
            encoding="utf-8",
        )
        step_risk_assessment(_make_session(tmp_path))

        risks = _load_register(tmp_path)["risks"]
        risk = next(r for r in risks if r["id"] == "RISK-STEP-VERIFY-LOOP")
        assert risk["category"] == "进度"
        assert risk["score"] == 12

    def test_manual_entry_is_preserved(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        _save_register(tmp_path, {
            "version": 1, "generated_at": "2026-01-01T00:00:00+00:00",
            "scan_sources": ["manual"],
            "risks": [_valid_risk()],
        })
        step_risk_assessment(_make_session(tmp_path))

        risk = next(r for r in _load_register(tmp_path)["risks"]
                    if r["id"] == "RISK-MANUAL-001")
        assert risk["owner"] == "张工"
        assert risk["status"] == "open"
        assert risk["mitigation"] == "增加回归测试"


class TestRiskReview:
    def _prepare_valid(self, tmp_path, monkeypatch):
        _fake_kpi([], monkeypatch)
        _save_register(tmp_path, {
            "version": 1, "generated_at": "2026-01-01T00:00:00+00:00",
            "scan_sources": ["manual"],
            "risks": [_valid_risk()],
        })
        sess = _make_session(tmp_path)
        step_risk_assessment(sess)
        return sess

    def test_valid_register_passes_and_writes_marker(
        self, tmp_path, monkeypatch
    ):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        step_review_risk(sess)

        marker = sess.session_dir / "risk-review.json"
        assert marker.is_file()
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["step"] == "risk-review"

        report = (tmp_path / RISK_REPORT).read_text(encoding="utf-8")
        assert "RISK-MANUAL-001" in report

    def test_missing_plan_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        (tmp_path / RISK_PLAN).unlink()
        with pytest.raises(PipelineStepError, match="缺少产物"):
            step_review_risk(sess)

    def test_high_risk_without_owner_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0]["owner"] = "待指定"
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="必须指定责任人"):
            step_review_risk(sess)

    def test_high_risk_without_mitigation_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0]["mitigation"] = ""
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="必须填写缓解措施"):
            step_review_risk(sess)

    def test_high_risk_without_review_due_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0]["review_due"] = "下个月"
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="review_due"):
            step_review_risk(sess)

    def test_accept_without_rationale_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0].update(
            {"status": "closed", "response": "accept", "rationale": ""}
        )
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="未说明理由"):
            step_review_risk(sess)

    def test_score_must_equal_l_times_i(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0]["score"] = 20
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="score 与 L×I 不一致"):
            step_review_risk(sess)

    def test_high_risk_with_pending_owner_is_red(self, tmp_path, monkeypatch):
        sess = self._prepare_valid(tmp_path, monkeypatch)
        register = _load_register(tmp_path)
        register["risks"][0]["owner"] = "待指定"
        _save_register(tmp_path, register)
        with pytest.raises(PipelineStepError, match="必须指定责任人"):
            step_review_risk(sess)

    def test_auto_high_risk_is_pending_triage_not_blocking(
        self, tmp_path, monkeypatch
    ):
        _fake_kpi([{
            "metric": "c_line_coverage_pct", "label": "C 行覆盖率",
            "value": 41.0, "threshold": 80.0, "status": "FAIL",
        }], monkeypatch)
        _touch(tmp_path, ".yuleosh/reports/coverage-trend.jsonl")
        sess = _make_session(tmp_path)
        step_risk_assessment(sess)

        # 自动条目无人可指定 → 不阻断自动化流水线，但必须显式暴露为待分级
        step_review_risk(sess)
        marker = json.loads(
            (sess.session_dir / "risk-review.json").read_text(encoding="utf-8")
        )
        assert marker["pending_triage"] == ["RISK-KPI-C-LINE-COVERAGE-PCT"]
        report = (tmp_path / RISK_REPORT).read_text(encoding="utf-8")
        assert "待分级高风险：1" in report
        assert "自动识别，待分级" in report


class TestRegistration:
    def test_profile_loads_man_5(self):
        profile = load_profile("aspice_man_v3.1")
        area = next(a for a in profile.areas if a.id == "MAN.5")
        assert {bp.id for bp in area.base_practices} == {
            f"MAN.5.BP{i}" for i in range(1, 5)
        }
        paths = {
            ev.path for bp in area.base_practices for ev in bp.output_evidence
        }
        assert {RISK_PLAN, RISK_REGISTER, RISK_REPORT} <= paths

    def test_gate_g13_registered(self):
        gate = next(g for g in GATES if g["gate"] == "G13")
        assert gate["step_keys"] == [
            "risk-assessment", "risk-review", "final-report"
        ]

    def test_steps_registered_before_final_report(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        assert keys.index("measurement-review") < keys.index("risk-assessment")
        assert keys.index("risk-assessment") < keys.index("risk-review")
        assert keys.index("risk-review") < keys.index("final-report")
