#!/usr/bin/env python3
"""
E2E Integration Tests — 完整报告管道的端到端测试

测试内容：
  1. MISRA 完整管道路径：mock cppcheck output → parse → group → enrich → report (JSON/MD/Excel)
  2. UT 完整管道路径：mock JUnit XML + lcov → parse → coverage report
  3. 趋势导出：MISRA + UT 趋势 JSON 输出
  4. Tool Drivers: CppcheckDriver + ClangTidyDriver stub
  5. 测试输出文件存在且包含期望字段

模拟数据来源：tests/ci/mock_report_data.py

Usage:
    pytest tests/ci/test_e2e_report_pipeline.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add project source to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src" / "yuleosh" / "ci"))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# Import modules under test
from yuleosh.ci.misra_report import (
    parse_cppcheck_output,
    group_by_rule,
    enrich_with_definitions,
    compute_summary_stats,
    generate_json_report,
    generate_markdown_report,
    save_report,
    load_rule_definitions,
    get_tool_version,
)

from yuleosh.report.trend_exporter import (
    export_misra_trend,
    export_ut_trend,
    export_all_trends,
    export_trend_for_project,
)

from yuleosh.ci.tool_drivers import (
    create_driver,
    CppcheckDriver,
    ClangTidyDriver,
    list_drivers,
)

# Import mock data generators
sys.path.insert(0, str(_PROJECT_ROOT / "tests" / "ci"))
from mock_report_data import (
    make_misra_output,
    make_misra_output_empty,
    make_misra_output_only_header,
    make_misra_output_malformed,
    make_misra_output_massive,
    make_junit_xml,
    make_junit_xml_with_shall,
    make_junit_empty,
    make_junit_malformed,
    make_lcov,
    make_lcov_extreme,
    make_lcov_empty,
    make_trend_jsonl_entry,
)

# Import test helpers from review_helpers (public API)
from yuleosh.ci.review_helpers import (
    parse_junit_xml,
    auto_map_shall_coverage,
)

# Report directory for test outputs
_TEST_OUTPUT_DIR = _PROJECT_ROOT / ".yuleosh" / "reports"


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_misra_dir(tmp_path):
    """Create a mock project directory with trend JSONL files."""
    report_dir = tmp_path / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Write a few MISRA trend entries
    misra_trend = report_dir / "misra-trend.jsonl"
    with open(misra_trend, "w", encoding="utf-8") as f:
        for i in range(10):
            f.write(make_trend_jsonl_entry(
                report_type="misra",
                total_violations=10 - i,
                required=5 - i // 2,
                advisory=3 - i // 3,
                commit=f"commit{i:08x}",
            ))

    # Write a few coverage trend entries
    cov_trend = report_dir / "coverage-trend.jsonl"
    with open(cov_trend, "w", encoding="utf-8") as f:
        for i in range(10):
            f.write(make_trend_jsonl_entry(
                report_type="coverage",
                line_rate=80.0 + i,
                branch_rate=70.0 + i * 0.5,
                commit=f"commit{i:08x}",
            ))

    return tmp_path


# ===========================================================================
# A: MISRA 完整管道路径
# ==========================================================================


class TestMisraPipelineE2E:
    """A1: 模拟 cppcheck raw output + 跑完整 MISRA 报告管道"""

    def test_full_pipeline_with_mock_data(self, tmp_path):
        """使用模拟数据走完 parse → group → enrich → summary → JSON/MD 全过程。"""
        raw_output = make_misra_output(count=15)

        # Step 1: Parse
        violations = parse_cppcheck_output(raw_output)
        assert len(violations) > 0, f"Expected violations, got {len(violations)}"

        # Step 2: Load rules
        rule_defs = load_rule_definitions()

        # Step 3: Group & enrich
        groups = group_by_rule(violations)
        enriched = enrich_with_definitions(violations, rule_defs)

        # Step 4: Summary
        summary = compute_summary_stats(enriched, groups)
        assert summary["total_violations"] > 0
        assert summary["unique_rules"] > 0

        # Step 5: Generate JSON report
        output_dir = tmp_path / ".yuleosh" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        report = generate_json_report(violations, groups, rule_defs, output_dir=output_dir)

        # Verify all expected fields exist
        assert "generated_at" in report
        assert "total_violations" in report
        assert "groups" in report

    def test_output_file_exists_and_has_fields(self, tmp_path):
        """检查输出文件（JSON/MD）存在且包含期望字段。"""
        raw_output = make_misra_output(count=8)
        violations = parse_cppcheck_output(raw_output)
        rule_defs = load_rule_definitions()
        groups = group_by_rule(violations)
        enriched = enrich_with_definitions(violations, rule_defs)
        summary = compute_summary_stats(enriched, groups)

        output_dir = tmp_path / ".yuleosh" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save reports
        json_path, md_path, trace_path, excel_path = save_report(
            violations, groups, summary, rule_defs, output_dir,
        )

        # Verify files exist
        assert json_path.exists(), f"JSON report not found: {json_path}"
        assert md_path.exists(), f"MD report not found: {md_path}"
        assert trace_path.exists(), f"Traceability matrix not found: {trace_path}"

        # Verify JSON content has expected fields
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "total_violations" in data
        assert "groups" in data
        assert data["total_violations"] == len(violations)

        # Verify MD content
        md_content = md_path.read_text(encoding="utf-8")
        assert "MISRA" in md_content or "Report" in md_content
        assert str(summary["total_violations"]) in md_content

    def test_json_fields_consistency(self, tmp_path):
        """验证 JSON 报告各字段之间的一致性。"""
        raw_output = make_misra_output(count=10)
        violations = parse_cppcheck_output(raw_output)
        rule_defs = load_rule_definitions()
        groups = group_by_rule(violations)
        enriched = enrich_with_definitions(violations, rule_defs)
        summary = compute_summary_stats(enriched, groups)

        report = generate_json_report(violations, groups, rule_defs)

        # violations count matches
        assert len(violations) == report["total_violations"]

        # groups count matches
        assert report["unique_rules"] == len(groups)


# ===========================================================================
# B: UT 管道路径
# ==========================================================================


class TestUTPipelineE2E:
    """B1: 模拟 JUnit XML + lcov + 部分 UT 报告管道"""

    def test_junit_parse_with_mock_data(self, tmp_path):
        """模拟 JUnit XML 解析。"""
        xml = make_junit_xml(total=10, passed=6, failed=2, skipped=1, errors=1)
        xml_path = tmp_path / "junit.xml"
        xml_path.write_text(xml, encoding="utf-8")

        results = parse_junit_xml(xml_path)
        assert len(results) == 10
        passed = sum(1 for r in results if r["status"] == "passed")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = sum(1 for r in results if r["status"] == "error")

        assert passed == 6
        assert failed == 2
        assert skipped == 1
        assert errors == 1

    def test_junit_with_shall_mapping(self, tmp_path):
        """模拟 JUnit XML + SHALL 自动映射。"""
        xml = make_junit_xml_with_shall(["10_1", "17_7", "12_1", "15_5"], all_passed=True)
        xml_path = tmp_path / "junit_shall.xml"
        xml_path.write_text(xml, encoding="utf-8")

        results = parse_junit_xml(xml_path)
        assert len(results) == 4

        # Simulate SHALL statements
        shall_statements = [
            {"statement": "SHALL-10.1 The system shall do X.", "section": "3.1", "line": 10},
            {"statement": "SHALL-17.7 No printf allowed.", "section": "5.2", "line": 20},
            {"statement": "SHALL-12.1 Types shall be consistent.", "section": "4.1", "line": 15},
            {"statement": "SHALL-15.5 Return shall be consistent.", "section": "6.1", "line": 25},
            {"statement": "SHALL-8.4 Prototypes required.", "section": "2.1", "line": 5},
        ]
        covered, shall_map, assertion_map = auto_map_shall_coverage(shall_statements, results)
        assert len(covered) == 4  # 10_1, 17_7, 12_1, 15_5 all covered
        assert 4 not in covered  # SHALL-8.4 not tested

    def test_junit_edge_cases(self, tmp_path):
        """测试 JUnit 边缘场景：空、格式异常、纯净通过。"""
        # Empty
        empty = make_junit_empty()
        p = tmp_path / "empty.xml"
        p.write_text(empty)
        assert parse_junit_xml(p) == []

        # Malformed
        p2 = tmp_path / "bad.xml"
        p2.write_text(make_junit_malformed())
        assert parse_junit_xml(p2) == []

        # 100% passed
        xml = make_junit_xml(total=20, passed=20, failed=0, skipped=0)
        p3 = tmp_path / "all_pass.xml"
        p3.write_text(xml)
        results = parse_junit_xml(p3)
        assert len(results) == 20
        assert all(r["status"] == "passed" for r in results)


# ===========================================================================
# C: Trend Exporter 测试
# ==========================================================================


class TestTrendExporterE2E:
    """C1: 趋势导出器 — MISRA 和 UT 维度"""

    def test_export_misra_trend(self, mock_misra_dir):
        """验证 MISRA 趋势导出。"""
        result = export_misra_trend(str(mock_misra_dir))
        assert result["report_type"] == "misra"
        assert "project" in result
        assert "generated_at" in result
        assert len(result["history"]) > 0
        assert result["total_entries"] == 10

        # Check history entry fields
        entry = result["history"][0]
        assert "build_id" in entry
        assert "generated_at" in entry
        assert "total_violations" in entry
        assert "required" in entry
        assert "advisory" in entry
        assert "files_checked" in entry

    def test_export_ut_trend(self, mock_misra_dir):
        """验证 UT/覆盖率趋势导出。"""
        result = export_ut_trend(str(mock_misra_dir))
        assert result["report_type"] == "ut"
        assert "project" in result
        assert len(result["history"]) > 0
        assert result["total_entries"] == 10

        # Check history entry fields (coverage trend entries)
        entry = result["history"][0]
        assert "build_id" in entry
        assert "generated_at" in entry
        assert "line_rate" in entry
        assert "branch_rate" in entry
        assert "total_files" in entry

    def test_export_all_trends(self, mock_misra_dir):
        """验证 MISRA + UT 完整趋势汇总。"""
        result = export_all_trends(str(mock_misra_dir))
        assert "trends" in result
        assert "misra" in result["trends"]
        assert "ut" in result["trends"]
        assert result["trends"]["misra"]["report_type"] == "misra"
        assert result["trends"]["ut"]["report_type"] == "ut"
        assert "generated_at" in result
        assert "project" in result

    def test_export_image_trend_with_project_id(self, mock_misra_dir):
        """验证 project_id 维度的趋势导出。"""
        result = export_misra_trend(str(mock_misra_dir), project_id="my-project-v2")
        assert result["project"] == "my-project-v2"

    def test_export_trend_empty_dir(self, tmp_path):
        """验证空项目目录的趋势导出（无数据时返回空 history）。"""
        # No trend files exist yet
        result = export_misra_trend(str(tmp_path))
        assert result["report_type"] == "misra"
        assert result["total_entries"] == 0
        assert len(result["history"]) == 0

        result_ut = export_ut_trend(str(tmp_path))
        assert result_ut["total_entries"] == 0

    def test_export_trend_for_project_api(self, mock_misra_dir):
        """验证 export_trend_for_project API。"""
        result = export_trend_for_project(str(mock_misra_dir), "misra")
        assert result is not None
        assert result["report_type"] == "misra"

        result_ut = export_trend_for_project(str(mock_misra_dir), "ut")
        assert result_ut is not None
        assert result_ut["report_type"] == "ut"

        result_unknown = export_trend_for_project(str(mock_misra_dir), "unknown")
        assert result_unknown is None


# ===========================================================================
# D: Tool Drivers 测试
# ==========================================================================


class TestToolDrivers:
    """D1: Tool Drivers — CppcheckDriver + ClangTidyDriver"""

    def test_create_cppcheck_driver(self, tmp_path):
        """创建 CppcheckDriver 并验证接口。"""
        driver = create_driver("cppcheck", str(tmp_path))
        assert isinstance(driver, CppcheckDriver)
        assert driver.name == "cppcheck"

    def test_create_clang_tidy_driver(self, tmp_path):
        """创建 ClangTidyDriver stub 并验证接口。"""
        driver = create_driver("clang-tidy", str(tmp_path))
        assert isinstance(driver, ClangTidyDriver)
        assert driver.name == "clang-tidy"

    def test_create_unknown_driver(self, tmp_path):
        """未知工具名称应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Unknown tool"):
            create_driver("unknown-tool", str(tmp_path))

    def test_cppcheck_driver_parse(self, tmp_path):
        """CppcheckDriver.parse() 应正确解析 mock 输入。"""
        driver = CppcheckDriver(str(tmp_path))
        raw = make_misra_output(count=5)
        violations = driver.parse(raw)
        # 5 violations + 1 checkersReport line
        assert len(violations) >= 5
        for v in violations:
            assert "file" in v
            assert "line" in v
            assert "severity" in v
            assert "message" in v

    def test_cppcheck_driver_parse_c2012_format(self, tmp_path):
        """CppcheckDriver 应正确解析 legacy 格式。"""
        driver = CppcheckDriver(str(tmp_path))
        raw = """\
/src/main.c:42:5: style: Violation [misra-c2012-17.7]
/src/main.c:95:9: style: Violation [misra-c2012-10.1]
"""
        violations = driver.parse(raw)
        assert len(violations) == 2
        for v in violations:
            # Parser normalizes to canonical C:2023 format
            assert v["rule_id"] in ("misra-c2023-17.7", "misra-c2023-10.1"), (
                f"Expected canonical misra-c2023-17.7 or misra-c2023-10.1, got {v['rule_id']}"
            )

    def test_clang_tidy_driver_stub(self, tmp_path):
        """ClangTidyDriver 所有方法应返回 stub 标识。"""
        driver = ClangTidyDriver(str(tmp_path))
        assert driver.parse("any input") == []
        assert "stub" in driver.run("/some/file.c").lower()
        report = driver.generate_report([])
        assert report["status"] == "stub"
        assert report["tool"] == "clang-tidy"

    def test_cppcheck_driver_generate_report(self, tmp_path):
        """CppcheckDriver.generate_report() 应生成有效报告。"""
        driver = CppcheckDriver(str(tmp_path))
        raw = make_misra_output(count=8)
        violations = driver.parse(raw)
        report = driver.generate_report(violations)

        assert "schema_version" in report
        assert "total_violations" in report
        assert report["total_violations"] == len(violations)

    def test_driver_registry_and_listing(self):
        """验证驱动注册表和列表功能。"""
        names = list_drivers()
        assert "cppcheck" in names
        assert "clang-tidy" in names


# ===========================================================================
# E: 边缘场景测试
# ==========================================================================


class TestEdgeCases:
    """覆盖边缘场景：空输出、巨量违规、极端覆盖率"""

    def test_empty_misra_output(self):
        """空 cppcheck 输出应返回空违规列表。"""
        violations = parse_cppcheck_output(make_misra_output_empty())
        assert violations == []

    def test_only_header_misra_output(self):
        """仅有 header 的 cppcheck 输出 — checkersReport 被解析为 1 条。"""
        violations = parse_cppcheck_output(make_misra_output_only_header())
        # The checkersReport line matches the legacy format
        assert len(violations) <= 1

    def test_malformed_misra_output(self):
        """格式异常的 cppcheck 输出不应崩溃，应正常解析可用行。"""
        raw = make_misra_output_malformed()
        violations = parse_cppcheck_output(raw)
        # 2-3 matches depending on format parsing:
        #   [/src/main.c:42:5] (style) Violation [misra-c2012-10.1] → valid
        #   [/src/utils.c:10:0] (unknown_severity) weird format here → valid
        #   [/src/main.c:99:1] (style) → message captures next line
        # The checkersReport line may also match.
        assert len(violations) >= 2

    def test_large_misra_output(self):
        """大量违规不应超过内存承受能力。"""
        raw = make_misra_output_massive(count=500)
        violations = parse_cppcheck_output(raw)
        # 500 violations + 1 checkersReport line
        assert len(violations) >= 500

    def test_large_misra_pipeline(self, tmp_path):
        """大量违规的完整管道不应失败。"""
        raw = make_misra_output_massive(count=200)
        violations = parse_cppcheck_output(raw)
        rule_defs = load_rule_definitions()
        groups = group_by_rule(violations)
        enriched = enrich_with_definitions(violations, rule_defs)
        summary = compute_summary_stats(enriched, groups)
        # 200 violations + 1 checkersReport line
        assert summary["total_violations"] >= 200
        assert summary["unique_rules"] >= 1

    def test_extreme_coverage_lcov(self):
        """极端覆盖率 lcov 输出不应失败。"""
        extremes = make_lcov_extreme()
        assert "zero_coverage" in extremes
        assert "full_coverage" in extremes
        assert "many_files" in extremes

        # All should be parseable (at least non-empty)
        for name, lcov_text in extremes.items():
            assert lcov_text
            if name == "zero_coverage":
                assert "DA:1,0" in lcov_text
            elif name == "full_coverage":
                assert "LH:" in lcov_text

    def test_empty_lcov(self):
        """空 lcov 文件应包含空字符串。"""
        assert make_lcov_empty() == ""

    def test_junit_extreme(self, tmp_path):
        """大量 JUnit 测试用例（1000个）不应失败。"""
        xml = make_junit_xml(total=1000, passed=900, failed=50, skipped=50, errors=0)
        p = tmp_path / "large.xml"
        p.write_text(xml)
        results = parse_junit_xml(p)
        assert len(results) == 1000
        passed = sum(1 for r in results if r["status"] == "passed")
        assert passed == 900


# ===========================================================================
# F: 多项目隔离测试
# ==========================================================================


class TestMultiProjectIsolation:
    """C: 多项目/多版本对比（轻量版）"""

    def test_project_id_in_trend(self, mock_misra_dir):
        """验证 trend 数据中包含 project_id。"""
        result = export_misra_trend(str(mock_misra_dir), project_id="project-alpha")
        assert result["project"] == "project-alpha"

        # Different project
        result2 = export_misra_trend(str(mock_misra_dir), project_id="project-beta")
        assert result2["project"] == "project-beta"
        # Data should be same (same underlying dir) but project IDs differ
        assert result["project"] != result2["project"]

    def test_file_based_project_isolation(self, tmp_path):
        """不同项目的目录隔离——各自维护独立的 .yuleosh/reports/ 目录。"""
        proj_a = tmp_path / "project-a"
        proj_b = tmp_path / "project-b"

        # Create trend data for project A
        report_a = proj_a / ".yuleosh" / "reports"
        report_a.mkdir(parents=True, exist_ok=True)
        with open(report_a / "misra-trend.jsonl", "w", encoding="utf-8") as f:
            f.write(make_trend_jsonl_entry(report_type="misra", total_violations=10))

        # Create different trend data for project B
        report_b = proj_b / ".yuleosh" / "reports"
        report_b.mkdir(parents=True, exist_ok=True)
        with open(report_b / "misra-trend.jsonl", "w", encoding="utf-8") as f:
            f.write(make_trend_jsonl_entry(report_type="misra", total_violations=25))

        # Each project sees its own data
        a_trend = export_misra_trend(str(proj_a))
        b_trend = export_misra_trend(str(proj_b))

        assert a_trend["history"][0]["total_violations"] == 10
        assert b_trend["history"][0]["total_violations"] == 25
        assert a_trend["project"] != b_trend["project"]
