"""T3 / SYS-REQ-003: 合规引擎能识别 SYS 区内容（不再 "unknown check type"）。

需求追溯: STAKE-03a → SYS-REQ-003

缺陷: SYS.3(系统验证) / SYS.5(系统确认) 的检查项在 checker 的 elif 链中无
任何分支匹配，一律落到 "unknown check type — not recognized"（有证据也判
不了）；SYS 区的 verification / validation / interface / architecture 与
SWE 区同名词但语义不同，却共用同一套 SWE 取向启发式。

验收: 对 aspice_sys_v3.1 实跑，报告中 "unknown check type" 条目数为 0。

反假绿红线（本文件刻意把守）:
  * 「系统级执行」判定不得被 pytest / CI 单元测试结果顶替 ——
    SWE.6.BP2 曾因复用 _test_suite_passes 而假绿，此处不得重蹈。
"""

import json
import os

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.step_handlers import (
    step_sys_requirements,
    step_sys_architecture,
    step_sys_verification,
    step_sys_integration,
    step_sys_validation,
)


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("# 车窗防夹\n\n## GPIO 控制\n\n系统应驱动 LED。\n\n"
                    "## 传感器通信\n\n系统应读取传感器。\n", encoding="utf-8")
    sess = type("S", (), {})()
    sess.project_dir = str(tmp_path)
    sess.spec_path = str(spec)
    sess.session_dir = str(tmp_path / ".osh" / "sessions" / "t3")
    return sess


def _gen_all_sys_docs(tmp_path):
    sess = _make_session(tmp_path)
    for fn in (step_sys_requirements, step_sys_architecture,
               step_sys_verification, step_sys_integration,
               step_sys_validation):
        fn(sess)
    return sess


def _sys_report(tmp_path):
    checker = ComplianceChecker(project_dir=str(tmp_path),
                                profile=load_profile("aspice_sys_v3.1"))
    return checker.run()


def _all_details(report):
    return [d for sec in report["swe_sections"].values()
            for bp in sec["base_practices"] for d in bp["details"]]


# ── 1. 验收: unknown 归零 ────────────────────────────────────────────────

def test_no_unknown_check_type_for_sys_profile(tmp_path):
    _gen_all_sys_docs(tmp_path)
    details = _all_details(_sys_report(tmp_path))

    unknown = [d for d in details if "unknown check type" in d]
    assert unknown == [], f"仍有判不了的检查项: {unknown}"


def test_sys3_and_sys5_items_are_recognized_with_concrete_reasons(tmp_path):
    """SYS.3/5 检查项须给出具体理由，而非 'unknown'。"""
    _gen_all_sys_docs(tmp_path)
    report = _sys_report(tmp_path)

    for area in ("sys.3", "sys.5"):
        details = [d for bp in report["swe_sections"][area]["base_practices"]
                   for d in bp["details"]]
        assert details, f"{area} 无任何判定明细"
        for d in details:
            if d.strip().startswith("❌ Check:"):
                assert "unknown check type" not in d
                # 必须给出可行动的失败原因
                assert "(" in d


# ── 2. 范围类判定（真实覆盖）────────────────────────────────────────────

def test_scope_check_passes_when_doc_covers_all_sys_req(tmp_path):
    _gen_all_sys_docs(tmp_path)
    docs = tmp_path / "docs"
    req_ids = {"SYS-REQ-001", "SYS-REQ-002"}
    (docs / "system-requirements.md").write_text(
        "\n".join(f"- **{r}** — 系统应提供某能力。" for r in sorted(req_ids)),
        encoding="utf-8")
    (docs / "system-verification.md").write_text(
        "# 系统验证 (SYS.3)\n\n"
        "| 验证用例 | 覆盖需求 |\n|:---|:---|\n"
        "| VC-01 | SYS-REQ-001 |\n| VC-02 | SYS-REQ-002 |\n",
        encoding="utf-8")

    report = _sys_report(tmp_path)
    sys3 = report["swe_sections"]["sys.3"]
    details = [d for bp in sys3["base_practices"] for d in bp["details"]]
    assert any("covers 2/2 system requirements" in d for d in details), details


def test_scope_check_fails_on_partial_coverage(tmp_path):
    """覆盖不全必须判红 —— 不得因文件存在就放行。"""
    _gen_all_sys_docs(tmp_path)
    docs = tmp_path / "docs"
    (docs / "system-requirements.md").write_text(
        "- **SYS-REQ-001** — A。\n- **SYS-REQ-002** — B。\n", encoding="utf-8")
    (docs / "system-verification.md").write_text(
        "# 系统验证\n\n只覆盖 SYS-REQ-001。\n", encoding="utf-8")

    report = _sys_report(tmp_path)
    details = [d for bp in report["swe_sections"]["sys.3"]["base_practices"]
               for d in bp["details"]]
    assert any("covers only 1/2 system requirements" in d for d in details), details


# ── 3. 执行类判定（反假绿核心）──────────────────────────────────────────

def test_execution_check_fails_without_system_level_record(tmp_path):
    _gen_all_sys_docs(tmp_path)
    details = [d for bp in _sys_report(tmp_path)["swe_sections"]["sys.3"]["base_practices"]
               for d in bp["details"]]
    assert any("no system-level execution record" in d for d in details), details


def test_execution_check_not_satisfied_by_pytest_or_ci(tmp_path):
    """反假绿: 仅有 pytest/CI 通过证据，不得算系统级执行。"""
    _gen_all_sys_docs(tmp_path)
    ci = tmp_path / ".osh" / "ci"
    ci.mkdir(parents=True, exist_ok=True)
    (ci / "layer1-ok.json").write_text(
        json.dumps({"status": "passed", "passed": 570, "failed": 0}),
        encoding="utf-8")

    details = [d for bp in _sys_report(tmp_path)["swe_sections"]["sys.3"]["base_practices"]
               for d in bp["details"]]
    assert any("no system-level execution record" in d for d in details), details


def test_execution_check_passes_with_real_system_record(tmp_path):
    """有系统级执行记录（含用例与 passed 状态）时才放行。"""
    _gen_all_sys_docs(tmp_path)
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "system-verification-results.json").write_text(
        json.dumps({"status": "passed",
                    "cases": [{"id": "VC-01", "result": "pass"}]}),
        encoding="utf-8")

    details = [d for bp in _sys_report(tmp_path)["swe_sections"]["sys.3"]["base_practices"]
               for d in bp["details"]]
    assert any("system execution record: system-verification-results.json" in d
               for d in details), details


def test_execution_record_requires_cases_not_just_status(tmp_path):
    """只有 status=passed 但无用例列表 → 不算执行证据。"""
    _gen_all_sys_docs(tmp_path)
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "system-verification-results.json").write_text(
        json.dumps({"status": "passed", "cases": []}), encoding="utf-8")

    checker = ComplianceChecker(str(tmp_path))
    assert checker._sys_execution_record("docs/system-verification.md") is None


# ── 4. 过程域隔离 ───────────────────────────────────────────────────────

def test_sys_helpers_are_area_scoped(tmp_path):
    """无需求源时 helper 如实返回空，不得当作全覆盖。"""
    checker = ComplianceChecker(str(tmp_path))
    assert checker._sys_requirements_ids() == set()
    assert checker._sys_doc_covers_requirements("docs/system-verification.md") == (
        False, 0, 0)
