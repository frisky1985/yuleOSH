"""MAN.6 测量（管理过程组）落地测试。

覆盖:
- aspice_man_v3.1 profile 经通用 loader 加载为 1 个过程域（5 条 BP）
- 测量计划自 ci.kpi 阈值单一来源派生（度量项 ID / 数据源 / 判据）
- 测量报告只采信 kpi_status() 的真实数据；无数据项不推断为通过
- FAIL 项产出纠正措施；KPI 面板异常降级为无数据
- step_review_measurement 确定性门禁：缺产物/缺章节即 RED
- G12 门禁注册与 checker 识别
"""

import json
import os

import pytest

from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.gates import GATES
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_measurement,
    step_review_measurement,
)
from yuleosh.pipeline.step_handlers.measurement import (
    MEASUREMENT_PLAN,
    MEASUREMENT_REPORT,
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
    sess = PipelineSession("man-test", str(spec))
    sess.project_dir = str(tmp_path)
    return sess


def _fake_dashboard(entries, trend=None):
    return json.dumps(
        {"timestamp": "2026-11-09T00:00:00+00:00",
         "entries": entries,
         "trend_28d": trend or {}},
        ensure_ascii=False,
    )


def _touch_sources(tmp_path, *rel_paths):
    for rel in rel_paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}\n", encoding="utf-8")


class TestMeasurementPlan:
    def test_plan_defines_all_indicators(self, tmp_path):
        sess = _make_session(tmp_path)

        step_measurement(sess)

        plan = (tmp_path / MEASUREMENT_PLAN).read_text(encoding="utf-8")
        for mid in ("M-001", "M-004", "M-008"):
            assert mid in plan
        assert "## 度量项定义" in plan
        assert "## 测量规程" in plan
        assert "## 可追溯性" in plan
        # 阈值来自 ci.kpi 单一事实来源
        assert "85.0" in plan  # python_line_coverage_pct

    def test_plan_is_deterministic(self, tmp_path):
        sess = _make_session(tmp_path)
        step_measurement(sess)
        first = (tmp_path / MEASUREMENT_PLAN).read_text(encoding="utf-8")
        step_measurement(sess)
        second = (tmp_path / MEASUREMENT_PLAN).read_text(encoding="utf-8")
        assert first == second


class TestMeasurementReport:
    def test_no_kpi_data_marks_all_no_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status",
            lambda *a, **k: _fake_dashboard([]),
        )
        sess = _make_session(tmp_path)

        step_measurement(sess)

        report = (tmp_path / MEASUREMENT_REPORT).read_text(encoding="utf-8")
        assert "— 8 无数据" in report
        assert "✅ 0 /" in report
        assert "不对其做任何通过性推断" in report

    def test_pass_and_fail_entries_are_rendered(self, tmp_path, monkeypatch):
        entries = [
            {"metric": "misra_total_violations", "label": "MISRA",
             "value": 10, "threshold": 50, "status": "PASS", "unit": "count"},
            {"metric": "c_line_coverage_pct", "label": "覆盖率",
             "value": 60.0, "threshold": 80.0, "status": "FAIL", "unit": "%"},
        ]
        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status",
            lambda *a, **k: _fake_dashboard(entries),
        )
        _touch_sources(
            tmp_path,
            ".yuleosh/reports/misra-trend.jsonl",
            ".yuleosh/reports/coverage-trend.jsonl",
        )
        sess = _make_session(tmp_path)

        step_measurement(sess)

        report = (tmp_path / MEASUREMENT_REPORT).read_text(encoding="utf-8")
        assert "✅ 1 /" in report and "❌ 1 /" in report
        assert "M-003" in report  # FAIL 项进入纠正措施
        assert "## 纠正措施" in report
        assert "待制定" in report

    def test_pass_without_raw_source_is_not_trusted(self, tmp_path, monkeypatch):
        """kpi_status 在无数据时回退 0→PASS；原始文件缺失则不得判绿。"""
        entries = [
            {"metric": "misra_total_violations", "label": "MISRA",
             "value": 0, "threshold": 50, "status": "PASS", "unit": "count"},
        ]
        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status",
            lambda *a, **k: _fake_dashboard(entries),
        )
        sess = _make_session(tmp_path)

        step_measurement(sess)

        report = (tmp_path / MEASUREMENT_REPORT).read_text(encoding="utf-8")
        assert "— 8 无数据" in report
        assert "✅ 1" not in report

    def test_kpi_panel_error_degrades_to_no_data(self, tmp_path, monkeypatch):
        def _boom(*a, **k):
            raise ValueError("nan")

        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status", _boom)
        sess = _make_session(tmp_path)

        step_measurement(sess)  # 不抛异常

        report = (tmp_path / MEASUREMENT_REPORT).read_text(encoding="utf-8")
        assert "— 8 无数据" in report

    def test_trend_section_rendered_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status",
            lambda *a, **k: _fake_dashboard(
                [],
                trend={"misra": {"total": 12.0}, "coverage": {"line": 81.5}},
            ),
        )
        sess = _make_session(tmp_path)

        step_measurement(sess)

        report = (tmp_path / MEASUREMENT_REPORT).read_text(encoding="utf-8")
        assert "28 天趋势均值" in report


class TestReviewGate:
    def test_review_passes_after_generation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "yuleosh.pipeline.step_handlers.measurement.kpi_status",
            lambda *a, **k: _fake_dashboard([]),
        )
        sess = _make_session(tmp_path)
        step_measurement(sess)

        assert step_review_measurement(sess).endswith(MEASUREMENT_REPORT)

    def test_review_red_when_plan_missing(self, tmp_path):
        sess = _make_session(tmp_path)

        with pytest.raises(PipelineStepError, match="MAN.6 测量门禁 RED"):
            step_review_measurement(sess)

    def test_review_red_when_section_missing(self, tmp_path):
        sess = _make_session(tmp_path)
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "measurement-plan.md").write_text("# 空模板\n", encoding="utf-8")
        (docs / "measurement-report.md").write_text(
            "# 报告\n\n## 测量结果\n\n## 可追溯性\n", encoding="utf-8")

        with pytest.raises(PipelineStepError, match="缺少章节"):
            step_review_measurement(sess)


class TestRegistration:
    def test_profile_loads_man_6(self):
        profile = load_profile("aspice_man_v3.1")
        area = next(a for a in profile.areas if a.id == "MAN.6")
        assert {bp.id for bp in area.base_practices} == {
            f"MAN.6.BP{i}" for i in range(1, 6)
        }
        paths = {
            ev.path for bp in area.base_practices for ev in bp.output_evidence
        }
        assert MEASUREMENT_PLAN in paths and MEASUREMENT_REPORT in paths

    def test_gate_g12_registered(self):
        gate = next(g for g in GATES if g["gate"] == "G12")
        assert gate["step_keys"] == ["measurement", "measurement-review", "final-report"]

    def test_steps_registered_at_tail(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        assert keys.index("val-review") < keys.index("measurement")
        assert keys.index("measurement") < keys.index("measurement-review")
        assert keys.index("measurement-review") < keys.index("final-report")


def test_compliance_checker_uses_man_profile(tmp_path, monkeypatch):
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    monkeypatch.setattr(
        "yuleosh.pipeline.step_handlers.measurement.kpi_status",
        lambda *a, **k: _fake_dashboard([]),
    )
    sess = _make_session(tmp_path)
    step_measurement(sess)

    profile = load_profile("aspice_man_v3.1")
    report = ComplianceChecker(project_dir=str(tmp_path), profile=profile).run()

    sections = report["swe_sections"]
    assert "man.6" in sections
    assert sections["man.6"]["id"] == "MAN.6"
