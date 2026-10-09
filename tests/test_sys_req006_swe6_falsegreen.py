"""SWE.6 反假绿回归测试（SWE.6 软件合格性测试）。

守住反假绿硬规矩：软件合格性测试须在"目标/等效环境"执行，
只认真 SIL/HIL 结果，禁用 ``_test_suite_passes()`` / pytest 单测顶替。

场景:
- A: 仓库单测通过(``_test_suite_passes()==True``)但无 SIL/HIL 结果
     → SWE.6.BP2 执行类("All qualification tests pass" /
       "Tests are executed in target or equivalent environment")判 RED，非假绿。
- B: 存在 ``.osh/ci/`` 下含 sil 且 all_passed 的真实结果
     → SWE.6.BP2 执行类判 GREEN（诚实的 GREEN 路径）。
- C: SWE.4 单元测试仍基于 ``_test_suite_passes()``，不被 SWE.6 改动破坏（回归保护）。
"""
import json

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile


def _make_swe_project(tmp_path, with_ci_pass=True, with_sil=False):
    # 单次创建 ci 目录，避免 sandbox shim 对 exist_ok 重复 mkdir 误报 EEXIST
    if with_ci_pass or with_sil:
        ci = tmp_path / ".osh" / "ci"
        ci.mkdir(parents=True, exist_ok=True)
        if with_ci_pass:
            # 让 _test_suite_passes() 返回 True —— 用于证明 SWE.6 不再被它放行
            (ci / "pytest.json").write_text(
                json.dumps({"status": "passed", "passed": 12, "failed": 0}), encoding="utf-8")
        if with_sil:
            (ci / "sil-qualification.json").write_text(json.dumps({
                "all_passed": True,
                "results": [{"elf": "app.elf", "passed": True}],
            }), encoding="utf-8")
    if with_ci_pass:
        # 让 SWE.4 的 _count_unit_tests() > 0，从而单元测试 check 走
        # _test_suite_passes() 分支判 GREEN（回归保护点）
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "dummy_test.py").write_text("# dummy unit test\n", encoding="utf-8")
    return tmp_path


def _swe6_status(report, needle):
    """SWE.6 中匹配 needle 的 check 是否为 GREEN(True)/RED(False)。"""
    section = report["swe_sections"]["swe.6"]
    for bp in section["base_practices"]:
        for d in bp["details"]:
            if needle in d:
                return "✅" in d
    raise AssertionError(f"SWE.6 未找到含 '{needle}' 的检查项")


def _swe4_detail(report):
    """返回 SWE.4 'All unit tests pass' 检查的 detail 文案。"""
    section = report["swe_sections"]["swe.4"]
    for bp in section["base_practices"]:
        for d in bp["details"]:
            if "All unit tests pass" in d:
                return d
    raise AssertionError("SWE.4 未找到 'All unit tests pass' 检查项")


def test_swe6_execution_red_without_sil(tmp_path):
    """A: 单测通过但无 SIL/HIL 结果 → SWE.6.BP2 执行类判 RED（反假绿核心）。"""
    p = _make_swe_project(tmp_path, with_ci_pass=True, with_sil=False)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_v3.1"))
    report = checker.run()

    assert _swe6_status(report, "All qualification tests pass") is False
    assert _swe6_status(report, "Tests are executed in target or equivalent environment") is False


def test_swe6_execution_green_with_sil(tmp_path):
    """B: 存在真 SIL/HIL 结果 → SWE.6.BP2 执行类判 GREEN（诚实路径）。"""
    p = _make_swe_project(tmp_path, with_ci_pass=True, with_sil=True)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_v3.1"))
    report = checker.run()

    assert _swe6_status(report, "All qualification tests pass") is True
    assert _swe6_status(report, "Tests are executed in target or equivalent environment") is True


def test_swe4_unit_test_unaffected(tmp_path):
    """C: 回归保护 —— SWE.6 改动仅对 SWE.6 插入 SIL 分支，SWE.4 必须仍走
    ``_test_suite_passes()`` 的 else 分支（detail 不得出现 SIL/HIL 要求），
    证明未被误伤为需目标环境执行证据。"""
    p = _make_swe_project(tmp_path, with_ci_pass=True, with_sil=False)
    checker = ComplianceChecker(project_dir=str(p), profile=load_profile("aspice_v3.1"))
    report = checker.run()

    detail = _swe4_detail(report)
    assert "SIL/HIL" not in detail, f"SWE.4 不应被要求 SIL/HIL（误伤）: {detail}"
    assert "target/equivalent-environment" not in detail, f"SWE.4 不应走 SWE.6 分支: {detail}"
