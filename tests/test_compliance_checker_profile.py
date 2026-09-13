"""A1-05 ComplianceChecker profile 驱动改造测试 (T-010 Q4 sprint).

验证：
- 默认构造走 load_profile("aspice_v3.1")（零改动兼容旧调用）
- 显式注入 profile 生效（A-M2 接入新标准的入口）
- 旧 template_path 路径零改动可跑
- profile 路径与 yaml 路径输出在 checker 消费字段上一致（golden 零漂移）
"""

from pathlib import Path

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import StandardProfile, ProfileMeta, load_profile

_FIXTURE = Path(__file__).parent / "fixtures" / "compliance_sample"
_YAML = (
    Path(__file__).parent.parent
    / "src"
    / "yuleosh"
    / "compliance"
    / "profiles"
    / "aspice_v3.1.yaml"
)


def _norm(rep: dict) -> dict:
    """抽取 checker 实际消费的核心字段，屏蔽时间戳/路径等非确定项。"""
    return {
        "standard": rep["standard"],
        "version": rep["version"],
        "swe_keys": sorted(rep["swe_sections"].keys()),
        "summary": rep["summary"],
        "statuses": {
            k: [bp["status"] for bp in v["base_practices"]]
            for k, v in rep["swe_sections"].items()
        },
    }


def test_default_constructor_loads_profile():
    checker = ComplianceChecker(str(_FIXTURE))
    rep = checker.run()
    assert rep["standard"] == "ASPICE"
    assert rep["version"] == "3.1"
    assert rep["swe_sections"].keys() == {
        "swe.1", "swe.2", "swe.3", "swe.4", "swe.5", "swe.6",
    }
    # 默认构造也暴露 profile 对象
    assert isinstance(checker.profile, StandardProfile)


def test_template_path_backward_compat():
    checker = ComplianceChecker(str(_FIXTURE), template_path=_YAML)
    rep = checker.run()
    assert rep["standard"] == "ASPICE"
    assert rep["swe_sections"].keys() == {
        "swe.1", "swe.2", "swe.3", "swe.4", "swe.5", "swe.6",
    }
    # 旧路径不构建 profile 对象（向后兼容语义）
    assert checker.profile is None


def test_profile_and_yaml_paths_equivalent():
    """profile 路径与 yaml 路径在 checker 消费字段上必须一致（golden 零漂移）。"""
    via_profile = ComplianceChecker(str(_FIXTURE)).run()
    via_yaml = ComplianceChecker(str(_FIXTURE), template_path=_YAML).run()
    assert _norm(via_profile) == _norm(via_yaml)


def test_injected_profile_overrides_standard():
    """显式注入自定义 profile 应覆盖标准名（A-M2 接入入口）。"""
    custom = StandardProfile(
        meta=ProfileMeta(standard="ISO26262", version="2018", description="custom"),
        areas=[],
    )
    checker = ComplianceChecker(str(_FIXTURE), profile=custom)
    rep = checker.run()
    assert rep["standard"] == "ISO26262"
    assert rep["version"] == "2018"
    # 无 area 时无 swe 区块
    assert rep["swe_sections"] == {}
    assert rep["summary"]["total_bps"] == 0


def test_injected_real_profile_runs():
    profile = load_profile("aspice_v3.1")
    checker = ComplianceChecker(str(_FIXTURE), profile=profile)
    rep = checker.run()
    assert rep["standard"] == "ASPICE"
    assert "swe.1" in rep["swe_sections"]
    assert _norm(rep) == _norm(ComplianceChecker(str(_FIXTURE)).run())
