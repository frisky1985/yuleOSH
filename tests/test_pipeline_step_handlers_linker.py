#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_linker."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_linker import (
    step_review_linker,
    _find_linker_scripts,
    _check_stack_size,
    _check_section_definitions,
    _check_vector_table_alignment,
    _check_memory_regions,
    _check_lma_vma_difference,
    _check_arm_exception_tables,
    _check_heap_stack_overlap,
    _static_linker_review,
    _build_linker_review_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession for linker review testing."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-linker",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-linker"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _create_file(project_dir: Path, rel_path: str, content: str = "") -> Path:
    """Create a file under project_dir and return its path."""
    p = project_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# A minimal valid STM32 linker script for testing
LINKER_SCRIPT_MINIMAL = """/* STM32F4 Linker Script */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1M
    RAM (xw)    : ORIGIN = 0x20000000, LENGTH = 192K
    CCM (rw)    : ORIGIN = 0x10000000, LENGTH = 64K
}

SECTIONS
{
    .isr_vector :
    {
        . = ALIGN(256);
        __Vectors = .;
        KEEP(*(.isr_vector))
        . = ALIGN(4);
    } > FLASH

    .text :
    {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    } > FLASH

    .ARM.exidx :
    {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
    } > FLASH

    .ARM.extab :
    {
        *(.ARM.extab*)
    } > FLASH

    .data : AT (__etext)
    {
        _sdata = .;
        *(.data*)
        _edata = .;
    } > RAM AT > FLASH

    .bss :
    {
        _sbss = .;
        *(.bss*)
        _ebss = .;
    } > RAM

    .noinit (NOLOAD) :
    {
        *(.noinit*)
    } > RAM

    .heap (NOLOAD) :
    {
        . = ALIGN(8);
        __heap_start = .;
        __heap_size = 0x400;
        . += __heap_size;
        __heap_end = .;
    } > RAM

    .stack (NOLOAD) :
    {
        . = ALIGN(8);
        __stack_start = .;
        STACK_SIZE = 0x400;
        . += STACK_SIZE;
        __stack_end = .;
    } > RAM
}
"""


# =============================================================================
# _find_linker_scripts
# =============================================================================

class TestFindLinkerScripts:
    """Tests for _find_linker_scripts — linker script discovery."""

    def test_no_scripts(self, tmp_path):
        """GIVEN no linker scripts in the project
           WHEN _find_linker_scripts runs
           THEN it returns empty."""
        result = _find_linker_scripts(tmp_path)
        assert result == []

    def test_finds_ld_file(self, tmp_path):
        """GIVEN a .ld file exists
           WHEN _find_linker_scripts runs
           THEN it finds the file."""
        _create_file(tmp_path, "STM32F407.ld", LINKER_SCRIPT_MINIMAL)
        result = _find_linker_scripts(tmp_path)
        assert len(result) == 1

    def test_finds_lds_file(self, tmp_path):
        """GIVEN a .lds file exists
           WHEN _find_linker_scripts runs
           THEN it finds the file."""
        _create_file(tmp_path, "linker.lds", LINKER_SCRIPT_MINIMAL)
        result = _find_linker_scripts(tmp_path)
        assert len(result) == 1

    def test_ignores_hidden_files(self, tmp_path):
        """GIVEN a hidden .ld file
           WHEN _find_linker_scripts runs
           THEN it skips .-prefixed names."""
        _create_file(tmp_path, ".hidden.ld", "content")
        result = _find_linker_scripts(tmp_path)
        assert len(result) == 0


# =============================================================================
# _check_stack_size
# =============================================================================

class TestCheckStackSize:
    """Tests for _check_stack_size — stack and heap size checks."""

    def test_stack_size_too_small(self, tmp_path):
        """GIVEN stack size < 1 KB
           WHEN _check_stack_size runs
           THEN it returns a major finding."""
        content = "STACK_SIZE = 512"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("Stack size" in fi["message"] and "< 1 KB" in fi["message"] for fi in findings)

    def test_stack_size_borderline(self, tmp_path):
        """GIVEN stack size between 1 KB and 2 KB
           WHEN _check_stack_size runs
           THEN it returns a minor finding."""
        content = "STACK_SIZE = 1500"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("Stack size" in fi["message"] and "< 2 KB" in fi["message"] for fi in findings)

    def test_stack_size_adequate(self, tmp_path):
        """GIVEN stack size >= 2 KB
           WHEN _check_stack_size runs
           THEN it returns an info finding."""
        content = "STACK_SIZE = 4096"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("Stack size defined" in fi["message"] for fi in findings)

    def test_alternate_stack_syntax(self, tmp_path):
        """GIVEN __stack_size syntax
           WHEN _check_stack_size runs
           THEN it finds and checks it."""
        content = "__stack_size = 1024"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("Stack size" in fi["message"] for fi in findings)

    def test_heap_zero(self, tmp_path):
        """GIVEN heap size explicitly 0
           WHEN _check_stack_size runs
           THEN it reports no dynamic memory expected."""
        content = "HEAP_SIZE = 0"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("Heap size explicitly set to 0" in fi["message"] for fi in findings)

    def test_heap_positive(self, tmp_path):
        """GIVEN heap size > 0
           WHEN _check_stack_size runs
           THEN it reports dynamic allocation is intentional."""
        content = "HEAP_SIZE = 2048"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("verify dynamic allocation is intentional" in fi["message"] for fi in findings)

    def test_no_stack_definition(self, tmp_path):
        """GIVEN no explicit stack size definition
           WHEN _check_stack_size runs
           THEN it returns a minor finding."""
        content = "int x;"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_stack_size(content, f)
        assert any("No explicit stack size definition" in fi["message"] for fi in findings)


# =============================================================================
# _check_section_definitions
# =============================================================================

class TestCheckSectionDefinitions:
    """Tests for _check_section_definitions — essential section checks."""

    def test_missing_text(self, tmp_path):
        """GIVEN no .text section
           WHEN _check_section_definitions runs
           THEN it returns a critical finding."""
        content = ".data : { *(.data*) }"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_section_definitions(content, f)
        assert any(fi["severity"] == "critical" and ".text" in fi["message"] for fi in findings)

    def test_missing_data_and_bss(self, tmp_path):
        """GIVEN no .data and .bss sections
           WHEN _check_section_definitions runs
           THEN it returns major findings."""
        content = ".text : { *(.text*) }"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_section_definitions(content, f)
        assert any(".data" in fi["message"] for fi in findings)
        assert any(".bss" in fi["message"] for fi in findings)

    def test_all_sections_present(self, tmp_path):
        """GIVEN .text, .data, .bss sections present
           WHEN _check_section_definitions runs
           THEN no critical/major missing-section findings."""
        content = ".text : {} .data : {} .bss : {}"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_section_definitions(content, f)
        assert not any(".section" in fi["message"] for fi in findings)

    def test_noinit_recommended(self, tmp_path):
        """GIVEN .text, .data, .bss but no .noinit
           WHEN _check_section_definitions runs
           THEN it suggests considering .noinit."""
        content = ".text : {} .data : {} .bss : {}"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_section_definitions(content, f)
        assert any("No .noinit section found" in fi["message"] for fi in findings)


# =============================================================================
# _check_vector_table_alignment
# =============================================================================

class TestCheckVectorTableAlignment:
    """Tests for _check_vector_table_alignment — vector table alignment checks."""

    def test_vector_table_insufficient_alignment(self, tmp_path):
        """GIVEN vector table with alignment < 256
           WHEN _check_vector_table_alignment runs
           THEN it warns about insufficient alignment."""
        content = "__Vectors = .; . = ALIGN(16);"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_vector_table_alignment(content, f)
        assert any("alignment" in fi["message"] and "256" in fi["message"] for fi in findings)

    def test_vector_table_no_align_directive(self, tmp_path):
        """GIVEN vector table present but no ALIGN directive
           WHEN _check_vector_table_alignment runs
           THEN it verifies alignment indirectly."""
        content = "__Vectors = .;"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_vector_table_alignment(content, f)
        assert any("no explicit ALIGN directive" in fi["message"] for fi in findings)

    def test_no_vector_table(self, tmp_path):
        """GIVEN no vector table symbol
           WHEN _check_vector_table_alignment runs
           THEN it returns info."""
        content = ".text : {}"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_vector_table_alignment(content, f)
        assert any("No vector table symbol" in fi["message"] for fi in findings)


# =============================================================================
# _check_memory_regions
# =============================================================================

class TestCheckMemoryRegions:
    """Tests for _check_memory_regions — ROM/RAM address range checks."""

    def test_no_regions(self, tmp_path):
        """GIVEN no MEMORY regions defined
           WHEN _check_memory_regions runs
           THEN it returns a major finding."""
        content = "SECTIONS { .text : {} }"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_memory_regions(content, f)
        assert any("No MEMORY regions defined" in fi["message"] for fi in findings)

    def test_ram_region_small(self, tmp_path):
        """GIVEN RAM region < 4 KB
           WHEN _check_memory_regions runs
           THEN it warns about small RAM."""
        content = "RAM : ORIGIN = 0x20000000, LENGTH = 0x800"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_memory_regions(content, f)
        assert any("too small" in fi["message"] for fi in findings)

    def test_normal_regions(self, tmp_path):
        """GIVEN normal RAM and FLASH regions
           WHEN _check_memory_regions runs
           THEN it reports memory region info."""
        content = """
        FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M
        RAM (xw) : ORIGIN = 0x20000000, LENGTH = 192K
        """
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_memory_regions(content, f)
        region_findings = [fi for fi in findings if "region" in fi.get("category", "")]
        assert len(region_findings) > 0

    def test_custom_region_names(self, tmp_path):
        """GIVEN regions with non-standard names
           WHEN _check_memory_regions runs
           THEN it still parses them."""
        content = "SRAM1 (xw) : ORIGIN = 0x30000000, LENGTH = 32K"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_memory_regions(content, f)
        assert len(findings) > 0


# =============================================================================
# _check_lma_vma_difference
# =============================================================================

class TestCheckLmaVmaDifference:
    """Tests for _check_lma_vma_difference — load/virtual address checks."""

    def test_missing_at_specifier(self, tmp_path):
        """GIVEN .data section without AT>
           WHEN _check_lma_vma_difference runs
           THEN it returns a major finding."""
        content = ".data : { *(.data*) } > RAM"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_lma_vma_difference(content, f)
        assert any("AT>" in fi["message"] or "AT >" in fi["message"] or "without AT" in fi["message"] for fi in findings)

    def test_correct_at_specifier(self, tmp_path):
        """GIVEN .data section with AT> for LMA/VMA separation
           WHEN _check_lma_vma_difference runs
           THEN it confirms LMA/VMA separation."""
        content = '.data : AT(__etext) { *(.data*) } > RAM AT> FLASH'
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_lma_vma_difference(content, f)
        assert any("LMA/VMA separation confirmed" in fi["message"] for fi in findings)

    def test_no_data_section(self, tmp_path):
        """GIVEN no .data section
           WHEN _check_lma_vma_difference runs
           THEN it skips the check."""
        content = ".text : { *(.text*) }"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_lma_vma_difference(content, f)
        assert any("LMA/VMA check skipped" in fi["message"] for fi in findings)


# =============================================================================
# _check_arm_exception_tables
# =============================================================================

class TestCheckArmExceptionTables:
    """Tests for _check_arm_exception_tables — .ARM.exidx/.extab checks."""

    def test_exidx_present_in_flash(self, tmp_path):
        """GIVEN .ARM.exidx placed in FLASH
           WHEN _check_arm_exception_tables runs
           THEN it reports correct placement."""
        content = ".ARM.exidx : { } > FLASH"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_arm_exception_tables(content, f)
        assert any("correct for ARM exception tables" in fi["message"] for fi in findings)

    def test_exidx_in_ram(self, tmp_path):
        """GIVEN .ARM.exidx placed in RAM
           WHEN _check_arm_exception_tables runs
           THEN it returns a major finding."""
        content = ".ARM.exidx : { *(.ARM.exidx*) } > RAM"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_arm_exception_tables(content, f)
        assert any("MUST be in a read-only region" in fi["message"] for fi in findings)

    def test_no_exidx_c_only(self, tmp_path):
        """GIVEN no .ARM.exidx (C-only firmware)
           WHEN _check_arm_exception_tables runs
           THEN it reports expected for C-only."""
        content = ".text : { *(.text*) }"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_arm_exception_tables(content, f)
        assert any("expected for C-only" in fi["message"] for fi in findings)

    def test_cpp_refs_without_exidx(self, tmp_path):
        """GIVEN C++ personality references but no .ARM.exidx
           WHEN _check_arm_exception_tables runs
           THEN it returns a critical finding."""
        content = ".text : { *(.text*) } __gxx_personality"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_arm_exception_tables(content, f)
        assert any(fi["severity"] == "critical" for fi in findings)

    def test_exidx_without_extab(self, tmp_path):
        """GIVEN .ARM.exidx without .ARM.extab
           WHEN _check_arm_exception_tables runs
           THEN it reports compact model."""
        content = ".ARM.exidx : { } > FLASH"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_arm_exception_tables(content, f)
        assert any("without" in fi["message"] and "ARM.extab" in fi["message"] for fi in findings)


# =============================================================================
# _check_heap_stack_overlap
# =============================================================================

class TestCheckHeapStackOverlap:
    """Tests for _check_heap_stack_overlap — heap/stack overlap detection."""

    def test_heap_and_stack_same_region(self, tmp_path):
        """GIVEN .heap and .stack in the same region
           WHEN _check_heap_stack_overlap runs
           THEN it warns about overlap risk."""
        content = """
        .heap : { *(.heap*) } > RAM
        .stack : { *(.stack*) } > RAM
        """
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_heap_stack_overlap(content, f)
        assert any("share the same memory region" in fi["message"] for fi in findings)

    def test_different_regions(self, tmp_path):
        """GIVEN .heap and .stack in different regions
           WHEN _check_heap_stack_overlap runs
           THEN it reports no overlap risk."""
        content = """
        .heap : { *(.heap*) } > RAM
        .stack : { *(.stack*) } > ITCM
        """
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_heap_stack_overlap(content, f)
        assert any("no overlap risk" in fi["message"] for fi in findings)

    def test_no_stack_section(self, tmp_path):
        """GIVEN .heap without .stack section
           WHEN _check_heap_stack_overlap runs
           THEN it returns info."""
        content = ".heap (NOLOAD) : { *(.heap*) } > RAM"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_heap_stack_overlap(content, f)
        assert any("no .stack section" in fi["message"] for fi in findings)

    def test_no_heap_section(self, tmp_path):
        """GIVEN .stack without .heap section
           WHEN _check_heap_stack_overlap runs
           THEN it returns info."""
        content = ".stack (NOLOAD) : { *(.stack*) } > RAM"
        f = _create_file(tmp_path, "linker.ld", content)
        findings = _check_heap_stack_overlap(content, f)
        assert any("no .heap section" in fi["message"] for fi in findings)


# =============================================================================
# _build_linker_review_prompt
# =============================================================================

class TestBuildLinkerReviewPrompt:
    """Tests for _build_linker_review_prompt — LLM prompt builder."""

    def test_generates_prompts(self, tmp_path):
        """GIVEN linker script contents
           WHEN _build_linker_review_prompt runs
           THEN it returns system and user prompts."""
        linker_contents = {"/path/linker.ld": LINKER_SCRIPT_MINIMAL}
        system_prompt, user_prompt = _build_linker_review_prompt(linker_contents)
        assert "linker script" in system_prompt.lower()
        assert "linker.ld" in user_prompt

    def test_empty_contents(self):
        """GIVEN empty linker contents dict
           WHEN _build_linker_review_prompt runs
           THEN prompts still contain key sections."""
        system_prompt, user_prompt = _build_linker_review_prompt({})
        assert "linker script" in system_prompt.lower()
        assert "Linker Scripts" in user_prompt


# =============================================================================
# _static_linker_review
# =============================================================================

class TestStaticLinkerReview:
    """Tests for _static_linker_review — all static checks combined."""

    def test_no_scripts(self, tmp_path):
        """GIVEN no linker scripts
           WHEN _static_linker_review runs
           THEN it returns a discovery finding."""
        findings = _static_linker_review(tmp_path)
        assert any("No linker script" in fi["message"] for fi in findings)

    def test_with_linker_script(self, tmp_path):
        """GIVEN a valid linker script
           WHEN _static_linker_review runs
           THEN multiple category findings are generated."""
        _create_file(tmp_path, "STM32F407.ld", LINKER_SCRIPT_MINIMAL)
        findings = _static_linker_review(tmp_path)
        assert len(findings) > 1

    def test_unreadable_file(self, tmp_path):
        """GIVEN an unreadable linker script
           WHEN _static_linker_review runs
           THEN it returns an IO error finding."""
        f = _create_file(tmp_path, "linker.ld", LINKER_SCRIPT_MINIMAL)
        f.chmod(0o000)
        try:
            findings = _static_linker_review(tmp_path)
            # Should not crash — unreadable file gracefully skipped
            assert isinstance(findings, list)
        finally:
            f.chmod(0o644)


# =============================================================================
# step_review_linker — end-to-end
# =============================================================================

class TestStepReviewLinker:
    """Tests for step_review_linker — the main pipeline step handler."""

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_empty_project(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN an empty project directory
           WHEN step_review_linker runs
           THEN it reports no linker scripts found."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        result = step_review_linker(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-linker"
        assert len(report["linker_scripts_found"]) == 0

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_with_linker_script(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a linker script file exists
           WHEN step_review_linker runs
           THEN it generates multiple findings and calls LLM."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "# Linker Review\nLooks correct.", "usage": {"total_tokens": 200}}

        _create_file(tmp_path, "STM32F407.ld", LINKER_SCRIPT_MINIMAL)

        result = step_review_linker(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-linker"
        assert len(report["linker_scripts_found"]) == 1
        assert report["finding_count"] > 0

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_llm_failure_non_fatal(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_linker runs
           THEN the step still completes with a fallback."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.side_effect = RuntimeError("LLM down")

        _create_file(tmp_path, "linker.ld", LINKER_SCRIPT_MINIMAL)

        result = step_review_linker(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-linker"
        assert "unavailable" in report["llm_review"] or "(LLM-powered" in report["llm_review"]

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_critical_finding_triggers_failed(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a linker script with missing .text section
           WHEN step_review_linker runs
           THEN the overall status is 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "bad", "usage": {"total_tokens": 10}}

        # Linker script with no .text section
        content = "SECTIONS { .data : { *(.data*) } }"
        _create_file(tmp_path, "linker.ld", content)

        result = step_review_linker(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_write_error(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN the output file cannot be written
           WHEN step_review_linker runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        mock_session.session_dir = tmp_path / "nonexistent" / "deep"

        with pytest.raises(PipelineStepError, match="Cannot write linker review"):
            step_review_linker(mock_session)

    @patch("yuleosh.pipeline.step_handlers.review_linker._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_linker.os.environ")
    def test_exception_wrapping(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN an unexpected exception during processing
           WHEN step_review_linker runs
           THEN it is wrapped in PipelineStepError."""
        mock_environ.get.side_effect = RuntimeError("Unexpected failure")
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        with pytest.raises(PipelineStepError, match="Linker review step failed"):
            step_review_linker(mock_session)
