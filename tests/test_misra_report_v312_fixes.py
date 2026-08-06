"""
v3.12.x 遗留 7 失败修复 — 根因回归测试（sprint-contract-v312-fixes.md）。

覆盖三个 MISRA 根因场景（08-05 yuleDKCS 教训：报告数字必须可溯源）：
  1. parse_cppcheck_output 过滤 unmatchedSuppression / branch-limit 信息行
     （1b700f9d 引入，防止信息行被误计为违规导致 3615 vs 0 式数字失真）
  2. save_report 序列化：violations_raw 与 groups 同源一致
     （修复 groups 有数据但 raw 数组空的序列化 bug）
  3. 报告更新逻辑：清空重跑后数字正确（旧数据残留不污染新报告）

另含 fault-inject fixture 挂载语义验证（无 CMakeLists 时跳过构建不报错）。
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from yuleosh.ci.misra_report.core.analysis import group_by_rule
from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
from yuleosh.ci.misra_report.core.reporting import save_report

# ===========================================================================
# 根因1: parse_cppcheck_output 过滤 unmatchedSuppression / branch-limit
# ===========================================================================


class TestParserFiltersDiagnosticLines:
    """unmatchedSuppression / branch-limit 信息行不得被当作违规。"""

    def test_unmatched_suppression_not_counted(self):
        """Suppressed 'x' from 'file' [unmatchedSuppression] 不是违规。"""
        text = (
            "[/src/main.c:42:5] (style) misra violation "
            "(use --rule-texts=<file> to get proper output) [misra-c2012-17.7]\n"
            "[/src/main.c:1:0] (information) Suppressed 'missingIncludeSystem' "
            "from '/src/main.c' [unmatchedSuppression]\n"
        )
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1, f"unmatchedSuppression 被误计: {violations}"
        assert violations[0]["rule_id"] == "misra-c2023-17.7"
        assert "unmatchedSuppression" not in violations[0]["message"]

    def test_branch_limit_not_counted(self):
        """Branch limit of N exceeded [branch-limit] 不是违规。"""
        text = (
            "[/src/uart.c:10:0] (information) Branch limit of 1000 exceeded "
            "[branch-limit]\n"
            "[/src/uart.c:12:4] (style) misra violation "
            "(use --rule-texts=<file> to get proper output) [misra-c2012-15.6]\n"
        )
        violations = parse_cppcheck_output(text)
        assert len(violations) == 1, f"branch-limit 被误计: {violations}"
        assert violations[0]["rule_id"] == "misra-c2023-15.6"

    def test_real_information_findings_still_counted(self):
        """missingInclude 等真实 information 级 finding 仍保留（可溯源计数）。"""
        text = (
            "[/src/utils.c:10:0] (information) Include file: \"config.h\" "
            "not found. [missingInclude]\n"
            "[nofile:0:0] (information) Active checkers: 309/1056 "
            "[checkersReport]\n"
        )
        violations = parse_cppcheck_output(text)
        # missingInclude + checkersReport 都是真实信息（保留）；无违规规则 ID
        assert len(violations) == 2
        sevs = {v["severity"] for v in violations}
        assert sevs == {"information"}

    def test_mixed_output_counts_only_real_violations(self):
        """混合输出：只有真实违规计入，诊断信息行被过滤。"""
        text = (
            "[/src/main.c:42:5] (style) misra violation "
            "(use --rule-texts=<file> to get proper output) [misra-c2012-17.7]\n"
            "[/src/main.c:1:0] (information) Suppressed 'x' [unmatchedSuppression]\n"
            "[nofile:0:0] (information) Branch limit of 1000 exceeded "
            "[branch-limit]\n"
            "[/src/utils.c:10:0] (information) Include file: \"config.h\" "
            "not found. [missingInclude]\n"
        )
        violations = parse_cppcheck_output(text)
        # 2 条真实（17.7 + missingInclude），2 条诊断行被过滤
        assert len(violations) == 2
        rules = [v["rule_id"] for v in violations]
        assert "misra-c2023-17.7" in rules
        assert None in rules  # missingInclude 无 MISRA 规则 ID 但保留计数


# ===========================================================================
# 根因2: save_report 序列化 — violations_raw 与 groups 同源一致
# ===========================================================================


class TestSaveReportRawGroupsConsistency:
    """save_report 输出中 violations_raw 与 groups 必须一致、可溯源。"""

    def _make_violations(self):
        return [
            {"rule_id": "Rule 10.1", "severity": "high", "file": "a.c",
             "line": 10, "message": "Implicit conversion"},
            {"rule_id": "Rule 10.1", "severity": "high", "file": "a.c",
             "line": 20, "message": "Implicit conversion"},
            {"rule_id": "Rule 15.6", "severity": "medium", "file": "b.c",
             "line": 30, "message": "Nesting"},
        ]

    def test_raw_length_equals_violations(self):
        """violations_raw 长度必须等于输入 violations 数（不为空）。"""
        violations = self._make_violations()
        groups = group_by_rule(violations)
        with tempfile.TemporaryDirectory() as td:
            json_path, _, _, _ = save_report(
                violations, groups, {}, {}, Path(td)
            )
            report = json.loads(json_path.read_text())
            assert report["total_violations"] == 3
            assert len(report["violations_raw"]) == 3, (
                f"violations_raw 为空/不一致: {len(report['violations_raw'])}"
            )

    def test_groups_counts_match_raw(self):
        """groups 每规则 count 必须等于 violations_raw 中该规则条数。"""
        violations = self._make_violations()
        groups = group_by_rule(violations)
        with tempfile.TemporaryDirectory() as td:
            json_path, _, _, _ = save_report(
                violations, groups, {}, {}, Path(td)
            )
            report = json.loads(json_path.read_text())
            raw_counts = Counter(v["rule_id"] for v in report["violations_raw"])
            for rid, g in report["groups"].items():
                assert g["count"] == raw_counts.get(rid, 0), (
                    f"{rid}: groups={g['count']} != raw={raw_counts.get(rid, 0)}"
                )

    def test_raw_empty_groups_empty_consistent(self):
        """无违规时 raw 与 groups 都为空且 total=0（一致的空态）。"""
        with tempfile.TemporaryDirectory() as td:
            json_path, _, _, _ = save_report(
                [], {}, {}, {}, Path(td)
            )
            report = json.loads(json_path.read_text())
            assert report["total_violations"] == 0
            assert report["violations_raw"] == []
            assert report["groups"] == {}

    def test_new_style_dict_roundtrip(self):
        """new-style save_report(report_dict, output_dir) 保持 raw/groups。"""
        violations = self._make_violations()
        groups = group_by_rule(violations)
        with tempfile.TemporaryDirectory() as td:
            json_path, _, _, _ = save_report(
                violations, groups, {}, {}, Path(td)
            )
            report = json.loads(json_path.read_text())
            # new-style 路径：直接以 report dict 再存一次（返回 list[Path]）
            saved = save_report(report, Path(td), "misra-report-copy")
            json_path2 = saved[0]
            report2 = json.loads(json_path2.read_text())
            assert len(report2["violations_raw"]) == 3
            assert report2["total_violations"] == 3


# ===========================================================================
# 根因3: 旧数据残留 — 清空重跑后数字必须正确
# ===========================================================================


class TestSaveReportNoStaleData:
    """预置旧污染报告后重跑，新报告数字必须正确（无残留）。"""

    def _write_stale_report(self, out: Path):
        """模拟旧 bug 残留：groups 有数据但 raw 空 + total=999。"""
        stale = {
            "schema_version": "1.0",
            "generated_at": "old",
            "total_violations": 999,
            "unique_rules": 99,
            "violations_raw": [],  # 旧 bug：raw 空
            "groups": {"Rule 99.9": {"count": 999, "violations": []}},
        }
        (out / "misra-report.json").write_text(json.dumps(stale))
        (out / "misra-report.md").write_text("OLD STALE CONTENT 999")

    def test_rerun_overwrites_stale_json(self):
        """清空重跑后 total_violations 为真实新数（非 999）。"""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self._write_stale_report(out)
            violations = [
                {"rule_id": "Rule 10.1", "severity": "high", "file": "a.c",
                 "line": 10, "message": "m1"},
            ]
            groups = group_by_rule(violations)
            json_path, _, _, _ = save_report(
                violations, groups, {}, {}, out
            )
            fresh = json.loads(json_path.read_text())
            assert fresh["total_violations"] == 1, (
                f"旧数据残留: 期望 1 实际 {fresh['total_violations']}"
            )
            assert len(fresh["violations_raw"]) == 1

    def test_rerun_overwrites_stale_markdown(self):
        """markdown 报告全量重写，不含旧内容。"""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self._write_stale_report(out)
            violations = [
                {"rule_id": "Rule 10.1", "severity": "high", "file": "a.c",
                 "line": 10, "message": "m1"},
            ]
            groups = group_by_rule(violations)
            _, md_path, _, _ = save_report(
                violations, groups, {}, {}, out
            )
            md_content = md_path.read_text()
            assert "OLD STALE CONTENT" not in md_content
            assert "999" not in md_content

    def test_stale_groups_not_merged_into_fresh(self):
        """旧报告 groups（Rule 99.9）不得出现在新报告。"""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self._write_stale_report(out)
            violations = [
                {"rule_id": "Rule 10.1", "severity": "high", "file": "a.c",
                 "line": 10, "message": "m1"},
            ]
            groups = group_by_rule(violations)
            json_path, _, _, _ = save_report(
                violations, groups, {}, {}, out
            )
            fresh = json.loads(json_path.read_text())
            assert "Rule 99.9" not in fresh["groups"]
            assert fresh["groups"]["Rule 10.1"]["count"] == 1


# ===========================================================================
# fault-inject fixture: CMakeLists 挂载语义
# ===========================================================================


class TestFaultInjectFixtureMount:
    """src/fault-inject/CMakeLists.txt 存在且构建跳过语义正确。"""

    def test_cmake_lists_exists(self):
        """fixture CMakeLists.txt 必须存在（含 fault-inject 目标）。"""
        repo_root = Path(__file__).resolve().parent.parent
        cmake = repo_root / "src" / "fault-inject" / "CMakeLists.txt"
        assert cmake.exists(), f"缺失: {cmake}"
        content = cmake.read_text()
        assert "add_library(fault-inject" in content
        assert "FAULT_INJECT_TESTS" in content

    def test_build_skips_without_cmake_lists(self):
        """无 CMakeLists.txt → 跳过构建（不调用 cmake，不报错）。"""
        from unittest.mock import patch

        from yuleosh.pipeline.step_handlers.fault_inject import FaultInjectStage

        stage = FaultInjectStage()
        with tempfile.TemporaryDirectory() as td, patch("subprocess.run") as mock_run:
            result = stage.build_test_firmware(td)
            assert result is False
            mock_run.assert_not_called()
