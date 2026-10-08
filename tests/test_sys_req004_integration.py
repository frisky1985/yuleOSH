"""SYS.4 反假绿回归测试（SYS-REQ-004 / 系统集成）。

守住三条硬规矩之一：系统级执行只认系统级执行记录或真 SIL/HIL，
禁用 ``_test_suite_passes()`` / pytest / CI 单测顶替。

场景:
- A: 仓库单测通过(``_test_suite_passes()==True``)但无系统级集成记录
     → SYS.4 执行类("builds succeed" / "tests verify data flow")判 RED，非假绿。
- B: 存在 ``.osh/evidence/system-integration-results.json``
     → SYS.4 执行类判 GREEN（诚实的 GREEN 路径）。
- C: SWE.4 集成检查仍基于 ``_test_suite_passes()``，不被 SYS 区改动破坏（回归保护）。
"""

import json

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile


def _make_sys_project(tmp_path, with_integration_results=False, with_ci_pass=True):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    # 实质性系统文档(>100 字，含 sequence / stub / driver)
    (docs / "system-requirements.md").write_text(
        "# 系统需求\n\n## 可追溯性\n\n- 追溯至上游涉众需求。\n", encoding="utf-8")
    (docs / "system-architecture.md").write_text(
        "# 系统架构\n\n## 可追溯性\n\n- 覆盖全部系统需求。\n", encoding="utf-8")
    (docs / "system-verification.md").write_text(
        "# 系统验证\n\n## 可追溯性\n\n- 验证准则已定义。\n", encoding="utf-8")
    (docs / "system-validation.md").write_text(
        "# 系统确认\n\n## 可追溯性\n\n- 确认准则已定义。\n", encoding="utf-8")
    (docs / "system-integration.md").write_text(
        "# 系统集\n\n"
        "## 集成序列\n\n系统集成的构建顺序已定义并论证(sequence)：先集成电源管理单元，"
        "再集成通信总线，最后集成应用处理器，以降低接口耦合风险。\n\n"
        "## 桩与驱动\n\n在硬件未就绪时，使用 stub 与 driver 对未实现的下位机进行集成替代。\n\n"
        "## 策略遵循\n\n集成严格遵循上述已定义的策略与接口契约执行。\n",
        encoding="utf-8")

    osh = tmp_path / ".osh"
    osh.mkdir(exist_ok=True)
    if with_ci_pass:
        ci = osh / "ci"
        ci.mkdir(exist_ok=True)
        # 让 _test_suite_passes() 返回 True —— 用于证明 SYS 区不再被它放行
        (ci / "pytest.json").write_text(
            json.dumps({"status": "passed", "passed": 12, "failed": 0}), encoding="utf-8")
    if with_integration_results:
        ev = osh / "evidence"
        ev.mkdir(exist_ok=True)
        (ev / "system-integration-results.json").write_text(
            json.dumps({"status": "passed", "cases": ["build", "data-flow"]}),
            encoding="utf-8")
    return tmp_path


def _sys4_status(report, needle):
    """SYS.4 中匹配 needle 的 check 是否为 GREEN(True)/RED(False)。"""
    section = report["swe_sections"]["sys.4"]
    for bp in section["base_practices"]:
        for d in bp["details"]:
            if needle in d:
                return "✅" in d
    raise AssertionError(f"SYS.4 未找到含 '{needle}' 的检查项")


def _swe5_status(report, needle):
    section = report["swe_sections"]["swe.5"]
    for bp in section["base_practices"]:
        for d in bp["details"]:
            if needle in d:
                return "✅" in d
    raise AssertionError(f"SWE.5 未找到含 '{needle}' 的检查项")


def test_sys4_execution_red_without_system_evidence(tmp_path):
    """A: 单测通过但无系统级集成记录 → SYS.4 执行类判 RED（反假绿核心断言）。"""
    p = _make_sys_project(tmp_path, with_integration_results=False, with_ci_pass=True)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_sys_v3.1"))
    report = checker.run()

    # 执行类必须 RED：仓库单测不再能顶替系统级集成
    assert _sys4_status(report, "Integration builds succeed") is False
    assert _sys4_status(report, "Integration tests verify data flow") is False

    # 策略类应 GREEN：docs/system-integration.md 实质性即可（与执行类分离）
    assert _sys4_status(report, "Integration sequence is defined") is True
    assert _sys4_status(report, "Integration follows the defined strategy") is True
    # stub/driver 查系统级文档（不再误查 SWE 的 integration-strategy.md）
    assert _sys4_status(report, "Stubs/drivers are identified") is True


def test_sys4_execution_green_with_system_evidence(tmp_path):
    """B: 存在系统级集成执行记录 → SYS.4 执行类判 GREEN（诚实路径）。"""
    p = _make_sys_project(tmp_path, with_integration_results=True, with_ci_pass=True)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_sys_v3.1"))
    report = checker.run()

    assert _sys4_status(report, "Integration builds succeed") is True
    assert _sys4_status(report, "Integration tests verify data flow") is True


def test_swe5_integration_still_uses_test_suite(tmp_path):
    """C: 回归保护 —— SWE.5 集成检查仍基于 _test_suite_passes()，未被 SYS 改动破坏。

    注: "Integration builds succeed" 属 SWE.5(软件集成)，非 SWE.4(组件集成)。
    """
    p = _make_sys_project(tmp_path, with_integration_results=False, with_ci_pass=True)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_v3.1"))
    report = checker.run()

    # SWE.5.BP2 "Integration builds succeed" 在 SWE 区应 GREEN（经由 _test_suite_passes）
    assert _swe5_status(report, "Integration builds succeed") is True
