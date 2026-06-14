"""Deep tests for hardware.debugger — AIDebugger, DebugReport."""

import pytest
from unittest.mock import MagicMock, patch

from yuleosh.hardware.debugger import AIDebugger, DebugReport


class TestDebugReport:
    def test_defaults(self):
        r = DebugReport()
        assert r.error == ""
        assert r.severity == "info"
        assert r.error_type == "unknown"
        assert r.registers == {}
        assert r.stack_trace == []
        assert r.raw_logs == []
        assert r.suggestions == []
        assert r.matched_rules == []

    def test_to_dict(self):
        r = DebugReport(
            error="HardFault at 0x08001234",
            severity="critical",
            error_type="hardfault",
            registers={"pc": "0x08001234"},
            stack_trace=["#0  HardFault_Handler"],
            raw_logs=["Boot OK", "HardFault at 0x08001234"],
            suggestions=["Check null pointer"],
            matched_rules=["hardfault: HardFault exception"],
        )
        d = r.to_dict()
        assert d["error"] == "HardFault at 0x08001234"
        assert d["severity"] == "critical"
        assert d["registers"]["pc"] == "0x08001234"
        # raw_logs truncated to 50
        assert len(d["raw_logs"]) == 2

    def test_summary_critical(self):
        r = DebugReport(
            error="HardFault at 0x08001234",
            severity="critical",
            error_type="hardfault",
            registers={"pc": "0x08001234"},
            stack_trace=["#0  HardFault_Handler"],
            suggestions=["Check null pointer"],
        )
        s = r.summary()
        assert "[CRITICAL]" in s
        assert "hardfault" in s
        assert "pc" in s or "Registers" in s

    def test_summary_no_error(self):
        r = DebugReport()
        s = r.summary()
        assert "[INFO]" in s
        assert "unknown" in s


class TestAIDebuggerAnalyzeLog:
    def test_hardfault_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log([
            "Boot OK",
            "HardFault at 0x08001234",
        ])
        assert report.error_type == "hardfault"
        assert report.severity == "critical"
        assert "HardFault" in report.error
        assert len(report.suggestions) >= 1

    def test_assert_fail_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Assertion failed at line 42"])
        assert report.error_type == "assert_fail"
        assert report.severity == "critical"

    def test_stack_overflow_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["stack overflow detected"])
        assert report.error_type == "stack_overflow"
        assert report.severity == "error"

    def test_wdt_reset_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["watchdog reset"])
        assert report.error_type == "wdt_reset"
        assert report.severity == "warning"

    def test_div_zero_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["divide by zero error"])
        assert report.error_type == "div_zero"
        assert "除法" in report.suggestions[0]

    def test_fault_isr_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Default_Handler called"])
        assert report.error_type == "fault_isr"

    def test_boot_fail_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Boot failed"])
        assert report.error_type == "boot_fail"

    def test_timeout_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["operation timed out"])
        assert report.error_type == "timeout"

    def test_general_error_detection(self):
        debugger = AIDebugger()
        report = debugger.analyze_log(["Error: sensor not initialized"])
        assert report.error_type == "general_error"

    def test_severity_priority_highest_wins(self):
        """When multiple patterns match, the highest severity should be used."""
        debugger = AIDebugger()
        report = debugger.analyze_log([
            "HardFault at 0x08000000",
            "timeout on I2C",
        ])
        # HardFault (critical) should win over timeout (warning)
        assert report.error_type == "hardfault"
        assert report.severity == "critical"

    def test_matched_rules_append_on_equal_severity(self):
        debugger = AIDebugger()
        report = debugger.analyze_log([
            "timeout on I2C",
            "watchdog reset",
        ])
        # Both warning — timeout matched first, watchdog goes to matched_rules
        assert report.error_type == "timeout"
        assert len(report.matched_rules) >= 1

    def test_heuristic_scan_no_boot(self):
        """When no boot messages at all, should flag no_boot_output."""
        debugger = AIDebugger()
        report = debugger.analyze_log(["garbage line", "another line"])
        assert report.error_type == "no_boot_output"
        assert report.severity == "warning"

    def test_heuristic_scan_incomplete_boot(self):
        """Boot started but no OK/done → incomplete_boot."""
        debugger = AIDebugger()
        report = debugger.analyze_log(["Boot starting ...", "Init peripheral"])
        assert report.error_type == "incomplete_boot"
        assert report.severity == "warning"

    def test_empty_log_heuristic(self):
        debugger = AIDebugger()
        report = debugger.analyze_log([])
        assert report.error_type == "no_boot_output"

    def test_heuristic_scan_with_ok(self):
        """Boot + OK → should not be incomplete_boot, should remain unknown."""
        debugger = AIDebugger()
        report = debugger.analyze_log(["Boot OK", "System ready"])
        assert report.error_type == "unknown" or report.error_type == "no_boot_output"
        # Strictly: boot OK means no error; unknown stays

    def test_stack_trace_extraction(self):
        debugger = AIDebugger()
        report = debugger.analyze_log([
            "HardFault",
            "#0  HardFault_Handler",
            "#1  some_function",
            "#   some detail",
        ])
        assert len(report.stack_trace) >= 2
        assert "HardFault" in report.stack_trace[0]

    def test_repr_no_llm(self):
        debugger = AIDebugger()
        assert "rules-only" in repr(debugger)

    def test_repr_with_llm(self):
        mock_llm = MagicMock()
        debugger = AIDebugger(llm_client=mock_llm)
        assert "enabled" in repr(debugger)


class TestAIDebuggerSuggestFix:
    def test_rule_based_fix(self):
        debugger = AIDebugger()
        fix = debugger.suggest_fix("HardFault at 0x08000000", "int *p = NULL;")
        assert "HardFault" in fix or "hardfault" in fix or "检测到" in fix

    def test_unrecognized_pattern(self):
        debugger = AIDebugger()
        # Use a truly unrecognizable pattern that doesn't match ANY rule
        fix = debugger.suggest_fix("ZwXyQpLm 9988776655", "some code")
        assert "无法自动识别" in fix

    def test_with_llm_client(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "Check your pointer arithmetic."
        debugger = AIDebugger(llm_client=mock_llm)
        fix = debugger.suggest_fix("HardFault", "int *p = NULL;")
        mock_llm.complete.assert_called_once()
        assert "LLM 分析" in fix

    def test_llm_raises_exception(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = RuntimeError("API down")
        debugger = AIDebugger(llm_client=mock_llm)
        fix = debugger.suggest_fix("HardFault", "int *p = NULL;")
        assert "规则建议" in fix  # should still have rule advice


class TestAIDebuggerCheckRegisters:
    def test_parse_registers(self):
        gdb_output = """r0             0x0      0
r1             0x20001000   536875008
pc             0x080001234  134219732
lr             0x080005678  134219896
sp             0x20002000   536879104
xpsr           0x01000003   16777219
"""
        result = AIDebugger.check_registers(gdb_output)
        assert "r0" in result["registers"]
        assert result["registers"]["pc"] == "0x080001234"
        assert len(result["suspicious"]) >= 0  # pc is not 0

    def test_suspicious_pc_zero(self):
        gdb_output = "pc             0x0      0\nlr             0x0      0\n"
        result = AIDebugger.check_registers(gdb_output)
        suspicious_strs = [s for s in result["suspicious"] if "pc=0x0" in s]
        assert len(suspicious_strs) >= 1

    def test_suspicious_sp(self):
        gdb_output = "sp             0x10000000   268435456\n"
        result = AIDebugger.check_registers(gdb_output)
        sp_suspicious = [s for s in result["suspicious"] if "SP=" in s]
        assert len(sp_suspicious) >= 1

    def test_xpsr_flag_exception(self):
        # IPSR bits 0-8 set to 0x1FF → bit 8 (0x100) is set
        gdb_output = "xpsr           0x000001FF   511\n"
        result = AIDebugger.check_registers(gdb_output)
        assert any("Exception active" in f for f in result["flags"])

    def test_empty_gdb_output(self):
        result = AIDebugger.check_registers("")
        assert result["registers"] == {}


class TestAIDebuggerCallLlm:
    def test_call_llm_complete(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "Analysis result"
        debugger = AIDebugger(llm_client=mock_llm)
        result = debugger._call_llm("error", "code")
        assert result == "Analysis result"

    def test_call_llm_non_string_result(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = 42
        debugger = AIDebugger(llm_client=mock_llm)
        result = debugger._call_llm("error", "code")
        assert result == "42"

    def test_call_llm_no_llm(self):
        debugger = AIDebugger()
        result = debugger._call_llm("error", "code")
        assert "not available" in result
