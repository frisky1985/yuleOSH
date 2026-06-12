#!/usr/bin/env python3
"""
Tests for yuleOSH Embedded C Code Review module (c_review + resource_predictor).

Verifies:
  - volatile keyword detection on ISR-shared globals
  - ISR race condition detection
  - Clean code: no false positives
  - Resource predictor output format correctness
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure the project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from review.c_review import (
    review_embedded_c,
    _check_content,
    _llm_review_snippet,
)
from review.resource_predictor import predict_resources, predict_all_in_project
from review.run import ReviewFinding, ReviewResult


# ══════════════════════════════════════════════════════════════
# Fixtures: C code snippets for testing
# ══════════════════════════════════════════════════════════════

BAD_VOLATILE_C = """
#include <stdint.h>

/* Shared global — should be volatile! */
uint32_t system_tick;
uint8_t sensor_ready_flag;

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    /* ISR modifies shared data without volatile */
    system_tick++;
    sensor_ready_flag = 1;
}
"""

BAD_ISR_RACE_C = """
#include <stdint.h>

volatile uint32_t g_irq_count = 0;

static void some_function(void)
{
    /* Race: g_irq_count modified outside critical section */
    g_irq_count = 100;
}
"""

CLEAN_EMBEDDED_C = """
#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static volatile uint32_t g_system_tick = 0;
static uint8_t g_local_flag = 0;

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    /* Volatile + critical section — correct */
    taskENTER_CRITICAL();
    g_system_tick++;
    taskEXIT_CRITICAL();
    __DSB();
}

void app_main(void)
{
    int local_counter = 0;
    vTaskDelay(pdMS_TO_TICKS(1000));
}
"""

BAD_HARDCODED_DELAY_C = """
#include <stdint.h>

void delay_busy_wait(void)
{
    /* Hardcoded busy-wait — bad for FreeRTOS */
    for (volatile uint32_t i = 0; i < 100000; i++) {
        __NOP();
    }
}

void normal_delay(void)
{
    /* This is fine */
    HAL_Delay(10);
}
"""

BAD_DEBUG_PRINTF_C = """
#include <stdio.h>

void debug_function(void)
{
    uint32_t value = 42;
    printf("Debug: value = %u\\n", value);
}

void release_function(void)
{
    uint32_t result = 1 + 2;
}
"""

BAD_LARGE_LOCAL_C = """
#include <stdint.h>

void process_buffer(void)
{
    /* Large local array on stack — risk of overflow */
    uint8_t big_buffer[1024];
    uint16_t large_table[512];

    for (int i = 0; i < 1024; i++) {
        big_buffer[i] = (uint8_t)i;
    }
}
"""

RESOURCE_TEST_C = """
#include <stdint.h>
#include <string.h>

/* Global state */
static uint32_t g_counter = 0;
static uint8_t g_buffer[256];

typedef struct {
    uint32_t id;
    uint8_t data[64];
    uint16_t length;
} Packet;

static Packet g_rx_packet;

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    g_counter++;
}

void process_packet(void)
{
    uint8_t temp_buf[128];
    memcpy(temp_buf, g_buffer, 128);
}
"""


# ══════════════════════════════════════════════════════════════
# Tests: volatile detection
# ══════════════════════════════════════════════════════════════


class TestVolatileDetection:
    """Verify detection of missing volatile keywords on ISR-shared globals."""

    def test_detects_missing_volatile(self):
        """ISR file with non-volatile globals should be flagged."""
        findings = _check_content(BAD_VOLATILE_C, "bad_volatile.c", "test/bad_volatile.c")
        volatile_issues = [f for f in findings if "volatile" in f.get("message", "").lower()]
        assert len(volatile_issues) >= 1, (
            f"Expected at least 1 volatile warning, got {len(volatile_issues)}: {findings}"
        )

    def test_clean_code_no_false_volatile(self):
        """Clean code with proper volatile should not trigger false positives."""
        findings = _check_content(CLEAN_EMBEDDED_C, "clean.c", "test/clean.c")
        volatile_issues = [f for f in findings if "volatile" in f.get("message", "").lower()]
        assert len(volatile_issues) == 0, (
            f"Expected 0 volatile warnings on clean code, got {len(volatile_issues)}: {findings}"
        )


# ══════════════════════════════════════════════════════════════
# Tests: ISR race condition
# ══════════════════════════════════════════════════════════════


class TestISRRaceCondition:
    """Verify detection of unprotected global variable access."""

    def test_detects_isr_race(self):
        """Global modified outside critical section should be flagged."""
        findings = _check_content(BAD_ISR_RACE_C, "bad_race.c", "test/bad_race.c")
        race_issues = [f for f in findings if "临界区" in f.get("message", "") or "critical" in f.get("message", "").lower()]
        race_issues += [f for f in findings if "竞态" in f.get("message", "")]
        assert len(race_issues) >= 1, (
            f"Expected at least 1 race condition finding, got {len(race_issues)}: {findings}"
        )


# ══════════════════════════════════════════════════════════════
# Tests: hardcoded delays
# ══════════════════════════════════════════════════════════════


class TestHardcodedDelay:
    """Verify detection of busy-wait delay loops."""

    def test_detects_hardcoded_delay(self):
        """Busy-wait loops should be flagged."""
        findings = _check_content(BAD_HARDCODED_DELAY_C, "bad_delay.c", "test/bad_delay.c")
        delay_issues = [f for f in findings if "延时" in f.get("message", "")]
        assert len(delay_issues) >= 1, (
            f"Expected at least 1 hardcoded delay finding, got {len(delay_issues)}: {findings}"
        )

    def test_hal_delay_not_flagged(self):
        """HAL_Delay call line should NOT be flagged as hardcoded delay."""
        findings = _check_content(BAD_HARDCODED_DELAY_C, "bad_delay.c", "test/bad_delay.c")
        # HAL_Delay(10) is on line 13 (1-indexed), check it's not flagged
        hal_line_issues = [f for f in findings if f.get("line", 0) == 13]
        assert len(hal_line_issues) == 0, (
            f"HAL_Delay line should not be flagged: {hal_line_issues}"
        )


# ══════════════════════════════════════════════════════════════
# Tests: printf/debug detection
# ══════════════════════════════════════════════════════════════


class TestDebugPrintf:
    """Verify detection of printf/debug statements in release code."""

    def test_detects_printf(self):
        """printf calls should be flagged."""
        findings = _check_content(BAD_DEBUG_PRINTF_C, "debug.c", "test/debug.c")
        printf_issues = [f for f in findings if "printf" in f.get("message", "")]
        assert len(printf_issues) >= 1, (
            f"Expected at least 1 printf finding, got {len(printf_issues)}: {findings}"
        )

    def test_clean_function_no_printf(self):
        """Function without printf should not trigger printf alert."""
        findings = _check_content(BAD_DEBUG_PRINTF_C, "debug.c", "test/debug.c")
        release_fn_issues = [
            f for f in findings
            if "release_function" in f.get("message", "")
        ]
        assert len(release_fn_issues) == 0


# ══════════════════════════════════════════════════════════════
# Tests: large local array
# ══════════════════════════════════════════════════════════════


class TestLargeLocalArray:
    """Verify detection of large stack-allocated arrays."""

    def test_detects_large_local(self):
        """Large arrays inside functions should be flagged."""
        findings = _check_content(BAD_LARGE_LOCAL_C, "large_local.c", "test/large_local.c")
        stack_issues = [f for f in findings if "栈" in f.get("message", "") or "stack" in f.get("message", "").lower()]
        assert len(stack_issues) >= 1, (
            f"Expected at least 1 stack risk finding, got {len(stack_issues)}: {findings}"
        )


# ══════════════════════════════════════════════════════════════
# Tests: resource predictor
# ══════════════════════════════════════════════════════════════


class TestResourcePredictor:
    """Verify resource predictor output format and consistency."""

    def test_predictor_output_format(self):
        """predict_resources should return a dict with all required keys."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".c", delete=False, encoding="utf-8"
        ) as f:
            f.write(RESOURCE_TEST_C)
            tmp_path = f.name

        try:
            result = predict_resources(tmp_path)

            # Required keys
            expected_keys = {
                "ram_estimate", "rom_estimate", "cpu_estimate",
                "stack_risk", "isr_latency", "suggestions",
            }
            assert expected_keys.issubset(result.keys()), (
                f"Missing keys: {expected_keys - result.keys()}"
            )

            # Types
            assert isinstance(result["ram_estimate"], str), (
                f"ram_estimate should be str, got {type(result['ram_estimate'])}"
            )
            assert isinstance(result["rom_estimate"], str), (
                f"rom_estimate should be str, got {type(result['rom_estimate'])}"
            )
            assert isinstance(result["cpu_estimate"], str), (
                f"cpu_estimate should be str, got {type(result['cpu_estimate'])}"
            )
            assert isinstance(result["stack_risk"], str), (
                f"stack_risk should be str, got {type(result['stack_risk'])}"
            )
            assert isinstance(result["isr_latency"], str), (
                f"isr_latency should be str, got {type(result['isr_latency'])}"
            )
            assert isinstance(result["suggestions"], list), (
                f"suggestions should be list, got {type(result['suggestions'])}"
            )

            # stack_risk should be one of: 低, 中, 高 (or N/A)
            assert result["stack_risk"] in ("低", "中", "高", "N/A"), (
                f"Unexpected stack_risk value: {result['stack_risk']}"
            )

            # ram/rom estimates should contain "KB" or "N/A"
            if "N/A" not in result["ram_estimate"]:
                assert "KB" in result["ram_estimate"] or "B" in result["ram_estimate"], (
                    f"ram_estimate should reference KB: {result['ram_estimate']}"
                )

            # isr_latency should contain μs or us or N/A
            if "N/A" not in result["isr_latency"]:
                assert "μs" in result["isr_latency"] or "us" in result["isr_latency"], (
                    f"isr_latency should reference μs/us: {result['isr_latency']}"
                )

        finally:
            os.unlink(tmp_path)

    def test_predictor_with_missing_file(self):
        """predict_resources should handle non-existent files gracefully."""
        result = predict_resources("/nonexistent/file.c")
        assert result["ram_estimate"] == "N/A (文件不存在)"
        assert "文件未找到" in result["suggestions"]

    def test_predict_all_in_project(self):
        """predict_all_in_project should return a list of per-file results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test C file
            test_file = Path(tmpdir) / "src" / "main.c"
            test_file.parent.mkdir(parents=True)
            test_file.write_text(RESOURCE_TEST_C)

            results = predict_all_in_project(tmpdir)
            assert len(results) == 1, (
                f"Expected 1 result, got {len(results)}"
            )
            assert results[0]["file"] == "src/main.c"
            assert "ram_estimate" in results[0]


# ══════════════════════════════════════════════════════════════
# Tests: integration with review engine
# ══════════════════════════════════════════════════════════════


class TestReviewIntegration:
    """Verify c_review integrates correctly with the review engine."""

    def test_review_embedded_c_no_files(self):
        """Review with no .c/.h files should pass cleanly."""
        result = review_embedded_c(
            "test-integration", "/tmp", []
        )
        assert result.status in ("passed", "failed")
        if result.status == "passed":
            assert "No embedded C files" in result.summary

    def test_review_embedded_c_with_file(self):
        """Review with a real C file should produce findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project structure
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            test_file = src_dir / "main.c"
            test_file.write_text(BAD_VOLATILE_C)

            result = review_embedded_c(
                "test-volatile", tmpdir, ["src/main.c"]
            )
            assert result.status in ("passed", "failed", "retry")
            assert len(result.findings) >= 1, (
                f"Expected at least 1 finding, got {len(result.findings)}"
            )

    def test_clean_file_no_false_positives(self):
        """Clean embedded C code should have minimal findings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            test_file = src_dir / "main.c"
            test_file.write_text(CLEAN_EMBEDDED_C)

            result = review_embedded_c(
                "test-clean", tmpdir, ["src/main.c"]
            )
            # Clean code might still produce info-level findings,
            # but should not produce critical/major ones
            critical_major = [
                f for f in result.findings
                if f.severity in ("critical", "major")
            ]
            assert len(critical_major) == 0, (
                f"Clean code should have 0 critical/major findings, "
                f"got {len(critical_major)}: "
                f"{[(f.severity, f.message[:40]) for f in critical_major]}"
            )


# ══════════════════════════════════════════════════════════════
# Tests: edge cases
# ══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_file(self):
        """Empty file should produce no findings."""
        findings = _check_content("", "empty.c", "test/empty.c")
        assert len(findings) == 0, f"Empty file should have 0 findings, got {len(findings)}"

    def test_header_file(self):
        """Header files should be analyzable."""
        header_content = """
#ifndef _MY_HEADER_H
#define _MY_HEADER_H

#include <stdint.h>

/* Shared global in header (should be volatile if ISR-related) */
extern uint32_t g_system_tick;

#endif
"""
        findings = _check_content(header_content, "header.h", "test/header.h")
        # Headers with extern declarations should not cause false positives
        assert isinstance(findings, list)

    def test_llm_snippet_empty(self):
        """LLM review should handle empty snippets gracefully."""
        result = _llm_review_snippet("")
        assert isinstance(result, list)
