# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""run_misra_check × ScannerAdapter 集成测试（2026-08-19 P1）。

验收标准 #1/#4：默认 cppcheck 路径零回归；商业工具经 report_file 全流程
（detect → run → parse → normalize → 报告）产出带 tool 字段的报告；
GSCR 翻译走 RulesetRegistry 单例实例（预存类级调用 bug 修复验证）。
"""

import json

from yuleosh.ci.result import CIResult
from yuleosh.ci.stages import run_misra_check

PARASOFT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<report version="2023.2">
  <file path="src/brake_control.c">
    <violation rule="MISRA.C.2012.10.1" line="42" severity="Error" category="Required">
      The operands of a logical operator shall be parenthesized
    </violation>
    <violation rule="MISRA.C.2012.15.7" line="57" severity="Warning" category="Required">
      All if...else if constructs shall be terminated with an else clause
    </violation>
  </file>
  <file path="src/brake_control.h">
    <violation rule="MISRA.C.2012.2.5" line="12" severity="Info" category="Advisory">
      A macro shall not be defined with the same name as a keyword
    </violation>
  </file>
</report>
"""


def _make_project(tmp_path, misra_yaml: str) -> str:
    src = tmp_path / "src"
    src.mkdir()
    (src / "brake_control.c").write_text("int x;\n")
    (src / "brake_control.h").write_text("#define X 1\n")
    y = tmp_path / ".yuleosh"
    y.mkdir()
    (y / "ci-config.yaml").write_text(misra_yaml)
    return str(tmp_path)


class TestScannerDispatch:
    def test_default_cppcheck_skips_when_no_c_files(self, tmp_path):
        """默认路径：无 C 文件 → skipped，返回 True（不回归）。"""
        ci = CIResult(1, "test")
        assert run_misra_check(str(tmp_path), ci) is True
        assert ci.stages[-1]["status"] == "skipped"

    def test_commercial_scanner_full_flow(self, tmp_path):
        """Parasoft report_file → detect/run/parse/normalize → 报告带 tool 字段。"""
        proj = _make_project(
            tmp_path,
            "misra:\n"
            "  scanner: parasoft\n"
            "  scanner_config:\n"
            "    report_file: parasoft-report.xml\n",
        )
        (tmp_path / "parasoft-report.xml").write_text(PARASOFT_XML)

        ci = CIResult(1, "test")
        result = run_misra_check(proj, ci)
        # 10.1 error + 15.7 warning（business）→ 门禁阻断（fail-closed 正常）
        assert result is False
        assert ci.stages[-1]["status"] == "failed"

        report_path = tmp_path / ".yuleosh" / "reports" / "misra-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["total_violations"] == 3
        tools = {v.get("tool") for v in report["violations_raw"]}
        assert tools == {"parasoft"}
        assert report["check_standard"].startswith("MISRA C:2023")
        # 原始输出保留
        assert (tmp_path / ".yuleosh" / "reports" / "misra-raw-output.txt").exists()
        # GSCR 报告：RulesetRegistry().get_default() 预存 bug 修复验证
        gscr_path = tmp_path / ".yuleosh" / "reports" / "gscr-report.json"
        assert gscr_path.exists()

    def test_commercial_scanner_zero_violations_passes(self, tmp_path):
        """商业工具输出无违规 → passed（report_file 路径）。"""
        proj = _make_project(
            tmp_path,
            "misra:\n"
            "  scanner: ldra\n"
            "  scanner_config:\n"
            "    report_file: ldra-report.txt\n",
        )
        (tmp_path / "ldra-report.txt").write_text(
            "LDRA Testbed - clean\nNo violations found\n"
        )
        ci = CIResult(1, "test")
        result = run_misra_check(proj, ci)
        assert result is True
        assert ci.stages[-1]["status"] == "passed"
        report = json.loads(
            (tmp_path / ".yuleosh" / "reports" / "misra-report.json").read_text()
        )
        assert report["total_violations"] == 0

    def test_unknown_scanner_fails_closed(self, tmp_path):
        """misra.scanner 未注册 → 阻断（fail-closed，不静默 skip）。"""
        proj = _make_project(tmp_path, "misra:\n  scanner: bogus_tool\n")
        ci = CIResult(1, "test")
        result = run_misra_check(proj, ci)
        assert result is False
        assert ci.stages[-1]["status"] in ("failed", "skipped")

    def test_configured_scanner_not_detected_fails_closed(self, tmp_path):
        """配置了商业工具但本机未安装 → 阻断（与 cppcheck 未安装同语义）。"""
        proj = _make_project(
            tmp_path,
            "misra:\n"
            "  scanner: qac\n"
            "  scanner_config:\n"
            "    cli_path: qacli-not-installed-xyz\n",
        )
        ci = CIResult(1, "test")
        result = run_misra_check(proj, ci)
        assert result is False
        assert ci.stages[-1]["status"] in ("failed", "skipped")

    def test_rule_ids_normalized_in_report(self, tmp_path):
        """报告 violations_raw 中规则 ID 已归一化（商业工具格式 → 规范键）。"""
        proj = _make_project(
            tmp_path,
            "misra:\n"
            "  scanner: parasoft\n"
            "  scanner_config:\n"
            "    report_file: parasoft-report.xml\n",
        )
        (tmp_path / "parasoft-report.xml").write_text(PARASOFT_XML)
        ci = CIResult(1, "test")
        run_misra_check(proj, ci)
        report = json.loads(
            (tmp_path / ".yuleosh" / "reports" / "misra-report.json").read_text()
        )
        rule_ids = {v.get("rule_id") for v in report["violations_raw"]}
        assert "misra-c2012-10.1" in rule_ids  # 10.1 modified → c2012 身份
        assert "misra-c2023-15.7" in rule_ids  # 15.7 unchanged → c2023
        assert "misra-c2023-2.5" in rule_ids


# ===================================================================
# GSCR RulesetRegistry 预存 bug 回归（2026-08-19）
# ===================================================================


class TestGscrRegistryFix:
    def test_ruleset_registry_class_call_still_works(self):
        """类级调用 get_default() 曾抛 TypeError（缺 self）→ 修复为实例化调用。

        该回归测试防止 review_misra 的 GSCR 翻译路径退回静默失败。
        """
        from yuleosh.ci.rulesets import RulesetRegistry

        ruleset = RulesetRegistry().get_default()
        assert ruleset is not None
        assert hasattr(ruleset, "translate_violations")
