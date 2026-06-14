# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep tests for yuleosh.review.c_review — coverage of all static analysis
functions, _llm_review_snippet, _get_llm_client, and review_embedded_c
with various directory structures, file scanning, and edge cases.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.review.c_review import (
    review_embedded_c,
    _check_content,
    _llm_review_snippet,
    _get_llm_client,
    _LLM_CLIENT,
    _LLM_SYSTEM_PROMPT,
    RE_ISR_HANDLER,
    RE_VOLATILE_VAR,
    RE_GLOBAL_VAR,
    RE_MEMORY_BARRIER,
    RE_CRITICAL_SECTION,
    RE_WATCHDOG_FEED,
    RE_HARDCODED_DELAY,
    RE_HAL_DELAY,
    RE_DEBUG_PRINTF,
    RE_LARGE_LOCAL,
    RE_RECURSIVE,
)


# ======================================================================
# _get_llm_client — fallback and direct import
# ======================================================================


class TestGetLLMClient:
    """Test _get_llm_client lazy loading and fallback logic."""

    def test_returns_client(self):
        """Should return a client (real or mock)."""
        client = _get_llm_client()
        assert client is not None
        assert hasattr(client, "chat_completion")

    def test_mock_client_has_chat_completion(self):
        """The fallback mock client should support chat_completion."""
        from unittest.mock import patch
        import yuleosh.review.c_review as crm
        crm._LLM_CLIENT = None
        # Force mock path by removing llm modules
        with patch.dict('sys.modules', {
            'yuleosh.llm': None,
            'yuleosh.llm.client': None,
            'llm': None,
            'llm.client': None,
        }):
            client = crm._get_llm_client()
            result = client.chat_completion()
            assert isinstance(result, dict)

    def test_lazy_loading(self):
        """Subsequent calls should return the cached instance."""
        global _LLM_CLIENT
        _LLM_CLIENT = None
        c1 = _get_llm_client()
        c2 = _get_llm_client()
        assert c1 is c2  # same instance


# ======================================================================
# _llm_review_snippet — edge cases
# ======================================================================


class TestLLMReviewSnippet:
    """Test _llm_review_snippet behavior with mocks."""

    def test_empty_content(self):
        result = _llm_review_snippet("")
        assert isinstance(result, list)
        assert result == []

    def test_llm_returns_non_json(self):
        """When LLM returns garbage, should return empty list."""
        with patch("yuleosh.review.c_review._get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = {"content": "not json at all"}
            mock_get.return_value = mock_client
            result = _llm_review_snippet("int x = 1;")
            assert result == []

    def test_llm_returns_valid_findings(self):
        """When LLM returns valid JSON findings, should parse them."""
        with patch("yuleosh.review.c_review._get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = {
                "content": json.dumps([
                    {"severity": "major", "line": 5, "message": "Missing volatile",
                     "suggestion": "Add volatile"},
                ])
            }
            mock_get.return_value = mock_client
            result = _llm_review_snippet("int x = 1;")
            assert len(result) == 1
            assert result[0]["severity"] == "major"

    def test_llm_returns_object_not_list(self):
        """When LLM returns a single object, should handle gracefully."""
        with patch("yuleosh.review.c_review._get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = {
                "content": '{"severity": "major", "line": 1, "message": "oops"}'
            }
            mock_get.return_value = mock_client
            result = _llm_review_snippet("int x;")
            assert result == []

    def test_llm_returns_outside_code_fence(self):
        """LLM response wrapped in code fences."""
        with patch("yuleosh.review.c_review._get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = {
                "content": "Here is my review:\n```json\n[{\"severity\": \"info\", \"line\": 1, \"message\": \"test\"}]\n```"
            }
            mock_get.return_value = mock_client
            result = _llm_review_snippet("int x;")
            # Should parse via regex match from ``` ... ``` or just find the []
            assert len(result) >= 1

    def test_llm_exception(self):
        """Exception in LLM call should return empty list."""
        with patch("yuleosh.review.c_review._get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = Exception("API error")
            mock_get.return_value = mock_client
            result = _llm_review_snippet("int x;")
            assert result == []


# ======================================================================
# Regex patterns — verify they compile and match correctly
# ======================================================================


class TestRegexPatterns:
    """Test regex patterns used for C static analysis."""

    def test_isr_handler_match(self):
        assert RE_ISR_HANDLER.search("HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)")
        assert RE_ISR_HANDLER.search("USART1_IRQHandler(void)")
        assert RE_ISR_HANDLER.search("__attribute__((interrupt))")

    def test_volatile_var_match(self):
        assert RE_VOLATILE_VAR.search("static uint32_t system_tick;")
        assert RE_VOLATILE_VAR.search("int16_t counter;")

    def test_memory_barrier_match(self):
        assert RE_MEMORY_BARRIER.search("__DSB();")
        assert RE_MEMORY_BARRIER.search("__sync_synchronize();")
        assert RE_MEMORY_BARRIER.search("__atomic_store_n(&x, 1, __ATOMIC_SEQ_CST);")

    def test_critical_section_match(self):
        assert RE_CRITICAL_SECTION.search("taskENTER_CRITICAL();")
        assert RE_CRITICAL_SECTION.search("__disable_irq();")
        assert RE_CRITICAL_SECTION.search("HAL_NVIC_DisableIRQ(IRQn);")
        assert RE_CRITICAL_SECTION.search("portENTER_CRITICAL();")

    def test_watchdog_match(self):
        assert RE_WATCHDOG_FEED.search("HAL_IWDG_Refresh();")
        assert RE_WATCHDOG_FEED.search("wdt_feed();")
        assert RE_WATCHDOG_FEED.search("__HAL_IWDG_RELOAD_COUNTER();")

    def test_hardcoded_delay_match(self):
        assert RE_HARDCODED_DELAY.search("for (volatile uint32_t i = 0; i < 100000; i++)")
        assert RE_HARDCODED_DELAY.search("while (count--)")
        assert RE_HARDCODED_DELAY.search("delay_us(100)")

    def test_hal_delay_match(self):
        assert RE_HAL_DELAY.search("HAL_Delay(10);")

    def test_debug_printf_match(self):
        assert RE_DEBUG_PRINTF.search('printf("hello");')
        assert RE_DEBUG_PRINTF.search('DEBUG_PRINT("msg");')
        assert RE_DEBUG_PRINTF.search('#define DEBUG')

    def test_large_local_match(self):
        assert RE_LARGE_LOCAL.search("uint8_t big_buffer[1024];")
        assert RE_LARGE_LOCAL.search("char huge_buffer[2048];")

    def test_recursive_match(self):
        assert RE_RECURSIVE.search(
            "void foo(int x)\n{\n    foo(x - 1);\n}"
        )


# ======================================================================
# _check_content — detailed check functionality
# ======================================================================


class TestCheckContent:
    """Test _check_content static analysis in detail."""

    MEMORY_BARRIER_MISSING_C = """
#include <stdint.h>

static volatile uint32_t g_flag = 0;

void some_function(void)
{
    __disable_irq();
    g_flag = 1;
    __enable_irq();
    /* Missing DSB/ISB after re-enabling interrupts */
}
"""

    MEMORY_BARRIER_PRESENT_C = """
#include <stdint.h>

static volatile uint32_t g_flag = 0;

void some_function(void)
{
    taskENTER_CRITICAL();
    g_flag = 1;
    taskEXIT_CRITICAL();
    __DSB();
}
"""

    WDT_IN_LOOP_C = """
#include <stdint.h>

void main_loop(void)
{
    while (1) {
        process_data();
        HAL_IWDG_Refresh();
        HAL_IWDG_Refresh();
    }
}
"""

    UNPROTECTED_GLOBAL_C = """
#include <stdint.h>

static uint32_t g_counter = 0;

void normal_function(void)
{
    g_counter = 42;  /* No critical section protection */
}
"""

    DEBUG_DEFINE_C = """
#include <stdint.h>

#define DEBUG

void test(void)
{
    uint32_t x = 1;
}
"""

    TYPEDEF_STRUCT_C = """
#include <stdint.h>

typedef struct {
    uint32_t id;
    uint8_t data[64];
} Packet;

Packet g_packet;

void HAL_SPI_Callback(void)
{
    g_packet.id = 1;
}
"""

    SINGLE_COMMENT_C = """
#include <stdint.h>

// This is a single-line comment
uint32_t g_value;

void HAL_UART_Callback(void)
{
    g_value++;
}
"""

    GENERIC_IRQ_C = """
/* Generic IRQ handler */
void TIM2_IRQHandler(void)
{
    uint32_t status = 0;
    uint8_t local_buffer[64];
}
"""

    def test_memory_barrier_missing(self):
        """Should flag missing DSB/ISB after __enable_irq."""
        findings = _check_content(self.MEMORY_BARRIER_MISSING_C,
                                  "bad_barrier.c", "test/bad_barrier.c")
        barrier_issues = [f for f in findings if "memory barrier" in f.get("message", "").lower()
                          or "DSB" in f.get("message", "")]
        assert len(barrier_issues) >= 1

    def test_memory_barrier_present(self):
        """Should not flag when DSB is present."""
        findings = _check_content(self.MEMORY_BARRIER_PRESENT_C,
                                  "good_barrier.c", "test/good_barrier.c")
        barrier_issues = [f for f in findings if "memory barrier" in f.get("message", "").lower()
                          or "DSB" in f.get("message", "")]
        assert len(barrier_issues) == 0

    def test_watchdog_in_loop(self):
        """Watchdog feed inside a loop should trigger info-level finding."""
        findings = _check_content(self.WDT_IN_LOOP_C,
                                  "wdt_loop.c", "test/wdt_loop.c")
        wdt_issues = [f for f in findings if "看门狗" in f.get("message", "")]
        assert len(wdt_issues) >= 1

    def test_unprotected_global(self):
        """Global modified without critical section should be flagged."""
        findings = _check_content(self.UNPROTECTED_GLOBAL_C,
                                  "unprotected.c", "test/unprotected.c")
        unprotected_issues = [f for f in findings if "临界区" in f.get("message", "")]
        assert len(unprotected_issues) >= 1

    def test_debug_define_flagged(self):
        """#define DEBUG should be flagged as info."""
        findings = _check_content(self.DEBUG_DEFINE_C,
                                  "debug_def.c", "test/debug_def.c")
        debug_issues = [f for f in findings if "DEBUG" in f.get("message", "")]
        assert len(debug_issues) >= 1

    def test_typedef_struct_not_false_positive(self):
        """Struct typedef lines should not trigger volatile warnings."""
        findings = _check_content(self.TYPEDEF_STRUCT_C,
                                  "typedef.c", "test/typedef.c")
        # The non-volatile global g_packet should be flagged sine ISR handler exists
        # but the typedef lines themselves should not cause parsing errors
        assert isinstance(findings, list)

    def test_single_line_comment_skipped(self):
        """Single-line comments should be properly handled."""
        findings = _check_content(self.SINGLE_COMMENT_C,
                                  "comment.c", "test/comment.c")
        assert isinstance(findings, list)

    def test_generic_irq_handler(self):
        """Generic IRQ handler without globals should not find race conditions."""
        findings = _check_content(self.GENERIC_IRQ_C,
                                  "generic_irq.c", "test/generic_irq.c")
        race_issues = [f for f in findings if "竞态" in f.get("message", "")]
        assert len(race_issues) == 0

    def test_no_critical_section_findings_if_not_present(self):
        """If critical section entry/exit not present, barrier check should be skipped."""
        content = """void foo(void) { int x = 1; }"""
        findings = _check_content(content, "simple.c", "test/simple.c")
        barrier_issues = [f for f in findings if "barrier" in f.get("message", "").lower()]
        assert len(barrier_issues) == 0

    def test_recursive_function(self):
        """Recursive function pattern should be detectable."""
        content = """void recurse(int n)
{
    if (n > 0) recurse(n - 1);
}"""
        assert RE_RECURSIVE.search(content)

    def test_hal_delay_not_hardcoded(self):
        """HAL_Delay should NOT be flagged as hardcoded delay."""
        content = """void wait(void) { HAL_Delay(10); }"""
        findings = _check_content(content, "hal_delay.c", "test/hal_delay.c")
        hc_issues = [f for f in findings if "硬编码延时" in f.get("message", "")]
        assert len(hc_issues) == 0

    def test_empty_file_no_findings(self):
        findings = _check_content("", "empty.c", "test/empty.c")
        assert len(findings) == 0


# ======================================================================
# review_embedded_c — full entry point with directory scanning
# ======================================================================


class TestReviewEmbeddedC:
    """Test the review_embedded_c entry point."""

    def test_with_src_dir_scan(self):
        """Should scan src/ for C files when no changed_files given."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "main.c").write_text(
                'uint32_t g_tick;\nvoid HAL_GPIO_EXTI_Callback(uint16_t p) { g_tick++; }'
            )

            result = review_embedded_c("test", tmpdir, [])
            assert result.status in ("passed", "failed", "retry")
            assert len(result.findings) >= 1

    def test_with_cross_dir_scan(self):
        """Should scan cross/ for C files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cross_dir = Path(tmpdir) / "cross"
            cross_dir.mkdir()
            (cross_dir / "drivers" / "uart.c").parent.mkdir(parents=True)
            (cross_dir / "drivers" / "uart.c").write_text(
                'int x = 1;'
            )

            result = review_embedded_c("test", tmpdir, [])
            assert result.status == "passed"
            assert "No embedded C files" in result.summary or result.status == "passed"

    def test_with_main_dir_scan(self):
        """Should scan main/ for C files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main_dir = Path(tmpdir) / "main"
            main_dir.mkdir()
            (main_dir / "app.c").write_text(
                'uint32_t g_counter;\nvoid HAL_GPIO_EXTI_Callback(uint16_t p) { g_counter++; }'
            )
            result = review_embedded_c("test", tmpdir, [])
            assert len(result.findings) >= 1

    def test_nonexistent_file_skipped(self):
        """Files in changed_files that don't exist should be skipped."""
        result = review_embedded_c("test", "/tmp", ["nonexistent.c"])
        assert result is not None

    def test_no_c_files_found(self):
        """When no C files found, should return passed with summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = review_embedded_c("test", tmpdir, [])
            assert result.status == "passed"
            assert "No embedded C files" in result.summary

    def test_non_c_files_skipped(self):
        """Non .c/.h files in changed_files should be filtered."""
        result = review_embedded_c("test", "/tmp", ["readme.md", "main.py"])
        # Should fall back to scanning directories
        assert result is not None

    def test_llm_findings_integration(self):
        """LLM findings should be added to the result with proper categories."""
        with patch("yuleosh.review.c_review._llm_review_snippet") as mock_llm:
            mock_llm.return_value = [
                {"severity": "major", "line": 3, "message": "Missing volatile",
                 "suggestion": "Add volatile keyword"},
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                src_dir = Path(tmpdir) / "src"
                src_dir.mkdir()
                (src_dir / "test.c").write_text(
                    'uint32_t g_tick;\n'
                    'void HAL_GPIO_EXTI_Callback(uint16_t p) { g_tick++; }'
                )

                result = review_embedded_c("test", tmpdir, [])
                llm_findings = [f for f in result.findings if f.category == "embedded-c-llm"]
                assert len(llm_findings) >= 1

    def test_llm_exception_handled(self):
        """Exception in LLM pass should be caught."""
        with patch("yuleosh.review.c_review._llm_review_snippet",
                   side_effect=Exception("LLM crashed")):
            with tempfile.TemporaryDirectory() as tmpdir:
                src_dir = Path(tmpdir) / "src"
                src_dir.mkdir()
                (src_dir / "test.c").write_text(
                    'uint32_t g_tick;\n'
                    'void HAL_GPIO_EXTI_Callback(uint16_t p) { g_tick++; }'
                )
                result = review_embedded_c("test", tmpdir, [])
                # Should not raise despite LLM failure
                assert result is not None

    def test_template_dir_scan(self):
        """When no src/cross/main, should scan templates/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            templates = Path(tmpdir) / "templates"
            templates.mkdir()
            tmpl_dir = templates / "default"
            tmpl_dir.mkdir()
            main_subdir = tmpl_dir / "main"
            main_subdir.mkdir()
            (main_subdir / "app.c").write_text(
                'void HAL_GPIO_EXTI_Callback(uint16_t p) { int x = 1; }'
            )

            result = review_embedded_c("test", tmpdir, [])
            assert result is not None
            assert result.status in ("passed", "failed", "retry")
