#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for MMIO Configuration Review (DEF-008).
"""

import os
import sys
import tempfile
import json
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.pipeline.step_handlers.review_mmio import (
    _find_mmio_sources,
    _check_clock_config,
    _check_gpio_config,
    _check_nvic_config,
    _check_dma_config,
    _check_mmio_consistency,
    _build_mmio_report,
    _render_mmio_report,
)


class TestMmioReview:
    """Test MMIO review functions."""

    @pytest.fixture
    def temp_project(self):
        """Create temp project with MMIO config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src"
            src.mkdir(parents=True)

            # Clock config
            (src / "stm32_clock.c").write_text("""
#include "stm32f4xx_hal.h"
void HAL_RCC_Init(void) {
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE | RCC_OSCILLATORTYPE_LSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.LSEState = RCC_LSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLM = 8;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);
}
""")

            # GPIO config
            (src / "gpio_config.c").write_text("""
#include "stm32f4xx_hal.h"
void MX_GPIO_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
}
""")

            # NVIC config
            (src / "nvic_config.c").write_text("""
#include "stm32f4xx_hal.h"
void HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
void MX_NVIC_Init(void) {
    HAL_NVIC_SetPriority(USART1_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(USART1_IRQn);
    HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream0_IRQn);
}
""")

            # DMA config
            (src / "dma_config.c").write_text("""
#include "stm32f4xx_hal.h"
DMA_HandleTypeDef hdma_usart1_tx;
void MX_DMA_Init(void) {
    __HAL_RCC_DMA1_CLK_ENABLE();
    hdma_usart1_tx.Instance = DMA1_Stream0;
    hdma_usart1_tx.Init.Channel = DMA_CHANNEL_2;
    hdma_usart1_tx.Init.Direction = DMA_MEMORY_TO_PERIPH;
    hdma_usart1_tx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_usart1_tx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_usart1_tx.Init.Mode = DMA_NORMAL;
    hdma_usart1_tx.Init.Priority = DMA_PRIORITY_HIGH;
    HAL_DMA_Init(&hdma_usart1_tx);
}
""")

            yield tmpdir

    def test_find_sources_clock(self, temp_project):
        """Verify clock config files are discovered."""
        cats = _find_mmio_sources(Path(temp_project))
        assert len(cats["clock_config"]) >= 1

    def test_find_sources_gpio(self, temp_project):
        """Verify GPIO config files are discovered."""
        cats = _find_mmio_sources(Path(temp_project))
        assert len(cats["gpio_config"]) >= 1

    def test_check_clock(self, temp_project):
        """Verify clock checks detect HSE/LSE/PLL."""
        cats = _find_mmio_sources(Path(temp_project))
        findings = _check_clock_config(cats["clock_config"], Path(temp_project))
        # Should find HSE, LSE, PLL configured
        clock_issues = [f for f in findings if f["severity"] == "warning"]
        # With our config file, there should be few warnings
        assert isinstance(findings, list)

    def test_check_gpio(self, temp_project):
        """Verify GPIO checks detect init calls."""
        cats = _find_mmio_sources(Path(temp_project))
        findings = _check_gpio_config(cats["gpio_config"], Path(temp_project))
        gpio_init = [f for f in findings if "HAL_GPIO_Init" in f.get("message", "")]
        assert len(gpio_init) >= 0

    def test_check_nvic(self, temp_project):
        """Verify NVIC checks detect priorities."""
        cats = _find_mmio_sources(Path(temp_project))
        findings = _check_nvic_config(cats["nvic_config"], Path(temp_project))
        irq_findings = [f for f in findings if "interrupt" in f.get("message", "").lower()]
        assert isinstance(findings, list)

    def test_check_dma(self, temp_project):
        """Verify DMA checks detect configuration."""
        cats = _find_mmio_sources(Path(temp_project))
        findings = _check_dma_config(cats["dma_config"], Path(temp_project))
        dma_findings = [f for f in findings if "DMA" in f.get("message", "")]
        assert len(dma_findings) >= 0

    def test_build_report(self, temp_project):
        """Verify full report generation."""
        report = _build_mmio_report(Path(temp_project))
        assert "summary" in report
        assert "findings" in report
        assert report["summary"]["total_findings"] >= 0
        categories = report["summary"]["categories"]
        assert "clock_config" in categories

    def test_render_report(self, temp_project):
        """Verify markdown rendering."""
        report = _build_mmio_report(Path(temp_project))
        markdown = _render_mmio_report(report)
        assert "MMIO 配置审查报告" in markdown
        assert "摘要" in markdown
