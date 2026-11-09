"""VAL.1 产品确认（确认过程组）落地测试。

覆盖:
- aspice_val_v3.1 profile 经通用 loader 加载为 1 个过程域（4 条 BP）
- 确认计划自涉众需求派生；无需求时如实标注 Not Covered
- 确认报告只采信 validation-results.yaml 的真实记录（无证据的 PASS 降级）
- step_review_val 确定性门禁：缺产物/缺章节即 RED
- G11 门禁注册与步骤顺序
"""

import os

import pytest

from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_review_val,
    step_val_validation,
)
from yuleosh.pipeline.step_handlers.validation import (
    VALIDATION_PLAN,
    VALIDATION_REPORT,
    VALIDATION_RESULTS,
)


@pytest.fixture(autouse=True)
def _restore_osh_home():
    """还原 OSH_HOME，避免 tmp 路径泄漏给后续用例。"""
    before = os.environ.get("OSH_HOME")
    yield
    if before is None:
        os.environ.pop("OSH_HOME", None)
    else:
        os.environ["OSH_HOME"] = before


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("# 产品\n\n## 需求\n\n确认可用。\n", encoding="utf-8")
    sess = PipelineSession("val-test", str(spec))
    sess.project_dir = str(tmp_path)
    return sess


def _write_stakeholders(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "stakeholder-requirements.md").write_text(
        "# 涉众需求\n\n"
        "- STAKE-001 驾驶员可在 3 秒内完成待办创建\n"
        "- STAKE-002 待办在进程重启后不丢失\n",
        encoding="utf-8",
    )


def _write_results(tmp_path, body: str):
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / VALIDATION_RESULTS).write_text(body, encoding="utf-8")


class TestValidationPlan:
    def test_plan_derives_scenarios_from_stakeholders(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_stakeholders(tmp_path)

        step_val_validation(sess)

        plan = (tmp_path / VALIDATION_PLAN).read_text(encoding="utf-8")
        assert "STAKE-001" in plan and "STAKE-002" in plan
        assert "VAL-001" in plan and "VAL-002" in plan
        assert "`stakeholder`" in plan
        assert "## 确认措施与准则" in plan
        assert "## 确认覆盖矩阵" in plan
        assert "## 可追溯性" in plan

    def test_plan_without_requirements_is_not_covered(self, tmp_path):
        sess = _make_session(tmp_path)

        step_val_validation(sess)

        plan = (tmp_path / VALIDATION_PLAN).read_text(encoding="utf-8")
        assert "Not Covered" in plan
        assert "VAL-001" not in plan  # 不得凭空造确认场景
        assert "`none`" in plan


class TestValidationReport:
    def test_recorded_pass_with_evidence_counts(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_stakeholders(tmp_path)
        _write_results(
            tmp_path,
            "VAL-001:\n  result: pass\n  evidence: reports/val-001.md\n",
        )

        step_val_validation(sess)

        report = (tmp_path / VALIDATION_REPORT).read_text(encoding="utf-8")
        assert "✅ 1 /" in report
        assert "reports/val-001.md" in report
        assert "未执行" in report  # VAL-002 无记录

    def test_pass_without_evidence_is_downgraded(self, tmp_path):
        """无证据的 PASS 不得计入通过（反假绿）。"""
        sess = _make_session(tmp_path)
        _write_stakeholders(tmp_path)
        _write_results(tmp_path, "VAL-001:\n  result: passing\n")

        step_val_validation(sess)

        report = (tmp_path / VALIDATION_REPORT).read_text(encoding="utf-8")
        assert "✅ 0 /" in report
        assert "— 未执行" in report

    def test_missing_results_marks_all_not_run(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_stakeholders(tmp_path)

        step_val_validation(sess)

        report = (tmp_path / VALIDATION_REPORT).read_text(encoding="utf-8")
        assert "— 2 未执行" in report
        assert "不**给出整体通过结论" in report


class TestReviewGate:
    def test_review_passes_after_generation(self, tmp_path):
        sess = _make_session(tmp_path)
        _write_stakeholders(tmp_path)
        step_val_validation(sess)

        assert step_review_val(sess).endswith(VALIDATION_REPORT)

    def test_review_red_when_plan_missing(self, tmp_path):
        sess = _make_session(tmp_path)

        with pytest.raises(PipelineStepError, match="VAL.1 确认门禁 RED"):
            step_review_val(sess)

    def test_review_red_when_section_missing(self, tmp_path):
        sess = _make_session(tmp_path)
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "validation-plan.md").write_text("# 空模板\n", encoding="utf-8")
        (docs / "validation-report.md").write_text(
            "# 报告\n\n## 确认结果汇总\n\n## 可追溯性\n", encoding="utf-8"
        )

        with pytest.raises(PipelineStepError, match="缺少章节"):
            step_review_val(sess)


class TestRegistration:
    def test_profile_loads_val_1(self):
        profile = load_profile("aspice_val_v3.1")
        assert any(a.id == "VAL.1" for a in profile.areas)
        area = next(a for a in profile.areas if a.id == "VAL.1")
        assert {bp.id for bp in area.base_practices} == {
            "VAL.1.BP1",
            "VAL.1.BP2",
            "VAL.1.BP3",
            "VAL.1.BP4",
        }
        paths = {
            ev.path
            for bp in area.base_practices
            for ev in bp.output_evidence
        }
        assert VALIDATION_PLAN in paths and VALIDATION_REPORT in paths

    def test_gate_g11_registered(self):
        gate = next(g for g in GATES if g["gate"] == "G11")
        assert gate["step_keys"] == ["val-validation", "val-review", "final-report"]

    def test_steps_registered_before_final_report(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        assert keys.index("val-validation") < keys.index("val-review")
        assert keys.index("val-review") < keys.index("final-report")


def test_compliance_checker_uses_val_profile(tmp_path):
    """checker 以 VAL profile 运行，能识别 handler 产出的 VAL.1 证据。"""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    sess = _make_session(tmp_path)
    _write_stakeholders(tmp_path)
    step_val_validation(sess)

    profile = load_profile("aspice_val_v3.1")
    report = ComplianceChecker(project_dir=str(tmp_path), profile=profile).run()

    sections = report["swe_sections"]
    assert "val.1" in sections
    assert sections["val.1"]["id"] == "VAL.1"
