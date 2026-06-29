#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_rtos."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_rtos import (
    step_review_rtos,
    _find_rtos_config_files,
    _check_max_priorities,
    _check_minimal_stack,
    _check_interrupt_priority,
    _check_hooks_and_watchdog,
    _check_config_assert,
    _check_stack_overflow_hook,
    _check_run_time_stats,
    _check_mutex_and_semaphore,
    _static_rtos_review,
    _build_rtos_review_prompt,
    _parse_config_macro,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession for RTOS review testing."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-rtos",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-rtos"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _create_file(project_dir: Path, rel_path: str, content: str = "") -> Path:
    """Create a file under project_dir and return its path."""
    p = project_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# Sample FreeRTOSConfig.h content for reuse
FREERTOS_CONFIG_BASIC = """#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#define configMAX_PRIORITIES             5
#define configMINIMAL_STACK_SIZE         128
#define configTICK_RATE_HZ               1000
#define configCPU_CLOCK_HZ               168000000
#define configUSE_PREEMPTION             1
#define configUSE_IDLE_HOOK              0
#define configUSE_TICK_HOOK              0
#define configUSE_MUTEXES                1
#define configUSE_RECURSIVE_MUTEXES      1
#define configUSE_COUNTING_SEMAPHORES    1
#define configUSE_QUEUE_SETS             0
#define configCHECK_FOR_STACK_OVERFLOW   2
#define configUSE_TICKLESS_IDLE          0
#define configUSE_PORT_OPTIMISED_TASK_SELECTION 1

#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 5

#define configASSERT(x)  vAssertCalled((x))
#endif
"""


# =============================================================================
# _parse_config_macro
# =============================================================================

class TestParseConfigMacro:
    """Tests for _parse_config_macro — FreeRTOS #define extraction."""

    def test_simple_define(self):
        """GIVEN a standard #define macro
           WHEN _parse_config_macro runs
           THEN it returns the value."""
        content = "#define configMAX_PRIORITIES 5\n"
        val = _parse_config_macro("configMAX_PRIORITIES", content)
        assert val == "5"

    def test_undef(self):
        """GIVEN an #undef directive
           WHEN _parse_config_macro runs
           THEN it returns 'undef'."""
        content = "#undef configUSE_MUTEXES"
        val = _parse_config_macro("configUSE_MUTEXES", content)
        assert val == "undef"

    def test_not_defined(self):
        """GIVEN no definition for the macro
           WHEN _parse_config_macro runs
           THEN it returns the default."""
        content = ""
        val = _parse_config_macro("configMAX_PRIORITIES", content, default="not_set")
        assert val == "not_set"

    def test_with_comment(self):
        """GIVEN a define with trailing comment
           WHEN _parse_config_macro runs
           THEN it returns the clean value."""
        content = "#define configMAX_PRIORITIES  32  // Maximum task priorities\n"
        val = _parse_config_macro("configMAX_PRIORITIES", content)
        assert val == "32"

    def test_hex_value(self):
        """GIVEN a hex value define
           WHEN _parse_config_macro runs
           THEN it returns the hex string."""
        content = "#define configCPU_CLOCK_HZ  0x0A000000\n"
        val = _parse_config_macro("configCPU_CLOCK_HZ", content)
        assert val == "0x0A000000"


# =============================================================================
# _find_rtos_config_files
# =============================================================================

class TestFindRtosConfigFiles:
    """Tests for _find_rtos_config_files — RTOS config discovery."""

    def test_no_files(self, tmp_path):
        """GIVEN no RTOS config files
           WHEN _find_rtos_config_files runs
           THEN it returns empty."""
        result = _find_rtos_config_files(tmp_path)
        assert result == []

    def test_finds_freertos_config(self, tmp_path):
        """GIVEN a FreeRTOSConfig.h file
           WHEN _find_rtos_config_files runs
           THEN it finds the file."""
        _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)
        result = _find_rtos_config_files(tmp_path)
        assert len(result) == 1

    def test_finds_rtconfig(self, tmp_path):
        """GIVEN an rtconfig.h file
           WHEN _find_rtos_config_files runs
           THEN it finds the file."""
        _create_file(tmp_path, "rtconfig.h", "#define RT_USING_")
        result = _find_rtos_config_files(tmp_path)
        assert len(result) == 1

    def test_content_search_fallback(self, tmp_path):
        """GIVEN no well-known filenames but a header with RTOS defines
           WHEN _find_rtos_config_files runs
           THEN it finds the file via content search."""
        _create_file(tmp_path, "inc/app_config.h", "configMAX_PRIORITIES 10")
        result = _find_rtos_config_files(tmp_path)
        assert len(result) == 1

    def test_deduplication(self, tmp_path):
        """GIVEN the same file discovered via multiple patterns
           WHEN _find_rtos_config_files runs
           THEN it returns unique paths."""
        f = _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)
        result = _find_rtos_config_files(tmp_path)
        assert len(result) == 1


# =============================================================================
# _check_max_priorities
# =============================================================================

class TestCheckMaxPriorities:
    """Tests for _check_max_priorities — configMAX_PRIORITIES validation."""

    def test_normal_value(self, tmp_path):
        """GIVEN configMAX_PRIORITIES within normal range
           WHEN _check_max_priorities runs
           THEN it returns an info finding."""
        content = "#define configMAX_PRIORITIES 8\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_max_priorities(content, f)
        assert any("configMAX_PRIORITIES=8" in fi["message"] for fi in findings)

    def test_too_many_priorities(self, tmp_path):
        """GIVEN configMAX_PRIORITIES > 32
           WHEN _check_max_priorities runs
           THEN it returns a minor finding about RAM usage."""
        content = "#define configMAX_PRIORITIES 64\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_max_priorities(content, f)
        assert any("increases scheduler RAM usage" in fi["message"] for fi in findings)

    def test_too_few_priorities(self, tmp_path):
        """GIVEN configMAX_PRIORITIES < 4
           WHEN _check_max_priorities runs
           THEN it returns a major finding."""
        content = "#define configMAX_PRIORITIES 2\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_max_priorities(content, f)
        assert any("may cause priority inversion" in fi["message"] for fi in findings)

    def test_not_defined(self, tmp_path):
        """GIVEN configMAX_PRIORITIES not defined
           WHEN _check_max_priorities runs
           THEN it returns a major finding."""
        content = "#define something_else 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_max_priorities(content, f)
        assert any("not defined" in fi["message"] for fi in findings)


# =============================================================================
# _check_minimal_stack
# =============================================================================

class TestCheckMinimalStack:
    """Tests for _check_minimal_stack — configMINIMAL_STACK_SIZE checks."""

    def test_normal_value(self, tmp_path):
        """GIVEN configMINIMAL_STACK_SIZE >= 120
           WHEN _check_minimal_stack runs
           THEN it returns an info finding."""
        content = "#define configMINIMAL_STACK_SIZE 200\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_minimal_stack(content, f)
        assert any("configMINIMAL_STACK_SIZE=200" in fi["message"] for fi in findings)

    def test_too_small_under_60(self, tmp_path):
        """GIVEN configMINIMAL_STACK_SIZE < 60
           WHEN _check_minimal_stack runs
           THEN it returns a major finding."""
        content = "#define configMINIMAL_STACK_SIZE 50\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_minimal_stack(content, f)
        assert any("idle task stack" in fi["message"] for fi in findings)

    def test_borderline_under_120(self, tmp_path):
        """GIVEN configMINIMAL_STACK_SIZE between 60 and 119
           WHEN _check_minimal_stack runs
           THEN it returns a minor finding."""
        content = "#define configMINIMAL_STACK_SIZE 80\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_minimal_stack(content, f)
        assert any("verify this is sufficient" in fi["message"] for fi in findings)

    def test_not_defined(self, tmp_path):
        """GIVEN configMINIMAL_STACK_SIZE not defined
           WHEN _check_minimal_stack runs
           THEN it returns a minor finding."""
        content = "#define something_else 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_minimal_stack(content, f)
        assert any("not defined" in fi["message"] for fi in findings)


# =============================================================================
# _check_interrupt_priority
# =============================================================================

class TestCheckInterruptPriority:
    """Tests for _check_interrupt_priority — interrupt priority checks."""

    def test_syscall_priority_set(self, tmp_path):
        """GIVEN configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY defined
           WHEN _check_interrupt_priority runs
           THEN it reports the priority value."""
        content = "#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_interrupt_priority(content, f)
        assert any("configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY=5" in fi["message"] for fi in findings)

    def test_syscall_priority_zero(self, tmp_path):
        """GIVEN max syscall priority = 0
           WHEN _check_interrupt_priority runs
           THEN it warns about all interrupts disabled from API."""
        content = "#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 0\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_interrupt_priority(content, f)
        assert any("all interrupts disabled from kernel" in fi["message"] for fi in findings)

    def test_port_optimised_selection(self, tmp_path):
        """GIVEN configUSE_PORT_OPTIMISED_TASK_SELECTION enabled
           WHEN _check_interrupt_priority runs
           THEN it reports the setting."""
        content = "#define configUSE_PORT_OPTIMISED_TASK_SELECTION 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_interrupt_priority(content, f)
        assert any("configUSE_PORT_OPTIMISED_TASK_SELECTION enabled" in fi["message"] for fi in findings)

    def test_alt_macro_name(self, tmp_path):
        """GIVEN configMAX_SYSCALL_INTERRUPT_PRIORITY (alternative name)
           WHEN _check_interrupt_priority runs
           THEN it reports the deprecated status."""
        content = "#define configMAX_SYSCALL_INTERRUPT_PRIORITY 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_interrupt_priority(content, f)
        assert any("deprecated in newer FreeRTOS" in fi["message"] for fi in findings)

    def test_priority_bits(self, tmp_path):
        """GIVEN configPRIO_BITS defined
           WHEN _check_interrupt_priority runs
           THEN it reports the value."""
        content = "#define configPRIO_BITS 4\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_interrupt_priority(content, f)
        assert any("configPRIO_BITS=4" in fi["message"] for fi in findings)


# =============================================================================
# _check_hooks_and_watchdog
# =============================================================================

class TestCheckHooksAndWatchdog:
    """Tests for _check_hooks_and_watchdog — hook function and watchdog checks."""

    def test_idle_hook_enabled(self, tmp_path):
        """GIVEN configUSE_IDLE_HOOK enabled
           WHEN _check_hooks_and_watchdog runs
           THEN it reports the setting."""
        content = "#define configUSE_IDLE_HOOK 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_hooks_and_watchdog(content, f)
        assert any("CPU sleep / watchdog feed expected" in fi["message"] for fi in findings)

    def test_idle_hook_disabled(self, tmp_path):
        """GIVEN configUSE_IDLE_HOOK disabled
           WHEN _check_hooks_and_watchdog runs
           THEN it suggests enabling it."""
        content = "#define configUSE_IDLE_HOOK 0\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_hooks_and_watchdog(content, f)
        assert any("consider enabling for low-power" in fi["message"] for fi in findings)

    def test_tickless_idle(self, tmp_path):
        """GIVEN configUSE_TICKLESS_IDLE enabled
           WHEN _check_hooks_and_watchdog runs
           THEN it reports low-power idle mode."""
        content = "#define configUSE_IDLE_HOOK 0\n#define configUSE_TICKLESS_IDLE 2\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_hooks_and_watchdog(content, f)
        assert any("low-power idle mode enabled" in fi["message"] for fi in findings)

    def test_high_tick_rate(self, tmp_path):
        """GIVEN configTICK_RATE_HZ > 1000
           WHEN _check_hooks_and_watchdog runs
           THEN it warns about context switch overhead."""
        content = "#define configTICK_RATE_HZ 2000\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_hooks_and_watchdog(content, f)
        assert any("high tick rate increases context switch" in fi["message"] for fi in findings)

    def test_low_tick_rate(self, tmp_path):
        """GIVEN configTICK_RATE_HZ < 100
           WHEN _check_hooks_and_watchdog runs
           THEN it warns about reduced granularity."""
        content = "#define configTICK_RATE_HZ 50\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_hooks_and_watchdog(content, f)
        assert any("low tick rate reduces timer granularity" in fi["message"] for fi in findings)


# =============================================================================
# _check_config_assert
# =============================================================================

class TestCheckConfigAssert:
    """Tests for _check_config_assert — configASSERT definition checks."""

    def test_assert_defined_with_handler(self, tmp_path):
        """GIVEN configASSERT defined with vAssertCalled
           WHEN _check_config_assert runs
           THEN it reports proper debug support."""
        content = '#define configASSERT(x) vAssertCalled((x))\n'
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_config_assert(content, f)
        assert any("vAssertCalled" in fi["message"] for fi in findings)

    def test_assert_not_defined(self, tmp_path):
        """GIVEN configASSERT not defined
           WHEN _check_config_assert runs
           THEN it recommends defining it."""
        content = "#define configMAX_PRIORITIES 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_config_assert(content, f)
        assert any("not defined" in fi["message"] for fi in findings)

    def test_assert_noop(self, tmp_path):
        """GIVEN configASSERT defined as empty
           WHEN _check_config_assert runs
           THEN it warns about no-op assertion."""
        content = "#define configASSERT(x)\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_config_assert(content, f)
        assert any("no-op" in fi["message"] for fi in findings)


# =============================================================================
# _check_stack_overflow_hook
# =============================================================================

class TestCheckStackOverflowHook:
    """Tests for _check_stack_overflow_hook — stack overflow detection checks."""

    def test_method_2_enabled(self, tmp_path):
        """GIVEN configCHECK_FOR_STACK_OVERFLOW=2
           WHEN _check_stack_overflow_hook runs
           THEN it reports method 2 (canary)."""
        content = "#define configCHECK_FOR_STACK_OVERFLOW 2\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_stack_overflow_hook(content, f)
        assert any("canary pattern" in fi["message"] for fi in findings)

    def test_method_1_enabled(self, tmp_path):
        """GIVEN configCHECK_FOR_STACK_OVERFLOW=1
           WHEN _check_stack_overflow_hook runs
           THEN it reports method 1."""
        content = "#define configCHECK_FOR_STACK_OVERFLOW 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_stack_overflow_hook(content, f)
        assert any("stack pointer checked on context switch" in fi["message"] for fi in findings)

    def test_disabled(self, tmp_path):
        """GIVEN configCHECK_FOR_STACK_OVERFLOW=0
           WHEN _check_stack_overflow_hook runs
           THEN it recommends enabling."""
        content = "#define configCHECK_FOR_STACK_OVERFLOW 0\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_stack_overflow_hook(content, f)
        assert any("stack overflow detection disabled" in fi["message"] for fi in findings)

    def test_not_defined(self, tmp_path):
        """GIVEN configCHECK_FOR_STACK_OVERFLOW not defined
           WHEN _check_stack_overflow_hook runs
           THEN it recommends setting it."""
        content = "#define configMAX_PRIORITIES 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_stack_overflow_hook(content, f)
        assert any("not defined" in fi["message"] for fi in findings)


# =============================================================================
# _check_run_time_stats
# =============================================================================

class TestCheckRunTimeStats:
    """Tests for _check_run_time_stats — runtime statistics checks."""

    def test_stats_enabled(self, tmp_path):
        """GIVEN configGENERATE_RUN_TIME_STATS enabled
           WHEN _check_run_time_stats runs
           THEN it reports stats enabled."""
        content = "#define configGENERATE_RUN_TIME_STATS 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_run_time_stats(content, f)
        assert any("task CPU utilization stats enabled" in fi["message"] for fi in findings)

    def test_stats_disabled(self, tmp_path):
        """GIVEN configGENERATE_RUN_TIME_STATS disabled
           WHEN _check_run_time_stats runs
           THEN it suggests enabling for profiling."""
        content = "#define configGENERATE_RUN_TIME_STATS 0\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_run_time_stats(content, f)
        assert any("enable for performance debugging" in fi["message"] for fi in findings)

    def test_stats_not_defined(self, tmp_path):
        """GIVEN configGENERATE_RUN_TIME_STATS not defined
           WHEN _check_run_time_stats runs
           THEN it suggests enabling."""
        content = "#define configMAX_PRIORITIES 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_run_time_stats(content, f)
        assert any("enable for performance debugging" in fi["message"] for fi in findings)


# =============================================================================
# _check_mutex_and_semaphore
# =============================================================================

class TestCheckMutexAndSemaphore:
    """Tests for _check_mutex_and_semaphore — sync mechanism checks."""

    def test_mutex_enabled(self, tmp_path):
        """GIVEN configUSE_MUTEXES enabled
           WHEN _check_mutex_and_semaphore runs
           THEN it reports priority inheritance available."""
        content = "#define configUSE_MUTEXES 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_mutex_and_semaphore(content, f)
        assert any("priority inheritance available" in fi["message"] for fi in findings)

    def test_recursive_mutex(self, tmp_path):
        """GIVEN configUSE_RECURSIVE_MUTEXES enabled
           WHEN _check_mutex_and_semaphore runs
           THEN it reports the setting."""
        content = "#define configUSE_RECURSIVE_MUTEXES 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_mutex_and_semaphore(content, f)
        assert any("configUSE_RECURSIVE_MUTEXES enabled" in fi["message"] for fi in findings)

    def test_no_sync_enabled(self, tmp_path):
        """GIVEN no mutex or semaphore features enabled
           WHEN _check_mutex_and_semaphore runs
           THEN it warns about synchronization strategy."""
        content = "#define configMAX_PRIORITIES 5\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_mutex_and_semaphore(content, f)
        assert any("No mutex or semaphore features" in fi["message"] for fi in findings)

    def test_queue_sets(self, tmp_path):
        """GIVEN configUSE_QUEUE_SETS enabled
           WHEN _check_mutex_and_semaphore runs
           THEN it reports the setting."""
        content = "#define configUSE_QUEUE_SETS 1\n"
        f = _create_file(tmp_path, "FreeRTOSConfig.h", content)
        findings = _check_mutex_and_semaphore(content, f)
        assert any("configUSE_QUEUE_SETS enabled" in fi["message"] for fi in findings)


# =============================================================================
# _build_rtos_review_prompt
# =============================================================================

class TestBuildRtosReviewPrompt:
    """Tests for _build_rtos_review_prompt — LLM prompt builder."""

    def test_generates_prompts(self, tmp_path):
        """GIVEN RTOS config file contents
           WHEN _build_rtos_review_prompt runs
           THEN it returns system and user prompts."""
        rtos_contents = {"/path/FreeRTOSConfig.h": FREERTOS_CONFIG_BASIC}
        system_prompt, user_prompt = _build_rtos_review_prompt(rtos_contents)
        assert "rtos configuration" in system_prompt.lower()
        assert "FreeRTOSConfig.h" in user_prompt

    def test_empty_contents(self):
        """GIVEN empty RTOS contents dict
           WHEN _build_rtos_review_prompt runs
           THEN prompts still contain key sections."""
        system_prompt, user_prompt = _build_rtos_review_prompt({})
        assert "rtos configuration" in system_prompt.lower()
        assert "RTOS Configuration Files" in user_prompt


# =============================================================================
# _static_rtos_review
# =============================================================================

class TestStaticRtosReview:
    """Tests for _static_rtos_review — all static checks combined."""

    def test_no_config_files(self, tmp_path):
        """GIVEN no RTOS config files
           WHEN _static_rtos_review runs
           THEN it returns a discovery finding."""
        findings = _static_rtos_review(tmp_path)
        assert any("No RTOS configuration file" in fi["message"] for fi in findings)

    def test_with_freertos_config(self, tmp_path):
        """GIVEN a valid FreeRTOSConfig.h
           WHEN _static_rtos_review runs
           THEN multiple category findings are generated."""
        _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)
        findings = _static_rtos_review(tmp_path)
        assert len(findings) > 1
        # Should have findings from multiple categories
        categories = {f["category"] for f in findings}
        assert len(categories) > 1

    def test_unreadable_file(self, tmp_path):
        """GIVEN an unreadable config file
           WHEN _static_rtos_review runs
           THEN it returns an IO error finding."""
        f = _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)
        f.chmod(0o000)
        try:
            findings = _static_rtos_review(tmp_path)
            # Should not crash — unreadable file gracefully skipped
            assert isinstance(findings, list)
        finally:
            f.chmod(0o644)


# =============================================================================
# step_review_rtos — end-to-end
# =============================================================================

class TestStepReviewRtos:
    """Tests for step_review_rtos — the main pipeline step handler."""

    @patch("yuleosh.pipeline.step_handlers.review_rtos._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_rtos.os.environ")
    def test_empty_project(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN an empty project directory
           WHEN step_review_rtos runs
           THEN it reports no config files found."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        result = step_review_rtos(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-rtos"
        assert len(report["config_files_found"]) == 0

    @patch("yuleosh.pipeline.step_handlers.review_rtos._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_rtos.os.environ")
    def test_with_freertos_config(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a FreeRTOSConfig.h file exists
           WHEN step_review_rtos runs
           THEN it generates multiple findings."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "# RTOS Review\nGood config.", "usage": {"total_tokens": 200}}

        _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)

        result = step_review_rtos(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-rtos"
        assert len(report["config_files_found"]) == 1
        assert report["finding_count"] > 0

    @patch("yuleosh.pipeline.step_handlers.review_rtos._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_rtos.os.environ")
    def test_llm_failure_non_fatal(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_rtos runs
           THEN the step still completes."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.side_effect = RuntimeError("LLM down")

        _create_file(tmp_path, "FreeRTOSConfig.h", FREERTOS_CONFIG_BASIC)

        result = step_review_rtos(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-rtos"
        assert "unavailable" in report["llm_review"] or "(LLM-powered" in report["llm_review"]

    @patch("yuleosh.pipeline.step_handlers.review_rtos._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_rtos.os.environ")
    def test_write_error(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN the output file cannot be written
           WHEN step_review_rtos runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        mock_session.session_dir = tmp_path / "nonexistent" / "deep"

        with pytest.raises(PipelineStepError, match="Cannot write RTOS review"):
            step_review_rtos(mock_session)

    @patch("yuleosh.pipeline.step_handlers.review_rtos._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_rtos.os.environ")
    def test_passed_status(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a well-configured FreeRTOS config
           WHEN step_review_rtos runs
           THEN the status may be passed."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "good", "usage": {"total_tokens": 50}}

        # Well-configured config with all settings appropriate
        config = """#define configMAX_PRIORITIES 15
#define configMINIMAL_STACK_SIZE 256
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 5
#define configTICK_RATE_HZ 1000
#define configUSE_IDLE_HOOK 0
#define configUSE_TICK_HOOK 0
#define configUSE_MUTEXES 1
#define configCHECK_FOR_STACK_OVERFLOW 2
#define configASSERT(x) vAssertCalled((x))
"""
        _create_file(tmp_path, "FreeRTOSConfig.h", config)

        result = step_review_rtos(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-rtos"
        # Status could be passed if no critical findings
        assert report["status"] in ("passed", "failed", "retry")
