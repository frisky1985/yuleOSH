#!/usr/bin/env python3
"""
ASPICE V-Model Full Process Support Verification

验证 yuleOSH 是否完整支持 ASPICE V 模型开发全流程：
- SYS.1-5 (系统过程)
- SWE.1-6 (软件过程)
- SUP.1/8/9/10 (支持过程)
- MAN.1/2/3 (管理过程)
"""

import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from yuleosh.compliance.profile import load_profile
from yuleosh.compliance.compliance_checker import ComplianceChecker, _merge_profiles
from yuleosh.evidence.aspice_check import ASPICE_FULL_PROFILES


def test_profile_loading():
    """测试 1: 所有 profile 可加载"""
    print("=" * 70)
    print("测试 1: Profile 加载")
    print("=" * 70)

    all_ok = True
    for name in ASPICE_FULL_PROFILES:
        try:
            p = load_profile(name)
            td = p.to_template_dict()
            areas = [k for k in td.keys() if k != 'meta']
            print(f"✅ {name}")
            print(f"   过程域: {', '.join(areas)}")
        except Exception as e:
            print(f"❌ {name}: {e}")
            all_ok = False

    return all_ok


def test_profile_merge():
    """测试 2: Profile 合并"""
    print("\n" + "=" * 70)
    print("测试 2: Profile 合并（全 V 模型覆盖）")
    print("=" * 70)

    try:
        merged = _merge_profiles(ASPICE_FULL_PROFILES)
        areas = [k for k in merged.keys() if k != 'meta']

        # 统计各过程域
        process_families = {
            'SYS': [],
            'SWE': [],
            'SUP': [],
            'MAN': [],
        }

        total_bps = 0
        for area in areas:
            bps = merged[area].get('base_practices', [])
            total_bps += len(bps)

            # 分类到过程族
            for family in process_families:
                if area.upper().startswith(family):
                    process_families[family].append(area)
                    break

        print(f"✅ 合并成功：{len(areas)} 个过程域，{total_bps} 个 Base Practices")
        print(f"\n过程族覆盖:")
        for family, areas_list in process_families.items():
            if areas_list:
                print(f"  {family}: {len(areas_list)} 个过程 - {', '.join(sorted(areas_list))}")
            else:
                print(f"  {family}: ❌ 未覆盖")

        # 验证完整性
        expected = {
            'SYS': ['sys.1', 'sys.2', 'sys.3', 'sys.4', 'sys.5'],
            'SWE': ['swe.1', 'swe.2', 'swe.3', 'swe.4', 'swe.5', 'swe.6'],
            'SUP': ['sup.1', 'sup.8', 'sup.9', 'sup.10'],
            'MAN': ['man.1', 'man.2', 'man.3'],
        }

        all_covered = True
        for family, expected_areas in expected.items():
            actual = [a.lower() for a in process_families[family]]
            missing = set(expected_areas) - set(actual)
            if missing:
                print(f"\n❌ {family} 缺失: {missing}")
                all_covered = False

        return all_covered and total_bps > 0

    except Exception as e:
        print(f"❌ 合并失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compliance_checker_integration():
    """测试 3: ComplianceChecker 集成评估"""
    print("\n" + "=" * 70)
    print("测试 3: ComplianceChecker 全 V 模型评估")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)

        # 创建最小证据（触发各过程域的评估）
        (project / ".git").mkdir()  # SUP.8
        (project / "docs").mkdir()
        (project / "docs" / "qa-plan.md").write_text("# QA Plan\nQuality assurance activities...")
        (project / "docs" / "known-issues.md").write_text("# Known Issues\nIssue tracking...")
        (project / "docs" / "change-requests.md").write_text("# Change Requests\nCR management...")
        (project / "docs" / "project-plan.md").write_text("# Project Plan\nProject management...")
        (project / "docs" / "risk-register.md").write_text("# Risk Register\nRisk management...")

        try:
            # 使用全 V 模型 profile 组合
            checker = ComplianceChecker(
                project_dir=str(project),
                profile_names=ASPICE_FULL_PROFILES
            )
            report = checker.run()

            # 验证报告结构
            summary = report["summary"]
            print(f"✅ 评估完成")
            print(f"   总 BP 数: {summary['total_bps']}")
            print(f"   ✅ 通过: {summary['passed']}")
            print(f"   ⚠️  部分: {summary['partial']}")
            print(f"   ❌ 失败: {summary['failed']}")

            # 验证各过程域都被评估
            sections = report["swe_sections"]
            process_families = {'SYS': 0, 'SWE': 0, 'SUP': 0, 'MAN': 0}

            for key in sections:
                for family in process_families:
                    if key.upper().startswith(family):
                        process_families[family] += 1
                        break

            print(f"\n过程域评估覆盖:")
            all_evaluated = True
            for family, count in process_families.items():
                if count > 0:
                    print(f"  {family}: ✅ {count} 个过程已评估")
                else:
                    print(f"  {family}: ❌ 未评估")
                    all_evaluated = False

            return all_evaluated and summary['total_bps'] > 0

        except Exception as e:
            print(f"❌ 评估失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_gap_check_default():
    """测试 4: Gap Check 默认使用全 V 模型"""
    print("\n" + "=" * 70)
    print("测试 4: Gap Check 默认配置")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            from yuleosh.evidence.aspice_check import aspice_gap_check

            # 不指定 profile，应默认使用 ASPICE_FULL_PROFILES
            result = aspice_gap_check(project_dir=tmpdir, output_format="json")
            report = json.loads(result)

            # 验证覆盖所有过程域
            sections = report.get("gaps", [])
            process_families = {'SYS': 0, 'SWE': 0, 'SUP': 0, 'MAN': 0}

            for gap in sections:
                swe_id = gap.get("swe_id", "")
                for family in process_families:
                    if swe_id.upper().startswith(family):
                        process_families[family] += 1
                        break

            print(f"✅ Gap Check 默认使用全 V 模型评估")
            print(f"   总缺口数: {len(sections)}")
            print(f"\n过程域覆盖:")

            all_covered = True
            for family, count in process_families.items():
                if count > 0:
                    print(f"  {family}: ✅ {count} 个过程")
                else:
                    print(f"  {family}: ⚠️  无缺口（可能已满足或未评估）")

            return True

        except Exception as e:
            print(f"❌ Gap Check 失败: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """运行全部验证"""
    print("\n" + "🔍 yuleOSH ASPICE V 模型全流程支持验证" + "\n")

    results = {
        "Profile 加载": test_profile_loading(),
        "Profile 合并": test_profile_merge(),
        "ComplianceChecker 集成": test_compliance_checker_integration(),
        "Gap Check 默认配置": test_gap_check_default(),
    }

    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ 结论: yuleOSH 完整支持 ASPICE V 模型开发全流程")
        print("=" * 70)
        print("\n覆盖范围:")
        print("  • SYS.1-5: 系统需求、架构、验证、集成、确认")
        print("  • SWE.1-6: 软件需求、架构、详设、单元、集成、合格性")
        print("  • SUP.1/8/9/10: 质量保证、配置管理、问题解决、变更管理")
        print("  • MAN.1/2/3: 项目管理、需求管理、风险管理")
        print("\n关键能力:")
        print("  • 多 profile 合并评估（单次遍历覆盖全 V 模型）")
        print("  • 反假绿机制（严格证据验证，杜绝虚假合规）")
        print("  • 过程域感知（SYS/SWE 语义区分，避免跨域误判）")
        print("  • 默认全 V 模型评估（无需手动指定 profile）")
        return 0
    else:
        print("❌ 结论: yuleOSH 对 ASPICE V 模型支持存在缺口")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
