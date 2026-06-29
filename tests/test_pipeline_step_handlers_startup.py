#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_startup — startup code review."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_startup import (
    step_review_startup,
    _find_startup_files,
    _check_reset_handler,
    _check_stack_pointer_init,
    _check_bss_zeroing,
    _check_data_copy,
    _check_clock_config,
    _check_main_call,
    _check_fpu_enable,
    _check_system_init_timing,
    _check_default_handler_weak,
    _check_cpp_constructors,
    _check_interrupt_state,
    _static_startup_review,
    _build_startup_review_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with a temp project structure."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n## Requirements\nSTP-001: shall initialize memory\n")
    session = PipelineSession(
        name="test-startup",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-startup"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    session.token_usage_total = 0
    session.token_usage_steps = []
    return session


def _fake_llm_result(content="# Startup Review\n\n## Findings\n\nAll OK.",
                      total_tokens=250,
                      prompt_tokens=120) -> dict:
    return {
        "content": content,
        "usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": total_tokens - prompt_tokens,
        },
        "model": "test-model",
    }


# =============================================================================
# Unit tests — helper functions
# =============================================================================

class TestFindStartupFiles:
    """Tests for _find_startup_files — startup file discovery."""

    def test_finds_all_patterns(self, tmp_path):
        """GIVEN a project with startup and system files
           WHEN _find_startup_files runs
           THEN it returns all matching files."""
        (tmp_path / "startup_stm32f407.s").write_text("; Startup\n")
        (tmp_path / "system_stm32f4xx.c").write_text("// System init\n")
        (tmp_path / "crt0.S").write_text("; CRT\n")
        (tmp_path / "regular.c").write_text("// Not startup\n")

        result = _find_startup_files(tmp_path)
        names = sorted(str(p.name) for p in result)
        assert "startup_stm32f407.s" in names
        assert "system_stm32f4xx.c" in names
        assert "crt0.S" in names
        assert "regular.c" not in names

    def test_empty_project(self, tmp_path):
        """GIVEN an empty project
           WHEN _find_startup_files runs
           THEN it returns an empty list."""
        result = _find_startup_files(tmp_path)
        assert result == []

    def test_deduplicates(self, tmp_path):
        """GIVEN the same file matched by multiple patterns
           WHEN _find_startup_files runs
           THEN each file appears only once."""
        (tmp_path / "system_stm32f4xx.c").write_text("// code\n")
        result = _find_startup_files(tmp_path)
        assert len(result) == 1


class TestCheckResetHandler:
    """Tests for _check_reset_handler — Reset_Handler detection."""

    def test_reset_handler_present(self, tmp_path):
        """GIVEN content with Reset_Handler definition
           WHEN _check_reset_handler runs
           THEN it returns an 'info' finding."""
        content = "Reset_Handler PROC\n"
        f = tmp_path / "startup.s"
        findings = _check_reset_handler(content, f)
        assert len(findings) == 1
        assert findings[0]["severity"] == "info"
        assert findings[0]["category"] == "reset_handler"

    def test_reset_handler_missing(self, tmp_path):
        """GIVEN content without Reset_Handler
           WHEN _check_reset_handler runs
           THEN it returns a 'critical' finding."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_reset_handler(content, f)
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"


class TestCheckStackPointerInit:
    """Tests for _check_stack_pointer_init — SP initialization check."""

    def test_initial_sp_found(self, tmp_path):
        """GIVEN content with __initial_sp reference
           WHEN _check_stack_pointer_init runs
           THEN it returns an 'info' finding."""
        content = ".word __initial_sp\n"
        f = tmp_path / "startup.s"
        findings = _check_stack_pointer_init(content, f)
        assert findings[0]["severity"] == "info"

    def test_no_stack_init(self, tmp_path):
        """GIVEN content without initial_sp
           WHEN _check_stack_pointer_init runs
           THEN it returns a 'major' finding."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_stack_pointer_init(content, f)
        assert findings[0]["severity"] == "major"

    def test_ldr_sp_pattern(self, tmp_path):
        """GIVEN content with LDR SP instruction
           WHEN _check_stack_pointer_init runs
           THEN it returns 'info' finding."""
        content = "LDR SP, =__stack_top\n"
        f = tmp_path / "startup.s"
        findings = _check_stack_pointer_init(content, f)
        assert findings[0]["severity"] == "info"


class TestCheckBssZeroing:
    """Tests for _check_bss_zeroing — BSS clear detection."""

    def test_bss_start_found(self, tmp_path):
        """GIVEN content with __bss_start reference
           WHEN _check_bss_zeroing runs
           THEN it returns 'info' finding."""
        content = "__bss_start:\n"
        f = tmp_path / "startup.s"
        findings = _check_bss_zeroing(content, f)
        assert findings[0]["severity"] == "info"

    def test_bss_missing(self, tmp_path):
        """GIVEN content without BSS patterns
           WHEN _check_bss_zeroing runs
           THEN it returns 'major' finding."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_bss_zeroing(content, f)
        assert findings[0]["severity"] == "major"

    def test_sbss_ebss_pattern(self, tmp_path):
        """GIVEN content with sbss/ebss references
           WHEN _check_bss_zeroing runs
           THEN it returns 'info' finding."""
        content = "sbss = .;\n"
        f = tmp_path / "startup.s"
        findings = _check_bss_zeroing(content, f)
        assert findings[0]["severity"] == "info"


class TestCheckDataCopy:
    """Tests for _check_data_copy — .data copy detection."""

    def test_data_start_found(self, tmp_path):
        """GIVEN content with __data_start reference
           WHEN _check_data_copy runs
           THEN it returns 'info' finding."""
        content = "__data_start = .;\n"
        f = tmp_path / "startup.s"
        findings = _check_data_copy(content, f)
        assert findings[0]["severity"] == "info"

    def test_data_missing(self, tmp_path):
        """GIVEN content without .data copy patterns
           WHEN _check_data_copy runs
           THEN it returns 'major' finding."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_data_copy(content, f)
        assert findings[0]["severity"] == "major"

    def test_etext_pattern(self, tmp_path):
        """GIVEN content with __etext reference
           WHEN _check_data_copy runs
           THEN it returns 'info' finding."""
        content = "__etext = .;\n"
        f = tmp_path / "startup.s"
        findings = _check_data_copy(content, f)
        assert findings[0]["severity"] == "info"


class TestCheckClockConfig:
    """Tests for _check_clock_config — clock/PLL config detection."""

    def test_clock_config_found(self, tmp_path):
        """GIVEN content with SystemCoreClock or SystemInit
           WHEN _check_clock_config runs
           THEN it returns 'info' finding."""
        content = "SystemCoreClock = 168000000;\n"
        f = tmp_path / "system_stm32f4xx.c"
        findings = _check_clock_config(content, f)
        assert findings[0]["severity"] == "info"

    def test_no_clock_config(self, tmp_path):
        """GIVEN content without clock config
           WHEN _check_clock_config runs
           THEN it returns 'info' with no-config message (non-critical)."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_clock_config(content, f)
        assert findings[0]["severity"] == "info"
        assert "No clock config" in findings[0]["message"]


class TestCheckMainCall:
    """Tests for _check_main_call — main() invocation detection."""

    def test_bl_main_found(self, tmp_path):
        """GIVEN content with 'bl main' instruction
           WHEN _check_main_call runs
           THEN it returns 'info' finding."""
        content = "bl main\n"
        f = tmp_path / "startup.s"
        findings = _check_main_call(content, f)
        assert findings[0]["severity"] == "info"

    def test_main_not_found(self, tmp_path):
        """GIVEN content without main call
           WHEN _check_main_call runs
           THEN it returns 'minor' finding."""
        content = "int setup(void) { return 0; }\n"
        f = tmp_path / "setup.c"
        findings = _check_main_call(content, f)
        assert findings[0]["severity"] == "minor"

    def test_main_function_reference(self, tmp_path):
        """GIVEN content with 'main(' in C code
           WHEN _check_main_call runs
           THEN it returns 'info' finding."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_main_call(content, f)
        assert findings[0]["severity"] == "info"


class TestCheckFpuEnable:
    """Tests for _check_fpu_enable — FPU configuration check."""

    def test_cpacr_write_detected(self, tmp_path):
        """GIVEN content with CPACR write for FPU
           WHEN _check_fpu_enable runs
           THEN it returns 'info' with FPU enabled."""
        content = "SCB->CPACR = 0xF00000;\n"
        f = tmp_path / "system_stm32f4xx.c"
        findings = _check_fpu_enable(content, f)
        assert len(findings) >= 1
        enabled = [f for f in findings if "FPU enabled" in f.get("message", "")]
        assert len(enabled) >= 1

    def test_fpu_capable_core_no_fpu(self, tmp_path):
        """GIVEN content referencing Cortex-M4 but no CPACR
           WHEN _check_fpu_enable runs
           THEN it returns a 'critical' finding."""
        content = "// Cortex-M4 based MCU\n"
        f = tmp_path / "startup.c"
        findings = _check_fpu_enable(content, f)
        criticals = [f for f in findings if f["severity"] == "critical"]
        assert len(criticals) >= 1

    def test_no_fpu_capable_core(self, tmp_path):
        """GIVEN content with no FPU-capable core reference
           WHEN _check_fpu_enable runs
           THEN it returns 'info' with FPU check skipped."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_fpu_enable(content, f)
        assert findings[0]["severity"] == "info"
        assert "FPU check skipped" in findings[0]["message"]


class TestCheckSystemInitTiming:
    """Tests for _check_system_init_timing — SystemInit before main()."""

    def test_system_init_before_main(self, tmp_path):
        """GIVEN content with SystemInit (after BSS) before main()
           WHEN _check_system_init_timing runs
           THEN it returns 'info' with correct timing."""
        content = (
            "__bss_start = .;\n"
            "SystemInit();\n"
            "bl main\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_system_init_timing(content, f)
        infos = [f for f in findings if f["severity"] == "info"]
        assert len(infos) >= 1

    def test_no_system_init(self, tmp_path):
        """GIVEN content with no SystemInit
           WHEN _check_system_init_timing runs
           THEN it returns 'info' about separate file."""
        content = "bl main\n"
        f = tmp_path / "startup.s"
        findings = _check_system_init_timing(content, f)
        assert findings[0]["severity"] == "info"

    def test_system_init_after_main(self, tmp_path):
        """GIVEN content where SystemInit appears after main()
           WHEN _check_system_init_timing runs
           THEN it returns 'minor' finding about ordering."""
        content = (
            "bl main\n"
            "SystemInit:\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_system_init_timing(content, f)
        minors = [f for f in findings if f["severity"] == "minor"]
        assert len(minors) >= 1


class TestCheckDefaultHandlerWeak:
    """Tests for _check_default_handler_weak — WEAK/ALIAS detection."""

    def test_weak_attribute_found(self, tmp_path):
        """GIVEN content with Default_Handler and .weak
           WHEN _check_default_handler_weak runs
           THEN it returns 'info' with handler count."""
        content = (
            ".weak Default_Handler\n"
            ".type Default_Handler, %function\n"
            "Default_Handler:\n"
            "    b .\n"
            ".word USART1_IRQHandler\n"
            ".word TIM2_IRQHandler\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_default_handler_weak(content, f)
        infos = [f for f in findings if f["severity"] == "info"]
        assert len(infos) >= 1

    def test_no_default_handler(self, tmp_path):
        """GIVEN content without Default_Handler
           WHEN _check_default_handler_weak runs
           THEN it returns 'info'."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_default_handler_weak(content, f)
        assert findings[0]["severity"] == "info"

    def test_default_handler_without_weak(self, tmp_path):
        """GIVEN content with Default_Handler but no WEAK
           WHEN _check_default_handler_weak runs
           THEN it returns 'minor' finding."""
        content = (
            "Default_Handler:\n"
            "    b .\n"
            ".word USART1_IRQHandler\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_default_handler_weak(content, f)
        minors = [f for f in findings if f["severity"] == "minor"]
        assert len(minors) >= 1


class TestCheckCppConstructors:
    """Tests for _check_cpp_constructors — C++ static constructor support."""

    def test_init_array_with_loop(self, tmp_path):
        """GIVEN content with .init_array section and iteration loop
           WHEN _check_cpp_constructors runs
           THEN it returns 'info' finding."""
        content = (
            ".init_array :\n"
            "{\n"
            "    __init_array_start = .;\n"
            "    KEEP(*(SORT(.init_array.*)))\n"
            "    __init_array_end = .;\n"
            "}\n"
            "bl __libc_init_array\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_cpp_constructors(content, f)
        infos = [f for f in findings if f["severity"] == "info"]
        assert len(infos) >= 1

    def test_init_array_without_loop(self, tmp_path):
        """GIVEN content with .init_array but no iteration loop
           WHEN _check_cpp_constructors runs
           THEN it returns 'critical' finding."""
        content = (
            ".init_array :\n"
            "{\n"
            "    KEEP(*(SORT(.init_array.*)))\n"
            "}\n"
        )
        f = tmp_path / "startup.s"
        findings = _check_cpp_constructors(content, f)
        criticals = [f for f in findings if f["severity"] == "critical"]
        assert len(criticals) >= 1

    def test_no_cpp_references(self, tmp_path):
        """GIVEN content without C++ constructor references
           WHEN _check_cpp_constructors runs
           THEN it returns 'info' about C-only firmware."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_cpp_constructors(content, f)
        assert findings[0]["severity"] == "info"
        assert "C-only firmware" in findings[0]["message"]


class TestCheckInterruptState:
    """Tests for _check_interrupt_state — interrupt enable/disable in startup."""

    def test_cpsid_found(self, tmp_path):
        """GIVEN content with CPSID I (disable interrupts)
           WHEN _check_interrupt_state runs
           THEN it returns 'info' with best-practice message."""
        content = "CPSID I\n"
        f = tmp_path / "startup.s"
        findings = _check_interrupt_state(content, f)
        assert len(findings) >= 1
        assert "Interrupts disabled" in findings[0]["message"]

    def test_cpsie_found(self, tmp_path):
        """GIVEN content with CPSIE I (enable interrupts early)
           WHEN _check_interrupt_state runs
           THEN it returns 'info' with intentional message."""
        content = "CPSIE I\n"
        f = tmp_path / "startup.s"
        findings = _check_interrupt_state(content, f)
        assert len(findings) >= 1
        assert "Interrupts enabled" in findings[0]["message"]

    def test_no_interrupt_instructions(self, tmp_path):
        """GIVEN content without CPSID/CPSIE
           WHEN _check_interrupt_state runs
           THEN it returns 'info' about default state."""
        content = "int main(void) { return 0; }\n"
        f = tmp_path / "main.c"
        findings = _check_interrupt_state(content, f)
        assert len(findings) >= 1
        assert "default" in findings[0]["message"]


class TestStaticStartupReview:
    """Tests for _static_startup_review — orchestrator of all startup checks."""

    def test_no_startup_files(self, tmp_path):
        """GIVEN an empty project
           WHEN _static_startup_review runs
           THEN it returns a 'major' discovery finding."""
        findings = _static_startup_review(tmp_path)
        majors = [f for f in findings if f["severity"] == "major"]
        assert len(majors) >= 1
        assert any("No startup file" in f["message"] for f in findings)

    def test_full_startup_file(self, tmp_path):
        """GIVEN a complete startup file with all patterns
           WHEN _static_startup_review runs
           THEN it returns findings from multiple check modules."""
        (tmp_path / "startup_stm32f407.s").write_text(
            '.word __initial_sp\n'
            '.word Reset_Handler\n'
            '.weak Default_Handler\n'
            '.type Default_Handler, %function\n'
            'Default_Handler:\n'
            '    b .\n'
            'Reset_Handler:\n'
            '    CPSID I\n'
            '    ldr r0, =__bss_start\n'
            '    ldr r1, =__bss_end\n'
            '    mov r2, #0\n'
            '    bl main\n'
        )
        findings = _static_startup_review(tmp_path)
        categories = set(f["category"] for f in findings)
        assert "reset_handler" in categories
        assert "stack_init" in categories
        assert "bss_init" in categories
        assert "interrupt_state" in categories
        assert "main_call" in categories

    def test_clock_config_separate_file(self, tmp_path):
        """GIVEN clock config in a separate system_*.c file
           WHEN _static_startup_review runs
           THEN clock config is detected."""
        (tmp_path / "system_stm32f4xx.c").write_text(
            'void SystemInit(void) {\n'
            '    SystemCoreClock = 168000000;\n'
            '}\n'
        )
        findings = _static_startup_review(tmp_path)
        clock_findings = [f for f in findings if f["category"] == "clock_config"]
        assert len(clock_findings) >= 1

    def test_io_error_skips_file(self, tmp_path):
        """GIVEN an unreadable startup file
           WHEN _static_startup_review runs
           THEN it returns findings from other checks ignoring the unreadable file."""
        f = tmp_path / "startup_stm32f407.s"
        f.write_text("; startup\n")
        # Remove read permission
        f.chmod(0o000)
        try:
            findings = _static_startup_review(tmp_path)
            # The unreadable file won't be found by glob if the directory is readable
            # but the file is unreadable. The code will try to read it and catch OSError.
            # But glob may fail to read the file. Let's just verify we don't crash.
            assert isinstance(findings, list)
        finally:
            f.chmod(0o644)


class TestBuildStartupReviewPrompt:
    """Tests for _build_startup_review_prompt — LLM prompt construction."""

    def test_returns_prompts(self, tmp_path):
        """GIVEN startup file contents
           WHEN _build_startup_review_prompt runs
           THEN it returns system_prompt and user_prompt strings."""
        contents = {"startup.s": ".word __initial_sp\n.word Reset_Handler\n"}
        system_prompt, user_prompt = _build_startup_review_prompt(contents)
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 50
        assert isinstance(user_prompt, str)
        assert "startup.s" in user_prompt


# =============================================================================
# Integration tests — step_review_startup
# =============================================================================

class TestStepReviewStartup:
    """Test suite for step_review_startup — the pipeline step handler."""

    # ── Happy path ──────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_happy_path(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN a valid session with startup files and working LLM
           WHEN step_review_startup runs
           THEN it writes a JSON report and returns the output path."""
        mock_environ.get.return_value = str(tmp_path)
        (tmp_path / "startup_stm32f407.s").write_text(
            '.word __initial_sp\n'
            '.word Reset_Handler\n'
            'Reset_Handler:\n'
            '    CPSID I\n'
            '    bl main\n'
        )
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_startup(mock_session)

        out_path = Path(result)
        assert out_path.exists()
        assert out_path.name == "startup-review.json"
        report = json.loads(out_path.read_text())
        assert report["step"] == "review-startup"
        assert report["reviewer"] == "小克"
        assert "status" in report
        assert "static_findings" in report
        assert "llm_review" in report

    # ── LLM call fails (non-fatal) ──────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_llm_failure_is_non_fatal(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_startup runs
           THEN it still succeeds with llm_review as error message."""
        mock_environ.get.return_value = str(tmp_path)
        (tmp_path / "startup_stm32f407.s").write_text(
            '.word __initial_sp\n'
            '.word Reset_Handler\n'
        )
        mock_call_llm.side_effect = RuntimeError("LLM unavailable")

        result = step_review_startup(mock_session)
        report = json.loads(Path(result).read_text())
        assert "(LLM-powered review unavailable)" in report["llm_review"]

    # ── Token usage tracked ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_token_usage_tracked(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN LLM returns usage info
           WHEN step_review_startup completes
           THEN session token totals are updated."""
        mock_environ.get.return_value = str(tmp_path)
        (tmp_path / "startup_stm32f407.s").write_text(
            '.word __initial_sp\n'
            '.word Reset_Handler\n'
        )
        mock_call_llm.return_value = _fake_llm_result(total_tokens=280)

        step_review_startup(mock_session)

        assert mock_session.token_usage_total > 0
        steps = [s for s in mock_session.token_usage_steps if s["step"] == "review-startup"]
        assert len(steps) == 1
        assert steps[0]["usage"]["total_tokens"] == 280

    # ── Critical finding → failed status ────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_critical_finding_triggers_failed(self, mock_environ, mock_call_llm,
                                               mock_session, tmp_path):
        """GIVEN a finding with 'critical' severity (e.g. FPU on Cortex-M4)
           WHEN step_review_startup runs
           THEN overall status is 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        # Trigger FPU critical: Cortex-M4 ref but no CPACR
        (tmp_path / "startup_stm32f4xx.c").write_text(
            '// Cortex-M4 based MCU\n'
            'int main(void) { return 0; }\n'
        )
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_startup(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] == "failed"

    # ── Output write error ──────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_output_write_error_raises(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN output file cannot be written
           WHEN step_review_startup runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.return_value = _fake_llm_result()
        import shutil
        shutil.rmtree(mock_session.session_dir)
        mock_session.session_dir.write_text("not_a_dir")

        with pytest.raises(PipelineStepError, match="Cannot write"):
            step_review_startup(mock_session)

    # ── No startup files ────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_startup._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_startup.os.environ")
    def test_no_startup_files(self, mock_environ, mock_call_llm, mock_session, tmp_path):
        """GIVEN a project with no startup files
           WHEN step_review_startup runs
           THEN it succeeds with discovery finding and no LLM review."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.return_value = _fake_llm_result()

        result = step_review_startup(mock_session)
        report = json.loads(Path(result).read_text())
        assert "static_findings" in report
        assert report["llm_review"] == ""
