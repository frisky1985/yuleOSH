"""SUP/MAN 评估域接入回归测试（P2(b) / SYS-REQ: 支持管理过程可评估）。

守住：SUP.1/8/9/10 与 MAN.1/2/3 此前无任何分支匹配，检查项一律落入
"unknown check type — not recognized" → 有评估动作也判不了。本测试证明：

- A: 空项目跑 support/mgmt profile → 各过程域 section 存在，且检查项**不再**
     落入 unknown 兜底（已被 P2 分支分发），无证据时如实判 RED（反假绿）。
- B: 真实产物齐备 → 对应 BP 判 GREEN（诚实 GREEN 路径）。
- C: 组合 profile（SWE + SUP/MAN）合并生效，``swe_sections`` 同时含 swe.* 与
     sup.*/man.*，无键冲突。
"""

import os

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile


def _status_for(report, area_key, needle):
    """返回 area_key 过程域中匹配 needle 的检查项是否为 GREEN(True)/RED(False)。"""
    section = report["swe_sections"][area_key]
    for bp in section["base_practices"]:
        for d in bp["details"]:
            if needle in d:
                return "✅" in d
    raise AssertionError(f"{area_key} 未找到含 '{needle}' 的检查项")


def _all_details(report, area_key):
    out = []
    for bp in report["swe_sections"][area_key]["base_practices"]:
        out.extend(bp["details"])
    return out


def _make_project(tmp_path, with_evidence=False):
    """构造项目；with_evidence=True 时写入 SUP/MAN 真实产物。"""
    if with_evidence:
        # 模拟版本控制（配置管理基线的最低下限诚实证据）
        (tmp_path / ".git").mkdir(exist_ok=True)
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "qa-plan.md").write_text(
            "# QA Plan\n\n"
            "- 质量保证计划已定义并评审通过，覆盖代码评审、静态分析与单元测试门禁。\n"
            "- 独立 QA 角色按里程碑执行审计，审计发现项纳入缺陷跟踪直至闭环。\n"
            "- 发布前须通过合格性测试与发布评审，方可进入配置管理基线。\n",
            encoding="utf-8")
        (docs / "project-plan.md").write_text(
            "# Project Plan\n\n"
            "- 项目计划含进度与里程碑安排，WBS 分解为需求、设计、实现、验证四个阶段。\n"
            "- 每阶段设定出口准则与负责人，并按周跟踪进度与偏差。\n"
            "- 里程碑 M1 需求冻结、M2 架构评审、M3 集成测试、M4 合格性测试与发布评审。\n",
            encoding="utf-8")
        (docs / "risk-register.md").write_text(
            "# Risk Register\n\n| Risk ID | Description | Likelihood | Impact | Mitigation |\n"
            "|---|---|---|---|---|\n| R1 | 硬件交付延迟 | 中 | 高 | 预留缓冲与替代供应商 |\n"
            "| R2 | 需求蔓延 | 高 | 中 | 变更控制委员会评审 |\n",
            encoding="utf-8")
        (docs / "change-requests.md").write_text(
            "# Change Requests\n\n| CR ID | Title | Status | Decision |\n|---|---|---|---|\n"
            "| CR-1 | 新增看门狗定时器 | analyzed | approved |\n"
            "| CR-2 | 调整通信波特率 | analyzed | rejected |\n",
            encoding="utf-8")
        (docs / "known-issues.md").write_text(
            "# Known Issues\n\n| Issue ID | Description | Status | Closure |\n|---|---|---|---|\n"
            "| ISS-1 | 低温下 ADC 读数漂移 | closed | 已通过硬件滤波修复 |\n"
            "| ISS-2 | 日志偶发丢帧 | closed | 已增大缓冲区 |\n",
            encoding="utf-8")
    return tmp_path


def test_sup_man_sections_present_and_evaluated_not_unknown(tmp_path):
    """A: 空项目 → SUP/MAN 各过程域存在，且检查项不再落入 unknown 兜底。"""
    p = _make_project(tmp_path, with_evidence=False)
    checker = ComplianceChecker(
        project_dir=str(p),
        profile_names=["aspice_support_mgmt_v3.1"],
    )
    report = checker.run()

    expected_areas = ["sup.1", "sup.8", "sup.9", "sup.10", "man.1", "man.2", "man.3"]
    for area in expected_areas:
        assert area in report["swe_sections"], f"{area} 过程域未在报告中出现（评估域缺失）"
        # 关键断言：不得有 "unknown check type" —— 证明已被 P2 分支分发
        for d in _all_details(report, area):
            assert "unknown check type" not in d, f"{area} 仍有检查项落入 unknown 兜底: {d}"


def test_sup_man_red_without_evidence(tmp_path):
    """A': 空项目 → 无证据时如实判 RED（反假绿，绝不臆造 GREEN）。"""
    p = _make_project(tmp_path, with_evidence=False)
    checker = ComplianceChecker(
        project_dir=str(p),
        profile_names=["aspice_support_mgmt_v3.1"],
    )
    report = checker.run()

    # SUP.8 配置管理：无 .git → RED
    assert _status_for(report, "sup.8", "version control") is False
    # MAN.3 风险：无 risk-register.md → RED
    assert _status_for(report, "man.3", "risk register") is False
    # SUP.9 问题：无 known-issues.md → RED
    assert _status_for(report, "sup.9", "Problems and defects") is False
    # SUP.10 变更：无 change-requests.md → RED
    assert _status_for(report, "sup.10", "Change requests are identified") is False


def test_sup_man_green_with_evidence(tmp_path):
    """B: 真实产物齐备 → 对应 BP 判 GREEN（诚实 GREEN 路径）。"""
    p = _make_project(tmp_path, with_evidence=True)
    checker = ComplianceChecker(
        project_dir=str(p),
        profile_names=["aspice_support_mgmt_v3.1"],
    )
    report = checker.run()

    assert _status_for(report, "sup.8", "version control") is True
    assert _status_for(report, "man.3", "risk register") is True
    assert _status_for(report, "sup.9", "Problems and defects") is True
    assert _status_for(report, "sup.10", "Change requests are identified") is True
    assert _status_for(report, "man.1", "project plan with schedule") is True
    assert _status_for(report, "sup.1", "quality assurance plan") is True


def test_combined_profiles_merge_swe_and_sup_man(tmp_path):
    """C: 组合 profile（SWE + SUP/MAN）合并生效，swe_sections 同时含两类域。"""
    p = _make_project(tmp_path, with_evidence=True)
    checker = ComplianceChecker(
        project_dir=str(p),
        profile_names=["aspice_v3.1", "aspice_support_mgmt_v3.1"],
    )
    report = checker.run()

    # 工程过程域与 支持/管理过程域 同时出现，证明合并无键冲突
    assert "swe.1" in report["swe_sections"]
    assert "sup.1" in report["swe_sections"]
    assert "man.3" in report["swe_sections"]
    # SWE.1 自身评估未被合并破坏
    assert report["swe_sections"]["swe.1"]["id"] == "SWE.1"
    assert report["swe_sections"]["sup.1"]["id"] == "SUP.1"
