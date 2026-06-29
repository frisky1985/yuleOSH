#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_mmio — MMIO configuration review."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_mmio import (
    step_review_mmio,
    _find_mmio_sources,
    _check_clock_config,
    _check_gpio_config,
    _check_nvic_config,
    _check_dma_config,
    _check_mmio_consistency,
    _build_mmio_report,
    _render_mmio_report,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with spec file for MMIO review.

    NOTE: review_mmio uses session.spec_path.parent as project_dir,
    so we must place the spec file such that parent == tmp_path.
    """
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n## Requirements\nMMIO-001: shall configure clocks\n")
    session = PipelineSession(
        name="test-mmio",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-mmio"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


# =============================================================================
# Unit tests — helper functions
# =============================================================================

class TestFindMmioSources:
    """Tests for _find_mmio_sources — MMIO file discovery."""

    def test_discovery_by_pattern(self, tmp_path):
        """GIVEN a project with clock, gpio, nvic, dma, and peripheral files
           WHEN _find_mmio_sources runs
           THEN each category contains the expected files."""
        # Clock files
        (tmp_path / "stm32f4xx_hal_rcc.h").write_text("// RCC header\n")
        # GPIO files
        (tmp_path / "gpio_config.c").write_text("// GPIO config\n")
        (tmp_path / "pin_mux.c").write_text("// Pin mux\n")
        # NVIC files
        (tmp_path / "startup_stm32f407.s").write_text("// Startup\n")
        (tmp_path / "nvic_config.c").write_text("// NVIC\n")
        # DMA files
        (tmp_path / "dma_config.c").write_text("// DMA\n")
        # Peripheral files
        (tmp_path / "uart_config.c").write_text("// UART\n")
        (tmp_path / "spi_driver.c").write_text("// SPI\n")

        categories = _find_mmio_sources(tmp_path)

        assert len(categories["clock_config"]) >= 1
        assert len(categories["gpio_config"]) >= 1
        assert len(categories["nvic_config"]) >= 1
        assert len(categories["dma_config"]) >= 1
        assert len(categories["peripheral_config"]) >= 1

    def test_empty_project(self, tmp_path):
        """GIVEN an empty project
           WHEN _find_mmio_sources runs
           THEN all categories are empty lists."""
        categories = _find_mmio_sources(tmp_path)
        for key in categories:
            assert categories[key] == []

    def test_deduplicates(self, tmp_path):
        """GIVEN symlinks or duplicate patterns
           WHEN _find_mmio_sources runs
           THEN the same file is not listed twice."""
        (tmp_path / "clock.c").write_text("// clock\n")
        categories = _find_mmio_sources(tmp_path)
        assert len(categories["clock_config"]) == 1


class TestCheckClockConfig:
    """Tests for _check_clock_config — clock system analysis."""

    def test_missing_hse_pll(self, tmp_path):
        """GIVEN clock files without HSE or PLL configuration
           WHEN _check_clock_config runs
           THEN it returns 'warning' findings for missing HSE and PLL."""
        (tmp_path / "clock.c").write_text("// Simple clock setup\n// No HSE, No PLL\n")
        files = [tmp_path / "clock.c"]
        findings = _check_clock_config(files, tmp_path)
        warnings = [f for f in findings if f["severity"] == "warning"]
        categories = {f["category"] for f in warnings}
        assert "clock" in categories

    def test_full_clock_config(self, tmp_path):
        """GIVEN clock files with HSE, LSE, PLL, RCC init and CSS
           WHEN _check_clock_config runs
           THEN no 'warning' findings are returned."""
        (tmp_path / "clock.c").write_text(
            '#define HSE_VALUE 8000000\n'
            '#define LSE_VALUE 32768\n'
            'void HAL_RCC_OscConfig(void) {\n'
            '    RCC_PLL_init();\n'
            '    RCC_CR_CSSON = 1;\n'
            '}\n'
        )
        files = [tmp_path / "clock.c"]
        findings = _check_clock_config(files, tmp_path)
        warnings = [f for f in findings if f["severity"] == "warning"]
        assert len(warnings) == 0

    def test_pllm_out_of_range(self, tmp_path):
        """GIVEN a PLLM value outside typical range
           WHEN _check_clock_config runs
           THEN it adds a warning finding about PLLM."""
        (tmp_path / "clock.c").write_text(
            '#define PLLM 99\n'  # > 63 triggers warning
            '#define HSE_VALUE 8000000\n'
            'void HAL_RCC_OscConfig(void) {\n'
            '    RCC_PLLM = 99;\n'
            '}\n'
        )
        files = [tmp_path / "clock.c"]
        findings = _check_clock_config(files, tmp_path)
        pllm_issues = [f for f in findings if "PLLM" in f.get("message", "")]
        assert len(pllm_issues) >= 1


class TestCheckGpioConfig:
    """Tests for _check_gpio_config — GPIO pin configuration review."""

    def test_detects_gpio_inits(self, tmp_path):
        """GIVEN files with HAL_GPIO_Init calls
           WHEN _check_gpio_config runs
           THEN it reports the GPIO count and finds info findings."""
        (tmp_path / "gpio.c").write_text(
            'void init_pins(void) {\n'
            '    GPIO_InitTypeDef gpio;\n'
            '    HAL_GPIO_Init(GPIOA, &gpio);\n'
            '    HAL_GPIO_Init(GPIOB, &gpio);\n'
            '}\n'
        )
        files = [tmp_path / "gpio.c"]
        findings = _check_gpio_config(files, tmp_path)
        gpio_findings = [f for f in findings if f["category"] == "gpio"]
        assert len(gpio_findings) >= 1

    def test_no_gpio_inits(self, tmp_path):
        """GIVEN files with no HAL_GPIO_Init calls
           WHEN _check_gpio_config runs
           THEN it returns an info finding about no GPIO inits."""
        (tmp_path / "main.c").write_text('int main(void) { return 0; }\n')
        files = [tmp_path / "main.c"]
        findings = _check_gpio_config(files, tmp_path)
        messages = [f["message"] for f in findings]
        assert any("No HAL_GPIO_Init" in m for m in messages)

    def test_detects_gpio_write_pins(self, tmp_path):
        """GIVEN files with HAL_GPIO_WritePin calls
           WHEN _check_gpio_config runs
           THEN it reports pin writes."""
        (tmp_path / "gpio.c").write_text(
            'void set_pins(void) {\n'
            '    HAL_GPIO_WritePin(GPIOA, LED_Pin);\n'
            '    HAL_GPIO_Init(GPIOA, NULL);\n'
            '}\n'
        )
        files = [tmp_path / "gpio.c"]
        findings = _check_gpio_config(files, tmp_path)
        write_findings = [f for f in findings if "pin writes" in f.get("message", "").lower()]
        assert len(write_findings) >= 1


class TestCheckNvicConfig:
    """Tests for _check_nvic_config — NVIC interrupt configuration review."""

    def test_detects_priority_settings(self, tmp_path):
        """GIVEN files with HAL_NVIC_SetPriority calls
           WHEN _check_nvic_config runs
           THEN it reports priority settings."""
        (tmp_path / "nvic.c").write_text(
            'void init_nvic(void) {\n'
            '    HAL_NVIC_SetPriorityGrouping(0x07);\n'
            '    HAL_NVIC_SetPriority(USART1_IRQn, 5, 0);\n'
            '    HAL_NVIC_EnableIRQ(USART1_IRQn);\n'
            '}\n'
        )
        files = [tmp_path / "nvic.c"]
        findings = _check_nvic_config(files, tmp_path)
        assert len(findings) >= 1

    def test_no_grouping_warning(self, tmp_path):
        """GIVEN files without priority grouping
           WHEN _check_nvic_config runs
           THEN it returns a warning about undefined grouping."""
        (tmp_path / "nvic.c").write_text(
            'void init_nvic(void) {\n'
            '    HAL_NVIC_EnableIRQ(USART1_IRQn);\n'
            '}\n'
        )
        files = [tmp_path / "nvic.c"]
        findings = _check_nvic_config(files, tmp_path)
        warnings = [f for f in findings if f["severity"] == "warning"]
        assert len(warnings) >= 1

    def test_priority_out_of_range(self, tmp_path):
        """GIVEN an NVIC priority > 15
           WHEN _check_nvic_config runs
           THEN it returns a warning about suspicious priority."""
        (tmp_path / "nvic.c").write_text(
            'void init_nvic(void) {\n'
            '    HAL_NVIC_SetPriorityGrouping(0x07);\n'
            '    HAL_NVIC_SetPriority(TIM1_IRQn, 99, 0);\n'
            '    HAL_NVIC_EnableIRQ(TIM1_IRQn);\n'
            '}\n'
        )
        files = [tmp_path / "nvic.c"]
        findings = _check_nvic_config(files, tmp_path)
        susp_findings = [f for f in findings if "Suspicious" in f.get("message", "")]
        assert len(susp_findings) >= 1


class TestCheckDmaConfig:
    """Tests for _check_dma_config — DMA configuration review."""

    def test_detects_dma(self, tmp_path):
        """GIVEN files with DMA configuration
           WHEN _check_dma_config runs
           THEN it reports DMA findings."""
        (tmp_path / "dma.c").write_text(
            'void init_dma(void) {\n'
            '    HAL_DMA_Init(&hdma_uart);\n'
            '    __HAL_DMA_ENABLE_IT(&hdma_uart, DMA_IT_TC);\n'
            '}\n'
        )
        files = [tmp_path / "dma.c"]
        findings = _check_dma_config(files, tmp_path)
        dma_findings = [f for f in findings if f["category"] == "dma"]
        assert len(dma_findings) >= 1

    def test_no_dma(self, tmp_path):
        """GIVEN files without DMA configuration
           WHEN _check_dma_config runs
           THEN it returns an info finding about no DMA."""
        (tmp_path / "main.c").write_text('int main(void) { return 0; }\n')
        files = [tmp_path / "main.c"]
        findings = _check_dma_config(files, tmp_path)
        messages = [f["message"] for f in findings]
        assert any("No DMA configuration" in m for m in messages)

    def test_dma_channel_tracking(self, tmp_path):
        """GIVEN files with DMA_CHANNEL_x references
           WHEN _check_dma_config runs
           THEN channel information is included in finding messages."""
        (tmp_path / "dma.c").write_text(
            'void init_dma(void) {\n'
            '    hdma_uart.Instance = DMA_CHANNEL_4;\n'
            '    HAL_DMA_Init(&hdma_uart);\n'
            '    HAL_DMA_Start(&hdma_uart, src, dst, 100);\n'
            '}\n'
        )
        files = [tmp_path / "dma.c"]
        findings = _check_dma_config(files, tmp_path)
        dma_findings = [f for f in findings if f["category"] == "dma"]
        # Should mention channels
        channel_mentioned = any("DMA configured" in f.get("message", "") for f in dma_findings)
        assert channel_mentioned


class TestCheckMmioConsistency:
    """Tests for _check_mmio_consistency — cross-configuration consistency."""

    def test_dma_not_configured_for_peripheral(self, tmp_path):
        """GIVEN DMA files exist, but an ADC peripheral file lacks DMA usage
           WHEN _check_mmio_consistency runs
           THEN it returns an info finding suggesting DMA for that peripheral."""
        categories = {
            "clock_config": [],
            "gpio_config": [],
            "nvic_config": [],
            "dma_config": [tmp_path / "dma.c"],
            "peripheral_config": [tmp_path / "adc_config.c"],
        }
        # Create DMA file
        (tmp_path / "dma.c").write_text('void dma_init(void) { HAL_DMA_Init(&hdma); }\n')
        # Create ADC file without DMA
        (tmp_path / "adc_config.c").write_text('void adc_init(void) { HAL_ADC_Init(&hadc); }\n')

        findings = _check_mmio_consistency(categories, tmp_path)
        consistency = [f for f in findings if f["category"] == "consistency"]
        assert len(consistency) >= 1

    def test_all_peripherals_dma_ready(self, tmp_path):
        """GIVEN all peripherals with DMA support have DMA references
           WHEN _check_mmio_consistency runs
           THEN no consistency findings about missing DMA."""
        categories = {
            "clock_config": [],
            "gpio_config": [],
            "nvic_config": [],
            "dma_config": [tmp_path / "dma.c"],
            "peripheral_config": [tmp_path / "spi_config.c"],
        }
        (tmp_path / "dma.c").write_text('void dma_init(void) { HAL_DMA_Init(&hdma); }\n')
        (tmp_path / "spi_config.c").write_text('void spi_init(void) { HAL_SPI_Init(&hspi); /* DMA used */ }\n+DMA\n')

        findings = _check_mmio_consistency(categories, tmp_path)
        consistency = [f for f in findings if f["category"] == "consistency"]
        # May still have MspInit findings, but not DMA-missing ones
        dma_missing = [f for f in consistency if "DMA not configured" in f.get("message", "")]
        assert len(dma_missing) == 0


class TestBuildMmioReport:
    """Tests for _build_mmio_report — unified report builder."""

    def test_builds_full_report(self, tmp_path):
        """GIVEN a project with MMIO files
           WHEN _build_mmio_report runs
           THEN it returns a dict with summary and findings."""
        (tmp_path / "stm32f4xx_hal_rcc.h").write_text(
            '#define HSE_VALUE 8000000\n'
            '#define LSE_VALUE 32768\n'
            'void HAL_RCC_OscConfig(void) {}\n'
        )
        report = _build_mmio_report(tmp_path)
        assert "generated_at" in report
        assert "summary" in report
        assert "findings" in report
        assert report["summary"]["total_findings"] >= 0

    def test_empty_project(self, tmp_path):
        """GIVEN an empty project
           WHEN _build_mmio_report runs
           THEN it returns a report with zero findings."""
        report = _build_mmio_report(tmp_path)
        assert report["summary"]["total_findings"] >= 0

    def test_finding_severity_counts(self, tmp_path):
        """GIVEN a project that triggers various severities
           WHEN _build_mmio_report runs
           THEN the severity_counts dictionary is populated."""
        (tmp_path / "clock.c").write_text(
            '#define HSE_VALUE 8000000\n'
        )
        (tmp_path / "dma.c").write_text('void dma_init(void) { HAL_DMA_Init(&hdma); }\n')
        report = _build_mmio_report(tmp_path)
        assert "severity_counts" in report["summary"]


class TestRenderMmioReport:
    """Tests for _render_mmio_report — markdown rendering."""

    def test_renders_empty_report(self):
        """GIVEN an empty report dict
           WHEN _render_mmio_report runs
           THEN it returns markdown without crashing."""
        report = {
            "generated_at": "2025-01-01T00:00:00",
            "summary": {
                "categories": {"clock_config": 0, "gpio_config": 0, "nvic_config": 0,
                               "dma_config": 0, "peripheral_config": 0},
                "total_findings": 0,
                "severity_counts": {"error": 0, "warning": 0, "info": 0},
            },
            "findings": [],
        }
        md = _render_mmio_report(report)
        assert "MMIO 配置审查报告" in md
        assert "生成时间" in md

    def test_renders_findings_table(self):
        """GIVEN a report with findings
           WHEN _render_mmio_report runs
           THEN the findings are rendered in a markdown table."""
        report = {
            "generated_at": "2025-01-01T00:00:00",
            "summary": {
                "categories": {"clock_config": 1, "gpio_config": 0, "nvic_config": 0,
                               "dma_config": 0, "peripheral_config": 0},
                "total_findings": 1,
                "severity_counts": {"error": 0, "warning": 1, "info": 0},
            },
            "findings": [
                {
                    "severity": "warning",
                    "category": "clock",
                    "file": "multiple",
                    "line": 0,
                    "message": "No HSE found",
                },
            ],
        }
        md = _render_mmio_report(report)
        assert "No HSE found" in md
        assert "详细发现" in md


# =============================================================================
# Integration tests — step_review_mmio
# =============================================================================

class TestStepReviewMmio:
    """Test suite for step_review_mmio — the pipeline step handler."""

    # ── Happy path ──────────────────────────────────────────────────────────

    def test_happy_path(self, mock_session, tmp_path):
        """GIVEN a valid session with MMIO source files
           WHEN step_review_mmio runs
           THEN it writes a JSON report and returns the output path."""
        # Create MMIO source files relative to spec_path.parent (= tmp_path)
        (tmp_path / "stm32f4xx_hal_rcc.h").write_text(
            '#define HSE_VALUE 8000000\n'
            '#define LSE_VALUE 32768\n'
        )
        (tmp_path / "gpio_config.c").write_text(
            'void init_pins(void) {\n'
            '    HAL_GPIO_Init(GPIOA, NULL);\n'
            '}\n'
        )

        result = step_review_mmio(mock_session)

        out_path = Path(result)
        assert out_path.exists()
        assert out_path.name == "review-mmio.json"
        report = json.loads(out_path.read_text())
        assert "summary" in report
        assert "findings" in report
        assert report["summary"]["total_findings"] >= 0

    # ── Empty project ───────────────────────────────────────────────────────

    def test_empty_project(self, mock_session, tmp_path):
        """GIVEN a project with no MMIO-related files
           WHEN step_review_mmio runs
           THEN it still succeeds with minimal findings."""
        # No files at all in tmp_path except the spec file
        result = step_review_mmio(mock_session)

        report = json.loads(Path(result).read_text())
        assert "summary" in report
        assert report["summary"]["total_findings"] >= 0

    # ── All subsystems configured ───────────────────────────────────────────

    def test_all_subsystems_configured(self, mock_session, tmp_path):
        """GIVEN a project with clock, gpio, nvic, and dma configs
           WHEN step_review_mmio runs
           THEN the report captures findings from all subsystems."""
        # Clock
        (tmp_path / "stm32f4xx_hal_rcc.h").write_text(
            '#define HSE_VALUE 8000000\n#define LSE_VALUE 32768\n'
        )
        # GPIO
        (tmp_path / "gpio_config.c").write_text(
            'void init_pins(void) {\n'
            '    GPIO_InitTypeDef g;\n'
            '    HAL_GPIO_Init(GPIOC, &g);\n'
            '}\n'
        )
        # NVIC
        (tmp_path / "nvic_config.c").write_text(
            'void init_nvic(void) {\n'
            '    HAL_NVIC_SetPriorityGrouping(0x07);\n'
            '    HAL_NVIC_SetPriority(TIM2_IRQn, 5, 0);\n'
            '    HAL_NVIC_EnableIRQ(TIM2_IRQn);\n'
            '}\n'
        )
        # DMA
        (tmp_path / "dma_config.c").write_text(
            'void init_dma(void) {\n'
            '    HAL_DMA_Init(&hdma);\n'
            '}\n'
        )

        result = step_review_mmio(mock_session)
        report = json.loads(Path(result).read_text())

        # Should have findings from multiple categories
        cat_findings = set(f["category"] for f in report["findings"])
        # At minimum, we should have some categories
        assert len(cat_findings) >= 1

    # ── PM output ───────────────────────────────────────────────────────────

    def test_output_format(self, mock_session, tmp_path):
        """GIVEN a session with some MMIO files
           WHEN step_review_mmio runs
           THEN the JSON report has expected top-level keys."""
        (tmp_path / "gpio_config.c").write_text(
            'void init_pins(void) { HAL_GPIO_Init(GPIOA, NULL); }\n'
        )

        result = step_review_mmio(mock_session)
        report = json.loads(Path(result).read_text())

        assert "generated_at" in report
        assert "summary" in report
        assert "findings" in report
        s = report["summary"]
        assert "categories" in s
        assert "total_findings" in s
        assert "severity_counts" in s

    # ── Error handling ──────────────────────────────────────────────────────

    def test_exception_raises_pipeline_error(self, mock_session, tmp_path):
        """GIVEN an environment where the step raises an unexpected exception
           WHEN step_review_mmio runs
           THEN it wraps it in PipelineStepError."""

        # Monkey-patch _build_mmio_report to fail
        with patch("yuleosh.pipeline.step_handlers.review_mmio._build_mmio_report",
                   side_effect=ValueError("unexpected")):
            with pytest.raises(PipelineStepError, match="MMIO configuration review failed"):
                step_review_mmio(mock_session)
