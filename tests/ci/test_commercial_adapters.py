# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""商业扫描器适配器（Parasoft / QAC / LDRA / MCP）单测（2026-08-19 P2）。

验收标准 #3：真实商业工具输出样例能被 parse + normalize 成统一 violations。
样例格式在各适配器模块 docstring 中说明（代表性输出，供客户接入时对齐）。
"""


from yuleosh.ci.config import MisraConfig
from yuleosh.ci.scanners.ldra_adapter import LdraScannerAdapter
from yuleosh.ci.scanners.mcp_adapter import McpScannerAdapter
from yuleosh.ci.scanners.parasoft_adapter import ParasoftScannerAdapter
from yuleosh.ci.scanners.qac_adapter import QacScannerAdapter

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

QAC_TEXT = """\
QAC 10.4.1 - MISRA C:2023 analysis
src/speed_control.c:33: (Required) Rule 10.1: Operands shall not be of inappropriate essential type
src/speed_control.c:47: (Advisory) Rule 2.5: A macro shall not be defined with the same name as a keyword
src/speed_control.h:12: (Required) Dir 4.1: Run-time failures shall be minimized
"""

LDRA_TEXT = """\
LDRA Testbed - MISRA C:2023 compliance report
RULE 10.1, src/steering.c, line 42, Required: Operands shall not be of inappropriate essential type
RULE 15.7, src/steering.c, line 87, Required: All if...else if constructs shall be terminated with an else clause
DIR 4.1, src/steering.c, line 12, Required: Run-time failures shall be minimized
"""

CPPCHECK_STYLE = """\
src/engine.c:10:1: style: This code is unreachable. [misra-c2012-2.2]
"""


# ===================================================================
# Parasoft
# ===================================================================


class TestParasoftAdapter:
    def test_parse_and_normalize(self):
        adapter = ParasoftScannerAdapter()
        violations = adapter.normalize(adapter.parse(PARASOFT_XML))
        assert len(violations) == 3
        assert all(v.tool == "parasoft" for v in violations)
        by_rule = {v.rule_id: v for v in violations}
        # C:2012 工具输出诚实映射：10.1 modified → c2012；15.7/2.5 → c2023
        assert "misra-c2012-10.1" in by_rule
        assert "misra-c2023-15.7" in by_rule
        assert "misra-c2023-2.5" in by_rule
        assert by_rule["misra-c2012-10.1"].severity == "error"
        assert by_rule["misra-c2023-2.5"].severity == "style"
        assert by_rule["misra-c2012-10.1"].file == "src/brake_control.c"
        assert by_rule["misra-c2012-10.1"].line == 42
        assert by_rule["misra-c2012-10.1"].rule_year == "2012"

    def test_run_reads_report_file(self, tmp_path):
        rp = tmp_path / "parasoft-report.xml"
        rp.write_text(PARASOFT_XML)
        cfg = MisraConfig(
            scanner="parasoft",
            scanner_config={"report_file": "parasoft-report.xml"},
        )
        adapter = ParasoftScannerAdapter()
        assert adapter.detect(str(tmp_path), cfg) is True
        result = adapter.run(str(tmp_path), config=cfg, target_files=["src/brake_control.c"])
        assert result.ok
        assert "MISRA.C.2012.10.1" in result.raw_output

    def test_detect_false_without_config(self, tmp_path):
        assert ParasoftScannerAdapter().detect(str(tmp_path)) is False

    def test_detect_false_when_report_missing(self, tmp_path):
        cfg = MisraConfig(scanner_config={"report_file": "missing.xml"})
        assert ParasoftScannerAdapter().detect(str(tmp_path), cfg) is False

    def test_parse_invalid_xml_returns_empty(self):
        assert ParasoftScannerAdapter().parse("<report><unclosed>") == []

    def test_run_missing_report_file_errors(self, tmp_path):
        cfg = MisraConfig(scanner_config={"report_file": "missing.xml"})
        result = ParasoftScannerAdapter().run(str(tmp_path), config=cfg)
        assert not result.ok
        assert "report file not found" in result.error


# ===================================================================
# QAC
# ===================================================================


class TestQacAdapter:
    def test_parse_and_normalize(self):
        adapter = QacScannerAdapter()
        violations = adapter.normalize(adapter.parse(QAC_TEXT))
        assert len(violations) == 3
        assert all(v.tool == "qac" for v in violations)
        by_rule = {v.rule_id: v for v in violations}
        assert "misra-c2023-10.1" in by_rule
        assert "misra-c2023-2.5" in by_rule
        assert "misra-c2023-dir-4.1" in by_rule
        assert by_rule["misra-c2023-10.1"].severity == "required"
        assert by_rule["misra-c2023-2.5"].severity == "advisory"
        assert by_rule["misra-c2023-10.1"].file == "src/speed_control.c"
        assert by_rule["misra-c2023-10.1"].line == 33

    def test_run_reads_report_file(self, tmp_path):
        rp = tmp_path / "qac-report.txt"
        rp.write_text(QAC_TEXT)
        cfg = MisraConfig(scanner_config={"report_file": "qac-report.txt"})
        adapter = QacScannerAdapter()
        assert adapter.detect(str(tmp_path), cfg) is True
        result = adapter.run(str(tmp_path), config=cfg)
        assert result.ok
        assert "Rule 10.1" in result.raw_output

    def test_detect_false_without_config(self, tmp_path):
        assert QacScannerAdapter().detect(str(tmp_path)) is False

    def test_parse_non_matching_lines_ignored(self):
        assert QacScannerAdapter().parse("header line\nno violation here\n") == []


# ===================================================================
# LDRA
# ===================================================================


class TestLdraAdapter:
    def test_parse_and_normalize(self):
        adapter = LdraScannerAdapter()
        violations = adapter.normalize(adapter.parse(LDRA_TEXT))
        assert len(violations) == 3
        assert all(v.tool == "ldra" for v in violations)
        by_rule = {v.rule_id: v for v in violations}
        assert "misra-c2023-10.1" in by_rule
        assert "misra-c2023-15.7" in by_rule
        assert "misra-c2023-dir-4.1" in by_rule
        assert by_rule["misra-c2023-10.1"].severity == "required"
        assert by_rule["misra-c2023-dir-4.1"].file == "src/steering.c"
        assert by_rule["misra-c2023-dir-4.1"].line == 12

    def test_run_reads_report_file(self, tmp_path):
        rp = tmp_path / "ldra-report.txt"
        rp.write_text(LDRA_TEXT)
        cfg = MisraConfig(scanner_config={"report_file": "ldra-report.txt"})
        adapter = LdraScannerAdapter()
        assert adapter.detect(str(tmp_path), cfg) is True
        result = adapter.run(str(tmp_path), config=cfg)
        assert result.ok
        assert "RULE 10.1" in result.raw_output

    def test_detect_false_without_config(self, tmp_path):
        assert LdraScannerAdapter().detect(str(tmp_path)) is False


# ===================================================================
# MCP（P3 最小实现）
# ===================================================================


class TestMcpAdapter:
    def test_parse_cppcheck_style(self):
        adapter = McpScannerAdapter()
        violations = adapter.normalize(adapter.parse(CPPCHECK_STYLE))
        assert len(violations) == 1
        assert violations[0].tool == "mcp"
        assert violations[0].rule_id == "misra-c2012-2.2"

    def test_parse_qac_style(self):
        adapter = McpScannerAdapter()
        violations = adapter.normalize(adapter.parse(QAC_TEXT))
        assert len(violations) == 3
        assert all(v.tool == "mcp" for v in violations)

    def test_parse_empty(self):
        assert McpScannerAdapter().parse("") == []

    def test_run_requires_config(self, tmp_path):
        result = McpScannerAdapter().run(str(tmp_path), config=None)
        assert not result.ok
        assert "cli_path or output_file" in result.error

    def test_run_reads_output_file(self, tmp_path):
        (tmp_path / "mcp-output.txt").write_text(CPPCHECK_STYLE)
        cfg = MisraConfig(scanner_config={"output_file": "mcp-output.txt"})
        adapter = McpScannerAdapter()
        assert adapter.detect(str(tmp_path), cfg) is True
        result = adapter.run(str(tmp_path), config=cfg)
        assert result.ok
        assert "misra-c2012-2.2" in result.raw_output

    def test_detect_false_without_config(self, tmp_path):
        assert McpScannerAdapter().detect(str(tmp_path)) is False
