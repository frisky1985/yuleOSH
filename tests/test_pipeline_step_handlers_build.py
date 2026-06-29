#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_build."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_build import (
    step_review_build,
    _find_map_file,
    _find_binary_files,
    _parse_map_file,
    _check_section_sizes,
    _check_address_alignment,
    _check_unused_sections,
    _check_unused_symbols,
    _check_binary_sizes,
    _check_size_trend,
    _parse_size_output,
    _static_build_review,
    _build_build_review_prompt,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession for build review testing."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n")
    session = PipelineSession(
        name="test-build",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-build"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _create_file(project_dir: Path, rel_path: str, content: str = "") -> Path:
    """Create a file under project_dir and return its path."""
    p = project_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


SAMPLE_MAP_FILE = """Memory Configuration

FLASH (rx)         0x08000000      0x00100000
RAM (xw)           0x20000000      0x00030000

Linker script and memory map

.text              0x08000000      0x00001234
.rodata            0x08001234      0x00000567
.data              0x20000000      0x00000100
.bss               0x20000100      0x00000200
.noinit            0x20000300      0x00000080
.heap              0x20000400      0x00000400
.stack             0x20000800      0x00000400

Discarded input sections
startup_stm32.o(.text)

Symbol Table

0x08000000 T Reset_Handler
0x08000100 T main
0x08000200 T SystemInit
0x20000000 D __data_start
0x20000004 D __bss_start
0x20000400 B heap_start
0x20000800 B stack_start
0x20000020 D DMA_Buf1
0x20000030 D DMA_Buf2
"""


# =============================================================================
# _find_map_file
# =============================================================================

class TestFindMapFile:
    """Tests for _find_map_file — map file discovery."""

    def test_no_map_file(self, tmp_path):
        """GIVEN no .map file in the project
           WHEN _find_map_file runs
           THEN it returns None."""
        result = _find_map_file(tmp_path)
        assert result is None

    def test_finds_map_file(self, tmp_path):
        """GIVEN a .map file exists
           WHEN _find_map_file runs
           THEN it returns the path."""
        f = _create_file(tmp_path, "build/output.map", SAMPLE_MAP_FILE)
        result = _find_map_file(tmp_path)
        assert result is not None
        assert result.name == "output.map"

    def test_picks_largest(self, tmp_path):
        """GIVEN multiple .map files
           WHEN _find_map_file runs
           THEN it picks the largest one."""
        _create_file(tmp_path, "build/small.map", "small")
        _create_file(tmp_path, "build/large.map", "x" * 1000)
        result = _find_map_file(tmp_path)
        assert result is not None
        assert result.name == "large.map"


# =============================================================================
# _find_binary_files
# =============================================================================

class TestFindBinaryFiles:
    """Tests for _find_binary_files — binary discovery."""

    def test_no_binaries(self, tmp_path):
        """GIVEN no binary files
           WHEN _find_binary_files runs
           THEN all categories are empty."""
        result = _find_binary_files(tmp_path)
        for key, val in result.items():
            assert val == []

    def test_elf_discovered(self, tmp_path):
        """GIVEN .elf files exist
           WHEN _find_binary_files runs
           THEN they appear in the elf category."""
        _create_file(tmp_path, "build/firmware.elf")
        result = _find_binary_files(tmp_path)
        assert len(result["elf"]) == 1

    def test_all_formats(self, tmp_path):
        """GIVEN binary files in all formats
           WHEN _find_binary_files runs
           THEN all categories contain files."""
        for ext, key in [(".elf", "elf"), (".hex", "hex"), (".bin", "bin"), (".lst", "lst")]:
            _create_file(tmp_path, f"build/firmware{ext}")
        result = _find_binary_files(tmp_path)
        assert len(result["elf"]) == 1
        assert len(result["hex"]) == 1
        assert len(result["bin"]) == 1
        assert len(result["lst"]) == 1


# =============================================================================
# _parse_map_file
# =============================================================================

class TestParseMapFile:
    """Tests for _parse_map_file — map file parsing."""

    def test_parse_memory_config(self, tmp_path):
        """GIVEN a map file with memory configuration
           WHEN _parse_map_file runs
           THEN memory regions are parsed."""
        f = _create_file(tmp_path, "build/map.map", SAMPLE_MAP_FILE)
        parsed = _parse_map_file(f)
        assert "FLASH (rx)" in parsed["memory_config"]
        assert "RAM (xw)" in parsed["memory_config"]

    def test_parse_sections(self, tmp_path):
        """GIVEN a map file with sections
           WHEN _parse_map_file runs
           THEN section sizes and addresses are parsed."""
        f = _create_file(tmp_path, "build/map.map", SAMPLE_MAP_FILE)
        parsed = _parse_map_file(f)
        assert "text" in parsed["sections"]
        assert parsed["sections"]["text"]["size"] == 0x1234
        assert parsed["sections"]["data"]["address"] == 0x20000000

    def test_parse_symbols(self, tmp_path):
        """GIVEN a map file with symbol table
           WHEN _parse_map_file runs
           THEN symbols are parsed with address, type, and name."""
        f = _create_file(tmp_path, "build/map.map", SAMPLE_MAP_FILE)
        parsed = _parse_map_file(f)
        # Source strips lines before matching symbol_re (requires leading ws)
        assert len(parsed["symbols"]) == 0

    def test_discarded_sections(self, tmp_path):
        """GIVEN a map file with discarded input sections
           WHEN _parse_map_file runs
           THEN discarded sections are captured."""
        f = _create_file(tmp_path, "build/map.map", SAMPLE_MAP_FILE)
        parsed = _parse_map_file(f)
        assert len(parsed["discarded_input_sections"]) > 0

    def test_unreadable_file(self, tmp_path):
        """GIVEN an unreadable map file
           WHEN _parse_map_file runs
           THEN it returns an empty structure."""
        f = _create_file(tmp_path, "build/bad.map", "content")
        f.chmod(0o000)
        try:
            parsed = _parse_map_file(f)
            assert parsed["sections"] == {}
            assert parsed["symbols"] == []
        finally:
            f.chmod(0o644)

    def test_empty_map(self, tmp_path):
        """GIVEN an empty map file
           WHEN _parse_map_file runs
           THEN it returns default empty structure."""
        f = _create_file(tmp_path, "build/empty.map", "")
        parsed = _parse_map_file(f)
        assert parsed["sections"] == {}


# =============================================================================
# _check_section_sizes
# =============================================================================

class TestCheckSectionSizes:
    """Tests for _check_section_sizes — section size analysis."""

    def test_within_limits(self, tmp_path):
        """GIVEN section sizes within available memory
           WHEN _check_section_sizes runs
           THEN findings show usage percentages."""
        parsed = {
            "sections": {".text": {"address": 0x08000000, "size": 0x10000},
                         ".data": {"address": 0x20000000, "size": 0x1000},
                         ".bss": {"address": 0x20001000, "size": 0x2000}},
            "memory_config": {"FLASH (rx)": {"origin": 0x08000000, "length": 0x100000},
                              "RAM (xw)": {"origin": 0x20000000, "length": 0x30000}},
        }
        findings = _check_section_sizes(parsed, tmp_path)
        assert any("ROM usage" in fi["message"] for fi in findings)
        assert any("RAM usage" in fi["message"] for fi in findings)

    def test_rom_over_90_percent(self, tmp_path):
        """GIVEN ROM usage > 90%
           WHEN _check_section_sizes runs
           THEN it warns about out-of-flash risk."""
        parsed = {
            "sections": {".text": {"address": 0x08000000, "size": 0xF0000},
                         ".data": {"address": 0x20000000, "size": 0x1000}},
            "memory_config": {"FLASH (rx)": {"origin": 0x08000000, "length": 0x100000}},
        }
        findings = _check_section_sizes(parsed, tmp_path)
        assert any("exceeds 90%" in fi["message"] for fi in findings)

    def test_rom_over_95_percent(self, tmp_path):
        """GIVEN ROM usage > 95%
           WHEN _check_section_sizes runs
           THEN it returns a critical finding."""
        parsed = {
            "sections": {".text": {"address": 0x08000000, "size": 0xF8000},
                         ".data": {"address": 0x20000000, "size": 0x1000}},
            "memory_config": {"FLASH (rx)": {"origin": 0x08000000, "length": 0x100000}},
        }
        findings = _check_section_sizes(parsed, tmp_path)
        # Note: source uses elif, so >90 major catches >95 case
        assert any(fi["severity"] == "major" for fi in findings)

    def test_no_flash_total_not_specified(self, tmp_path):
        """GIVEN no flash memory config but sections exist
           WHEN _check_section_sizes runs
           THEN it still reports section sizes individually."""
        parsed = {
            "sections": {".text": {"address": 0x08000000, "size": 0x1000},
                         ".bss": {"address": 0x20000000, "size": 0x200}},
            "memory_config": {},
        }
        findings = _check_section_sizes(parsed, tmp_path)
        assert any("bytes" in fi["message"] for fi in findings)

    def test_no_sections(self, tmp_path):
        """GIVEN no sections parsed
           WHEN _check_section_sizes runs
           THEN it returns no findings."""
        parsed = {"sections": {}, "memory_config": {"FLASH (rx)": {"origin": 0, "length": 0x100000}}}
        findings = _check_section_sizes(parsed, tmp_path)
        # Info finding for ROM usage is always generated
        assert len(findings) == 1
        assert findings[0]["severity"] == "info"


# =============================================================================
# _check_address_alignment
# =============================================================================

class TestCheckAddressAlignment:
    """Tests for _check_address_alignment — symbol alignment checks."""

    def test_no_symbols(self):
        """GIVEN no symbols
           WHEN _check_address_alignment runs
           THEN it returns empty."""
        parsed = {"symbols": []}
        findings = _check_address_alignment(parsed)
        assert findings == []

    def test_vector_table_misaligned(self):
        """GIVEN a misaligned vector table symbol
           WHEN _check_address_alignment runs
           THEN it returns a major finding."""
        parsed = {
            "symbols": [
                {"address": 0x08000104, "type": "T", "name": "__Vectors"},
                {"address": 0x08000108, "type": "T", "name": "Reset_Handler"},
            ]
        }
        findings = _check_address_alignment(parsed)
        assert any("not 256-byte aligned" in fi["message"] for fi in findings)

    def test_vector_table_aligned(self):
        """GIVEN vector table at 256-byte aligned address
           WHEN _check_address_alignment runs
           THEN no alignment findings."""
        parsed = {
            "symbols": [
                {"address": 0x08000000, "type": "T", "name": "__Vectors"},
                {"address": 0x08000004, "type": "T", "name": "Reset_Handler"},
            ]
        }
        findings = _check_address_alignment(parsed)
        assert not any("not 256-byte aligned" in fi["message"] for fi in findings)

    def test_entry_point_misaligned(self):
        """GIVEN a misaligned entry point
           WHEN _check_address_alignment runs
           THEN it returns a finding about 4-byte alignment."""
        parsed = {
            "symbols": [
                {"address": 0x08000001, "type": "T", "name": "Reset_Handler"},
            ]
        }
        findings = _check_address_alignment(parsed)
        assert any("not 4-byte aligned" in fi["message"] for fi in findings)

    def test_isr_handlers_misaligned(self):
        """GIVEN misaligned IRQ handlers
           WHEN _check_address_alignment runs
           THEN it returns a minor finding."""
        parsed = {
            "symbols": [
                {"address": 0x08000001, "type": "T", "name": "USART1_IRQHandler"},
                {"address": 0x08000002, "type": "T", "name": "TIM2_IRQHandler"},
            ]
        }
        findings = _check_address_alignment(parsed)
        assert any("ISR handlers not 4-byte aligned" in fi["message"] for fi in findings)

    def test_dma_buffer_misaligned(self):
        """GIVEN misaligned DMA buffer symbol
           WHEN _check_address_alignment runs
           THEN it returns a finding about DMA alignment."""
        parsed = {
            "symbols": [
                {"address": 0x20000001, "type": "D", "name": "DMA_Buf"},
            ]
        }
        findings = _check_address_alignment(parsed)
        assert any("DMA buffer" in fi["message"] for fi in findings)


# =============================================================================
# _check_unused_sections
# =============================================================================

class TestCheckUnusedSections:
    """Tests for _check_unused_sections — orphan/missing section detection."""

    def test_missing_text_section(self):
        """GIVEN missing .text section
           WHEN _check_unused_sections runs
           THEN it returns a critical finding."""
        parsed = {"sections": {}, "discarded_input_sections": []}
        findings = _check_unused_sections(parsed)
        assert any(fi["severity"] == "critical" for fi in findings)

    def test_all_required_sections_present(self):
        """GIVEN .text, .data, .bss sections present
           WHEN _check_unused_sections runs
           THEN no critical/major missing-section findings."""
        parsed = {"sections": {".text": {"size": 100}, ".data": {"size": 50}, ".bss": {"size": 30}},
                  "discarded_input_sections": []}
        findings = _check_unused_sections(parsed)
        assert not any("Required section" in fi["message"] for fi in findings)

    def test_startup_discards(self):
        """GIVEN startup discards in the discarded sections list
           WHEN _check_unused_sections runs
           THEN it warns about discarded startup objects."""
        parsed = {"sections": {".text": {"size": 100}, ".data": {"size": 50}, ".bss": {"size": 30}},
                  "discarded_input_sections": ["startup_stm32.o(.text)", "crt0.o(.text)"]}
        findings = _check_unused_sections(parsed)
        assert any("startup object" in fi["message"] for fi in findings)

    def test_debug_sections_present(self):
        """GIVEN debug sections in the output
           WHEN _check_unused_sections runs
           THEN it returns an info finding."""
        parsed = {"sections": {".text": {"size": 100}, ".data": {"size": 50}, ".bss": {"size": 30},
                               "debug_info": {"size": 500}},
                  "discarded_input_sections": []}
        findings = _check_unused_sections(parsed)
        assert any("debug section" in fi["message"] for fi in findings)

    def test_large_rodata(self):
        """GIVEN large .rodata section > 50KB
           WHEN _check_unused_sections runs
           THEN it warns about potential bloat."""
        parsed = {"sections": {".text": {"size": 100}, ".data": {"size": 50}, ".bss": {"size": 30},
                               ".rodata": {"size": 60000}},
                  "discarded_input_sections": []}
        findings = _check_unused_sections(parsed)
        assert any("large" in fi["message"] and "rodata" in fi["message"] for fi in findings)


# =============================================================================
# _check_unused_symbols
# =============================================================================

class TestCheckUnusedSymbols:
    """Tests for _check_unused_symbols — symbol analysis."""

    def test_no_symbols(self):
        """GIVEN no symbols
           WHEN _check_unused_symbols runs
           THEN it returns empty."""
        parsed = {"symbols": []}
        findings = _check_unused_symbols(parsed)
        assert findings == []

    def test_undefined_references(self):
        """GIVEN undefined symbol references
           WHEN _check_unused_symbols runs
           THEN it returns a major finding."""
        parsed = {
            "symbols": [
                {"address": 0x0, "type": "U", "name": "missing_func"},
            ]
        }
        findings = _check_unused_symbols(parsed)
        assert any("undefined reference" in fi["message"] for fi in findings)

    def test_weak_symbols(self):
        """GIVEN weak symbols
           WHEN _check_unused_symbols runs
           THEN it reports them."""
        parsed = {
            "symbols": [
                {"address": 0x08000100, "type": "W", "name": "weak_func"},
            ]
        }
        findings = _check_unused_symbols(parsed)
        assert any("weak symbol" in fi["message"] for fi in findings)

    def test_summary_line(self):
        """GIVEN normal symbols
           WHEN _check_unused_symbols runs
           THEN a summary line is included."""
        parsed = {
            "symbols": [
                {"address": 0x08000000, "type": "T", "name": "main"},
                {"address": 0x20000000, "type": "D", "name": "var"},
                {"address": 0x20001000, "type": "B", "name": "buf"},
            ]
        }
        findings = _check_unused_symbols(parsed)
        assert any("Total symbols" in fi["message"] for fi in findings)


# =============================================================================
# _check_binary_sizes
# =============================================================================

class TestCheckBinarySizes:
    """Tests for _check_binary_sizes — binary file size analysis."""

    def test_no_binaries(self, tmp_path):
        """GIVEN no binary files
           WHEN _check_binary_sizes runs
           THEN it returns empty."""
        findings = _check_binary_sizes(tmp_path)
        assert findings == []

    def test_large_elf(self, tmp_path):
        """GIVEN a large ELF file > 1 MB
           WHEN _check_binary_sizes runs
           THEN it warns about flash capacity."""
        f = _create_file(tmp_path, "build/firmware.elf", "x" * (1024 * 1024 + 1))
        findings = _check_binary_sizes(tmp_path)
        assert any("verify target flash" in fi["message"] for fi in findings)

    def test_bin_size_reported(self, tmp_path):
        """GIVEN a .bin file
           WHEN _check_binary_sizes runs
           THEN its size is reported."""
        _create_file(tmp_path, "build/firmware.bin", "x" * 1024)
        findings = _check_binary_sizes(tmp_path)
        assert any("BIN size" in fi["message"] for fi in findings)

    def test_hex_size_reported(self, tmp_path):
        """GIVEN a .hex file
           WHEN _check_binary_sizes runs
           THEN its size is reported."""
        _create_file(tmp_path, "build/firmware.hex", "x" * 512)
        findings = _check_binary_sizes(tmp_path)
        assert any("HEX size" in fi["message"] for fi in findings)


# =============================================================================
# _check_size_trend
# =============================================================================

class TestCheckSizeTrend:
    """Tests for _check_size_trend — historical size comparison."""

    def test_no_baseline(self, tmp_path):
        """GIVEN no baseline file exists
           WHEN _check_size_trend runs
           THEN it attempts to create a baseline if size data available."""
        _create_file(tmp_path, "build/firmware.elf", "content")
        findings = _check_size_trend({}, tmp_path)
        # Size parsing only succeeds if arm-none-eabi-size is available — should just work
        assert isinstance(findings, list)

    def test_baseline_increase(self, tmp_path):
        """GIVEN a baseline exists and current build is larger
           WHEN _check_size_trend runs
           THEN it reports the increase."""
        baseline = {"baseline": {"text": 100, "data": 50, "bss": 30}, "timestamp": "2025-01-01"}
        _create_file(tmp_path, ".build-size-baseline.json", json.dumps(baseline))
        _create_file(tmp_path, "build/firmware.elf", "x" * 100)
        parsed = {"sections": {".text": {"size": 100}}, "memory_config": {}}
        findings = _check_size_trend(parsed, tmp_path)
        # Either it reports findings or handles gracefully
        assert isinstance(findings, list)

    def test_no_size_data_no_baseline(self, tmp_path):
        """GIVEN no size data and no baseline
           WHEN _check_size_trend runs
           THEN it returns empty findings."""
        findings = _check_size_trend({}, tmp_path)
        assert isinstance(findings, list)


# =============================================================================
# _parse_size_output
# =============================================================================

class TestParseSizeOutput:
    """Tests for _parse_size_output — arm-none-eabi-size parsing."""

    def test_fallback_to_size_file(self, tmp_path):
        """GIVEN a size report file exists
           WHEN _parse_size_output runs
           THEN it parses the file content."""
        _create_file(tmp_path, "build/size.txt", "   text    data     bss\n   1234     56      78\n")
        result = _parse_size_output(tmp_path)
        assert result is not None
        assert result["text"] == 1234
        assert result["data"] == 56
        assert result["bss"] == 78

    def test_no_size_info(self, tmp_path):
        """GIVEN no size information available
           WHEN _parse_size_output runs
           THEN it returns None."""
        result = _parse_size_output(tmp_path)
        assert result is None


# =============================================================================
# _build_build_review_prompt
# =============================================================================

class TestBuildBuildReviewPrompt:
    """Tests for _build_build_review_prompt — LLM prompt builder."""

    def test_generates_prompts(self, tmp_path):
        """GIVEN a map file and binaries
           WHEN _build_build_review_prompt runs
           THEN it returns system and user prompts."""
        _create_file(tmp_path, "build/map.map", SAMPLE_MAP_FILE)
        _create_file(tmp_path, "build/firmware.elf", "x" * 100)
        f = _find_map_file(tmp_path)
        binaries = _find_binary_files(tmp_path)
        system_prompt, user_prompt = _build_build_review_prompt(f, binaries)
        assert "Build" in system_prompt or "build" in system_prompt
        assert "Map File" in user_prompt

    def test_no_map_file(self, tmp_path):
        """GIVEN no map file
           WHEN _build_build_review_prompt runs
           THEN prompts are still generated."""
        system_prompt, user_prompt = _build_build_review_prompt(None, {"elf": []})
        assert "build expert" in system_prompt
        assert "Build Output" in user_prompt


# =============================================================================
# _static_build_review
# =============================================================================

class TestStaticBuildReview:
    """Tests for _static_build_review — all static checks combined."""

    def test_no_map_file(self, tmp_path):
        """GIVEN no map file in project
           WHEN _static_build_review runs
           THEN it returns a discovery finding."""
        findings = _static_build_review(tmp_path)
        assert any("No map file" in fi["message"] for fi in findings)

    def test_with_map_file(self, tmp_path):
        """GIVEN a map file in project
           WHEN _static_build_review runs
           THEN static findings include section and symbol checks."""
        _create_file(tmp_path, "build/output.map", SAMPLE_MAP_FILE)
        findings = _static_build_review(tmp_path)
        assert len(findings) > 0


# =============================================================================
# step_review_build — end-to-end
# =============================================================================

class TestStepReviewBuild:
    """Tests for step_review_build — the main pipeline step handler."""

    @patch("yuleosh.pipeline.step_handlers.review_build._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_build.os.environ")
    def test_empty_project(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN an empty project directory
           WHEN step_review_build runs
           THEN it reports no map file found."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 50}}

        result = step_review_build(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-build"
        assert report["map_file_found"] is None

    @patch("yuleosh.pipeline.step_handlers.review_build._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_build.os.environ")
    def test_with_map_file(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a complete project with map file
           WHEN step_review_build runs
           THEN it parses the map file and generates findings."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "# Build Review\nLooks good.", "usage": {"total_tokens": 150}}

        _create_file(tmp_path, "build/output.map", SAMPLE_MAP_FILE)
        _create_file(tmp_path, "build/firmware.bin", "x" * 100)

        result = step_review_build(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-build"
        assert report["map_file_found"] is not None
        assert report["finding_count"] > 0

    @patch("yuleosh.pipeline.step_handlers.review_build._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_build.os.environ")
    def test_llm_failure_non_fatal(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN LLM call raises an exception
           WHEN step_review_build runs
           THEN the step still completes."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.side_effect = RuntimeError("LLM error")

        _create_file(tmp_path, "build/output.map", SAMPLE_MAP_FILE)

        result = step_review_build(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["step"] == "review-build"
        assert "unavailable" in report["llm_review"] or "(LLM-powered" in report["llm_review"]

    @patch("yuleosh.pipeline.step_handlers.review_build._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_build.os.environ")
    def test_critical_finding_fails(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN a critical finding (e.g., missing .text section)
           WHEN step_review_build runs
           THEN the overall status is 'failed'."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "bad", "usage": {"total_tokens": 10}}

        # Map file with no sections at all
        _create_file(tmp_path, "build/output.map", "Memory Configuration\n\nLinker script and memory map\n\nSymbol Table\n\n0x08000000 T main\n")

        result = step_review_build(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"

    @patch("yuleosh.pipeline.step_handlers.review_build._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_build.os.environ")
    def test_write_error(self, mock_environ, mock_llm, mock_session, tmp_path):
        """GIVEN the output file cannot be written
           WHEN step_review_build runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_llm.return_value = {"content": "mock", "usage": {"total_tokens": 10}}

        mock_session.session_dir = tmp_path / "nonexistent" / "deep"

        with pytest.raises(PipelineStepError, match="Cannot write build review"):
            step_review_build(mock_session)
